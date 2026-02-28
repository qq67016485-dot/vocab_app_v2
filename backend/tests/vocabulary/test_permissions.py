import pytest
from unittest.mock import MagicMock
from vocabulary.permissions import IsAdmin, IsTeacherOrAdmin, IsStudent
from tests.factories import AdminUserFactory, TeacherUserFactory, StudentUserFactory


def _make_request(user):
    """Create a mock request with the given user."""
    request = MagicMock()
    request.user = user
    return request


@pytest.mark.django_db
class TestIsAdmin:
    def setup_method(self):
        self.permission = IsAdmin()
        self.view = MagicMock()

    def test_admin_allowed(self):
        request = _make_request(AdminUserFactory())
        assert self.permission.has_permission(request, self.view) is True

    def test_teacher_denied(self):
        request = _make_request(TeacherUserFactory())
        assert self.permission.has_permission(request, self.view) is False

    def test_student_denied(self):
        request = _make_request(StudentUserFactory())
        assert self.permission.has_permission(request, self.view) is False

    def test_anonymous_denied(self):
        request = MagicMock()
        request.user.is_authenticated = False
        assert self.permission.has_permission(request, self.view) is False


@pytest.mark.django_db
class TestIsTeacherOrAdmin:
    def setup_method(self):
        self.permission = IsTeacherOrAdmin()
        self.view = MagicMock()

    def test_admin_allowed(self):
        request = _make_request(AdminUserFactory())
        assert self.permission.has_permission(request, self.view) is True

    def test_teacher_allowed(self):
        request = _make_request(TeacherUserFactory())
        assert self.permission.has_permission(request, self.view) is True

    def test_student_denied(self):
        request = _make_request(StudentUserFactory())
        assert self.permission.has_permission(request, self.view) is False

    def test_anonymous_denied(self):
        request = MagicMock()
        request.user.is_authenticated = False
        assert self.permission.has_permission(request, self.view) is False


@pytest.mark.django_db
class TestIsStudent:
    def setup_method(self):
        self.permission = IsStudent()
        self.view = MagicMock()

    def test_student_allowed(self):
        request = _make_request(StudentUserFactory())
        assert self.permission.has_permission(request, self.view) is True

    def test_admin_denied(self):
        request = _make_request(AdminUserFactory())
        assert self.permission.has_permission(request, self.view) is False

    def test_teacher_denied(self):
        request = _make_request(TeacherUserFactory())
        assert self.permission.has_permission(request, self.view) is False

    def test_anonymous_denied(self):
        request = MagicMock()
        request.user.is_authenticated = False
        assert self.permission.has_permission(request, self.view) is False
