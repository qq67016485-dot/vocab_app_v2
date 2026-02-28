"""
Practice views — adapted from v1 with updated FK paths.

Changes from v1:
- UserMeaningMastery → UserWordProgress
- meaning__questions → word__questions
- meaning.term.term_text → word.text
"""
import random
from datetime import date, datetime
from collections import defaultdict

from django.db import transaction
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from users.models import CustomUser
from ..models import UserWordProgress, Question, UserAnswer
from ..serializers import QuestionSerializer
from ..services.practice_service import PracticeService
from ..constants import QUESTION_TYPE_TO_SKILL_TAG


class NextPracticeWordView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        today = date.today()

        answer_count_today = UserAnswer.objects.filter(
            user=user, answered_at__date=today,
        ).count()

        if answer_count_today >= user.daily_question_limit:
            return Response({
                "message": f"You have reached your daily practice limit of {user.daily_question_limit} questions. Great work!",
            })

        due_records = UserWordProgress.objects.select_related(
            'word', 'level',
        ).filter(
            user=user,
            next_review_date__lte=today,
            instructional_status='READY',
        ).filter(
            word__questions__lexile_score__gte=user.lexile_min,
            word__questions__lexile_score__lte=user.lexile_max,
        ).distinct().order_by('next_review_date')

        if not due_records.exists():
            return Response({
                "message": "No words with suitable questions are due for review today. Great work!",
            })

        next_record = due_records.first()
        word = next_record.word
        current_level = next_record.level

        question = Question.objects.filter(
            word=word,
            lexile_score__gte=user.lexile_min,
            lexile_score__lte=user.lexile_max,
            suitable_levels=current_level,
        ).order_by('?').first()

        if not question:
            question = Question.objects.filter(
                word=word,
                lexile_score__gte=user.lexile_min,
                lexile_score__lte=user.lexile_max,
            ).order_by('?').first()

        if not question:
            return Response({
                "error": f"Could not find any suitable question for '{word.text}'.",
            }, status=status.HTTP_404_NOT_FOUND)

        reason_category = None
        if not next_record.last_reviewed_at:
            reason_category = "NEW_WORD"
        else:
            recent_answers = UserAnswer.objects.filter(
                user=user, question__word=word,
            ).order_by('-answered_at')[:2]
            if any(not answer.is_correct for answer in recent_answers):
                reason_category = "STRUGGLE_WORD"
            else:
                points_to_promote = next_record.level.points_to_promote
                if next_record.level.level_id >= 4 and next_record.mastery_points >= points_to_promote - 1:
                    reason_category = "MASTERY_CHECK"
                elif random.randint(1, 3) == 1:
                    reason_category = "STANDARD_REVIEW"

        serializer = QuestionSerializer(question)
        response_data = serializer.data
        response_data['reason_category'] = reason_category
        return Response(response_data)


class SubmitAnswerView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        question_id = request.data.get('question_id')
        user_answer = request.data.get('user_answer')
        duration_seconds = request.data.get('duration_seconds', 0)
        answer_switches = request.data.get('answer_switches', 0)

        if not question_id or user_answer is None:
            return Response(
                {'error': 'Missing question_id or user_answer'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            response_data = PracticeService.process_answer(
                request.user, question_id, user_answer,
                duration_seconds, answer_switches,
            )
            return Response(response_data)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_404_NOT_FOUND)


class SessionSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        start_time_str = request.data.get('start_time')
        if not start_time_str:
            return Response(
                {"error": "start_time is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            start_time = datetime.fromisoformat(start_time_str)
        except ValueError:
            return Response(
                {"error": "Invalid start_time format."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        session_answers = UserAnswer.objects.filter(
            user=request.user, answered_at__gte=start_time,
        ).select_related('question__word')

        if not session_answers.exists():
            return Response({
                "total_practiced": 0,
                "strengths": [],
                "weaknesses": [],
            })

        strengths = set()
        weaknesses_data = defaultdict(
            lambda: {'term': '', 'skill_tags': set()},
        )

        for answer in session_answers:
            word = answer.question.word
            if answer.is_correct:
                strengths.add(word.text)
            else:
                weaknesses_data[word.id]['term'] = word.text
                skill_tag = QUESTION_TYPE_TO_SKILL_TAG.get(
                    answer.question.question_type, 'other',
                )
                weaknesses_data[word.id]['skill_tags'].add(skill_tag)

        final_weaknesses = [
            {
                'term': data['term'],
                'skill_tags': list(data['skill_tags']),
            }
            for data in weaknesses_data.values()
        ]

        final_strengths = list(
            strengths - {data['term'] for data in final_weaknesses},
        )

        return Response({
            "total_practiced": len(
                strengths | {data['term'] for data in final_weaknesses},
            ),
            "strengths": final_strengths[:5],
            "weaknesses": final_weaknesses[:5],
        })


class ApplySessionBonusesView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        max_focus_streak = request.data.get('max_focus_streak', 0)
        try:
            max_focus_streak = int(max_focus_streak)
        except (TypeError, ValueError):
            return Response(
                {"error": "Invalid max_focus_streak provided."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if max_focus_streak < 0:
            return Response(
                {"error": "Invalid max_focus_streak provided."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        focus_streak_bonus = min(max_focus_streak, 10)
        if focus_streak_bonus > 0:
            with transaction.atomic():
                user = CustomUser.objects.select_for_update().get(pk=request.user.pk)
                PracticeService.update_xp_and_level(user, focus_streak_bonus)

        return Response({
            "success": f"{focus_streak_bonus} bonus XP applied successfully.",
        })
