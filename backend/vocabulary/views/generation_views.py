"""
Generation views — Admin-only endpoints for the LLM content pipeline.
These are NEW in v2 (no v1 equivalent).
"""
import threading

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

STALE_JOB_THRESHOLD_SECONDS = 1800

from ..models import (
    GenerationJob, GenerationJobLog, WordSet,
    WordPack, PrimerCardContent, MicroStory, ClozeItem, Question,
    GraphicNovelPage,
)
from ..permissions import IsAdmin
from ..services.generation_pipeline_service import (
    PIPELINE_STEP_ORDER,
    restart_pipeline_from_step,
    restart_graphic_novel_substep,
    run_full_pipeline,
    resume_pipeline,
)


def _immutable_word_set_response():
    return Response(
        {'error': 'Generated Word Sets are immutable. Create a new Word Set to add or change words.'},
        status=status.HTTP_400_BAD_REQUEST,
    )


def _graphic_novel_image_page_statuses(word_set):
    pages = (
        GraphicNovelPage.objects.filter(novel__pack__word_set=word_set)
        .select_related('novel', 'novel__pack')
        .order_by('novel__pack__order', 'novel_id', 'page_number')
    )
    return [
        {
            'id': page.id,
            'pack_id': page.novel.pack_id,
            'pack_label': page.novel.pack.label,
            'novel_id': page.novel_id,
            'novel_title': page.novel.title,
            'page_number': page.page_number,
            'status': page.generation_status,
            'attempts': page.generation_attempts,
            'error_message': page.generation_error,
            'has_image': bool(page.display_image),
            'image_url': page.display_image.url if page.display_image else '',
            'use_edited_image': page.use_edited_image,
            'has_edited_image': page.has_edited_image,
            'is_review_page': page.is_review_page,
            'started_at': page.generation_started_at.isoformat() if page.generation_started_at else None,
            'completed_at': page.generation_completed_at.isoformat() if page.generation_completed_at else None,
        }
        for page in pages
    ]


GRAPHIC_NOVEL_SCRIPT_SUBSTEPS = [
    ('team_selection', 'Team Selection'),
    ('router_premises', 'Router + Premises'),
    ('premise_scoring', 'Premise Scoring'),
    ('cloze_generation', 'Cloze Generation'),
    ('beat_sheet_vocab_roles', 'Beat Sheet + Vocab Roles'),
    ('final_script_self_check', 'Final Script + Self-Check'),
]


def _graphic_novel_script_substep_statuses(job):
    substep_logs = [
        log for log in job.logs.filter(step=GenerationJobLog.Step.GRAPHIC_NOVEL_SCRIPT)
        if isinstance(log.output_data, dict) and log.output_data.get('substep')
    ]
    packs = {}
    for log in substep_logs:
        output_data = log.output_data or {}
        pack_id = output_data.get('pack_id') or 'unknown'
        if pack_id not in packs:
            packs[pack_id] = {
                'pack_id': output_data.get('pack_id'),
                'pack_label': output_data.get('pack_label', 'Pack'),
                'substeps': {
                    key: {
                        'substep': key,
                        'label': label,
                        'status': GenerationJob.Status.PENDING,
                        'duration_seconds': None,
                        'error_message': '',
                        'artifact_path': '',
                        'artifact_name': '',
                        'summary': None,
                        'updated_at': None,
                    }
                    for key, label in GRAPHIC_NOVEL_SCRIPT_SUBSTEPS
                },
            }
        substep = output_data.get('substep')
        if substep not in packs[pack_id]['substeps']:
            packs[pack_id]['substeps'][substep] = {
                'substep': substep,
                'label': output_data.get('substep_label', substep),
                'status': GenerationJob.Status.PENDING,
                'duration_seconds': None,
                'error_message': '',
                'artifact_path': '',
                'artifact_name': '',
                'summary': None,
                'updated_at': None,
            }
        packs[pack_id]['substeps'][substep].update({
            'status': log.status,
            'duration_seconds': log.duration_seconds,
            'error_message': log.error_message,
            'artifact_path': output_data.get('artifact_path', ''),
            'artifact_name': output_data.get('artifact_name', ''),
            'summary': output_data.get('summary'),
            'updated_at': log.created_at.isoformat(),
        })

    return [
        {
            'pack_id': pack_data['pack_id'],
            'pack_label': pack_data['pack_label'],
            'substeps': list(pack_data['substeps'].values()),
        }
        for pack_data in sorted(packs.values(), key=lambda item: str(item['pack_label']))
    ]


class GenerationQueueView(APIView):
    """GET /api/admin/generation-queue/ — List word sets awaiting generation."""
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        queue = WordSet.objects.filter(
            generation_status=WordSet.GenerationStatus.GENERATION_REQUESTED,
        ).select_related('creator', 'requested_by', 'curriculum', 'level').order_by('requested_at')
        data = [
            {
                'id': ws.id,
                'title': ws.title,
                'input_source_title': ws.input_source_title,
                'input_source_chapter': ws.input_source_chapter,
                'curriculum': ws.curriculum.name if ws.curriculum else None,
                'level': ws.level.name if ws.level else None,
                'word_count': len(ws.input_words) if isinstance(ws.input_words, list) else 0,
                'target_lexile': ws.target_lexile,
                'requested_by': ws.requested_by.username if ws.requested_by else None,
                'requested_at': ws.requested_at,
                'creator': ws.creator.username,
            }
            for ws in queue
        ]
        return Response(data)


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

        active_job = word_set.generation_jobs.filter(
            status__in=[GenerationJob.Status.PENDING, GenerationJob.Status.RUNNING],
        ).first()
        if active_job:
            return Response(
                {'error': 'A generation job is already running for this word set.', 'job_id': active_job.id},
                status=status.HTTP_409_CONFLICT,
            )

        if word_set.generation_status == WordSet.GenerationStatus.GENERATED:
            return _immutable_word_set_response()

        if word_set.generation_status == WordSet.GenerationStatus.GENERATING:
            return Response(
                {'error': 'Generation is already in progress for this Word Set.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        words = request.data.get('words', [])
        if not words and word_set.input_words:
            words = word_set.input_words
        if not words:
            return Response(
                {'error': 'Word list is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        words = list(dict.fromkeys(w.strip() for w in words if w.strip()))

        job = GenerationJob.objects.create(
            word_set=word_set,
            created_by=request.user,
            input_words=words,
            input_source_title=request.data.get('source_title', word_set.input_source_title),
            input_source_chapter=request.data.get('source_chapter', word_set.input_source_chapter),
            input_source_text=request.data.get('source_text', word_set.source_text),
            target_lexile=word_set.target_lexile,
            target_language=request.data.get('target_language', 'zh-CN'),
        )

        word_set.generation_status = WordSet.GenerationStatus.GENERATING
        word_set.save(update_fields=['generation_status'])

        # Run pipeline in background thread so the response returns immediately
        thread = threading.Thread(target=run_full_pipeline, args=(job.id,), daemon=True)
        thread.start()

        return Response({
            'job_id': job.id,
            'status': job.status,
            'message': 'Generation job created and pipeline started.',
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

        if job.status in (GenerationJob.Status.RUNNING, GenerationJob.Status.PENDING):
            latest_log = job.logs.order_by('-created_at').first()
            last_activity = latest_log.created_at if latest_log else job.created_at
            if (timezone.now() - last_activity).total_seconds() > STALE_JOB_THRESHOLD_SECONDS:
                GraphicNovelPage.objects.filter(
                    novel__pack__word_set=job.word_set,
                    generation_status=GraphicNovelPage.GenerationStatus.RUNNING,
                ).update(
                    generation_status=GraphicNovelPage.GenerationStatus.FAILED,
                    generation_error='Page image generation stalled after 15 minutes without job activity.',
                    generation_completed_at=timezone.now(),
                )
                job.status = GenerationJob.Status.FAILED
                job.error_message = 'Job stalled — no activity for 15 minutes. You can resume the pipeline.'
                job.save(update_fields=['status', 'error_message'])
                job.word_set.generation_status = WordSet.GenerationStatus.TO_GENERATE
                job.word_set.save(update_fields=['generation_status'])
                GenerationJobLog.objects.create(
                    job=job,
                    step=latest_log.step if latest_log else _next_resume_step(job.last_completed_step),
                    status=GenerationJob.Status.FAILED,
                    error_message=job.error_message,
                    output_data={'message': 'Marked job failed because no activity was recorded for 15 minutes.'},
                )

        graphic_novel_image_pages = _graphic_novel_image_page_statuses(job.word_set)
        graphic_novel_script_substeps = _graphic_novel_script_substep_statuses(job)

        return Response({
            'id': job.id,
            'status': job.status,
            'job_type': job.job_type,
            'word_set_id': job.word_set_id,
            'input_words': job.input_words,
            'last_completed_step': job.last_completed_step,
            'words_created': job.words_created,
            'questions_created': job.questions_created,
            'primer_cards_created': job.primer_cards_created,
            'stories_created': job.stories_created,
            'graphic_novels_created': job.graphic_novels_created,
            'cloze_items_created': job.cloze_items_created,
            'error_message': job.error_message,
            'created_at': job.created_at.isoformat(),
            'completed_at': job.completed_at.isoformat() if job.completed_at else None,
            'graphic_novel_image_pages': graphic_novel_image_pages,
            'graphic_novel_script_substeps': graphic_novel_script_substeps,
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
                'output_data': log.output_data,
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
        for word in words:
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
            'items__word', 'stories', 'graphic_novels__pages', 'cloze_items__word',
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

            graphic_novel = pack.graphic_novels.filter(channel='5page').first()
            graphic_novel_data = None
            if graphic_novel:
                graphic_novel_data = {
                    'id': graphic_novel.id,
                    'title': graphic_novel.title,
                    'synopsis': graphic_novel.synopsis,
                    'reading_level': graphic_novel.reading_level,
                    'pages': [
                        {
                            'id': page.id,
                            'page_number': page.page_number,
                            'image_url': page.display_image.url if page.display_image else '',
                            'original_image_url': page.image.url if page.image else '',
                            'edited_image_url': page.edited_image.url if page.edited_image else '',
                            'has_edited_image': page.has_edited_image,
                            'use_edited_image': page.use_edited_image,
                            'generation_status': page.generation_status,
                            'generation_attempts': page.generation_attempts,
                            'generation_error': page.generation_error,
                            'panel_count': page.panel_count,
                            'layout_description': page.layout_description,
                            'vocab_words': page.vocab_words_used,
                            'is_review_page': page.is_review_page,
                        }
                        for page in graphic_novel.pages.all()
                    ],
                }

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
                'graphic_novel': graphic_novel_data,
                'stories': stories,
                'cloze_items': cloze_items,
            })

        return Response({
            'job_id': job.id,
            'job_status': job.status,
            'word_set_title': job.word_set.title,
            'words': words_data,
            'questions': questions_data,
            'packs': packs_data,
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

        return Response({
            'message': 'Generated content approved.',
        })


class ResumeGenerationJobView(APIView):
    """POST /api/generation-jobs/{id}/resume/ — Resume a failed pipeline."""
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, job_id):
        try:
            with transaction.atomic():
                job = GenerationJob.objects.select_for_update().get(id=job_id)

                if job.status != GenerationJob.Status.FAILED:
                    return Response(
                        {'error': 'Only failed jobs can be resumed.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                resume_from_step = _next_resume_step(job.last_completed_step)
                job.status = GenerationJob.Status.RUNNING
                job.error_message = ''
                job.save(update_fields=['status', 'error_message'])

                GenerationJobLog.objects.create(
                    job=job,
                    step=resume_from_step,
                    status=GenerationJob.Status.RUNNING,
                    output_data={
                        'message': f'Resuming pipeline from after step: {job.last_completed_step or "start"}.',
                    },
                )
        except GenerationJob.DoesNotExist:
            return Response(
                {'error': 'Job not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        thread = threading.Thread(
            target=resume_pipeline, args=(job.id,), daemon=True,
        )
        thread.start()

        return Response({
            'job_id': job.id,
            'status': 'RUNNING',
            'message': f'Resuming pipeline from after step: {job.last_completed_step or "start"}.',
        })


class RestartGenerationStepView(APIView):
    """POST /api/generation-jobs/{id}/restart-step/ - testing-only manual rerun."""
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, job_id):
        step = request.data.get('step')
        include_subsequent = _parse_bool(
            request.data.get('include_subsequent', request.data.get('run_subsequent', True)),
        )

        if step not in PIPELINE_STEP_ORDER:
            return Response(
                {
                    'error': 'Invalid pipeline step.',
                    'valid_steps': PIPELINE_STEP_ORDER,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                job = GenerationJob.objects.select_for_update().get(id=job_id)

                if job.status in (GenerationJob.Status.PENDING, GenerationJob.Status.RUNNING):
                    return Response(
                        {'error': 'A generation job is already running.'},
                        status=status.HTTP_409_CONFLICT,
                    )

                job.status = GenerationJob.Status.RUNNING
                job.error_message = ''
                job.save(update_fields=['status', 'error_message'])

                GenerationJobLog.objects.create(
                    job=job,
                    step=step,
                    status=GenerationJob.Status.RUNNING,
                    output_data={
                        'message': 'Testing restart queued.',
                        'include_subsequent': include_subsequent,
                    },
                )
        except GenerationJob.DoesNotExist:
            return Response(
                {'error': 'Job not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        thread = threading.Thread(
            target=restart_pipeline_from_step,
            args=(job.id, step, include_subsequent),
            daemon=True,
        )
        thread.start()

        return Response({
            'job_id': job.id,
            'status': GenerationJob.Status.RUNNING,
            'step': step,
            'include_subsequent': include_subsequent,
            'message': 'Testing restart started.',
        })


VALID_SUBSTEP_KEYS = {key for key, _ in GRAPHIC_NOVEL_SCRIPT_SUBSTEPS}


class RestartGraphicNovelSubstepView(APIView):
    """POST /api/generation-jobs/{id}/restart-substep/ - restart from a specific graphic novel substep."""
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, job_id):
        pack_id = request.data.get('pack_id')
        substep = request.data.get('substep')

        if not pack_id or not substep:
            return Response(
                {'error': 'Both pack_id and substep are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if substep not in VALID_SUBSTEP_KEYS:
            return Response(
                {'error': f'Invalid substep. Valid: {sorted(VALID_SUBSTEP_KEYS)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                job = GenerationJob.objects.select_for_update().get(id=job_id)

                if job.status in (GenerationJob.Status.PENDING, GenerationJob.Status.RUNNING):
                    return Response(
                        {'error': 'A generation job is already running.'},
                        status=status.HTTP_409_CONFLICT,
                    )

                if not WordPack.objects.filter(id=pack_id, word_set=job.word_set).exists():
                    return Response(
                        {'error': 'Pack not found for this job.'},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                job.status = GenerationJob.Status.RUNNING
                job.error_message = ''
                job.save(update_fields=['status', 'error_message'])

        except GenerationJob.DoesNotExist:
            return Response(
                {'error': 'Job not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        thread = threading.Thread(
            target=restart_graphic_novel_substep,
            args=(job.id, int(pack_id), substep),
            daemon=True,
        )
        thread.start()

        return Response({
            'job_id': job.id,
            'status': GenerationJob.Status.RUNNING,
            'pack_id': pack_id,
            'substep': substep,
            'message': 'Substep restart started.',
        })


def _run_page_image_edit(page_id, edit_prompt, reference_bytes):
    """Background worker: regenerate one page image via OpenAI images.edit.

    Runs in a daemon thread so the request worker is freed during the slow
    (~30-60s) image call. Reads/writes the page via its own DB connection and
    records terminal state on the page (COMPLETED + edited_image, or FAILED +
    generation_error) for the frontend to poll.
    """
    from ..services.generation.helpers import (
        _call_openai_image_releasing_db,
        _close_old_connections_if_safe,
    )
    from ..services.image_utils import png_to_jpeg_bytes

    _close_old_connections_if_safe()
    try:
        try:
            page = (
                GraphicNovelPage.objects
                .select_related('novel', 'novel__pack')
                .get(id=page_id)
            )
        except GraphicNovelPage.DoesNotExist:
            return

        try:
            new_bytes = _call_openai_image_releasing_db(
                edit_prompt, size="1792x1024", reference_image=reference_bytes,
            )
        except Exception as exc:  # noqa: BLE001 - record provider failure for the admin to see
            page.generation_status = GraphicNovelPage.GenerationStatus.FAILED
            page.generation_error = f'Image edit failed: {exc}'
            page.generation_completed_at = timezone.now()
            page.save(update_fields=[
                'generation_status', 'generation_error', 'generation_completed_at',
            ])
            return

        title_slug = ''.join(
            c if c.isalnum() else '_' for c in page.novel.title.lower()
        ).strip('_')[:60] or 'graphic_novel'
        filename = f"{title_slug}_page_{page.page_number}_edited.png"
        # Preserve the original in `image`; the edit lands in `edited_image`.
        page.edited_image.save(filename, ContentFile(new_bytes), save=False)
        # Lightweight JPEG companion for students; best-effort.
        update_fields = [
            'edited_image', 'use_edited_image', 'prompt_used',
            'generation_status', 'generation_error', 'generation_completed_at',
        ]
        try:
            jpeg_bytes = png_to_jpeg_bytes(new_bytes)
            page.edited_image_jpeg.save(
                f"{title_slug}_page_{page.page_number}_edited.jpg",
                ContentFile(jpeg_bytes), save=False,
            )
            update_fields.append('edited_image_jpeg')
        except ValueError:
            pass
        page.use_edited_image = True
        page.prompt_used = f"{page.prompt_used}\n\n[ADMIN EDIT] {edit_prompt}".strip()
        page.generation_status = GraphicNovelPage.GenerationStatus.COMPLETED
        page.generation_error = ''
        page.generation_completed_at = timezone.now()
        page.save(update_fields=update_fields)
    finally:
        _close_old_connections_if_safe()


def _run_page_image_redraw(page_id, prompt, reference_bytes):
    """Background worker: re-run one page's original image generation.

    Unlike an edit (which uses this page's own image + an instruction), a redraw
    replays the exact payload of the original generation attempt — the
    template-built prompt plus the previous page as the continuity reference —
    in the hope a second roll of the dice produces a cleaner image. The result
    lands in `edited_image` and is auto-selected, leaving the original `image`
    intact and reversible via the variant picker. Records terminal state on the
    page for the frontend to poll, mirroring `_run_page_image_edit`.
    """
    from ..services.generation.helpers import (
        _call_openai_image_releasing_db,
        _close_old_connections_if_safe,
    )
    from ..services.image_utils import png_to_jpeg_bytes

    _close_old_connections_if_safe()
    try:
        try:
            page = (
                GraphicNovelPage.objects
                .select_related('novel', 'novel__pack')
                .get(id=page_id)
            )
        except GraphicNovelPage.DoesNotExist:
            return

        try:
            new_bytes = _call_openai_image_releasing_db(
                prompt, size="1792x1024", reference_image=reference_bytes,
            )
        except Exception as exc:  # noqa: BLE001 - record provider failure for the admin to see
            page.generation_status = GraphicNovelPage.GenerationStatus.FAILED
            page.generation_error = f'Image redraw failed: {exc}'
            page.generation_completed_at = timezone.now()
            page.save(update_fields=[
                'generation_status', 'generation_error', 'generation_completed_at',
            ])
            return

        title_slug = ''.join(
            c if c.isalnum() else '_' for c in page.novel.title.lower()
        ).strip('_')[:60] or 'graphic_novel'
        filename = f"{title_slug}_page_{page.page_number}_edited.png"
        # Preserve the original in `image`; the redraw lands in `edited_image`.
        page.edited_image.save(filename, ContentFile(new_bytes), save=False)
        update_fields = [
            'edited_image', 'use_edited_image', 'prompt_used',
            'generation_status', 'generation_error', 'generation_completed_at',
        ]
        try:
            jpeg_bytes = png_to_jpeg_bytes(new_bytes)
            page.edited_image_jpeg.save(
                f"{title_slug}_page_{page.page_number}_edited.jpg",
                ContentFile(jpeg_bytes), save=False,
            )
            update_fields.append('edited_image_jpeg')
        except ValueError:
            pass
        page.use_edited_image = True
        page.prompt_used = f"{page.prompt_used}\n\n[REDRAW] {prompt}".strip()
        page.generation_status = GraphicNovelPage.GenerationStatus.COMPLETED
        page.generation_error = ''
        page.generation_completed_at = timezone.now()
        page.save(update_fields=update_fields)
    finally:
        _close_old_connections_if_safe()


class EditGraphicNovelPageImageView(APIView):
    """
    POST /api/graphic-novel-pages/{page_id}/edit-image/

    Re-generate a single graphic novel page image using the page's current
    image as a visual reference plus an admin-supplied edit instruction.
    Validates synchronously, then runs the slow OpenAI images.edit call in a
    background thread so the request worker is not held for the ~30-60s wait.
    Returns 202 with the page in RUNNING state; the frontend polls
    `image-status/` for the terminal result.
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, page_id):
        edit_prompt = (request.data.get('prompt') or '').strip()
        if not edit_prompt:
            return Response(
                {'error': 'A prompt describing the edit is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            page = (
                GraphicNovelPage.objects
                .select_related('novel', 'novel__pack')
                .get(id=page_id)
            )
        except GraphicNovelPage.DoesNotExist:
            return Response(
                {'error': 'Graphic novel page not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if page.generation_status == GraphicNovelPage.GenerationStatus.RUNNING:
            return Response(
                {'error': 'An image edit is already in progress for this page.'},
                status=status.HTTP_409_CONFLICT,
            )

        if not page.image:
            return Response(
                {'error': 'This page has no image to edit yet. Generate it first.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Edit builds on whatever variant is currently displayed. Read the
        # reference bytes synchronously so an unreadable file fails fast (404)
        # before we spawn a worker.
        source = page.display_image
        try:
            source.open('rb')
            try:
                reference_bytes = source.read()
            finally:
                source.close()
        except (FileNotFoundError, OSError):
            return Response(
                {'error': 'The current image file could not be read from storage.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        page.generation_status = GraphicNovelPage.GenerationStatus.RUNNING
        page.generation_error = ''
        page.generation_attempts = (page.generation_attempts or 0) + 1
        page.generation_started_at = timezone.now()
        page.generation_completed_at = None
        page.save(update_fields=[
            'generation_status', 'generation_error', 'generation_attempts',
            'generation_started_at', 'generation_completed_at',
        ])

        thread = threading.Thread(
            target=_run_page_image_edit,
            args=(page.id, edit_prompt, reference_bytes),
            daemon=True,
        )
        thread.start()

        return Response(
            _graphic_novel_page_image_payload(page, message='Image edit started.'),
            status=status.HTTP_202_ACCEPTED,
        )


class RedrawGraphicNovelPageImageView(APIView):
    """
    POST /api/graphic-novel-pages/{page_id}/redraw-image/

    Re-run the page's original image generation with the exact same payload the
    pipeline used — the template-built prompt plus the previous page as the
    continuity reference. A second attempt on the same prompt sometimes clears
    artifacts in a bad image. Validates + builds the payload synchronously, then
    runs the slow OpenAI call in a background thread (returns 202 + RUNNING;
    frontend polls `image-status/`). The result saves to `edited_image` and is
    auto-selected, so the original is preserved and reversible.
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, page_id):
        from ..services.generation.graphic_novel_images import (
            build_page_image_prompt,
            previous_page_reference_bytes,
        )

        try:
            page = (
                GraphicNovelPage.objects
                .select_related('novel', 'novel__pack')
                .get(id=page_id)
            )
        except GraphicNovelPage.DoesNotExist:
            return Response(
                {'error': 'Graphic novel page not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if page.generation_status == GraphicNovelPage.GenerationStatus.RUNNING:
            return Response(
                {'error': 'An image operation is already in progress for this page.'},
                status=status.HTTP_409_CONFLICT,
            )

        if not page.image:
            return Response(
                {'error': 'This page has no image to redraw yet. Generate it first.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Build the original-generation payload synchronously so any failure
        # surfaces before we spawn a worker.
        prompt = build_page_image_prompt(page)
        reference_bytes = previous_page_reference_bytes(page)

        page.generation_status = GraphicNovelPage.GenerationStatus.RUNNING
        page.generation_error = ''
        page.generation_attempts = (page.generation_attempts or 0) + 1
        page.generation_started_at = timezone.now()
        page.generation_completed_at = None
        page.save(update_fields=[
            'generation_status', 'generation_error', 'generation_attempts',
            'generation_started_at', 'generation_completed_at',
        ])

        thread = threading.Thread(
            target=_run_page_image_redraw,
            args=(page.id, prompt, reference_bytes),
            daemon=True,
        )
        thread.start()

        return Response(
            _graphic_novel_page_image_payload(page, message='Image redraw started.'),
            status=status.HTTP_202_ACCEPTED,
        )


def _graphic_novel_page_image_payload(page, message=None):
    """Serialize a page's image state (both variants + which is active)."""
    payload = {
        'id': page.id,
        'page_number': page.page_number,
        'image_url': page.display_image.url if page.display_image else '',
        'original_image_url': page.image.url if page.image else '',
        'edited_image_url': page.edited_image.url if page.edited_image else '',
        'has_edited_image': page.has_edited_image,
        'use_edited_image': page.use_edited_image,
        'generation_status': page.generation_status,
        'generation_error': page.generation_error,
    }
    if message:
        payload['message'] = message
    return payload


class GraphicNovelPageImageStatusView(APIView):
    """
    GET /api/graphic-novel-pages/{page_id}/image-status/

    Poll target for the async edit-image flow. Returns the page's current
    image state (both variant URLs + which is active + generation_status), so
    the admin UI can detect when a background edit has COMPLETED or FAILED.
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request, page_id):
        try:
            page = (
                GraphicNovelPage.objects
                .select_related('novel')
                .get(id=page_id)
            )
        except GraphicNovelPage.DoesNotExist:
            return Response(
                {'error': 'Graphic novel page not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(_graphic_novel_page_image_payload(page))


class SelectGraphicNovelPageImageView(APIView):
    """
    POST /api/graphic-novel-pages/{page_id}/select-image/  {"variant": "original" | "edited"}

    Choose whether the original or the edited image is the one shown to
    students and in review. Reversible at any time; neither file is deleted.
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, page_id):
        variant = (request.data.get('variant') or '').strip().lower()
        if variant not in ('original', 'edited'):
            return Response(
                {'error': "variant must be 'original' or 'edited'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            page = (
                GraphicNovelPage.objects
                .select_related('novel')
                .get(id=page_id)
            )
        except GraphicNovelPage.DoesNotExist:
            return Response(
                {'error': 'Graphic novel page not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if variant == 'edited' and not page.edited_image:
            return Response(
                {'error': 'This page has no edited image to select.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        page.use_edited_image = (variant == 'edited')
        page.save(update_fields=['use_edited_image'])

        return Response(_graphic_novel_page_image_payload(
            page, message=f'Now displaying the {variant} image.',
        ))


def _next_resume_step(last_completed_step):
    if not last_completed_step:
        return PIPELINE_STEP_ORDER[0]
    try:
        return PIPELINE_STEP_ORDER[PIPELINE_STEP_ORDER.index(last_completed_step) + 1]
    except ValueError:
        return PIPELINE_STEP_ORDER[0]
    except IndexError:
        return PIPELINE_STEP_ORDER[-1]


def _parse_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in ('false', '0', 'no', 'off')
    return bool(value)


class LatestGenerationJobView(APIView):
    """GET /api/word-sets/{id}/latest-job/ — Get most recent job for this word set."""
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request, word_set_id):
        job = GenerationJob.objects.filter(
            word_set_id=word_set_id,
        ).order_by('-created_at').first()

        if not job:
            return Response(
                {'error': 'No generation jobs found for this word set.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response({
            'id': job.id,
            'status': job.status,
            'job_type': job.job_type,
            'input_words': job.input_words,
            'last_completed_step': job.last_completed_step,
            'created_at': job.created_at.isoformat(),
            'completed_at': job.completed_at.isoformat() if job.completed_at else None,
        })


class AddWordsAndGenerateView(APIView):
    """POST /api/word-sets/{id}/add-words/ — Add new words and run pipeline for them only."""
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, word_set_id):
        try:
            word_set = WordSet.objects.get(id=word_set_id)
        except WordSet.DoesNotExist:
            return Response(
                {'error': 'Word set not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        return _immutable_word_set_response()


class WordSetContentView(APIView):
    """GET /api/word-sets/{id}/content/ — All generated content for the entire word set."""
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request, word_set_id):
        try:
            word_set = WordSet.objects.get(id=word_set_id)
        except WordSet.DoesNotExist:
            return Response(
                {'error': 'Word set not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # All words in the word set
        words = word_set.words.prefetch_related('definitions').all()
        words_data = []
        for word in words:
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

        word_ids = [word['id'] for word in words_data]

        # All questions for words in this word set
        questions = Question.objects.filter(
            word_id__in=word_ids,
        ).select_related('word')
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

        # All packs for this word set
        packs = WordPack.objects.filter(
            word_set=word_set,
        ).prefetch_related(
            'items__word', 'stories', 'graphic_novels__pages', 'cloze_items__word',
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

            graphic_novel = pack.graphic_novels.filter(channel='5page').first()
            graphic_novel_data = None
            if graphic_novel:
                graphic_novel_data = {
                    'id': graphic_novel.id,
                    'title': graphic_novel.title,
                    'synopsis': graphic_novel.synopsis,
                    'reading_level': graphic_novel.reading_level,
                    'pages': [
                        {
                            'id': page.id,
                            'page_number': page.page_number,
                            'image_url': page.display_image.url if page.display_image else '',
                            'original_image_url': page.image.url if page.image else '',
                            'edited_image_url': page.edited_image.url if page.edited_image else '',
                            'has_edited_image': page.has_edited_image,
                            'use_edited_image': page.use_edited_image,
                            'generation_status': page.generation_status,
                            'generation_attempts': page.generation_attempts,
                            'generation_error': page.generation_error,
                            'panel_count': page.panel_count,
                            'layout_description': page.layout_description,
                            'vocab_words': page.vocab_words_used,
                            'is_review_page': page.is_review_page,
                        }
                        for page in graphic_novel.pages.all()
                    ],
                }

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
                'graphic_novel': graphic_novel_data,
                'stories': stories,
                'cloze_items': cloze_items,
            })

        return Response({
            'word_set_id': word_set.id,
            'word_set_title': word_set.title,
            'words': words_data,
            'questions': questions_data,
            'packs': packs_data,
        })

    def post(self, request, word_set_id):
        try:
            word_set = WordSet.objects.get(id=word_set_id)
        except WordSet.DoesNotExist:
            return Response(
                {'error': 'Word set not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        return _immutable_word_set_response()
