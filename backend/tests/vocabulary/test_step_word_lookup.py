"""Tests for word lookup and dedup steps in the generation pipeline."""
import pytest
from unittest.mock import patch

from vocabulary.models import (
    Word, WordDefinition, DefinitionEmbedding,
    GenerationJob, GenerationJobLog,
)
from vocabulary.services.generation_pipeline_service import (
    _reconstruct_context,
    _step_word_lookup,
    _step_dedup_and_persist,
)
from tests.factories import (
    WordFactory, WordDefinitionFactory, GenerationJobFactory,
)
from tests.vocabulary.generation_fixtures import WORD_LOOKUP_RESPONSE


@pytest.mark.django_db
class TestStepWordLookup:
    """Tests for _step_word_lookup — calls LLM to look up word definitions."""

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_returns_words_data(self, mock_load, mock_anthropic):
        mock_load.return_value = "System prompt template with {words}"
        mock_anthropic.return_value = WORD_LOOKUP_RESPONSE
        job = GenerationJobFactory(input_words=['bright', 'discover'])

        result = _step_word_lookup(job)

        assert len(result) == 2
        assert result[0]['term'] == 'bright'
        assert result[1]['term'] == 'discover'

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_creates_job_log(self, mock_load, mock_anthropic):
        mock_load.return_value = "System prompt"
        mock_anthropic.return_value = WORD_LOOKUP_RESPONSE
        job = GenerationJobFactory(input_words=['bright', 'discover'])

        _step_word_lookup(job)

        log = GenerationJobLog.objects.get(job=job, step=GenerationJobLog.Step.WORD_LOOKUP)
        assert log.status == GenerationJob.Status.COMPLETED
        assert log.duration_seconds is not None
        assert log.output_data is not None

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_logs_failure_on_llm_error(self, mock_load, mock_anthropic):
        mock_load.return_value = "System prompt"
        mock_anthropic.side_effect = ValueError("Could not parse JSON")
        job = GenerationJobFactory(input_words=['bright'])

        with pytest.raises(ValueError):
            _step_word_lookup(job)

        log = GenerationJobLog.objects.get(job=job, step=GenerationJobLog.Step.WORD_LOOKUP)
        assert log.status == GenerationJob.Status.FAILED
        assert 'Could not parse JSON' in log.error_message


@pytest.mark.django_db
class TestStepDedupAndPersist:
    """Tests for _step_dedup_and_persist — vector dedup + Word/WordDefinition creation."""

    @patch('vocabulary.services.embedding_service.find_duplicate_definition')
    @patch('vocabulary.services.embedding_service.get_embedding')
    def test_creates_new_words(self, mock_embed, mock_dedup):
        mock_dedup.return_value = None  # No duplicates
        mock_embed.return_value = [0.1] * 768
        job = GenerationJobFactory(input_words=['bright', 'discover'])

        words = _step_dedup_and_persist(job, WORD_LOOKUP_RESPONSE['words'])

        assert len(words) == 2
        assert Word.objects.filter(text='bright').exists()
        assert Word.objects.filter(text='discover').exists()
        # Definitions should be created
        assert WordDefinition.objects.count() == 2
        # Embeddings should be stored
        assert DefinitionEmbedding.objects.count() == 2

    @patch('vocabulary.services.embedding_service.find_duplicate_definition')
    @patch('vocabulary.services.embedding_service.get_embedding')
    def test_skips_duplicates(self, mock_embed, mock_dedup):
        existing_word = WordFactory(text='bright', part_of_speech='adjective')
        mock_dedup.return_value = existing_word  # Found duplicate
        mock_embed.return_value = [0.1] * 768
        job = GenerationJobFactory(input_words=['bright'])

        words_data = [WORD_LOOKUP_RESPONSE['words'][0]]
        words = _step_dedup_and_persist(job, words_data)

        assert len(words) == 1
        assert words[0].id == existing_word.id
        # Should NOT create a new Word
        assert Word.objects.filter(text='bright').count() == 1

    @patch('vocabulary.services.embedding_service.find_duplicate_definition')
    @patch('vocabulary.services.embedding_service.get_embedding')
    def test_adds_words_to_word_set(self, mock_embed, mock_dedup):
        mock_dedup.return_value = None
        mock_embed.return_value = [0.1] * 768
        job = GenerationJobFactory(input_words=['bright'])

        words_data = [WORD_LOOKUP_RESPONSE['words'][0]]
        _step_dedup_and_persist(job, words_data)

        assert job.word_set.words.count() == 1
        assert job.word_set.words.first().text == 'bright'

    @patch('vocabulary.services.embedding_service.find_duplicate_definition')
    @patch('vocabulary.services.embedding_service.get_embedding')
    def test_updates_job_words_created_counter(self, mock_embed, mock_dedup):
        mock_dedup.return_value = None
        mock_embed.return_value = [0.1] * 768
        job = GenerationJobFactory(input_words=['bright', 'discover'])

        _step_dedup_and_persist(job, WORD_LOOKUP_RESPONSE['words'])

        job.refresh_from_db()
        assert job.words_created == 2

    @patch('vocabulary.services.embedding_service.find_duplicate_definition')
    @patch('vocabulary.services.embedding_service.get_embedding')
    def test_creates_dedup_log(self, mock_embed, mock_dedup):
        mock_dedup.return_value = None
        mock_embed.return_value = [0.1] * 768
        job = GenerationJobFactory(input_words=['bright'])

        _step_dedup_and_persist(job, [WORD_LOOKUP_RESPONSE['words'][0]])

        log = GenerationJobLog.objects.get(job=job, step=GenerationJobLog.Step.DEDUP)
        assert log.status == GenerationJob.Status.COMPLETED
        assert log.output_data['word_snapshots'][0]['term'] == 'bright'

    def test_reconstruct_context_uses_dedup_snapshot_definition(self):
        job = GenerationJobFactory(input_words=['bright'])
        word = WordFactory(text='bright', part_of_speech='adjective')
        WordDefinitionFactory(
            word=word,
            definition_text='Stale first definition.',
            example_sentence='A stale example.',
        )
        job.word_set.words.add(word)
        GenerationJobLog.objects.create(
            job=job,
            step=GenerationJobLog.Step.DEDUP,
            status=GenerationJob.Status.COMPLETED,
            output_data={
                'word_snapshots': [
                    {
                        'term': 'bright',
                        'word_id': word.id,
                        'definition_id': 999,
                        'part_of_speech': 'adjective',
                        'definition': 'Exact generated definition.',
                        'example_sentence': 'Exact generated example.',
                        'lexile_score': 600,
                    },
                ],
            },
        )

        _, words_data, _ = _reconstruct_context(job)

        assert words_data == [
            {
                'term': 'bright',
                'part_of_speech': 'adjective',
                'definition': 'Exact generated definition.',
                'example_sentence': 'Exact generated example.',
                'lexile_score': 600,
            },
        ]
