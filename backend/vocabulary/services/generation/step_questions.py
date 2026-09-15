"""Pipeline step 4: Generate Questions."""
import json
import logging
import random
import string
import time

from vocabulary.models import (
    Question, MasteryLevel,
    GenerationJob, GenerationJobLog,
)
from vocabulary.constants import QUESTION_TYPE_LEVEL
from vocabulary.services.generation.content_reuse import (
    find_reusable_question_words,
)
from vocabulary.services.generation.helpers import (
    _content_lexile, _log_step, _call_llm_with_config,
)
import vocabulary.services.llm_service as _llm_service

logger = logging.getLogger(__name__)

QUESTION_BATCH_SIZE = 2

# Total LLM calls per batch: 1 initial + regenerations when the response
# fails structural validation (see _first_invalid_question).
QUESTION_BATCH_MAX_ATTEMPTS = 3


def _normalize_option_text(text):
    """Normalize an option/answer the way grading does
    (PracticeService.normalize_answer): strip, lowercase, drop punctuation."""
    if not isinstance(text, str):
        text = str(text)
    return text.strip().lower().translate(str.maketrans('', '', string.punctuation))


def _first_invalid_question(question_sets):
    """Return a short description of the first structurally broken question in
    a batch response, or None when every question passes.

    Broken means: fewer than 2 options, duplicated option texts, no correct
    answer, or a correct answer that is not among the options. Grading is an
    exact match against correct_answers, so an answer missing from the options
    makes the item impossible to ever grade correct — catch it here and
    regenerate the batch instead of persisting ungradeable items.
    """
    for qs in question_sets:
        term = qs.get('term', '')
        for qd in qs.get('questions', []):
            options = qd.get('options')
            if isinstance(options, dict) and 'choices' in options:
                options = options['choices']
            if not isinstance(options, list) or len(options) < 2:
                return f"'{term}' question has fewer than 2 options"
            normalized = [_normalize_option_text(o) for o in options]
            if len(set(normalized)) != len(normalized):
                return f"'{term}' question has duplicate options: {options!r}"
            correct_answers = qd.get('correct_answers') or []
            if not correct_answers:
                return f"'{term}' question has no correct answer"
            for answer in correct_answers:
                if _normalize_option_text(answer) not in normalized:
                    return (
                        f"'{term}' correct answer {answer!r} is not among "
                        f"the options {options!r}"
                    )
    return None


def _step_generate_questions(job, words, words_data, site_config=None, allow_reuse=True):
    """
    Step 4: Call LLM to generate practice questions for each word.

    Uses two alternating prompts (A/B) chosen randomly per batch for variety.
    Batches words into groups of QUESTION_BATCH_SIZE to keep error rates low.
    Each batch's questions are validated before persisting (correct answer
    among the options, no duplicated options); a batch that fails validation
    is regenerated in place, up to QUESTION_BATCH_MAX_ATTEMPTS calls.

    Idempotent at word granularity: questions created by a batch are committed
    immediately (no surrounding transaction), so when a later batch fails and the
    job is resumed/retried, words that already have questions for this job are
    skipped instead of regenerated. This avoids wasted LLM calls and duplicate
    questions on resume.

    Cross-wordset reuse (``allow_reuse``): a word whose prior jobs inside the
    Lexile reuse window already produced full question coverage is skipped too
    (practice serves questions by word, job-agnostically). Restart passes
    ``allow_reuse=False`` so an explicit rerun always regenerates.
    """
    if site_config is None:
        from vocabulary.services.generation.llm_config_service import get_step_config
        site_config = get_step_config('question_gen')['primary']
    start = time.time()
    try:
        templates = {
            'A': _llm_service.load_prompt_template('question_generation_A'),
            'B': _llm_service.load_prompt_template('question_generation_B'),
        }

        word_list = []
        for wd in words_data:
            word_list.append({
                'term': wd['term'],
                'part_of_speech': wd.get('part_of_speech', ''),
                'definition': wd.get('definition', ''),
                'example_sentence': wd.get('example_sentence', ''),
            })

        batches = [
            word_list[i:i + QUESTION_BATCH_SIZE]
            for i in range(0, len(word_list), QUESTION_BATCH_SIZE)
        ]

        word_map = {w.text.lower(): w for w in words}
        mastery_levels = {ml.level_id: ml for ml in MasteryLevel.objects.all()}
        total_batches = len(batches)
        skipped_batches = 0

        # Words that already have questions from a prior run of this job. A batch
        # whose words are all present here succeeded earlier and is skipped on
        # resume. Words with full question coverage from a prior in-window job
        # (dedup attached the shared word) are reused: they are skipped as well,
        # and only the uncovered words of a mixed batch are sent to the LLM.
        completed_word_ids = set(
            Question.objects.filter(generation_job=job)
            .values_list('word_id', flat=True).distinct()
        )
        reusable_word_ids = (
            find_reusable_question_words(words, _content_lexile(job))
            if allow_reuse else set()
        ) - completed_word_ids
        if reusable_word_ids:
            logger.info(
                "Question generation reusing existing questions for %d word(s) "
                "from prior in-window jobs.", len(reusable_word_ids),
            )
        covered_word_ids = completed_word_ids | reusable_word_ids

        for batch_idx, batch in enumerate(batches, 1):
            batch_terms = [w['term'] for w in batch]

            pending = [
                w for w in batch
                if (w['term'].lower() in word_map
                    and word_map[w['term'].lower()].id not in covered_word_ids)
            ]

            if not pending:
                skipped_batches += 1
                logger.info(
                    "Question generation batch %d/%d already complete; skipping: %s",
                    batch_idx, total_batches, ', '.join(batch_terms),
                )
                continue

            input_json = json.dumps({
                'target_lexile_level': _content_lexile(job),
                'words': pending,
            }, indent=2)

            # Regenerate the batch in place when the response fails structural
            # validation (ungradeable or ambiguous items). Validation errors
            # are deterministic-classified by the queue runner, so without
            # these in-step attempts a bad batch would park the job FAILED
            # until a manual restart.
            question_sets = []
            for attempt in range(1, QUESTION_BATCH_MAX_ATTEMPTS + 1):
                prompt_label = random.choice(['A', 'B'])
                template = templates[prompt_label]
                logger.info(
                    "Question generation batch %d/%d (prompt %s, attempt %d/%d): %s",
                    batch_idx, total_batches, prompt_label, attempt,
                    QUESTION_BATCH_MAX_ATTEMPTS,
                    ', '.join(w['term'] for w in pending),
                )
                prompt_text = template.replace('{input_json}', input_json)
                result = _call_llm_with_config(site_config, prompt_text, '')
                question_sets = result.get('generated_question_sets', [])
                invalid_reason = _first_invalid_question(question_sets)
                if invalid_reason is None:
                    break
                logger.warning(
                    "Question generation batch %d/%d attempt %d/%d failed "
                    "validation: %s",
                    batch_idx, total_batches, attempt,
                    QUESTION_BATCH_MAX_ATTEMPTS, invalid_reason,
                )
            else:
                raise ValueError(
                    f"Question generation batch {batch_idx} failed validation "
                    f"after {QUESTION_BATCH_MAX_ATTEMPTS} attempts: "
                    f"{invalid_reason}"
                )

            persisted_terms = set()
            for qs in question_sets:
                term = qs.get('term', '').lower()
                word = word_map.get(term)
                if not word:
                    logger.warning("Question set for unknown term '%s', skipping", term)
                    continue

                questions = qs.get('questions', [])
                for qd in questions:
                    options = qd.get('options')
                    if isinstance(options, dict) and 'choices' in options:
                        options = options['choices']

                    q_type = (qd.get('question_type') or 'DEFINITION_MC_SINGLE').strip()
                    level = mastery_levels.get(QUESTION_TYPE_LEVEL.get(q_type))
                    if level is None:
                        # Persisting anyway would create a question no mastery
                        # level ever serves — invisible to students, with the
                        # step still reporting success. Fail the batch so the
                        # normal retry path regenerates it.
                        raise ValueError(
                            f"Question for '{term}' has question_type '{q_type}' "
                            f"with no servable mastery level (unmapped type or "
                            f"missing MasteryLevel row)."
                        )

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
                    question.suitable_levels.add(level)

                if questions:
                    persisted_terms.add(term)

            # Every word sent in the batch must have come back with questions;
            # a silently dropped word would otherwise never be retried (resume
            # tracks per-word rows, not batch expectations).
            expected_terms = {w['term'].lower() for w in pending}
            missing_terms = expected_terms - persisted_terms
            if missing_terms:
                raise ValueError(
                    f"Question generation batch {batch_idx} returned no "
                    f"questions for: {', '.join(sorted(missing_terms))}"
                )

        # Count all questions for the job (including batches skipped this run) so
        # the counter is correct whether this was a fresh run or a resume.
        created_count = Question.objects.filter(generation_job=job).count()
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
                'batches_skipped': skipped_batches,
                'words_reused': len(reusable_word_ids),
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
