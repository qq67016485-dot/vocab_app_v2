"""Graphic novel image generation (Step 7B)."""
import logging
import time

from django.core.files.base import ContentFile
from django.utils import timezone

from vocabulary.models import (
    GenerationJob, GenerationJobLog, GraphicNovel, GraphicNovelPage,
)
from vocabulary.services.generation.graphic_novel_helpers import (
    _characters_for_graphic_novel_page,
    _format_character_name_colors,
    _format_characters_for_image_prompt,
    _format_graphic_novel_setting_context,
    _format_panels_as_prose,
    _format_synopsis_for_page,
    _format_vocab_details_for_review,
    _format_vocab_highlighting,
)
from vocabulary.services.generation.helpers import (
    _call_openai_image_releasing_db,
    _log_step,
)
import vocabulary.services.llm_service as _llm_service

logger = logging.getLogger(__name__)


def _step_graphic_novel_images(job, packs):
    """
    Step 7B: Generate one full-page image for each graphic novel page.

    Continues on individual page failures so a later resume can fill gaps.
    """
    _log_step(
        job, GenerationJobLog.Step.GRAPHIC_NOVEL_IMAGES,
        GenerationJob.Status.RUNNING,
        output_data={'message': 'Starting graphic novel image generation'},
    )
    start = time.time()
    template = _llm_service.load_prompt_template('graphic_novel_page')
    review_template = _llm_service.load_prompt_template('graphic_novel_review_page')
    created_count = 0
    pending_count = 0
    skipped_count = 0
    failed_pages = []
    logger.info("Graphic novel image generation started for job %s", job.id)

    pages = list(
        GraphicNovelPage.objects.filter(novel__pack__in=packs, novel__channel='5page')
        .select_related('novel', 'novel__pack')
        .order_by('novel_id', 'page_number')
    )

    if not pages:
        novel_count = GraphicNovel.objects.filter(pack__in=packs, channel='5page').count()
        logger.warning(
            "No graphic novel pages found for job %s (%d packs, %d novels). "
            "The graphic_novel_script step may need to run first.",
            job.id, len(packs), novel_count,
        )
        _log_step(
            job,
            GenerationJobLog.Step.GRAPHIC_NOVEL_IMAGES,
            GenerationJob.Status.FAILED,
            output_data={'pages_created': 0, 'pages_skipped': 0, 'failed_pages': []},
            error_message="No graphic novel pages found for image generation.",
        )
        raise RuntimeError("No graphic novel pages found for image generation.")

    prev_image_bytes = None
    prev_novel_id = None

    for page in pages:
        if page.novel_id != prev_novel_id:
            prev_image_bytes = None
            prev_novel_id = page.novel_id

        if page.image:
            try:
                ref = page.display_image
                prev_image_bytes = ref.read()
                ref.seek(0)
            except (FileNotFoundError, OSError):
                prev_image_bytes = None
            skipped_count += 1
            if page.generation_status != GraphicNovelPage.GenerationStatus.COMPLETED:
                page.generation_status = GraphicNovelPage.GenerationStatus.COMPLETED
                page.generation_error = ''
                page.generation_completed_at = page.generation_completed_at or timezone.now()
                page.save(update_fields=[
                    'generation_status', 'generation_error', 'generation_completed_at',
                ])
            continue
        pending_count += 1
        label = f"{page.novel.pack.label} page {page.page_number}"

        page.generation_status = GraphicNovelPage.GenerationStatus.RUNNING
        page.generation_attempts = (page.generation_attempts or 0) + 1
        page.generation_error = ''
        page.generation_started_at = timezone.now()
        page.generation_completed_at = None
        page.save(update_fields=[
            'generation_status', 'generation_attempts', 'generation_error',
            'generation_started_at', 'generation_completed_at',
        ])
        _log_step(
            job,
            GenerationJobLog.Step.GRAPHIC_NOVEL_IMAGES,
            GenerationJob.Status.RUNNING,
            output_data={
                'message': f'Generating graphic novel image for {label}.',
                'page_id': page.id,
                'pack_label': page.novel.pack.label,
                'novel_title': page.novel.title,
                'page_number': page.page_number,
                'attempt': page.generation_attempts,
            },
        )

        if page.is_review_page:
            characters_text = _format_characters_for_image_prompt(
                _characters_for_graphic_novel_page(page)
            )
            vocab_details = _format_vocab_details_for_review(page)
            prompt = review_template.format(
                style_prompt=page.novel.style_prompt,
                characters=characters_text,
                synopsis=page.novel.synopsis,
                vocab_details=vocab_details,
                setting_context=_format_graphic_novel_setting_context(page),
                review_artifact_type=page.novel.metadata.get('review_artifact_type', 'review spread'),
            )
        else:
            panel_details = _format_panels_as_prose(page.panel_descriptions or [])
            characters_text = _format_characters_for_image_prompt(
                _characters_for_graphic_novel_page(page)
            )
            prompt = template.format(
                title=page.novel.title,
                synopsis=_format_synopsis_for_page(page),
                characters=characters_text,
                style_prompt=page.novel.style_prompt,
                page_number=page.page_number,
                panel_count=page.panel_count,
                layout_description=page.layout_description,
                panel_details=panel_details,
                vocab_highlighting=_format_vocab_highlighting(page),
                setting_context=_format_graphic_novel_setting_context(page),
                character_name_colors=_format_character_name_colors(page),
            )

        try:
            logger.info(
                "Generating graphic novel page image for '%s' page %s",
                page.novel.title, page.page_number,
            )
            image_bytes = _call_openai_image_releasing_db(
                prompt, size="1792x1024", reference_image=prev_image_bytes,
            )
            title_slug = ''.join(
                c if c.isalnum() else '_' for c in page.novel.title.lower()
            ).strip('_')[:60] or 'graphic_novel'
            filename = f"{title_slug}_page_{page.page_number}.png"
            page.image.save(filename, ContentFile(image_bytes), save=False)
            page.prompt_used = prompt
            page.generation_status = GraphicNovelPage.GenerationStatus.COMPLETED
            page.generation_error = ''
            page.generation_completed_at = timezone.now()
            page.save(update_fields=[
                'image', 'prompt_used', 'generation_status',
                'generation_error', 'generation_completed_at',
            ])
            prev_image_bytes = image_bytes
            created_count += 1
            _log_step(
                job,
                GenerationJobLog.Step.GRAPHIC_NOVEL_IMAGES,
                GenerationJob.Status.RUNNING,
                output_data={
                    'message': f'Completed graphic novel image for {label}.',
                    'page_id': page.id,
                    'pack_label': page.novel.pack.label,
                    'novel_title': page.novel.title,
                    'page_number': page.page_number,
                    'attempt': page.generation_attempts,
                    'page_status': page.generation_status,
                },
            )

        except Exception as first_exc:
            logger.warning(
                "Graphic novel image generation failed for %s (attempt %d): %s",
                label, page.generation_attempts, first_exc,
            )
            page.generation_attempts += 1
            page.save(update_fields=['generation_attempts'])
            _log_step(
                job,
                GenerationJobLog.Step.GRAPHIC_NOVEL_IMAGES,
                GenerationJob.Status.RUNNING,
                output_data={
                    'message': f'Retrying graphic novel image for {label} (attempt {page.generation_attempts}).',
                    'page_id': page.id,
                    'page_number': page.page_number,
                    'attempt': page.generation_attempts,
                },
            )

            try:
                image_bytes = _call_openai_image_releasing_db(
                    prompt, size="1792x1024", reference_image=prev_image_bytes,
                )
                title_slug = ''.join(
                    c if c.isalnum() else '_' for c in page.novel.title.lower()
                ).strip('_')[:60] or 'graphic_novel'
                filename = f"{title_slug}_page_{page.page_number}.png"
                page.image.save(filename, ContentFile(image_bytes), save=False)
                page.prompt_used = prompt
                page.generation_status = GraphicNovelPage.GenerationStatus.COMPLETED
                page.generation_error = ''
                page.generation_completed_at = timezone.now()
                page.save(update_fields=[
                    'image', 'prompt_used', 'generation_status',
                    'generation_error', 'generation_completed_at',
                ])
                prev_image_bytes = image_bytes
                created_count += 1
                _log_step(
                    job,
                    GenerationJobLog.Step.GRAPHIC_NOVEL_IMAGES,
                    GenerationJob.Status.RUNNING,
                    output_data={
                        'message': f'Completed graphic novel image for {label} on retry.',
                        'page_id': page.id,
                        'pack_label': page.novel.pack.label,
                        'novel_title': page.novel.title,
                        'page_number': page.page_number,
                        'attempt': page.generation_attempts,
                        'page_status': GraphicNovelPage.GenerationStatus.COMPLETED,
                    },
                )
            except Exception as retry_exc:
                logger.error(
                    "Graphic novel image generation failed for %s on retry: %s",
                    label, retry_exc,
                )
                page.generation_status = GraphicNovelPage.GenerationStatus.FAILED
                page.generation_error = str(retry_exc)
                page.generation_completed_at = timezone.now()
                page.save(update_fields=[
                    'generation_status', 'generation_error', 'generation_completed_at',
                ])
                failed_pages.append(label)
                _log_step(
                    job,
                    GenerationJobLog.Step.GRAPHIC_NOVEL_IMAGES,
                    GenerationJob.Status.RUNNING,
                    output_data={
                        'message': f'Failed graphic novel image for {label} after retry. Stopping.',
                        'page_id': page.id,
                        'pack_label': page.novel.pack.label,
                        'novel_title': page.novel.title,
                        'page_number': page.page_number,
                        'attempt': page.generation_attempts,
                        'page_status': page.generation_status,
                    },
                    error_message=str(retry_exc),
                )
                break

    duration = time.time() - start
    incomplete_pages = [
        f"{page.novel.pack.label} page {page.page_number}"
        for page in GraphicNovelPage.objects.filter(novel__pack__in=packs)
        .select_related('novel', 'novel__pack')
        if page.generation_status != GraphicNovelPage.GenerationStatus.COMPLETED or not page.image
    ]
    if incomplete_pages and not failed_pages:
        failed_pages.extend(incomplete_pages)

    if failed_pages:
        _log_step(
            job, GenerationJobLog.Step.GRAPHIC_NOVEL_IMAGES,
            GenerationJob.Status.FAILED,
            duration=duration,
            output_data={
                'pages_created': created_count,
                'pages_skipped': skipped_count,
                'failed_pages': failed_pages,
            },
            error_message=f"{len(failed_pages)} graphic novel page generation(s) failed.",
        )
        raise RuntimeError(
            f"Graphic novel image generation failed for {len(failed_pages)} page(s)."
        )

    _log_step(
        job, GenerationJobLog.Step.GRAPHIC_NOVEL_IMAGES,
        GenerationJob.Status.COMPLETED,
        duration=duration,
        output_data={
            'pages_created': created_count,
            'pages_skipped': skipped_count,
            'failed_pages': failed_pages,
        },
    )
    logger.info(
        "Graphic novel image generation completed for job %s: %d pages created, %d pages failed",
        job.id, created_count, len(failed_pages),
    )
