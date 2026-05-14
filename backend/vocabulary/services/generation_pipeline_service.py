"""
Generation pipeline orchestrator.

Runs the full LLM content generation pipeline for a word set:
  1. Word Lookup (LLM defines words)
  2. Dedup & Persist (vector embedding dedup + create Word/WordDefinition)
  3. Generate Translations (LLM translates definitions/examples)
  4. Generate Questions (LLM generates practice questions)
  5. Auto-Create Packs (group words into packs of ~5)
  6. Generate Primers (LLM generates primer card content)
  7. Generate Stories & Cloze (LLM generates per-pack stories/cloze)
  8. Generate Images (Gemini generates per-word images)
"""
import json
import logging
import math
import random
import time

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.db import close_old_connections
from django.utils import timezone

from vocabulary.models import (
    Word, WordDefinition, DefinitionEmbedding, Translation,
    Question, MasteryLevel, WordSet, WordPack, WordPackItem, PrimerCardContent,
    MicroStory, GraphicNovel, GraphicNovelPage, ClozeItem, GeneratedImage,
    GenerationJob, GenerationJobLog,
)
from vocabulary.services.llm_service import (
    call_gemini, call_openai_image, load_prompt_template,
)
from vocabulary.constants import QUESTION_TYPE_LEVEL
from vocabulary.services.embedding_service import (
    get_embedding, find_duplicate_definition,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = 'gemini-3.1-pro-preview'
BACKUP_MODEL = 'gemini-3-pro-preview'

# Content Lexile should be 15% below the word set's target Lexile
# so scaffolding text is easier to read than the vocabulary being taught.
LEXILE_OFFSET = 0.85


def _content_lexile(job):
    """Return the Lexile level for generated content (15% below target)."""
    return int(job.target_lexile * LEXILE_OFFSET)


def _log_step(job, step, status, duration=None, input_data=None,
              output_data=None, error_message=''):
    """Create a GenerationJobLog entry for a pipeline step."""
    return GenerationJobLog.objects.create(
        job=job,
        step=step,
        status=status,
        duration_seconds=duration,
        input_data=input_data,
        output_data=output_data,
        error_message=error_message,
    )


# Ordered list of pipeline steps. Each entry: (step_enum, step_function_name)
# Step functions receive (job, context) and return updated context.
PIPELINE_STEP_ORDER = [
    GenerationJobLog.Step.WORD_LOOKUP,
    GenerationJobLog.Step.DEDUP,
    GenerationJobLog.Step.TRANSLATION,
    GenerationJobLog.Step.QUESTION_GEN,
    GenerationJobLog.Step.PACK_CREATION,
    GenerationJobLog.Step.PRIMER_GEN,
    GenerationJobLog.Step.GRAPHIC_NOVEL_SCRIPT,
    GenerationJobLog.Step.GRAPHIC_NOVEL_IMAGES,
    GenerationJobLog.Step.CREATIVE_DIRECTION,
    GenerationJobLog.Step.IMAGE_GEN,
    GenerationJobLog.Step.PICTURE_MATCH_GEN,
]


def _validate_pipeline_step(step):
    if step not in PIPELINE_STEP_ORDER:
        valid_steps = ', '.join(PIPELINE_STEP_ORDER)
        raise ValueError(f"Unknown pipeline step '{step}'. Valid steps: {valid_steps}")


def _reconstruct_context(job):
    """Rebuild intermediate state from DB for resuming a failed pipeline."""
    words = list(job.word_set.words.filter(text__in=job.input_words).distinct())
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
    """
    Remove generated artifacts for a step before a manual testing rerun.

    This is intentionally scoped to the job/word set and exists for prompt
    iteration, where rerunning should not be blocked by resume-safety skips.
    """
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
        Question.objects.filter(generation_job=job).exclude(
            question_type=Question.QuestionType.PICTURE_WORD_MATCH,
        ).delete()
        job.questions_created = 0
        job.save(update_fields=['questions_created'])

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
        packs = WordPack.objects.filter(word_set=job.word_set)
        MicroStory.objects.filter(pack__in=packs).delete()
        ClozeItem.objects.filter(pack__in=packs).delete()
        job.stories_created = 0
        job.cloze_items_created = 0
        job.save(update_fields=['stories_created', 'cloze_items_created'])

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
        )

    elif step == S.CREATIVE_DIRECTION and word_ids:
        WordDefinition.objects.filter(word_id__in=word_ids).update(visual_scene='')

    elif step == S.IMAGE_GEN and word_ids:
        GeneratedImage.objects.filter(word_id__in=word_ids).delete()
        job.images_created = 0
        job.save(update_fields=['images_created'])

    elif step == S.PICTURE_MATCH_GEN:
        Question.objects.filter(
            generation_job=job,
            question_type=Question.QuestionType.PICTURE_WORD_MATCH,
        ).delete()


def _clear_testing_outputs(job, steps, words):
    for step in steps:
        _clear_testing_outputs_for_step(job, step, words)


def _step_uses_generation_model(step):
    return step in {
        GenerationJobLog.Step.WORD_LOOKUP,
        GenerationJobLog.Step.TRANSLATION,
        GenerationJobLog.Step.QUESTION_GEN,
        GenerationJobLog.Step.PACK_CREATION,
        GenerationJobLog.Step.PRIMER_GEN,
        GenerationJobLog.Step.STORY_CLOZE_GEN,
        GenerationJobLog.Step.GRAPHIC_NOVEL_SCRIPT,
        GenerationJobLog.Step.CREATIVE_DIRECTION,
    }


def _run_step(job, step, words, words_data, packs):
    """Dispatch a single pipeline step with one retry, then backup model fallback."""
    S = GenerationJobLog.Step
    attempts = [DEFAULT_MODEL, DEFAULT_MODEL]
    if _step_uses_generation_model(step):
        attempts.append(BACKUP_MODEL)

    for attempt_number, model in enumerate(attempts, 1):
        try:
            return _execute_step(job, step, words, words_data, packs, S, model)
        except Exception as exc:
            if attempt_number == len(attempts):
                raise

            next_model = attempts[attempt_number]
            logger.warning(
                "Step %s failed on attempt %d using model %s; retrying with %s: %s",
                step, attempt_number, model, next_model, exc,
            )
            _log_step(
                job,
                step,
                GenerationJob.Status.FAILED,
                input_data={
                    'attempt': attempt_number,
                    'model': model,
                    'next_model': next_model,
                },
                output_data={'retrying': True},
                error_message=str(exc),
            )


def _execute_step(job, step, words, words_data, packs, S, model):
    if step == S.WORD_LOOKUP:
        words_data = _step_word_lookup(job, model)
    elif step == S.DEDUP:
        words = _step_dedup_and_persist(job, words_data)
    elif step == S.TRANSLATION:
        _step_generate_translations(job, words, words_data, model)
    elif step == S.QUESTION_GEN:
        _step_generate_questions(job, words, words_data, model)
    elif step == S.PACK_CREATION:
        packs = _step_auto_create_packs(job, words, words_data, model)
    elif step == S.PRIMER_GEN:
        _step_generate_primers(job, words, words_data, model)
    elif step == S.STORY_CLOZE_GEN:
        _step_generate_stories_and_cloze(job, packs, words_data, model)
    elif step == S.GRAPHIC_NOVEL_SCRIPT:
        _step_graphic_novel_script(job, packs, words_data, model)
    elif step == S.GRAPHIC_NOVEL_IMAGES:
        _step_graphic_novel_images(job, packs)
    elif step == S.CREATIVE_DIRECTION:
        _step_creative_direction(job, words, model)
    elif step == S.IMAGE_GEN:
        _step_generate_images(job, words)
    elif step == S.PICTURE_MATCH_GEN:
        _step_generate_picture_match_questions(job, words, packs)
    return words, words_data, packs


def run_full_pipeline(job_id):
    """
    Main entry point. Runs all pipeline steps sequentially.
    Tracks last_completed_step and updates word_set.generation_status.
    """
    close_old_connections()
    job = None

    try:
        job = GenerationJob.objects.select_related('word_set').get(id=job_id)
        job.status = GenerationJob.Status.RUNNING
        job.error_message = ''
        job.save(update_fields=['status', 'error_message'])

        # Clear any existing words from the word_set to avoid duplicates on re-run
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


def resume_pipeline(job_id):
    """
    Resume a failed pipeline from the step after last_completed_step.
    Reconstructs intermediate state from DB.
    """
    close_old_connections()
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

        # Find where to resume
        if job.last_completed_step:
            try:
                last_idx = PIPELINE_STEP_ORDER.index(job.last_completed_step)
                remaining_steps = PIPELINE_STEP_ORDER[last_idx + 1:]
            except ValueError:
                remaining_steps = PIPELINE_STEP_ORDER
        else:
            remaining_steps = PIPELINE_STEP_ORDER

        # Reconstruct state from DB
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


def restart_pipeline_from_step(job_id, start_step, include_subsequent=True):
    """
    Temporary prompt-testing entry point.

    Reruns one selected pipeline step, or that step and every following step.
    Existing generated artifacts for the selected run range are cleared first so
    step-level resume guards do not keep old prompt output around.
    """
    close_old_connections()
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


def _step_word_lookup(job, model=DEFAULT_MODEL):
    """
    Step 1: Call LLM to look up definitions for the input word list.

    Returns:
        list[dict]: Parsed word data from LLM response.
    """
    start = time.time()
    try:
        template = load_prompt_template('word_lookup')
        words_str = ', '.join(job.input_words)
        user_prompt = (
            f"Words to look up: {words_str}\n"
            f"Target Lexile level: {job.target_lexile}L\n"
            f"Source: {job.input_source_title}"
        )
        if job.input_source_chapter:
            user_prompt += f", Chapter: {job.input_source_chapter}"
        if job.input_source_text:
            user_prompt += f"\n\nSource passage:\n{job.input_source_text}"

        result = call_gemini(model, template, user_prompt)
        words_data = result.get('words', [])

        duration = time.time() - start
        _log_step(
            job, GenerationJobLog.Step.WORD_LOOKUP,
            GenerationJob.Status.COMPLETED,
            duration=duration,
            input_data={'words': job.input_words},
            output_data=result,
        )
        return words_data

    except Exception as exc:
        duration = time.time() - start
        _log_step(
            job, GenerationJobLog.Step.WORD_LOOKUP,
            GenerationJob.Status.FAILED,
            duration=duration,
            input_data={'words': job.input_words},
            error_message=str(exc),
        )
        raise


def _step_dedup_and_persist(job, words_data):
    """
    Step 2: Check for duplicate definitions via vector embedding,
    then create Word + WordDefinition + DefinitionEmbedding records.

    Returns:
        list[Word]: List of Word objects (new or existing deduplicated).
    """
    start = time.time()
    words = []
    new_count = 0

    # Deduplicate words_data by term (case-insensitive) — LLM may return duplicates
    seen_terms = set()
    unique_words_data = []
    for wd in words_data:
        key = wd['term'].lower()
        if key not in seen_terms:
            seen_terms.add(key)
            unique_words_data.append(wd)

    for wd in unique_words_data:
        term = wd['term']
        pos = wd.get('part_of_speech', '')
        definition = wd.get('definition', '')

        # Check for existing duplicate
        existing = find_duplicate_definition(term, pos, definition)
        if existing:
            logger.info("Dedup: reusing existing Word '%s' (id=%s)", term, existing.id)
            image_category = wd.get('image_category', '')
            if image_category and not existing.image_category:
                existing.image_category = image_category
                existing.save(update_fields=['image_category'])
            words.append(existing)
            job.word_set.words.add(existing)
            continue

        # Create new Word — source_context comes from the job, not per-word LLM output
        source_context = ''
        if job.input_source_title:
            source_context = f"From {job.input_source_title}"
            if job.input_source_chapter:
                source_context += f", {job.input_source_chapter}"

        word = Word.objects.create(
            text=term,
            part_of_speech=pos,
            image_category=wd.get('image_category', ''),
            source_context=source_context,
        )

        # Create WordDefinition
        defn = WordDefinition.objects.create(
            word=word,
            definition_text=definition,
            example_sentence=wd.get('example_sentence', ''),
            lexile_score=wd.get('lexile_score'),
        )

        # Store embedding
        embedding_vector = get_embedding(definition)
        DefinitionEmbedding.objects.create(
            definition=defn,
            embedding=embedding_vector,
            model_version=settings.QWEN_EMBEDDING_MODEL,
        )

        job.word_set.words.add(word)
        words.append(word)
        new_count += 1

    job.words_created = new_count
    job.save(update_fields=['words_created'])

    # Update input_words to reflect LLM-normalized terms (e.g., "salutations" → "salutation")
    # so downstream queries using text__in=job.input_words match correctly.
    job.input_words = [w.text for w in words]
    job.save(update_fields=['input_words'])

    duration = time.time() - start
    _log_step(
        job, GenerationJobLog.Step.DEDUP,
        GenerationJob.Status.COMPLETED,
        duration=duration,
        output_data={'new_words': new_count, 'total': len(words)},
    )

    return words


def _step_generate_translations(job, words, words_data, model=DEFAULT_MODEL):
    """
    Step 3: Call LLM to generate translations for definitions and examples.

    Creates Translation records using Django's GenericForeignKey.
    """
    start = time.time()
    try:
        template = load_prompt_template('translation')
        target_language = job.target_language

        # Build items to translate — include term for context
        items_list = []
        for wd in words_data:
            term = wd.get('term', '')
            items_list.append(f"- term: {term}")
            items_list.append(f"  definition_text: {wd.get('definition', '')}")
            example = wd.get('example_sentence', '')
            if example:
                items_list.append(f"  example_sentence: {example}")

        items_str = '\n'.join(items_list)
        prompt = template.format(
            target_language=target_language,
            items_to_translate=items_str,
        )

        result = call_gemini(model, prompt, f"Translate to {target_language}")
        translations = result.get('translations', [])

        # Get ContentType for WordDefinition
        wd_ct = ContentType.objects.get_for_model(WordDefinition)

        # Map words_data terms to Word objects for definition lookup
        word_map = {w.text: w for w in words}

        for trans in translations:
            field_name = trans.get('source_field', '')
            source_text = trans.get('source_text', '')
            translated_text = trans.get('translated_text', '')

            # Find the matching WordDefinition
            for word in words:
                defn = word.definitions.first()
                if not defn:
                    continue

                if field_name == 'definition_text' and source_text in defn.definition_text:
                    Translation.objects.update_or_create(
                        content_type=wd_ct,
                        object_id=defn.id,
                        field_name='definition_text',
                        language=target_language,
                        defaults={'translated_text': translated_text},
                    )
                    break
                elif field_name == 'example_sentence' and source_text in defn.example_sentence:
                    Translation.objects.update_or_create(
                        content_type=wd_ct,
                        object_id=defn.id,
                        field_name='example_sentence',
                        language=target_language,
                        defaults={'translated_text': translated_text},
                    )
                    break

        duration = time.time() - start
        _log_step(
            job, GenerationJobLog.Step.TRANSLATION,
            GenerationJob.Status.COMPLETED,
            duration=duration,
            output_data={'translations_count': len(translations)},
        )

    except Exception as exc:
        duration = time.time() - start
        _log_step(
            job, GenerationJobLog.Step.TRANSLATION,
            GenerationJob.Status.FAILED,
            duration=duration,
            error_message=str(exc),
        )
        raise


QUESTION_BATCH_SIZE = 6


def _step_generate_questions(job, words, words_data, model=DEFAULT_MODEL):
    """
    Step 4: Call LLM to generate practice questions for each word.

    Uses two alternating prompts (A/B) chosen randomly per batch for variety.
    Batches words into groups of QUESTION_BATCH_SIZE to keep error rates low.
    """

    start = time.time()
    try:

        templates = {
            'A': load_prompt_template('question_generation_A'),
            'B': load_prompt_template('question_generation_B'),
        }

        # Build word list with existing definitions from Step 1
        word_list = []
        for wd in words_data:
            word_list.append({
                'term': wd['term'],
                'part_of_speech': wd.get('part_of_speech', ''),
                'definition': wd.get('definition', ''),
                'example_sentence': wd.get('example_sentence', ''),
            })

        # Split into batches of QUESTION_BATCH_SIZE
        batches = [
            word_list[i:i + QUESTION_BATCH_SIZE]
            for i in range(0, len(word_list), QUESTION_BATCH_SIZE)
        ]

        word_map = {w.text.lower(): w for w in words}
        mastery_levels = {ml.level_id: ml for ml in MasteryLevel.objects.all()}
        created_count = 0
        total_batches = len(batches)

        for batch_idx, batch in enumerate(batches, 1):
            batch_terms = [w['term'] for w in batch]
            prompt_label = random.choice(['A', 'B'])
            template = templates[prompt_label]
            logger.info(
                "Question generation batch %d/%d (prompt %s): %s",
                batch_idx, total_batches, prompt_label, ', '.join(batch_terms),
            )

            input_json = json.dumps({
                'target_lexile_level': _content_lexile(job),
                'words': batch,
            }, indent=2)

            prompt_text = template.replace('{input_json}', input_json)
            result = call_gemini(model, prompt_text, '')
            question_sets = result.get('generated_question_sets', [])

            for qs in question_sets:
                term = qs.get('term', '').lower()
                word = word_map.get(term)
                if not word:
                    logger.warning("Question set for unknown term '%s', skipping", term)
                    continue

                for qd in qs.get('questions', []):
                    options = qd.get('options')
                    if isinstance(options, dict) and 'choices' in options:
                        options = options['choices']

                    q_type = qd.get('question_type', 'DEFINITION_MC_SINGLE')
                    question = Question.objects.create(
                        word=word,
                        question_type=q_type,
                        question_text=qd.get('question_text', ''),
                        options=options,
                        correct_answers=qd.get('correct_answers', []),
                        explanation=qd.get('explanation', ''),
                        example_sentence=qd.get('example_sentence', ''),
                        lexile_score=qd.get('lexile_score'),
                        generation_job=job,
                    )

                    level_num = QUESTION_TYPE_LEVEL.get(q_type)
                    if level_num:
                        ml = mastery_levels.get(level_num)
                        if ml:
                            question.suitable_levels.add(ml)

                    created_count += 1

        job.questions_created = created_count
        job.save(update_fields=['questions_created'])

        duration = time.time() - start
        _log_step(
            job, GenerationJobLog.Step.QUESTION_GEN,
            GenerationJob.Status.COMPLETED,
            duration=duration,
            output_data={
                'questions_created': created_count,
                'batches': total_batches,
            },
        )

    except Exception as exc:
        duration = time.time() - start
        _log_step(
            job, GenerationJobLog.Step.QUESTION_GEN,
            GenerationJob.Status.FAILED,
            duration=duration,
            error_message=str(exc),
        )
        raise


def _step_auto_create_packs(job, words, words_data, model=DEFAULT_MODEL):
    """
    Step 5: Use LLM to group words into semantically related packs.
    Falls back to sequential chunking if LLM fails.

    If packs already exist for this word set during a resumed job, appends any
    unpacked generated words instead of creating duplicates.

    Returns:
        list[WordPack]: All pack objects (existing + new).
    """
    start = time.time()
    pack_size = settings.GENERATION_WORDS_PER_PACK
    word_map = {w.text.lower(): w for w in words}

    existing_packs = list(
        WordPack.objects.filter(word_set=job.word_set)
        .prefetch_related('items__word')
        .order_by('order')
    )

    # Resume mode: add any generated words that are not already in packs.
    if existing_packs:
        # Find which words are already in packs
        packed_word_ids = set()
        for pack in existing_packs:
            for item in pack.items.all():
                packed_word_ids.add(item.word_id)

        new_words = [w for w in words if w.id not in packed_word_ids]
        if not new_words:
            # All words already packed
            duration = time.time() - start
            _log_step(
                job, GenerationJobLog.Step.PACK_CREATION,
                GenerationJob.Status.COMPLETED,
                duration=duration,
                output_data={'packs_created': 0, 'words_added_to_existing': 0},
            )
            return existing_packs

        # Fill the last pack if it has room, then create new packs for overflow
        last_pack = existing_packs[-1]
        last_pack_count = last_pack.items.count()
        added_to_existing = 0
        remaining_words = list(new_words)

        if last_pack_count < pack_size:
            room = pack_size - last_pack_count
            to_add = remaining_words[:room]
            remaining_words = remaining_words[room:]
            for word in to_add:
                WordPackItem.objects.create(
                    pack=last_pack, word=word, order=last_pack_count,
                )
                last_pack_count += 1
                added_to_existing += 1

        # Create new packs for remaining words
        new_packs = []
        if remaining_words:
            max_order = existing_packs[-1].order + 1
            num_new_packs = max(1, math.ceil(len(remaining_words) / pack_size))
            for i in range(num_new_packs):
                chunk = remaining_words[i * pack_size:(i + 1) * pack_size]
                pack = WordPack.objects.create(
                    word_set=job.word_set,
                    label=f"Pack {max_order + i + 1}",
                    order=max_order + i,
                )
                for idx, word in enumerate(chunk):
                    WordPackItem.objects.create(pack=pack, word=word, order=idx)
                new_packs.append(pack)

        logger.info(
            "Resume packing: %d added to existing, %d new packs created",
            added_to_existing, len(new_packs),
        )

        duration = time.time() - start
        _log_step(
            job, GenerationJobLog.Step.PACK_CREATION,
            GenerationJob.Status.COMPLETED,
            duration=duration,
            output_data={
                'packs_created': len(new_packs),
                'words_added_to_existing': added_to_existing,
            },
        )
        return existing_packs + new_packs

    # Fresh generation: use LLM to group words semantically
    try:

        template = load_prompt_template('pack_grouping')

        # Calculate balanced pack distribution (max 6 per pack)
        max_per_pack = pack_size
        total_words = len(words)
        num_packs = math.ceil(total_words / max_per_pack)

        # Build word list with definitions for the LLM
        word_info_parts = []
        for wd in words_data:
            word_info_parts.append(
                f"- {wd['term']} ({wd.get('part_of_speech', '')}): {wd.get('definition', '')}"
            )

        prompt_text = template.replace('{num_packs}', str(num_packs))
        prompt_text = prompt_text.replace('{max_per_pack}', str(max_per_pack))
        user_prompt = '\n'.join(word_info_parts)
        result = call_gemini(model, prompt_text, user_prompt)
        llm_packs = result.get('packs', [])

        # Validate: every word must appear exactly once
        seen = set()
        for p in llm_packs:
            for t in p.get('words', []):
                seen.add(t.lower())
        all_terms = {w.text.lower() for w in words}
        if seen != all_terms:
            raise ValueError(
                f"LLM pack grouping mismatch: missing={all_terms - seen}, extra={seen - all_terms}"
            )

        packs = []
        for i, pack_data in enumerate(llm_packs):
            text_type = pack_data.get('text_type', 'fiction')
            if text_type not in ('fiction', 'narrative_nonfiction'):
                text_type = 'fiction'
            pack = WordPack.objects.create(
                word_set=job.word_set,
                label=pack_data.get('label', f'Pack {i + 1}'),
                text_type=text_type,
                order=i,
            )
            for idx, term in enumerate(pack_data.get('words', [])):
                word = word_map.get(term.lower())
                if word:
                    WordPackItem.objects.create(pack=pack, word=word, order=idx)
            packs.append(pack)

        logger.info("LLM grouped %d words into %d packs", len(words), len(packs))

    except Exception as llm_exc:
        logger.warning("LLM pack grouping failed, falling back to sequential: %s", llm_exc)
        # Fallback: sequential chunking
        packs = []
        num_packs = max(1, math.ceil(len(words) / pack_size))
        for i in range(num_packs):
            chunk = words[i * pack_size:(i + 1) * pack_size]
            pack = WordPack.objects.create(
                word_set=job.word_set,
                label=f"Pack {i + 1}",
                order=i,
            )
            for idx, word in enumerate(chunk):
                WordPackItem.objects.create(pack=pack, word=word, order=idx)
            packs.append(pack)

    duration = time.time() - start
    _log_step(
        job, GenerationJobLog.Step.PACK_CREATION,
        GenerationJob.Status.COMPLETED,
        duration=duration,
        output_data={'packs_created': len(packs)},
    )

    return packs


def _step_generate_primers(job, words, words_data, model=DEFAULT_MODEL):
    """
    Step 6: Call LLM to generate primer card content for each word.
    Uses definition and example_sentence from step 1 (word lookup).
    LLM generates syllable_text and kid_friendly_definition only.
    """
    start = time.time()
    try:
        template = load_prompt_template('primer_generation')

        # Build word info with definition + example from step 1
        word_info_parts = []
        words_data_map = {}
        for wd in words_data:
            term = wd['term']
            words_data_map[term.lower()] = wd
            word_info_parts.append(
                f"- {term} ({wd.get('part_of_speech', '')}): "
                f"definition: {wd.get('definition', '')} | "
                f"example: {wd.get('example_sentence', '')}"
            )

        user_prompt = '\n'.join(word_info_parts)
        prompt_text = template.replace('{target_lexile}', str(_content_lexile(job)))
        result = call_gemini(model, prompt_text, user_prompt)
        primers = result.get('primer_cards', [])

        word_map = {w.text.lower(): w for w in words}
        created_count = 0

        for pc in primers:
            term = pc.get('term', '').lower()
            word = word_map.get(term)
            if not word:
                logger.warning("Primer for unknown term '%s', skipping", term)
                continue

            # Use example_sentence from step 1 word lookup
            wd = words_data_map.get(term, {})
            example = wd.get('example_sentence', '')

            PrimerCardContent.objects.update_or_create(
                word=word,
                defaults={
                    'syllable_text': pc.get('syllable_text', ''),
                    'kid_friendly_definition': pc.get('kid_friendly_definition', ''),
                    'example_sentence': example,
                },
            )
            created_count += 1

        job.primer_cards_created = created_count
        job.save(update_fields=['primer_cards_created'])

        duration = time.time() - start
        _log_step(
            job, GenerationJobLog.Step.PRIMER_GEN,
            GenerationJob.Status.COMPLETED,
            duration=duration,
            output_data={'primers_created': created_count},
        )

    except Exception as exc:
        duration = time.time() - start
        _log_step(
            job, GenerationJobLog.Step.PRIMER_GEN,
            GenerationJob.Status.FAILED,
            duration=duration,
            error_message=str(exc),
        )
        raise


def _step_generate_stories_and_cloze(job, packs, words_data, model=DEFAULT_MODEL):
    """
    Step 7: Call LLM to generate micro story + cloze items for each pack.
    Skips packs that already have stories when resuming a partially completed job.
    """
    start = time.time()
    try:
        template = load_prompt_template('story_cloze_generation')
        total_stories = 0
        total_cloze = 0

        for pack in packs:
            # Skip packs that already have stories
            if pack.stories.exists():
                logger.info("Pack '%s' already has stories, skipping", pack.label)
                continue

            pack_word_texts = list(
                pack.items.values_list('word__text', flat=True)
            )

            # Filter words_data for this pack's words
            pack_words_data = [
                wd for wd in words_data
                if wd['term'].lower() in [t.lower() for t in pack_word_texts]
            ]

            # Build word info with definitions for richer context
            word_parts = []
            for wd in pack_words_data:
                word_parts.append(
                    f"- {wd['term']} ({wd.get('part_of_speech', '')}): {wd.get('definition', '')}"
                )
            word_info = '\n'.join(word_parts)

            content_lexile = _content_lexile(job)
            user_prompt = (
                f"Pack Label: {pack.label}\n"
                f"Text Type: {pack.text_type}\n"
                f"Target Lexile: {content_lexile}\n\n"
                f"Target words:\n{word_info}"
            )
            system_prompt = template.format(target_lexile=content_lexile)

            result = call_gemini(model, system_prompt, user_prompt)

            # Create MicroStory — try both field names for robustness
            story_data = result.get('micro_passage', result.get('micro_story', {}))
            MicroStory.objects.create(
                pack=pack,
                story_text=story_data.get('text', story_data.get('story_text', '')),
                reading_level=story_data.get('reading_level', content_lexile),
            )
            total_stories += 1

            # Create ClozeItems
            cloze_data = result.get('cloze_items', [])
            word_map = {
                item.word.text.lower(): item.word
                for item in pack.items.select_related('word').all()
            }

            for idx, ci in enumerate(cloze_data):
                term = ci.get('term', '').lower()
                word = word_map.get(term)
                if not word:
                    continue

                ClozeItem.objects.create(
                    pack=pack,
                    word=word,
                    sentence_text=ci.get('sentence_text', ''),
                    correct_answer=ci.get('correct_answer', ''),
                    distractors=ci.get('distractors', []),
                    order=idx,
                )
                total_cloze += 1

        job.stories_created = total_stories
        job.cloze_items_created = total_cloze
        job.save(update_fields=['stories_created', 'cloze_items_created'])

        duration = time.time() - start
        _log_step(
            job, GenerationJobLog.Step.STORY_CLOZE_GEN,
            GenerationJob.Status.COMPLETED,
            duration=duration,
            output_data={'stories': total_stories, 'cloze_items': total_cloze},
        )

    except Exception as exc:
        duration = time.time() - start
        _log_step(
            job, GenerationJobLog.Step.STORY_CLOZE_GEN,
            GenerationJob.Status.FAILED,
            duration=duration,
            error_message=str(exc),
        )
        raise


def _page_vocab_words(page_data):
    words = []
    for panel in page_data.get('panels', []):
        for word in panel.get('vocab_words', []):
            if word and word not in words:
                words.append(word)
    for word in page_data.get('vocab_words', []):
        if word and word not in words:
            words.append(word)
    return words


def _step_graphic_novel_script(job, packs, words_data, model=DEFAULT_MODEL):
    """
    Step 7A: Generate a graphic novel script and cloze items for each pack.

    The script step creates the novel/page records without images so image
    generation can resume independently.
    """
    start = time.time()
    try:
        template = load_prompt_template('graphic_novel_script')
        total_novels = 0
        total_cloze = 0

        for pack in packs:
            if hasattr(pack, 'graphic_novel'):
                logger.info("Pack '%s' already has a graphic novel, skipping", pack.label)
                continue

            pack_word_texts = list(pack.items.values_list('word__text', flat=True))
            pack_word_keys = {text.lower() for text in pack_word_texts}
            pack_words_data = [
                wd for wd in words_data
                if wd['term'].lower() in pack_word_keys
            ]

            word_info = '\n'.join(
                f"- {wd['term']} ({wd.get('part_of_speech', '')}): {wd.get('definition', '')}"
                for wd in pack_words_data
            )
            content_lexile = _content_lexile(job)
            user_prompt = (
                f"Pack Label: {pack.label}\n"
                f"Text Type: {pack.text_type}\n"
                f"Target Lexile: {content_lexile}\n\n"
                f"Target words:\n{word_info}"
            )
            system_prompt = template.replace('{target_lexile}', str(content_lexile))
            result = call_gemini(model, system_prompt, user_prompt)

            novel = GraphicNovel.objects.create(
                pack=pack,
                title=result.get('title', f'{pack.label} Graphic Novel'),
                synopsis=result.get('synopsis', ''),
                style_prompt=result.get(
                    'style_prompt',
                    result.get('style_notes', 'Middle-grade graphic novel art with clear readable lettering.'),
                ),
                reading_level=result.get('reading_level', content_lexile),
            )
            total_novels += 1

            for idx, page_data in enumerate(result.get('pages', []), 1):
                panel_descriptions = page_data.get('panels', [])
                GraphicNovelPage.objects.create(
                    novel=novel,
                    page_number=page_data.get('page_number', idx),
                    panel_count=page_data.get('panel_count', len(panel_descriptions) or 1),
                    layout_description=page_data.get('layout_description', ''),
                    panel_descriptions=panel_descriptions,
                    vocab_words_used=_page_vocab_words(page_data),
                )

            word_map = {
                item.word.text.lower(): item.word
                for item in pack.items.select_related('word').all()
            }
            for idx, ci in enumerate(result.get('cloze_items', [])):
                term = ci.get('term', '').lower()
                word = word_map.get(term)
                if not word:
                    continue

                ClozeItem.objects.create(
                    pack=pack,
                    word=word,
                    sentence_text=ci.get('sentence_text', ''),
                    correct_answer=ci.get('correct_answer', ''),
                    distractors=ci.get('distractors', []),
                    order=idx,
                )
                total_cloze += 1

        job.graphic_novels_created = GraphicNovel.objects.filter(pack__in=packs).count()
        job.cloze_items_created = ClozeItem.objects.filter(pack__in=packs).count()
        job.save(update_fields=['graphic_novels_created', 'cloze_items_created'])

        duration = time.time() - start
        _log_step(
            job, GenerationJobLog.Step.GRAPHIC_NOVEL_SCRIPT,
            GenerationJob.Status.COMPLETED,
            duration=duration,
            output_data={
                'graphic_novels_created': total_novels,
                'cloze_items_created': total_cloze,
            },
        )

    except Exception as exc:
        duration = time.time() - start
        _log_step(
            job, GenerationJobLog.Step.GRAPHIC_NOVEL_SCRIPT,
            GenerationJob.Status.FAILED,
            duration=duration,
            error_message=str(exc),
        )
        raise


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
    template = load_prompt_template('graphic_novel_page')
    created_count = 0
    pending_count = 0
    failed_pages = []

    pages = list(
        GraphicNovelPage.objects.filter(novel__pack__in=packs)
        .select_related('novel', 'novel__pack')
        .order_by('novel_id', 'page_number')
    )

    for page in pages:
        if page.image:
            continue
        pending_count += 1

        vocab_words = ', '.join(page.vocab_words_used)
        panel_details = json.dumps(page.panel_descriptions, indent=2)
        prompt = template.format(
            title=page.novel.title,
            synopsis=page.novel.synopsis,
            style_prompt=page.novel.style_prompt,
            page_number=page.page_number,
            panel_count=page.panel_count,
            layout_description=page.layout_description,
            panel_details=panel_details,
            vocab_words=vocab_words or 'the target vocabulary words',
        )

        try:
            image_bytes = call_openai_image(prompt, size="1792x1024")
            title_slug = ''.join(
                c if c.isalnum() else '_' for c in page.novel.title.lower()
            ).strip('_')[:60] or 'graphic_novel'
            filename = f"{title_slug}_page_{page.page_number}.png"
            page.image.save(filename, ContentFile(image_bytes), save=False)
            page.prompt_used = prompt
            page.save(update_fields=['image', 'prompt_used'])
            created_count += 1

        except Exception as exc:
            label = f"{page.novel.pack.label} page {page.page_number}"
            logger.warning("Graphic novel image generation failed for %s: %s", label, exc)
            failed_pages.append(label)
            continue

    duration = time.time() - start
    if pending_count > 0 and created_count == 0:
        _log_step(
            job, GenerationJobLog.Step.GRAPHIC_NOVEL_IMAGES,
            GenerationJob.Status.FAILED,
            duration=duration,
            output_data={
                'pages_created': 0,
                'failed_pages': failed_pages,
            },
            error_message=f"All {pending_count} graphic novel page generations failed.",
        )
        raise RuntimeError(
            f"Graphic novel image generation failed for all {pending_count} pages."
        )

    _log_step(
        job, GenerationJobLog.Step.GRAPHIC_NOVEL_IMAGES,
        GenerationJob.Status.COMPLETED,
        duration=duration,
        output_data={
            'pages_created': created_count,
            'failed_pages': failed_pages,
        },
    )


CREATIVE_DIRECTION_GROUPS = {
    'character': ['ICONIC_CHARACTER', 'EMOTION_STATE', 'SENSORY_TRAIT'],
    'action': ['DYNAMIC_ACTION', 'EPIC_SCALE', 'SPATIAL_RELATION'],
    'elemental': ['INVISIBLE_PROCESS', 'ABSTRACT_METAPHOR', 'PORTABLE_OBJECT'],
}

# Reverse lookup: category -> group name
_CATEGORY_TO_GROUP = {
    cat: group
    for group, cats in CREATIVE_DIRECTION_GROUPS.items()
    for cat in cats
}


def _step_creative_direction(job, words, model=DEFAULT_MODEL):
    """
    Generate visual scene descriptions for each word based on its image_category.
    Groups words by category type and calls LLM with category-specific prompts.
    """
    _log_step(
        job, GenerationJobLog.Step.CREATIVE_DIRECTION,
        GenerationJob.Status.RUNNING,
        output_data={'message': 'Starting creative direction'},
    )
    start = time.time()

    defn_map = {}
    for d in WordDefinition.objects.filter(word__in=words).order_by('word_id', 'id'):
        defn_map.setdefault(d.word_id, d)

    # Skip words that already have a visual_scene (resume safety)
    words_needing_scene = [
        w for w in words
        if w.id in defn_map and not defn_map[w.id].visual_scene
    ]

    if not words_needing_scene:
        duration = time.time() - start
        _log_step(
            job, GenerationJobLog.Step.CREATIVE_DIRECTION,
            GenerationJob.Status.COMPLETED,
            duration=duration,
            output_data={'scenes_generated': 0, 'skipped': len(words)},
        )
        return

    # Group words by creative direction template
    groups: dict[str, list] = {'character': [], 'action': [], 'elemental': []}
    for word in words_needing_scene:
        group = _CATEGORY_TO_GROUP.get(word.image_category, 'elemental')
        groups[group].append(word)

    total_scenes = 0
    for group_name, group_words in groups.items():
        if not group_words:
            continue

        template = load_prompt_template(f'creative_direction_{group_name}')

        words_json = json.dumps([
            {
                'term': w.text,
                'definition': defn_map[w.id].definition_text,
            }
            for w in group_words
        ], indent=2)

        prompt_text = template.replace('{words_json}', words_json)
        result = call_gemini(model, prompt_text, '')

        scenes = result.get('scenes', [])
        scene_map = {}
        for scene_item in scenes:
            term = scene_item.get('term') if isinstance(scene_item, dict) else None
            visual_scene = (
                scene_item.get('visual_scene') if isinstance(scene_item, dict) else None
            )
            if not term or not visual_scene:
                logger.warning(
                    "Skipping malformed creative direction scene for group '%s': %s",
                    group_name, scene_item,
                )
                continue
            scene_map[term.lower()] = visual_scene

        for w in group_words:
            scene = scene_map.get(w.text.lower(), '')
            if scene:
                defn = defn_map[w.id]
                defn.visual_scene = scene
                defn.save(update_fields=['visual_scene'])
                total_scenes += 1

    duration = time.time() - start
    _log_step(
        job, GenerationJobLog.Step.CREATIVE_DIRECTION,
        GenerationJob.Status.COMPLETED,
        duration=duration,
        output_data={
            'scenes_generated': total_scenes,
            'total_words': len(words),
        },
    )


def _step_generate_images(job, words):
    """
    Step 8: Generate images for each word via OpenAI GPT-Image-2.

    Continues on individual image failures — partial success is acceptable.
    """
    _log_step(
        job, GenerationJobLog.Step.IMAGE_GEN,
        GenerationJob.Status.RUNNING,
        output_data={'message': 'Starting image generation'},
    )
    start = time.time()
    created_count = 0
    failed_words = []

    # Batch lookups to avoid N+1 queries
    defn_map = {}
    for d in WordDefinition.objects.filter(word__in=words).order_by('word_id', 'id'):
        defn_map.setdefault(d.word_id, d)
    already_approved = set(
        GeneratedImage.objects.filter(
            word__in=words, status=GeneratedImage.Status.APPROVED
        ).values_list('word_id', flat=True)
    )

    for word in words:
        if word.id in already_approved:
            created_count += 1
            continue

        defn = defn_map.get(word.id)
        definition_text = defn.definition_text if defn else word.text
        visual_scene = defn.visual_scene if defn else ''

        if visual_scene:
            template = load_prompt_template('image_master_style')
            prompt = template.format(
                word=word.text,
                definition=definition_text,
                visual_scene=visual_scene,
            )
        else:
            template = load_prompt_template('image_generation')
            prompt = template.format(word=word.text, definition=definition_text)

        try:
            image_bytes = call_openai_image(prompt)

            filename = f"{word.text.lower().replace(' ', '_')}_{word.id}.png"
            image_file = ContentFile(image_bytes, name=filename)

            GeneratedImage.objects.create(
                word=word,
                image=image_file,
                prompt_used=prompt,
                status=GeneratedImage.Status.APPROVED,
            )
            created_count += 1

        except Exception as exc:
            logger.warning(
                "Image generation failed for word '%s': %s", word.text, exc,
            )
            failed_words.append(word.text)
            continue

    job.images_created = created_count
    job.save(update_fields=['images_created'])

    duration = time.time() - start

    if created_count == 0 and len(words) > 0:
        _log_step(
            job, GenerationJobLog.Step.IMAGE_GEN,
            GenerationJob.Status.FAILED,
            duration=duration,
            output_data={'images_created': 0, 'failed_words': failed_words},
            error_message=f"All {len(words)} image generations failed.",
        )
        raise RuntimeError(
            f"Image generation failed for all {len(words)} words: {', '.join(failed_words)}"
        )

    _log_step(
        job, GenerationJobLog.Step.IMAGE_GEN,
        GenerationJob.Status.COMPLETED,
        duration=duration,
        output_data={
            'images_created': created_count,
            'failed_words': failed_words,
        },
    )


def _step_generate_picture_match_questions(job, words, packs):
    """
    Step 9: Generate PICTURE_WORD_MATCH questions for each word that has an
    approved generated image.

    Question stem: the word's definition + its image.
    Options: 4 word terms — 1 correct, up to 2 pack-mates, 1 random outside word.
    Suitable mastery level: 1 (Recognition).
    """


    start = time.time()
    created_count = 0

    # Build pack membership map: word_id → list of pack-mate Word objects
    pack_mates_map = {}  # word_id -> [Word, ...] (excluding self)
    for pack in packs:
        pack_items = list(pack.items.select_related('word').all())
        pack_word_objs = [item.word for item in pack_items]
        for word_obj in pack_word_objs:
            pack_mates_map[word_obj.id] = [w for w in pack_word_objs if w.id != word_obj.id]

    # Fetch all word ids in this word set for exclusion when picking outside words
    word_set_ids = set(w.id for w in words)

    # Batch lookups to avoid N+1 queries
    approved_images = {
        img.word_id: img
        for img in GeneratedImage.objects.filter(
            word__in=words, status=GeneratedImage.Status.APPROVED
        )
    }
    defn_map = {}
    for d in WordDefinition.objects.filter(word__in=words).order_by('word_id', 'id'):
        defn_map.setdefault(d.word_id, d)

    # Pre-fetch a pool of outside distractor words (avoids per-word ORDER BY RANDOM())
    outside_pool = list(
        Word.objects.exclude(id__in=word_set_ids).order_by('?')[:50]
    )

    # Level 1 MasteryLevel object
    try:
        level1 = MasteryLevel.objects.get(level_id=1)
    except MasteryLevel.DoesNotExist:
        level1 = None

    outside_idx = 0
    for word in words:
        image = approved_images.get(word.id)
        if not image:
            continue

        defn = defn_map.get(word.id)
        if not defn:
            continue
        definition_text = defn.definition_text

        # Build distractor pool from pack-mates (up to 2)
        mates = list(pack_mates_map.get(word.id, []))
        random.shuffle(mates)
        distractors = mates[:2]

        # Add 1 random word from outside the word set (from pre-fetched pool)
        if outside_pool:
            distractors.append(outside_pool[outside_idx % len(outside_pool)])
            outside_idx += 1

        # If still need more distractors (pack has < 2 mates), fill from pool
        if len(distractors) < 3 and outside_pool:
            existing_ids = {d.id for d in distractors} | {word.id}
            for w in outside_pool:
                if w.id not in existing_ids and len(distractors) < 3:
                    distractors.append(w)
                    existing_ids.add(w.id)

        # Build options: correct answer + distractors, shuffled
        all_options = [word.text] + [d.text for d in distractors]
        random.shuffle(all_options)

        question_text = definition_text

        question = Question.objects.create(
            word=word,
            question_type=Question.QuestionType.PICTURE_WORD_MATCH,
            question_text=question_text,
            options=all_options,
            correct_answers=[word.text],
            explanation=f"The image shows '{word.text}', which means: {definition_text}",
            example_sentence='',
            lexile_score=_content_lexile(job),
            generation_job=job,
        )

        if level1:
            question.suitable_levels.add(level1)

        created_count += 1

    duration = time.time() - start
    _log_step(
        job, GenerationJobLog.Step.PICTURE_MATCH_GEN,
        GenerationJob.Status.COMPLETED,
        duration=duration,
        output_data={'questions_created': created_count},
    )
    logger.info("Picture-word match: created %d questions", created_count)
