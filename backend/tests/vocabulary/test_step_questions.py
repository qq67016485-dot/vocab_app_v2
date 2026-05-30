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
)
from tests.vocabulary.generation_fixtures import (
    WORD_LOOKUP_RESPONSE, QUESTION_RESPONSE,
)


@pytest.mark.django_db
class TestStepGenerateQuestions:
    """Tests for _step_generate_questions — LLM generates practice questions per word."""

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
