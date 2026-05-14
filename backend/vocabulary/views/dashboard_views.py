"""
Dashboard views — adapted from v1 with updated FK paths.

Changes from v1:
- UserMeaningMastery → UserWordProgress
- meaning__questions → word__questions
- meaning.term.term_text → word.text
- teacher role check allows ADMIN too
"""
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from users.models import CustomUser
from ..models import UserWordProgress, MasteryLevel, UserAnswer, MasteryLevelLog
from ..permissions import IsStudent, IsTeacherOrAdmin
from ..serializers import WordSerializer, RosterDashboardSerializer
from ..services.dashboard_service import DashboardService
from ..utils import end_of_local_day


class StudentDashboardView(APIView):
    permission_classes = [IsAuthenticated, IsStudent]

    def get(self, request, *args, **kwargs):
        student = request.user
        today = timezone.localdate()
        due_cutoff = end_of_local_day(today)

        lexile_filter = Q(
            word__questions__lexile_score__gte=student.lexile_min,
            word__questions__lexile_score__lte=student.lexile_max,
        ) | Q(
            word__questions__lexile_score__isnull=True,
        )

        # Words answered today — exclude from due count so practiced words don't reappear
        answered_word_ids_today = set(
            UserAnswer.objects.filter(
                user=student, answered_at__date=today,
            ).values_list('question__word_id', flat=True)
        )

        words_due_qs = UserWordProgress.objects.filter(
            user=student,
            next_review_at__lte=due_cutoff,
            instructional_status='READY',
        ).filter(lexile_filter).distinct()

        if answered_word_ids_today:
            words_due_qs = words_due_qs.exclude(word_id__in=answered_word_ids_today)

        words_due_count = words_due_qs.count()

        total_words_count = UserWordProgress.objects.filter(user=student).count()
        questions_answered_today = UserAnswer.objects.filter(
            user=student, answered_at__date=today,
        ).count()

        # Streak logic
        if student.last_practice_date and student.last_practice_date < (today - timedelta(days=1)):
            if student.streak_freezes_available > 0:
                student.streak_freezes_available -= 1
                student.last_practice_date = today - timedelta(days=1)
                student.save(update_fields=['streak_freezes_available', 'last_practice_date'])
            else:
                student.current_practice_streak = 0
                student.save(update_fields=['current_practice_streak'])

        # Mastery breakdown with deltas
        current_counts = list(MasteryLevel.objects.filter(is_hidden=False).annotate(
            word_count=Count('userwordprogress', filter=Q(userwordprogress__user=student)),
        ).values('level_id', 'level_name', 'word_count').order_by('level_id'))
        mastered_level_id = MasteryLevel.objects.filter(
            is_hidden=False,
        ).order_by('-level_id').values_list('level_id', flat=True).first()
        hidden_level_ids = set(
            MasteryLevel.objects.filter(is_hidden=True).values_list('level_id', flat=True)
        )

        if mastered_level_id:
            hidden_word_count = UserWordProgress.objects.filter(
                user=student, level__is_hidden=True,
            ).count()
            for item in current_counts:
                if item['level_id'] == mastered_level_id:
                    item['word_count'] += hidden_word_count
                    break

        deltas = {item['level_id']: {'today': 0, 'week': 0} for item in current_counts}

        now = timezone.now()
        start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_week = start_of_today - timedelta(days=start_of_today.weekday())

        recent_logs = MasteryLevelLog.objects.filter(
            user=student, timestamp__gte=start_of_week,
        ).select_related('old_level', 'new_level')

        def display_level_id(level):
            if level.level_id in hidden_level_ids:
                return mastered_level_id
            return level.level_id

        for log in recent_logs:
            new_level_id = display_level_id(log.new_level)
            old_level_id = display_level_id(log.old_level)
            if new_level_id == old_level_id:
                continue
            if new_level_id in deltas:
                deltas[new_level_id]['week'] += 1
            if old_level_id in deltas:
                deltas[old_level_id]['week'] -= 1
            if log.timestamp >= start_of_today:
                if new_level_id in deltas:
                    deltas[new_level_id]['today'] += 1
                if old_level_id in deltas:
                    deltas[old_level_id]['today'] -= 1

        mastery_breakdown = [
            {
                'level_id': item['level_id'],
                'level_name': item['level_name'],
                'word_count': item['word_count'],
                'delta_today': deltas[item['level_id']]['today'],
                'delta_week': deltas[item['level_id']]['week'],
            }
            for item in current_counts
        ]

        remaining_slots = student.daily_question_limit - questions_answered_today
        session_goal_total = max(0, min(words_due_count, remaining_slots))

        return Response({
            "words_due_today": session_goal_total,
            "total_words": total_words_count,
            "practice_streak": student.current_practice_streak,
            "streak_freezes_available": student.streak_freezes_available,
            "mastery_breakdown": mastery_breakdown,
            "questions_answered_today": questions_answered_today,
            "daily_question_limit": student.daily_question_limit,
            "daily_goal_min": student.daily_goal_min,
            "daily_goal_max": student.daily_goal_max,
            "last_goal_prompt_date": student.last_goal_prompt_date,
            "session_goal_total": session_goal_total,
        })


class StudentGoalPromptView(APIView):
    permission_classes = [IsAuthenticated, IsStudent]

    def post(self, request, *args, **kwargs) -> Response:
        student = request.user
        student.last_goal_prompt_date = timezone.localdate()
        student.save(update_fields=['last_goal_prompt_date'])
        return Response({"recorded": True})


class StudentProgressDashboardView(APIView):
    permission_classes = [IsAuthenticated, IsTeacherOrAdmin]

    def get(self, request, student_id, *args, **kwargs):
        teacher = request.user
        try:
            student = teacher.students.get(id=student_id)
        except CustomUser.DoesNotExist:
            return Response(
                {'error': 'Student not found or not assigned to you.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        response_data = DashboardService.get_student_progress(student)
        return Response(response_data)


class WordsByLevelView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, level_id, *args, **kwargs):
        mastered_level_id = MasteryLevel.objects.filter(
            is_hidden=False,
        ).order_by('-level_id').values_list('level_id', flat=True).first()
        level_filter = Q(level__level_id=level_id, level__is_hidden=False)
        if level_id == mastered_level_id:
            level_filter |= Q(level__is_hidden=True)

        mastery_records = UserWordProgress.objects.filter(
            level_filter,
            user=request.user,
        ).select_related('word').prefetch_related('word__definitions')

        words = [record.word for record in mastery_records]
        serializer = WordSerializer(words, many=True, context={'request': request})
        return Response(serializer.data)


class LearningPatternsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, student_id=None, *args, **kwargs):
        requesting_user = request.user

        if requesting_user.role == CustomUser.Role.STUDENT:
            target_student = requesting_user
        elif requesting_user.role in (CustomUser.Role.TEACHER, CustomUser.Role.ADMIN):
            if not student_id:
                return Response(
                    {'error': 'Student ID is required for teachers.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                target_student = requesting_user.students.get(id=student_id)
            except CustomUser.DoesNotExist:
                return Response(
                    {'error': 'Student not found or not assigned to you.'},
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            return Response(
                {'error': 'Could not identify a student for this report.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        response_data = DashboardService.get_learning_patterns(target_student)
        return Response(response_data)


class RosterDashboardView(APIView):
    permission_classes = [IsAuthenticated, IsTeacherOrAdmin]

    def get(self, request, *args, **kwargs):
        group_id = request.query_params.get('group_id')
        final_data = DashboardService.get_roster_dashboard(request.user, group_id)
        serializer = RosterDashboardSerializer(final_data)
        return Response(serializer.data)
