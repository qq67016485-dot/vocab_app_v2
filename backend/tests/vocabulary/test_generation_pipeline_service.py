"""
RED tests for generation_pipeline_service.py.

Tests the full pipeline orchestrator: run_full_pipeline and each individual step.
All external calls (LLM, embedding API, image API) are mocked.
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import date

from django.utils import timezone
from django.contrib.contenttypes.models import ContentType

from vocabulary.models import (
    Word, WordDefinition, DefinitionEmbedding, Translation,
    Question, WordPack, WordPackItem, PrimerCardContent,
    MicroStory, ClozeItem, GeneratedImage,
    GenerationJob, GenerationJobLog,
)
from vocabulary.services.generation_pipeline_service import (
    run_full_pipeline,
    _step_word_lookup,
    _step_dedup_and_persist,
    _step_generate_translations,
    _step_generate_questions,
    _step_auto_create_packs,
    _step_generate_primers,
    _step_generate_stories_and_cloze,
    _step_generate_images,
)
from tests.factories import (
    AdminUserFactory, WordFactory, WordDefinitionFactory,
    WordSetFactory, GenerationJobFactory, MasteryLevelFactory,
    DefinitionEmbeddingFactory,
)


# Sample LLM response data used across tests
WORD_LOOKUP_RESPONSE = {
    "words": [
        {
            "term": "bright",
            "part_of_speech": "adjective",
            "definition": "Giving out or reflecting a lot of light; shining.",
            "example_sentence": "The bright stars lit up the night sky.",
            "lexile_score": 600,
            "source_context": "From test book",
        },
        {
            "term": "discover",
            "part_of_speech": "verb",
            "definition": "To find something for the first time.",
            "example_sentence": "She wanted to discover new places.",
            "lexile_score": 650,
            "source_context": "From test book",
        },
    ]
}

TRANSLATION_RESPONSE = {
    "translations": [
        {
            "source_field": "definition_text",
            "source_text": "Giving out or reflecting a lot of light; shining.",
            "translated_text": "发出或反射大量光线；闪耀的。",
        },
        {
            "source_field": "example_sentence",
            "source_text": "The bright stars lit up the night sky.",
            "translated_text": "明亮的星星照亮了夜空。",
        },
        {
            "source_field": "definition_text",
            "source_text": "To find something for the first time.",
            "translated_text": "第一次发现某物。",
        },
        {
            "source_field": "example_sentence",
            "source_text": "She wanted to discover new places.",
            "translated_text": "她想发现新的地方。",
        },
    ]
}

QUESTION_RESPONSE = {
    "questions": [
        {
            "term": "bright",
            "question_type": "DEFINITION_MC_SINGLE",
            "question_text": "What does 'bright' mean?",
            "options": ["Shining", "Dark", "Quiet", "Slow"],
            "correct_answers": ["Shining"],
            "explanation": "Bright means giving out light.",
            "example_sentence": "The sun is very bright today.",
            "lexile_score": 600,
        },
    ]
}

PRIMER_RESPONSE = {
    "primer_cards": [
        {
            "term": "bright",
            "syllable_text": "bright",
            "kid_friendly_definition": "Something that shines a lot.",
            "example_sentence": "The bright sun makes me happy!",
        },
        {
            "term": "discover",
            "syllable_text": "dis·cov·er",
            "kid_friendly_definition": "To find something new.",
            "example_sentence": "I want to discover what is inside the box.",
        },
    ]
}

STORY_CLOZE_RESPONSE = {
    "micro_story": {
        "story_text": "The **bright** sun rose over the hills. Maya wanted to **discover** what was in the cave.",
        "reading_level": 650,
    },
    "cloze_items": [
        {
            "term": "bright",
            "sentence_text": "The _______ light woke me up early.",
            "correct_answer": "bright",
            "distractors": ["dark", "quiet"],
        },
        {
            "term": "discover",
            "sentence_text": "Scientists _______ new species every year.",
            "correct_answer": "discover",
            "distractors": ["ignore", "forget"],
        },
    ],
}


@pytest.mark.django_db
class TestStepWordLookup:
    """Tests for _step_word_lookup — calls LLM to look up word definitions."""

    @patch('vocabulary.services.generation_pipeline_service.call_anthropic')
    @patch('vocabulary.services.generation_pipeline_service.load_prompt_template')
    def test_returns_words_data(self, mock_load, mock_anthropic):
        mock_load.return_value = "System prompt template with {words}"
        mock_anthropic.return_value = WORD_LOOKUP_RESPONSE
        job = GenerationJobFactory(input_words=['bright', 'discover'])

        result = _step_word_lookup(job)

        assert len(result) == 2
        assert result[0]['term'] == 'bright'
        assert result[1]['term'] == 'discover'

    @patch('vocabulary.services.generation_pipeline_service.call_anthropic')
    @patch('vocabulary.services.generation_pipeline_service.load_prompt_template')
    def test_creates_job_log(self, mock_load, mock_anthropic):
        mock_load.return_value = "System prompt"
        mock_anthropic.return_value = WORD_LOOKUP_RESPONSE
        job = GenerationJobFactory(input_words=['bright', 'discover'])

        _step_word_lookup(job)

        log = GenerationJobLog.objects.get(job=job, step=GenerationJobLog.Step.WORD_LOOKUP)
        assert log.status == GenerationJob.Status.COMPLETED
        assert log.duration_seconds is not None
        assert log.output_data is not None

    @patch('vocabulary.services.generation_pipeline_service.call_anthropic')
    @patch('vocabulary.services.generation_pipeline_service.load_prompt_template')
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

    @patch('vocabulary.services.generation_pipeline_service.find_duplicate_definition')
    @patch('vocabulary.services.generation_pipeline_service.get_embedding')
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

    @patch('vocabulary.services.generation_pipeline_service.find_duplicate_definition')
    @patch('vocabulary.services.generation_pipeline_service.get_embedding')
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

    @patch('vocabulary.services.generation_pipeline_service.find_duplicate_definition')
    @patch('vocabulary.services.generation_pipeline_service.get_embedding')
    def test_adds_words_to_word_set(self, mock_embed, mock_dedup):
        mock_dedup.return_value = None
        mock_embed.return_value = [0.1] * 768
        job = GenerationJobFactory(input_words=['bright'])

        words_data = [WORD_LOOKUP_RESPONSE['words'][0]]
        _step_dedup_and_persist(job, words_data)

        assert job.word_set.words.count() == 1
        assert job.word_set.words.first().text == 'bright'

    @patch('vocabulary.services.generation_pipeline_service.find_duplicate_definition')
    @patch('vocabulary.services.generation_pipeline_service.get_embedding')
    def test_updates_job_words_created_counter(self, mock_embed, mock_dedup):
        mock_dedup.return_value = None
        mock_embed.return_value = [0.1] * 768
        job = GenerationJobFactory(input_words=['bright', 'discover'])

        _step_dedup_and_persist(job, WORD_LOOKUP_RESPONSE['words'])

        job.refresh_from_db()
        assert job.words_created == 2

    @patch('vocabulary.services.generation_pipeline_service.find_duplicate_definition')
    @patch('vocabulary.services.generation_pipeline_service.get_embedding')
    def test_creates_dedup_log(self, mock_embed, mock_dedup):
        mock_dedup.return_value = None
        mock_embed.return_value = [0.1] * 768
        job = GenerationJobFactory(input_words=['bright'])

        _step_dedup_and_persist(job, [WORD_LOOKUP_RESPONSE['words'][0]])

        log = GenerationJobLog.objects.get(job=job, step=GenerationJobLog.Step.DEDUP)
        assert log.status == GenerationJob.Status.COMPLETED


@pytest.mark.django_db
class TestStepGenerateTranslations:
    """Tests for _step_generate_translations — LLM translates definitions + examples."""

    @patch('vocabulary.services.generation_pipeline_service.call_anthropic')
    @patch('vocabulary.services.generation_pipeline_service.load_prompt_template')
    def test_creates_translation_records(self, mock_load, mock_anthropic):
        mock_load.return_value = "Translate {items_to_translate} into {target_language}"
        mock_anthropic.return_value = TRANSLATION_RESPONSE
        word1 = WordFactory(text='bright')
        # Use definition/example texts that match the TRANSLATION_RESPONSE source_text values
        defn1 = WordDefinitionFactory(
            word=word1,
            definition_text='Giving out or reflecting a lot of light; shining.',
            example_sentence='The bright stars lit up the night sky.',
        )
        word2 = WordFactory(text='discover')
        defn2 = WordDefinitionFactory(
            word=word2,
            definition_text='To find something for the first time.',
            example_sentence='She wanted to discover new places.',
        )
        job = GenerationJobFactory(input_words=['bright', 'discover'], target_language='zh-CN')

        _step_generate_translations(job, [word1, word2], WORD_LOOKUP_RESPONSE['words'])

        assert Translation.objects.count() == 4  # 2 words x 2 fields (definition + example)

    @patch('vocabulary.services.generation_pipeline_service.call_anthropic')
    @patch('vocabulary.services.generation_pipeline_service.load_prompt_template')
    def test_creates_translation_log(self, mock_load, mock_anthropic):
        mock_load.return_value = "Translate template"
        mock_anthropic.return_value = TRANSLATION_RESPONSE
        word1 = WordFactory(text='bright')
        WordDefinitionFactory(word=word1)
        job = GenerationJobFactory(input_words=['bright'], target_language='zh-CN')

        _step_generate_translations(job, [word1], [WORD_LOOKUP_RESPONSE['words'][0]])

        log = GenerationJobLog.objects.get(job=job, step=GenerationJobLog.Step.TRANSLATION)
        assert log.status == GenerationJob.Status.COMPLETED


@pytest.mark.django_db
class TestStepGenerateQuestions:
    """Tests for _step_generate_questions — LLM generates practice questions per word."""

    @patch('vocabulary.services.generation_pipeline_service.call_anthropic')
    @patch('vocabulary.services.generation_pipeline_service.load_prompt_template')
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

    @patch('vocabulary.services.generation_pipeline_service.call_anthropic')
    @patch('vocabulary.services.generation_pipeline_service.load_prompt_template')
    def test_updates_questions_created_counter(self, mock_load, mock_anthropic):
        mock_load.return_value = "Question gen template"
        mock_anthropic.return_value = QUESTION_RESPONSE
        word = WordFactory(text='bright')
        WordDefinitionFactory(word=word)
        job = GenerationJobFactory(input_words=['bright'])

        _step_generate_questions(job, [word], WORD_LOOKUP_RESPONSE['words'])

        job.refresh_from_db()
        assert job.questions_created >= 1

    @patch('vocabulary.services.generation_pipeline_service.call_anthropic')
    @patch('vocabulary.services.generation_pipeline_service.load_prompt_template')
    def test_creates_question_gen_log(self, mock_load, mock_anthropic):
        mock_load.return_value = "Question gen template"
        mock_anthropic.return_value = QUESTION_RESPONSE
        word = WordFactory(text='bright')
        WordDefinitionFactory(word=word)
        job = GenerationJobFactory(input_words=['bright'])

        _step_generate_questions(job, [word], WORD_LOOKUP_RESPONSE['words'])

        log = GenerationJobLog.objects.get(job=job, step=GenerationJobLog.Step.QUESTION_GEN)
        assert log.status == GenerationJob.Status.COMPLETED


@pytest.mark.django_db
class TestStepAutoCreatePacks:
    """Tests for _step_auto_create_packs — groups words into packs of ~5."""

    def test_creates_packs_from_words(self):
        job = GenerationJobFactory(input_words=['a', 'b', 'c', 'd', 'e', 'f', 'g'])
        words = [WordFactory(text=w) for w in ['a', 'b', 'c', 'd', 'e', 'f', 'g']]

        packs = _step_auto_create_packs(job, words)

        assert len(packs) == 2  # 7 words / 5 per pack = 2 packs
        assert WordPack.objects.filter(word_set=job.word_set).count() == 2

    def test_creates_pack_items(self):
        job = GenerationJobFactory(input_words=['a', 'b', 'c'])
        words = [WordFactory(text=w) for w in ['a', 'b', 'c']]

        packs = _step_auto_create_packs(job, words)

        total_items = sum(p.items.count() for p in packs)
        assert total_items == 3

    def test_single_pack_for_small_word_list(self):
        job = GenerationJobFactory(input_words=['a', 'b'])
        words = [WordFactory(text=w) for w in ['a', 'b']]

        packs = _step_auto_create_packs(job, words)

        assert len(packs) == 1

    def test_creates_pack_creation_log(self):
        job = GenerationJobFactory(input_words=['a', 'b'])
        words = [WordFactory(text=w) for w in ['a', 'b']]

        _step_auto_create_packs(job, words)

        log = GenerationJobLog.objects.get(job=job, step=GenerationJobLog.Step.PACK_CREATION)
        assert log.status == GenerationJob.Status.COMPLETED


@pytest.mark.django_db
class TestStepGeneratePrimers:
    """Tests for _step_generate_primers — LLM generates primer card content per word."""

    @patch('vocabulary.services.generation_pipeline_service.call_anthropic')
    @patch('vocabulary.services.generation_pipeline_service.load_prompt_template')
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

    @patch('vocabulary.services.generation_pipeline_service.call_anthropic')
    @patch('vocabulary.services.generation_pipeline_service.load_prompt_template')
    def test_updates_primer_cards_created_counter(self, mock_load, mock_anthropic):
        mock_load.return_value = "Primer template"
        mock_anthropic.return_value = PRIMER_RESPONSE
        word = WordFactory(text='bright')
        WordDefinitionFactory(word=word)
        job = GenerationJobFactory(input_words=['bright'])

        _step_generate_primers(job, [word], [WORD_LOOKUP_RESPONSE['words'][0]])

        job.refresh_from_db()
        assert job.primer_cards_created >= 1

    @patch('vocabulary.services.generation_pipeline_service.call_anthropic')
    @patch('vocabulary.services.generation_pipeline_service.load_prompt_template')
    def test_creates_primer_gen_log(self, mock_load, mock_anthropic):
        mock_load.return_value = "Primer template"
        mock_anthropic.return_value = PRIMER_RESPONSE
        word = WordFactory(text='bright')
        WordDefinitionFactory(word=word)
        job = GenerationJobFactory(input_words=['bright'])

        _step_generate_primers(job, [word], [WORD_LOOKUP_RESPONSE['words'][0]])

        log = GenerationJobLog.objects.get(job=job, step=GenerationJobLog.Step.PRIMER_GEN)
        assert log.status == GenerationJob.Status.COMPLETED


@pytest.mark.django_db
class TestStepGenerateStoriesAndCloze:
    """Tests for _step_generate_stories_and_cloze — LLM generates per-pack stories + cloze items."""

    @patch('vocabulary.services.generation_pipeline_service.call_anthropic')
    @patch('vocabulary.services.generation_pipeline_service.load_prompt_template')
    def test_creates_story_and_cloze_items(self, mock_load, mock_anthropic):
        mock_load.return_value = "Story template"
        mock_anthropic.return_value = STORY_CLOZE_RESPONSE
        job = GenerationJobFactory(input_words=['bright', 'discover'])
        word1 = WordFactory(text='bright')
        word2 = WordFactory(text='discover')
        pack = WordPack.objects.create(word_set=job.word_set, label='Pack 1', order=0)
        WordPackItem.objects.create(pack=pack, word=word1, order=0)
        WordPackItem.objects.create(pack=pack, word=word2, order=1)

        _step_generate_stories_and_cloze(job, [pack], WORD_LOOKUP_RESPONSE['words'])

        assert MicroStory.objects.filter(pack=pack).count() == 1
        assert ClozeItem.objects.filter(pack=pack).count() == 2

    @patch('vocabulary.services.generation_pipeline_service.call_anthropic')
    @patch('vocabulary.services.generation_pipeline_service.load_prompt_template')
    def test_updates_counters(self, mock_load, mock_anthropic):
        mock_load.return_value = "Story template"
        mock_anthropic.return_value = STORY_CLOZE_RESPONSE
        job = GenerationJobFactory(input_words=['bright', 'discover'])
        word1 = WordFactory(text='bright')
        word2 = WordFactory(text='discover')
        pack = WordPack.objects.create(word_set=job.word_set, label='Pack 1', order=0)
        WordPackItem.objects.create(pack=pack, word=word1, order=0)
        WordPackItem.objects.create(pack=pack, word=word2, order=1)

        _step_generate_stories_and_cloze(job, [pack], WORD_LOOKUP_RESPONSE['words'])

        job.refresh_from_db()
        assert job.stories_created == 1
        assert job.cloze_items_created == 2

    @patch('vocabulary.services.generation_pipeline_service.call_anthropic')
    @patch('vocabulary.services.generation_pipeline_service.load_prompt_template')
    def test_creates_story_cloze_log(self, mock_load, mock_anthropic):
        mock_load.return_value = "Story template"
        mock_anthropic.return_value = STORY_CLOZE_RESPONSE
        job = GenerationJobFactory(input_words=['bright'])
        word = WordFactory(text='bright')
        pack = WordPack.objects.create(word_set=job.word_set, label='Pack 1', order=0)
        WordPackItem.objects.create(pack=pack, word=word, order=0)

        _step_generate_stories_and_cloze(job, [pack], [WORD_LOOKUP_RESPONSE['words'][0]])

        log = GenerationJobLog.objects.get(job=job, step=GenerationJobLog.Step.STORY_CLOZE_GEN)
        assert log.status == GenerationJob.Status.COMPLETED


@pytest.mark.django_db
class TestStepGenerateImages:
    """Tests for _step_generate_images — Gemini generates images per word."""

    @patch('vocabulary.services.generation_pipeline_service.call_gemini_image')
    def test_creates_generated_image_records(self, mock_gemini):
        mock_gemini.return_value = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        word = WordFactory(text='bright')
        WordDefinitionFactory(word=word)
        job = GenerationJobFactory(input_words=['bright'])

        _step_generate_images(job, [word])

        assert GeneratedImage.objects.filter(word=word).count() == 1
        img = GeneratedImage.objects.get(word=word)
        assert img.status == GeneratedImage.Status.PENDING_REVIEW

    @patch('vocabulary.services.generation_pipeline_service.call_gemini_image')
    def test_updates_images_created_counter(self, mock_gemini):
        mock_gemini.return_value = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        word = WordFactory(text='bright')
        WordDefinitionFactory(word=word)
        job = GenerationJobFactory(input_words=['bright'])

        _step_generate_images(job, [word])

        job.refresh_from_db()
        assert job.images_created == 1

    @patch('vocabulary.services.generation_pipeline_service.call_gemini_image')
    def test_creates_image_gen_log(self, mock_gemini):
        mock_gemini.return_value = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        word = WordFactory(text='bright')
        WordDefinitionFactory(word=word)
        job = GenerationJobFactory(input_words=['bright'])

        _step_generate_images(job, [word])

        log = GenerationJobLog.objects.get(job=job, step=GenerationJobLog.Step.IMAGE_GEN)
        assert log.status == GenerationJob.Status.COMPLETED

    @patch('vocabulary.services.generation_pipeline_service.call_gemini_image')
    def test_continues_on_single_image_failure(self, mock_gemini):
        """If one image fails, others should still be generated."""
        mock_gemini.side_effect = [Exception("API error"), b'\x89PNG\r\n\x1a\n' + b'\x00' * 100]
        word1 = WordFactory(text='bright')
        word2 = WordFactory(text='discover')
        WordDefinitionFactory(word=word1)
        WordDefinitionFactory(word=word2)
        job = GenerationJobFactory(input_words=['bright', 'discover'])

        _step_generate_images(job, [word1, word2])

        assert GeneratedImage.objects.count() == 1  # Only word2 succeeded
        job.refresh_from_db()
        assert job.images_created == 1


@pytest.mark.django_db
class TestRunFullPipeline:
    """Tests for run_full_pipeline — the main orchestrator."""

    @patch('vocabulary.services.generation_pipeline_service._step_generate_images')
    @patch('vocabulary.services.generation_pipeline_service._step_generate_stories_and_cloze')
    @patch('vocabulary.services.generation_pipeline_service._step_generate_primers')
    @patch('vocabulary.services.generation_pipeline_service._step_auto_create_packs')
    @patch('vocabulary.services.generation_pipeline_service._step_generate_questions')
    @patch('vocabulary.services.generation_pipeline_service._step_generate_translations')
    @patch('vocabulary.services.generation_pipeline_service._step_dedup_and_persist')
    @patch('vocabulary.services.generation_pipeline_service._step_word_lookup')
    def test_runs_all_steps_in_order(
        self, mock_lookup, mock_dedup, mock_translate, mock_questions,
        mock_packs, mock_primers, mock_stories, mock_images,
    ):
        word = WordFactory(text='bright')
        mock_lookup.return_value = WORD_LOOKUP_RESPONSE['words']
        mock_dedup.return_value = [word]
        mock_packs.return_value = [MagicMock()]
        job = GenerationJobFactory(input_words=['bright'])

        run_full_pipeline(job.id)

        mock_lookup.assert_called_once()
        mock_dedup.assert_called_once()
        mock_translate.assert_called_once()
        mock_questions.assert_called_once()
        mock_packs.assert_called_once()
        mock_primers.assert_called_once()
        mock_stories.assert_called_once()
        mock_images.assert_called_once()

    @patch('vocabulary.services.generation_pipeline_service._step_generate_images')
    @patch('vocabulary.services.generation_pipeline_service._step_generate_stories_and_cloze')
    @patch('vocabulary.services.generation_pipeline_service._step_generate_primers')
    @patch('vocabulary.services.generation_pipeline_service._step_auto_create_packs')
    @patch('vocabulary.services.generation_pipeline_service._step_generate_questions')
    @patch('vocabulary.services.generation_pipeline_service._step_generate_translations')
    @patch('vocabulary.services.generation_pipeline_service._step_dedup_and_persist')
    @patch('vocabulary.services.generation_pipeline_service._step_word_lookup')
    def test_sets_job_status_to_running_then_completed(
        self, mock_lookup, mock_dedup, mock_translate, mock_questions,
        mock_packs, mock_primers, mock_stories, mock_images,
    ):
        mock_lookup.return_value = []
        mock_dedup.return_value = []
        mock_packs.return_value = []
        job = GenerationJobFactory(input_words=['bright'])

        run_full_pipeline(job.id)

        job.refresh_from_db()
        assert job.status == GenerationJob.Status.COMPLETED
        assert job.completed_at is not None

    @patch('vocabulary.services.generation_pipeline_service._step_word_lookup')
    def test_sets_job_status_to_failed_on_error(self, mock_lookup):
        mock_lookup.side_effect = Exception("LLM is down")
        job = GenerationJobFactory(input_words=['bright'])

        run_full_pipeline(job.id)

        job.refresh_from_db()
        assert job.status == GenerationJob.Status.FAILED
        assert 'LLM is down' in job.error_message

    @patch('vocabulary.services.generation_pipeline_service._step_generate_images')
    @patch('vocabulary.services.generation_pipeline_service._step_generate_stories_and_cloze')
    @patch('vocabulary.services.generation_pipeline_service._step_generate_primers')
    @patch('vocabulary.services.generation_pipeline_service._step_auto_create_packs')
    @patch('vocabulary.services.generation_pipeline_service._step_generate_questions')
    @patch('vocabulary.services.generation_pipeline_service._step_generate_translations')
    @patch('vocabulary.services.generation_pipeline_service._step_dedup_and_persist')
    @patch('vocabulary.services.generation_pipeline_service._step_word_lookup')
    def test_passes_words_data_between_steps(
        self, mock_lookup, mock_dedup, mock_translate, mock_questions,
        mock_packs, mock_primers, mock_stories, mock_images,
    ):
        words_data = WORD_LOOKUP_RESPONSE['words']
        word_objs = [WordFactory(text='bright'), WordFactory(text='discover')]
        packs = [MagicMock()]

        mock_lookup.return_value = words_data
        mock_dedup.return_value = word_objs
        mock_packs.return_value = packs

        job = GenerationJobFactory(input_words=['bright', 'discover'])
        run_full_pipeline(job.id)

        # Verify data flows correctly between steps
        mock_dedup.assert_called_once_with(job, words_data)
        mock_translate.assert_called_once_with(job, word_objs, words_data)
        mock_questions.assert_called_once_with(job, word_objs, words_data)
        mock_packs.assert_called_once_with(job, word_objs)
        mock_primers.assert_called_once_with(job, word_objs, words_data)
        mock_stories.assert_called_once_with(job, packs, words_data)
        mock_images.assert_called_once_with(job, word_objs)
