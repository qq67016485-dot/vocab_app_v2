"""
Instructional views — adapted from v1 with updated FK paths.
Delegates to InstructionalService for pack data and completion.
"""
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..services.instructional_service import InstructionalService
from ..models import StudentWordSetAssignment, WordPack, StudentPackCompletion


class StudentAssignedSetsView(APIView):
    """List assigned word sets with pack progress for the current student."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        student = request.user
        assignments = StudentWordSetAssignment.objects.filter(
            user=student,
        ).select_related(
            'word_set__curriculum', 'word_set__level',
        ).prefetch_related(
            'word_set__packs__items',
            'word_set__words',
        ).order_by('-assigned_at')

        completed_pack_ids = set(
            StudentPackCompletion.objects.filter(
                user=student,
            ).values_list('pack_id', flat=True)
        )

        result = []
        for assignment in assignments:
            ws = assignment.word_set
            packs_data = [
                {
                    'pack_id': pack.id,
                    'label': pack.label,
                    'word_count': pack.items.count(),
                    'is_completed': pack.id in completed_pack_ids,
                }
                for pack in ws.packs.all()
            ]
            result.append({
                'set_id': ws.id,
                'title': ws.title,
                'curriculum': ws.curriculum.name if ws.curriculum else None,
                'level': ws.level.name if ws.level else None,
                'total_words': ws.words.count(),
                'packs': packs_data,
            })

        return Response(result)


class InstructionalPackView(APIView):
    """Full pack data for the instructional flow."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pack_id):
        try:
            data = InstructionalService.get_pack_data(request.user, pack_id)
            return Response(data)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_404_NOT_FOUND)
        except PermissionError as e:
            return Response({'error': str(e)}, status=status.HTTP_403_FORBIDDEN)


class CompletePackView(APIView):
    """Mark pack done, flip words to READY."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pack_id):
        try:
            InstructionalService.complete_pack(request.user, pack_id)
            return Response({'success': 'Pack completed successfully.'})
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_404_NOT_FOUND)
        except PermissionError as e:
            return Response({'error': str(e)}, status=status.HTTP_403_FORBIDDEN)
