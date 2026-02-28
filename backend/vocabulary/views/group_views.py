"""
Student group views — adapted from v1 with updated role checks.
ADMIN role now also has access in addition to TEACHER.
"""
from rest_framework import viewsets, permissions

from users.models import StudentGroup, CustomUser
from ..serializers import StudentGroupSerializer, StudentGroupFormSerializer


class IsTeacherOwner(permissions.BasePermission):
    """Object-level permission: only the group's teacher can interact with it."""
    def has_object_permission(self, request, view, obj):
        return obj.teacher == request.user


class StudentGroupViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsTeacherOwner]

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return StudentGroupFormSerializer
        return StudentGroupSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated and user.role in (
            CustomUser.Role.TEACHER, CustomUser.Role.ADMIN,
        ):
            return StudentGroup.objects.filter(
                teacher=user,
            ).prefetch_related('students')
        return StudentGroup.objects.none()

    def get_serializer(self, *args, **kwargs):
        serializer_class = self.get_serializer_class()
        kwargs['context'] = self.get_serializer_context()

        if serializer_class == StudentGroupFormSerializer:
            serializer_instance = serializer_class(*args, **kwargs)
            serializer_instance.fields['students'].queryset = (
                self.request.user.students.all()
            )
            return serializer_instance

        return serializer_class(*args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(teacher=self.request.user)
