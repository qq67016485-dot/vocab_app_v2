"""Tests for compute_item_stats (CTT item stats + QA flags), the admin
question flag endpoint, and serve exclusion of flagged questions."""
import json
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from vocabulary.models import (
    MasteryLevel, Question, UserAnswer, UserWordProgress,
)
from tests.factories import (
    AdminUserFactory, QuestionFactory, StudentUserFactory, TeacherUserFactory,
    WordFactory, WordSetFactory,
)


def _seed_mastery_levels():
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


def _make_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _run_command(*args):
    out = StringIO()
    call_command('compute_item_stats', *args, stdout=out)
    return out.getvalue()


def _add_answers(question, outcomes, users=None):
    """One UserAnswer per outcome, each from a fresh student by default."""
    for i, is_correct in enumerate(outcomes):
        user = users[i] if users else StudentUserFactory()
        UserAnswer.objects.create(
            user=user, question=question, user_answer='x', is_correct=is_correct,
        )


def _answer_at(user, question, is_correct, when):
    """UserAnswer with an explicit answered_at (auto_now_add bypass)."""
    answer = UserAnswer.objects.create(
        user=user, question=question, user_answer='x', is_correct=is_correct,
    )
    UserAnswer.objects.filter(pk=answer.pk).update(answered_at=when)
    return answer


# =============================================================================
# STATS MATH
# =============================================================================

@pytest.mark.django_db
class TestComputeItemStatsMath:
    def test_shrunk_difficulty_known_outcomes(self):
        # Same type for both questions so m mixes them: 16 answers, 6 correct.
        q1 = QuestionFactory(question_type=Question.QuestionType.DEFINITION_MC_SINGLE)
        q2 = QuestionFactory(question_type=Question.QuestionType.DEFINITION_MC_SINGLE)
        _add_answers(q1, [True] * 6)
        _add_answers(q2, [False] * 10)

        _run_command()

        q1.refresh_from_db()
        q2.refresh_from_db()
        # m = 6/16 = 0.375
        # q1: p = (6 + 8*0.375) / (6 + 8) = 9/14
        assert q1.difficulty_index == pytest.approx(9 / 14)
        # q2: p = (0 + 8*0.375) / (10 + 8) = 1/6
        assert q2.difficulty_index == pytest.approx(1 / 6)
        assert q2.qa_flags == ['too_hard']
        assert q1.qa_flags == []

    def test_difficulty_null_below_min_n(self):
        question = QuestionFactory()
        _add_answers(question, [True, True, False, True])  # n=4 < 5

        _run_command()

        question.refresh_from_db()
        assert question.difficulty_index is None
        assert question.qa_flags == []
        # The check ran — only the stat is gated on n.
        assert question.qa_checked_at is not None

    def test_min_n_override(self):
        question = QuestionFactory()
        _add_answers(question, [True, False, True, False])  # n=4, 2 correct

        _run_command('--min-n', '3')

        question.refresh_from_db()
        # Single question of its type: m = 2/4 = 0.5; p = (2 + 8*0.5)/(4 + 8) = 0.5
        assert question.difficulty_index == pytest.approx(0.5)

    def test_discrimination_null_below_10_answers(self):
        question = QuestionFactory()
        _add_answers(question, [True] * 5 + [False] * 4)  # n=9

        _run_command()

        question.refresh_from_db()
        assert question.discrimination_index is None

    def test_discrimination_shrinkage_band(self):
        # n=15: 10 strong users (target correct, all other answers correct)
        # and 5 weak users (target wrong, other answers wrong). Leave-one-out
        # ability is perfectly correlated with the outcome -> d = 1.0, then
        # shrunk toward 0: 1.0 * (15 - 10) / 10 = 0.5.
        target = QuestionFactory(question_type=Question.QuestionType.DEFINITION_MC_SINGLE)
        other = QuestionFactory(question_type=Question.QuestionType.CONTEXT_MC_SINGLE)
        for _ in range(10):
            strong = StudentUserFactory()
            _add_answers(target, [True], users=[strong])
            _add_answers(other, [True], users=[strong])
        for _ in range(5):
            weak = StudentUserFactory()
            _add_answers(target, [False], users=[weak])
            _add_answers(other, [False], users=[weak])

        _run_command()

        target.refresh_from_db()
        assert target.discrimination_index == pytest.approx(0.5)
        assert 'low_discrimination' not in target.qa_flags

    def test_discrimination_null_when_zero_variance(self):
        # n=20 but every answer correct -> outcomes have zero variance.
        question = QuestionFactory()
        _add_answers(question, [True] * 20)

        _run_command()

        question.refresh_from_db()
        assert question.difficulty_index == pytest.approx(1.0)
        assert question.discrimination_index is None
        assert question.qa_flags == ['too_easy']

    def test_low_discrimination_flag(self):
        # n=20 (no shrinkage). Four ability groups (0, 1/3, 2/3, 1 via three
        # other questions) with the same 3/5 pass rate on the target in every
        # group -> outcome independent of ability -> d = 0 < 0.2.
        target = QuestionFactory(question_type=Question.QuestionType.DEFINITION_MC_SINGLE)
        others = [
            QuestionFactory(question_type=Question.QuestionType.CONTEXT_MC_SINGLE)
            for _ in range(3)
        ]
        for ability_group in range(4):
            for i in range(5):
                user = StudentUserFactory()
                for j, other in enumerate(others):
                    _add_answers(other, [j < ability_group], users=[user])
                _add_answers(target, [i % 2 == 0], users=[user])

        _run_command()

        target.refresh_from_db()
        assert target.discrimination_index == pytest.approx(0.0, abs=1e-9)
        assert 'low_discrimination' in target.qa_flags

    def test_too_easy_flag(self):
        question = QuestionFactory()
        _add_answers(question, [True] * 20)

        _run_command()

        question.refresh_from_db()
        assert question.difficulty_index > 0.9
        assert 'too_easy' in question.qa_flags


# =============================================================================
# FLAG BOOKKEEPING
# =============================================================================

@pytest.mark.django_db
class TestFlagBookkeeping:
    def test_foreign_flags_preserved_stat_flags_replaced(self):
        question = QuestionFactory(qa_flags=['verification_mismatch', 'too_easy'])
        _add_answers(question, [True, False, True, False, True, False])  # p=0.5

        _run_command()

        question.refresh_from_db()
        assert question.qa_flags == ['verification_mismatch']
        assert question.qa_checked_at is not None

    def test_never_sets_is_serve_excluded(self):
        question = QuestionFactory()
        _add_answers(question, [False] * 20)  # too_hard territory

        _run_command()

        question.refresh_from_db()
        assert 'too_hard' in question.qa_flags
        assert question.is_serve_excluded is False

    def test_dry_run_writes_nothing(self):
        question = QuestionFactory()
        _add_answers(question, [True] * 20)

        out = _run_command('--dry-run')

        question.refresh_from_db()
        assert question.difficulty_index is None
        assert question.qa_checked_at is None
        assert 'dry-run' in out

    def test_sentence_write_questions_skipped(self):
        question = QuestionFactory(
            question_type=Question.QuestionType.SENTENCE_WRITE_GUIDED,
            correct_answers=[],
            options={'scenario': 'x', 'rubric_anchors': []},
        )
        _add_answers(question, [True] * 10)

        _run_command()

        question.refresh_from_db()
        assert question.qa_checked_at is None
        assert question.difficulty_index is None

    def test_word_set_scoping(self):
        ws1 = WordSetFactory()
        ws2 = WordSetFactory()
        word1 = WordFactory()
        word2 = WordFactory()
        ws1.words.add(word1)
        ws2.words.add(word2)
        q1 = QuestionFactory(word=word1)
        q2 = QuestionFactory(word=word2)
        _add_answers(q1, [True] * 6)
        _add_answers(q2, [True] * 6)

        _run_command('--word-set', str(ws1.id))

        q1.refresh_from_db()
        q2.refresh_from_db()
        assert q1.qa_checked_at is not None
        assert q2.qa_checked_at is None
        assert q2.difficulty_index is None

    def test_output_writes_json_report(self, tmp_path):
        question = QuestionFactory()
        _add_answers(question, [True] * 6)
        out_path = tmp_path / 'report.json'

        _run_command('--output', str(out_path))

        payload = json.loads(out_path.read_text())
        assert payload['question_types']
        row = payload['question_types'][0]
        assert row['question_type'] == question.question_type
        assert row['questions'] == 1
        assert row['mean_difficulty'] is not None


# =============================================================================
# --gradient (analysis only)
# =============================================================================

@pytest.mark.django_db
class TestGradientMode:
    def test_only_delayed_answers_counted(self):
        word = WordFactory()
        q_l1 = QuestionFactory(
            word=word, question_type=Question.QuestionType.DEFINITION_MC_SINGLE,
        )
        q_l3 = QuestionFactory(
            word=word, question_type=Question.QuestionType.CONTEXT_MC_SINGLE,
        )
        user = StudentUserFactory()
        t0 = timezone.now() - timedelta(days=5)
        _answer_at(user, q_l1, True, t0)                              # first: no gap
        _answer_at(user, q_l3, False, t0 + timedelta(hours=1))        # gap 1h: excluded
        _answer_at(user, q_l1, True, t0 + timedelta(hours=30))        # gap 29h: kept (L1)

        out = _run_command('--gradient')

        l1_lines = [l for l in out.splitlines() if l.startswith('L1')]
        assert len(l1_lines) == 1
        assert '1.000' in l1_lines[0]  # the single kept answer was correct
        # The 1h-gap L3 answer was filtered out -> no L3 row at all.
        assert not any(l.startswith('L3') for l in out.splitlines())

    def test_skips_types_not_in_level_mapping(self):
        word = WordFactory()
        question = QuestionFactory(
            word=word, question_type=Question.QuestionType.SYNONYM_MATCHING,
        )
        user = StudentUserFactory()
        t0 = timezone.now() - timedelta(days=5)
        _answer_at(user, question, True, t0)
        _answer_at(user, question, True, t0 + timedelta(hours=48))

        out = _run_command('--gradient')

        assert 'no delayed answers' in out

    def test_gradient_does_not_write(self):
        word = WordFactory()
        question = QuestionFactory(word=word)
        user = StudentUserFactory()
        t0 = timezone.now() - timedelta(days=5)
        _answer_at(user, question, True, t0)
        _answer_at(user, question, True, t0 + timedelta(hours=48))

        _run_command('--gradient')

        question.refresh_from_db()
        assert question.qa_checked_at is None
        assert question.difficulty_index is None


# =============================================================================
# FLAG ENDPOINT
# =============================================================================

@pytest.mark.django_db
class TestFlagQuestionView:
    def test_admin_can_flag_and_unflag(self):
        client = _make_client(AdminUserFactory())
        question = QuestionFactory()

        response = client.post(f'/api/questions/{question.id}/flag/', {'flagged': True}, format='json')
        assert response.status_code == 200
        assert response.data == {'id': question.id, 'is_serve_excluded': True}
        question.refresh_from_db()
        assert question.is_serve_excluded is True

        response = client.post(f'/api/questions/{question.id}/flag/', {'flagged': False}, format='json')
        assert response.status_code == 200
        assert response.data['is_serve_excluded'] is False
        question.refresh_from_db()
        assert question.is_serve_excluded is False

    def test_teacher_forbidden(self):
        client = _make_client(TeacherUserFactory())
        question = QuestionFactory()
        response = client.post(f'/api/questions/{question.id}/flag/', {'flagged': True}, format='json')
        assert response.status_code == 403
        question.refresh_from_db()
        assert question.is_serve_excluded is False

    def test_student_forbidden(self):
        client = _make_client(StudentUserFactory())
        question = QuestionFactory()
        response = client.post(f'/api/questions/{question.id}/flag/', {'flagged': True}, format='json')
        assert response.status_code == 403
        question.refresh_from_db()
        assert question.is_serve_excluded is False

    def test_flagged_must_be_boolean(self):
        client = _make_client(AdminUserFactory())
        question = QuestionFactory()
        response = client.post(f'/api/questions/{question.id}/flag/', {'flagged': 'yes'}, format='json')
        assert response.status_code == 400

    def test_unknown_question_404(self):
        client = _make_client(AdminUserFactory())
        response = client.post('/api/questions/999999/flag/', {'flagged': True}, format='json')
        assert response.status_code == 404


# =============================================================================
# SERVE EXCLUSION (NextPracticeWordView)
# =============================================================================

@pytest.mark.django_db
class TestServeExcludedQuestions:
    @pytest.fixture(autouse=True)
    def setup(self):
        _seed_mastery_levels()
        self.student = StudentUserFactory()
        self.client = _make_client(self.student)
        self.word = WordFactory(text='bright')
        self.level1 = MasteryLevel.objects.get(level_id=1)
        UserWordProgress.objects.create(
            user=self.student, word=self.word,
            level=self.level1, next_review_at=timezone.now(),
        )

    def _make_question(self, excluded, at_level=True, text='Q'):
        question = QuestionFactory(
            word=self.word, question_text=text, lexile_score=650,
            is_serve_excluded=excluded,
        )
        if at_level:
            question.suitable_levels.add(self.level1)
        return question

    def test_excluded_question_never_served_when_alternative_exists(self):
        self._make_question(excluded=True, text='FLAGGED')
        good = self._make_question(excluded=False, text='GOOD')

        response = self.client.get('/api/practice/next/')

        assert response.status_code == 200
        assert response.data['id'] == good.id
        assert response.data['question_text'] == 'GOOD'

    def test_any_question_fallback_still_excludes_flagged(self):
        # The flagged question is the ONLY one tagged at the word's level; the
        # fallback (any question for the word) must still skip it and serve the
        # untagged, unflagged one.
        self._make_question(excluded=True, at_level=True, text='FLAGGED')
        good = self._make_question(excluded=False, at_level=False, text='GOOD')

        response = self.client.get('/api/practice/next/')

        assert response.status_code == 200
        assert response.data['id'] == good.id

    def test_word_with_only_excluded_questions_is_not_picked(self):
        self._make_question(excluded=True, text='FLAGGED')

        response = self.client.get('/api/practice/next/')

        # No serveable question -> the word isn't due-eligible at all.
        assert response.status_code == 200
        assert 'message' in response.data
        assert 'question_text' not in response.data
