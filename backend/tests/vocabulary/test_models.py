import pytest
from datetime import date
from django.contrib.contenttypes.models import ContentType

from vocabulary.models import (
    Tag, Word, WordDefinition, DefinitionEmbedding, Translation,
    MasteryLevel, UserWordProgress, MasteryLevelLog,
    Question, PracticeSession, UserAnswer,
    Curriculum, Level, WordSet, StudentWordSetAssignment,
    WordPack, WordPackItem, PrimerCardContent, MicroStory,
    ClozeItem, GeneratedImage, StudentPackCompletion,
    GenerationJob, GenerationJobLog,
)
from tests.factories import (
    TagFactory, WordFactory, WordDefinitionFactory, DefinitionEmbeddingFactory,
    MasteryLevelFactory, UserWordProgressFactory, WordSetFactory,
    WordPackFactory, WordPackItemFactory, PrimerCardContentFactory,
    MicroStoryFactory, ClozeItemFactory, QuestionFactory,
    GenerationJobFactory, GenerationJobLogFactory,
    AdminUserFactory, TeacherUserFactory, StudentUserFactory,
    CurriculumFactory, LevelFactory,
)


# =============================================================================
# CORE VOCABULARY MODELS
# =============================================================================

@pytest.mark.django_db
class TestWord:
    def test_create_word(self):
        word = WordFactory(text='eloquent', part_of_speech='adjective')
        assert word.text == 'eloquent'
        assert word.part_of_speech == 'adjective'

    def test_word_not_unique(self):
        """Same text allowed (homonyms get separate Word records)."""
        w1 = WordFactory(text='bank', part_of_speech='noun')
        w2 = WordFactory(text='bank', part_of_speech='verb')
        assert w1.pk != w2.pk

    def test_str_with_pos(self):
        word = WordFactory(text='run', part_of_speech='verb')
        assert str(word) == 'run (verb)'

    def test_str_without_pos(self):
        word = WordFactory(text='hello', part_of_speech='')
        assert str(word) == 'hello'

    def test_tags_m2m(self):
        word = WordFactory()
        tag1 = TagFactory(tag_name='academic')
        tag2 = TagFactory(tag_name='science')
        word.tags.add(tag1, tag2)
        assert word.tags.count() == 2


@pytest.mark.django_db
class TestWordDefinition:
    def test_create_definition(self):
        defn = WordDefinitionFactory(lexile_score=500)
        assert defn.word is not None
        assert defn.lexile_score == 500

    def test_ordering_by_lexile(self):
        word = WordFactory()
        WordDefinitionFactory(word=word, lexile_score=800)
        WordDefinitionFactory(word=word, lexile_score=400)
        WordDefinitionFactory(word=word, lexile_score=600)
        definitions = list(word.definitions.all())
        scores = [d.lexile_score for d in definitions]
        assert scores == [400, 600, 800]

    def test_str_representation(self):
        word = WordFactory(text='vivid')
        defn = WordDefinitionFactory(
            word=word, definition_text='Producing strong mental images', lexile_score=700,
        )
        assert "vivid" in str(defn)
        assert "700L" in str(defn)


@pytest.mark.django_db
class TestDefinitionEmbedding:
    def test_create_embedding(self):
        emb = DefinitionEmbeddingFactory()
        assert len(emb.embedding) == 768
        assert emb.model_version == 'qwen2.5-embedding-v1'

    def test_one_to_one_constraint(self):
        defn = WordDefinitionFactory()
        DefinitionEmbeddingFactory(definition=defn)
        with pytest.raises(Exception):
            DefinitionEmbeddingFactory(definition=defn)


@pytest.mark.django_db
class TestTranslation:
    def test_create_translation(self):
        defn = WordDefinitionFactory()
        ct = ContentType.objects.get_for_model(WordDefinition)
        translation = Translation.objects.create(
            content_type=ct,
            object_id=defn.pk,
            field_name='definition_text',
            language='zh-CN',
            translated_text='测试翻译',
        )
        assert translation.language == 'zh-CN'
        assert translation.content_object == defn

    def test_unique_constraint(self):
        defn = WordDefinitionFactory()
        ct = ContentType.objects.get_for_model(WordDefinition)
        Translation.objects.create(
            content_type=ct, object_id=defn.pk,
            field_name='definition_text', language='zh-CN',
            translated_text='翻译1',
        )
        with pytest.raises(Exception):
            Translation.objects.create(
                content_type=ct, object_id=defn.pk,
                field_name='definition_text', language='zh-CN',
                translated_text='翻译2',
            )

    def test_multiple_languages(self):
        defn = WordDefinitionFactory()
        ct = ContentType.objects.get_for_model(WordDefinition)
        Translation.objects.create(
            content_type=ct, object_id=defn.pk,
            field_name='definition_text', language='zh-CN',
            translated_text='中文翻译',
        )
        Translation.objects.create(
            content_type=ct, object_id=defn.pk,
            field_name='definition_text', language='ja',
            translated_text='日本語翻訳',
        )
        translations = Translation.objects.filter(
            content_type=ct, object_id=defn.pk,
        )
        assert translations.count() == 2

    def test_multiple_fields(self):
        defn = WordDefinitionFactory()
        ct = ContentType.objects.get_for_model(WordDefinition)
        Translation.objects.create(
            content_type=ct, object_id=defn.pk,
            field_name='definition_text', language='zh-CN',
            translated_text='定义翻译',
        )
        Translation.objects.create(
            content_type=ct, object_id=defn.pk,
            field_name='example_sentence', language='zh-CN',
            translated_text='例句翻译',
        )
        assert Translation.objects.filter(
            content_type=ct, object_id=defn.pk, language='zh-CN',
        ).count() == 2


# =============================================================================
# MASTERY & PROGRESS MODELS
# =============================================================================

@pytest.mark.django_db
class TestMasteryLevel:
    def test_create_and_retrieve_levels(self):
        """Verify mastery levels can be created and retrieved."""
        MasteryLevelFactory(level_id=1, level_name='Introduction', interval_days=0, points_to_promote=3)
        MasteryLevelFactory(level_id=6, level_name='Mastered', interval_days=30, points_to_promote=0)
        assert MasteryLevel.objects.count() == 2
        assert MasteryLevel.objects.get(level_id=1).level_name == 'Introduction'
        assert MasteryLevel.objects.get(level_id=6).level_name == 'Mastered'


@pytest.mark.django_db
class TestUserWordProgress:
    def test_create_progress(self):
        progress = UserWordProgressFactory()
        assert progress.mastery_points == 0
        assert progress.instructional_status == 'READY'

    def test_unique_user_word(self):
        student = StudentUserFactory()
        word = WordFactory()
        level = MasteryLevelFactory(level_id=1)
        UserWordProgress.objects.create(
            user=student, word=word, level=level,
            next_review_date=date.today(),
        )
        with pytest.raises(Exception):
            UserWordProgress.objects.create(
                user=student, word=word, level=level,
                next_review_date=date.today(),
            )


# =============================================================================
# QUESTION & PRACTICE MODELS
# =============================================================================

@pytest.mark.django_db
class TestQuestion:
    def test_create_question(self):
        q = QuestionFactory()
        assert q.question_type == Question.QuestionType.DEFINITION_MC_SINGLE
        assert q.word is not None

    def test_all_20_question_types(self):
        assert len(Question.QuestionType.choices) == 20

    def test_generation_job_nullable(self):
        q = QuestionFactory()
        assert q.generation_job is None

    def test_question_linked_to_job(self):
        job = GenerationJobFactory()
        q = QuestionFactory(generation_job=job)
        assert q.generation_job == job
        assert q in job.generated_questions.all()


# =============================================================================
# CURRICULUM & WORD SET MODELS
# =============================================================================

@pytest.mark.django_db
class TestWordSet:
    def test_create_word_set(self):
        ws = WordSetFactory(title='Test Book')
        assert ws.title == 'Test Book'
        assert ws.source_text == ''

    def test_source_text_field(self):
        ws = WordSetFactory(source_text='A passage from the book...')
        assert ws.source_text == 'A passage from the book...'

    def test_add_words(self):
        ws = WordSetFactory()
        w1 = WordFactory()
        w2 = WordFactory()
        ws.words.add(w1, w2)
        assert ws.words.count() == 2

    def test_str_with_chapter(self):
        teacher = TeacherUserFactory(username='mrs_jones')
        ws = WordSetFactory(title='Cosmos', unit_or_chapter='Ch 1', creator=teacher)
        assert str(ws) == "'Cosmos - Ch 1' by mrs_jones"

    def test_str_without_chapter(self):
        teacher = TeacherUserFactory(username='mrs_jones')
        ws = WordSetFactory(title='Cosmos', unit_or_chapter='', creator=teacher)
        assert str(ws) == "'Cosmos' by mrs_jones"


# =============================================================================
# INSTRUCTIONAL LAYER MODELS
# =============================================================================

@pytest.mark.django_db
class TestInstructionalModels:
    def test_word_pack_ordering(self):
        ws = WordSetFactory()
        WordPackFactory(word_set=ws, label='Pack B', order=2)
        WordPackFactory(word_set=ws, label='Pack A', order=1)
        packs = list(ws.packs.all())
        assert packs[0].label == 'Pack A'
        assert packs[1].label == 'Pack B'

    def test_word_pack_item_unique(self):
        pack = WordPackFactory()
        word = WordFactory()
        WordPackItemFactory(pack=pack, word=word)
        with pytest.raises(Exception):
            WordPackItemFactory(pack=pack, word=word)

    def test_primer_card_one_to_one(self):
        word = WordFactory()
        PrimerCardContentFactory(word=word)
        with pytest.raises(Exception):
            PrimerCardContentFactory(word=word)

    def test_primer_card_no_translation_fields(self):
        """v2 removed definition_translation/example_translation from PrimerCardContent."""
        assert not hasattr(PrimerCardContent, 'definition_translation')
        assert not hasattr(PrimerCardContent, 'example_translation')

    def test_micro_story(self):
        story = MicroStoryFactory(reading_level=500)
        assert '**word**' in story.story_text
        assert story.reading_level == 500

    def test_cloze_item(self):
        cloze = ClozeItemFactory()
        assert '_______' in cloze.sentence_text
        assert len(cloze.distractors) == 2

    def test_generated_image_status(self):
        word = WordFactory()
        img = GeneratedImage.objects.create(
            word=word, image_url='https://example.com/img.png',
            prompt_used='A test prompt',
        )
        assert img.status == GeneratedImage.Status.PENDING_REVIEW

    def test_student_pack_completion(self):
        student = StudentUserFactory()
        pack = WordPackFactory()
        completion = StudentPackCompletion.objects.create(user=student, pack=pack)
        assert completion.completed_at is not None


# =============================================================================
# GENERATION PIPELINE MODELS
# =============================================================================

@pytest.mark.django_db
class TestGenerationJob:
    def test_create_job(self):
        job = GenerationJobFactory()
        assert job.status == GenerationJob.Status.PENDING
        assert job.job_type == GenerationJob.JobType.FULL_PIPELINE
        assert job.input_words == ['apple', 'banana', 'cherry']
        assert job.created_by.role == 'ADMIN'

    def test_output_counters_default_zero(self):
        job = GenerationJobFactory()
        assert job.words_created == 0
        assert job.questions_created == 0
        assert job.primer_cards_created == 0
        assert job.stories_created == 0
        assert job.cloze_items_created == 0
        assert job.images_created == 0

    def test_status_choices(self):
        statuses = [s[0] for s in GenerationJob.Status.choices]
        assert 'PENDING' in statuses
        assert 'RUNNING' in statuses
        assert 'COMPLETED' in statuses
        assert 'FAILED' in statuses
        assert 'PARTIALLY_COMPLETED' in statuses


@pytest.mark.django_db
class TestGenerationJobLog:
    def test_create_log(self):
        log = GenerationJobLogFactory()
        assert log.step == GenerationJobLog.Step.WORD_LOOKUP
        assert log.status == GenerationJob.Status.PENDING

    def test_all_steps(self):
        steps = [s[0] for s in GenerationJobLog.Step.choices]
        assert 'WORD_LOOKUP' in steps
        assert 'DEDUP' in steps
        assert 'TRANSLATION' in steps
        assert 'QUESTION_GEN' in steps
        assert 'PACK_CREATION' in steps
        assert 'PRIMER_GEN' in steps
        assert 'STORY_CLOZE_GEN' in steps
        assert 'IMAGE_GEN' in steps
        assert len(steps) == 8
