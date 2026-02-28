"""
Dashboard views — adapted from v1 with updated FK paths.

Changes from v1:
- UserMeaningMastery → UserWordProgress
- meaning__questions → word__questions
- meaning.term.term_text → word.text
- teacher role check allows ADMIN too
"""
from datetime import date, timedelta

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


class StudentDashboardView(APIView):
    permission_classes = [IsAuthenticated, IsStudent]

    def get(self, request, *args, **kwargs):
        student = request.user
        today = date.today()

        lexile_filter = Q(
            word__questions__lexile_score__gte=student.lexile_min,
            word__questions__lexile_score__lte=student.lexile_max,
        ) | Q(
            word__questions__lexile_score__isnull=True,
        )

        words_due_count = UserWordProgress.objects.filter(
            user=student,
            next_review_date__lte=today,
            instructional_status='READY',
        ).filter(lexile_filter).distinct().count()

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
        current_counts = list(MasteryLevel.objects.annotate(
            word_count=Count('userwordprogress', filter=Q(userwordprogress__user=student)),
        ).values('level_id', 'level_name', 'word_count').order_by('level_id'))

        deltas = {item['level_id']: {'today': 0, 'week': 0} for item in current_counts}

        now = timezone.now()
        start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_week = start_of_today - timedelta(days=start_of_today.weekday())

        recent_logs = MasteryLevelLog.objects.filter(
            user=student, timestamp__gte=start_of_week,
        ).select_related('old_level', 'new_level')

        for log in recent_logs:
            if log.new_level.level_id in deltas:
                deltas[log.new_level.level_id]['week'] += 1
            if log.old_level.level_id in deltas:
                deltas[log.old_level.level_id]['week'] -= 1
            if log.timestamp >= start_of_today:
                if log.new_level.level_id in deltas:
                    deltas[log.new_level.level_id]['today'] += 1
                if log.old_level.level_id in deltas:
                    deltas[log.old_level.level_id]['today'] -= 1

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
            "session_goal_total": session_goal_total,
        })


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
        mastery_records = UserWordProgress.objects.filter(
            user=request.user, level__level_id=level_id,
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
