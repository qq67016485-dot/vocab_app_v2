"""Tests for the translations step in the generation pipeline."""
import pytest
from unittest.mock import patch

from vocabulary.models import (
    Translation, GenerationJob, GenerationJobLog,
)
from vocabulary.services.generation_pipeline_service import (
    _step_generate_translations,
)
from tests.factories import (
    WordFactory, WordDefinitionFactory, GenerationJobFactory,
)
from tests.vocabulary.generation_fixtures import (
    WORD_LOOKUP_RESPONSE, TRANSLATION_RESPONSE,
)


@pytest.mark.django_db
class TestStepGenerateTranslations:
    """Tests for _step_generate_translations — LLM translates definitions + examples."""

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_creates_translation_records(self, mock_load, mock_anthropic):
        mock_load.return_value = "Translate {items_to_translate} into {target_language}"
        mock_anthropic.return_value = TRANSLATION_RESPONSE
        word1 = WordFactory(text='bright')
        # Use definition/example texts that match the TRANSLATION_RESPONSE source_text values
        WordDefinitionFactory(
            word=word1,
            definition_text='Giving out or reflecting a lot of light; shining.',
            example_sentence='The bright stars lit up the night sky.',
        )
        word2 = WordFactory(text='discover')
        WordDefinitionFactory(
            word=word2,
            definition_text='To find something for the first time.',
            example_sentence='She wanted to discover new places.',
        )
        job = GenerationJobFactory(input_words=['bright', 'discover'], target_language='zh-CN')

        _step_generate_translations(job, [word1, word2], WORD_LOOKUP_RESPONSE['words'])

        assert Translation.objects.count() == 4  # 2 words x 2 fields (definition + example)

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_creates_translation_log(self, mock_load, mock_anthropic):
        mock_load.return_value = "Translate template"
        mock_anthropic.return_value = TRANSLATION_RESPONSE
        word1 = WordFactory(text='bright')
        WordDefinitionFactory(
            word=word1,
            definition_text='Giving out or reflecting a lot of light; shining.',
            example_sentence='The bright stars lit up the night sky.',
        )
        job = GenerationJobFactory(input_words=['bright'], target_language='zh-CN')

        _step_generate_translations(job, [word1], [WORD_LOOKUP_RESPONSE['words'][0]])

        log = GenerationJobLog.objects.get(job=job, step=GenerationJobLog.Step.TRANSLATION)
        assert log.status == GenerationJob.Status.COMPLETED
