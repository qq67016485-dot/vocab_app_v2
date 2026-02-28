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
    Question, WordPack, WordPackItem, PrimerCardContent,
    MicroStory, ClozeItem, GeneratedImage,
    GenerationJob, GenerationJobLog,
)
from vocabulary.services.llm_service import (
    call_anthropic, call_gemini_image, load_prompt_template,
)
from vocabulary.services.embedding_service import (
    get_embedding, find_duplicate_definition,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = 'claude-sonnet-4-20250514'


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


def run_full_pipeline(job_id):
    """
    Main entry point. Runs all pipeline steps sequentially.

    Updates job status to RUNNING → COMPLETED or FAILED.
    """
    job = GenerationJob.objects.get(id=job_id)
    job.status = GenerationJob.Status.RUNNING
    job.save(update_fields=['status'])

    try:
        # Step 1: Word Lookup
        words_data = _step_word_lookup(job)

        # Step 2: Dedup & Persist
        words = _step_dedup_and_persist(job, words_data)

        # Step 3: Translations
        _step_generate_translations(job, words, words_data)

        # Step 4: Questions
        _step_generate_questions(job, words, words_data)

        # Step 5: Auto-create packs
        packs = _step_auto_create_packs(job, words)

        # Step 6: Primers
        _step_generate_primers(job, words, words_data)

        # Step 7: Stories & Cloze
        _step_generate_stories_and_cloze(job, packs, words_data)

        # Step 8: Images
        _step_generate_images(job, words)

        job.status = GenerationJob.Status.COMPLETED
        job.completed_at = timezone.now()
        job.save(update_fields=['status', 'completed_at'])

    except Exception as exc:
        logger.exception("Pipeline failed for job %s: %s", job_id, exc)
        job.status = GenerationJob.Status.FAILED
        job.error_message = str(exc)
        job.save(update_fields=['status', 'error_message'])


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

        result = call_anthropic(DEFAULT_MODEL, template, user_prompt)
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
        )

        job.word_set.words.add(word)
        words.append(word)
        new_count += 1

    job.words_created = new_count
    job.save(update_fields=['words_created'])

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

        result = call_anthropic(DEFAULT_MODEL, prompt, f"Translate to {target_language}")
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


def _step_generate_questions(job, words, words_data):
    """
    Step 4: Call LLM to generate practice questions for each word.
    """
    start = time.time()
    try:
        template = load_prompt_template('question_generation')
        question_types = ', '.join(settings.GENERATION_QUESTION_TYPES)

        # Build word info for the prompt
        word_info_parts = []
        for wd in words_data:
            word_info_parts.append(
                f"- {wd['term']} ({wd.get('part_of_speech', '')}): {wd.get('definition', '')}"
            )

        user_prompt = '\n'.join(word_info_parts)
        system_prompt = template.format(
            target_lexile=job.target_lexile,
            question_types=question_types,
        )

        result = call_anthropic(DEFAULT_MODEL, system_prompt, user_prompt)
        questions_data = result.get('questions', [])

        # Map terms to Word objects
        word_map = {w.text.lower(): w for w in words}
        created_count = 0

        for qd in questions_data:
            term = qd.get('term', '').lower()
            word = word_map.get(term)
            if not word:
                logger.warning("Question for unknown term '%s', skipping", term)
                continue

            Question.objects.create(
                word=word,
                question_type=qd.get('question_type', 'DEFINITION_MC_SINGLE'),
                question_text=qd.get('question_text', ''),
                options=qd.get('options'),
                correct_answers=qd.get('correct_answers', []),
                explanation=qd.get('explanation', ''),
                example_sentence=qd.get('example_sentence', ''),
                lexile_score=qd.get('lexile_score'),
                generation_job=job,
            )
            created_count += 1

        job.questions_created = created_count
        job.save(update_fields=['questions_created'])

        duration = time.time() - start
        _log_step(
            job, GenerationJobLog.Step.QUESTION_GEN,
            GenerationJob.Status.COMPLETED,
            duration=duration,
            output_data={'questions_created': created_count},
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


def _step_auto_create_packs(job, words):
    """
    Step 5: Group words into packs of ~GENERATION_WORDS_PER_PACK.

    Returns:
        list[WordPack]: Created pack objects.
    """
    start = time.time()
    pack_size = settings.GENERATION_WORDS_PER_PACK
    num_packs = max(1, math.ceil(len(words) / pack_size))
    packs = []

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
    """
    start = time.time()
    try:
        template = load_prompt_template('primer_generation')

        # Build word info
        word_info_parts = []
        for wd in words_data:
            word_info_parts.append(
                f"- {wd['term']} ({wd.get('part_of_speech', '')}): {wd.get('definition', '')}"
            )

        user_prompt = '\n'.join(word_info_parts)
        result = call_anthropic(DEFAULT_MODEL, template, user_prompt)
        primers = result.get('primer_cards', [])

        word_map = {w.text.lower(): w for w in words}
        created_count = 0

        for pc in primers:
            term = pc.get('term', '').lower()
            word = word_map.get(term)
            if not word:
                logger.warning("Primer for unknown term '%s', skipping", term)
                continue

            PrimerCardContent.objects.update_or_create(
                word=word,
                defaults={
                    'syllable_text': pc.get('syllable_text', ''),
                    'kid_friendly_definition': pc.get('kid_friendly_definition', ''),
                    'example_sentence': pc.get('example_sentence', ''),
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
    """
    start = time.time()
    try:
        template = load_prompt_template('story_cloze_generation')
        total_stories = 0
        total_cloze = 0

        for pack in packs:
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

            result = call_anthropic(DEFAULT_MODEL, system_prompt, user_prompt)

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

            # Save image to media storage (URL-based for now)
            import base64
            data_url = f"data:image/png;base64,{base64.b64encode(image_bytes).decode()}"

            GeneratedImage.objects.create(
                word=word,
                image_url=data_url,
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
