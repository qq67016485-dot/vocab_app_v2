"""
Practice views — adapted from v1 with updated FK paths.

Changes from v1:
- UserMeaningMastery → UserWordProgress
- meaning__questions → word__questions
- meaning.term.term_text → word.text
"""
import random
from datetime import datetime, timedelta, timezone as dt_timezone
from collections import defaultdict

from django.core.cache import cache
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from users.models import CustomUser
from ..models import UserWordProgress, Question, UserAnswer
from ..serializers import QuestionSerializer
from ..services.practice_service import PracticeService, DailyLimitReached
from ..services import sentence_evaluation_service
from ..constants import QUESTION_TYPE_TO_SKILL_TAG
from ..utils import end_of_local_day, start_of_local_day

SENTENCE_WRITE_TYPES = (
    Question.QuestionType.SENTENCE_WRITE_GUIDED,
    Question.QuestionType.SENTENCE_WRITE_OPEN,
)

# Max revisions per variant (initial attempt + this many retries) — mirrors
# QuestionSerializer._MAX_REVISIONS. Guided (L4) gets more scaffolding room.
_MAX_REVISIONS = {
    Question.QuestionType.SENTENCE_WRITE_GUIDED: 3,
    Question.QuestionType.SENTENCE_WRITE_OPEN: 2,
}


class NextPracticeWordView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        today = timezone.localdate()
        due_cutoff = end_of_local_day(today)

        # Range filter, not answered_at__date: the __date lookup is non-sargable
        # on MySQL (DATE(CONVERT_TZ(...))) and scans the full answer history.
        answer_count_today = UserAnswer.objects.filter(
            user=user, answered_at__gte=start_of_local_day(today),
        ).count()

        if answer_count_today >= user.daily_question_limit:
            return Response({
                "message": f"You have reached your daily practice limit of {user.daily_question_limit} questions. Great work!",
            })

        # Exclude words already answered in this session
        session_start = request.query_params.get('session_start')
        answered_word_ids = set()
        if session_start:
            try:
                session_dt = datetime.fromisoformat(session_start.replace('Z', '+00:00'))
                answered_word_ids = set(
                    UserAnswer.objects.filter(
                        user=user,
                        answered_at__gte=session_dt,
                    ).values_list('question__word_id', flat=True)
                )
            except (ValueError, TypeError):
                pass

        lexile_q = Q(lexile_score__isnull=True) | Q(
            lexile_score__gte=user.lexile_min,
            lexile_score__lte=user.lexile_max,
        )

        # EXISTS subquery instead of a join + DISTINCT: the join multiplies each
        # progress row by its ~30-60 questions and forces a dedup-sort; EXISTS
        # probes the questions index per candidate row only.
        has_suitable_question = Question.objects.filter(
            lexile_q, word=OuterRef('word_id'),
        )

        due_records = UserWordProgress.objects.select_related(
            'word', 'level',
        ).filter(
            user=user,
            next_review_at__lte=due_cutoff,
            instructional_status='READY',
        ).filter(Exists(has_suitable_question)).order_by('next_review_at')

        if answered_word_ids:
            due_records = due_records.exclude(word_id__in=answered_word_ids)

        next_record = due_records.first()
        if next_record is None:
            return Response({
                "message": "No words with suitable questions are due for review today. Great work!",
            })

        # Availability probe (session-goal "keep going?" check): the caller only
        # needs to know whether anything is due — skip question selection.
        if request.query_params.get('peek'):
            return Response({'available': True})

        word = next_record.word
        current_level = next_record.level

        # Sentence-writing (LLM-judged) questions are excluded when the judge is
        # unhealthy (student still gets a receptive question) or when this word
        # served one in the immediately previous answer (avoid back-to-back
        # high-effort tasks).
        exclude_sentence_write = not sentence_evaluation_service.is_judge_healthy()
        if not exclude_sentence_write:
            last_answer = (
                UserAnswer.objects.filter(user=user, question__word=word)
                .order_by('-answered_at')
                .values_list('question__question_type', flat=True)
                .first()
            )
            if last_answer in SENTENCE_WRITE_TYPES:
                exclude_sentence_write = True

        def _pick_question(base_qs):
            # select_related covers the serializer's word.text and
            # word.primer_content reads (avoids two lazy queries per response).
            qs = base_qs.filter(lexile_q).select_related(
                'word', 'word__primer_content',
            )
            if exclude_sentence_write:
                qs = qs.exclude(question_type__in=SENTENCE_WRITE_TYPES)
            return qs.order_by('?').first()

        if current_level.is_hidden:
            question = _pick_question(Question.objects.filter(word=word))
        else:
            question = _pick_question(
                Question.objects.filter(word=word, suitable_levels=current_level)
            )
            if not question:
                question = _pick_question(Question.objects.filter(word=word))

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

    # Session key holding the server-side sentence-write attempt state:
    # {'question_id': int, 'attempts': [{sentence, hint, verdict}, ...]}.
    # Only one sentence-write loop is active at a time, so a single key that
    # resets when the question changes is enough (and self-prunes).
    _SW_SESSION_KEY = 'sw_attempts'

    # Non-terminal sentence-write misses call the judge LLM but record no
    # UserAnswer, so they escape the daily-answer counter. This per-day cache
    # counter bounds total judge invocations at daily_question_limit × the max
    # attempts a single question can legitimately consume (initial + revisions),
    # which covers honest use but caps the abandon-and-cycle cost path.
    _JUDGE_CALLS_PER_QUESTION = max(_MAX_REVISIONS.values()) + 1
    _JUDGE_COUNT_TTL = 90000  # ~25h — outlives one local day, then self-prunes

    @staticmethod
    def _typo_retry_key(user_id, question_id):
        return f'typo_retry:{user_id}:{question_id}'

    @staticmethod
    def _judge_calls_key(user_id):
        return f'sw_judge_calls:{user_id}:{timezone.localdate().isoformat()}'

    # Client-reported timing/switch telemetry feeds the response-quality
    # classifier (fast/slow/switched → review interval). Clamp to sane bounds so
    # a crafted payload can't push the scheduler outside its intended range;
    # out-of-range durations already fall through to the neutral 'solid' bucket.
    _MAX_DURATION_SECONDS = 3600
    _MAX_ANSWER_SWITCHES = 100

    @classmethod
    def _clamp_int(cls, value, low, high, default=0):
        try:
            value = int(value)
        except (TypeError, ValueError):
            return default
        return max(low, min(high, value))

    def post(self, request, *args, **kwargs):
        question_id = request.data.get('question_id')
        user_answer = request.data.get('user_answer')
        duration_seconds = self._clamp_int(
            request.data.get('duration_seconds', 0), 0, self._MAX_DURATION_SECONDS,
        )
        answer_switches = self._clamp_int(
            request.data.get('answer_switches', 0), 0, self._MAX_ANSWER_SWITCHES,
        )
        is_retry = request.data.get('is_retry', False)
        if isinstance(is_retry, str):
            is_retry = is_retry.lower() in ('true', '1')

        if not question_id or user_answer is None:
            return Response(
                {'error': 'Missing question_id or user_answer'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Sentence-writing questions are LLM-judged with a multi-turn revision
        # loop; they take a different submit path.
        try:
            question = Question.objects.select_related('word').get(id=question_id)
        except Question.DoesNotExist:
            return Response({'error': 'Question not found.'}, status=status.HTTP_404_NOT_FOUND)

        if question.question_type in SENTENCE_WRITE_TYPES:
            return self._handle_sentence_write(request, question, user_answer)

        typo_retry_key = self._typo_retry_key(request.user.id, question_id)
        had_typo_retry = False
        if not is_retry:
            had_typo_retry = bool(request.session.pop(typo_retry_key, False))

        try:
            response_data = PracticeService.process_answer(
                request.user, question_id, user_answer,
                duration_seconds, answer_switches,
                is_retry=is_retry,
                had_typo_retry=had_typo_retry,
                question=question,
            )
            if response_data.get('is_typo') and not is_retry:
                request.session[typo_retry_key] = True
                request.session.modified = True
            return Response(response_data)
        except DailyLimitReached:
            return Response({
                'daily_limit_reached': True,
                'message': f"You have reached your daily practice limit of {request.user.daily_question_limit} questions. Great work!",
            }, status=status.HTTP_429_TOO_MANY_REQUESTS)
        except ValueError as e:
            if had_typo_retry:
                request.session[typo_retry_key] = True
                request.session.modified = True
            return Response({'error': str(e)}, status=status.HTTP_404_NOT_FOUND)

    def _handle_sentence_write(self, request, question, user_answer):
        """Judge a sentence-writing attempt (server-tracked revision loop).

        Attempt state (count, hints, verdicts) is held server-side in the
        session — like the typo-retry flag — so the revision cap and the
        fragility decision cannot be reset by a client that withholds its
        attempt history. The request body's ``prior_attempts`` is ignored.

        Request extras:
          - gave_up: bool — student tapped "show me an example".

        Non-terminal miss → returns {sentence_write_pending: True, hint, ...}
        WITHOUT scoring. Terminal (correct, gave_up, or revisions exhausted) →
        calls process_answer with a productive judgment and returns the normal
        scored response plus the model sentence.
        """
        # Judged attempts respect the daily limit even though non-terminal
        # misses never record a UserAnswer — otherwise the judge LLM could be
        # called without bound.
        answers_today = UserAnswer.objects.filter(
            user=request.user,
            answered_at__gte=start_of_local_day(),
        ).count()
        if answers_today >= request.user.daily_question_limit:
            return Response({
                'sentence_write_unavailable': True,
                'message': "You've reached today's practice limit — great work!",
            })

        # Guard the judge (an LLM call) against a guessed question_id for a word
        # in a not-yet-unlocked pack — mirrors the READY check in process_answer,
        # but here it must run BEFORE the judge to avoid the cost/farming path.
        if not UserWordProgress.objects.filter(
            user=request.user, word=question.word, instructional_status='READY',
        ).exists():
            return Response(
                {'error': 'Question not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Bound total judge invocations per day (non-terminal misses don't count
        # against the daily-answer limit above). The give-up path skips this: it
        # makes no judge call.
        gave_up = bool(request.data.get('gave_up', False))
        judge_budget = request.user.daily_question_limit * self._JUDGE_CALLS_PER_QUESTION
        judge_calls_key = self._judge_calls_key(request.user.id)
        if not gave_up and (cache.get(judge_calls_key, 0) or 0) >= judge_budget:
            return Response({
                'sentence_write_unavailable': True,
                'message': "Let's come back to this one — try a different question.",
            })

        state = request.session.get(self._SW_SESSION_KEY) or {}
        if state.get('question_id') != question.id:
            state = {'question_id': question.id, 'attempts': []}
        prior_attempts = state.get('attempts') or []

        max_revisions = _MAX_REVISIONS.get(question.question_type, 2)
        revisions_used = len(prior_attempts)  # each prior attempt was one submit
        model_sentence = question.example_sentence

        # Give-up path: terminal miss, no judge call needed.
        if gave_up:
            self._clear_sw_state(request)
            judgment = {
                'is_correct': False,
                'quality_rule': 'productive_missed',
                'judge_result': {
                    'verdict': 'incorrect',
                    'error_type': 'gave_up',
                    'attempts': revisions_used + 1,
                    'gave_up': True,
                },
            }
            return self._score_sentence_write(
                request, question, user_answer, judgment,
                model_sentence=model_sentence,
            )

        # Count this judge call before making it (a failed call still cost the
        # attempt). incr() is atomic on shared caches; seed the key first since
        # incr() raises on a missing key.
        cache.add(judge_calls_key, 0, self._JUDGE_COUNT_TTL)
        try:
            cache.incr(judge_calls_key)
        except ValueError:
            cache.set(judge_calls_key, 1, self._JUDGE_COUNT_TTL)

        try:
            verdict = sentence_evaluation_service.evaluate_sentence(
                question, user_answer, prior_attempts=prior_attempts,
            )
        except sentence_evaluation_service.SentenceJudgeUnavailable:
            # Discard, don't penalize — the student gets a different question.
            # Attempt state is kept: it resumes if the judge recovers on this
            # question, and resets automatically on any other question.
            return Response({
                'sentence_write_unavailable': True,
                'message': "Let's come back to this one — try a different question.",
            })

        is_terminal_correct = verdict['is_correct']
        no_revisions_left = revisions_used >= max_revisions

        if not is_terminal_correct and not no_revisions_left:
            # Non-terminal miss: coach a revision, do not score yet. Record the
            # attempt server-side (new list, no in-place mutation).
            request.session[self._SW_SESSION_KEY] = {
                'question_id': question.id,
                'attempts': prior_attempts + [{
                    'sentence': str(user_answer or '')[:2000],
                    'hint': verdict['hint'],
                    'verdict': verdict['verdict'],
                }],
            }
            request.session.modified = True
            return Response({
                'sentence_write_pending': True,
                'verdict': verdict['verdict'],
                'error_type': verdict['error_type'],
                'hint': verdict['hint'],
                'hints': verdict.get('hints') or ([verdict['hint']] if verdict['hint'] else []),
                'attempts_used': revisions_used + 1,
                'revisions_left': max_revisions - revisions_used,
            })

        # Terminal outcome — decide the quality rule from server-held attempts.
        self._clear_sw_state(request)
        if is_terminal_correct:
            # Fragile only if a genuine (incorrect) miss preceded this fix; an
            # attempt-1 "almost" that gets fixed stays solid.
            had_incorrect = any(
                (a.get('verdict') == 'incorrect') for a in prior_attempts
            )
            quality_rule = 'productive_recovered' if had_incorrect else 'productive_correct'
        else:
            quality_rule = 'productive_missed'

        judgment = {
            'is_correct': is_terminal_correct,
            'quality_rule': quality_rule,
            'judge_result': {
                'verdict': verdict['verdict'],
                'error_type': verdict['error_type'],
                'hint': verdict['hint'],
                'hints': verdict.get('hints') or ([verdict['hint']] if verdict['hint'] else []),
                'attempts': revisions_used + 1,
                'gave_up': False,
            },
        }
        return self._score_sentence_write(
            request, question, user_answer, judgment,
            model_sentence=(None if is_terminal_correct else model_sentence),
            verdict=verdict,
        )

    def _clear_sw_state(self, request):
        if self._SW_SESSION_KEY in request.session:
            del request.session[self._SW_SESSION_KEY]
            request.session.modified = True

    def _score_sentence_write(self, request, question, user_answer, judgment,
                              model_sentence=None, verdict=None):
        try:
            response_data = PracticeService.process_answer(
                request.user, question.id, user_answer,
                duration_seconds=None, answer_switches=0,
                is_retry=False, productive_judgment=judgment,
                question=question,
            )
        except DailyLimitReached:
            # Raced past the cap between the top-of-handler check and here; the
            # judge already ran, so drop this attempt without scoring or penalty.
            self._clear_sw_state(request)
            return Response({
                'sentence_write_unavailable': True,
                'message': "You've reached today's practice limit — great work!",
            })
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_404_NOT_FOUND)

        response_data['sentence_write_done'] = True
        if verdict is not None:
            response_data['verdict'] = verdict['verdict']
            response_data['error_type'] = verdict['error_type']
            response_data['hint'] = verdict['hint']
            response_data['hints'] = (
                verdict.get('hints') or ([verdict['hint']] if verdict['hint'] else [])
            )
        if model_sentence:
            response_data['model_sentence'] = model_sentence
        return Response(response_data)


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

        # Floor the window: a practice session is same-day, so clamp start_time
        # to at most 24h ago. Without this a client could pass an epoch date and
        # force a full scan of the user's entire answer history every summary.
        if timezone.is_naive(start_time):
            start_time = timezone.make_aware(start_time, dt_timezone.utc)
        earliest = timezone.now() - timedelta(hours=24)
        if start_time < earliest:
            start_time = earliest

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

    # Session key holding the set of session_ids whose bonus was already applied.
    # Bounded to the most recent few so it can't grow unbounded in the session.
    _APPLIED_KEY = 'session_bonus_applied'
    _APPLIED_KEEP = 20

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

        # Idempotency: the streak bonus is a once-per-session award. Without this
        # a client could replay the call to stack +10 XP repeatedly. session_id
        # is the client's session start timestamp (unique per practice session).
        session_id = str(request.data.get('session_id') or '')
        applied = request.session.get(self._APPLIED_KEY, [])
        if session_id and session_id in applied:
            return Response({
                "success": "0 bonus XP applied successfully.",
                "already_applied": True,
            })

        focus_streak_bonus = min(max_focus_streak, 10)
        if focus_streak_bonus > 0:
            with transaction.atomic():
                user = CustomUser.objects.select_for_update().get(pk=request.user.pk)
                PracticeService.update_xp_and_level(user, focus_streak_bonus)

        if session_id:
            # Keep only the most recent ids (newest last) to bound session size.
            request.session[self._APPLIED_KEY] = (
                applied + [session_id]
            )[-self._APPLIED_KEEP:]
            request.session.modified = True

        return Response({
            "success": f"{focus_streak_bonus} bonus XP applied successfully.",
        })
