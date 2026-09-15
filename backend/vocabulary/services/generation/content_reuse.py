"""Cross-wordset reuse of word-level generated content.

Words are shared across wordsets (``WordSet.words`` M2M) and the dedup step
already attaches an existing ``Word``/``WordDefinition`` when a prior job
generated the same term+sense. This module lets the word-level steps
(QUESTION_GEN, SENTENCE_WRITE_GEN, PRIMER_GEN, TRANSLATION) skip the LLM call
for such words when the existing content was authored at a close enough Lexile
— within +/- ``CONTENT_REUSE_LEXILE_TOLERANCE`` of this job's content Lexile
(``target_lexile x 0.85``).

Pack-level steps never reuse: a graphic novel / infographic binds the pack's
specific word combination.

Provenance: questions derive their authoring Lexile from ``generation_job``
(NULL-job questions are never reused). Primers carry their own
``generated_content_lexile`` stamp. Translations are Lexile-independent — only
the target language matters.
"""
import logging

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db.models import Count

from vocabulary.models import (
    GenerationJob, PrimerCardContent, Question, Translation, WordDefinition,
)
from vocabulary.constants import QUESTION_TYPE_LEVEL
from vocabulary.services.generation.constants import (
    SENTENCE_WRITE_GUIDED_ONLY_MAX_LEXILE,
)
from vocabulary.services.generation.helpers import LEXILE_OFFSET

logger = logging.getLogger(__name__)

# The question-gen prompt contracts for exactly 3 questions per mastery level
# per word; reuse requires the same coverage so a truncated authoring run
# never counts as complete.
QUESTIONS_PER_LEVEL = 3

_SENTENCE_WRITE_TYPES = (
    Question.QuestionType.SENTENCE_WRITE_GUIDED,
    Question.QuestionType.SENTENCE_WRITE_OPEN,
)

# Mastery levels the choice-question step must cover (sentence-write types
# belong to SENTENCE_WRITE_GEN and are excluded).
CHOICE_QUESTION_LEVELS = sorted({
    level for q_type, level in QUESTION_TYPE_LEVEL.items()
    if q_type not in _SENTENCE_WRITE_TYPES
})


def content_lexile_for_target(target_lexile):
    """Content Lexile a job with ``target_lexile`` generates at."""
    return int(target_lexile * LEXILE_OFFSET)


def _tolerance():
    return getattr(settings, 'CONTENT_REUSE_LEXILE_TOLERANCE', 0.15)


def _within_window(authoring_content_lexile, content_lexile):
    if authoring_content_lexile is None:
        return False
    return abs(authoring_content_lexile - content_lexile) <= _tolerance() * content_lexile


def _in_window_job_lexiles(content_lexile):
    """{job_id: authoring content Lexile} for all jobs inside the reuse window."""
    result = {}
    for job_id, target in GenerationJob.objects.values_list('id', 'target_lexile'):
        authoring = content_lexile_for_target(target)
        if _within_window(authoring, content_lexile):
            result[job_id] = authoring
    return result


def find_reusable_question_words(words, content_lexile):
    """Word IDs with full per-level choice-question coverage from in-window jobs.

    "Full coverage" = at least ``QUESTIONS_PER_LEVEL`` non-sentence-write
    questions per mastery level in ``CHOICE_QUESTION_LEVELS``, authored by any
    job whose content Lexile is inside the window (this job included, so a
    resumed run's completed words qualify the same way).
    """
    word_ids = [w.id for w in words]
    job_ids = _in_window_job_lexiles(content_lexile)
    if not word_ids or not job_ids:
        return set()

    counts = (
        Question.objects
        .filter(word_id__in=word_ids, generation_job_id__in=job_ids)
        .exclude(question_type__in=_SENTENCE_WRITE_TYPES)
        .values('word_id', 'suitable_levels__level_id')
        .annotate(n=Count('id'))
    )
    per_word = {}
    for row in counts:
        level = row['suitable_levels__level_id']
        if level is not None:
            per_word.setdefault(row['word_id'], {})[level] = row['n']

    return {
        word_id for word_id, levels in per_word.items()
        if all(levels.get(level, 0) >= QUESTIONS_PER_LEVEL for level in CHOICE_QUESTION_LEVELS)
    }


def find_reusable_sentence_write_words(words, content_lexile, guided_only):
    """{question_type: set(word_ids)} of reusable sentence-write tasks.

    Reuse requires the authoring job to be in-window AND in the same variant
    mode: at/below ``SENTENCE_WRITE_GUIDED_ONLY_MAX_LEXILE`` only the guided
    variant exists (serving both L4 and L5), above it guided serves L4 and open
    serves L5. A cross-mode row carries the wrong variant set, so it never
    qualifies.
    """
    word_ids = [w.id for w in words]
    job_lexiles = _in_window_job_lexiles(content_lexile)
    mode_job_ids = [
        job_id for job_id, authoring in job_lexiles.items()
        if (authoring <= SENTENCE_WRITE_GUIDED_ONLY_MAX_LEXILE) == guided_only
    ]
    out = {q_type: set() for q_type in _SENTENCE_WRITE_TYPES}
    if not word_ids or not mode_job_ids:
        return out

    rows = (
        Question.objects
        .filter(
            word_id__in=word_ids,
            generation_job_id__in=mode_job_ids,
            question_type__in=_SENTENCE_WRITE_TYPES,
            suitable_levels__isnull=False,
        )
        .values('word_id', 'question_type', 'suitable_levels__level_id')
        .distinct()
    )
    levels_per = {}
    for row in rows:
        key = (row['word_id'], row['question_type'])
        levels_per.setdefault(key, set()).add(row['suitable_levels__level_id'])

    guided_level = QUESTION_TYPE_LEVEL[Question.QuestionType.SENTENCE_WRITE_GUIDED]
    open_level = QUESTION_TYPE_LEVEL[Question.QuestionType.SENTENCE_WRITE_OPEN]
    for (word_id, q_type), levels in levels_per.items():
        if q_type == Question.QuestionType.SENTENCE_WRITE_GUIDED:
            needed = {guided_level, open_level} if guided_only else {guided_level}
            if needed <= levels:
                out[q_type].add(word_id)
        elif not guided_only and open_level in levels:
            out[q_type].add(word_id)
    return out


def find_reusable_primer_words(words, content_lexile):
    """Word IDs whose primer was authored inside the reuse window."""
    word_ids = [w.id for w in words]
    if not word_ids:
        return set()
    return {
        row['word_id']
        for row in PrimerCardContent.objects
        .filter(word_id__in=word_ids)
        .values('word_id', 'generated_content_lexile')
        if _within_window(row['generated_content_lexile'], content_lexile)
    }


def resolve_definition(word, word_data):
    """The ``WordDefinition`` of ``word`` this job's ``word_data`` describes.

    Dedup attaches the definition matched by embedding; its text is carried in
    the words_data snapshot, so an exact text match identifies it. Falls back
    to the first definition (lowest Lexile, per model ordering) when the text
    is unavailable — e.g. a hand-built words_data.
    """
    text = (word_data.get('definition') or '').strip()
    if text:
        definition = word.definitions.filter(definition_text=text).first()
        if definition:
            return definition
    return word.definitions.first()


def definition_has_translations(definition, language):
    """Whether ``definition`` already carries the translations the step writes.

    ``definition_text`` is always required; ``example_sentence`` only when the
    definition actually has an example (nothing to translate otherwise).
    """
    needed = {'definition_text'}
    if definition.example_sentence:
        needed.add('example_sentence')
    existing = set(
        Translation.objects.filter(
            content_type=ContentType.objects.get_for_model(WordDefinition),
            object_id=definition.id,
            field_name__in=needed,
            language=language,
        ).values_list('field_name', flat=True)
    )
    return needed <= existing
