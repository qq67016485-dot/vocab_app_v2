"""
Tests for the 4 adapted v1 services:
- practice_service.py
- dashboard_service.py
- assignment_service.py
- instructional_service.py
"""
import pytest
from datetime import timedelta
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from vocabulary.models import (
    UserWordProgress, MasteryLevel, UserAnswer, Question,
    MasteryLevelLog, Translation, WordDefinition,
    TypoAttempt, SchedulingDecision,
    Word, WordPack, WordPackItem, PrimerCardContent,
    MicroStory, ClozeItem, StudentPackCompletion,
    StudentWordSetAssignment,
)
from vocabulary.services.practice_service import PracticeService
from vocabulary.services.dashboard_service import DashboardService
from vocabulary.services.assignment_service import AssignmentService
from vocabulary.services.instructional_service import InstructionalService
from tests.factories import (
    AdminUserFactory, TeacherUserFactory, StudentUserFactory,
    WordFactory, WordDefinitionFactory, WordSetFactory,
    WordPackFactory, WordPackItemFactory, PrimerCardContentFactory,
    MicroStoryFactory, ClozeItemFactory, QuestionFactory,
    MasteryLevelFactory, UserWordProgressFactory,
    StudentGroupFactory,
)


def _seed_mastery_levels():
    """Create visible and hidden mastery levels for tests."""
    levels = [
        (1, 'Novice', 1, 2, False),
        (2, 'Familiar', 3, 4, False),
        (3, 'Confident', 7, 7, False),
        (4, 'Proficient', 10, 10, False),
        (5, 'Mastered', 17, 15, False),
        (6, 'Long-Term Retention', 30, 25, True),
        (7, 'Long-Term Mastery', 60, 999, True),
    ]
    for lid, name, interval, pts, is_hidden in levels:
        MasteryLevel.objects.update_or_create(
            level_id=lid,
            defaults={
                'level_name': name,
                'interval_days': interval,
                'points_to_promote': pts,
                'is_hidden': is_hidden,
            },
        )


# =============================================================================
# PRACTICE SERVICE TESTS
# =============================================================================


@pytest.mark.django_db
class TestPracticeServiceNormalizeAnswer:
    def test_strips_and_lowercases(self):
        assert PracticeService.normalize_answer('  Hello World  ') == 'hello world'

    def test_removes_punctuation(self):
        assert PracticeService.normalize_answer("it's a test!") == 'its a test'

    def test_handles_non_string(self):
        assert PracticeService.normalize_answer(42) == '42'


@pytest.mark.django_db
class TestPracticeServiceProcessAnswer:
    @pytest.fixture(autouse=True)
    def setup(self):
        _seed_mastery_levels()
        self.student = StudentUserFactory()
        self.word = WordFactory(text='bright')
        self.defn = WordDefinitionFactory(word=self.word)
        self.question = QuestionFactory(
            word=self.word,
            correct_answers=['shining'],
            options=['shining', 'dark', 'quiet', 'slow'],
        )
        level1 = MasteryLevel.objects.get(level_id=1)
        self.mastery = UserWordProgress.objects.create(
            user=self.student,
            word=self.word,
            level=level1,
            next_review_at=timezone.now(),
        )

    def test_correct_answer_increments_mastery_points(self):
        result = PracticeService.process_answer(
            self.student, self.question.id, 'shining', 5, 0,
        )
        assert result['is_correct'] is True
        assert result['mastery_points'] == 1

    def test_incorrect_answer_decrements_mastery_points(self):
        self.mastery.mastery_points = 2
        self.mastery.save()
        result = PracticeService.process_answer(
            self.student, self.question.id, 'wrong', 5, 0,
        )
        assert result['is_correct'] is False
        assert result['mastery_points'] == 0

    def test_correct_answer_creates_user_answer(self):
        PracticeService.process_answer(
            self.student, self.question.id, 'shining', 10, 1,
        )
        answer = UserAnswer.objects.get(user=self.student, question=self.question)
        assert answer.is_correct is True
        assert answer.duration_seconds == 10
        assert answer.answer_switches == 1

    def test_level_up_on_enough_points(self):
        self.mastery.mastery_points = 2
        self.mastery.save()
        result = PracticeService.process_answer(
            self.student, self.question.id, 'shining', 5, 0,
        )
        assert result['did_level_up_word'] is True
        assert result['current_level_name'] == 'Familiar'

    def test_mastered_words_promote_to_hidden_long_term_level(self):
        level5 = MasteryLevel.objects.get(level_id=5)
        self.mastery.level = level5
        self.mastery.mastery_points = 15
        self.mastery.save()

        result = PracticeService.process_answer(
            self.student, self.question.id, 'shining', 5, 0,
        )

        self.mastery.refresh_from_db()
        assert result['did_level_up_word'] is True
        assert self.mastery.level.level_id == 6
        assert self.mastery.level.is_hidden is True

    def test_hidden_long_term_level_promotes_to_level_7(self):
        level6 = MasteryLevel.objects.get(level_id=6)
        self.mastery.level = level6
        self.mastery.mastery_points = 25
        self.mastery.save()

        result = PracticeService.process_answer(
            self.student, self.question.id, 'shining', 5, 0,
        )

        self.mastery.refresh_from_db()
        assert result['did_level_up_word'] is True
        assert self.mastery.level.level_id == 7
        assert self.mastery.level.interval_days == 60
        assert self.mastery.level.points_to_promote == 999
        assert self.mastery.level.is_hidden is True

    def test_remediation_feedback_on_incorrect(self):
        # Create a translation for remediation
        ct = ContentType.objects.get_for_model(WordDefinition)
        Translation.objects.create(
            content_type=ct,
            object_id=self.defn.id,
            field_name='definition_text',
            language='zh-CN',
            translated_text='明亮的',
        )
        result = PracticeService.process_answer(
            self.student, self.question.id, 'wrong', 5, 0,
        )
        assert 'skill_tag' in result
        assert result['translation'] == '明亮的'

    def test_raises_on_missing_question(self):
        with pytest.raises(ValueError, match="Question or mastery record not found"):
            PracticeService.process_answer(self.student, 99999, 'test', 5, 0)

    def test_xp_earned_on_correct(self):
        result = PracticeService.process_answer(
            self.student, self.question.id, 'shining', 5, 0,
        )
        assert result['xp_earned'] >= 5


@pytest.mark.django_db
class TestAdaptiveIntervals:
    @pytest.fixture(autouse=True)
    def setup(self):
        _seed_mastery_levels()
        self.student = StudentUserFactory()
        self.word = WordFactory(text='bright')
        self.defn = WordDefinitionFactory(word=self.word)
        self.question = QuestionFactory(
            word=self.word,
            correct_answers=['shining'],
            options=['shining', 'dark', 'quiet', 'slow'],
        )
        level1 = MasteryLevel.objects.get(level_id=1)
        self.mastery = UserWordProgress.objects.create(
            user=self.student,
            word=self.word,
            level=level1,
            next_review_at=timezone.now(),
        )

    def _add_timing_history(self, durations, question_type=None):
        question_type = question_type or self.question.question_type
        for index, duration in enumerate(durations):
            word = WordFactory(text=f'history_{index}_{duration}')
            question = QuestionFactory(
                word=word,
                question_type=question_type,
                correct_answers=['answer'],
            )
            UserAnswer.objects.create(
                user=self.student,
                question=question,
                user_answer='answer',
                is_correct=True,
                duration_seconds=duration,
            )

    def test_correct_answer_increases_learning_speed(self):
        PracticeService.process_answer(
            self.student, self.question.id, 'shining', 5, 0,
        )
        self.mastery.refresh_from_db()
        assert self.mastery.learning_speed > 1.0

    def test_incorrect_answer_decreases_learning_speed(self):
        PracticeService.process_answer(
            self.student, self.question.id, 'wrong', 5, 0,
        )
        self.mastery.refresh_from_db()
        assert self.mastery.learning_speed < 1.0

    def test_unclassified_correct_uses_existing_ema_formula_without_enough_history(self):
        result = PracticeService.process_answer(
            self.student, self.question.id, 'shining', 5, 0,
        )
        self.mastery.refresh_from_db()
        expected = 0.3 * 1.2 + 0.7 * 1.0  # 1.06
        assert abs(self.mastery.learning_speed - expected) < 0.001
        assert result['response_quality'] == 'insufficient_timing_baseline'
        assert result['is_fragile'] is False

    def test_next_review_at_is_datetime(self):
        PracticeService.process_answer(
            self.student, self.question.id, 'shining', 5, 0,
        )
        self.mastery.refresh_from_db()
        assert self.mastery.next_review_at is not None
        assert hasattr(self.mastery.next_review_at, 'hour')

    def test_adaptive_interval_scales_with_learning_speed(self):
        self.mastery.learning_speed = 1.5
        self.mastery.save()
        before = timezone.now()
        PracticeService.process_answer(
            self.student, self.question.id, 'shining', 5, 0,
        )
        self.mastery.refresh_from_db()
        new_speed = 0.3 * 1.2 + 0.7 * 1.5  # 1.41
        expected_days = self.mastery.level.interval_days * new_speed
        actual_delta = (self.mastery.next_review_at - before).total_seconds() / 86400
        assert abs(actual_delta - expected_days) < 0.05

    def test_minimum_interval_is_one_day(self):
        self.mastery.learning_speed = 0.1
        self.mastery.save()
        before = timezone.now()
        PracticeService.process_answer(
            self.student, self.question.id, 'wrong', 5, 0,
        )
        self.mastery.refresh_from_db()
        actual_delta = (self.mastery.next_review_at - before).total_seconds() / 86400
        assert actual_delta >= 0.99

    def test_retry_does_not_update_learning_speed(self):
        PracticeService.process_answer(
            self.student, self.question.id, 'wrong', 5, 0,
        )
        self.mastery.refresh_from_db()
        speed_after_wrong = self.mastery.learning_speed
        PracticeService.process_answer(
            self.student, self.question.id, 'shining', 5, 0, is_retry=True,
        )
        self.mastery.refresh_from_db()
        assert self.mastery.learning_speed == speed_after_wrong

    def test_timing_baseline_requires_15_valid_same_question_type_samples(self):
        self._add_timing_history([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 100, 120])
        self._add_timing_history(
            [2, 3, 4, 5, 6],
            question_type=Question.QuestionType.SYNONYM_MC_SINGLE,
        )

        result = PracticeService.process_answer(
            self.student, self.question.id, 'shining', 2, 0,
        )

        self.mastery.refresh_from_db()
        assert result['response_quality'] == 'insufficient_timing_baseline'
        expected = 0.3 * 1.2 + 0.7 * 1.0
        assert abs(self.mastery.learning_speed - expected) < 0.001

    def test_fast_correct_uses_same_question_type_baseline(self):
        self._add_timing_history(range(2, 17))

        before = timezone.now()
        result = PracticeService.process_answer(
            self.student, self.question.id, 'shining', 2, 0,
        )

        self.mastery.refresh_from_db()
        expected_speed = 0.3 * 1.25 + 0.7 * 1.0
        expected_days = self.mastery.level.interval_days * expected_speed * 1.15
        actual_delta = (self.mastery.next_review_at - before).total_seconds() / 86400
        assert result['response_quality'] == 'fast_correct'
        assert result['is_fragile'] is False
        assert abs(self.mastery.learning_speed - expected_speed) < 0.001
        assert abs(actual_delta - expected_days) < 0.05

    def test_slow_correct_is_fragile_when_baseline_exists(self):
        level3 = MasteryLevel.objects.get(level_id=3)
        self.mastery.level = level3
        self.mastery.save()
        self._add_timing_history(range(2, 17))

        before = timezone.now()
        result = PracticeService.process_answer(
            self.student, self.question.id, 'shining', 16, 0,
        )

        self.mastery.refresh_from_db()
        expected_speed = 0.3 * 0.85 + 0.7 * 1.0
        expected_days = level3.interval_days * expected_speed * 0.85
        actual_delta = (self.mastery.next_review_at - before).total_seconds() / 86400
        assert result['response_quality'] == 'slow_correct'
        assert result['is_fragile'] is True
        assert abs(self.mastery.learning_speed - expected_speed) < 0.001
        assert abs(actual_delta - expected_days) < 0.05

    def test_switched_correct_is_fragile_when_baseline_exists(self):
        self._add_timing_history(range(2, 17))

        result = PracticeService.process_answer(
            self.student, self.question.id, 'shining', 8, 1,
        )

        self.mastery.refresh_from_db()
        expected_speed = 0.3 * 0.9 + 0.7 * 1.0
        assert result['response_quality'] == 'switched_correct'
        assert result['is_fragile'] is True
        assert abs(self.mastery.learning_speed - expected_speed) < 0.001

    def test_typo_retry_correct_is_fragile_when_baseline_exists(self):
        self._add_timing_history(range(2, 17))

        result = PracticeService.process_answer(
            self.student, self.question.id, 'shining', 8, 0,
            had_typo_retry=True,
        )

        self.mastery.refresh_from_db()
        expected_speed = 0.3 * 0.9 + 0.7 * 1.0
        assert result['response_quality'] == 'typo_retry_correct'
        assert result['is_fragile'] is True
        assert abs(self.mastery.learning_speed - expected_speed) < 0.001

    def test_incorrect_uses_schedule_adjustment_without_timing_history(self):
        level3 = MasteryLevel.objects.get(level_id=3)
        self.mastery.level = level3
        self.mastery.mastery_points = 7
        self.mastery.save()

        before = timezone.now()
        result = PracticeService.process_answer(
            self.student, self.question.id, 'wrong', 8, 0,
        )

        self.mastery.refresh_from_db()
        expected_speed = 0.3 * 0.5 + 0.7 * 1.0
        expected_days = self.mastery.level.interval_days * expected_speed * 0.5
        actual_delta = (self.mastery.next_review_at - before).total_seconds() / 86400
        assert result['response_quality'] == 'incorrect'
        assert result['is_fragile'] is True
        assert abs(self.mastery.learning_speed - expected_speed) < 0.001
        assert abs(actual_delta - expected_days) < 0.05

    def test_fragile_promotion_caps_interval_at_old_level_interval(self):
        self.mastery.mastery_points = 2
        self.mastery.save()
        self._add_timing_history(range(2, 17))

        before = timezone.now()
        result = PracticeService.process_answer(
            self.student, self.question.id, 'shining', 16, 0,
        )

        self.mastery.refresh_from_db()
        actual_delta = (self.mastery.next_review_at - before).total_seconds() / 86400
        assert result['did_level_up_word'] is True
        assert self.mastery.level.level_id == 2
        assert result['response_quality'] == 'slow_correct'
        assert actual_delta < 1.05


@pytest.mark.django_db
class TestPracticeInstrumentation:
    """Step-0 instrumentation logs: TypoAttempt + SchedulingDecision."""

    @pytest.fixture(autouse=True)
    def setup(self):
        _seed_mastery_levels()
        self.student = StudentUserFactory()
        self.word = WordFactory(text='bright')
        self.defn = WordDefinitionFactory(word=self.word)
        # Type-to-spell question: the correct answer IS the target word.
        self.spell_question = QuestionFactory(
            word=self.word,
            correct_answers=['bright'],
        )
        self.question = QuestionFactory(
            word=self.word,
            correct_answers=['shining'],
            options=['shining', 'dark', 'quiet', 'slow'],
        )
        level1 = MasteryLevel.objects.get(level_id=1)
        self.mastery = UserWordProgress.objects.create(
            user=self.student,
            word=self.word,
            level=level1,
            next_review_at=timezone.now(),
        )

    def _add_timing_history(self, durations):
        for index, duration in enumerate(durations):
            word = WordFactory(text=f'instrument_history_{index}')
            question = QuestionFactory(
                word=word,
                question_type=self.question.question_type,
                correct_answers=['answer'],
            )
            UserAnswer.objects.create(
                user=self.student,
                question=question,
                user_answer='answer',
                is_correct=True,
                duration_seconds=duration,
            )

    def test_typo_submit_logs_typo_attempt_only(self):
        result = PracticeService.process_answer(
            self.student, self.spell_question.id, 'brigt', 5, 0,
        )

        # The response payload is exactly as before (no scoring side effects).
        assert result == {
            'is_typo': True,
            'is_correct': False,
            'message': 'Almost! Check your spelling and try again.',
        }
        # The log write commits even though process_answer returned early
        # from inside its atomic block.
        attempt = TypoAttempt.objects.get()
        assert attempt.user == self.student
        assert attempt.question == self.spell_question
        assert attempt.attempted_text == 'brigt'  # raw answer, not normalized
        assert UserAnswer.objects.count() == 0
        assert SchedulingDecision.objects.count() == 0
        self.mastery.refresh_from_db()
        self.student.refresh_from_db()
        assert self.mastery.mastery_points == 0
        assert self.student.current_practice_streak == 0
        assert self.student.xp_points == 0

    def test_non_typo_wrong_answer_logs_no_typo_attempt(self):
        result = PracticeService.process_answer(
            self.student, self.question.id, 'wrong', 5, 0,
        )

        assert result['is_correct'] is False
        assert TypoAttempt.objects.count() == 0
        assert UserAnswer.objects.count() == 1

    def test_correct_answer_logs_scheduling_decision(self):
        # A second due READY word makes the backlog count non-trivial.
        UserWordProgress.objects.create(
            user=self.student,
            word=WordFactory(text='luminous'),
            level=MasteryLevel.objects.get(level_id=1),
            next_review_at=timezone.now(),
        )

        result = PracticeService.process_answer(
            self.student, self.question.id, 'shining', 5, 0,
        )

        assert result['is_correct'] is True
        decision = SchedulingDecision.objects.get()
        assert decision.user == self.student
        assert decision.word == self.word
        assert decision.question == self.question
        assert decision.mastery_level_before == 1
        assert decision.mastery_level_after == 1
        assert decision.learning_speed_before == 1.0
        expected_speed = 0.3 * 1.2 + 0.7 * 1.0  # unclassified_correct EMA
        assert abs(decision.learning_speed_after - expected_speed) < 0.001
        assert decision.response_quality_rule == 'insufficient_timing_baseline'
        assert decision.intended_interval_days == result['review_interval_days']
        self.mastery.refresh_from_db()
        assert decision.next_review_at == self.mastery.next_review_at
        assert decision.jitter_offset_days is None
        assert decision.jitter_probability is None
        # The just-answered word was pushed past today's cutoff; only the
        # other due word counts.
        assert decision.due_backlog_size == 1

    def test_incorrect_answer_logs_scheduling_decision(self):
        self.mastery.mastery_points = 2
        self.mastery.save()

        result = PracticeService.process_answer(
            self.student, self.question.id, 'wrong', 5, 0,
        )

        assert result['is_correct'] is False
        self.mastery.refresh_from_db()
        assert self.mastery.mastery_points == 0  # -2 points, floored at 0
        decision = SchedulingDecision.objects.get()
        assert decision.response_quality_rule == 'incorrect'
        assert decision.mastery_level_before == 1
        assert decision.mastery_level_after == 1
        expected_speed = 0.3 * 0.5 + 0.7 * 1.0
        assert abs(decision.learning_speed_after - expected_speed) < 0.001
        assert decision.intended_interval_days == result['review_interval_days']

    def test_retry_logs_no_scheduling_decision(self):
        PracticeService.process_answer(
            self.student, self.question.id, 'wrong', 5, 0,
        )
        assert SchedulingDecision.objects.count() == 1

        result = PracticeService.process_answer(
            self.student, self.question.id, 'shining', 5, 0, is_retry=True,
        )

        assert result['is_correct'] is True
        assert SchedulingDecision.objects.count() == 1
        assert TypoAttempt.objects.count() == 0

    def test_productive_judgment_logs_scheduling_decision(self):
        judgment = {
            'is_correct': True,
            'quality_rule': 'productive_correct',
            'judge_result': {'verdict': 'correct', 'attempts': 1},
        }
        result = PracticeService.process_answer(
            self.student, self.question.id,
            'The bright sun fills the room.', None, 0,
            productive_judgment=judgment,
        )

        assert result['is_correct'] is True
        decision = SchedulingDecision.objects.get()
        assert decision.response_quality_rule == 'productive_correct'
        assert decision.intended_interval_days == result['review_interval_days']

    def test_fragile_promotion_records_capped_interval(self):
        self.mastery.mastery_points = 2
        self.mastery.save()
        self._add_timing_history(range(2, 17))

        result = PracticeService.process_answer(
            self.student, self.question.id, 'shining', 16, 0,
        )

        # slow_correct + promotion caps the interval at the old level
        # interval (level 1: 1 day x old learning speed 1.0).
        assert result['response_quality'] == 'slow_correct'
        assert result['did_level_up_word'] is True
        assert result['review_interval_days'] == 1.0
        decision = SchedulingDecision.objects.get()
        assert decision.mastery_level_before == 1
        assert decision.mastery_level_after == 2
        assert decision.response_quality_rule == 'slow_correct'
        assert decision.intended_interval_days == 1.0
        self.mastery.refresh_from_db()
        assert decision.next_review_at == self.mastery.next_review_at

@pytest.mark.django_db
class TestPracticeServiceStreak:
    def test_streak_increments_on_consecutive_days(self):
        student = StudentUserFactory()
        student.last_practice_date = timezone.localdate() - timedelta(days=1)
        student.current_practice_streak = 2
        student.save()

        PracticeService.update_practice_streak(student)
        student.refresh_from_db()

        assert student.current_practice_streak == 3
        assert student.last_practice_date == timezone.localdate()

    def test_streak_resets_on_gap(self):
        student = StudentUserFactory()
        student.last_practice_date = timezone.localdate() - timedelta(days=3)
        student.current_practice_streak = 5
        student.save()

        PracticeService.update_practice_streak(student)
        student.refresh_from_db()

        assert student.current_practice_streak == 1


# =============================================================================
# DASHBOARD SERVICE TESTS
# =============================================================================


@pytest.mark.django_db
class TestDashboardServiceStudentProgress:
    @pytest.fixture(autouse=True)
    def setup(self):
        _seed_mastery_levels()
        self.student = StudentUserFactory()
        self.word = WordFactory(text='bright')
        self.defn = WordDefinitionFactory(word=self.word)
        self.question = QuestionFactory(word=self.word)
        level1 = MasteryLevel.objects.get(level_id=1)
        UserWordProgress.objects.create(
            user=self.student, word=self.word,
            level=level1, next_review_at=timezone.now(),
        )

    def test_returns_student_username(self):
        result = DashboardService.get_student_progress(self.student)
        assert result['student_username'] == self.student.username

    def test_returns_mastery_counts(self):
        result = DashboardService.get_student_progress(self.student)
        assert 'mastery_counts' in result
        assert len(result['mastery_counts']) >= 1

    def test_rolls_hidden_mastery_counts_into_mastered(self):
        hidden_level = MasteryLevel.objects.get(level_id=6)
        hidden_word = WordFactory(text='settled')
        UserWordProgress.objects.create(
            user=self.student,
            word=hidden_word,
            level=hidden_level,
            next_review_at=timezone.now(),
        )

        result = DashboardService.get_student_progress(self.student)

        level_names = [item['level_name'] for item in result['mastery_counts']]
        assert 'Long-Term Retention' not in level_names
        assert 'Long-Term Mastery' not in level_names
        mastered = next(item for item in result['mastery_counts'] if item['level_name'] == 'Mastered')
        assert mastered['word_count'] == 1

    def test_returns_recent_answers(self):
        UserAnswer.objects.create(
            user=self.student, question=self.question,
            user_answer='test', is_correct=True,
        )
        result = DashboardService.get_student_progress(self.student)
        assert len(result['recent_answers']) == 1
        assert result['recent_answers'][0]['term'] == 'bright'

    def test_returns_practice_stats(self):
        result = DashboardService.get_student_progress(self.student)
        assert 'today' in result['practice_stats']
        assert 'past_3_days' in result['practice_stats']
        assert 'past_7_days' in result['practice_stats']


@pytest.mark.django_db
class TestDashboardServiceRoster:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.teacher = TeacherUserFactory()
        self.student = StudentUserFactory()
        self.teacher.students.add(self.student)

    def test_returns_roster(self):
        result = DashboardService.get_roster_dashboard(self.teacher, 'all')
        assert len(result['roster']) == 1
        assert result['roster'][0].username == self.student.username

    def test_filters_by_group(self):
        group = StudentGroupFactory(teacher=self.teacher)
        group.students.add(self.student)

        result = DashboardService.get_roster_dashboard(self.teacher, group.id)
        assert len(result['roster']) == 1


@pytest.mark.django_db
class TestDashboardServiceLearningPatterns:
    def test_returns_empty_for_no_mistakes(self):
        student = StudentUserFactory()
        result = DashboardService.get_learning_patterns(student)
        assert result['total_analyzed'] == 0
        assert result['patterns'] == []
        assert result['challenging_words'] == []

    def test_returns_patterns_for_incorrect_answers(self):
        _seed_mastery_levels()
        student = StudentUserFactory()
        word = WordFactory(text='bright')
        WordDefinitionFactory(word=word)
        question = QuestionFactory(
            word=word,
            question_type='DEFINITION_MC_SINGLE',
        )

        UserAnswer.objects.create(
            user=student, question=question,
            user_answer='wrong', is_correct=False,
        )
        result = DashboardService.get_learning_patterns(student)
        assert result['total_analyzed'] == 1
        assert len(result['patterns']) >= 1


# =============================================================================
# ASSIGNMENT SERVICE TESTS
# =============================================================================


@pytest.mark.django_db
class TestAssignmentService:
    @pytest.fixture(autouse=True)
    def setup(self):
        _seed_mastery_levels()
        self.teacher = TeacherUserFactory()
        self.student = StudentUserFactory()
        self.teacher.students.add(self.student)
        self.word = WordFactory(text='bright')
        self.word_set = WordSetFactory(creator=self.teacher)
        self.word_set.words.add(self.word)

    def test_assigns_word_set_to_student(self):
        count, students = AssignmentService.assign_word_set(
            self.teacher, self.word_set, [self.student.id], [],
        )
        assert count == 1
        assert StudentWordSetAssignment.objects.filter(
            user=self.student, word_set=self.word_set,
        ).exists()

    def test_creates_user_word_progress(self):
        AssignmentService.assign_word_set(
            self.teacher, self.word_set, [self.student.id], [],
        )
        progress = UserWordProgress.objects.get(
            user=self.student, word=self.word,
        )
        assert progress.level.level_id == 1
        assert progress.instructional_status == 'READY'

    def test_sets_pending_for_words_in_packs(self):
        pack = WordPackFactory(word_set=self.word_set)
        WordPackItem.objects.create(pack=pack, word=self.word, order=0)

        AssignmentService.assign_word_set(
            self.teacher, self.word_set, [self.student.id], [],
        )
        progress = UserWordProgress.objects.get(
            user=self.student, word=self.word,
        )
        assert progress.instructional_status == 'PENDING'

    def test_assigns_via_group(self):
        group = StudentGroupFactory(teacher=self.teacher)
        group.students.add(self.student)

        count, students = AssignmentService.assign_word_set(
            self.teacher, self.word_set, [], [group.id],
        )
        assert count == 1

    def test_raises_on_no_students(self):
        with pytest.raises(ValueError, match='No valid students'):
            AssignmentService.assign_word_set(
                self.teacher, self.word_set, [], [],
            )

    def test_returns_zero_for_empty_word_set(self):
        empty_ws = WordSetFactory(creator=self.teacher)
        count, _ = AssignmentService.assign_word_set(
            self.teacher, empty_ws, [self.student.id], [],
        )
        assert count == 0


# =============================================================================
# INSTRUCTIONAL SERVICE TESTS
# =============================================================================


@pytest.mark.django_db
class TestInstructionalServiceGetPackData:
    @pytest.fixture(autouse=True)
    def setup(self):
        _seed_mastery_levels()
        self.teacher = TeacherUserFactory()
        self.student = StudentUserFactory()
        self.teacher.students.add(self.student)

        self.word_set = WordSetFactory(creator=self.teacher)
        self.word = WordFactory(text='bright')
        self.word_set.words.add(self.word)

        # Create assignment
        StudentWordSetAssignment.objects.create(
            user=self.student, word_set=self.word_set, assigned_by=self.teacher,
        )

        self.pack = WordPackFactory(word_set=self.word_set, label='Pack 1')
        WordPackItem.objects.create(pack=self.pack, word=self.word, order=0)

    def test_returns_pack_data(self):
        result = InstructionalService.get_pack_data(self.student, self.pack.id)
        assert result['pack_id'] == self.pack.id
        assert result['label'] == 'Pack 1'

    def test_returns_primer_cards(self):
        PrimerCardContent.objects.create(
            word=self.word,
            syllable_text='bright',
            kid_friendly_definition='Something that shines.',
            example_sentence='The sun is bright.',
        )
        result = InstructionalService.get_pack_data(self.student, self.pack.id)
        assert len(result['primer_cards']) == 1
        assert result['primer_cards'][0]['term_text'] == 'bright'
        assert result['primer_cards'][0]['kid_friendly_definition'] == 'Something that shines.'

    def test_returns_translations_in_primer(self):
        defn = WordDefinitionFactory(word=self.word)
        ct = ContentType.objects.get_for_model(WordDefinition)
        Translation.objects.create(
            content_type=ct, object_id=defn.id,
            field_name='definition_text', language='zh-CN',
            translated_text='明亮的',
        )
        PrimerCardContent.objects.create(
            word=self.word, syllable_text='bright',
            kid_friendly_definition='Shining.', example_sentence='Bright sun.',
        )

        result = InstructionalService.get_pack_data(self.student, self.pack.id)
        assert result['primer_cards'][0]['definition_translation'] == '明亮的'

    def test_returns_story(self):
        MicroStory.objects.create(
            pack=self.pack,
            story_text='The **bright** sun shone.',
            reading_level=650,
        )
        result = InstructionalService.get_pack_data(self.student, self.pack.id)
        assert result['story'] is not None
        assert 'bright' in result['story']['story_text']

    def test_returns_cloze_items(self):
        ClozeItem.objects.create(
            pack=self.pack, word=self.word,
            sentence_text='The _______ star.', correct_answer='bright',
            distractors=['dark', 'quiet'], order=0,
        )
        result = InstructionalService.get_pack_data(self.student, self.pack.id)
        assert len(result['cloze_items']) == 1

    def test_raises_on_unassigned_pack(self):
        unassigned_student = StudentUserFactory()
        with pytest.raises(PermissionError):
            InstructionalService.get_pack_data(unassigned_student, self.pack.id)

    def test_raises_on_missing_pack(self):
        with pytest.raises(ValueError, match='Pack not found'):
            InstructionalService.get_pack_data(self.student, 99999)


@pytest.mark.django_db
class TestInstructionalServiceCompletePack:
    @pytest.fixture(autouse=True)
    def setup(self):
        _seed_mastery_levels()
        self.teacher = TeacherUserFactory()
        self.student = StudentUserFactory()
        self.teacher.students.add(self.student)
        self.word_set = WordSetFactory(creator=self.teacher)
        self.word = WordFactory(text='bright')
        self.word_set.words.add(self.word)
        StudentWordSetAssignment.objects.create(
            user=self.student, word_set=self.word_set, assigned_by=self.teacher,
        )
        self.pack = WordPackFactory(word_set=self.word_set)
        WordPackItem.objects.create(pack=self.pack, word=self.word, order=0)
        level1 = MasteryLevel.objects.get(level_id=1)
        UserWordProgress.objects.create(
            user=self.student, word=self.word,
            level=level1, next_review_at=timezone.now(),
            instructional_status='PENDING',
        )

    def test_creates_completion_record(self):
        InstructionalService.complete_pack(self.student, self.pack.id)
        assert StudentPackCompletion.objects.filter(
            user=self.student, pack=self.pack,
        ).exists()

    def test_flips_status_to_ready(self):
        InstructionalService.complete_pack(self.student, self.pack.id)
        progress = UserWordProgress.objects.get(
            user=self.student, word=self.word,
        )
        assert progress.instructional_status == 'READY'

    def test_is_idempotent(self):
        InstructionalService.complete_pack(self.student, self.pack.id)
        InstructionalService.complete_pack(self.student, self.pack.id)
        assert StudentPackCompletion.objects.filter(
            user=self.student, pack=self.pack,
        ).count() == 1

    def test_raises_on_unassigned(self):
        unassigned = StudentUserFactory()
        with pytest.raises(PermissionError):
            InstructionalService.complete_pack(unassigned, self.pack.id)
