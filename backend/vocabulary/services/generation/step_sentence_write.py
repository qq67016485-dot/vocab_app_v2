"""Pipeline step: Generate sentence-writing (productive) questions.

Runs after QUESTION_GEN. For each word it produces two productive tasks — a
guided task at mastery Level 4 (scenario + sentence starter) and an open task at
Level 5 (light scenario, no starter) — each from its own prompt. These questions
carry no closed ``correct_answers``; at answer time an LLM judges the student's
sentence (see services/sentence_evaluation_service.py). See
docs/feature_plan/design-sentence-writing-questions.md.

Idempotent at word granularity: a word already having a question of a given
sentence-write type for this job is skipped on resume. No wrapping transaction —
each word's rows commit as its batch succeeds, mirroring step_questions.
"""
import json
import logging
import time

from vocabulary.models import (
    Question, MasteryLevel,
    GenerationJob, GenerationJobLog,
)
from vocabulary.constants import QUESTION_TYPE_LEVEL
from vocabulary.services.generation.constants import (
    SENTENCE_WRITE_BATCH_SIZE, SENTENCE_WRITE_GUIDED_ONLY_MAX_LEXILE,
)
from vocabulary.services.generation.helpers import (
    _content_lexile, _log_step, _call_llm_with_config,
)
import vocabulary.services.llm_service as _llm_service

logger = logging.getLogger(__name__)

# (question_type, prompt template) pairs generated per word. Guided → L4,
# Open → L5; the level itself comes from QUESTION_TYPE_LEVEL.
_VARIANTS = [
    (Question.QuestionType.SENTENCE_WRITE_GUIDED, 'sentence_write_guided'),
    (Question.QuestionType.SENTENCE_WRITE_OPEN, 'sentence_write_open'),
]


def _step_generate_sentence_write(job, words, words_data, site_config=None):
    """Generate the two sentence-writing questions per word.

    ``site_config`` is the ``sentence_write_gen`` primary config; the orchestrator
    supplies it and the retry/fallback plan.
    """
    if site_config is None:
        from vocabulary.services.generation.llm_config_service import get_step_config
        site_config = get_step_config('sentence_write_gen')['primary']
    start = time.time()
    try:
        target_lexile = _content_lexile(job)
        # At/below the threshold, only the guided variant is produced, and it is
        # served at both L4 and L5 (open/unscaffolded production is withheld from
        # lower-proficiency readers). See constants for the rationale.
        guided_only = target_lexile <= SENTENCE_WRITE_GUIDED_ONLY_MAX_LEXILE
        word_map = {w.text.lower(): w for w in words}
        mastery_levels = {ml.level_id: ml for ml in MasteryLevel.objects.all()}
        open_level_num = QUESTION_TYPE_LEVEL.get(
            Question.QuestionType.SENTENCE_WRITE_OPEN
        )

        word_list = [
            {
                'term': wd['term'],
                'part_of_speech': wd.get('part_of_speech', ''),
                'definition': wd.get('definition', ''),
                'example_sentence': wd.get('example_sentence', ''),
            }
            for wd in words_data
        ]

        total_batches = 0
        skipped_batches = 0

        for q_type, template_name in _VARIANTS:
            if guided_only and q_type == Question.QuestionType.SENTENCE_WRITE_OPEN:
                logger.info(
                    "Sentence-write: content Lexile %s <= %s — skipping OPEN "
                    "variant (guided serves L4 and L5).",
                    target_lexile, SENTENCE_WRITE_GUIDED_ONLY_MAX_LEXILE,
                )
                continue

            template = _llm_service.load_prompt_template(template_name)
            level_num = QUESTION_TYPE_LEVEL.get(q_type)
            task_levels = [mastery_levels[level_num]] if level_num in mastery_levels else []
            # In guided-only mode the guided question doubles as the L5 task.
            if (
                guided_only
                and q_type == Question.QuestionType.SENTENCE_WRITE_GUIDED
                and open_level_num in mastery_levels
                and mastery_levels[open_level_num] not in task_levels
            ):
                task_levels.append(mastery_levels[open_level_num])

            # Words that already have this variant for this job (resume skip).
            completed_word_ids = set(
                Question.objects.filter(
                    generation_job=job, question_type=q_type,
                ).values_list('word_id', flat=True).distinct()
            )

            batches = [
                word_list[i:i + SENTENCE_WRITE_BATCH_SIZE]
                for i in range(0, len(word_list), SENTENCE_WRITE_BATCH_SIZE)
            ]

            for batch_idx, batch in enumerate(batches, 1):
                total_batches += 1
                batch_terms = [w['term'] for w in batch]
                batch_word_ids = {
                    word_map[t.lower()].id for t in batch_terms if t.lower() in word_map
                }

                if batch_word_ids and batch_word_ids.issubset(completed_word_ids):
                    skipped_batches += 1
                    logger.info(
                        "Sentence-write %s batch %d already complete; skipping: %s",
                        q_type, batch_idx, ', '.join(batch_terms),
                    )
                    continue

                # Clear a partial prior attempt for these words before regenerating.
                partial_word_ids = batch_word_ids & completed_word_ids
                if partial_word_ids:
                    Question.objects.filter(
                        generation_job=job, question_type=q_type,
                        word_id__in=partial_word_ids,
                    ).delete()

                # Only send words not already done (a partial batch may mix).
                pending = [
                    w for w in batch
                    if word_map.get(w['term'].lower())
                    and word_map[w['term'].lower()].id not in (
                        completed_word_ids - partial_word_ids
                    )
                ]
                if not pending:
                    skipped_batches += 1
                    continue

                input_json = json.dumps({
                    'target_lexile_level': target_lexile,
                    'words': pending,
                }, indent=2)

                logger.info(
                    "Sentence-write %s batch %d/%d: %s",
                    q_type, batch_idx, len(batches), ', '.join(w['term'] for w in pending),
                )
                result = _call_llm_with_config(site_config, template, input_json)
                tasks = result.get('sentence_tasks', [])

                persisted_terms = _persist_tasks(
                    job, q_type, tasks, word_map, task_levels, target_lexile,
                )

                # Every pending word must have come back with a task; a
                # silently dropped word would otherwise never be retried
                # (resume tracks per-word rows, not batch expectations).
                missing_terms = {
                    w['term'].lower() for w in pending
                } - persisted_terms
                if missing_terms:
                    raise ValueError(
                        f"Sentence-write {q_type} batch {batch_idx} returned "
                        f"no task for: {', '.join(sorted(missing_terms))}"
                    )

        created_count = Question.objects.filter(
            generation_job=job,
            question_type__in=[v[0] for v in _VARIANTS],
        ).count()

        duration = time.time() - start
        _log_step(
            job, GenerationJobLog.Step.SENTENCE_WRITE_GEN,
            GenerationJob.Status.COMPLETED,
            duration=duration,
            output_data={
                'sentence_questions_created': created_count,
                'batches': total_batches,
                'batches_skipped': skipped_batches,
            },
        )

    except Exception as exc:
        duration = time.time() - start
        _log_step(
            job, GenerationJobLog.Step.SENTENCE_WRITE_GEN,
            GenerationJob.Status.FAILED,
            duration=duration,
            error_message=str(exc),
        )
        raise


def _persist_tasks(job, q_type, tasks, word_map, mastery_levels_to_add, target_lexile):
    """Create Question rows from the LLM's ``sentence_tasks`` for one variant.

    ``mastery_levels_to_add`` is the list of MasteryLevel rows to attach as
    ``suitable_levels`` (usually one; the guided variant gets both L4 and L5 in
    guided-only mode).

    Returns the set of lowercased terms a row was created for, so the caller
    can verify batch coverage.
    """
    persisted_terms = set()
    for task in tasks:
        term = (task.get('term') or '').lower()
        word = word_map.get(term)
        if not word:
            logger.warning("Sentence task for unknown term '%s', skipping", term)
            continue

        # Rubric anchors + starter live in options (the student serializer strips
        # the hidden anchors; the judge reads them). correct_answers stays empty —
        # there is no closed answer set.
        options = {
            'intended_sense': task.get('intended_sense', ''),
            'acceptable_use_notes': task.get('acceptable_use_notes', []),
        }
        starter = task.get('sentence_starter')
        if starter:
            options['sentence_starter'] = starter

        lexile = task.get('lexile_score')
        if not isinstance(lexile, int):
            lexile = target_lexile

        question = Question.objects.create(
            word=word,
            question_type=q_type,
            question_text=task.get('scenario', ''),
            options=options,
            correct_answers=[],
            explanation='',
            example_sentence=task.get('model_sentence', ''),
            lexile_score=lexile,
            generation_job=job,
        )
        if mastery_levels_to_add:
            question.suitable_levels.add(*mastery_levels_to_add)
        persisted_terms.add(term)
    return persisted_terms
