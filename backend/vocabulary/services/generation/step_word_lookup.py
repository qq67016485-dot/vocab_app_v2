"""Pipeline steps 1-2: Word Lookup and Dedup & Persist."""
import logging
import time

from django.conf import settings

from vocabulary.models import (
    Word, WordDefinition, DefinitionEmbedding,
    GenerationJob, GenerationJobLog,
)
import vocabulary.services.embedding_service as _embedding_service
import vocabulary.services.llm_service as _llm_service
from vocabulary.services.generation.helpers import (
    _content_lexile, _log_step, _log_metadata,
    _call_llm_with_config,
)

logger = logging.getLogger(__name__)


def _validate_word_lookup_result(job, words_data):
    if len(words_data) != len(job.input_words):
        raise ValueError(
            f"Word lookup must return one result per input word; "
            f"expected {len(job.input_words)}, got {len(words_data)}."
        )
    seen_terms = set()
    for idx, wd in enumerate(words_data, 1):
        term = (wd.get('term') or '').strip()
        if not term:
            raise ValueError(f"Word lookup result {idx} is missing term.")
        term_key = term.lower()
        if term_key in seen_terms:
            raise ValueError(f"Word lookup returned duplicate term '{term}'.")
        seen_terms.add(term_key)
        if not (wd.get('definition') or '').strip():
            raise ValueError(f"Word lookup result for '{term}' is missing definition.")
        if not (wd.get('example_sentence') or '').strip():
            raise ValueError(f"Word lookup result for '{term}' is missing example_sentence.")



def _latest_dedup_word_snapshots(job):
    log = (
        job.logs.filter(
            step=GenerationJobLog.Step.DEDUP,
            status=GenerationJob.Status.COMPLETED,
            output_data__word_snapshots__isnull=False,
        )
        .order_by('-created_at')
        .first()
    )
    if not log or not isinstance(log.output_data, dict):
        return []
    return log.output_data.get('word_snapshots') or []


def _latest_word_lookup_snapshot(job):
    """Retrieve word_lookup_snapshot from the most recent completed WORD_LOOKUP log."""
    log = (
        job.logs.filter(
            step=GenerationJobLog.Step.WORD_LOOKUP,
            status=GenerationJob.Status.COMPLETED,
        )
        .order_by('-created_at')
        .first()
    )
    if not log or not isinstance(log.output_data, dict):
        return []
    return log.output_data.get('word_lookup_snapshot') or []


def _snapshots_to_words_data(snapshots):
    return [
        {
            'term': snapshot.get('term', ''),
            'part_of_speech': snapshot.get('part_of_speech', ''),
            'definition': snapshot.get('definition', ''),
            'example_sentence': snapshot.get('example_sentence', ''),
            'lexile_score': snapshot.get('lexile_score'),
        }
        for snapshot in snapshots
    ]


def _definition_for_snapshot(word, incoming_definition):
    exact_match = word.definitions.filter(definition_text=incoming_definition).first()
    return exact_match or word.definitions.first()


def _step_word_lookup(job, site_config=None):
    """Step 1: Call LLM to look up definitions for the input word list."""
    if site_config is None:
        from vocabulary.services.generation.llm_config_service import get_step_config
        site_config = get_step_config('word_lookup')['primary']
    start = time.time()
    try:
        template = _llm_service.load_prompt_template('word_lookup')
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

        result = _call_llm_with_config(site_config, template, user_prompt)
        words_data = result.get('words', [])
        _validate_word_lookup_result(job, words_data)

        duration = time.time() - start
        _log_step(
            job, GenerationJobLog.Step.WORD_LOOKUP,
            GenerationJob.Status.COMPLETED,
            duration=duration,
            input_data={'words': job.input_words},
            output_data=_log_metadata(
                model=site_config['model'],
                prompt_template='word_lookup',
                prompt_text=template,
                words_returned=len(words_data),
                word_lookup_snapshot=[
                    {
                        'term': wd.get('term', ''),
                        'part_of_speech': wd.get('part_of_speech', ''),
                        'definition': wd.get('definition', ''),
                        'example_sentence': wd.get('example_sentence', ''),
                        'lexile_score': wd.get('lexile_score'),
                    }
                    for wd in words_data
                ],
            ),
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
    """
    start = time.time()
    words = []
    word_snapshots = []
    new_count = 0

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

        existing = _embedding_service.find_duplicate_definition(term, pos, definition)
        if existing:
            logger.info("Dedup: reusing existing Word '%s' (id=%s)", term, existing.id)
            words.append(existing)
            job.word_set.words.add(existing)
            defn = _definition_for_snapshot(existing, wd.get('definition', ''))
            word_snapshots.append({
                'term': existing.text,
                'word_id': existing.id,
                'definition_id': defn.id if defn else None,
                'part_of_speech': existing.part_of_speech,
                'definition': defn.definition_text if defn else wd.get('definition', ''),
                'example_sentence': defn.example_sentence if defn else wd.get('example_sentence', ''),
                'lexile_score': defn.lexile_score if defn else wd.get('lexile_score'),
            })
            continue

        source_context = ''
        if job.input_source_title:
            source_context = f"From {job.input_source_title}"
            if job.input_source_chapter:
                source_context += f", {job.input_source_chapter}"

        word = Word.objects.create(
            text=term,
            part_of_speech=pos,
            source_context=source_context,
        )

        defn = WordDefinition.objects.create(
            word=word,
            definition_text=definition,
            example_sentence=wd.get('example_sentence', ''),
            lexile_score=wd.get('lexile_score'),
        )

        embedding_vector = _embedding_service.get_embedding(definition)
        DefinitionEmbedding.objects.create(
            definition=defn,
            embedding=embedding_vector,
            model_version=settings.QWEN_EMBEDDING_MODEL,
        )

        job.word_set.words.add(word)
        words.append(word)
        word_snapshots.append({
            'term': word.text,
            'word_id': word.id,
            'definition_id': defn.id,
            'part_of_speech': word.part_of_speech,
            'definition': defn.definition_text,
            'example_sentence': defn.example_sentence,
            'lexile_score': defn.lexile_score,
        })
        new_count += 1

    job.words_created = new_count
    job.save(update_fields=['words_created'])

    job.input_words = [w.text for w in words]
    job.save(update_fields=['input_words'])

    duration = time.time() - start
    _log_step(
        job, GenerationJobLog.Step.DEDUP,
        GenerationJob.Status.COMPLETED,
        duration=duration,
        output_data={
            'new_words': new_count,
            'total': len(words),
            'word_snapshots': word_snapshots,
        },
    )

    return words
