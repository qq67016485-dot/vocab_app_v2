"""
Generation views — Admin-only endpoints for the LLM content pipeline.
These are NEW in v2 (no v1 equivalent).
"""
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import (
    GenerationJob, GenerationJobLog, GeneratedImage, WordSet,
    WordPack, PrimerCardContent, MicroStory, ClozeItem,
)
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


class GenerationJobContentView(APIView):
    """GET /api/generation-jobs/{id}/content/ — All generated content for review."""
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request, job_id):
        try:
            job = GenerationJob.objects.select_related('word_set').get(id=job_id)
        except GenerationJob.DoesNotExist:
            return Response(
                {'error': 'Job not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Words created by this job (match input_words against word_set.words)
        input_words_lower = [w.lower() for w in job.input_words]
        words = job.word_set.words.filter(
            text__in=job.input_words,
        ).prefetch_related('definitions').distinct()

        words_data = []
        word_ids = []
        for word in words:
            word_ids.append(word.id)
            definitions = [
                {
                    'id': d.id,
                    'definition_text': d.definition_text,
                    'example_sentence': d.example_sentence,
                    'lexile_score': d.lexile_score,
                }
                for d in word.definitions.all()
            ]
            words_data.append({
                'id': word.id,
                'text': word.text,
                'part_of_speech': word.part_of_speech,
                'definitions': definitions,
            })

        # Questions generated by this job
        questions = job.generated_questions.select_related('word').all()
        questions_data = [
            {
                'id': q.id,
                'word_text': q.word.text,
                'question_type': q.question_type,
                'question_text': q.question_text,
                'options': q.options,
                'correct_answers': q.correct_answers,
                'explanation': q.explanation,
            }
            for q in questions
        ]

        # Packs for this word set
        packs = WordPack.objects.filter(
            word_set=job.word_set,
        ).prefetch_related(
            'items__word', 'stories', 'cloze_items__word',
        ).order_by('order')

        packs_data = []
        for pack in packs:
            pack_words = [
                {'id': item.word.id, 'text': item.word.text}
                for item in pack.items.all()
            ]

            primer_cards = []
            for item in pack.items.select_related('word__primer_content').all():
                pc = getattr(item.word, 'primer_content', None)
                if pc:
                    primer_cards.append({
                        'id': pc.id,
                        'word_text': item.word.text,
                        'syllable_text': pc.syllable_text,
                        'kid_friendly_definition': pc.kid_friendly_definition,
                        'example_sentence': pc.example_sentence,
                    })

            stories = [
                {
                    'id': s.id,
                    'story_text': s.story_text,
                    'reading_level': s.reading_level,
                }
                for s in pack.stories.all()
            ]

            cloze_items = [
                {
                    'id': ci.id,
                    'word_text': ci.word.text,
                    'sentence_text': ci.sentence_text,
                    'correct_answer': ci.correct_answer,
                    'distractors': ci.distractors,
                }
                for ci in pack.cloze_items.all()
            ]

            packs_data.append({
                'id': pack.id,
                'label': pack.label,
                'words': pack_words,
                'primer_cards': primer_cards,
                'stories': stories,
                'cloze_items': cloze_items,
            })

        # Images for words in this job
        images = GeneratedImage.objects.filter(
            word_id__in=word_ids,
        ).select_related('word')
        images_data = [
            {
                'id': img.id,
                'word_text': img.word.text,
                'image_url': img.image_url,
                'status': img.status,
            }
            for img in images
        ]

        return Response({
            'job_id': job.id,
            'job_status': job.status,
            'word_set_title': job.word_set.title,
            'words': words_data,
            'questions': questions_data,
            'packs': packs_data,
            'images': images_data,
        })


class ApproveGenerationJobView(APIView):
    """POST /api/generation-jobs/{id}/approve/ — Approve all generated content."""
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, job_id):
        try:
            job = GenerationJob.objects.get(id=job_id)
        except GenerationJob.DoesNotExist:
            return Response(
                {'error': 'Job not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if job.status not in (
            GenerationJob.Status.COMPLETED,
            GenerationJob.Status.PARTIALLY_COMPLETED,
        ):
            return Response(
                {'error': 'Job must be completed before approval.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Approve all pending images for words in this job
        word_ids = list(
            job.word_set.words.filter(text__in=job.input_words).values_list('id', flat=True)
        )
        approved_count = GeneratedImage.objects.filter(
            word_id__in=word_ids,
            status=GeneratedImage.Status.PENDING_REVIEW,
        ).update(status=GeneratedImage.Status.APPROVED)

        return Response({
            'message': 'Generation job approved.',
            'images_approved': approved_count,
        })
