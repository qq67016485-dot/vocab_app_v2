"""
Practice service — processes student answers and manages mastery progression.

V2 changes from v1:
- Removed all BKT (update_bkt_state, UserKnowledgeComponentState)
- meaning → word FK path
- UserMeaningMastery → UserWordProgress
- definition_chinese → Translation model lookup
"""
from datetime import date, timedelta
import string
import logging

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from users.models import CustomUser
from vocabulary.models import (
    UserWordProgress, MasteryLevel, UserAnswer, Question,
    MasteryLevelLog, Translation, WordDefinition,
)
from vocabulary.constants import QUESTION_TYPE_TO_SKILL_TAG
from vocabulary.utils import get_tier_info

logger = logging.getLogger(__name__)


class PracticeService:
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
        today = date.today()
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
    def _get_translation(word, language):
        """Look up the definition translation for a word in the student's native language."""
        defn = word.definitions.first()
        if not defn:
            return ''
        ct = ContentType.objects.get_for_model(WordDefinition)
        try:
            return Translation.objects.get(
                content_type=ct,
                object_id=defn.id,
                field_name='definition_text',
                language=language,
            ).translated_text
        except Translation.DoesNotExist:
            return ''

    @classmethod
    def process_answer(cls, user, question_id, user_answer, duration_seconds, answer_switches):
        with transaction.atomic():
            cls.update_practice_streak(user)

            try:
                question = Question.objects.select_related('word').get(id=question_id)
                mastery_record = UserWordProgress.objects.select_related('level').get(
                    user=user, word=question.word,
                )
            except (Question.DoesNotExist, UserWordProgress.DoesNotExist):
                raise ValueError("Question or mastery record not found.")

            level_before = mastery_record.level
            normalized_user_answer = cls.normalize_answer(user_answer)

            correct_answers_from_db = question.correct_answers
            if not isinstance(correct_answers_from_db, list):
                correct_answers_from_db = [correct_answers_from_db]

            is_correct = any(
                normalized_user_answer == cls.normalize_answer(ans)
                for ans in correct_answers_from_db
            )

            current_mastery_level_before_update = mastery_record.level
            did_level_up_word = False
            xp_earned = 0
            bonus_info = {}

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

            mastery_record.next_review_date = date.today() + timedelta(
                days=mastery_record.level.interval_days,
            )
            mastery_record.last_reviewed_at = timezone.now()
            mastery_record.save()

            UserAnswer.objects.create(
                user=user,
                question=question,
                user_answer=user_answer,
                is_correct=is_correct,
                duration_seconds=duration_seconds,
                answer_switches=answer_switches,
            )

            did_level_up_user = False
            if xp_earned > 0:
                did_level_up_user = cls.update_xp_and_level(user, xp_earned)

            remediation_feedback = {}
            if not is_correct:
                skill_tag = QUESTION_TYPE_TO_SKILL_TAG.get(question.question_type, 'other')
                translation = cls._get_translation(question.word, user.native_language)
                remediation_feedback = {
                    'skill_tag': skill_tag,
                    'translation': translation,
                }

            return {
                "is_correct": is_correct,
                "correct_answer": question.correct_answers[0],
                "explanation": question.explanation,
                "example_sentence": question.example_sentence,
                "mastery_points": mastery_record.mastery_points,
                "points_to_promote": mastery_record.level.points_to_promote,
                "current_level_name": mastery_record.level.level_name,
                "did_level_up_word": did_level_up_word,
                "xp_earned": xp_earned,
                "bonus_info": bonus_info,
                "did_level_up_user": did_level_up_user,
                **remediation_feedback,
            }
