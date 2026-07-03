"""
Practice service — processes student answers and manages mastery progression.

V2 changes from v1:
- Removed all BKT (update_bkt_state, UserKnowledgeComponentState)
- meaning → word FK path
- UserMeaningMastery → UserWordProgress
- definition_chinese → Translation model lookup
"""
from datetime import timedelta
import math
import string
import logging

from django.conf import settings
from django.core.cache import cache
from django.db import models, transaction
from django.utils import timezone

from users.models import CustomUser
from vocabulary.models import (
    UserWordProgress, MasteryLevel, UserAnswer, Question,
    MasteryLevelLog,
)
from vocabulary.constants import QUESTION_TYPE_TO_SKILL_TAG
from vocabulary.utils import get_tier_info, get_definition_translation

logger = logging.getLogger(__name__)


class PracticeService:
    MIN_TIMING_BASELINE_SAMPLES = 15
    TIMING_BASELINE_LIMIT = 50
    # Baselines are 25th/80th percentiles over up to 50 samples — they move
    # slowly, so a short cache TTL replaces an O(history) scan on every submit.
    TIMING_BASELINE_CACHE_TTL = 600  # 10 min
    MIN_VALID_DURATION_SECONDS = 1
    MAX_VALID_DURATION_SECONDS = 100
    MIN_REVIEW_INTERVAL_DAYS = 1.0
    ALPHA = 0.3

    RESPONSE_QUALITY_RULES = {
        'fast_correct': {
            'quality': 1.25,
            'interval_factor': 1.15,
            'is_fragile': False,
            'schedule_reason': 'fast_correct',
        },
        'solid_correct': {
            'quality': 1.10,
            'interval_factor': 1.00,
            'is_fragile': False,
            'schedule_reason': 'solid_correct',
        },
        'slow_correct': {
            'quality': 0.85,
            'interval_factor': 0.85,
            'is_fragile': True,
            'schedule_reason': 'slow_correct',
        },
        'switched_correct': {
            'quality': 0.90,
            'interval_factor': 0.85,
            'is_fragile': True,
            'schedule_reason': 'switched_correct',
        },
        'typo_retry_correct': {
            'quality': 0.90,
            'interval_factor': 0.85,
            'is_fragile': True,
            'schedule_reason': 'typo_retry_correct',
        },
        'incorrect': {
            'quality': 0.50,
            'interval_factor': 0.50,
            'is_fragile': True,
            'schedule_reason': 'incorrect',
        },
        'unclassified_correct': {
            'quality': 1.20,
            'interval_factor': 1.00,
            'is_fragile': False,
            'schedule_reason': 'insufficient_timing_baseline',
        },
        # Productive sentence-writing (LLM-judged). Timing is meaningless for
        # free writing, so these are keyed off the judge outcome, not duration.
        'productive_correct': {
            'quality': 1.10,
            'interval_factor': 1.00,
            'is_fragile': False,
            'schedule_reason': 'productive_correct',
        },
        'productive_recovered': {
            'quality': 0.90,
            'interval_factor': 0.85,
            'is_fragile': True,
            'schedule_reason': 'productive_recovered',
        },
        'productive_missed': {
            'quality': 0.60,
            'interval_factor': 0.60,
            'is_fragile': True,
            'schedule_reason': 'productive_missed',
        },
    }

    @classmethod
    def update_xp_and_level(cls, user, xp_to_add):
        user.xp_points += xp_to_add
        did_level_up = False
        while True:
            current_tier_info = get_tier_info(user.level)
            if not current_tier_info:
                break
            xp_for_next_level = current_tier_info['xp_per_level']
            total_xp_for_current_level = 0
            for tier in settings.TIER_CONFIG.values():
                if tier['min_level'] < user.level:
                    levels_in_tier = min(user.level - 1, tier['max_level']) - tier['min_level'] + 1
                    total_xp_for_current_level += levels_in_tier * tier['xp_per_level']
            xp_in_current_level = user.xp_points - total_xp_for_current_level
            if xp_in_current_level >= xp_for_next_level:
                user.level += 1
                did_level_up = True
            else:
                break
        user.save(update_fields=['xp_points', 'level'])
        return did_level_up

    @staticmethod
    def update_practice_streak(user):
        today = timezone.localdate()
        if user.last_practice_date == today:
            return
        yesterday = today - timedelta(days=1)
        if user.last_practice_date == yesterday:
            user.current_practice_streak += 1
            if user.current_practice_streak > 0 and user.current_practice_streak % 3 == 0:
                if user.streak_freezes_available < 5:
                    user.streak_freezes_available += 1
        else:
            user.current_practice_streak = 1
        user.last_practice_date = today
        user.save(update_fields=['current_practice_streak', 'last_practice_date', 'streak_freezes_available'])

    @staticmethod
    def normalize_answer(answer_text):
        if not isinstance(answer_text, str):
            answer_text = str(answer_text)
        return answer_text.strip().lower().translate(str.maketrans('', '', string.punctuation))

    @staticmethod
    def _damerau_levenshtein_distance(s1, s2):
        """Compute Damerau-Levenshtein distance (substitution, insertion, deletion, transposition)."""
        len1, len2 = len(s1), len(s2)
        d = [[0] * (len2 + 1) for _ in range(len1 + 1)]
        for i in range(len1 + 1):
            d[i][0] = i
        for j in range(len2 + 1):
            d[0][j] = j
        for i in range(1, len1 + 1):
            for j in range(1, len2 + 1):
                cost = 0 if s1[i - 1] == s2[j - 1] else 1
                d[i][j] = min(
                    d[i - 1][j] + 1,       # deletion
                    d[i][j - 1] + 1,       # insertion
                    d[i - 1][j - 1] + cost, # substitution
                )
                if i > 1 and j > 1 and s1[i - 1] == s2[j - 2] and s1[i - 2] == s2[j - 1]:
                    d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)  # transposition
        return d[len1][len2]

    @classmethod
    def _valid_duration_filter(cls):
        return {
            'duration_seconds__gt': cls.MIN_VALID_DURATION_SECONDS,
            'duration_seconds__lt': cls.MAX_VALID_DURATION_SECONDS,
        }

    @staticmethod
    def _percentile(sorted_values, percentile):
        if not sorted_values:
            return None
        if len(sorted_values) == 1:
            return float(sorted_values[0])

        rank = (len(sorted_values) - 1) * percentile
        lower = math.floor(rank)
        upper = math.ceil(rank)
        if lower == upper:
            return float(sorted_values[int(rank)])

        weight = rank - lower
        return (
            sorted_values[lower] * (1 - weight)
            + sorted_values[upper] * weight
        )

    @classmethod
    def _get_timing_baseline(cls, user, question_type):
        # Cached per (user, question_type): the underlying scan joins Question
        # over the user's answer history on every scored submit otherwise. An
        # empty-string sentinel caches the "not enough samples yet" case too.
        cache_key = f'timing_baseline:{user.id}:{question_type}'
        cached = cache.get(cache_key)
        if cached is not None:
            return cached or None

        durations = list(
            UserAnswer.objects.filter(
                user=user,
                question__question_type=question_type,
                **cls._valid_duration_filter(),
            )
            .order_by('-answered_at')
            .values_list('duration_seconds', flat=True)[:cls.TIMING_BASELINE_LIMIT]
        )

        if len(durations) < cls.MIN_TIMING_BASELINE_SAMPLES:
            baseline = None
        else:
            sorted_durations = sorted(durations)
            baseline = {
                'fast_threshold': cls._percentile(sorted_durations, 0.25),
                'slow_threshold': cls._percentile(sorted_durations, 0.80),
                'sample_count': len(sorted_durations),
            }

        cache.set(cache_key, baseline if baseline is not None else '',
                  cls.TIMING_BASELINE_CACHE_TTL)
        return baseline

    @classmethod
    def _classify_response_quality(
        cls, user, question, is_correct, duration_seconds,
        answer_switches, had_typo_retry,
    ):
        if not is_correct:
            return cls.RESPONSE_QUALITY_RULES['incorrect'].copy()

        baseline = cls._get_timing_baseline(user, question.question_type)
        if not baseline:
            return cls.RESPONSE_QUALITY_RULES['unclassified_correct'].copy()

        candidates = []
        try:
            duration_value = float(duration_seconds)
        except (TypeError, ValueError):
            duration_value = None

        if (
            duration_value is not None
            and baseline['fast_threshold'] is not None
            and duration_value <= baseline['fast_threshold']
        ):
            candidates.append('fast_correct')
        elif (
            duration_value is not None
            and baseline['slow_threshold'] is not None
            and duration_value >= baseline['slow_threshold']
        ):
            candidates.append('slow_correct')
        else:
            candidates.append('solid_correct')

        try:
            switch_count = int(answer_switches or 0)
        except (TypeError, ValueError):
            switch_count = 0

        if switch_count > 0:
            candidates.append('switched_correct')
        if had_typo_retry:
            candidates.append('typo_retry_correct')

        best_name = min(
            candidates,
            key=lambda name: (
                cls.RESPONSE_QUALITY_RULES[name]['quality'],
                cls.RESPONSE_QUALITY_RULES[name]['interval_factor'],
            ),
        )
        rule = cls.RESPONSE_QUALITY_RULES[best_name].copy()
        rule['baseline_sample_count'] = baseline['sample_count']
        return rule

    @classmethod
    def process_answer(
        cls, user, question_id, user_answer, duration_seconds, answer_switches,
        is_retry=False, had_typo_retry=False, productive_judgment=None,
        question=None,
    ):
        """Process a submitted answer and update mastery/scheduling.

        ``productive_judgment`` (sentence-writing questions only) short-circuits
        the exact-match + typo path. It is a dict:
            {
                'is_correct': bool,      # from the LLM judge
                'quality_rule': str,     # a RESPONSE_QUALITY_RULES key
                'judge_result': dict,    # persisted on UserAnswer for analytics
            }
        When present the answer is terminal (the backend already ran the
        judge/revision loop), so ``is_retry`` is always False here.

        ``question`` lets a caller that already fetched the Question (with
        ``select_related('word')``) pass it in and skip the duplicate lookup.
        """
        with transaction.atomic():
            if not is_retry:
                cls.update_practice_streak(user)

            try:
                if question is None:
                    question = Question.objects.select_related('word').get(id=question_id)
                mastery_record = UserWordProgress.objects.select_related('level').get(
                    user=user, word=question.word,
                )
            except (Question.DoesNotExist, UserWordProgress.DoesNotExist):
                raise ValueError("Question or mastery record not found.")

            level_before = mastery_record.level

            if productive_judgment is not None:
                is_correct = bool(productive_judgment.get('is_correct'))
            else:
                normalized_user_answer = cls.normalize_answer(user_answer)

                correct_answers_from_db = question.correct_answers
                if not isinstance(correct_answers_from_db, list):
                    correct_answers_from_db = [correct_answers_from_db]

                is_correct = any(
                    normalized_user_answer == cls.normalize_answer(ans)
                    for ans in correct_answers_from_db
                )

                # Typo detection: only for type-to-spell questions (answer == target word)
                # If near-miss, return early without recording the attempt
                if not is_correct and normalized_user_answer:
                    term_normalized = cls.normalize_answer(question.word.text)
                    is_type_to_spell = any(
                        cls.normalize_answer(ans) == term_normalized
                        for ans in correct_answers_from_db
                    )
                    if is_type_to_spell and len(term_normalized) > 0:
                        distance = cls._damerau_levenshtein_distance(
                            normalized_user_answer, term_normalized
                        )
                        ratio = distance / len(term_normalized)
                        if ratio <= 0.25:
                            return {
                                'is_typo': True,
                                'is_correct': False,
                                'message': 'Almost! Check your spelling and try again.',
                            }

            current_mastery_level_before_update = mastery_record.level
            old_learning_speed = mastery_record.learning_speed
            did_level_up_word = False
            did_level_up_user = False
            xp_earned = 0
            bonus_info = {}
            schedule_info = None

            if not is_retry:
                if productive_judgment is not None:
                    response_quality = cls.RESPONSE_QUALITY_RULES[
                        productive_judgment['quality_rule']
                    ].copy()
                else:
                    response_quality = cls._classify_response_quality(
                        user=user,
                        question=question,
                        is_correct=is_correct,
                        duration_seconds=duration_seconds,
                        answer_switches=answer_switches,
                        had_typo_retry=had_typo_retry,
                    )

                if is_correct:
                    mastery_record.mastery_points += 1
                    if mastery_record.mastery_points >= current_mastery_level_before_update.points_to_promote:
                        try:
                            next_level = MasteryLevel.objects.get(
                                level_id=current_mastery_level_before_update.level_id + 1,
                            )
                            mastery_record.level = next_level
                            did_level_up_word = True
                            if current_mastery_level_before_update.level_id == 1:
                                xp_earned += 2
                                bonus_info['new_word_mastery'] = 2
                        except MasteryLevel.DoesNotExist:
                            pass
                elif productive_judgment is not None:
                    # Softened miss for productive tasks: a genuine attempt at
                    # producing the word is worth more than a wrong MC click, so
                    # drop only 1 point and never force a demotion (still fragile
                    # → shorter interval via response_quality).
                    mastery_record.mastery_points = max(0, mastery_record.mastery_points - 1)
                else:
                    mastery_record.mastery_points = max(0, mastery_record.mastery_points - 2)
                    if current_mastery_level_before_update.level_id > 1:
                        try:
                            previous_level = MasteryLevel.objects.get(
                                level_id=current_mastery_level_before_update.level_id - 1,
                            )
                            if mastery_record.mastery_points < previous_level.points_to_promote:
                                mastery_record.level = previous_level
                        except MasteryLevel.DoesNotExist:
                            pass

                if mastery_record.level != level_before:
                    MasteryLevelLog.objects.create(
                        user=user,
                        word=question.word,
                        old_level=level_before,
                        new_level=mastery_record.level,
                    )

                if is_correct:
                    xp_earned += 5
                    if current_mastery_level_before_update.level_id >= 4:
                        xp_earned += 5
                        bonus_info['good_old_memory'] = 5
                    # Reward the high-effort productive task on a clean first try.
                    if (
                        productive_judgment is not None
                        and response_quality['schedule_reason'] == 'productive_correct'
                    ):
                        xp_earned += 5
                        bonus_info['sentence_writing'] = 5

                mastery_record.learning_speed = (
                    cls.ALPHA * response_quality['quality']
                    + (1 - cls.ALPHA) * mastery_record.learning_speed
                )

                adaptive_days = (
                    mastery_record.level.interval_days
                    * mastery_record.learning_speed
                    * response_quality['interval_factor']
                )
                if response_quality['is_fragile'] and mastery_record.level != level_before:
                    pre_promotion_days = (
                        current_mastery_level_before_update.interval_days
                        * old_learning_speed
                    )
                    adaptive_days = min(adaptive_days, pre_promotion_days)

                review_interval_days = max(cls.MIN_REVIEW_INTERVAL_DAYS, adaptive_days)
                mastery_record.next_review_at = timezone.now() + timedelta(
                    days=review_interval_days,
                )
                mastery_record.last_reviewed_at = timezone.now()
                mastery_record.save()
                schedule_info = {
                    'response_quality': response_quality['schedule_reason'],
                    'is_fragile': response_quality['is_fragile'],
                    'review_interval_days': review_interval_days,
                    'next_review_at': mastery_record.next_review_at,
                    'schedule_reason': response_quality['schedule_reason'],
                }

                UserAnswer.objects.create(
                    user=user,
                    question=question,
                    user_answer=user_answer,
                    is_correct=is_correct,
                    duration_seconds=duration_seconds,
                    answer_switches=answer_switches,
                    judge_result=(
                        productive_judgment.get('judge_result')
                        if productive_judgment is not None else None
                    ),
                )

                if xp_earned > 0:
                    did_level_up_user = cls.update_xp_and_level(user, xp_earned)
            else:
                # Increment retry_count on the LATEST answer only. `.update()`
                # silently ignores `order_by`, so filtering by the fetched pk is
                # required — updating the unfiltered queryset would touch every
                # historical answer this user gave for this question.
                latest_pk = (
                    UserAnswer.objects.filter(user=user, question=question)
                    .order_by('-answered_at')
                    .values_list('pk', flat=True)
                    .first()
                )
                if latest_pk is not None:
                    UserAnswer.objects.filter(pk=latest_pk).update(
                        retry_count=models.F('retry_count') + 1,
                    )

            remediation_feedback = {}
            if not is_correct:
                skill_tag = QUESTION_TYPE_TO_SKILL_TAG.get(question.question_type, 'other')
                translation = get_definition_translation(question.word, user.native_language)
                remediation_feedback = {
                    'skill_tag': skill_tag,
                    'translation': translation,
                }

            response = {
                "is_correct": is_correct,
                "is_retry": is_retry,
                "explanation": question.explanation,
                "example_sentence": question.example_sentence,
                **remediation_feedback,
            }

            if is_correct:
                if question.correct_answers:
                    response["correct_answer"] = question.correct_answers[0]

            if not is_retry:
                response.update({
                    "mastery_points": mastery_record.mastery_points,
                    "points_to_promote": mastery_record.level.points_to_promote,
                    "current_level_name": mastery_record.level.level_name,
                    "did_level_up_word": did_level_up_word,
                    "xp_earned": xp_earned,
                    "bonus_info": bonus_info,
                    "did_level_up_user": did_level_up_user,
                })
                if schedule_info:
                    response.update(schedule_info)

            return response
