"""
Teacher views — adapted from v1 with updated FK paths.

Changes from v1:
- WordMeaning → Word
- meaning → word FK path
- ImportValidation/Finalization removed (replaced by generation pipeline)
- Role checks allow ADMIN in addition to TEACHER
- ContentGenerationService calls removed from pack actions (generation is admin-only now)
"""
from datetime import date, timedelta

from django.db import transaction
from django.db.models import Q
from rest_framework import viewsets, status, serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import action

from users.models import CustomUser, StudentGroup
from ..models import (
    Curriculum, Level, WordSet, Word, WordDefinition,
    UserWordProgress, MasteryLevel, WordPack, WordPackItem,
    PrimerCardContent, GeneratedImage,
)
from ..serializers import (
    CurriculumSerializer, LevelSerializer, WordSetSerializer,
    WordSetDetailSerializer, WordSetFormSerializer,
    TeacherStudentSerializer, StudentCreateUpdateSerializer, WordSerializer,
)
from ..permissions import IsTeacherOrAdmin
from ..services.assignment_service import AssignmentService


def _can_edit_word_set(user, word_set):
    """Return True if the user owns the word set or is an admin."""
    return word_set.creator == user or user.role == CustomUser.Role.ADMIN


class TeacherStudentViewSet(viewsets.ModelViewSet):
    serializer_class = StudentCreateUpdateSerializer
    permission_classes = [IsAuthenticated, IsTeacherOrAdmin]

    def get_queryset(self):
        user = self.request.user
        if user.role in (CustomUser.Role.TEACHER, CustomUser.Role.ADMIN):
            return user.students.all().order_by('username')
        return CustomUser.objects.none()

    def perform_create(self, serializer):
        teacher = self.request.user
        student = serializer.save(role=CustomUser.Role.STUDENT)
        teacher.students.add(student)

        group_id = self.request.data.get('group_id')
        if group_id:
            try:
                group = teacher.student_groups.get(id=group_id)
                group.students.add(student)
            except StudentGroup.DoesNotExist:
                pass


class WordViewSet(viewsets.ReadOnlyModelViewSet):
    """Lists words visible to the current user (teacher sees students' words)."""
    permission_classes = [IsAuthenticated]
    serializer_class = WordSerializer

    def get_queryset(self):
        user = self.request.user
        base_qs = Word.objects.prefetch_related('definitions')
        if user.role in (CustomUser.Role.TEACHER, CustomUser.Role.ADMIN):
            student_ids = user.students.values_list('id', flat=True)
            return base_qs.filter(
                user_progress__user_id__in=student_ids,
            ).distinct().order_by('-created_at')
        return base_qs.filter(
            user_progress__user=user,
        ).order_by('-created_at')


class CurriculumViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Curriculum.objects.all().order_by('name')
    serializer_class = CurriculumSerializer
    permission_classes = [IsAuthenticated]


class LevelViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Level.objects.all()
    serializer_class = LevelSerializer
    permission_classes = [IsAuthenticated]


class WordSetViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsTeacherOrAdmin]

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return WordSetDetailSerializer
        if self.action in ['create', 'update', 'partial_update']:
            return WordSetFormSerializer
        return WordSetSerializer

    def get_queryset(self):
        user = self.request.user
        if user.role == CustomUser.Role.ADMIN:
            return WordSet.objects.all().order_by('-created_at')
        return WordSet.objects.filter(
            Q(creator=user) | Q(is_public=True),
        ).distinct().order_by('-created_at')

    def perform_create(self, serializer):
        instance = serializer.save(creator=self.request.user)
        if instance.input_words:
            instance.generation_status = WordSet.GenerationStatus.TO_GENERATE
            instance.save(update_fields=['generation_status'])

    def perform_update(self, serializer):
        if not _can_edit_word_set(self.request.user, serializer.instance):
            raise serializers.ValidationError(
                "You do not have permission to edit this Word Set.",
            )
        instance = serializer.save()
        if instance.input_words and instance.generation_status == WordSet.GenerationStatus.DRAFT:
            instance.generation_status = WordSet.GenerationStatus.TO_GENERATE
            instance.save(update_fields=['generation_status'])

    def perform_destroy(self, instance):
        if not _can_edit_word_set(self.request.user, instance):
            raise serializers.ValidationError(
                "You do not have permission to delete this Word Set.",
            )
        instance.delete()

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def assign(self, request, pk=None):
        word_set = self.get_object()
        student_ids = request.data.get('student_ids', [])
        group_ids = request.data.get('group_ids', [])

        try:
            count, students = AssignmentService.assign_word_set(
                request.user, word_set, student_ids, group_ids,
            )
            if count == 0 and not students.exists():
                return Response({
                    'message': 'This Word Set is empty. No words were assigned.',
                })
            student_names = ", ".join(s.username for s in students)
            return Response({
                'success': f"Assigned '{word_set.title}' to {count} student(s): {student_names}.",
            })
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def add_word(self, request, pk=None):
        word_set = self.get_object()
        word_id = request.data.get('word_id')
        if not _can_edit_word_set(request.user, word_set):
            return Response(
                {'error': 'You do not have permission to edit this Word Set.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            word = Word.objects.get(id=word_id)
            word_set.words.add(word)
            return Response({
                'success': f"Added '{word.text}' to '{word_set.title}'.",
            })
        except Word.DoesNotExist:
            return Response(
                {'error': 'Word not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

    @action(detail=True, methods=['post'])
    def remove_word(self, request, pk=None):
        word_set = self.get_object()
        word_id = request.data.get('word_id')
        if not _can_edit_word_set(request.user, word_set):
            return Response(
                {'error': 'You do not have permission to edit this Word Set.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            word = Word.objects.get(id=word_id)
            word_set.words.remove(word)
            return Response({
                'success': f"Removed '{word.text}' from '{word_set.title}'.",
            })
        except Word.DoesNotExist:
            return Response(
                {'error': 'Word not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

    # --- Pack Management Actions ---

    @action(detail=True, methods=['get', 'post'], url_path='packs')
    def packs(self, request, pk=None):
        word_set = self.get_object()
        if not _can_edit_word_set(request.user, word_set):
            return Response(
                {'error': 'Permission denied.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if request.method == 'GET':
            packs = word_set.packs.prefetch_related('items__word').all()
            data = []
            for pack in packs:
                words = [
                    {
                        'id': item.word.id,
                        'term_text': item.word.text,
                        'order': item.order,
                    }
                    for item in pack.items.all()
                ]
                data.append({
                    'id': pack.id,
                    'label': pack.label,
                    'order': pack.order,
                    'word_count': len(words),
                    'words': words,
                })
            return Response(data)

        # POST: create a new pack
        label = request.data.get('label', '').strip()
        word_ids = request.data.get('word_ids', [])
        if not label:
            return Response(
                {'error': 'Pack label is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        max_order = word_set.packs.count()
        pack = WordPack.objects.create(
            word_set=word_set, label=label, order=max_order,
        )
        for i, wid in enumerate(word_ids[:9]):
            try:
                word = Word.objects.get(id=wid)
                WordPackItem.objects.create(pack=pack, word=word, order=i)
            except Word.DoesNotExist:
                pass
        return Response(
            {'id': pack.id, 'label': pack.label, 'order': pack.order},
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True, methods=['patch', 'delete'],
        url_path='packs/(?P<pack_id>[^/.]+)',
    )
    def pack_detail(self, request, pk=None, pack_id=None):
        word_set = self.get_object()
        if not _can_edit_word_set(request.user, word_set):
            return Response(
                {'error': 'Permission denied.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            pack = word_set.packs.get(id=pack_id)
        except WordPack.DoesNotExist:
            return Response(
                {'error': 'Pack not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if request.method == 'DELETE':
            pack.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        if 'label' in request.data:
            pack.label = request.data['label']
        if 'order' in request.data:
            pack.order = request.data['order']
        pack.save()

        if 'word_ids' in request.data:
            pack.items.all().delete()
            for i, wid in enumerate(request.data['word_ids'][:9]):
                try:
                    word = Word.objects.get(id=wid)
                    WordPackItem.objects.create(pack=pack, word=word, order=i)
                except Word.DoesNotExist:
                    pass

        return Response({'id': pack.id, 'label': pack.label, 'order': pack.order})

    @action(
        detail=True, methods=['get'],
        url_path='packs/(?P<pack_id>[^/.]+)/images',
    )
    def pack_images(self, request, pk=None, pack_id=None):
        word_set = self.get_object()
        if not _can_edit_word_set(request.user, word_set):
            return Response(
                {'error': 'Permission denied.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            pack = word_set.packs.prefetch_related('items__word').get(id=pack_id)
        except WordPack.DoesNotExist:
            return Response(
                {'error': 'Pack not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        word_ids = pack.items.values_list('word_id', flat=True)
        images = GeneratedImage.objects.filter(
            word_id__in=word_ids,
        ).select_related('word').order_by('-created_at')

        data = [
            {
                'id': img.id,
                'word_id': img.word_id,
                'term': img.word.text,
                'image_url': img.image.url if img.image else '',
                'status': img.status,
                'created_at': img.created_at.isoformat(),
            }
            for img in images
        ]
        return Response(data)


class TeacherStudentDetailView(APIView):
    permission_classes = [IsAuthenticated, IsTeacherOrAdmin]

    def patch(self, request, student_id, *args, **kwargs):
        teacher = request.user
        try:
            student = teacher.students.get(id=student_id)
        except CustomUser.DoesNotExist:
            return Response(
                {'error': 'Student not found or not assigned to you.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = StudentCreateUpdateSerializer(
            student, data=request.data, partial=True,
        )
        if serializer.is_valid():
            updated_student = serializer.save()
            response_serializer = TeacherStudentSerializer(updated_student)
            return Response(response_serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class BulkCreateStudentsView(APIView):
    permission_classes = [IsAuthenticated, IsTeacherOrAdmin]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        students_data = request.data
        if not isinstance(students_data, list):
            return Response(
                {'error': 'Request body must be a list of student objects.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        report = {'success_count': 0, 'errors': []}
        all_usernames = [s.get('username', '').strip() for s in students_data]

        if len(all_usernames) != len(set(all_usernames)):
            return Response(
                {'error': 'The provided list contains duplicate usernames.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        existing = CustomUser.objects.filter(
            username__in=all_usernames,
        ).values_list('username', flat=True)
        if existing:
            return Response(
                {'error': f"Usernames already exist: {', '.join(existing)}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        teacher = request.user
        for i, student_data in enumerate(students_data, 1):
            username = student_data.get('username', '').strip()
            password = student_data.get('password', '').strip()
            group_name = student_data.get('group_name', '').strip()

            if not username or not password:
                report['errors'].append(f"Row {i}: Missing username or password.")
                continue

            student = CustomUser.objects.create_user(
                username=username, password=password,
                role=CustomUser.Role.STUDENT,
            )
            teacher.students.add(student)

            if group_name:
                group, _ = StudentGroup.objects.get_or_create(
                    name=group_name, teacher=teacher,
                )
                group.students.add(student)

            report['success_count'] += 1

        if report['errors']:
            transaction.set_rollback(True)
            return Response(report, status=status.HTTP_400_BAD_REQUEST)

        return Response(report, status=status.HTTP_201_CREATED)
