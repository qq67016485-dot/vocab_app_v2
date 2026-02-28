import factory
from django.utils import timezone
from datetime import date

from users.models import CustomUser, StudentGroup
from vocabulary.models import (
    Tag, Word, WordDefinition, DefinitionEmbedding, Translation,
    MasteryLevel, UserWordProgress, MasteryLevelLog,
    Question, PracticeSession, UserAnswer,
    Curriculum, Level, WordSet, StudentWordSetAssignment,
    WordPack, WordPackItem, PrimerCardContent, MicroStory,
    ClozeItem, GeneratedImage, StudentPackCompletion,
    GenerationJob, GenerationJobLog,
)


# =============================================================================
# USER FACTORIES
# =============================================================================

class AdminUserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CustomUser

    username = factory.Sequence(lambda n: f'admin_{n}')
    password = 'testpass123'
    role = CustomUser.Role.ADMIN
    native_language = 'zh-CN'

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        password = kwargs.pop('password')
        user = model_class.objects.create_user(*args, **kwargs)
        user.set_password(password)
        user.save(update_fields=['password'])
        return user


class TeacherUserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CustomUser

    username = factory.Sequence(lambda n: f'teacher_{n}')
    password = 'testpass123'
    role = CustomUser.Role.TEACHER
    native_language = 'zh-CN'

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        password = kwargs.pop('password')
        user = model_class.objects.create_user(*args, **kwargs)
        user.set_password(password)
        user.save(update_fields=['password'])
        return user


class StudentUserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CustomUser

    username = factory.Sequence(lambda n: f'student_{n}')
    password = 'testpass123'
    role = CustomUser.Role.STUDENT
    native_language = 'zh-CN'

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        password = kwargs.pop('password')
        user = model_class.objects.create_user(*args, **kwargs)
        user.set_password(password)
        user.save(update_fields=['password'])
        return user


class StudentGroupFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = StudentGroup

    name = factory.Sequence(lambda n: f'Group {n}')
    teacher = factory.SubFactory(TeacherUserFactory)


# =============================================================================
# VOCABULARY FACTORIES
# =============================================================================

class TagFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Tag

    tag_name = factory.Sequence(lambda n: f'tag_{n}')


class WordFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Word

    text = factory.Sequence(lambda n: f'word_{n}')
    part_of_speech = 'noun'
    source_context = 'From test context'


class WordDefinitionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = WordDefinition

    word = factory.SubFactory(WordFactory)
    definition_text = factory.LazyAttribute(lambda obj: f'Definition of {obj.word.text}')
    example_sentence = factory.LazyAttribute(lambda obj: f'{obj.word.text} is used in a sentence.')
    lexile_score = 650


class DefinitionEmbeddingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DefinitionEmbedding

    definition = factory.SubFactory(WordDefinitionFactory)
    embedding = factory.LazyFunction(lambda: [0.1] * 768)
    model_version = 'qwen2.5-embedding-v1'


class MasteryLevelFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = MasteryLevel
        django_get_or_create = ('level_id',)

    level_id = 1
    level_name = 'Introduction'
    interval_days = 0
    points_to_promote = 3


class UserWordProgressFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserWordProgress

    user = factory.SubFactory(StudentUserFactory)
    word = factory.SubFactory(WordFactory)
    level = factory.SubFactory(MasteryLevelFactory)
    mastery_points = 0
    next_review_date = factory.LazyFunction(date.today)


class CurriculumFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Curriculum

    name = factory.Sequence(lambda n: f'Curriculum {n}')


class LevelFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Level

    name = factory.Sequence(lambda n: f'Grade {n}')
    order = factory.Sequence(lambda n: n)


class WordSetFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = WordSet

    title = factory.Sequence(lambda n: f'Word Set {n}')
    creator = factory.SubFactory(TeacherUserFactory)


class WordPackFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = WordPack

    word_set = factory.SubFactory(WordSetFactory)
    label = factory.Sequence(lambda n: f'Pack {n}')
    order = factory.Sequence(lambda n: n)


class WordPackItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = WordPackItem

    pack = factory.SubFactory(WordPackFactory)
    word = factory.SubFactory(WordFactory)
    order = factory.Sequence(lambda n: n)


class PrimerCardContentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PrimerCardContent

    word = factory.SubFactory(WordFactory)
    syllable_text = 'test·word'
    kid_friendly_definition = 'A simple definition for kids.'
    example_sentence = 'Here is an example sentence.'


class MicroStoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = MicroStory

    pack = factory.SubFactory(WordPackFactory)
    story_text = 'Once upon a time, there was a **word**.'
    reading_level = 650


class ClozeItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ClozeItem

    pack = factory.SubFactory(WordPackFactory)
    word = factory.SubFactory(WordFactory)
    sentence_text = 'The _______ was bright.'
    correct_answer = 'sun'
    distractors = ['moon', 'star']


class QuestionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Question

    word = factory.SubFactory(WordFactory)
    question_type = Question.QuestionType.DEFINITION_MC_SINGLE
    question_text = factory.LazyAttribute(lambda obj: f'What does {obj.word.text} mean?')
    correct_answers = ['correct answer']
    options = ['correct answer', 'wrong 1', 'wrong 2', 'wrong 3']


class GenerationJobFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = GenerationJob

    word_set = factory.SubFactory(WordSetFactory)
    created_by = factory.SubFactory(AdminUserFactory)
    input_words = ['apple', 'banana', 'cherry']
    target_lexile = 650
    target_language = 'zh-CN'


class GenerationJobLogFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = GenerationJobLog

    job = factory.SubFactory(GenerationJobFactory)
    step = GenerationJobLog.Step.WORD_LOOKUP
