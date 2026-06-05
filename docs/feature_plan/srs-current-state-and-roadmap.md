# Spaced Repetition: Current State & Upgrade Roadmap

> Companion to `design-adaptive-spaced-repetition.md`. That document is the **design intent**; this one records what is **actually in the code today** (verified against the source on 2026-06-04) and lays out the realistic path forward, including the Penn GSE capstone direction.

## How to read this doc

- **Section 1** is ground truth — every claim is backed by a `file:line` reference into the live backend.
- **Section 2** reconciles the design doc against reality (what shipped, what is still vapor).
- **Section 3** is the forward plan, ordered by effort and dependency.

---

## 1. Current state (verified against source)

The SRS system has two halves: **retrieval** (which word/question to show next) and **scheduling** (when a word comes back after an answer). Only the per-student-per-word adaptive interval (design doc §1) is built. Word relationships and repetition compression (§2, §3) are **not present in any form**.

### 1.1 Retrieval — `NextPracticeWordView`

`backend/vocabulary/views/practice_views.py:29`

- Due query: `UserWordProgress` where `next_review_at <= end_of_local_day(today)`, `instructional_status='READY'`, ordered by `next_review_at` ascending (oldest-due first). `practice_views.py:68`
- Lexile gate: word must have at least one `Question` with `lexile_score` in `[user.lexile_min, user.lexile_max]` **or** `lexile_score IS NULL`. `practice_views.py:61`
- Session dedup: words already answered since `session_start` are excluded. `practice_views.py:76`
- Daily cap: stops at `user.daily_question_limit` (default 30). `practice_views.py:41`
- Question pick: random question matching the word's current level via `suitable_levels`; hidden levels 6–7 ignore `suitable_levels` and draw any in-range question. `practice_views.py:93`
- `reason_category` (NEW_WORD / STRUGGLE_WORD / MASTERY_CHECK / STANDARD_REVIEW) is a **display label only** — it does not affect ordering or selection. `practice_views.py:113`

There is **no priority weighting, no overdue-penalty, no interleaving** beyond "oldest due first." Order is purely `next_review_at ASC`.

### 1.2 Scheduling — `PracticeService.process_answer`

`backend/vocabulary/services/practice_service.py:251`

On every **non-retry** answer, the service:

1. **Classifies response quality** (`_classify_response_quality`, `practice_service.py:197`).
2. **Updates mastery points** (+1 correct / −2 incorrect, floored at 0) and promotes/demotes against `points_to_promote`. `practice_service.py:318`
3. **Updates `learning_speed`** via EWMA: `learning_speed = 0.3 * quality + 0.7 * old_speed` (`ALPHA = 0.3`). `practice_service.py:358`
4. **Computes the next interval**:
   ```
   adaptive_days = level.interval_days * learning_speed * interval_factor
   # fragile + just-promoted → cap at old_level.interval_days * old_learning_speed
   review_interval_days = max(1.0, adaptive_days)
   next_review_at = now + timedelta(days=review_interval_days)
   ```
   `practice_service.py:363`

Constants (`practice_service.py:31`): `MIN_TIMING_BASELINE_SAMPLES=15`, `TIMING_BASELINE_LIMIT=50`, valid duration window `1 < s < 100`, `MIN_REVIEW_INTERVAL_DAYS=1.0`, `ALPHA=0.3`.

Response-quality table (`RESPONSE_QUALITY_RULES`, `practice_service.py:38`) — **matches the design doc §1 exactly**:

| Quality | quality | interval_factor | fragile |
|---|---:|---:|:--:|
| `fast_correct` | 1.25 | 1.15 | no |
| `solid_correct` | 1.10 | 1.00 | no |
| `slow_correct` | 0.85 | 0.85 | yes |
| `switched_correct` | 0.90 | 0.85 | yes |
| `typo_retry_correct` | 0.90 | 0.85 | yes |
| `incorrect` | 0.50 | 0.50 | yes |
| `unclassified_correct` | 1.20 | 1.00 | no |

Timing baseline: per-learner, per-`question_type`, latest 50 valid first-attempt durations; needs ≥15 samples or the answer falls back to `unclassified_correct`. Fast/slow = 25th/80th percentile (`_get_timing_baseline`, `_percentile`, `practice_service.py:156`). When multiple correct signals apply, the **most conservative** (lowest quality, then lowest factor) wins. `practice_service.py:240`

Retries (`is_retry=True`) only bump `retry_count` and never touch mastery, XP, `learning_speed`, or the schedule. `practice_service.py:400`

### 1.3 Mastery schedule (`MasteryLevel`)

`backend/vocabulary/models.py:107` — seeded data per CHANGELOG / migration `0017`:

| Level | Name | interval_days | points_to_promote | Hidden |
|---:|---|---:|---:|:--:|
| 1 | Novice | 1 | 2 | no |
| 2 | Familiar | 3 | 4 | no |
| 3 | Confident | 7 | 7 | no |
| 4 | Proficient | 10 | 10 | no |
| 5 | Mastered | 17 | 15 | no |
| 6 | Long-Term Retention | 30 | 25 | yes |
| 7 | Long-Term Mastery | 60 | 999 | yes |

Points accumulate (not reset on promotion). Levels 6–7 roll into the student-facing "Mastered" bucket.

### 1.4 Relevant persisted signals

- `UserWordProgress`: `level`, `mastery_points`, `next_review_at` (DateTime), `last_reviewed_at`, `learning_speed`, `instructional_status`. Indexed `(user, next_review_at)` and `(user, instructional_status)`. `models.py:121`
- `UserAnswer`: `is_correct`, `duration_seconds`, `answer_switches`, `retry_count`, `answered_at`. Indexed `(user, answered_at)`, `(user, is_correct)`, `(question, answered_at)`.
- `MasteryLevelLog`: full promote/demote trajectory per user-word.
- `Question.difficulty_index` / `discrimination_index`: fields **exist** (`models.py:219`) but are **never written anywhere** in the backend — confirmed by grep (no assignment outside migrations).

---

## 2. Design doc vs. reality

| Design doc section | Status in code | Evidence |
|---|---|---|
| §1 Adaptive intervals (`learning_speed`, DateTimeField, migration 0014) | **Shipped & faithful** | `practice_service.py:358`, `models.py:134`, `migrations/0014_adaptive_intervals.py` |
| §1a Response-quality scheduling (7 qualities, timing percentiles, fragile cap) | **Shipped & faithful** | `RESPONSE_QUALITY_RULES` table matches doc 1:1 |
| §2 `WordRelationship` model | **Not started** | No `class WordRelationship` anywhere; grep clean |
| §2 `Word.lemma` field | **Not started** | `Word` has no `lemma` field (`models.py:19`) |
| §3 `apply_implicit_credit` / repetition compression | **Not started** | No function, no call site |
| §3 deps (`nltk` lemmatizer, `wordfreq`) | **Not installed** | Not in `requirements.txt`; grep clean |

**Bottom line:** the design doc describes one shipped feature and two aspirational ones. The shipped half is implemented exactly as written. The "Implementation order" table at the doc's end is still accurate: Phases 1/1a Done, Phases 2–7 Planned with no code.

### Drift / inaccuracies to note

- The design doc's §3 `apply_implicit_credit` pseudocode references `child_progress.level.interval_days` and `Word.objects.filter(lemma=...)`. Both APIs are speculative — `Word.lemma` does not exist, so this code cannot run as written without the Phase-2 schema change first.
- The doc presents response-quality scheduling as the ceiling of the adaptive system. The capstone direction (§3.4 below) supersedes it with a trainable recall model, which is a different and more powerful approach than tuning the EWMA.

---

## 3. Upgrade roadmap

Three independent tracks. They do not block each other; pick by goal.

### 3.1 Track A — Finish the design doc as written (relationship-based compression)

Lowest novelty, already specced. Reduces review load by transferring implicit credit across morphologically/semantically related words.

1. **Phase 2** — `WordRelationship` model + `Word.lemma` field + migration. Add compound index `(parent_word, relation_type)`.
2. **Phase 3** — WORD_FAMILY detection as a **periodic management command** (`nltk` WordNetLemmatizer), not pipeline-time, so links form regardless of word creation order.
3. **Phase 4** — `apply_implicit_credit` hook in `process_answer` after the mastery update, on correct non-retry answers only. Respect the 1.5× lookahead window and pushforward cap from the design doc.
4. **Phase 5** — SUBSUMES detection via `DefinitionEmbedding` cosine similarity + `wordfreq` Zipf for direction.

Risk: implicit credit silently defers reviews — must ship behind a flag and measure retention impact, or it can quietly harm learning.

### 3.2 Track B — Retrieval quality (cheap wins, no new models)

The current "oldest due first" ordering is naive. Without schema changes:

- **Overdue weighting**: prioritize words whose `now - next_review_at` is large relative to their interval (most at-risk of being forgotten) rather than strict `next_review_at ASC`.
- **Struggle-word boost**: the `STRUGGLE_WORD` signal is already computed for display (`practice_views.py:117`) but unused for ordering — let it bias selection.
- **Question-type interleaving**: vary `question_type` within a session for the same skill, which the literature links to better retention than blocked practice.

These are scoring tweaks in one view; easy to A/B.

### 3.3 Track C — Item quality flags (capstone feature #2)

`Question.difficulty_index` and `discrimination_index` exist but are dead fields. Compute them offline from `UserAnswer` history:

- **difficulty_index** = p-value (proportion correct on first attempt).
- **discrimination_index** = point-biserial between item correctness and learner ability.
- Add distractor analysis for MC items.
- Flag bad items (too easy/hard, negative discrimination) and feed back into the LLM generation pipeline ([[project_generation-pipeline-modular]]).

Pure analytics; no scheduling risk. Good first capstone deliverable because it is self-contained and evaluable (reliability / IRT fit).

### 3.4 Track D — ML forgetting curve (capstone feature #1, the headline upgrade)

Replace the heuristic `learning_speed` EWMA with a **trainable recall-probability model** (Half-Life Regression or FSRS-style Difficulty/Stability/Retrievability). See [[project_capstone-analytics-direction]].

- **Inputs already persisted**: `UserAnswer` (correctness, duration, switches, retries, timestamps), `last_reviewed_at`/`next_review_at`, `MasteryLevelLog` trajectory. No new event capture needed to start.
- **Target**: schedule `next_review_at` at a chosen target retention (e.g. 0.85–0.90) instead of `interval_days * learning_speed * factor`.
- **Method**: offline training pipeline → persisted model artifact → inference in `process_answer`. Evaluate with AUC/MAE on held-out recall.
- **Rollout**: shadow mode first — compute the model's proposed `next_review_at` alongside the current one and log the delta before letting it drive scheduling.
- **Data**: mix of synthetic simulated learners + real usage, per the capstone plan.

This is the most ambitious track and the reason the schema already uses a DateTimeField for `next_review_at` (sub-day precision) — the heuristic was always meant to be a placeholder for a real memory model.

### Suggested sequencing for the capstone

```
Track C (item quality)      → self-contained, ships first, builds the analytics harness
Track D shadow mode         → reuses the same UserAnswer pipeline; high LA credibility
Track B (retrieval tweaks)  → quick wins, easy to A/B against Track D
Track A (compression)       → only if review-load reduction becomes a stated goal
```

Tracks C and D share an offline-analytics + evaluation harness; build it once.

