"""
RED tests for v2 API views.
Tests written BEFORE implementation — all should fail initially.
"""
import pytest
from datetime import datetime, time, timedelta
from unittest.mock import patch
from django.core.files.base import ContentFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from users.models import CustomUser, StudentGroup
from vocabulary.models import (
    Word, WordDefinition, Question, WordSet, MasteryLevel,
    UserWordProgress, UserAnswer, MasteryLevelLog, WordPack, WordPackItem,
    PrimerCardContent, MicroStory, GraphicNovel, GraphicNovelPage, ClozeItem,
    StudentWordSetAssignment, StudentPackCompletion,
    GenerationJob, GenerationJobLog, Curriculum, Level,
)
from tests.factories import (
    AdminUserFactory, TeacherUserFactory, StudentUserFactory,
    WordFactory, WordDefinitionFactory, WordSetFactory,
    QuestionFactory, MasteryLevelFactory, WordPackFactory,
    WordPackItemFactory, PrimerCardContentFactory, MicroStoryFactory,
    ClozeItemFactory, StudentGroupFactory, CurriculumFactory, LevelFactory,
    GenerationJobFactory, GraphicNovelFactory,
)


def _later_today():
    return timezone.make_aware(
        datetime.combine(timezone.localdate(), time(23, 59)),
        timezone.get_current_timezone(),
    )


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
    for lid, name, interval, pts, is_hidden in levels:
        MasteryLevel.objects.update_or_create(
            level_id=lid,
            defaults={
                'level_name': name,
                'interval_days': interval,
                'points_to_promote': pts,
                'is_hidden': is_hidden,
            },
        )


def _make_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


# =============================================================================
# AUTH VIEWS
# =============================================================================


@pytest.mark.django_db
class TestAuthViews:
    def test_csrf_cookie_set(self):
        client = APIClient()
        response = client.get('/api/csrf/')
        assert response.status_code == 200

    def test_login_success(self):
        student = StudentUserFactory()
        client = APIClient()
        response = client.post('/api/login/', {
            'username': student.username,
            'password': 'testpass123',
        })
        assert response.status_code == 200
        assert response.data['username'] == student.username
        assert response.data['role'] == 'STUDENT'

    def test_login_invalid_credentials(self):
        client = APIClient()
        response = client.post('/api/login/', {
            'username': 'nobody',
            'password': 'wrong',
        })
        assert response.status_code == 401

    def test_logout_success(self):
        student = StudentUserFactory()
        client = _make_client(student)
        response = client.post('/api/logout/')
        assert response.status_code == 200

    def test_user_detail(self):
        student = StudentUserFactory()
        client = _make_client(student)
        response = client.get('/api/user/')
        assert response.status_code == 200
        assert response.data['username'] == student.username

    def test_user_detail_requires_auth(self):
        client = APIClient()
        response = client.get('/api/user/')
        assert response.status_code == 403


# =============================================================================
# PRACTICE VIEWS
# =============================================================================


@pytest.mark.django_db
class TestNextPracticeWordView:
    @pytest.fixture(autouse=True)
    def setup(self):
        _seed_mastery_levels()
        self.student = StudentUserFactory()
        self.client = _make_client(self.student)
        self.word = WordFactory(text='bright')
        WordDefinitionFactory(word=self.word)
        self.question = QuestionFactory(
            word=self.word,
            correct_answers=['shining'],
            lexile_score=650,
        )
        level1 = MasteryLevel.objects.get(level_id=1)
        self.question.suitable_levels.add(level1)
        UserWordProgress.objects.create(
            user=self.student, word=self.word,
            level=level1, next_review_at=timezone.now(),
        )

    def test_returns_question(self):
        response = self.client.get('/api/practice/next/')
        assert response.status_code == 200
        assert 'question_text' in response.data
        assert response.data['term_text'] == 'bright'

    def test_returns_question_due_later_today(self):
        progress = UserWordProgress.objects.get(user=self.student, word=self.word)
        progress.next_review_at = _later_today()
        progress.save()

        response = self.client.get('/api/practice/next/')

        assert response.status_code == 200
        assert response.data['term_text'] == 'bright'

    def test_returns_reason_category(self):
        response = self.client.get('/api/practice/next/')
        assert response.status_code == 200
        assert 'reason_category' in response.data

    def test_respects_daily_limit(self):
        self.student.daily_question_limit = 1
        self.student.save()
        # Create one answer for today
        UserAnswer.objects.create(
            user=self.student, question=self.question,
            user_answer='test', is_correct=True,
        )
        response = self.client.get('/api/practice/next/')
        assert response.status_code == 200
        assert 'message' in response.data

    def test_no_due_words_message(self):
        # Move review date to future
        progress = UserWordProgress.objects.get(user=self.student, word=self.word)
        progress.next_review_at = timezone.now() + timedelta(days=7)
        progress.save()
        response = self.client.get('/api/practice/next/')
        assert response.status_code == 200
        assert 'message' in response.data

    def test_excludes_pending_instructional_status(self):
        """Words with PENDING status should not appear for practice."""
        progress = UserWordProgress.objects.get(user=self.student, word=self.word)
        progress.instructional_status = 'PENDING'
        progress.save()
        response = self.client.get('/api/practice/next/')
        assert response.status_code == 200
        assert 'message' in response.data

    def test_hidden_mastery_level_uses_questions_from_any_suitable_level(self):
        progress = UserWordProgress.objects.get(user=self.student, word=self.word)
        progress.delete()

        hidden_level = MasteryLevel.objects.get(level_id=6)
        level1 = MasteryLevel.objects.get(level_id=1)
        hidden_word = WordFactory(text='settled')
        question = QuestionFactory(
            word=hidden_word,
            question_text='What does settled mean?',
            correct_answers=['stable'],
            lexile_score=650,
        )
        question.suitable_levels.add(level1)
        UserWordProgress.objects.create(
            user=self.student,
            word=hidden_word,
            level=hidden_level,
            next_review_at=timezone.now(),
        )

        response = self.client.get('/api/practice/next/')

        assert response.status_code == 200
        assert response.data['term_text'] == 'settled'
        assert response.data['question_text'] == 'What does settled mean?'


@pytest.mark.django_db
class TestSubmitAnswerView:
    @pytest.fixture(autouse=True)
    def setup(self):
        _seed_mastery_levels()
        self.student = StudentUserFactory()
        self.client = _make_client(self.student)
        self.word = WordFactory(text='bright')
        self.question = QuestionFactory(
            word=self.word, correct_answers=['shining'],
        )
        level1 = MasteryLevel.objects.get(level_id=1)
        UserWordProgress.objects.create(
            user=self.student, word=self.word,
            level=level1, next_review_at=timezone.now(),
        )

    def test_correct_answer(self):
        response = self.client.post('/api/practice/submit/', {
            'question_id': self.question.id,
            'user_answer': 'shining',
            'duration_seconds': 5,
            'answer_switches': 0,
        })
        assert response.status_code == 200
        assert response.data['is_correct'] is True

    def test_incorrect_answer(self):
        response = self.client.post('/api/practice/submit/', {
            'question_id': self.question.id,
            'user_answer': 'wrong',
            'duration_seconds': 5,
            'answer_switches': 0,
        })
        assert response.status_code == 200
        assert response.data['is_correct'] is False

    def test_missing_fields(self):
        response = self.client.post('/api/practice/submit/', {})
        assert response.status_code == 400

    def test_invalid_question_id(self):
        response = self.client.post('/api/practice/submit/', {
            'question_id': 99999,
            'user_answer': 'test',
        })
        assert response.status_code == 404

    def test_incorrect_response_excludes_correct_answer(self):
        response = self.client.post('/api/practice/submit/', {
            'question_id': self.question.id,
            'user_answer': 'wrong',
            'duration_seconds': 5,
        })
        assert response.status_code == 200
        assert response.data['is_correct'] is False
        assert 'correct_answer' not in response.data

    def test_correct_response_includes_correct_answer(self):
        response = self.client.post('/api/practice/submit/', {
            'question_id': self.question.id,
            'user_answer': 'shining',
            'duration_seconds': 5,
        })
        assert response.status_code == 200
        assert response.data['is_correct'] is True
        assert response.data['correct_answer'] == 'shining'

    def test_retry_does_not_create_second_user_answer(self):
        self.client.post('/api/practice/submit/', {
            'question_id': self.question.id,
            'user_answer': 'wrong',
            'duration_seconds': 5,
        })
        assert UserAnswer.objects.filter(user=self.student).count() == 1
        self.client.post('/api/practice/submit/', {
            'question_id': self.question.id,
            'user_answer': 'shining',
            'is_retry': True,
        })
        assert UserAnswer.objects.filter(user=self.student).count() == 1

    def test_retry_does_not_change_mastery_points(self):
        self.client.post('/api/practice/submit/', {
            'question_id': self.question.id,
            'user_answer': 'wrong',
            'duration_seconds': 5,
        })
        progress = UserWordProgress.objects.get(user=self.student, word=self.word)
        points_after_wrong = progress.mastery_points

        self.client.post('/api/practice/submit/', {
            'question_id': self.question.id,
            'user_answer': 'shining',
            'is_retry': True,
        })
        progress.refresh_from_db()
        assert progress.mastery_points == points_after_wrong

    def test_retry_does_not_award_xp(self):
        self.client.post('/api/practice/submit/', {
            'question_id': self.question.id,
            'user_answer': 'wrong',
            'duration_seconds': 5,
        })
        self.student.refresh_from_db()
        xp_after_wrong = self.student.xp_points

        self.client.post('/api/practice/submit/', {
            'question_id': self.question.id,
            'user_answer': 'shining',
            'is_retry': True,
        })
        self.student.refresh_from_db()
        assert self.student.xp_points == xp_after_wrong

    def test_retry_correct_returns_is_correct_true(self):
        self.client.post('/api/practice/submit/', {
            'question_id': self.question.id,
            'user_answer': 'wrong',
            'duration_seconds': 5,
        })
        response = self.client.post('/api/practice/submit/', {
            'question_id': self.question.id,
            'user_answer': 'shining',
            'is_retry': True,
        })
        assert response.status_code == 200
        assert response.data['is_correct'] is True
        assert response.data['is_retry'] is True

    def test_retry_incorrect_excludes_correct_answer(self):
        self.client.post('/api/practice/submit/', {
            'question_id': self.question.id,
            'user_answer': 'wrong',
            'duration_seconds': 5,
        })
        response = self.client.post('/api/practice/submit/', {
            'question_id': self.question.id,
            'user_answer': 'still_wrong',
            'is_retry': True,
        })
        assert response.data['is_correct'] is False
        assert 'correct_answer' not in response.data

    def test_retry_increments_retry_count(self):
        self.client.post('/api/practice/submit/', {
            'question_id': self.question.id,
            'user_answer': 'wrong',
            'duration_seconds': 5,
        })
        answer = UserAnswer.objects.get(user=self.student, question=self.question)
        assert answer.retry_count == 0

        self.client.post('/api/practice/submit/', {
            'question_id': self.question.id,
            'user_answer': 'still_wrong',
            'is_retry': True,
        })
        answer.refresh_from_db()
        assert answer.retry_count == 1

        self.client.post('/api/practice/submit/', {
            'question_id': self.question.id,
            'user_answer': 'shining',
            'is_retry': True,
        })
        answer.refresh_from_db()
        assert answer.retry_count == 2

    def test_typo_retry_flag_makes_next_correct_answer_fragile(self):
        self.question.correct_answers = ['bright']
        self.question.save()
        for index, duration in enumerate(range(2, 17)):
            history_word = WordFactory(text=f'history_{index}')
            history_question = QuestionFactory(
                word=history_word,
                question_type=self.question.question_type,
                correct_answers=['answer'],
            )
            UserAnswer.objects.create(
                user=self.student,
                question=history_question,
                user_answer='answer',
                is_correct=True,
                duration_seconds=duration,
            )

        typo_response = self.client.post('/api/practice/submit/', {
            'question_id': self.question.id,
            'user_answer': 'brigt',
            'duration_seconds': 8,
        })
        assert typo_response.status_code == 200
        assert typo_response.data['is_typo'] is True

        correct_response = self.client.post('/api/practice/submit/', {
            'question_id': self.question.id,
            'user_answer': 'bright',
            'duration_seconds': 8,
        })

        assert correct_response.status_code == 200
        assert correct_response.data['is_correct'] is True
        assert correct_response.data['response_quality'] == 'typo_retry_correct'
        assert correct_response.data['is_fragile'] is True


@pytest.mark.django_db
class TestSessionSummaryView:
    @pytest.fixture(autouse=True)
    def setup(self):
        _seed_mastery_levels()
        self.student = StudentUserFactory()
        self.client = _make_client(self.student)

    def test_returns_summary(self):
        word = WordFactory(text='bright')
        WordDefinitionFactory(word=word)
        question = QuestionFactory(word=word)
        UserAnswer.objects.create(
            user=self.student, question=question,
            user_answer='correct', is_correct=True,
        )
        response = self.client.post('/api/practice/session-summary/', {
            'start_time': '2020-01-01T00:00:00',
        })
        assert response.status_code == 200
        assert 'total_practiced' in response.data
        assert 'strengths' in response.data
        assert 'weaknesses' in response.data

    def test_missing_start_time(self):
        response = self.client.post('/api/practice/session-summary/', {})
        assert response.status_code == 400


@pytest.mark.django_db
class TestApplySessionBonusesView:
    def test_applies_bonus_xp(self):
        student = StudentUserFactory()
        client = _make_client(student)
        original_xp = student.xp_points
        response = client.post('/api/practice/apply-bonuses/', {
            'max_focus_streak': 5,
        })
        assert response.status_code == 200
        student.refresh_from_db()
        assert student.xp_points == original_xp + 5

    def test_invalid_streak(self):
        student = StudentUserFactory()
        client = _make_client(student)
        response = client.post('/api/practice/apply-bonuses/', {
            'max_focus_streak': -1,
        })
        assert response.status_code == 400


# =============================================================================
# STUDENT DASHBOARD VIEWS
# =============================================================================


@pytest.mark.django_db
class TestStudentDashboardView:
    @pytest.fixture(autouse=True)
    def setup(self):
        _seed_mastery_levels()
        self.student = StudentUserFactory()
        self.client = _make_client(self.student)

    def test_returns_dashboard_data(self):
        response = self.client.get('/api/student/dashboard/')
        assert response.status_code == 200
        assert 'words_due_today' in response.data
        assert 'practice_streak' in response.data
        assert 'mastery_breakdown' in response.data
        assert 'daily_question_limit' in response.data

    def test_teacher_cannot_access(self):
        teacher = TeacherUserFactory()
        client = _make_client(teacher)
        response = client.get('/api/student/dashboard/')
        assert response.status_code == 403

    def test_returns_goal_bounds(self):
        response = self.client.get('/api/student/dashboard/')
        assert response.status_code == 200
        assert 'daily_goal_min' in response.data
        assert 'daily_goal_max' in response.data
        assert 'last_goal_prompt_date' in response.data
        assert response.data['daily_goal_min'] == self.student.daily_goal_min
        assert response.data['daily_goal_max'] == self.student.daily_goal_max

    def test_counts_words_due_later_today(self):
        word = WordFactory(text='bright')
        question = QuestionFactory(word=word, lexile_score=650)
        level1 = MasteryLevel.objects.get(level_id=1)
        question.suitable_levels.add(level1)
        UserWordProgress.objects.create(
            user=self.student, word=word,
            level=level1, next_review_at=_later_today(),
        )

        response = self.client.get('/api/student/dashboard/')

        assert response.status_code == 200
        assert response.data['words_due_today'] == 1

    def test_rolls_hidden_mastery_levels_into_mastered_breakdown(self):
        hidden_level = MasteryLevel.objects.get(level_id=6)
        word = WordFactory(text='settled')
        UserWordProgress.objects.create(
            user=self.student,
            word=word,
            level=hidden_level,
            next_review_at=timezone.now(),
        )

        response = self.client.get('/api/student/dashboard/')

        assert response.status_code == 200
        level_names = [item['level_name'] for item in response.data['mastery_breakdown']]
        assert 'Long-Term Retention' not in level_names
        assert 'Long-Term Mastery' not in level_names
        mastered = next(
            item for item in response.data['mastery_breakdown']
            if item['level_name'] == 'Mastered'
        )
        assert mastered['word_count'] == 1

    def test_hidden_mastery_transitions_do_not_change_mastered_deltas(self):
        level5 = MasteryLevel.objects.get(level_id=5)
        level6 = MasteryLevel.objects.get(level_id=6)
        level7 = MasteryLevel.objects.get(level_id=7)
        word = WordFactory(text='settled')

        for old_level, new_level in [
            (level5, level6),
            (level6, level7),
            (level7, level6),
            (level6, level5),
        ]:
            MasteryLevelLog.objects.create(
                user=self.student,
                word=word,
                old_level=old_level,
                new_level=new_level,
            )

        response = self.client.get('/api/student/dashboard/')

        assert response.status_code == 200
        mastered = next(
            item for item in response.data['mastery_breakdown']
            if item['level_name'] == 'Mastered'
        )
        assert mastered['delta_today'] == 0
        assert mastered['delta_week'] == 0


@pytest.mark.django_db
class TestStudentGoalPromptView:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.student = StudentUserFactory()
        self.client = _make_client(self.student)

    def test_records_prompt_date(self):
        assert self.student.last_goal_prompt_date is None
        response = self.client.post('/api/student/goal-prompt-shown/')
        assert response.status_code == 200
        assert response.data['recorded'] is True
        self.student.refresh_from_db()
        assert self.student.last_goal_prompt_date == timezone.localdate()

    def test_teacher_cannot_access(self):
        teacher = TeacherUserFactory()
        client = _make_client(teacher)
        response = client.post('/api/student/goal-prompt-shown/')
        assert response.status_code == 403
    def test_returns_words_at_level(self):
        _seed_mastery_levels()
        student = StudentUserFactory()
        word = WordFactory(text='bright')
        WordDefinitionFactory(word=word)
        level1 = MasteryLevel.objects.get(level_id=1)
        UserWordProgress.objects.create(
            user=student, word=word,
            level=level1, next_review_at=timezone.now(),
        )
        client = _make_client(student)
        response = client.get('/api/student/words-by-level/1/')
        assert response.status_code == 200
        assert len(response.data) == 1
        assert response.data[0]['text'] == 'bright'

    def test_mastered_word_list_includes_hidden_levels(self):
        _seed_mastery_levels()
        student = StudentUserFactory()
        visible_word = WordFactory(text='mastered')
        hidden_word = WordFactory(text='settled')
        WordDefinitionFactory(word=visible_word)
        WordDefinitionFactory(word=hidden_word)
        level5 = MasteryLevel.objects.get(level_id=5)
        level7 = MasteryLevel.objects.get(level_id=7)
        UserWordProgress.objects.create(
            user=student, word=visible_word,
            level=level5, next_review_at=timezone.now(),
        )
        UserWordProgress.objects.create(
            user=student, word=hidden_word,
            level=level7, next_review_at=timezone.now(),
        )
        client = _make_client(student)

        response = client.get('/api/student/words-by-level/5/')

        assert response.status_code == 200
        assert {item['text'] for item in response.data} == {'mastered', 'settled'}


@pytest.mark.django_db
class TestStudentLearningPatternsView:
    def test_student_can_view_own_patterns(self):
        student = StudentUserFactory()
        client = _make_client(student)
        response = client.get('/api/student/learning-patterns/')
        assert response.status_code == 200
        assert 'patterns' in response.data


# =============================================================================
# TEACHER DASHBOARD VIEWS
# =============================================================================


@pytest.mark.django_db
class TestStudentProgressDashboardView:
    def test_teacher_views_student_progress(self):
        _seed_mastery_levels()
        teacher = TeacherUserFactory()
        student = StudentUserFactory()
        teacher.students.add(student)
        client = _make_client(teacher)
        response = client.get(f'/api/teacher/students/{student.id}/progress/')
        assert response.status_code == 200
        assert response.data['student_username'] == student.username

    def test_admin_can_view(self):
        _seed_mastery_levels()
        admin = AdminUserFactory()
        student = StudentUserFactory()
        admin.students.add(student)
        client = _make_client(admin)
        response = client.get(f'/api/teacher/students/{student.id}/progress/')
        assert response.status_code == 200

    def test_student_cannot_access(self):
        student = StudentUserFactory()
        other_student = StudentUserFactory()
        client = _make_client(student)
        response = client.get(f'/api/teacher/students/{other_student.id}/progress/')
        assert response.status_code == 403

    def test_unassigned_student_returns_404(self):
        teacher = TeacherUserFactory()
        unrelated_student = StudentUserFactory()
        client = _make_client(teacher)
        response = client.get(f'/api/teacher/students/{unrelated_student.id}/progress/')
        assert response.status_code == 404


@pytest.mark.django_db
class TestTeacherLearningPatternsView:
    def test_teacher_views_student_patterns(self):
        teacher = TeacherUserFactory()
        student = StudentUserFactory()
        teacher.students.add(student)
        client = _make_client(teacher)
        response = client.get(f'/api/teacher/students/{student.id}/learning-patterns/')
        assert response.status_code == 200
        assert 'patterns' in response.data


@pytest.mark.django_db
class TestRosterDashboardView:
    def test_returns_roster_data(self):
        teacher = TeacherUserFactory()
        student = StudentUserFactory()
        teacher.students.add(student)
        client = _make_client(teacher)
        response = client.get('/api/teacher/roster/')
        assert response.status_code == 200
        assert 'roster' in response.data
        assert 'groups' in response.data

    def test_student_cannot_access(self):
        student = StudentUserFactory()
        client = _make_client(student)
        response = client.get('/api/teacher/roster/')
        assert response.status_code == 403

    def test_filters_by_group(self):
        teacher = TeacherUserFactory()
        student = StudentUserFactory()
        teacher.students.add(student)
        group = StudentGroupFactory(teacher=teacher)
        group.students.add(student)
        client = _make_client(teacher)
        response = client.get(f'/api/teacher/roster/?group_id={group.id}')
        assert response.status_code == 200
        assert len(response.data['roster']) == 1


# =============================================================================
# INSTRUCTIONAL VIEWS
# =============================================================================


@pytest.mark.django_db
class TestStudentAssignedSetsView:
    def test_returns_assigned_sets(self):
        _seed_mastery_levels()
        teacher = TeacherUserFactory()
        student = StudentUserFactory()
        teacher.students.add(student)
        ws = WordSetFactory(creator=teacher)
        word = WordFactory()
        ws.words.add(word)
        StudentWordSetAssignment.objects.create(
            user=student, word_set=ws, assigned_by=teacher,
        )
        client = _make_client(student)
        response = client.get('/api/student/assigned-sets/')
        assert response.status_code == 200
        assert len(response.data) >= 1
        assert response.data[0]['title'] == ws.title

    def test_includes_pack_progress(self):
        _seed_mastery_levels()
        teacher = TeacherUserFactory()
        student = StudentUserFactory()
        teacher.students.add(student)
        ws = WordSetFactory(creator=teacher)
        StudentWordSetAssignment.objects.create(
            user=student, word_set=ws, assigned_by=teacher,
        )
        pack = WordPackFactory(word_set=ws, label='Pack 1')
        StudentPackCompletion.objects.create(user=student, pack=pack)
        client = _make_client(student)
        response = client.get('/api/student/assigned-sets/')
        assert response.status_code == 200
        packs = response.data[0]['packs']
        assert packs[0]['is_completed'] is True


@pytest.mark.django_db
class TestInstructionalPackView:
    @pytest.fixture(autouse=True)
    def setup(self):
        _seed_mastery_levels()
        self.teacher = TeacherUserFactory()
        self.student = StudentUserFactory()
        self.teacher.students.add(self.student)
        self.ws = WordSetFactory(creator=self.teacher)
        self.word = WordFactory(text='bright')
        self.ws.words.add(self.word)
        StudentWordSetAssignment.objects.create(
            user=self.student, word_set=self.ws, assigned_by=self.teacher,
        )
        self.pack = WordPackFactory(word_set=self.ws, label='Pack 1')
        WordPackItem.objects.create(pack=self.pack, word=self.word, order=0)

    def test_returns_pack_data(self):
        client = _make_client(self.student)
        response = client.get(f'/api/instructional/packs/{self.pack.id}/')
        assert response.status_code == 200
        assert response.data['pack_id'] == self.pack.id
        assert response.data['label'] == 'Pack 1'

    def test_returns_legacy_micro_story_with_type(self):
        MicroStory.objects.create(
            pack=self.pack,
            story_text='The **bright** sun rose.',
            reading_level=650,
        )
        client = _make_client(self.student)

        response = client.get(f'/api/instructional/packs/{self.pack.id}/')

        assert response.status_code == 200
        assert response.data['story']['type'] == 'micro_story'
        assert response.data['story']['story_text'] == 'The **bright** sun rose.'

    def test_returns_graphic_novel_before_micro_story(self):
        MicroStory.objects.create(
            pack=self.pack,
            story_text='The **bright** sun rose.',
            reading_level=650,
        )
        novel = GraphicNovel.objects.create(
            pack=self.pack,
            title='The Bright Signal',
            synopsis='A student follows a signal.',
            style_prompt='Readable comic art.',
            reading_level=650,
            is_selected=True,
        )
        GraphicNovelPage.objects.create(
            novel=novel,
            page_number=1,
            panel_count=1,
            layout_description='Single splash page.',
            panel_descriptions=[{'panel_number': 1, 'vocab_words': ['bright']}],
            vocab_words_used=['bright'],
        )
        client = _make_client(self.student)

        response = client.get(f'/api/instructional/packs/{self.pack.id}/')

        assert response.status_code == 200
        assert response.data['story']['type'] == 'graphic_novel'
        assert response.data['story']['title'] == 'The Bright Signal'
        assert response.data['story']['pages'][0]['page_number'] == 1
        assert response.data['story']['pages'][0]['vocab_words'] == ['bright']

    def test_unassigned_student_gets_403(self):
        unassigned = StudentUserFactory()
        client = _make_client(unassigned)
        response = client.get(f'/api/instructional/packs/{self.pack.id}/')
        assert response.status_code == 403

    def test_missing_pack_gets_404(self):
        client = _make_client(self.student)
        response = client.get('/api/instructional/packs/99999/')
        assert response.status_code == 404


@pytest.mark.django_db
class TestCompletePackView:
    @pytest.fixture(autouse=True)
    def setup(self):
        _seed_mastery_levels()
        self.teacher = TeacherUserFactory()
        self.student = StudentUserFactory()
        self.teacher.students.add(self.student)
        self.ws = WordSetFactory(creator=self.teacher)
        self.word = WordFactory(text='bright')
        self.ws.words.add(self.word)
        StudentWordSetAssignment.objects.create(
            user=self.student, word_set=self.ws, assigned_by=self.teacher,
        )
        self.pack = WordPackFactory(word_set=self.ws)
        WordPackItem.objects.create(pack=self.pack, word=self.word, order=0)
        level1 = MasteryLevel.objects.get(level_id=1)
        UserWordProgress.objects.create(
            user=self.student, word=self.word,
            level=level1, next_review_at=timezone.now(),
            instructional_status='PENDING',
        )

    def test_completes_pack(self):
        client = _make_client(self.student)
        response = client.post(f'/api/instructional/packs/{self.pack.id}/complete/')
        assert response.status_code == 200
        assert StudentPackCompletion.objects.filter(
            user=self.student, pack=self.pack,
        ).exists()

    def test_flips_status_to_ready(self):
        client = _make_client(self.student)
        client.post(f'/api/instructional/packs/{self.pack.id}/complete/')
        progress = UserWordProgress.objects.get(user=self.student, word=self.word)
        assert progress.instructional_status == 'READY'


# =============================================================================
# TEACHER WORD SET VIEWS
# =============================================================================


@pytest.mark.django_db
class TestWordSetViewSet:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.teacher = TeacherUserFactory()
        self.client = _make_client(self.teacher)

    def test_list_word_sets(self):
        WordSetFactory(creator=self.teacher, title='Set A')
        response = self.client.get('/api/word-sets/')
        assert response.status_code == 200
        assert len(response.data) >= 1

    def test_create_word_set(self):
        response = self.client.post('/api/word-sets/', {
            'title': 'New Set', 'description': 'Test',
        })
        assert response.status_code == 201
        assert WordSet.objects.filter(title='New Set', creator=self.teacher).exists()

    def test_retrieve_word_set(self):
        ws = WordSetFactory(creator=self.teacher)
        word = WordFactory(text='bright')
        ws.words.add(word)
        response = self.client.get(f'/api/word-sets/{ws.id}/')
        assert response.status_code == 200
        assert 'words' in response.data

    def test_update_word_set(self):
        ws = WordSetFactory(creator=self.teacher)
        response = self.client.patch(f'/api/word-sets/{ws.id}/', {
            'title': 'Updated Title',
        })
        assert response.status_code == 200
        ws.refresh_from_db()
        assert ws.title == 'Updated Title'

    def test_delete_word_set(self):
        ws = WordSetFactory(creator=self.teacher)
        response = self.client.delete(f'/api/word-sets/{ws.id}/')
        assert response.status_code == 204

    def test_admin_can_delete_others_word_set(self):
        admin = AdminUserFactory()
        ws = WordSetFactory(creator=self.teacher)
        client = _make_client(admin)
        response = client.delete(f'/api/word-sets/{ws.id}/')
        assert response.status_code == 204
        assert not WordSet.objects.filter(id=ws.id).exists()

    def test_admin_can_delete_others_generated_word_set(self):
        admin = AdminUserFactory()
        ws = WordSetFactory(
            creator=self.teacher,
            generation_status=WordSet.GenerationStatus.GENERATED,
        )
        client = _make_client(admin)
        response = client.delete(f'/api/word-sets/{ws.id}/')
        assert response.status_code == 204
        assert not WordSet.objects.filter(id=ws.id).exists()

    def test_cannot_update_word_set_after_generation_requested(self):
        ws = WordSetFactory(
            creator=self.teacher,
            generation_status=WordSet.GenerationStatus.GENERATION_REQUESTED,
            input_words=['bright'],
        )
        response = self.client.patch(f'/api/word-sets/{ws.id}/', {
            'input_words': ['bright', 'discover'],
        }, format='json')
        assert response.status_code == 400
        ws.refresh_from_db()
        assert ws.input_words == ['bright']

    def test_cannot_delete_generated_word_set(self):
        ws = WordSetFactory(
            creator=self.teacher,
            generation_status=WordSet.GenerationStatus.GENERATED,
        )
        response = self.client.delete(f'/api/word-sets/{ws.id}/')
        assert response.status_code == 400
        assert WordSet.objects.filter(id=ws.id).exists()

    def test_cannot_edit_others_word_set(self):
        other_teacher = TeacherUserFactory()
        ws = WordSetFactory(creator=other_teacher)
        response = self.client.patch(f'/api/word-sets/{ws.id}/', {
            'title': 'Hacked',
        })
        assert response.status_code in (403, 404)

    def test_student_cannot_create(self):
        student = StudentUserFactory()
        client = _make_client(student)
        response = client.post('/api/word-sets/', {'title': 'Test'})
        assert response.status_code == 403


@pytest.mark.django_db
class TestWordSetAssignAction:
    def test_assigns_word_set(self):
        _seed_mastery_levels()
        teacher = TeacherUserFactory()
        student = StudentUserFactory()
        teacher.students.add(student)
        ws = WordSetFactory(creator=teacher)
        word = WordFactory()
        ws.words.add(word)
        # A word set can only be assigned when it has a published (is_selected)
        # graphic novel or infographic in at least one of its packs.
        pack = WordPackFactory(word_set=ws)
        GraphicNovelFactory(pack=pack, is_selected=True)
        client = _make_client(teacher)
        response = client.post(f'/api/word-sets/{ws.id}/assign/', {
            'student_ids': [student.id],
            'group_ids': [],
        }, format='json')
        assert response.status_code == 200
        assert StudentWordSetAssignment.objects.filter(
            user=student, word_set=ws,
        ).exists()


@pytest.mark.django_db
class TestWordSetAddRemoveWordActions:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.teacher = TeacherUserFactory()
        self.client = _make_client(self.teacher)
        self.ws = WordSetFactory(creator=self.teacher)
        self.word = WordFactory(text='bright')

    def test_add_word(self):
        response = self.client.post(f'/api/word-sets/{self.ws.id}/add_word/', {
            'word_id': self.word.id,
        })
        assert response.status_code == 200
        assert self.ws.words.filter(id=self.word.id).exists()

    def test_cannot_add_word_after_generation_starts(self):
        self.ws.generation_status = WordSet.GenerationStatus.GENERATION_REQUESTED
        self.ws.save(update_fields=['generation_status'])
        response = self.client.post(f'/api/word-sets/{self.ws.id}/add_word/', {
            'word_id': self.word.id,
        })
        assert response.status_code == 400
        assert not self.ws.words.filter(id=self.word.id).exists()

    def test_remove_word(self):
        self.ws.words.add(self.word)
        response = self.client.post(f'/api/word-sets/{self.ws.id}/remove_word/', {
            'word_id': self.word.id,
        })
        assert response.status_code == 200
        assert not self.ws.words.filter(id=self.word.id).exists()

    def test_cannot_remove_word_after_generation_starts(self):
        self.ws.words.add(self.word)
        self.ws.generation_status = WordSet.GenerationStatus.GENERATING
        self.ws.save(update_fields=['generation_status'])
        response = self.client.post(f'/api/word-sets/{self.ws.id}/remove_word/', {
            'word_id': self.word.id,
        })
        assert response.status_code == 400
        assert self.ws.words.filter(id=self.word.id).exists()


# =============================================================================
# PACK MANAGEMENT VIEWS
# =============================================================================


@pytest.mark.django_db
class TestPackManagement:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.teacher = TeacherUserFactory()
        self.client = _make_client(self.teacher)
        self.ws = WordSetFactory(creator=self.teacher)
        self.word = WordFactory(text='bright')
        self.ws.words.add(self.word)

    def test_list_packs(self):
        pack = WordPackFactory(word_set=self.ws, label='Pack 1')
        WordPackItem.objects.create(pack=pack, word=self.word, order=0)
        response = self.client.get(f'/api/word-sets/{self.ws.id}/packs/')
        assert response.status_code == 200
        assert len(response.data) == 1
        assert response.data[0]['label'] == 'Pack 1'

    def test_create_pack(self):
        response = self.client.post(
            f'/api/word-sets/{self.ws.id}/packs/',
            {'label': 'New Pack', 'word_ids': [self.word.id]},
            format='json',
        )
        assert response.status_code == 201
        assert WordPack.objects.filter(word_set=self.ws, label='New Pack').exists()

    def test_update_pack(self):
        pack = WordPackFactory(word_set=self.ws, label='Old Label')
        response = self.client.patch(
            f'/api/word-sets/{self.ws.id}/packs/{pack.id}/',
            {'label': 'New Label'},
        )
        assert response.status_code == 200
        pack.refresh_from_db()
        assert pack.label == 'New Label'

    def test_delete_pack(self):
        pack = WordPackFactory(word_set=self.ws)
        response = self.client.delete(
            f'/api/word-sets/{self.ws.id}/packs/{pack.id}/',
        )
        assert response.status_code == 204

# =============================================================================
# TEACHER STUDENT MANAGEMENT VIEWS
# =============================================================================


@pytest.mark.django_db
class TestTeacherStudentViewSet:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.teacher = TeacherUserFactory()
        self.client = _make_client(self.teacher)

    def test_list_students(self):
        student = StudentUserFactory()
        self.teacher.students.add(student)
        response = self.client.get('/api/teacher/students/')
        assert response.status_code == 200
        assert len(response.data) == 1

    def test_create_student(self):
        response = self.client.post('/api/teacher/students/', {
            'username': 'new_student_99',
            'password': 'pass123',
        })
        assert response.status_code == 201
        new_student = CustomUser.objects.get(username='new_student_99')
        assert new_student.role == 'STUDENT'
        assert self.teacher.students.filter(id=new_student.id).exists()

    def test_update_student_settings(self):
        student = StudentUserFactory()
        self.teacher.students.add(student)
        response = self.client.patch(
            f'/api/teacher/students/{student.id}/',
            {'daily_question_limit': 30, 'lexile_min': 400, 'lexile_max': 800},
        )
        assert response.status_code == 200
        student.refresh_from_db()
        assert student.daily_question_limit == 30


@pytest.mark.django_db
class TestBulkCreateStudentsView:
    def test_bulk_create(self):
        teacher = TeacherUserFactory()
        client = _make_client(teacher)
        response = client.post(
            '/api/teacher/students/bulk/',
            [
                {'username': 'bulk_1', 'password': 'pass123'},
                {'username': 'bulk_2', 'password': 'pass123'},
            ],
            format='json',
        )
        assert response.status_code == 201
        assert response.data['success_count'] == 2

    def test_rejects_duplicate_usernames(self):
        teacher = TeacherUserFactory()
        client = _make_client(teacher)
        response = client.post(
            '/api/teacher/students/bulk/',
            [
                {'username': 'dup', 'password': 'pass123'},
                {'username': 'dup', 'password': 'pass123'},
            ],
            format='json',
        )
        assert response.status_code == 400


# =============================================================================
# STUDENT GROUP VIEWS
# =============================================================================


@pytest.mark.django_db
class TestStudentGroupViewSet:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.teacher = TeacherUserFactory()
        self.client = _make_client(self.teacher)

    def test_list_groups(self):
        StudentGroupFactory(teacher=self.teacher, name='Class A')
        response = self.client.get('/api/groups/')
        assert response.status_code == 200
        assert len(response.data) == 1

    def test_create_group(self):
        response = self.client.post('/api/groups/', {
            'name': 'New Group',
        })
        assert response.status_code == 201
        assert StudentGroup.objects.filter(
            name='New Group', teacher=self.teacher,
        ).exists()

    def test_update_group(self):
        group = StudentGroupFactory(teacher=self.teacher)
        response = self.client.patch(f'/api/groups/{group.id}/', {
            'name': 'Updated Name',
        })
        assert response.status_code == 200
        group.refresh_from_db()
        assert group.name == 'Updated Name'

    def test_delete_group(self):
        group = StudentGroupFactory(teacher=self.teacher)
        response = self.client.delete(f'/api/groups/{group.id}/')
        assert response.status_code == 204

    def test_cannot_see_others_groups(self):
        other_teacher = TeacherUserFactory()
        StudentGroupFactory(teacher=other_teacher, name='Not Mine')
        response = self.client.get('/api/groups/')
        assert response.status_code == 200
        assert len(response.data) == 0


# =============================================================================
# WORD VIEWSET
# =============================================================================


@pytest.mark.django_db
class TestWordViewSet:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.teacher = TeacherUserFactory()
        self.student = StudentUserFactory()
        self.teacher.students.add(self.student)
        self.client = _make_client(self.teacher)

    def test_list_words(self):
        word = WordFactory(text='bright')
        WordDefinitionFactory(word=word)
        _seed_mastery_levels()
        level1 = MasteryLevel.objects.get(level_id=1)
        UserWordProgress.objects.create(
            user=self.student, word=word,
            level=level1, next_review_at=timezone.now(),
        )
        response = self.client.get('/api/words/')
        assert response.status_code == 200
        assert len(response.data) >= 1


# =============================================================================
# CURRICULUM & LEVEL VIEWS
# =============================================================================


@pytest.mark.django_db
class TestCurriculumAndLevelViews:
    def test_list_curricula(self):
        CurriculumFactory(name='Wonders')
        teacher = TeacherUserFactory()
        client = _make_client(teacher)
        response = client.get('/api/curricula/')
        assert response.status_code == 200
        assert len(response.data) >= 1

    def test_list_levels(self):
        LevelFactory(name='Grade 2')
        teacher = TeacherUserFactory()
        client = _make_client(teacher)
        response = client.get('/api/levels/')
        assert response.status_code == 200
        assert len(response.data) >= 1


# =============================================================================
# GENERATION VIEWS (Admin only)
# =============================================================================


@pytest.mark.django_db
class TestGenerationViews:
    def test_teacher_cannot_trigger_generation(self):
        teacher = TeacherUserFactory()
        ws = WordSetFactory(creator=teacher)
        client = _make_client(teacher)
        response = client.post(f'/api/word-sets/{ws.id}/generate/', {
            'words': ['apple', 'banana'],
        }, format='json')
        assert response.status_code == 403

    def test_admin_can_get_job_status(self):
        admin = AdminUserFactory()
        ws = WordSetFactory(creator=admin)
        job = GenerationJobFactory(word_set=ws, created_by=admin)
        client = _make_client(admin)
        response = client.get(f'/api/generation-jobs/{job.id}/')
        assert response.status_code == 200
        assert response.data['status'] == 'PENDING'

    def test_job_status_includes_graphic_novel_script_substeps(self):
        admin = AdminUserFactory()
        ws = WordSetFactory(creator=admin)
        job = GenerationJobFactory(word_set=ws, created_by=admin)
        GenerationJobLog.objects.create(
            job=job,
            step=GenerationJobLog.Step.GRAPHIC_NOVEL_SCRIPT,
            status=GenerationJob.Status.RUNNING,
            output_data={
                'substep': 'router_premises',
                'substep_label': 'Router + Premises',
                'pack_id': 123,
                'pack_label': 'Pack 1',
                'candidate_index': 0,
            },
        )
        GenerationJobLog.objects.create(
            job=job,
            step=GenerationJobLog.Step.GRAPHIC_NOVEL_SCRIPT,
            status=GenerationJob.Status.COMPLETED,
            duration_seconds=1.25,
            output_data={
                'substep': 'router_premises',
                'substep_label': 'Router + Premises',
                'pack_id': 123,
                'pack_label': 'Pack 1',
                'candidate_index': 0,
                'artifact_path': 'temp/generation_artifacts/job_1/pack_123_pack-1/cand_0/01_router_premises.json',
                'artifact_name': '01_router_premises.json',
                'summary': {'premise_count': 3},
            },
        )
        # A second candidate for the same pack must be grouped separately, not
        # collapsed into candidate 0's substeps.
        GenerationJobLog.objects.create(
            job=job,
            step=GenerationJobLog.Step.GRAPHIC_NOVEL_SCRIPT,
            status=GenerationJob.Status.COMPLETED,
            duration_seconds=2.0,
            output_data={
                'substep': 'team_selection',
                'substep_label': 'Team Selection',
                'pack_id': 123,
                'pack_label': 'Pack 1',
                'candidate_index': 1,
                'artifact_name': '01_team_selection.json',
            },
        )

        client = _make_client(admin)
        response = client.get(f'/api/generation-jobs/{job.id}/')

        assert response.status_code == 200
        pack_status = response.data['graphic_novel_script_substeps'][0]
        assert pack_status['pack_label'] == 'Pack 1'

        candidates = pack_status['candidates']
        assert [c['candidate_index'] for c in candidates] == [0, 1]

        cand0 = candidates[0]['substeps']
        assert [substep['substep'] for substep in cand0][:2] == [
            'team_selection',
            'router_premises',
        ]
        assert cand0[0]['label'] == 'Team Selection'
        assert cand0[0]['status'] == GenerationJob.Status.PENDING
        assert cand0[1]['substep'] == 'router_premises'
        assert cand0[1]['status'] == GenerationJob.Status.COMPLETED
        assert cand0[1]['artifact_name'] == '01_router_premises.json'

        # Candidate 1 has its own independent substep map.
        cand1 = candidates[1]['substeps']
        assert cand1[0]['substep'] == 'team_selection'
        assert cand1[0]['status'] == GenerationJob.Status.COMPLETED
        assert cand1[1]['status'] == GenerationJob.Status.PENDING

    def test_job_status_includes_infographic_design_substeps(self):
        """Infographic design + cloze both log under INFOGRAPHIC_DESIGN, so the
        status payload must split them into a per-candidate substep map (else the
        step row only reflects the last-logged substep)."""
        admin = AdminUserFactory()
        ws = WordSetFactory(creator=admin)
        job = GenerationJobFactory(word_set=ws, created_by=admin)
        for substep, label, st in [
            ('design', 'Infographic Design', GenerationJob.Status.COMPLETED),
            ('cloze', 'Infographic Cloze', GenerationJob.Status.RUNNING),
        ]:
            GenerationJobLog.objects.create(
                job=job,
                step=GenerationJobLog.Step.INFOGRAPHIC_DESIGN,
                status=st,
                output_data={
                    'substep': substep,
                    'substep_label': label,
                    'pack_id': 77,
                    'pack_label': 'IG Pack',
                    'candidate_index': 0,
                },
            )

        client = _make_client(admin)
        response = client.get(f'/api/generation-jobs/{job.id}/')

        assert response.status_code == 200
        pack_status = response.data['infographic_design_substeps'][0]
        assert pack_status['pack_label'] == 'IG Pack'
        cand0 = pack_status['candidates'][0]['substeps']
        assert [s['substep'] for s in cand0] == ['design', 'cloze']
        assert cand0[0]['status'] == GenerationJob.Status.COMPLETED
        assert cand0[1]['status'] == GenerationJob.Status.RUNNING

    def test_restart_infographic_substep_rejects_invalid_substep(self):
        admin = AdminUserFactory()
        ws = WordSetFactory(creator=admin)
        job = GenerationJobFactory(
            word_set=ws, created_by=admin, status=GenerationJob.Status.FAILED,
        )
        pack = WordPack.objects.create(word_set=ws, label='Pack 1', order=0)
        client = _make_client(admin)
        response = client.post(
            f'/api/generation-jobs/{job.id}/restart-infographic-substep/',
            {'pack_id': pack.id, 'substep': 'team_selection'},
            format='json',
        )
        assert response.status_code == 400
        assert 'Invalid substep' in response.data['error']

    def test_restart_infographic_substep_starts_thread(self):
        admin = AdminUserFactory()
        ws = WordSetFactory(creator=admin)
        job = GenerationJobFactory(
            word_set=ws, created_by=admin, status=GenerationJob.Status.FAILED,
        )
        pack = WordPack.objects.create(word_set=ws, label='Pack 1', order=0)
        client = _make_client(admin)
        with patch('vocabulary.views.generation_views.threading.Thread') as mock_thread:
            response = client.post(
                f'/api/generation-jobs/{job.id}/restart-infographic-substep/',
                {'pack_id': pack.id, 'substep': 'design', 'candidate_index': 1},
                format='json',
            )
        assert response.status_code == 200
        assert response.data['substep'] == 'design'
        assert response.data['candidate_index'] == 1
        mock_thread.assert_called_once()
        job.refresh_from_db()
        assert job.status == GenerationJob.Status.RUNNING

    def test_restart_infographic_substep_conflict_when_running(self):
        admin = AdminUserFactory()
        ws = WordSetFactory(creator=admin)
        job = GenerationJobFactory(
            word_set=ws, created_by=admin, status=GenerationJob.Status.RUNNING,
        )
        pack = WordPack.objects.create(word_set=ws, label='Pack 1', order=0)
        client = _make_client(admin)
        response = client.post(
            f'/api/generation-jobs/{job.id}/restart-infographic-substep/',
            {'pack_id': pack.id, 'substep': 'design'},
            format='json',
        )
        assert response.status_code == 409

    def test_job_status_includes_graphic_novel_page_statuses(self):
        admin = AdminUserFactory()
        ws = WordSetFactory(creator=admin)
        job = GenerationJobFactory(word_set=ws, created_by=admin)
        pack = WordPack.objects.create(word_set=ws, label='Pack 1', order=0)
        novel = GraphicNovel.objects.create(
            pack=pack,
            title='Page Status Novel',
            synopsis='A test synopsis.',
            style_prompt='Readable comic art.',
            reading_level=650,
            is_selected=True,
        )
        page = GraphicNovelPage.objects.create(
            novel=novel,
            page_number=1,
            generation_status=GraphicNovelPage.GenerationStatus.FAILED,
            generation_attempts=2,
            generation_error='API timeout',
            panel_count=1,
        )

        client = _make_client(admin)
        response = client.get(f'/api/generation-jobs/{job.id}/')

        assert response.status_code == 200
        assert response.data['graphic_novel_image_pages'][0]['id'] == page.id
        assert response.data['graphic_novel_image_pages'][0]['status'] == 'FAILED'
        assert response.data['graphic_novel_image_pages'][0]['attempts'] == 2
        assert response.data['graphic_novel_image_pages'][0]['error_message'] == 'API timeout'

    def test_stale_running_job_marks_running_graphic_page_failed(self):
        admin = AdminUserFactory()
        ws = WordSetFactory(creator=admin)
        job = GenerationJobFactory(
            word_set=ws,
            created_by=admin,
            status=GenerationJob.Status.RUNNING,
        )
        pack = WordPack.objects.create(word_set=ws, label='Pack 1', order=0)
        novel = GraphicNovel.objects.create(
            pack=pack,
            title='Stale Page Novel',
            synopsis='A test synopsis.',
            style_prompt='Readable comic art.',
            reading_level=650,
            is_selected=True,
        )
        page = GraphicNovelPage.objects.create(
            novel=novel,
            page_number=1,
            generation_status=GraphicNovelPage.GenerationStatus.RUNNING,
            generation_started_at=timezone.now() - timedelta(minutes=31),
            panel_count=1,
        )
        old_log = GenerationJobLog.objects.create(
            job=job,
            step=GenerationJobLog.Step.GRAPHIC_NOVEL_IMAGES,
            status=GenerationJob.Status.RUNNING,
        )
        GenerationJobLog.objects.filter(id=old_log.id).update(
            created_at=timezone.now() - timedelta(minutes=31),
        )

        client = _make_client(admin)
        response = client.get(f'/api/generation-jobs/{job.id}/')

        assert response.status_code == 200
        assert response.data['status'] == GenerationJob.Status.FAILED
        page.refresh_from_db()
        ws.refresh_from_db()
        assert page.generation_status == GraphicNovelPage.GenerationStatus.FAILED
        assert ws.generation_status == WordSet.GenerationStatus.TO_GENERATE
        assert GenerationJobLog.objects.filter(
            job=job,
            step=GenerationJobLog.Step.GRAPHIC_NOVEL_IMAGES,
            status=GenerationJob.Status.FAILED,
        ).exists()

    def test_admin_can_get_job_logs(self):
        admin = AdminUserFactory()
        ws = WordSetFactory(creator=admin)
        job = GenerationJobFactory(word_set=ws, created_by=admin)
        GenerationJobLog.objects.create(
            job=job, step='WORD_LOOKUP', status='COMPLETED',
        )
        client = _make_client(admin)
        response = client.get(f'/api/generation-jobs/{job.id}/logs/')
        assert response.status_code == 200
        assert len(response.data) >= 1

    @patch('vocabulary.views.generation_views.threading.Thread')
    def test_resume_job_records_fresh_running_activity(self, mock_thread):
        admin = AdminUserFactory()
        ws = WordSetFactory(creator=admin)
        job = GenerationJobFactory(
            word_set=ws,
            created_by=admin,
            status=GenerationJob.Status.FAILED,
            last_completed_step=GenerationJobLog.Step.WORD_LOOKUP,
            error_message='Previous failure',
        )
        old_log = GenerationJobLog.objects.create(
            job=job,
            step=GenerationJobLog.Step.WORD_LOOKUP,
            status=GenerationJob.Status.FAILED,
            error_message='Previous failure',
        )
        GenerationJobLog.objects.filter(id=old_log.id).update(
            created_at=timezone.now() - timedelta(minutes=20),
        )

        client = _make_client(admin)
        response = client.post(f'/api/generation-jobs/{job.id}/resume/')

        assert response.status_code == 200
        assert response.data['status'] == GenerationJob.Status.RUNNING
        mock_thread.return_value.start.assert_called_once()

        job.refresh_from_db()
        assert job.status == GenerationJob.Status.RUNNING
        assert job.error_message == ''

        running_log = GenerationJobLog.objects.filter(
            job=job,
            status=GenerationJob.Status.RUNNING,
        ).latest('created_at')
        assert running_log.step == GenerationJobLog.Step.DEDUP

        status_response = client.get(f'/api/generation-jobs/{job.id}/')
        assert status_response.status_code == 200
        assert status_response.data['status'] == GenerationJob.Status.RUNNING

    @patch('vocabulary.views.generation_views.threading.Thread')
    def test_admin_can_restart_generation_step_for_testing(self, mock_thread):
        admin = AdminUserFactory()
        ws = WordSetFactory(creator=admin)
        job = GenerationJobFactory(
            word_set=ws,
            created_by=admin,
            status=GenerationJob.Status.COMPLETED,
            last_completed_step=GenerationJobLog.Step.GRAPHIC_NOVEL_IMAGES,
        )

        client = _make_client(admin)
        response = client.post(
            f'/api/generation-jobs/{job.id}/restart-step/',
            {
                'step': GenerationJobLog.Step.QUESTION_GEN,
                'include_subsequent': True,
            },
            format='json',
        )

        assert response.status_code == 200
        assert response.data['status'] == GenerationJob.Status.RUNNING
        assert response.data['step'] == GenerationJobLog.Step.QUESTION_GEN
        mock_thread.return_value.start.assert_called_once()

        job.refresh_from_db()
        assert job.status == GenerationJob.Status.RUNNING
        assert job.error_message == ''

        running_log = GenerationJobLog.objects.filter(
            job=job,
            step=GenerationJobLog.Step.QUESTION_GEN,
            status=GenerationJob.Status.RUNNING,
        ).latest('created_at')
        assert running_log.output_data['include_subsequent'] is True

    def test_story_cloze_generation_is_not_active_restart_step(self):
        admin = AdminUserFactory()
        ws = WordSetFactory(creator=admin)
        job = GenerationJobFactory(
            word_set=ws,
            created_by=admin,
            status=GenerationJob.Status.COMPLETED,
        )

        client = _make_client(admin)
        response = client.post(
            f'/api/generation-jobs/{job.id}/restart-step/',
            {'step': GenerationJobLog.Step.STORY_CLOZE_GEN},
            format='json',
        )

        assert response.status_code == 400
        assert GenerationJobLog.Step.STORY_CLOZE_GEN not in response.data['valid_steps']

    def test_student_cannot_access_jobs(self):
        student = StudentUserFactory()
        client = _make_client(student)
        response = client.get('/api/generation-jobs/1/')
        assert response.status_code == 403

    def test_admin_cannot_add_words_to_generated_set(self):
        admin = AdminUserFactory()
        ws = WordSetFactory(
            creator=admin,
            generation_status=WordSet.GenerationStatus.GENERATED,
            input_words=['bright'],
        )
        client = _make_client(admin)
        response = client.post(f'/api/word-sets/{ws.id}/add-words/', {
            'words': ['discover'],
        }, format='json')
        assert response.status_code == 400
        ws.refresh_from_db()
        assert ws.input_words == ['bright']

    def _make_page_with_image(self, admin):
        ws = WordSetFactory(creator=admin)
        pack = WordPack.objects.create(word_set=ws, label='Pack 1', order=0)
        novel = GraphicNovel.objects.create(
            pack=pack,
            title='Edit Test Novel',
            synopsis='A test synopsis.',
            style_prompt='Readable comic art.',
            reading_level=650,
            is_selected=True,
        )
        page = GraphicNovelPage.objects.create(
            novel=novel,
            page_number=1,
            generation_status=GraphicNovelPage.GenerationStatus.COMPLETED,
            panel_count=1,
            prompt_used='Original prompt.',
        )
        # Minimal valid PNG header bytes are enough; the view only reads them.
        page.image.save('orig_page_1.png', ContentFile(b'\x89PNG\r\n\x1a\nORIGINAL'), save=True)
        return page

    @patch('vocabulary.views.generation_views.threading.Thread')
    def test_admin_edit_starts_async_image_job(self, mock_thread, settings, tmp_path):
        settings.MEDIA_ROOT = str(tmp_path)
        admin = AdminUserFactory()
        page = self._make_page_with_image(admin)

        client = _make_client(admin)
        response = client.post(
            f'/api/graphic-novel-pages/{page.id}/edit-image/',
            {'prompt': 'Make the sky purple.'},
            format='json',
        )

        # Validates synchronously, hands the slow image call to a worker thread.
        assert response.status_code == 202
        assert response.data['id'] == page.id
        assert response.data['generation_status'] == GraphicNovelPage.GenerationStatus.RUNNING
        mock_thread.return_value.start.assert_called_once()
        _, kwargs = mock_thread.call_args
        # The worker receives the page id, prompt, and reference image bytes.
        assert kwargs['args'][0] == page.id
        assert kwargs['args'][1] == 'Make the sky purple.'
        assert kwargs['args'][2].startswith(b'\x89PNG')

        page.refresh_from_db()
        assert page.generation_status == GraphicNovelPage.GenerationStatus.RUNNING
        assert page.generation_attempts == 1

    @patch('vocabulary.services.generation.helpers._llm_service.call_openai_image')
    def test_run_page_image_edit_worker_saves_edited_variant(self, mock_image, settings, tmp_path):
        from vocabulary.views.generation_views import _run_page_image_edit

        settings.MEDIA_ROOT = str(tmp_path)
        mock_image.return_value = b'\x89PNG\r\n\x1a\nEDITED'
        admin = AdminUserFactory()
        page = self._make_page_with_image(admin)

        _run_page_image_edit(page.id, 'Make the sky purple.', b'\x89PNG\r\n\x1a\nORIGINAL')

        # Reference image bytes were passed to the edit call.
        _, kwargs = mock_image.call_args
        assert kwargs['reference_image'].startswith(b'\x89PNG')
        page.refresh_from_db()
        assert page.generation_status == GraphicNovelPage.GenerationStatus.COMPLETED
        assert page.use_edited_image is True
        assert '[ADMIN EDIT] Make the sky purple.' in page.prompt_used
        # Original is preserved; edit lands in the separate edited_image field.
        page.image.open('rb')
        assert page.image.read() == b'\x89PNG\r\n\x1a\nORIGINAL'
        page.image.close()
        page.edited_image.open('rb')
        assert page.edited_image.read() == b'\x89PNG\r\n\x1a\nEDITED'
        page.edited_image.close()
        assert page.display_image == page.edited_image

    @patch('vocabulary.services.generation.helpers._llm_service.call_openai_image')
    def test_run_page_image_edit_worker_records_failure(self, mock_image, settings, tmp_path):
        from vocabulary.views.generation_views import _run_page_image_edit

        settings.MEDIA_ROOT = str(tmp_path)
        mock_image.side_effect = RuntimeError('provider exploded')
        admin = AdminUserFactory()
        page = self._make_page_with_image(admin)

        _run_page_image_edit(page.id, 'Make the sky purple.', b'\x89PNG\r\n\x1a\nORIGINAL')

        page.refresh_from_db()
        assert page.generation_status == GraphicNovelPage.GenerationStatus.FAILED
        assert 'provider exploded' in page.generation_error
        assert not page.edited_image

    @patch('vocabulary.views.generation_views.threading.Thread')
    def test_edit_image_409_when_already_running(self, mock_thread, settings, tmp_path):
        settings.MEDIA_ROOT = str(tmp_path)
        admin = AdminUserFactory()
        page = self._make_page_with_image(admin)
        page.generation_status = GraphicNovelPage.GenerationStatus.RUNNING
        page.save(update_fields=['generation_status'])

        client = _make_client(admin)
        response = client.post(
            f'/api/graphic-novel-pages/{page.id}/edit-image/',
            {'prompt': 'Make the sky purple.'},
            format='json',
        )
        assert response.status_code == 409
        mock_thread.return_value.start.assert_not_called()

    def test_image_status_returns_page_state(self, settings, tmp_path):
        settings.MEDIA_ROOT = str(tmp_path)
        admin = AdminUserFactory()
        page = self._make_page_with_image(admin)
        client = _make_client(admin)
        response = client.get(f'/api/graphic-novel-pages/{page.id}/image-status/')
        assert response.status_code == 200
        assert response.data['id'] == page.id
        assert response.data['generation_status'] == GraphicNovelPage.GenerationStatus.COMPLETED

    def test_image_status_403_for_student(self, settings, tmp_path):
        settings.MEDIA_ROOT = str(tmp_path)
        admin = AdminUserFactory()
        page = self._make_page_with_image(admin)
        student = StudentUserFactory()
        client = _make_client(student)
        response = client.get(f'/api/graphic-novel-pages/{page.id}/image-status/')
        assert response.status_code == 403

    def test_edit_image_requires_prompt(self, settings, tmp_path):
        settings.MEDIA_ROOT = str(tmp_path)
        admin = AdminUserFactory()
        page = self._make_page_with_image(admin)
        client = _make_client(admin)
        response = client.post(
            f'/api/graphic-novel-pages/{page.id}/edit-image/',
            {'prompt': '   '},
            format='json',
        )
        assert response.status_code == 400

    def test_edit_image_404_for_missing_page(self):
        admin = AdminUserFactory()
        client = _make_client(admin)
        response = client.post(
            '/api/graphic-novel-pages/999999/edit-image/',
            {'prompt': 'Change something.'},
            format='json',
        )
        assert response.status_code == 404

    def test_edit_image_400_when_page_has_no_image(self):
        admin = AdminUserFactory()
        ws = WordSetFactory(creator=admin)
        pack = WordPack.objects.create(word_set=ws, label='Pack 1', order=0)
        novel = GraphicNovel.objects.create(
            pack=pack, title='No Image Novel', synopsis='s',
            style_prompt='art', reading_level=650, is_selected=True,
        )
        page = GraphicNovelPage.objects.create(
            novel=novel, page_number=1, panel_count=1,
        )
        client = _make_client(admin)
        response = client.post(
            f'/api/graphic-novel-pages/{page.id}/edit-image/',
            {'prompt': 'Change something.'},
            format='json',
        )
        assert response.status_code == 400

    def test_student_cannot_edit_graphic_novel_page_image(self, settings, tmp_path):
        settings.MEDIA_ROOT = str(tmp_path)
        admin = AdminUserFactory()
        page = self._make_page_with_image(admin)
        student = StudentUserFactory()
        client = _make_client(student)
        response = client.post(
            f'/api/graphic-novel-pages/{page.id}/edit-image/',
            {'prompt': 'Change something.'},
            format='json',
        )
        assert response.status_code == 403

    @patch('vocabulary.services.generation.helpers._llm_service.call_openai_image')
    def test_admin_can_select_back_to_original_image(self, mock_image, settings, tmp_path):
        from vocabulary.views.generation_views import _run_page_image_edit

        settings.MEDIA_ROOT = str(tmp_path)
        mock_image.return_value = b'\x89PNG\r\n\x1a\nEDITED'
        admin = AdminUserFactory()
        page = self._make_page_with_image(admin)
        client = _make_client(admin)

        # Produce an edited variant (auto-selected) via the worker directly.
        _run_page_image_edit(page.id, 'Make it brighter.', b'\x89PNG\r\n\x1a\nORIGINAL')
        page.refresh_from_db()
        assert page.use_edited_image is True

        # Switch back to the original.
        response = client.post(
            f'/api/graphic-novel-pages/{page.id}/select-image/',
            {'variant': 'original'}, format='json',
        )
        assert response.status_code == 200
        assert response.data['use_edited_image'] is False
        assert response.data['has_edited_image'] is True
        page.refresh_from_db()
        assert page.use_edited_image is False
        assert page.display_image == page.image

        # And forward to the edited one again.
        response = client.post(
            f'/api/graphic-novel-pages/{page.id}/select-image/',
            {'variant': 'edited'}, format='json',
        )
        assert response.status_code == 200
        assert response.data['use_edited_image'] is True

    @patch('vocabulary.views.generation_views.threading.Thread')
    def test_admin_redraw_starts_async_image_job(self, mock_thread, settings, tmp_path):
        settings.MEDIA_ROOT = str(tmp_path)
        admin = AdminUserFactory()
        page = self._make_page_with_image(admin)

        client = _make_client(admin)
        response = client.post(
            f'/api/graphic-novel-pages/{page.id}/redraw-image/',
            format='json',
        )

        # Validates + builds the original payload synchronously, hands the slow
        # image call to a worker thread.
        assert response.status_code == 202
        assert response.data['id'] == page.id
        assert response.data['generation_status'] == GraphicNovelPage.GenerationStatus.RUNNING
        mock_thread.return_value.start.assert_called_once()
        _, kwargs = mock_thread.call_args
        # Worker gets (page_id, built prompt, previous-page reference bytes).
        assert kwargs['args'][0] == page.id
        assert isinstance(kwargs['args'][1], str) and kwargs['args'][1]
        # Page 1 has no previous page, so the continuity reference is None.
        assert kwargs['args'][2] is None

        page.refresh_from_db()
        assert page.generation_status == GraphicNovelPage.GenerationStatus.RUNNING
        assert page.generation_attempts == 1

    @patch('vocabulary.services.generation.helpers._llm_service.call_openai_image')
    def test_run_page_image_redraw_worker_saves_edited_variant(self, mock_image, settings, tmp_path):
        from vocabulary.views.generation_views import _run_page_image_redraw

        settings.MEDIA_ROOT = str(tmp_path)
        mock_image.return_value = b'\x89PNG\r\n\x1a\nREDRAWN'
        admin = AdminUserFactory()
        page = self._make_page_with_image(admin)

        _run_page_image_redraw(page.id, 'Built page prompt.', None)

        page.refresh_from_db()
        assert page.generation_status == GraphicNovelPage.GenerationStatus.COMPLETED
        assert page.use_edited_image is True
        assert '[REDRAW] Built page prompt.' in page.prompt_used
        # Original is preserved; redraw lands in the separate edited_image field.
        page.image.open('rb')
        assert page.image.read() == b'\x89PNG\r\n\x1a\nORIGINAL'
        page.image.close()
        page.edited_image.open('rb')
        assert page.edited_image.read() == b'\x89PNG\r\n\x1a\nREDRAWN'
        page.edited_image.close()
        assert page.display_image == page.edited_image

    @patch('vocabulary.services.generation.helpers._llm_service.call_openai_image')
    def test_run_page_image_redraw_worker_records_failure(self, mock_image, settings, tmp_path):
        from vocabulary.views.generation_views import _run_page_image_redraw

        settings.MEDIA_ROOT = str(tmp_path)
        mock_image.side_effect = RuntimeError('provider exploded')
        admin = AdminUserFactory()
        page = self._make_page_with_image(admin)

        _run_page_image_redraw(page.id, 'Built page prompt.', None)

        page.refresh_from_db()
        assert page.generation_status == GraphicNovelPage.GenerationStatus.FAILED
        assert 'provider exploded' in page.generation_error
        assert not page.edited_image

    @patch('vocabulary.views.generation_views.threading.Thread')
    def test_redraw_image_409_when_already_running(self, mock_thread, settings, tmp_path):
        settings.MEDIA_ROOT = str(tmp_path)
        admin = AdminUserFactory()
        page = self._make_page_with_image(admin)
        page.generation_status = GraphicNovelPage.GenerationStatus.RUNNING
        page.save(update_fields=['generation_status'])

        client = _make_client(admin)
        response = client.post(
            f'/api/graphic-novel-pages/{page.id}/redraw-image/',
            format='json',
        )
        assert response.status_code == 409
        mock_thread.return_value.start.assert_not_called()

    def test_redraw_image_404_for_missing_page(self):
        admin = AdminUserFactory()
        client = _make_client(admin)
        response = client.post(
            '/api/graphic-novel-pages/999999/redraw-image/',
            format='json',
        )
        assert response.status_code == 404

    def test_redraw_image_400_when_page_has_no_image(self):
        admin = AdminUserFactory()
        ws = WordSetFactory(creator=admin)
        pack = WordPack.objects.create(word_set=ws, label='Pack 1', order=0)
        novel = GraphicNovel.objects.create(
            pack=pack, title='No Image Novel', synopsis='s',
            style_prompt='art', reading_level=650, is_selected=True,
        )
        page = GraphicNovelPage.objects.create(
            novel=novel, page_number=1, panel_count=1,
        )
        client = _make_client(admin)
        response = client.post(
            f'/api/graphic-novel-pages/{page.id}/redraw-image/',
            format='json',
        )
        assert response.status_code == 400

    def test_student_cannot_redraw_graphic_novel_page_image(self, settings, tmp_path):
        settings.MEDIA_ROOT = str(tmp_path)
        admin = AdminUserFactory()
        page = self._make_page_with_image(admin)
        student = StudentUserFactory()
        client = _make_client(student)
        response = client.post(
            f'/api/graphic-novel-pages/{page.id}/redraw-image/',
            format='json',
        )
        assert response.status_code == 403

    def test_select_edited_without_edited_image_400(self, settings, tmp_path):
        settings.MEDIA_ROOT = str(tmp_path)
        admin = AdminUserFactory()
        page = self._make_page_with_image(admin)
        client = _make_client(admin)
        response = client.post(
            f'/api/graphic-novel-pages/{page.id}/select-image/',
            {'variant': 'edited'}, format='json',
        )
        assert response.status_code == 400

    def test_select_image_rejects_unknown_variant(self, settings, tmp_path):
        settings.MEDIA_ROOT = str(tmp_path)
        admin = AdminUserFactory()
        page = self._make_page_with_image(admin)
        client = _make_client(admin)
        response = client.post(
            f'/api/graphic-novel-pages/{page.id}/select-image/',
            {'variant': 'sideways'}, format='json',
        )
        assert response.status_code == 400

    def test_student_cannot_select_graphic_novel_page_image(self, settings, tmp_path):
        settings.MEDIA_ROOT = str(tmp_path)
        admin = AdminUserFactory()
        page = self._make_page_with_image(admin)
        student = StudentUserFactory()
        client = _make_client(student)
        response = client.post(
            f'/api/graphic-novel-pages/{page.id}/select-image/',
            {'variant': 'original'}, format='json',
        )
        assert response.status_code == 403
