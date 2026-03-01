"""
RED tests for v2 serializers.
Tests written BEFORE implementation — all should fail initially.
"""
import pytest
from datetime import date
from rest_framework.test import APIRequestFactory

from users.models import CustomUser
from vocabulary.models import (
    Word, WordDefinition, Question, WordSet, Curriculum, Level,
    MasteryLevel, UserWordProgress,
)
from vocabulary.serializers import (
    UserSerializer,
    WordSerializer,
    WordDetailSerializer,
    QuestionSerializer,
    CurriculumSerializer,
    LevelSerializer,
    WordSetSerializer,
    WordSetDetailSerializer,
    WordSetFormSerializer,
    StudentGroupSerializer,
    StudentGroupFormSerializer,
    RosterDashboardSerializer,
    RosterStudentSerializer,
    TeacherStudentSerializer,
    StudentCreateUpdateSerializer,
)
from tests.factories import (
    AdminUserFactory, TeacherUserFactory, StudentUserFactory,
    WordFactory, WordDefinitionFactory, WordSetFactory,
    CurriculumFactory, LevelFactory, StudentGroupFactory,
    QuestionFactory, MasteryLevelFactory,
)


factory = APIRequestFactory()


def _seed_mastery_levels():
    levels = [
        (1, 'Novice', 0, 2),
        (2, 'Familiar', 1, 4),
    ]
    for lid, name, interval, pts in levels:
        MasteryLevel.objects.get_or_create(
            level_id=lid,
            defaults={'level_name': name, 'interval_days': interval, 'points_to_promote': pts},
        )


# =============================================================================
# USER SERIALIZER
# =============================================================================


@pytest.mark.django_db
class TestUserSerializer:
    def test_serializes_basic_fields(self):
        student = StudentUserFactory()
        serializer = UserSerializer(student)
        data = serializer.data
        assert data['id'] == student.id
        assert data['username'] == student.username
        assert data['role'] == 'STUDENT'
        assert data['level'] == student.level
        assert data['xp_points'] == student.xp_points

    def test_includes_tier_info(self):
        student = StudentUserFactory()
        serializer = UserSerializer(student)
        data = serializer.data
        assert 'tier_info' in data
        assert isinstance(data['tier_info'], dict)

    def test_includes_xp_fields(self):
        student = StudentUserFactory()
        serializer = UserSerializer(student)
        data = serializer.data
        assert 'xp_in_current_level' in data
        assert 'xp_for_next_level' in data

    def test_includes_lexile_range(self):
        student = StudentUserFactory(lexile_min=400, lexile_max=800)
        serializer = UserSerializer(student)
        data = serializer.data
        assert data['lexile_min'] == 400
        assert data['lexile_max'] == 800

    def test_includes_native_language(self):
        student = StudentUserFactory(native_language='ja')
        serializer = UserSerializer(student)
        data = serializer.data
        assert data['native_language'] == 'ja'


# =============================================================================
# WORD SERIALIZER (replaces v1 WordMeaningSerializer)
# =============================================================================


@pytest.mark.django_db
class TestWordSerializer:
    def test_serializes_basic_fields(self):
        word = WordFactory(text='bright', part_of_speech='adjective')
        serializer = WordSerializer(word)
        data = serializer.data
        assert data['id'] == word.id
        assert data['text'] == 'bright'
        assert data['part_of_speech'] == 'adjective'

    def test_includes_definition(self):
        word = WordFactory(text='bright')
        WordDefinitionFactory(word=word, definition_text='Shining with light')
        serializer = WordSerializer(word)
        data = serializer.data
        assert data['definition'] == 'Shining with light'

    def test_definition_selects_by_lexile_for_students(self):
        """Student with Lexile range should get the best-matching definition."""
        student = StudentUserFactory(lexile_min=400, lexile_max=600)
        word = WordFactory(text='bright')
        WordDefinitionFactory(word=word, definition_text='Hard definition', lexile_score=900)
        WordDefinitionFactory(word=word, definition_text='Easy definition', lexile_score=500)

        request = factory.get('/')
        request.user = student
        serializer = WordSerializer(word, context={'request': request})
        data = serializer.data
        assert data['definition'] == 'Easy definition'

    def test_includes_example_sentence(self):
        word = WordFactory(text='bright')
        WordDefinitionFactory(word=word, example_sentence='The bright sun.')
        serializer = WordSerializer(word)
        data = serializer.data
        assert data['example_sentence'] == 'The bright sun.'

    def test_no_definition_returns_fallback(self):
        word = WordFactory(text='orphan')
        serializer = WordSerializer(word)
        data = serializer.data
        assert 'definition' in data


@pytest.mark.django_db
class TestWordDetailSerializer:
    def test_includes_definitions_list(self):
        word = WordFactory(text='bright')
        WordDefinitionFactory(word=word, definition_text='Def 1')
        WordDefinitionFactory(word=word, definition_text='Def 2')
        serializer = WordDetailSerializer(word)
        data = serializer.data
        assert len(data['definitions']) == 2


# =============================================================================
# QUESTION SERIALIZER
# =============================================================================


@pytest.mark.django_db
class TestQuestionSerializer:
    def test_serializes_question_fields(self):
        word = WordFactory(text='bright')
        question = QuestionFactory(
            word=word,
            question_text='What does bright mean?',
            options=['a', 'b', 'c', 'd'],
        )
        serializer = QuestionSerializer(question)
        data = serializer.data
        assert data['id'] == question.id
        assert data['question_text'] == 'What does bright mean?'
        assert data['options'] == ['a', 'b', 'c', 'd']

    def test_includes_word_text(self):
        """v2: term_text comes from word.text (not meaning.term.term_text)."""
        word = WordFactory(text='bright')
        question = QuestionFactory(word=word)
        serializer = QuestionSerializer(question)
        data = serializer.data
        assert data['term_text'] == 'bright'

    def test_excludes_correct_answers(self):
        """Correct answers should not be exposed to students during practice."""
        question = QuestionFactory()
        serializer = QuestionSerializer(question)
        data = serializer.data
        assert 'correct_answers' not in data


# =============================================================================
# WORD SET SERIALIZERS
# =============================================================================


@pytest.mark.django_db
class TestWordSetSerializer:
    def test_serializes_list_fields(self):
        teacher = TeacherUserFactory()
        ws = WordSetFactory(
            title='Unit 1', unit_or_chapter='Chapter 3',
            description='Test', creator=teacher,
        )
        serializer = WordSetSerializer(ws)
        data = serializer.data
        assert data['title'] == 'Unit 1'
        assert data['unit_or_chapter'] == 'Chapter 3'
        assert data['creator_username'] == teacher.username

    def test_includes_word_count(self):
        ws = WordSetFactory()
        ws.words.add(WordFactory(), WordFactory())
        serializer = WordSetSerializer(ws)
        data = serializer.data
        assert data['word_count'] == 2

    def test_includes_curriculum_and_level(self):
        curr = CurriculumFactory(name='Wonders')
        level = LevelFactory(name='Grade 2')
        ws = WordSetFactory(curriculum=curr, level=level)
        serializer = WordSetSerializer(ws)
        data = serializer.data
        assert data['curriculum']['name'] == 'Wonders'
        assert data['level']['name'] == 'Grade 2'


@pytest.mark.django_db
class TestWordSetDetailSerializer:
    def test_includes_words(self):
        ws = WordSetFactory()
        w1 = WordFactory(text='bright')
        w2 = WordFactory(text='dark')
        ws.words.add(w1, w2)
        serializer = WordSetDetailSerializer(ws)
        data = serializer.data
        assert 'words' in data
        texts = {w['text'] for w in data['words']}
        assert texts == {'bright', 'dark'}


@pytest.mark.django_db
class TestWordSetFormSerializer:
    def test_create_with_required_fields(self):
        teacher = TeacherUserFactory()
        request = factory.post('/')
        request.user = teacher
        serializer = WordSetFormSerializer(
            data={'title': 'New Set'},
            context={'request': request},
        )
        assert serializer.is_valid(), serializer.errors

    def test_accepts_curriculum_and_level_ids(self):
        curr = CurriculumFactory()
        level = LevelFactory()
        serializer = WordSetFormSerializer(
            data={
                'title': 'New Set',
                'curriculum_id': curr.id,
                'level_id': level.id,
            },
        )
        assert serializer.is_valid(), serializer.errors


# =============================================================================
# STUDENT GROUP SERIALIZERS
# =============================================================================


@pytest.mark.django_db
class TestStudentGroupSerializer:
    def test_serializes_group(self):
        teacher = TeacherUserFactory()
        group = StudentGroupFactory(teacher=teacher, name='Class A')
        student = StudentUserFactory()
        teacher.students.add(student)
        group.students.add(student)
        serializer = StudentGroupSerializer(group)
        data = serializer.data
        assert data['name'] == 'Class A'
        assert data['teacher_username'] == teacher.username
        assert data['student_count'] == 1
        assert len(data['students']) == 1


@pytest.mark.django_db
class TestStudentGroupFormSerializer:
    def test_validates_students_belong_to_teacher(self):
        teacher = TeacherUserFactory()
        unrelated_student = StudentUserFactory()
        request = factory.post('/')
        request.user = teacher
        serializer = StudentGroupFormSerializer(
            data={'name': 'Class B', 'students': [unrelated_student.id]},
            context={'request': request},
        )
        assert not serializer.is_valid()

    def test_valid_with_assigned_students(self):
        teacher = TeacherUserFactory()
        student = StudentUserFactory()
        teacher.students.add(student)
        request = factory.post('/')
        request.user = teacher
        serializer = StudentGroupFormSerializer(
            data={'name': 'Class B', 'students': [student.id]},
            context={'request': request},
        )
        assert serializer.is_valid(), serializer.errors


# =============================================================================
# TEACHER STUDENT SERIALIZERS
# =============================================================================


@pytest.mark.django_db
class TestTeacherStudentSerializer:
    def test_serializes_student_fields(self):
        student = StudentUserFactory(daily_question_limit=15, lexile_min=300, lexile_max=700)
        serializer = TeacherStudentSerializer(student)
        data = serializer.data
        assert data['username'] == student.username
        assert data['daily_question_limit'] == 15
        assert data['lexile_min'] == 300
        assert data['lexile_max'] == 700


@pytest.mark.django_db
class TestStudentCreateUpdateSerializer:
    def test_creates_student(self):
        serializer = StudentCreateUpdateSerializer(
            data={'username': 'new_student', 'password': 'pass123'},
        )
        assert serializer.is_valid(), serializer.errors
        user = serializer.save()
        assert user.role == 'STUDENT'
        assert user.check_password('pass123')

    def test_validates_lexile_range(self):
        serializer = StudentCreateUpdateSerializer(
            data={
                'username': 'test',
                'password': 'pass123',
                'lexile_min': 800,
                'lexile_max': 400,
            },
        )
        assert not serializer.is_valid()

    def test_updates_without_password(self):
        student = StudentUserFactory()
        old_pw_hash = student.password
        serializer = StudentCreateUpdateSerializer(
            student, data={'daily_question_limit': 30}, partial=True,
        )
        assert serializer.is_valid(), serializer.errors
        updated = serializer.save()
        assert updated.daily_question_limit == 30
        assert updated.password == old_pw_hash  # password unchanged

    def test_updates_password(self):
        student = StudentUserFactory()
        serializer = StudentCreateUpdateSerializer(
            student, data={'password': 'newpass456'}, partial=True,
        )
        assert serializer.is_valid(), serializer.errors
        updated = serializer.save()
        assert updated.check_password('newpass456')


# =============================================================================
# ROSTER SERIALIZERS
# =============================================================================


@pytest.mark.django_db
class TestRosterStudentSerializer:
    def test_includes_activity_and_snapshot(self):
        student = StudentUserFactory()
        student.activity_3d = {'questions_answered': 10, 'accuracy_percent': 85}
        student.snapshot = {
            'challenging_words': ['bright'],
            'skills_to_develop': ['definition_recall'],
            'words_due_for_review': 5,
        }
        serializer = RosterStudentSerializer(student)
        data = serializer.data
        assert data['activity_3d']['questions_answered'] == 10
        assert data['snapshot']['words_due_for_review'] == 5
