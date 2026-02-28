"""
Generation views — Admin-only endpoints for the LLM content pipeline.
These are NEW in v2 (no v1 equivalent).
"""
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import GenerationJob, GenerationJobLog, WordSet
from ..permissions import IsAdmin


class TriggerGenerationView(APIView):
    """POST /api/word-sets/{id}/generate/ — Start full pipeline."""
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, word_set_id):
        try:
            word_set = WordSet.objects.get(id=word_set_id)
        except WordSet.DoesNotExist:
            return Response(
                {'error': 'Word set not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        words = request.data.get('words', [])
        if not words:
            return Response(
                {'error': 'Word list is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        job = GenerationJob.objects.create(
            word_set=word_set,
            created_by=request.user,
            input_words=words,
            input_source_title=request.data.get('source_title', ''),
            input_source_chapter=request.data.get('source_chapter', ''),
            input_source_text=request.data.get('source_text', ''),
            target_lexile=request.data.get('target_lexile', 650),
            target_language=request.data.get('target_language', 'zh-CN'),
        )

        return Response({
            'job_id': job.id,
            'status': job.status,
            'message': 'Generation job created.',
        }, status=status.HTTP_201_CREATED)


class GenerationJobStatusView(APIView):
    """GET /api/generation-jobs/{id}/ — Job status + summary."""
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request, job_id):
        try:
            job = GenerationJob.objects.get(id=job_id)
        except GenerationJob.DoesNotExist:
            return Response(
                {'error': 'Job not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response({
            'id': job.id,
            'status': job.status,
            'job_type': job.job_type,
            'word_set_id': job.word_set_id,
            'input_words': job.input_words,
            'words_created': job.words_created,
            'questions_created': job.questions_created,
            'primer_cards_created': job.primer_cards_created,
            'stories_created': job.stories_created,
            'cloze_items_created': job.cloze_items_created,
            'images_created': job.images_created,
            'error_message': job.error_message,
            'created_at': job.created_at.isoformat(),
            'completed_at': job.completed_at.isoformat() if job.completed_at else None,
        })


class GenerationJobLogsView(APIView):
    """GET /api/generation-jobs/{id}/logs/ — Step-by-step logs."""
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request, job_id):
        try:
            job = GenerationJob.objects.get(id=job_id)
        except GenerationJob.DoesNotExist:
            return Response(
                {'error': 'Job not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        logs = job.logs.all().order_by('created_at')
        data = [
            {
                'id': log.id,
                'step': log.step,
                'status': log.status,
                'error_message': log.error_message,
                'duration_seconds': log.duration_seconds,
                'created_at': log.created_at.isoformat(),
            }
            for log in logs
        ]
        return Response(data)
