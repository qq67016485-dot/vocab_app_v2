"""Tests for the question generation step in the generation pipeline."""
import pytest
from unittest.mock import patch

from vocabulary.models import (
    Question, GenerationJob, GenerationJobLog,
)
from vocabulary.services.generation_pipeline_service import (
    _step_generate_questions,
)
from tests.factories import (
    WordFactory, WordDefinitionFactory, GenerationJobFactory,
    MasteryLevelFactory,
)
from tests.vocabulary.generation_fixtures import (
    WORD_LOOKUP_RESPONSE, QUESTION_RESPONSE,
)


def _question_response_for(*terms):
    """Build a QUESTION_RESPONSE with one question set per given term.

    A batch is only treated as complete when every word in it has questions, so
    a batch's mocked response must cover all of that batch's terms.
    """
    return {
        "generated_question_sets": [
            {
                "term": term,
                "questions": [
                    {
                        "question_type": "DEFINITION_MC_SINGLE",
                        "question_text": f"What does '{term}' mean?",
                        "options": ["A", "B", "C", "D"],
                        "correct_answers": ["A"],
                        "explanation": f"{term} explanation.",
                        "example_sentence": f"The {term} example.",
                        "lexile_score": 600,
                    },
                ],
            }
            for term in terms
        ],
    }


@pytest.mark.django_db
class TestStepGenerateQuestions:
    """Tests for _step_generate_questions — LLM generates practice questions per word."""

    @pytest.fixture(autouse=True)
    def seed_mastery_level(self):
        # DEFINITION_MC_SINGLE maps to level 1; the step now fails fast when a
        # question's mastery level cannot be attached.
        MasteryLevelFactory(level_id=1)

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_creates_questions(self, mock_load, mock_anthropic):
        mock_load.return_value = "Question gen template"
        mock_anthropic.return_value = QUESTION_RESPONSE
        word = WordFactory(text='bright')
        WordDefinitionFactory(word=word)
        job = GenerationJobFactory(input_words=['bright'])

        _step_generate_questions(job, [word], WORD_LOOKUP_RESPONSE['words'])

        assert Question.objects.filter(word=word).count() >= 1
        q = Question.objects.filter(word=word).first()
        assert q.generation_job == job

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_updates_questions_created_counter(self, mock_load, mock_anthropic):
        mock_load.return_value = "Question gen template"
        mock_anthropic.return_value = QUESTION_RESPONSE
        word = WordFactory(text='bright')
        WordDefinitionFactory(word=word)
        job = GenerationJobFactory(input_words=['bright'])

        _step_generate_questions(job, [word], WORD_LOOKUP_RESPONSE['words'])

        job.refresh_from_db()
        assert job.questions_created >= 1

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_creates_question_gen_log(self, mock_load, mock_anthropic):
        mock_load.return_value = "Question gen template"
        mock_anthropic.return_value = QUESTION_RESPONSE
        word = WordFactory(text='bright')
        WordDefinitionFactory(word=word)
        job = GenerationJobFactory(input_words=['bright'])

        _step_generate_questions(job, [word], WORD_LOOKUP_RESPONSE['words'])

        log = GenerationJobLog.objects.get(job=job, step=GenerationJobLog.Step.QUESTION_GEN)
        assert log.status == GenerationJob.Status.COMPLETED

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_failed_batch_persists_succeeded_batches(self, mock_load, mock_gemini):
        """A mid-step failure leaves earlier batches' questions committed in the DB."""
        mock_load.return_value = "Question gen template"
        # 3 words => 2 batches (size 2): [w0, w1], [w2]. First batch ok, second fails.
        words, words_data = self._make_words(['alpha', 'beta', 'gamma'])
        mock_gemini.side_effect = [
            _question_response_for('alpha', 'beta'),  # batch 1 covers alpha + beta
            RuntimeError('LLM truncated'),     # batch 2 (gamma) fails
        ]
        job = GenerationJobFactory(input_words=['alpha', 'beta', 'gamma'])

        with pytest.raises(RuntimeError):
            _step_generate_questions(job, words, words_data)

        # Batch 1's question survived even though batch 2 raised.
        assert Question.objects.filter(generation_job=job, word=words[0]).count() == 1
        assert Question.objects.filter(generation_job=job, word=words[2]).count() == 0

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_resume_skips_completed_batches_and_avoids_duplicates(self, mock_load, mock_gemini):
        """On resume, batches whose words already have questions are not regenerated."""
        mock_load.return_value = "Question gen template"
        words, words_data = self._make_words(['alpha', 'beta', 'gamma'])
        job = GenerationJobFactory(input_words=['alpha', 'beta', 'gamma'])

        # First run: batch 1 (alpha/beta) succeeds, batch 2 (gamma) fails.
        mock_gemini.side_effect = [
            _question_response_for('alpha', 'beta'),
            RuntimeError('LLM truncated'),
        ]
        with pytest.raises(RuntimeError):
            _step_generate_questions(job, words, words_data)
        assert Question.objects.filter(generation_job=job).count() == 2
        alpha_qid = Question.objects.get(generation_job=job, word=words[0]).id

        # Resume: only the gamma batch should call the LLM now.
        mock_gemini.reset_mock(side_effect=True)
        mock_gemini.side_effect = [_question_response_for('gamma')]
        _step_generate_questions(job, words, words_data)

        # The completed batch was skipped — exactly one LLM call this run.
        assert mock_gemini.call_count == 1
        # No duplicate created for alpha; its original row is untouched.
        assert Question.objects.filter(generation_job=job, word=words[0]).count() == 1
        assert Question.objects.get(generation_job=job, word=words[0]).id == alpha_qid
        # Gamma's batch now produced a question.
        assert Question.objects.filter(generation_job=job, word=words[2]).count() == 1

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_counter_reflects_total_after_resume(self, mock_load, mock_gemini):
        """questions_created counts all of the job's questions, not just this run's."""
        mock_load.return_value = "Question gen template"
        words, words_data = self._make_words(['alpha', 'beta', 'gamma'])
        job = GenerationJobFactory(input_words=['alpha', 'beta', 'gamma'])

        mock_gemini.side_effect = [
            _question_response_for('alpha', 'beta'),
            RuntimeError('LLM truncated'),
        ]
        with pytest.raises(RuntimeError):
            _step_generate_questions(job, words, words_data)

        mock_gemini.reset_mock(side_effect=True)
        mock_gemini.side_effect = [_question_response_for('gamma')]
        _step_generate_questions(job, words, words_data)

        job.refresh_from_db()
        assert job.questions_created == Question.objects.filter(generation_job=job).count()
        assert job.questions_created == 3
        log = GenerationJobLog.objects.filter(
            job=job, step=GenerationJobLog.Step.QUESTION_GEN,
            status=GenerationJob.Status.COMPLETED,
        ).latest('created_at')
        assert log.output_data['batches_skipped'] == 1

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_batch_missing_word_fails_step(self, mock_load, mock_gemini):
        """A word the LLM silently dropped must fail the batch — otherwise it
        never gets questions and resume never retries it."""
        mock_load.return_value = "Question gen template"
        words, words_data = self._make_words(['alpha', 'beta'])
        # One batch of 2, but the response only covers alpha.
        mock_gemini.return_value = _question_response_for('alpha')
        job = GenerationJobFactory(input_words=['alpha', 'beta'])

        with pytest.raises(ValueError, match='beta'):
            _step_generate_questions(job, words, words_data)

        log = GenerationJobLog.objects.get(
            job=job, step=GenerationJobLog.Step.QUESTION_GEN,
        )
        assert log.status == GenerationJob.Status.FAILED
        assert 'beta' in log.error_message

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_unmapped_question_type_fails_batch_without_orphan_row(
        self, mock_load, mock_gemini,
    ):
        """A question_type outside QUESTION_TYPE_LEVEL would persist a row no
        mastery level ever serves; the batch must fail instead."""
        mock_load.return_value = "Question gen template"
        words, words_data = self._make_words(['alpha'])
        response = _question_response_for('alpha')
        response['generated_question_sets'][0]['questions'][0]['question_type'] = (
            'NOT_A_REAL_TYPE'
        )
        mock_gemini.return_value = response
        job = GenerationJobFactory(input_words=['alpha'])

        with pytest.raises(ValueError, match='NOT_A_REAL_TYPE'):
            _step_generate_questions(job, words, words_data)

        assert Question.objects.filter(generation_job=job).count() == 0

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_question_type_whitespace_normalized(self, mock_load, mock_gemini):
        """A trailing-space type from the LLM maps to the same level instead
        of orphaning the row."""
        mock_load.return_value = "Question gen template"
        words, words_data = self._make_words(['alpha'])
        response = _question_response_for('alpha')
        response['generated_question_sets'][0]['questions'][0]['question_type'] = (
            'DEFINITION_MC_SINGLE '
        )
        mock_gemini.return_value = response
        job = GenerationJobFactory(input_words=['alpha'])

        _step_generate_questions(job, words, words_data)

        question = Question.objects.get(generation_job=job)
        assert question.question_type == 'DEFINITION_MC_SINGLE'
        assert list(
            question.suitable_levels.values_list('level_id', flat=True)
        ) == [1]

    def _make_words(self, terms):
        """Create Word + WordDefinition rows and the matching words_data list."""
        words = []
        words_data = []
        for term in terms:
            word = WordFactory(text=term)
            WordDefinitionFactory(word=word)
            words.append(word)
            words_data.append({
                'term': term,
                'part_of_speech': 'noun',
                'definition': f'Definition of {term}',
                'example_sentence': f'{term} is used in a sentence.',
            })
        return words, words_data
