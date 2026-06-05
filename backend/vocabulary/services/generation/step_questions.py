"""Pipeline step 4: Generate Questions."""
import json
import logging
import random
import time

from vocabulary.models import (
    Question, MasteryLevel,
    GenerationJob, GenerationJobLog,
)
from vocabulary.constants import QUESTION_TYPE_LEVEL
from vocabulary.services.generation.helpers import (
    _content_lexile, _log_step, _call_llm_with_config,
)
import vocabulary.services.llm_service as _llm_service

logger = logging.getLogger(__name__)

QUESTION_BATCH_SIZE = 2


def _step_generate_questions(job, words, words_data, site_config=None):
    """
    Step 4: Call LLM to generate practice questions for each word.

    Uses two alternating prompts (A/B) chosen randomly per batch for variety.
    Batches words into groups of QUESTION_BATCH_SIZE to keep error rates low.

    Idempotent at batch granularity: questions created by a batch are committed
    immediately (no surrounding transaction), so when a later batch fails and the
    job is resumed/retried, batches whose words already have questions for this
    job are skipped instead of regenerated. This avoids wasted LLM calls and
    duplicate questions on resume.
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
        # resume; a batch with only some present is a partial prior attempt and
        # gets its stale rows cleared before regeneration to avoid duplicates.
        completed_word_ids = set(
            Question.objects.filter(generation_job=job)
            .values_list('word_id', flat=True).distinct()
        )

        for batch_idx, batch in enumerate(batches, 1):
            batch_terms = [w['term'] for w in batch]
            batch_word_ids = {
                word_map[t.lower()].id for t in batch_terms if t.lower() in word_map
            }

            if batch_word_ids and batch_word_ids.issubset(completed_word_ids):
                skipped_batches += 1
                logger.info(
                    "Question generation batch %d/%d already complete; skipping: %s",
                    batch_idx, total_batches, ', '.join(batch_terms),
                )
                continue

            partial_word_ids = batch_word_ids & completed_word_ids
            if partial_word_ids:
                Question.objects.filter(
                    generation_job=job, word_id__in=partial_word_ids,
                ).delete()

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
            result = _call_llm_with_config(site_config, prompt_text, '')
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
