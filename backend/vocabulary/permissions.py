from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    """Only users with ADMIN role."""
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == 'ADMIN'
        )


class IsTeacherOrAdmin(BasePermission):
    """Users with TEACHER or ADMIN role."""
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role in ('TEACHER', 'ADMIN')
        )


class IsStudent(BasePermission):
    """Only users with STUDENT role."""
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == 'STUDENT'
        )
