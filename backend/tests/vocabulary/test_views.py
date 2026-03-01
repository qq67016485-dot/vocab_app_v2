"""
RED tests for v2 API views.
Tests written BEFORE implementation — all should fail initially.
"""
import pytest
from datetime import date, timedelta
from django.test import override_settings
from rest_framework.test import APIClient

from users.models import CustomUser, StudentGroup
from vocabulary.models import (
    Word, WordDefinition, Question, WordSet, MasteryLevel,
    UserWordProgress, UserAnswer, WordPack, WordPackItem,
    PrimerCardContent, MicroStory, ClozeItem, GeneratedImage,
    StudentWordSetAssignment, StudentPackCompletion,
    GenerationJob, GenerationJobLog, Curriculum, Level,
)
from tests.factories import (
    AdminUserFactory, TeacherUserFactory, StudentUserFactory,
    WordFactory, WordDefinitionFactory, WordSetFactory,
    QuestionFactory, MasteryLevelFactory, WordPackFactory,
    WordPackItemFactory, PrimerCardContentFactory, MicroStoryFactory,
    ClozeItemFactory, StudentGroupFactory, CurriculumFactory, LevelFactory,
    GenerationJobFactory,
)


def _seed_mastery_levels():
    levels = [
        (1, 'Novice', 0, 2),
        (2, 'Familiar', 1, 4),
        (3, 'Confident', 3, 7),
        (4, 'Proficient', 7, 10),
        (5, 'Mastered', 14, 999),
    ]
    for lid, name, interval, pts in levels:
        MasteryLevel.objects.get_or_create(
            level_id=lid,
            defaults={'level_name': name, 'interval_days': interval, 'points_to_promote': pts},
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
            level=level1, next_review_date=date.today(),
        )

    def test_returns_question(self):
        response = self.client.get('/api/practice/next/')
        assert response.status_code == 200
        assert 'question_text' in response.data
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
        progress.next_review_date = date.today() + timedelta(days=7)
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
            level=level1, next_review_date=date.today(),
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


@pytest.mark.django_db
class TestWordsByLevelView:
    def test_returns_words_at_level(self):
        _seed_mastery_levels()
        student = StudentUserFactory()
        word = WordFactory(text='bright')
        WordDefinitionFactory(word=word)
        level1 = MasteryLevel.objects.get(level_id=1)
        UserWordProgress.objects.create(
            user=student, word=word,
            level=level1, next_review_date=date.today(),
        )
        client = _make_client(student)
        response = client.get('/api/student/words-by-level/1/')
        assert response.status_code == 200
        assert len(response.data) == 1
        assert response.data[0]['text'] == 'bright'


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
            level=level1, next_review_date=date.today(),
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

    def test_remove_word(self):
        self.ws.words.add(self.word)
        response = self.client.post(f'/api/word-sets/{self.ws.id}/remove_word/', {
            'word_id': self.word.id,
        })
        assert response.status_code == 200
        assert not self.ws.words.filter(id=self.word.id).exists()


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

    def test_pack_images(self):
        pack = WordPackFactory(word_set=self.ws)
        WordPackItem.objects.create(pack=pack, word=self.word, order=0)
        GeneratedImage.objects.create(
            word=self.word,
            image_url='https://example.com/img.png',
            prompt_used='test prompt',
        )
        response = self.client.get(
            f'/api/word-sets/{self.ws.id}/packs/{pack.id}/images/',
        )
        assert response.status_code == 200
        assert len(response.data) >= 1


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
            level=level1, next_review_date=date.today(),
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

    def test_student_cannot_access_jobs(self):
        student = StudentUserFactory()
        client = _make_client(student)
        response = client.get('/api/generation-jobs/1/')
        assert response.status_code == 403
