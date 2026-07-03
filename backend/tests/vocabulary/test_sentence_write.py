"""Tests for the sentence-writing (productive, LLM-judged) question feature.

Covers: the generation step, the answer-time judge service, the scoring branch
in PracticeService, the submit-view revision loop, the selection guard, and the
student serializer's anchor/model-sentence hiding.
See docs/feature_plan/design-sentence-writing-questions.md.
"""
import pytest
from unittest.mock import patch

from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from vocabulary.models import (
    Question, MasteryLevel, UserWordProgress, UserAnswer,
)
from vocabulary.serializers import QuestionSerializer
from vocabulary.services.practice_service import PracticeService
from vocabulary.services import sentence_evaluation_service as judge
from vocabulary.services.generation.step_sentence_write import (
    _step_generate_sentence_write,
)
from tests.factories import (
    StudentUserFactory, WordFactory, WordDefinitionFactory,
    PrimerCardContentFactory, GenerationJobFactory,
)

GUIDED = Question.QuestionType.SENTENCE_WRITE_GUIDED
OPEN = Question.QuestionType.SENTENCE_WRITE_OPEN


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
    for lid, name, interval, pts, hidden in levels:
        MasteryLevel.objects.update_or_create(
            level_id=lid,
            defaults={
                'level_name': name, 'interval_days': interval,
                'points_to_promote': pts, 'is_hidden': hidden,
            },
        )


def _guided_response(*terms):
    return {'sentence_tasks': [
        {
            'term': t,
            'usage_reasoning': 'reasoning',
            'scenario': f'Write about cleaning, using "{t}".',
            'sentence_starter': f'I was {t} about ___.',
            'model_sentence': f'I was {t} about my desk.',
            'lexile_score': 620,
            'intended_sense': 'careful about detail',
            'acceptable_use_notes': ['simple is fine', 'reject "fast"'],
        } for t in terms
    ]}


def _open_response(*terms):
    return {'sentence_tasks': [
        {
            'term': t,
            'usage_reasoning': 'reasoning',
            'scenario': f'Think of a time and use "{t}".',
            'model_sentence': f'I chose to {t}.',
            'lexile_score': 810,
            'intended_sense': 'keep going',
            'acceptable_use_notes': ['any effort shown'],
        } for t in terms
    ]}


@pytest.mark.django_db
class TestSentenceWriteGeneration:
    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_creates_two_variants_per_word(self, mock_load, mock_llm):
        _seed_mastery_levels()
        mock_load.return_value = 'template'
        # guided call first, then open (order matches _VARIANTS)
        mock_llm.side_effect = [_guided_response('meticulous'), _open_response('meticulous')]
        word = WordFactory(text='meticulous')
        WordDefinitionFactory(word=word)
        # High Lexile → both variants (content Lexile > guided-only threshold).
        job = GenerationJobFactory(input_words=['meticulous'], target_lexile=800)

        _step_generate_sentence_write(
            job, [word], [{'term': 'meticulous', 'definition': 'careful'}],
        )

        assert Question.objects.filter(word=word, question_type=GUIDED).count() == 1
        assert Question.objects.filter(word=word, question_type=OPEN).count() == 1

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_guided_gets_l4_open_gets_l5_and_anchors_stored(self, mock_load, mock_llm):
        _seed_mastery_levels()
        mock_load.return_value = 'template'
        mock_llm.side_effect = [_guided_response('meticulous'), _open_response('meticulous')]
        word = WordFactory(text='meticulous')
        WordDefinitionFactory(word=word)
        job = GenerationJobFactory(input_words=['meticulous'], target_lexile=800)

        _step_generate_sentence_write(
            job, [word], [{'term': 'meticulous', 'definition': 'careful'}],
        )

        guided = Question.objects.get(word=word, question_type=GUIDED)
        open_q = Question.objects.get(word=word, question_type=OPEN)
        assert list(guided.suitable_levels.values_list('level_id', flat=True)) == [4]
        assert list(open_q.suitable_levels.values_list('level_id', flat=True)) == [5]
        # Rubric anchors + starter live in options; model sentence in example_sentence.
        assert guided.options['intended_sense'] == 'careful about detail'
        assert guided.options['acceptable_use_notes']
        assert guided.options['sentence_starter']
        assert guided.example_sentence
        assert guided.correct_answers == []
        # Open variant carries no starter.
        assert 'sentence_starter' not in open_q.options

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_guided_only_below_threshold_skips_open_and_serves_l4_and_l5(
        self, mock_load, mock_llm,
    ):
        _seed_mastery_levels()
        mock_load.return_value = 'template'
        # Only the guided variant is generated; open is never called.
        mock_llm.side_effect = [_guided_response('meticulous')]
        word = WordFactory(text='meticulous')
        WordDefinitionFactory(word=word)
        # target 650 → content Lexile int(650*0.85)=552 <= 600 → guided-only.
        job = GenerationJobFactory(input_words=['meticulous'], target_lexile=650)

        _step_generate_sentence_write(
            job, [word], [{'term': 'meticulous', 'definition': 'careful'}],
        )

        assert Question.objects.filter(word=word, question_type=OPEN).count() == 0
        guided = Question.objects.get(word=word, question_type=GUIDED)
        # Guided serves both L4 and L5 when open is withheld.
        assert sorted(
            guided.suitable_levels.values_list('level_id', flat=True)
        ) == [4, 5]
        # The open template was never invoked (single guided LLM call).
        assert mock_llm.call_count == 1

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_dropped_word_fails_batch(self, mock_load, mock_llm):
        """A word the LLM silently dropped must fail the batch — resume
        tracks per-word rows, so it would otherwise never be retried."""
        _seed_mastery_levels()
        mock_load.return_value = 'template'
        # Guided response covers only one of the two words in the batch.
        mock_llm.side_effect = [_guided_response('meticulous')]
        word_a = WordFactory(text='meticulous')
        word_b = WordFactory(text='persist')
        job = GenerationJobFactory(
            input_words=['meticulous', 'persist'], target_lexile=800,
        )
        words_data = [
            {'term': 'meticulous', 'definition': 'careful'},
            {'term': 'persist', 'definition': 'keep going'},
        ]

        with pytest.raises(ValueError, match='persist'):
            _step_generate_sentence_write(job, [word_a, word_b], words_data)

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_idempotent_resume_skips_completed_words(self, mock_load, mock_llm):
        _seed_mastery_levels()
        mock_load.return_value = 'template'
        mock_llm.side_effect = [_guided_response('meticulous'), _open_response('meticulous')]
        word = WordFactory(text='meticulous')
        WordDefinitionFactory(word=word)
        job = GenerationJobFactory(input_words=['meticulous'], target_lexile=800)
        words_data = [{'term': 'meticulous', 'definition': 'careful'}]

        _step_generate_sentence_write(job, [word], words_data)
        first_ids = set(Question.objects.filter(word=word).values_list('id', flat=True))

        # Re-run: both variants already present → no LLM calls, no duplicates.
        mock_llm.side_effect = AssertionError("should not call LLM on full resume")
        _step_generate_sentence_write(job, [word], words_data)
        assert set(Question.objects.filter(word=word).values_list('id', flat=True)) == first_ids


@pytest.mark.django_db
class TestSentenceJudge:
    def setup_method(self):
        cache.clear()

    def _question(self):
        word = WordFactory(text='meticulous')
        return Question.objects.create(
            word=word, question_type=GUIDED,
            question_text='Write about cleaning.',
            options={'intended_sense': 'careful', 'acceptable_use_notes': ['x']},
            correct_answers=[], example_sentence='I was meticulous about my desk.',
            lexile_score=620,
        )

    @patch('vocabulary.services.sentence_evaluation_service._call_llm_with_config')
    @patch('vocabulary.services.sentence_evaluation_service.get_step_config')
    def test_correct_verdict(self, mock_cfg, mock_llm):
        mock_cfg.return_value = {'primary': {'model': 'm', 'provider_type': 'gemini_native'}}
        mock_llm.return_value = {'verdict': 'correct', 'error_type': 'none', 'hint': 'Great!'}
        with patch('vocabulary.services.llm_service.load_prompt_template', return_value='t'):
            result = judge.evaluate_sentence(self._question(), 'I was meticulous about my desk.')
        assert result['is_correct'] is True
        assert result['verdict'] == 'correct'

    @patch('vocabulary.services.sentence_evaluation_service._call_llm_with_config')
    @patch('vocabulary.services.sentence_evaluation_service.get_step_config')
    def test_unknown_verdict_normalized_to_incorrect(self, mock_cfg, mock_llm):
        mock_cfg.return_value = {'primary': {'model': 'm', 'provider_type': 'gemini_native'}}
        mock_llm.return_value = {'verdict': 'banana', 'hint': 'x'}
        with patch('vocabulary.services.llm_service.load_prompt_template', return_value='t'):
            result = judge.evaluate_sentence(self._question(), 'whatever')
        assert result['verdict'] == 'incorrect'
        assert result['is_correct'] is False

    @patch('vocabulary.services.sentence_evaluation_service._call_llm_with_config')
    @patch('vocabulary.services.sentence_evaluation_service.get_step_config')
    def test_circuit_breaker_trips_after_repeated_failures(self, mock_cfg, mock_llm):
        mock_cfg.return_value = {'primary': {'model': 'm', 'provider_type': 'gemini_native'}}
        mock_llm.side_effect = RuntimeError('down')
        assert judge.is_judge_healthy() is True
        with patch('vocabulary.services.llm_service.load_prompt_template', return_value='t'):
            for _ in range(3):
                with pytest.raises(judge.SentenceJudgeUnavailable):
                    judge.evaluate_sentence(self._question(), 'x')
        assert judge.is_judge_healthy() is False

    @patch('vocabulary.services.sentence_evaluation_service.get_step_config')
    def test_config_error_also_trips_circuit_breaker(self, mock_cfg):
        # A missing/broken sentence_judge step config is at least as persistent
        # as a network failure — without tripping the breaker the picker would
        # keep serving sentence questions that can never be judged, trapping
        # the student on the same word.
        from vocabulary.services.generation.llm_config_service import LLMConfigError
        mock_cfg.side_effect = LLMConfigError('no config for sentence_judge')
        assert judge.is_judge_healthy() is True
        for _ in range(3):
            with pytest.raises(judge.SentenceJudgeUnavailable):
                judge.evaluate_sentence(self._question(), 'x')
        assert judge.is_judge_healthy() is False


@pytest.mark.django_db
class TestSentenceWriteScoring:
    @pytest.fixture(autouse=True)
    def setup(self):
        cache.clear()
        _seed_mastery_levels()
        self.student = StudentUserFactory()
        self.word = WordFactory(text='meticulous')
        WordDefinitionFactory(word=self.word)
        self.question = Question.objects.create(
            word=self.word, question_type=GUIDED, question_text='Write.',
            options={'intended_sense': 'x', 'acceptable_use_notes': ['y']},
            correct_answers=[], example_sentence='Model.', lexile_score=620,
        )
        level4 = MasteryLevel.objects.get(level_id=4)
        self.mastery = UserWordProgress.objects.create(
            user=self.student, word=self.word, level=level4,
            mastery_points=3, next_review_at=timezone.now(),
        )

    def _judgment(self, rule, is_correct):
        return {'is_correct': is_correct, 'quality_rule': rule,
                'judge_result': {'verdict': 'x', 'error_type': 'none'}}

    def test_productive_correct_awards_point_and_bonus(self):
        result = PracticeService.process_answer(
            self.student, self.question.id, 'A meticulous sentence.',
            duration_seconds=None, answer_switches=0,
            productive_judgment=self._judgment('productive_correct', True),
        )
        assert result['is_correct'] is True
        assert result['mastery_points'] == 4
        assert result['bonus_info'].get('sentence_writing') == 5

    def test_productive_missed_softened_no_demotion(self):
        result = PracticeService.process_answer(
            self.student, self.question.id, 'bad',
            duration_seconds=None, answer_switches=0,
            productive_judgment=self._judgment('productive_missed', False),
        )
        assert result['is_correct'] is False
        # -1 (softened), not -2; and no demotion below level 4.
        assert result['mastery_points'] == 2
        assert result['current_level_name'] == 'Proficient'

    def test_recovered_is_fragile(self):
        result = PracticeService.process_answer(
            self.student, self.question.id, 'A meticulous sentence.',
            duration_seconds=None, answer_switches=0,
            productive_judgment=self._judgment('productive_recovered', True),
        )
        assert result['is_fragile'] is True

    def test_judge_result_persisted_on_answer(self):
        PracticeService.process_answer(
            self.student, self.question.id, 'x',
            duration_seconds=None, answer_switches=0,
            productive_judgment=self._judgment('productive_missed', False),
        )
        answer = UserAnswer.objects.get(user=self.student, question=self.question)
        assert answer.judge_result is not None
        assert answer.judge_result['verdict'] == 'x'


@pytest.mark.django_db
class TestSentenceWriteSerializer:
    def test_hides_anchors_and_model_sentence(self):
        word = WordFactory(text='meticulous')
        PrimerCardContentFactory(word=word, kid_friendly_definition='very careful')
        q = Question.objects.create(
            word=word, question_type=GUIDED, question_text='Write.',
            options={'intended_sense': 'secret', 'acceptable_use_notes': ['secret'],
                     'sentence_starter': 'I was ___.'},
            correct_answers=[], example_sentence='Secret model sentence.',
            lexile_score=620,
        )
        data = QuestionSerializer(q).data
        # Judge anchors + model sentence must not leak.
        assert data['options'] is None
        assert data['example_sentence'] == ''
        # Student-safe subset present.
        assert data['sentence_write']['sentence_starter'] == 'I was ___.'
        assert data['sentence_write']['definition'] == 'very careful'
        assert data['sentence_write']['variant'] == 'guided'
        assert data['sentence_write']['max_revisions'] == 3


@pytest.mark.django_db
class TestSentenceWriteSubmitView:
    @pytest.fixture(autouse=True)
    def setup(self):
        cache.clear()
        _seed_mastery_levels()
        self.student = StudentUserFactory()
        self.client = APIClient()
        self.client.force_authenticate(user=self.student)
        self.word = WordFactory(text='meticulous')
        WordDefinitionFactory(word=self.word)
        self.question = Question.objects.create(
            word=self.word, question_type=GUIDED, question_text='Write.',
            options={'intended_sense': 'x', 'acceptable_use_notes': ['y']},
            correct_answers=[], example_sentence='Model sentence.', lexile_score=620,
        )
        level4 = MasteryLevel.objects.get(level_id=4)
        UserWordProgress.objects.create(
            user=self.student, word=self.word, level=level4,
            mastery_points=3, next_review_at=timezone.now(),
        )

    @patch('vocabulary.views.practice_views.sentence_evaluation_service.evaluate_sentence')
    def test_miss_returns_pending_hint_without_scoring(self, mock_eval):
        mock_eval.return_value = {
            'verdict': 'incorrect', 'error_type': 'wrong_meaning',
            'hint': 'Think about being careful.', 'is_correct': False,
        }
        resp = self.client.post('/api/practice/submit/', {
            'question_id': self.question.id, 'user_answer': 'wrong use',
        }, format='json')
        assert resp.status_code == 200
        assert resp.data['sentence_write_pending'] is True
        assert resp.data['hint']
        # No UserAnswer scored yet.
        assert not UserAnswer.objects.filter(user=self.student, question=self.question).exists()

    @patch('vocabulary.views.practice_views.sentence_evaluation_service.evaluate_sentence')
    def test_correct_scores_and_omits_model_sentence(self, mock_eval):
        mock_eval.return_value = {
            'verdict': 'correct', 'error_type': 'none', 'hint': 'Nice!', 'is_correct': True,
        }
        resp = self.client.post('/api/practice/submit/', {
            'question_id': self.question.id, 'user_answer': 'A meticulous sentence.',
        }, format='json')
        assert resp.status_code == 200
        assert resp.data['sentence_write_done'] is True
        assert resp.data['is_correct'] is True
        assert 'model_sentence' not in resp.data  # not revealed on success
        assert UserAnswer.objects.filter(user=self.student, question=self.question).count() == 1

    @patch('vocabulary.views.practice_views.sentence_evaluation_service.evaluate_sentence')
    def test_revisions_exhausted_reveals_model_and_scores_missed(self, mock_eval):
        mock_eval.return_value = {
            'verdict': 'incorrect', 'error_type': 'wrong_meaning',
            'hint': 'x', 'is_correct': False,
        }
        # Guided max_revisions = 3: three misses come back pending, the fourth
        # submit is terminal. Attempt state lives in the session, not the body.
        for attempt in range(3):
            resp = self.client.post('/api/practice/submit/', {
                'question_id': self.question.id, 'user_answer': f'wrong {attempt}',
            }, format='json')
            assert resp.data['sentence_write_pending'] is True
            assert resp.data['attempts_used'] == attempt + 1
        resp = self.client.post('/api/practice/submit/', {
            'question_id': self.question.id, 'user_answer': 'still wrong',
        }, format='json')
        assert resp.status_code == 200
        assert resp.data['sentence_write_done'] is True
        assert resp.data['is_correct'] is False
        assert resp.data['model_sentence'] == 'Model sentence.'

    @patch('vocabulary.views.practice_views.sentence_evaluation_service.evaluate_sentence')
    def test_cap_cannot_be_reset_by_client_supplied_state(self, mock_eval):
        """The old contract let the client post prior_attempts; a client that
        always claimed an empty history got unlimited judge calls and a
        first-try bonus. The cap must come from the server-held session."""
        mock_eval.return_value = {
            'verdict': 'incorrect', 'error_type': 'wrong_meaning',
            'hint': 'x', 'is_correct': False,
        }
        for _ in range(3):
            resp = self.client.post('/api/practice/submit/', {
                'question_id': self.question.id, 'user_answer': 'wrong',
                'prior_attempts': [],  # lie: claims a fresh first attempt
            }, format='json')
            assert resp.data.get('sentence_write_pending') is True
        # 4th submit, still claiming no history → must be terminal regardless.
        resp = self.client.post('/api/practice/submit/', {
            'question_id': self.question.id, 'user_answer': 'wrong',
            'prior_attempts': [],
        }, format='json')
        assert resp.data['sentence_write_done'] is True
        assert resp.data['is_correct'] is False

    @patch('vocabulary.views.practice_views.sentence_evaluation_service.evaluate_sentence')
    def test_correct_after_genuine_miss_gets_no_first_try_bonus(self, mock_eval):
        mock_eval.return_value = {
            'verdict': 'incorrect', 'error_type': 'wrong_meaning',
            'hint': 'x', 'is_correct': False,
        }
        resp = self.client.post('/api/practice/submit/', {
            'question_id': self.question.id, 'user_answer': 'wrong',
        }, format='json')
        assert resp.data['sentence_write_pending'] is True

        mock_eval.return_value = {
            'verdict': 'correct', 'error_type': 'none', 'hint': 'Nice!', 'is_correct': True,
        }
        resp = self.client.post('/api/practice/submit/', {
            'question_id': self.question.id, 'user_answer': 'A meticulous sentence.',
            'prior_attempts': [],  # client claims first try — server knows better
        }, format='json')
        assert resp.data['sentence_write_done'] is True
        assert resp.data['is_correct'] is True
        # productive_recovered, not productive_correct → no +5 sentence bonus.
        assert 'sentence_writing' not in resp.data.get('bonus_info', {})
        answer = UserAnswer.objects.get(user=self.student, question=self.question)
        assert answer.judge_result['attempts'] == 2

    @patch('vocabulary.views.practice_views.sentence_evaluation_service.evaluate_sentence')
    def test_daily_limit_blocks_judge_calls(self, mock_eval):
        # Pending misses never record a UserAnswer, so without this guard the
        # judge LLM could be called without bound past the daily limit.
        self.student.daily_question_limit = 1
        self.student.save()
        UserAnswer.objects.create(
            user=self.student, question=self.question,
            user_answer='x', is_correct=True, duration_seconds=5,
        )
        resp = self.client.post('/api/practice/submit/', {
            'question_id': self.question.id, 'user_answer': 'attempt',
        }, format='json')
        assert resp.status_code == 200
        assert resp.data['sentence_write_unavailable'] is True
        mock_eval.assert_not_called()

    @patch('vocabulary.views.practice_views.sentence_evaluation_service.evaluate_sentence')
    def test_judge_call_budget_caps_pending_misses(self, mock_eval):
        # Non-terminal misses don't record a UserAnswer, so the daily-answer
        # limit alone can't bound judge (LLM) calls. The per-day judge-call
        # budget (daily_question_limit × attempts-per-question) caps the
        # abandon-and-cycle pattern across distinct questions.
        mock_eval.return_value = {
            'verdict': 'incorrect', 'error_type': 'wrong_meaning',
            'hint': 'try again', 'is_correct': False,
        }
        self.student.daily_question_limit = 1  # budget = 1 × 4 = 4 judge calls
        self.student.save()
        level4 = MasteryLevel.objects.get(level_id=4)
        questions = []
        for i in range(6):
            w = WordFactory(text=f'word_{i}')
            UserWordProgress.objects.create(
                user=self.student, word=w, level=level4,
                mastery_points=3, next_review_at=timezone.now(),
            )
            questions.append(Question.objects.create(
                word=w, question_type=GUIDED, question_text='Write.',
                options={}, correct_answers=[], example_sentence='m.',
                lexile_score=620,
            ))

        # First 4 distinct questions each get one pending miss (a judge call).
        for q in questions[:4]:
            resp = self.client.post('/api/practice/submit/', {
                'question_id': q.id, 'user_answer': 'bad attempt',
            }, format='json')
            assert resp.data.get('sentence_write_pending') is True
        assert mock_eval.call_count == 4

        # The 5th is refused before the judge runs — budget exhausted.
        resp = self.client.post('/api/practice/submit/', {
            'question_id': questions[4].id, 'user_answer': 'bad attempt',
        }, format='json')
        assert resp.data.get('sentence_write_unavailable') is True
        assert mock_eval.call_count == 4  # not called again

        # Give-up makes no judge call, so it still works past the budget.
        resp = self.client.post('/api/practice/submit/', {
            'question_id': questions[5].id, 'user_answer': '', 'gave_up': True,
        }, format='json')
        assert resp.data.get('sentence_write_done') is True
        assert mock_eval.call_count == 4

    def test_give_up_reveals_model_without_judge_call(self):
        resp = self.client.post('/api/practice/submit/', {
            'question_id': self.question.id, 'user_answer': '',
            'gave_up': True,
        }, format='json')
        assert resp.status_code == 200
        assert resp.data['sentence_write_done'] is True
        assert resp.data['is_correct'] is False
        assert resp.data['model_sentence'] == 'Model sentence.'

    @patch('vocabulary.views.practice_views.sentence_evaluation_service.evaluate_sentence')
    def test_judge_unavailable_discards_without_scoring(self, mock_eval):
        mock_eval.side_effect = judge.SentenceJudgeUnavailable('down')
        resp = self.client.post('/api/practice/submit/', {
            'question_id': self.question.id, 'user_answer': 'attempt',
        }, format='json')
        assert resp.status_code == 200
        assert resp.data['sentence_write_unavailable'] is True
        assert not UserAnswer.objects.filter(user=self.student, question=self.question).exists()


@pytest.mark.django_db
class TestSentenceWriteSelectionGuard:
    @pytest.fixture(autouse=True)
    def setup(self):
        cache.clear()
        _seed_mastery_levels()
        self.student = StudentUserFactory()
        self.student.lexile_min = 0
        self.student.lexile_max = 2000
        self.student.save()
        self.client = APIClient()
        self.client.force_authenticate(user=self.student)
        self.word = WordFactory(text='meticulous')
        WordDefinitionFactory(word=self.word)
        self.level4 = MasteryLevel.objects.get(level_id=4)
        self.progress = UserWordProgress.objects.create(
            user=self.student, word=self.word, level=self.level4,
            next_review_at=timezone.now(), last_reviewed_at=timezone.now(),
        )
        self.sw = Question.objects.create(
            word=self.word, question_type=GUIDED, question_text='Write.',
            options={}, correct_answers=[], lexile_score=620,
        )
        self.sw.suitable_levels.add(self.level4)

    def test_excluded_when_judge_unhealthy(self):
        # Only a sentence-write question exists; when the judge is unhealthy it
        # must not be served. With no receptive fallback for this word the view
        # returns 404 (no suitable question) rather than the SW question — in
        # production L4/L5 words always have receptive types, so a receptive
        # question would be served instead.
        cache.set('sentence_judge:unhealthy', True, 300)
        resp = self.client.get('/api/practice/next/')
        assert resp.data.get('question_type') != GUIDED

    def test_served_when_judge_healthy(self):
        resp = self.client.get('/api/practice/next/')
        assert resp.status_code == 200
        assert resp.data.get('question_type') == GUIDED
