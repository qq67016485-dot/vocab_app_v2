"""Pipeline orchestrator: run, resume, and restart the generation pipeline."""
import logging

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from vocabulary.models import (
    Word, WordDefinition, Translation,
    Question, WordPack, WordPackItem, PrimerCardContent,
    GraphicNovel, GraphicNovelPage, ClozeItem, Infographic,
    WordSet, GenerationJob, GenerationJobLog,
)
from vocabulary.services.generation.constants import (
    GRAPHIC_NOVEL_IMAGE_MODEL, INFOGRAPHIC_IMAGE_MODEL, PIPELINE_STEP_ORDER,
    CONTENT_TYPE_GRAPHIC_NOVEL, CONTENT_TYPE_INFOGRAPHIC,
    job_generates_content_type,
)
from vocabulary.services.generation.helpers import (
    _log_step, _close_old_connections_if_safe,
)
from vocabulary.services.generation.llm_config_service import get_step_config
from vocabulary.services.generation.step_word_lookup import (
    _step_word_lookup, _step_dedup_and_persist,
    _latest_dedup_word_snapshots, _latest_word_lookup_snapshot,
    _snapshots_to_words_data,
)
from vocabulary.services.generation.step_translations import _step_generate_translations
from vocabulary.services.generation.step_questions import _step_generate_questions
from vocabulary.services.generation.step_sentence_write import _step_generate_sentence_write
from vocabulary.services.generation.step_packs import (
    _step_auto_create_packs, _step_generate_primers,
)
from vocabulary.services.generation.step_graphic_novel import (
    _step_graphic_novel_script, _step_graphic_novel_images,
    restart_graphic_novel_from_substep,
)
from vocabulary.services.generation.step_infographic import (
    _step_infographic_design, _step_infographic_image,
    restart_infographic_from_substep,
)

logger = logging.getLogger(__name__)


def _validate_pipeline_step(step):
    if step not in PIPELINE_STEP_ORDER:
        valid_steps = ', '.join(PIPELINE_STEP_ORDER)
        raise ValueError(f"Unknown pipeline step '{step}'. Valid steps: {valid_steps}")


def _reconstruct_context(job):
    """Rebuild intermediate state from DB for resuming a failed pipeline."""
    words = list(job.word_set.words.filter(text__in=job.input_words).distinct())
    snapshots = _latest_dedup_word_snapshots(job)
    if snapshots:
        words_data = _snapshots_to_words_data(snapshots)
    else:
        # Dedup never completed — fall back to the WORD_LOOKUP log so all
        # original words are available when dedup re-runs on resume.
        lookup_snapshot = _latest_word_lookup_snapshot(job)
        if lookup_snapshot:
            words_data = _snapshots_to_words_data(lookup_snapshot)
        else:
            words_data = []
            for w in words:
                defn = w.definitions.first()
                words_data.append({
                    'term': w.text,
                    'part_of_speech': w.part_of_speech,
                    'definition': defn.definition_text if defn else '',
                    'example_sentence': defn.example_sentence if defn else '',
                })
    packs = list(
        WordPack.objects.filter(word_set=job.word_set)
        .prefetch_related('items__word')
        .order_by('order')
    )
    return words, words_data, packs



def _clear_testing_outputs_for_step(job, step, words):
    """Remove generated artifacts for a step before a manual testing rerun."""
    S = GenerationJobLog.Step
    word_ids = [word.id for word in words]

    if step == S.DEDUP:
        job.word_set.words.clear()
        job.words_created = 0
        job.save(update_fields=['words_created'])

    elif step == S.TRANSLATION and word_ids:
        definition_ids = WordDefinition.objects.filter(
            word_id__in=word_ids,
        ).values_list('id', flat=True)
        definition_ct = ContentType.objects.get_for_model(WordDefinition)
        Translation.objects.filter(
            content_type=definition_ct,
            object_id__in=definition_ids,
            language=job.target_language,
        ).delete()

    elif step == S.QUESTION_GEN:
        Question.objects.filter(generation_job=job).delete()
        job.questions_created = 0
        job.save(update_fields=['questions_created'])

    elif step == S.SENTENCE_WRITE_GEN:
        Question.objects.filter(
            generation_job=job,
            question_type__in=[
                Question.QuestionType.SENTENCE_WRITE_GUIDED,
                Question.QuestionType.SENTENCE_WRITE_OPEN,
            ],
        ).delete()

    elif step == S.PACK_CREATION:
        WordPack.objects.filter(word_set=job.word_set).delete()
        job.stories_created = 0
        job.graphic_novels_created = 0
        job.cloze_items_created = 0
        job.save(update_fields=[
            'stories_created', 'graphic_novels_created', 'cloze_items_created',
        ])

    elif step == S.PRIMER_GEN and word_ids:
        PrimerCardContent.objects.filter(word_id__in=word_ids).delete()
        job.primer_cards_created = 0
        job.save(update_fields=['primer_cards_created'])

    elif step == S.STORY_CLOZE_GEN:
        raise ValueError(
            "STORY_CLOZE_GEN is legacy-only and is not an active generation step. "
            "Legacy MicroStory records remain readable through the student fallback."
        )

    elif step == S.GRAPHIC_NOVEL_SCRIPT:
        packs = WordPack.objects.filter(word_set=job.word_set)
        GraphicNovel.objects.filter(pack__in=packs).delete()
        ClozeItem.objects.filter(pack__in=packs).delete()
        job.graphic_novels_created = 0
        job.cloze_items_created = 0
        job.save(update_fields=['graphic_novels_created', 'cloze_items_created'])

    elif step == S.GRAPHIC_NOVEL_IMAGES:
        packs = WordPack.objects.filter(word_set=job.word_set)
        GraphicNovelPage.objects.filter(novel__pack__in=packs).update(
            image='', prompt_used='',
            generation_status=GraphicNovelPage.GenerationStatus.PENDING,
            generation_attempts=0,
            generation_error='',
            generation_started_at=None,
            generation_completed_at=None,
        )

    elif step == S.INFOGRAPHIC_DESIGN:
        packs = WordPack.objects.filter(word_set=job.word_set)
        # Drop staged infographic cloze + the infographics themselves; the pack's
        # promoted cloze (both FKs NULL) is left untouched.
        Infographic.objects.filter(pack__in=packs).delete()
        job.infographics_created = 0
        job.save(update_fields=['infographics_created'])

    elif step == S.INFOGRAPHIC_IMAGE:
        packs = WordPack.objects.filter(word_set=job.word_set)
        Infographic.objects.filter(pack__in=packs).update(
            image='', prompt_used='',
            generation_status=Infographic.GenerationStatus.PENDING,
            generation_attempts=0,
            generation_error='',
            generation_started_at=None,
            generation_completed_at=None,
        )


def _clear_testing_outputs(job, steps, words):
    for step in steps:
        _clear_testing_outputs_for_step(job, step, words)


def _step_uses_generation_model(step):
    return step in {
        GenerationJobLog.Step.WORD_LOOKUP,
        GenerationJobLog.Step.TRANSLATION,
        GenerationJobLog.Step.QUESTION_GEN,
        GenerationJobLog.Step.SENTENCE_WRITE_GEN,
        GenerationJobLog.Step.PACK_CREATION,
        GenerationJobLog.Step.PRIMER_GEN,
        GenerationJobLog.Step.GRAPHIC_NOVEL_SCRIPT,
        GenerationJobLog.Step.INFOGRAPHIC_DESIGN,
    }


_STEP_TO_CONFIG_KEY = {
    GenerationJobLog.Step.WORD_LOOKUP: 'word_lookup',
    GenerationJobLog.Step.TRANSLATION: 'translation',
    GenerationJobLog.Step.QUESTION_GEN: 'question_gen',
    GenerationJobLog.Step.SENTENCE_WRITE_GEN: 'sentence_write_gen',
    GenerationJobLog.Step.PACK_CREATION: 'pack_creation',
    GenerationJobLog.Step.PRIMER_GEN: 'primer_gen',
}


def _build_retry_payload(plan, failed_idx):
    """Build the retry-marker ``output_data`` for a failed-but-recoverable attempt.

    ``plan`` is the ordered list of ``(site_role, model)`` attempts, where
    ``site_role`` is ``'primary'``/``'fallback'`` (or ``None`` when a step has no
    site distinction, e.g. image generation). Attempt numbers are counted
    *within each role*, so a ``[primary, primary, primary, fallback]`` plan
    reads as "attempts 1-3 on primary, then attempt 1 on fallback" — which is
    what the pipeline actually does. The structured fields + ``retry_message`` let the
    frontend show an honest "retrying" state instead of a false failure.
    """
    per_role_numbers = []
    counts = {}
    for role, _model in plan:
        counts[role] = counts.get(role, 0) + 1
        per_role_numbers.append(counts[role])

    failed_role, failed_model = plan[failed_idx]
    next_role, next_model = plan[failed_idx + 1]
    failed_n = per_role_numbers[failed_idx]
    next_n = per_role_numbers[failed_idx + 1]

    def phrase(attempt_n, role, model):
        site = f" on {role} site" if role else ''
        return f"attempt {attempt_n}{site} ({model})"

    message = (
        f"{phrase(failed_n, failed_role, failed_model).capitalize()} failed; "
        f"retrying — {phrase(next_n, next_role, next_model)}."
    )
    return {
        'retrying': True,
        'failed_attempt': failed_n,
        'failed_site_role': failed_role,
        'failed_model': failed_model,
        'next_attempt': next_n,
        'next_site_role': next_role,
        'next_model': next_model,
        'retry_message': message,
    }


def _step_content_type(step):
    """The content type a step belongs to, or None if it always runs."""
    S = GenerationJobLog.Step
    if step in (S.GRAPHIC_NOVEL_SCRIPT, S.GRAPHIC_NOVEL_IMAGES):
        return CONTENT_TYPE_GRAPHIC_NOVEL
    if step in (S.INFOGRAPHIC_DESIGN, S.INFOGRAPHIC_IMAGE):
        return CONTENT_TYPE_INFOGRAPHIC
    return None


def _run_step(job, step, words, words_data, packs):
    """Dispatch a single pipeline step with one retry, then fallback model."""
    S = GenerationJobLog.Step

    # Skip a content-type's steps when the job didn't request that type.
    content_type = _step_content_type(step)
    if content_type is not None and not job_generates_content_type(job, content_type):
        logger.info("Skipping step %s — job %s does not generate %s.", step, job.id, content_type)
        return words, words_data, packs

    if step in (S.GRAPHIC_NOVEL_IMAGES, S.INFOGRAPHIC_IMAGE):
        image_model = (
            GRAPHIC_NOVEL_IMAGE_MODEL if step == S.GRAPHIC_NOVEL_IMAGES
            else INFOGRAPHIC_IMAGE_MODEL
        )
        attempts = [image_model, image_model]
        plan = [(None, model) for model in attempts]
        for attempt_number, model in enumerate(attempts, 1):
            try:
                return _execute_step(job, step, words, words_data, packs, S, model=model)
            except Exception as exc:
                if attempt_number == len(attempts):
                    raise
                payload = _build_retry_payload(plan, attempt_number - 1)
                logger.warning("Step %s: %s (%s)", step, payload['retry_message'], exc)
                _log_step(
                    job, step, GenerationJob.Status.FAILED,
                    input_data={'attempt': attempt_number, 'model': model},
                    output_data=payload,
                    error_message=str(exc),
                )
    elif step in (S.GRAPHIC_NOVEL_SCRIPT, S.INFOGRAPHIC_DESIGN):
        # These steps' substeps each have their own config — pass None and let the
        # step function look up per-substep configs internally.
        return _execute_step(job, step, words, words_data, packs, S, site_config=None)
    elif step in _STEP_TO_CONFIG_KEY:
        config = get_step_config(_STEP_TO_CONFIG_KEY[step])
        attempts = [
            config['primary'], config['primary'], config['primary'],
            config['fallback'],
        ]
        plan = [
            ('primary', config['primary']['model']),
            ('primary', config['primary']['model']),
            ('primary', config['primary']['model']),
            ('fallback', config['fallback']['model']),
        ]
        for attempt_number, site_config in enumerate(attempts, 1):
            try:
                return _execute_step(job, step, words, words_data, packs, S, site_config=site_config)
            except Exception as exc:
                if attempt_number == len(attempts):
                    raise
                payload = _build_retry_payload(plan, attempt_number - 1)
                logger.warning("Step %s: %s (%s)", step, payload['retry_message'], exc)
                _log_step(
                    job, step, GenerationJob.Status.FAILED,
                    input_data={
                        'attempt': attempt_number,
                        'model': site_config['model'],
                        'next_model': payload['next_model'],
                    },
                    output_data=payload,
                    error_message=str(exc),
                )
    else:
        # DEDUP step — no LLM call
        return _execute_step(job, step, words, words_data, packs, S)


def _execute_step(job, step, words, words_data, packs, S, site_config=None, model=None):
    if step == S.WORD_LOOKUP:
        words_data = _step_word_lookup(job, site_config)
    elif step == S.DEDUP:
        words = _step_dedup_and_persist(job, words_data)
        snapshots = _latest_dedup_word_snapshots(job)
        if snapshots:
            words_data = _snapshots_to_words_data(snapshots)
    elif step == S.TRANSLATION:
        _step_generate_translations(job, words, words_data, site_config)
    elif step == S.QUESTION_GEN:
        _step_generate_questions(job, words, words_data, site_config)
    elif step == S.SENTENCE_WRITE_GEN:
        _step_generate_sentence_write(job, words, words_data, site_config)
    elif step == S.PACK_CREATION:
        packs = _step_auto_create_packs(job, words, words_data, site_config)
    elif step == S.PRIMER_GEN:
        _step_generate_primers(job, words, words_data, site_config)
    elif step == S.GRAPHIC_NOVEL_SCRIPT:
        _step_graphic_novel_script(job, packs, words_data)
    elif step == S.GRAPHIC_NOVEL_IMAGES:
        _step_graphic_novel_images(job, packs)
    elif step == S.INFOGRAPHIC_DESIGN:
        _step_infographic_design(job, packs, words_data)
    elif step == S.INFOGRAPHIC_IMAGE:
        _step_infographic_image(job, packs)
    return words, words_data, packs



def run_full_pipeline(job_id):
    """Main entry point. Runs all pipeline steps sequentially."""
    _close_old_connections_if_safe()
    job = None

    try:
        job = GenerationJob.objects.select_related('word_set').get(id=job_id)
        job.status = GenerationJob.Status.RUNNING
        job.error_message = ''
        job.save(update_fields=['status', 'error_message'])

        job.word_set.words.clear()

        words, words_data, packs = [], [], []

        for step in PIPELINE_STEP_ORDER:
            words, words_data, packs = _run_step(
                job, step, words, words_data, packs,
            )
            job.last_completed_step = step
            job.save(update_fields=['last_completed_step'])

        job.status = GenerationJob.Status.COMPLETED
        job.completed_at = timezone.now()
        job.save(update_fields=['status', 'completed_at'])

        job.word_set.generation_status = WordSet.GenerationStatus.GENERATED
        job.word_set.save(update_fields=['generation_status'])

    except Exception as exc:
        logger.exception("Pipeline failed for job %s: %s", job_id, exc)
        try:
            if job is None:
                job = GenerationJob.objects.get(id=job_id)
            job.status = GenerationJob.Status.FAILED
            job.error_message = str(exc)
            job.save(update_fields=['status', 'error_message'])

            job.word_set.generation_status = WordSet.GenerationStatus.TO_GENERATE
            job.word_set.save(update_fields=['generation_status'])
        except Exception:
            logger.exception("Failed to mark job %s as FAILED in database", job_id)
    finally:
        _close_old_connections_if_safe()


def resume_pipeline(job_id):
    """Resume a failed pipeline from the step after last_completed_step."""
    _close_old_connections_if_safe()
    job = None

    try:
        job = GenerationJob.objects.select_related('word_set').get(id=job_id)
        if job.status not in (GenerationJob.Status.FAILED, GenerationJob.Status.RUNNING):
            raise ValueError(f"Job {job_id} cannot be resumed (current: {job.status})")

        job.status = GenerationJob.Status.RUNNING
        job.error_message = ''
        job.save(update_fields=['status', 'error_message'])

        job.word_set.generation_status = WordSet.GenerationStatus.GENERATING
        job.word_set.save(update_fields=['generation_status'])

        if job.last_completed_step:
            try:
                last_idx = PIPELINE_STEP_ORDER.index(job.last_completed_step)
                remaining_steps = PIPELINE_STEP_ORDER[last_idx + 1:]
            except ValueError:
                # last_completed_step is no longer in PIPELINE_STEP_ORDER
                # (e.g., the legacy GRAPHIC_NOVEL_6PAGE_* steps that ran after
                # GRAPHIC_NOVEL_IMAGES). Treat the job as fully completed.
                remaining_steps = []
        else:
            remaining_steps = PIPELINE_STEP_ORDER

        words, words_data, packs = _reconstruct_context(job)

        for step in remaining_steps:
            words, words_data, packs = _run_step(
                job, step, words, words_data, packs,
            )
            job.last_completed_step = step
            job.save(update_fields=['last_completed_step'])

        job.status = GenerationJob.Status.COMPLETED
        job.completed_at = timezone.now()
        job.save(update_fields=['status', 'completed_at'])

        job.word_set.generation_status = WordSet.GenerationStatus.GENERATED
        job.word_set.save(update_fields=['generation_status'])

    except Exception as exc:
        logger.exception("Resume failed for job %s: %s", job_id, exc)
        try:
            if job is None:
                job = GenerationJob.objects.get(id=job_id)
            job.status = GenerationJob.Status.FAILED
            job.error_message = str(exc)
            job.save(update_fields=['status', 'error_message'])

            job.word_set.generation_status = WordSet.GenerationStatus.TO_GENERATE
            job.word_set.save(update_fields=['generation_status'])
        except Exception:
            logger.exception("Failed to mark job %s as FAILED in database", job_id)
    finally:
        _close_old_connections_if_safe()



def restart_pipeline_from_step(job_id, start_step, include_subsequent=True):
    """
    Temporary prompt-testing entry point.

    Reruns one selected pipeline step, or that step and every following step.
    Existing generated artifacts for the selected run range are cleared first so
    step-level resume guards do not keep old prompt output around.
    """
    _close_old_connections_if_safe()
    job = None
    _validate_pipeline_step(start_step)

    try:
        job = GenerationJob.objects.select_related('word_set').get(id=job_id)
        job.status = GenerationJob.Status.RUNNING
        job.error_message = ''
        job.completed_at = None
        job.save(update_fields=['status', 'error_message', 'completed_at'])

        job.word_set.generation_status = WordSet.GenerationStatus.GENERATING
        job.word_set.save(update_fields=['generation_status'])

        start_idx = PIPELINE_STEP_ORDER.index(start_step)
        steps = (
            PIPELINE_STEP_ORDER[start_idx:]
            if include_subsequent
            else [PIPELINE_STEP_ORDER[start_idx]]
        )

        words, words_data, packs = _reconstruct_context(job)
        _clear_testing_outputs(job, steps, words)

        if start_step == GenerationJobLog.Step.WORD_LOOKUP:
            words, words_data, packs = [], [], []
        elif start_step == GenerationJobLog.Step.DEDUP:
            words, packs = [], []
        elif start_step == GenerationJobLog.Step.PACK_CREATION:
            packs = []

        _log_step(
            job,
            start_step,
            GenerationJob.Status.RUNNING,
            output_data={
                'message': 'Testing restart requested.',
                'include_subsequent': include_subsequent,
                'steps': list(steps),
            },
        )

        for step in steps:
            words, words_data, packs = _run_step(
                job, step, words, words_data, packs,
            )
            job.last_completed_step = step
            job.save(update_fields=['last_completed_step'])

        job.status = GenerationJob.Status.COMPLETED
        job.completed_at = timezone.now()
        job.save(update_fields=['status', 'completed_at'])

        job.word_set.generation_status = WordSet.GenerationStatus.GENERATED
        job.word_set.save(update_fields=['generation_status'])

    except Exception as exc:
        logger.exception(
            "Testing restart failed for job %s from %s: %s",
            job_id, start_step, exc,
        )
        try:
            if job is None:
                job = GenerationJob.objects.get(id=job_id)
            job.status = GenerationJob.Status.FAILED
            job.error_message = str(exc)
            job.save(update_fields=['status', 'error_message'])

            job.word_set.generation_status = WordSet.GenerationStatus.TO_GENERATE
            job.word_set.save(update_fields=['generation_status'])
        except Exception:
            logger.exception("Failed to mark job %s as FAILED in database", job_id)
    finally:
        _close_old_connections_if_safe()


def restart_graphic_novel_substep(job_id, pack_id, substep_key, candidate_index=0):
    """Restart one candidate of a pack's graphic novel from a specific substep.

    After regenerating the targeted candidate, this also generates scripts for any
    *other* pack candidates in the word set that still lack a complete graphic novel
    — e.g. candidates the original run never reached because an earlier one failed
    mid-step. Without this, a substep restart on the first pack would mark the
    whole job COMPLETED while later packs/candidates silently had no novel at all
    (job #48). The script step's skip-guard leaves already-complete candidates
    untouched, so the common "regenerate one candidate of a finished job" case adds
    no extra LLM calls.
    """
    _close_old_connections_if_safe()
    job = None

    try:
        job = GenerationJob.objects.select_related('word_set').get(id=job_id)
        job.status = GenerationJob.Status.RUNNING
        job.error_message = ''
        job.save(update_fields=['status', 'error_message'])

        _, words_data, _ = _reconstruct_context(job)

        _log_step(
            job,
            GenerationJobLog.Step.GRAPHIC_NOVEL_SCRIPT,
            GenerationJob.Status.RUNNING,
            output_data={
                'message': f'Substep restart: {substep_key} for pack {pack_id} candidate {candidate_index}',
                'substep_restart': substep_key,
                'pack_id': pack_id,
                'candidate_index': candidate_index,
            },
        )

        restart_graphic_novel_from_substep(
            job, pack_id, substep_key, words_data, candidate_index=candidate_index,
        )

        # Generate scripts for any remaining packs that never got a novel. The
        # script step skips packs that already have a novel with pages (incl. the
        # one just restarted), so this only fills genuine gaps. If a remaining
        # pack fails, the step raises and the job is correctly marked FAILED.
        remaining_packs = list(
            WordPack.objects.filter(word_set=job.word_set)
            .prefetch_related('items__word')
            .order_by('order')
        )
        _step_graphic_novel_script(job, remaining_packs, words_data)

        job.graphic_novels_created = GraphicNovel.objects.filter(
            pack__word_set=job.word_set
        ).count()
        job.cloze_items_created = ClozeItem.objects.filter(
            pack__word_set=job.word_set
        ).count()
        job.status = GenerationJob.Status.COMPLETED
        job.completed_at = timezone.now()
        job.save(update_fields=[
            'status', 'completed_at', 'graphic_novels_created', 'cloze_items_created',
        ])

        job.word_set.generation_status = WordSet.GenerationStatus.GENERATED
        job.word_set.save(update_fields=['generation_status'])

    except Exception as exc:
        logger.exception(
            "Substep restart failed for job %s pack %s substep %s: %s",
            job_id, pack_id, substep_key, exc,
        )
        try:
            if job is None:
                job = GenerationJob.objects.get(id=job_id)
            job.status = GenerationJob.Status.FAILED
            job.error_message = str(exc)
            job.save(update_fields=['status', 'error_message'])
        except Exception:
            logger.exception("Failed to mark job %s as FAILED in database", job_id)
    finally:
        _close_old_connections_if_safe()


def restart_infographic_substep(job_id, pack_id, substep_key, candidate_index=0):
    """Restart one candidate of a pack's infographic from a specific substep.

    Mirrors ``restart_graphic_novel_substep``: after regenerating the targeted
    candidate, it also generates any *other* pack infographic candidates in the
    word set that still lack one — candidates the original run never reached
    because an earlier one failed mid-step. ``_step_infographic_design``'s
    skip-guard leaves already-complete candidates (an ``Infographic`` row exists)
    untouched, so regenerating one candidate of a finished job adds no extra LLM
    calls for the others.

    Image rendering is NOT re-run here (mirrors the GN substep restart, which
    leaves image generation to the pipeline / a separate redraw): the design
    restart regenerates the candidate ``Infographic`` + its staged cloze, and the
    admin re-runs the image step if needed.
    """
    _close_old_connections_if_safe()
    job = None

    try:
        job = GenerationJob.objects.select_related('word_set').get(id=job_id)
        job.status = GenerationJob.Status.RUNNING
        job.error_message = ''
        job.save(update_fields=['status', 'error_message'])

        _, words_data, _ = _reconstruct_context(job)

        _log_step(
            job,
            GenerationJobLog.Step.INFOGRAPHIC_DESIGN,
            GenerationJob.Status.RUNNING,
            output_data={
                'message': f'Substep restart: {substep_key} for pack {pack_id} candidate {candidate_index}',
                'substep_restart': substep_key,
                'pack_id': pack_id,
                'candidate_index': candidate_index,
            },
        )

        restart_infographic_from_substep(
            job, pack_id, substep_key, words_data, candidate_index=candidate_index,
        )

        # Fill any remaining pack candidates that never got an infographic. The
        # design step skips candidates that already have an Infographic row (incl.
        # the one just restarted), so this only fills genuine gaps. If a remaining
        # candidate fails, the step raises and the job is correctly marked FAILED.
        remaining_packs = list(
            WordPack.objects.filter(word_set=job.word_set)
            .prefetch_related('items__word')
            .order_by('order')
        )
        _step_infographic_design(job, remaining_packs, words_data)

        job.infographics_created = Infographic.objects.filter(
            pack__word_set=job.word_set
        ).count()
        job.cloze_items_created = ClozeItem.objects.filter(
            pack__word_set=job.word_set
        ).count()
        job.status = GenerationJob.Status.COMPLETED
        job.completed_at = timezone.now()
        job.save(update_fields=[
            'status', 'completed_at', 'infographics_created', 'cloze_items_created',
        ])

        job.word_set.generation_status = WordSet.GenerationStatus.GENERATED
        job.word_set.save(update_fields=['generation_status'])

    except Exception as exc:
        logger.exception(
            "Infographic substep restart failed for job %s pack %s substep %s: %s",
            job_id, pack_id, substep_key, exc,
        )
        try:
            if job is None:
                job = GenerationJob.objects.get(id=job_id)
            job.status = GenerationJob.Status.FAILED
            job.error_message = str(exc)
            job.save(update_fields=['status', 'error_message'])
        except Exception:
            logger.exception("Failed to mark job %s as FAILED in database", job_id)
    finally:
        _close_old_connections_if_safe()
