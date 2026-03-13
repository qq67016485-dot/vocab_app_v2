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
import logging
import time
import math

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.utils import timezone

from vocabulary.models import (
    Word, WordDefinition, DefinitionEmbedding, Translation,
    Question, MasteryLevel, WordSet, WordPack, WordPackItem, PrimerCardContent,
    MicroStory, ClozeItem, GeneratedImage,
    GenerationJob, GenerationJobLog,
)
from vocabulary.services.llm_service import (
    call_anthropic, call_gemini, call_gemini_image, load_prompt_template,
)
from vocabulary.services.embedding_service import (
    get_embedding, find_duplicate_definition,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = 'gemini-3.1-pro-preview'


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
    GenerationJobLog.Step.STORY_CLOZE_GEN,
    GenerationJobLog.Step.IMAGE_GEN,
]


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


def _run_step(job, step, words, words_data, packs):
    """Dispatch a single pipeline step. Returns updated (words, words_data, packs)."""
    S = GenerationJobLog.Step
    if step == S.WORD_LOOKUP:
        words_data = _step_word_lookup(job)
    elif step == S.DEDUP:
        words = _step_dedup_and_persist(job, words_data)
    elif step == S.TRANSLATION:
        _step_generate_translations(job, words, words_data)
    elif step == S.QUESTION_GEN:
        _step_generate_questions(job, words, words_data)
    elif step == S.PACK_CREATION:
        packs = _step_auto_create_packs(job, words, words_data)
    elif step == S.PRIMER_GEN:
        _step_generate_primers(job, words, words_data)
    elif step == S.STORY_CLOZE_GEN:
        _step_generate_stories_and_cloze(job, packs, words_data)
    elif step == S.IMAGE_GEN:
        _step_generate_images(job, words)
    return words, words_data, packs


def run_full_pipeline(job_id):
    """
    Main entry point. Runs all pipeline steps sequentially.
    Tracks last_completed_step and updates word_set.generation_status.
    """
    job = GenerationJob.objects.select_related('word_set').get(id=job_id)
    job.status = GenerationJob.Status.RUNNING
    job.error_message = ''
    job.save(update_fields=['status', 'error_message'])

    # Clear any existing words from the word_set to avoid duplicates on re-run
    job.word_set.words.clear()

    words, words_data, packs = [], [], []

    try:
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
        logger.exception("Pipeline failed for job %s at step %s: %s", job_id, job.last_completed_step, exc)
        job.status = GenerationJob.Status.FAILED
        job.error_message = str(exc)
        job.save(update_fields=['status', 'error_message'])

        job.word_set.generation_status = WordSet.GenerationStatus.TO_GENERATE
        job.word_set.save(update_fields=['generation_status'])


def resume_pipeline(job_id):
    """
    Resume a failed pipeline from the step after last_completed_step.
    Reconstructs intermediate state from DB.
    """
    job = GenerationJob.objects.select_related('word_set').get(id=job_id)
    if job.status != GenerationJob.Status.FAILED:
        raise ValueError(f"Job {job_id} is not in FAILED status (current: {job.status})")

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

    try:
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
        logger.exception("Resume failed for job %s at step %s: %s", job_id, job.last_completed_step, exc)
        job.status = GenerationJob.Status.FAILED
        job.error_message = str(exc)
        job.save(update_fields=['status', 'error_message'])

        job.word_set.generation_status = WordSet.GenerationStatus.TO_GENERATE
        job.word_set.save(update_fields=['generation_status'])


def _step_word_lookup(job):
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
            f"Source: {job.input_source_title}"
        )
        if job.input_source_chapter:
            user_prompt += f", Chapter: {job.input_source_chapter}"
        if job.input_source_text:
            user_prompt += f"\n\nSource passage:\n{job.input_source_text}"

        result = call_gemini(DEFAULT_MODEL, template, user_prompt)
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

    for wd in words_data:
        term = wd['term']
        pos = wd.get('part_of_speech', '')
        definition = wd.get('definition', '')

        # Check for existing duplicate
        existing = find_duplicate_definition(term, pos, definition)
        if existing:
            logger.info("Dedup: reusing existing Word '%s' (id=%s)", term, existing.id)
            words.append(existing)
            job.word_set.words.add(existing)
            continue

        # Create new Word
        word = Word.objects.create(
            text=term,
            part_of_speech=pos,
            source_context=wd.get('source_context', ''),
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


def _step_generate_translations(job, words, words_data):
    """
    Step 3: Call LLM to generate translations for definitions and examples.

    Creates Translation records using Django's GenericForeignKey.
    """
    start = time.time()
    try:
        template = load_prompt_template('translation')
        target_language = job.target_language

        # Build items to translate
        items_list = []
        for wd in words_data:
            items_list.append(f"- definition_text: {wd.get('definition', '')}")
            example = wd.get('example_sentence', '')
            if example:
                items_list.append(f"- example_sentence: {example}")

        items_str = '\n'.join(items_list)
        prompt = template.format(
            target_language=target_language,
            items_to_translate=items_str,
        )

        result = call_gemini(DEFAULT_MODEL, prompt, f"Translate to {target_language}")
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


def _step_generate_questions(job, words, words_data):
    """
    Step 4: Call LLM to generate practice questions for each word.

    Uses the v1-style prompt format: sends simplified_words + target_lexile_level as JSON,
    expects generated_question_sets back with enriched word data + questions.
    Batches words into groups of QUESTION_BATCH_SIZE to keep error rates low.
    """
    start = time.time()
    try:
        import json as _json
        template = load_prompt_template('question_generation')

        # Build simplified word list
        simplified_words = []
        for wd in words_data:
            simplified_words.append({
                'term': wd['term'],
                'part_of_speech': wd.get('part_of_speech', ''),
                'simple_definition': wd.get('definition', ''),
            })

        # Split into batches of QUESTION_BATCH_SIZE
        batches = [
            simplified_words[i:i + QUESTION_BATCH_SIZE]
            for i in range(0, len(simplified_words), QUESTION_BATCH_SIZE)
        ]

        word_map = {w.text.lower(): w for w in words}
        mastery_levels = {ml.level_id: ml for ml in MasteryLevel.objects.all()}
        created_count = 0
        total_batches = len(batches)

        for batch_idx, batch in enumerate(batches, 1):
            batch_terms = [w['term'] for w in batch]
            logger.info(
                "Question generation batch %d/%d: %s",
                batch_idx, total_batches, ', '.join(batch_terms),
            )

            input_json = _json.dumps({
                'target_lexile_level': job.target_lexile,
                'simplified_words': batch,
            }, indent=2)

            prompt_text = template.replace('{input_json}', input_json)
            result = call_gemini(DEFAULT_MODEL, prompt_text, '')
            question_sets = result.get('generated_question_sets', [])

            for qs in question_sets:
                word_info = qs.get('word', [{}])[0] if qs.get('word') else {}
                term = word_info.get('term', '').lower()
                word = word_map.get(term)
                if not word:
                    logger.warning("Question set for unknown term '%s', skipping", term)
                    continue

                for qd in qs.get('questions', []):
                    options = qd.get('options')
                    if isinstance(options, dict) and 'choices' in options:
                        options = options['choices']

                    question = Question.objects.create(
                        word=word,
                        question_type=qd.get('question_type', 'DEFINITION_MC_SINGLE'),
                        question_text=qd.get('question_text', ''),
                        options=options,
                        correct_answers=qd.get('correct_answers', []),
                        explanation=qd.get('explanation', ''),
                        example_sentence=qd.get('example_sentence', ''),
                        lexile_score=qd.get('lexile_score'),
                        generation_job=job,
                    )

                    for level_num in qd.get('suitable_mastery_levels', []):
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


def _step_auto_create_packs(job, words, words_data):
    """
    Step 5: Use LLM to group words into semantically related packs.
    Falls back to sequential chunking if LLM fails.

    If packs already exist for this word set (incremental add), appends new words
    to existing packs instead of creating duplicates.

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

    # Incremental mode: add new words to existing packs
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
            "Incremental packing: %d added to existing, %d new packs created",
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
        import json as _json
        template = load_prompt_template('pack_grouping')

        # Build word list with definitions for the LLM
        word_info_parts = []
        for wd in words_data:
            word_info_parts.append(
                f"- {wd['term']} ({wd.get('part_of_speech', '')}): {wd.get('definition', '')}"
            )

        prompt_text = template.replace('{pack_size}', str(pack_size))
        user_prompt = '\n'.join(word_info_parts)
        result = call_gemini(DEFAULT_MODEL, prompt_text, user_prompt)
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
            pack = WordPack.objects.create(
                word_set=job.word_set,
                label=pack_data.get('label', f'Pack {i + 1}'),
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


def _step_generate_primers(job, words, words_data):
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
        result = call_gemini(DEFAULT_MODEL, template, user_prompt)
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


def _step_generate_stories_and_cloze(job, packs, words_data):
    """
    Step 7: Call LLM to generate micro story + cloze items for each pack.
    Skips packs that already have stories (incremental add scenario).
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

            word_info = ', '.join(pack_word_texts)
            user_prompt = f"Target words: {word_info}\nTarget Lexile: {job.target_lexile}"
            system_prompt = template.format(target_lexile=job.target_lexile)

            result = call_gemini(DEFAULT_MODEL, system_prompt, user_prompt)

            # Create MicroStory
            story_data = result.get('micro_story', {})
            MicroStory.objects.create(
                pack=pack,
                story_text=story_data.get('story_text', ''),
                reading_level=story_data.get('reading_level', job.target_lexile),
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


def _step_generate_images(job, words):
    """
    Step 8: Call Gemini to generate images for each word.

    Continues on individual image failures — partial success is acceptable.
    """
    start = time.time()
    created_count = 0

    for word in words:
        defn = word.definitions.first()
        definition_text = defn.definition_text if defn else word.text

        prompt = (
            f"Create a simple, colorful illustration for a children's vocabulary card. "
            f"The word is '{word.text}' which means '{definition_text}'. "
            f"The image should be clear, age-appropriate for children aged 8-14, "
            f"and help illustrate the meaning of the word. No text in the image."
        )

        try:
            image_bytes = call_gemini_image(prompt)

            filename = f"{word.text.lower().replace(' ', '_')}_{word.id}.png"
            image_file = ContentFile(image_bytes, name=filename)

            GeneratedImage.objects.create(
                word=word,
                image=image_file,
                prompt_used=prompt,
                status=GeneratedImage.Status.PENDING_REVIEW,
            )
            created_count += 1

        except Exception as exc:
            logger.warning(
                "Image generation failed for word '%s': %s", word.text, exc,
            )
            continue

    job.images_created = created_count
    job.save(update_fields=['images_created'])

    duration = time.time() - start
    _log_step(
        job, GenerationJobLog.Step.IMAGE_GEN,
        GenerationJob.Status.COMPLETED,
        duration=duration,
        output_data={'images_created': created_count},
    )
