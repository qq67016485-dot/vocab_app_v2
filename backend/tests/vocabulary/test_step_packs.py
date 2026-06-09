"""Tests for pack creation and primer generation steps in the pipeline."""
import pytest
from unittest.mock import patch

from vocabulary.models import (
    WordPack, PrimerCardContent,
    GenerationJob, GenerationJobLog,
)
from vocabulary.services.generation_pipeline_service import (
    _step_auto_create_packs,
    _step_generate_primers,
)
from vocabulary.services.generation.step_packs import _sanitize_syllable_text
from tests.factories import (
    WordFactory, WordDefinitionFactory, GenerationJobFactory,
)
from tests.vocabulary.generation_fixtures import (
    WORD_LOOKUP_RESPONSE, PRIMER_RESPONSE,
)


@pytest.mark.django_db
class TestStepAutoCreatePacks:
    """Tests for _step_auto_create_packs — groups words into packs of ~5."""

    def test_creates_packs_from_words(self):
        job = GenerationJobFactory(input_words=['a', 'b', 'c', 'd', 'e', 'f', 'g'])
        words = [WordFactory(text=w) for w in ['a', 'b', 'c', 'd', 'e', 'f', 'g']]

        packs = _step_auto_create_packs(job, words, allow_fallback=True)

        assert len(packs) == 2  # 7 words / 5 per pack = 2 packs
        assert WordPack.objects.filter(word_set=job.word_set).count() == 2

    def test_creates_pack_items(self):
        job = GenerationJobFactory(input_words=['a', 'b', 'c'])
        words = [WordFactory(text=w) for w in ['a', 'b', 'c']]

        packs = _step_auto_create_packs(job, words, allow_fallback=True)

        total_items = sum(p.items.count() for p in packs)
        assert total_items == 3

    def test_single_pack_for_small_word_list(self):
        job = GenerationJobFactory(input_words=['a', 'b'])
        words = [WordFactory(text=w) for w in ['a', 'b']]

        packs = _step_auto_create_packs(job, words, allow_fallback=True)

        assert len(packs) == 1

    def test_creates_pack_creation_log(self):
        job = GenerationJobFactory(input_words=['a', 'b'])
        words = [WordFactory(text=w) for w in ['a', 'b']]

        _step_auto_create_packs(job, words, allow_fallback=True)

        log = GenerationJobLog.objects.get(job=job, step=GenerationJobLog.Step.PACK_CREATION)
        assert log.status == GenerationJob.Status.COMPLETED

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_llm_grouping_uses_graphic_novel_structured_input(self, mock_load, mock_gemini):
        mock_load.return_value = "Pack template {num_packs} {max_per_pack} {input_json}"
        mock_gemini.return_value = {
            'packs': [
                {
                    'label': 'Signal Mystery',
                    'text_type': 'fiction',
                    'narrative_approach': 'quiet exploration',
                    'graphic_novel_fit': 'The words can become clues and actions.',
                    'words': ['bright', 'discover'],
                },
            ],
        }
        job = GenerationJobFactory(input_words=['bright', 'discover'])
        words = [WordFactory(text='bright'), WordFactory(text='discover')]

        packs = _step_auto_create_packs(job, words, WORD_LOOKUP_RESPONSE['words'])

        assert len(packs) == 1
        assert packs[0].label == 'Signal Mystery'
        assert packs[0].text_type == 'fiction'
        prompt_text = mock_gemini.call_args.args[1]
        assert '5-page ESL graphic novel script generation' in prompt_text
        assert '"grouping_goal"' in prompt_text
        assert '"example_sentence"' in prompt_text

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_llm_grouping_rejects_duplicate_words_and_fails_production_grouping(self, mock_load, mock_gemini):
        mock_load.return_value = "Pack template {num_packs} {max_per_pack} {input_json}"
        mock_gemini.return_value = {
            'packs': [
                {
                    'label': 'Broken Pack',
                    'text_type': 'fiction',
                    'words': ['bright', 'bright'],
                },
            ],
        }
        job = GenerationJobFactory(input_words=['bright', 'discover'])
        words = [WordFactory(text='bright'), WordFactory(text='discover')]

        with pytest.raises(ValueError, match='duplicated words'):
            _step_auto_create_packs(job, words, WORD_LOOKUP_RESPONSE['words'])

        log = GenerationJobLog.objects.get(job=job, step=GenerationJobLog.Step.PACK_CREATION)
        assert log.status == GenerationJob.Status.FAILED
        assert log.output_data['fallback_used'] is False
        assert 'quality_warning' in log.output_data

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_llm_grouping_can_use_explicit_sequential_fallback(self, mock_load, mock_gemini):
        mock_load.return_value = "Pack template {num_packs} {max_per_pack} {input_json}"
        mock_gemini.side_effect = ValueError('pack model unavailable')
        job = GenerationJobFactory(input_words=['bright', 'discover'])
        words = [WordFactory(text='bright'), WordFactory(text='discover')]

        packs = _step_auto_create_packs(
            job,
            words,
            WORD_LOOKUP_RESPONSE['words'],
            allow_fallback=True,
        )

        assert len(packs) == 1
        assert packs[0].label == 'Pack 1'
        assert [item.word.text for item in packs[0].items.order_by('order')] == ['bright', 'discover']
        log = GenerationJobLog.objects.get(job=job, step=GenerationJobLog.Step.PACK_CREATION)
        assert log.output_data['fallback_used'] is True
        assert log.output_data['quality_warning']


@pytest.mark.django_db
class TestStepGeneratePrimers:
    """Tests for _step_generate_primers — LLM generates primer card content per word."""

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_creates_primer_cards(self, mock_load, mock_anthropic):
        mock_load.return_value = "Primer template"
        mock_anthropic.return_value = PRIMER_RESPONSE
        word1 = WordFactory(text='bright')
        word2 = WordFactory(text='discover')
        WordDefinitionFactory(word=word1)
        WordDefinitionFactory(word=word2)
        job = GenerationJobFactory(input_words=['bright', 'discover'])

        _step_generate_primers(job, [word1, word2], WORD_LOOKUP_RESPONSE['words'])

        assert PrimerCardContent.objects.count() == 2
        primer = PrimerCardContent.objects.get(word=word1)
        assert primer.syllable_text == 'bright'
        assert 'shines' in primer.kid_friendly_definition.lower() or primer.kid_friendly_definition != ''

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_updates_primer_cards_created_counter(self, mock_load, mock_anthropic):
        mock_load.return_value = "Primer template"
        mock_anthropic.return_value = PRIMER_RESPONSE
        word = WordFactory(text='bright')
        WordDefinitionFactory(word=word)
        job = GenerationJobFactory(input_words=['bright'])

        _step_generate_primers(job, [word], [WORD_LOOKUP_RESPONSE['words'][0]])

        job.refresh_from_db()
        assert job.primer_cards_created >= 1

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_creates_primer_gen_log(self, mock_load, mock_anthropic):
        mock_load.return_value = "Primer template"
        mock_anthropic.return_value = PRIMER_RESPONSE
        word = WordFactory(text='bright')
        WordDefinitionFactory(word=word)
        job = GenerationJobFactory(input_words=['bright'])

        _step_generate_primers(job, [word], [WORD_LOOKUP_RESPONSE['words'][0]])

        log = GenerationJobLog.objects.get(job=job, step=GenerationJobLog.Step.PRIMER_GEN)
        assert log.status == GenerationJob.Status.COMPLETED

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_misspelled_syllable_text_falls_back_to_plain_term(self, mock_load, mock_gemini):
        """A phonetically respelled syllable breakdown must not reach the card."""
        mock_load.return_value = "Primer template"
        mock_gemini.return_value = {
            'primer_cards': [
                {
                    'term': 'simile',
                    'syllable_text': 'sim·i·lee',  # respelled — drops/changes letters
                    'kid_friendly_definition': 'a comparison using like or as',
                },
            ],
        }
        word = WordFactory(text='simile')
        WordDefinitionFactory(word=word)
        job = GenerationJobFactory(input_words=['simile'])

        _step_generate_primers(job, [word], [{'term': 'simile'}])

        primer = PrimerCardContent.objects.get(word=word)
        assert primer.syllable_text == 'simile'

    @patch('vocabulary.services.llm_service.call_gemini')
    @patch('vocabulary.services.llm_service.load_prompt_template')
    def test_correct_syllable_text_is_preserved(self, mock_load, mock_gemini):
        mock_load.return_value = "Primer template"
        mock_gemini.return_value = {
            'primer_cards': [
                {
                    'term': 'simile',
                    'syllable_text': 'sim·i·le',
                    'kid_friendly_definition': 'a comparison using like or as',
                },
            ],
        }
        word = WordFactory(text='simile')
        WordDefinitionFactory(word=word)
        job = GenerationJobFactory(input_words=['simile'])

        _step_generate_primers(job, [word], [{'term': 'simile'}])

        primer = PrimerCardContent.objects.get(word=word)
        assert primer.syllable_text == 'sim·i·le'


class TestSanitizeSyllableText:
    """Pure unit tests for _sanitize_syllable_text spelling preservation."""

    def test_keeps_breakdown_when_spelling_matches(self):
        assert _sanitize_syllable_text('simile', 'sim·i·le') == 'sim·i·le'

    def test_tolerates_hyphen_separator(self):
        assert _sanitize_syllable_text('discover', 'dis-cov-er') == 'dis-cov-er'

    def test_rejects_phonetic_respelling(self):
        assert _sanitize_syllable_text('simile', 'sim·i·lee') == 'simile'

    def test_rejects_dropped_letters(self):
        assert _sanitize_syllable_text('every', 'ev·ry') == 'every'

    def test_case_insensitive_match(self):
        assert _sanitize_syllable_text('Bright', 'bright') == 'bright'

    def test_empty_breakdown_falls_back_to_term(self):
        assert _sanitize_syllable_text('fume', '') == 'fume'

    def test_single_syllable_no_dots(self):
        assert _sanitize_syllable_text('spray', 'spray') == 'spray'
