# Feature Design: Adaptive Spaced Repetition & Word Relationships

> Based on principles from "The Math Academy Way" (Chapter 18: Spaced Repetition) by Justin Skycak, adapted for vocabulary learning.

## Overview

This document describes three interconnected improvements to the vocab app's spaced repetition system:

1. **Adaptive Intervals + Response Quality** 鈥?per-student-per-word review timing with stable timing baselines (IMPLEMENTED)
2. **Word Relationships** 鈥?knowledge graph connecting related words (PLANNED)
3. **Repetition Compression** 鈥?reducing review load via implicit credit (PLANNED)

---

## 1. Adaptive Intervals + Response Quality (Implemented)

### Problem

The original system used fixed intervals per mastery level. Every student, every word, same schedule, regardless of how easily the student learned the word.

### Solution

Each `UserWordProgress` record has a `learning_speed` float (default 1.0) that acts as a per-student-per-word multiplier on the base interval. First-attempt answer quality can also apply an immediate interval factor once the learner has enough timing history for the exact question type.

Current base schedule:

| Level | Name | Base interval | Promotion threshold | Student-facing behavior |
|---|---:|---:|---:|---|
| 1 | Novice | 1 day | 2 points | Visible |
| 2 | Familiar | 3 days | 4 points | Visible |
| 3 | Confident | 7 days | 7 points | Visible |
| 4 | Proficient | 10 days | 10 points | Visible |
| 5 | Mastered | 17 days | 15 points | Visible |
| 6 | Long-Term Retention | 30 days | 25 points | Hidden; rolled into Mastered |
| 7 | Long-Term Mastery | 60 days | 999 points | Hidden terminal level; rolled into Mastered |

Promotion thresholds are based on accumulated mastery points on the current `UserWordProgress` record; points are not reset when a word promotes. Under normal progression, a word enters level 6 at 15 points, so level 6 -> 7 requires 10 additional correct non-retry answers.

Hidden level behavior:

- Level 6 and 7 words remain in the student-facing Mastered accordion and `/api/student/words-by-level/5/` response.
- Daily/weekly dashboard deltas ignore transitions whose displayed level remains Mastered, such as 5->6, 6->7, 7->6, and 6->5.
- Practice for hidden levels ignores `Question.suitable_levels` and can use any question for the word within the student's Lexile range.

### Algorithm

After each non-retry answer, `PracticeService` classifies the response and updates scheduling:

```
learning_speed = 0.3 * quality + 0.7 * old_learning_speed
next_review_at = now + timedelta(
    days=max(1.0, interval_days * learning_speed * interval_factor)
)
```

- The 0.3 smoothing factor (alpha) means it takes ~3-4 answers for the multiplier to meaningfully shift.
- The 1-day floor prevents same-day repeat reviews.
- Incorrect answers always use the `incorrect` schedule adjustment, even without timing history.
- Correct answers use response-quality classification only when there are at least 15 valid historical first-attempt answers for the same learner and exact `question_type`.
- Timing baselines use the latest 50 persisted `UserAnswer.duration_seconds` values where `1 < duration_seconds < 100`.
- Fast and slow are based on the 25th and 80th percentiles of that per-learner/per-question-type baseline.
- If there are fewer than 15 valid samples, correct answers use `unclassified_correct`, preserving the old correct-answer behavior.

Response-quality rules:

| Response quality | Quality | Interval factor | Notes |
|---|---:|---:|---|
| `fast_correct` | 1.25 | 1.15 | Correct and at/below the 25th percentile |
| `solid_correct` | 1.10 | 1.00 | Correct and between timing thresholds |
| `slow_correct` | 0.85 | 0.85 | Correct and at/above the 80th percentile |
| `switched_correct` | 0.90 | 0.85 | Correct with `answer_switches > 0` |
| `typo_retry_correct` | 0.90 | 0.85 | Correct after server-tracked typo retry |
| `incorrect` | 0.50 | 0.50 | Any incorrect first attempt |
| `unclassified_correct` | 1.20 | 1.00 | Correct without enough timing history |

If multiple correct-answer signals apply, the most conservative quality/factor wins. For example, a fast answer with an answer switch becomes `switched_correct`, not `fast_correct`.

Fragile correct answers (`slow_correct`, `switched_correct`, `typo_retry_correct`) still add mastery points and can still promote. If a fragile answer promotes, the next interval is capped at:

```
old_level_interval_days * old_learning_speed
```

before applying the 1-day floor. This prevents a shaky promoted answer from jumping straight into the longer next-level schedule.

### Behavior examples (starting from learning_speed = 1.0)

| Sequence | Resulting speed | Immediate interval effect |
|---|---|---|
| 3 unclassified correct | 1.0 -> 1.06 -> 1.10 -> 1.13 | Old behavior until enough timing data exists |
| 1 fast correct | 1.0 -> 1.075 | Next interval is additionally multiplied by 1.15 |
| 1 slow correct | 1.0 -> 0.955 | Next interval is additionally multiplied by 0.85 |
| 1 incorrect | 1.0 -> 0.85 | Next interval is additionally multiplied by 0.50, with 1-day floor |

### Schema changes

- `UserWordProgress.next_review_date` (DateField) 鈫?`next_review_at` (DateTimeField) 鈥?enables sub-day precision so the adaptive multiplier has immediate effect rather than requiring rounding to integer days.
- `UserWordProgress.learning_speed` (FloatField, default 1.0) 鈥?the adaptive multiplier.
- Migration `0014_adaptive_intervals` handles the rename, backfill, and new field.
- Response-quality scheduling does not add a new persistence field. It uses existing `UserAnswer.duration_seconds`, `UserAnswer.answer_switches`, and `Question.question_type` history.

### Design decisions

- **Timing quality is gated by stable per-learner/per-question-type data.** The system does not use learner-wide or static timing fallbacks for correct answers. It waits for 15 valid same-question-type samples so early use behaves like the old binary system.
- **Outlier filtering is explicit.** Durations must satisfy `1 < duration_seconds < 100` to enter a timing baseline, reducing abandoned-tab noise.
- **Incorrect answers are always actionable.** Forgetting a word should shorten the schedule even before timing history is available.
- **Typo retries are tracked server-side.** The backend sets a short-lived Django session flag after returning `is_typo=True`; the next first-attempt correct answer for that user/question becomes `typo_retry_correct`.
- **DateTimeField instead of DateField.** With integer-day rounding, the multiplier would need to drift significantly before changing the actual review day. At Level 1 (1-day interval), the speed would need to hit 1.5 before `round(1 脳 1.5) = 2` changes anything. Sub-day precision makes the adaptive effect felt immediately.
- **Retries don't update learning_speed.** The scaffolded retry system (`is_retry=True`) is a teaching mechanism, not an assessment. Only first attempts inform the adaptive model.

---

## 2. Word Relationships (Planned)

### Problem

Words are independent entities. "happy", "unhappy", "happiness" each have their own review schedule with no awareness of their shared root. A student who demonstrates mastery of "unhappiness" has implicitly shown knowledge of "happy", but the system doesn't recognize this.

### Data model

```python
class WordRelationship(models.Model):
    class RelationType(models.TextChoices):
        WORD_FAMILY = 'WORD_FAMILY', 'Word Family'
        SUBSUMES = 'SUBSUMES', 'Subsumes'

    parent_word = models.ForeignKey(
        Word, related_name='child_relationships', on_delete=models.CASCADE,
    )
    child_word = models.ForeignKey(
        Word, related_name='parent_relationships', on_delete=models.CASCADE,
    )
    relation_type = models.CharField(max_length=20, choices=RelationType.choices)
    strength = models.FloatField(
        default=1.0,
        help_text='How strong the implicit credit transfer is (0.0 to 1.0).',
    )

    class Meta:
        unique_together = ('parent_word', 'child_word', 'relation_type')
```

### Relationship types

#### WORD_FAMILY

Words sharing the same lemma (root form). This is the highest-value relationship type.

- Direction: derived/complex form (parent) 鈫?root/simple form (child)
- Examples: "unhappiness" 鈫?"happy", "happiness" 鈫?"happy", "unhappy" 鈫?"happy"
- Default strength: 0.7
- Sibling credit (e.g., "unhappiness" 鈫?"happiness", sharing parent "happy"): strength 0.3鈥?.4

Detection method: **lemmatization** (rule-based, free, no LLM cost).

```python
from nltk.stem import WordNetLemmatizer

def find_word_family_links(new_word, existing_words):
    lemmatizer = WordNetLemmatizer()
    new_lemma = lemmatizer.lemmatize(new_word)
    links = []
    for existing in existing_words:
        if lemmatizer.lemmatize(existing.text) == new_lemma:
            links.append((new_word, existing, 'WORD_FAMILY'))
    return links
```

This runs as a **periodic batch job** (e.g., every few days via management command or cron), not during the generation pipeline or practice sessions. Reason: if "happy" is generated in week 1 and "unhappiness" in week 3, a generation-time scan would miss the relationship because the related word didn't exist yet. A periodic full scan catches relationships in both directions regardless of creation order.

#### SUBSUMES

A harder/rarer synonym that encompasses an easier/more common one. Knowing "irate" implies knowing "mad", but not vice versa.

- Direction: harder word (parent) 鈫?easier word (child)
- Examples: "irate" 鈫?"mad", "ephemeral" 鈫?"temporary"
- Default strength: 0.4

Detection method: **definition embeddings + word frequency**.

The app already stores vector embeddings for every word definition (`DefinitionEmbedding` model). Cosine similarity between definition embeddings detects synonyms more accurately than WordNet synsets because:

- Embeddings are based on the app's actual definition text, not a generic dictionary
- They capture similarity on a continuous scale, not binary "same synset or not"
- They avoid polysemy (WordNet's "mad" = angry OR insane) since embeddings are tied to the specific definition being taught

Once synonyms are identified via embedding similarity, the [`wordfreq`](https://pypi.org/project/wordfreq/) package determines direction. It provides a Zipf frequency score for any English word 鈥?lower frequency = rarer = harder. The rarer synonym becomes the parent.

```python
from wordfreq import zipf_frequency

def determine_subsumes_direction(word_a, word_b):
    """Returns (parent, child) where parent is the harder word."""
    freq_a = zipf_frequency(word_a, 'en')
    freq_b = zipf_frequency(word_b, 'en')
    if freq_a < freq_b:
        return (word_a, word_b)  # a is rarer/harder, subsumes b
    return (word_b, word_a)
```

Word frequency is a strong proxy for difficulty 鈥?it correlates with age of acquisition and Lexile level.

### Relationship types NOT included

- **MORPHOLOGICAL** (shared prefix/suffix across unrelated words, e.g., "un-" in unhappy/unlikely/uncertain) 鈥?too unstable, shared affix doesn't imply shared meaning.
- **SEMANTIC_CLUSTER** (conceptual neighborhood, e.g., weather words) 鈥?too loose for credit transfer.
- **SYNONYM_PAIR** (bidirectional) 鈥?replaced by the directional SUBSUMES type, which better models the asymmetry of vocabulary knowledge.
- **ANTONYM_PAIR** 鈥?knowing "hot" gives weak signal about "cold"; not worth the complexity.

### Credit direction

Credit flows **downward** 鈥?from parent (complex/rare) to child (simple/common):

- Mastering "unhappiness" gives credit to "happy" (WORD_FAMILY, strength 0.7)
- Mastering "irate" gives credit to "mad" (SUBSUMES)
- NOT the reverse: knowing "happy" doesn't imply knowing "unhappiness"

Credit also flows **sideways** between siblings 鈥?words sharing the same lemma/parent, at reduced strength:

- Mastering "unhappiness" gives credit to "happiness" and "unhappy" (siblings, strength 0.3鈥?.4)
- Sibling credit is weaker because the words differ in form/meaning, but the shared root means demonstrating one shows partial knowledge of the other

Sibling relationships are detected automatically by the periodic batch job: any two words that share the same lemma and are not in a direct parent鈫抍hild relationship are siblings. They do not need to be stored as explicit `WordRelationship` records 鈥?the compression algorithm can infer them at query time by finding words with the same lemma.

---

## 3. Repetition Compression (Planned)

### Problem

Without relationships, every word gets its own full review schedule. If 40 words are due today and 15 are closely related to words already reviewed in the session, the student still does all 40 reviews.

### Algorithm

When a student answers a question correctly (non-retry), after the existing mastery update:

```python
SIBLING_STRENGTH = 0.35

def apply_implicit_credit(mastery_record, user):
    word = mastery_record.word
    now = timezone.now()

    # Direct parent鈫抍hild credit
    relationships = WordRelationship.objects.filter(
        parent_word=word,
    ).select_related('child_word')

    credit_targets = [(rel.child_word, rel.strength) for rel in relationships]

    # Sibling credit: words sharing the same lemma, excluding self and
    # already-covered children. Detected via lemma match, not stored records.
    sibling_ids = Word.objects.filter(
        lemma=word.lemma,
    ).exclude(
        id=word.id,
    ).exclude(
        id__in=[t[0].id for t in credit_targets],
    ).values_list('id', flat=True)

    for sib_id in sibling_ids:
        try:
            sib_word = Word.objects.get(id=sib_id)
            credit_targets.append((sib_word, SIBLING_STRENGTH))
        except Word.DoesNotExist:
            continue

    for target_word, strength in credit_targets:
        try:
            child_progress = UserWordProgress.objects.get(
                user=user, word=target_word,
            )
        except UserWordProgress.DoesNotExist:
            continue

        # Only credit words due within 1.5脳 their interval
        lookahead = timedelta(
            days=child_progress.level.interval_days * 1.5,
        )
        if child_progress.next_review_at > now + lookahead:
            continue

        # Push review forward by a fraction of the interval
        credit_days = (
            child_progress.level.interval_days
            * strength
            * child_progress.learning_speed
        )
        child_progress.next_review_at += timedelta(days=credit_days)

        # Cap: prevent indefinite deferral
        max_pushforward = timedelta(
            days=child_progress.level.interval_days
            * child_progress.learning_speed
            * 1.5,
        )
        if child_progress.next_review_at > now + max_pushforward:
            child_progress.next_review_at = now + max_pushforward

        child_progress.save(update_fields=['next_review_at'])
```

### The 1.5脳 lookahead window

Only words due within `1.5 脳 interval_days` receive implicit credit. Words scheduled further out are already comfortably placed 鈥?nudging them forward wastes the credit on reviews the student wouldn't have done soon anyway.

For a Level 2 word (3-day interval), the window is 4.5 days. For Level 4 (10-day interval), 15 days.

### The pushforward cap

Implicit credit accumulates across sessions. Without a cap, a word could be deferred indefinitely if the student keeps nailing related words. The cap at `1.5 脳 interval_days 脳 learning_speed` ensures every word eventually comes up for an explicit check.

### Walkthrough

Student has these words at Level 2 (3-day base interval):

| Word | Due | Learning speed |
|---|---|---|
| unhappiness | today | 1.0 |
| happiness | tomorrow | 1.1 |
| happy | in 2 days | 0.9 |
| unhappy | in 2 days | 1.0 |

Relationships (WORD_FAMILY):
- unhappiness 鈫?happy (parent鈫抍hild, strength 0.7)
- unhappiness 鈫?unhappy (sibling, strength 0.35)
- unhappiness 鈫?happiness (sibling, strength 0.35)

Student answers "unhappiness" correctly. Implicit credit runs:

- **happy**: due in 2 days, within 4.5-day window. Credit = `3 脳 0.7 脳 0.9 = 1.89 days`. New due: ~3.9 days from now.
- **unhappy**: due in 2 days, within window. Credit = `3 脳 0.35 脳 1.0 = 1.05 days`. New due: ~3.05 days from now.
- **happiness**: due tomorrow, within window. Credit = `3 脳 0.35 脳 1.1 = 1.155 days`. New due: ~2.15 days from now.

Result: instead of reviewing 4 words over the next 2 days, the student may only need to review 1 or 2. The others got enough implicit credit to defer.

### What repetition compression does NOT do

- Does not change mastery levels. Implicit credit only affects review timing, not promotion. Words still need explicit correct answers to level up.
- Does not work in reverse. Answering "happy" correctly doesn't credit "unhappiness."
- Does not apply on incorrect answers. No implicit credit flows on wrong answers.

### Performance note

One extra query per correct answer (fetching relationships + child progress). For typical words with 2-4 relationships, this is negligible. Add a compound index on `WordRelationship(parent_word, relation_type)`.

---

## Implementation order

| Phase | What | Status |
|---|---|---|
| 1 | Adaptive intervals (learning_speed, DateTimeField) | Done (migration 0014) |
| 1a | Response-quality-aware scheduling | Done (no migration) |
| 2 | WordRelationship model + migration | Planned |
| 3 | WORD_FAMILY detection via periodic lemmatization batch job | Planned |
| 4 | Repetition compression (apply_implicit_credit) | Planned |
| 5 | SUBSUMES detection via definition embeddings + wordfreq | Planned |
| 6 | Admin UI for relationship review | Optional |
| 7 | Dashboard visualization of word clusters | Optional |

Phases 2鈥? are the minimum viable version. Phase 5 adds synonym-based compression. Phases 6鈥? are refinements.

### Dependencies

```
Phase 2 (model) 鈫?Phase 3 (word family detection)
                鈫?Phase 5 (subsumes detection)
Phase 2 + 3     鈫?Phase 4 (compression algorithm)
```
