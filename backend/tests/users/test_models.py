import pytest
from users.models import CustomUser, StudentGroup
from tests.factories import (
    AdminUserFactory, TeacherUserFactory, StudentUserFactory,
    StudentGroupFactory,
)


@pytest.mark.django_db
class TestCustomUser:
    def test_create_admin(self):
        user = AdminUserFactory()
        assert user.role == CustomUser.Role.ADMIN
        assert user.get_role_display() == 'Admin'
        assert user.native_language == 'zh-CN'

    def test_create_teacher(self):
        user = TeacherUserFactory()
        assert user.role == CustomUser.Role.TEACHER
        assert user.get_role_display() == 'Teacher'

    def test_create_student(self):
        user = StudentUserFactory()
        assert user.role == CustomUser.Role.STUDENT
        assert user.get_role_display() == 'Student'

    def test_default_role_is_student(self):
        user = CustomUser.objects.create_user(username='default_user', password='pass')
        assert user.role == CustomUser.Role.STUDENT

    def test_native_language_default(self):
        user = CustomUser.objects.create_user(username='lang_user', password='pass')
        assert user.native_language == 'zh-CN'

    def test_native_language_choices(self):
        user = StudentUserFactory(native_language='ja')
        assert user.native_language == 'ja'

    def test_str_representation(self):
        user = AdminUserFactory(username='testadmin')
        assert str(user) == 'testadmin (Admin)'

    def test_teacher_student_relationship(self):
        teacher = TeacherUserFactory()
        student = StudentUserFactory()
        teacher.students.add(student)
        assert student in teacher.students.all()
        assert teacher in student.teachers.all()

    def test_default_xp_and_level(self):
        user = StudentUserFactory()
        assert user.xp_points == 0
        assert user.level == 1

    def test_default_streak_values(self):
        user = StudentUserFactory()
        assert user.current_practice_streak == 0
        assert user.last_practice_date is None
        assert user.streak_freezes_available == 2

    def test_default_lexile_range(self):
        user = StudentUserFactory()
        assert user.lexile_min == 0
        assert user.lexile_max == 2000

    def test_three_roles_exist(self):
        roles = [choice[0] for choice in CustomUser.Role.choices]
        assert 'ADMIN' in roles
        assert 'TEACHER' in roles
        assert 'STUDENT' in roles
        assert len(roles) == 3


@pytest.mark.django_db
class TestStudentGroup:
    def test_create_group(self):
        group = StudentGroupFactory()
        assert group.name.startswith('Group')
        assert group.teacher.role in (CustomUser.Role.TEACHER, CustomUser.Role.ADMIN)

    def test_add_students(self):
        group = StudentGroupFactory()
        s1 = StudentUserFactory()
        s2 = StudentUserFactory()
        group.students.add(s1, s2)
        assert group.students.count() == 2

    def test_unique_name_per_teacher(self):
        teacher = TeacherUserFactory()
        StudentGroupFactory(name='Group A', teacher=teacher)
        with pytest.raises(Exception):
            StudentGroupFactory(name='Group A', teacher=teacher)

    def test_str_representation(self):
        teacher = TeacherUserFactory(username='mr_smith')
        group = StudentGroupFactory(name='Class 1', teacher=teacher)
        assert str(group) == "'Class 1' (Teacher: mr_smith)"
