# Spaced Repetition: Current State & Upgrade Roadmap

> Companion to `design-adaptive-spaced-repetition.md`. That document is the **design intent**; this one records what is **actually in the code today** (verified against the source on 2026-06-04) and lays out the realistic path forward, including the Penn GSE capstone direction.

> **Capstone-scope update (2026-06-29).** Revised while preparing the mentor overview for Dr. Yang Jiang (ETS). Key changes from the 2026-06-23 plan: (1) **placement / cold-start (Track E) is CUT** from the capstone — assigned word sets + the self-correcting scheduler make it redundant, and a homogeneous Asian-L1 early audience removes the fairness hook that made it interesting (§3.5). (2) The **learner simulator is built AFTER Track C + D**, seeded from the fitted system, not first (§3.6). (3) The **interval-selection-bias** caveat is refined — the natural review backlog already gives *late* Δt variance, so the fix is a small *early-weighted* jitter, not all-artificial variance (§3.4). (4) **Data scale** is growing toward ~20 learners / ~20k responses, rolling enrollment (§3.6). (5) The **DKT rejection** now leads with data scale; "DKT can't model time" is corrected as overstated (§4).

## How to read this doc

- **Section 1** is ground truth — every claim is backed by a `file:line` reference into the live backend.
- **Section 2** reconciles the design doc against reality (what shipped, what is still vapor).
- **Section 3** is the forward plan, ordered by effort and dependency.
- **Section 4** is the model-selection ADR: which ML approaches were evaluated for the capstone and why DeepFM / DKT were rejected for scheduling (reviewed 2026-06-23).

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

Timing baseline: per-learner, per-`question_type`, latest 50 valid first-attempt durations; needs ≥15 samples or the answer falls back to `unclassified_correct`. Fast/slow = 25th/80th percentile (`_get_timing_baseline`, `_percentile`, `practice_service.py:156`). Since 2026-07-03 the computed baseline is cached per (user, question_type) for 10 min (`TIMING_BASELINE_CACHE_TTL`) — a perf change only, but note for analytics that a submit may be classified against a baseline up to 10 min stale. When multiple correct signals apply, the **most conservative** (lowest quality, then lowest factor) wins. `practice_service.py:240`

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

- `UserWordProgress`: `level`, `mastery_points`, `next_review_at` (DateTime), `last_reviewed_at`, `learning_speed`, `instructional_status`. Indexed `(user, next_review_at)` and `(user, instructional_status, next_review_at)` (migration `0040`, 2026-07-03; replaced the old `(user, instructional_status)`). `models.py:121`
- `UserAnswer`: `is_correct`, `duration_seconds`, `answer_switches`, `retry_count`, `answered_at`, `judge_result` (JSON, sentence-writing judge verdicts — an item-quality signal for productive tasks). Indexed `(user, answered_at)`, `(user, is_correct)`, `(question, answered_at)`. Note: before 2026-07-03 a retry incremented `retry_count` on *every* historical answer for that user+question (Django `.update()` ignores `order_by`), so pre-fix `retry_count` values are inflated — treat them as unreliable in offline analysis.
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

Five tracks (A–E), largely independent; pick by goal. For the capstone, **C and D are in scope** (item quality + the memory model), the learner simulator + evaluation come after them, and B is an optional quick win. **A (compression) and E (placement) are out of scope** — see each track for why.

### 3.1 Track A — Relationship-based compression *(deferred — out of scope for the capstone)*

> **Status (2026-06-23): shelved, not deleted.** Originally the plan to reduce review load by transferring implicit credit across morphologically/semantically related words. It is the lowest-priority track now, for three reasons:
>
> 1. **It conflicts with Track D.** Track A's mechanism is silently deferring reviews via cross-word credit; Track D (FSRS) must fit a decay curve on *clean per-word recall observations*. Granting "construct"→"deconstruct" credit injects an unobserved confound into the exact signal Track D trains on. The two cannot run together without careful bookkeeping, and corrupting the headline deliverable to power a side feature is a bad trade.
> 2. **Its smart form already lives in Track E.** The valuable version of implicit credit — inferring knowledge of related/unseen words — is the DKT latent-credit direction parked in §3.5. The symbolic nltk-lemmatizer approach below is the brittle approximation of that; you wouldn't build both.
> 3. **Its trigger isn't met.** Review *load* is not the pain point for a low-volume K-8 ESL app — review *quality* and not boring the learner are, and those are Tracks C/D/E.
>
> Revisit only if review-load reduction becomes a stated product goal *and* Track D is no longer actively fitting. Prefer the Track E latent-credit mechanism over the symbolic plan below.

The original spec, retained for reference:

1. **Phase 2** — `WordRelationship` model + `Word.lemma` field + migration. Add compound index `(parent_word, relation_type)`.
2. **Phase 3** — WORD_FAMILY detection as a **periodic management command** (`nltk` WordNetLemmatizer), not pipeline-time, so links form regardless of word creation order.
3. **Phase 4** — `apply_implicit_credit` hook in `process_answer` after the mastery update, on correct non-retry answers only. Respect the 1.5× lookahead window and pushforward cap from the design doc.
4. **Phase 5** — SUBSUMES detection via `DefinitionEmbedding` cosine similarity + `wordfreq` Zipf for direction.

Risk: implicit credit silently defers reviews — must ship behind a flag and measure retention impact, or it can quietly harm learning. (And see the Track D conflict above.)

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

Pure analytics; no scheduling risk. Good first capstone deliverable because it is self-contained and evaluable. **Note (2026-06-29):** with placement (old Track E) now cut from scope, Track C stands on its own as the regeneration-loop feature — it no longer needs to double as IRT calibration for a CAT. Full IRT (`b`/`a` calibration) stays *future* analytics; for the capstone, simple small-data flags (high error rate, repeated confusion, high skip rate, rubric review).

### 3.4 Track D — ML forgetting curve (capstone feature #1, the headline upgrade)

Replace the heuristic `learning_speed` EWMA with a **trainable recall-probability model**. See [[project_capstone-analytics-direction]].

**Model choice (reviewed 2026-06-23): FSRS as primary, Half-Life Regression (HLR) as the baseline you beat.** Both are decay models (the right model family — see §4) with the three properties the scheduler needs:

- **Strict monotonicity** — recall probability decreases with elapsed time by construction, so a target-retention solve never schedules a later review *earlier*.
- **Closed-form invertibility** — given a target retention θ, solve for the next interval Δt in O(1) algebra, no root-finding inside the request:
  - HLR: `P = 2^(−Δt/h)`, `h = 2^(w·x)` ⇒ `Δt = −h·log₂(θ)`.
  - FSRS: `R = (1 + t/(9S))^(−1)` ⇒ also closed-form invertible in S, t.
- **Interpretability** — HLR's log-linear weights and FSRS's Difficulty/Stability/Retrievability both map onto cognitive constructs (Ebbinghaus decay), which is what an EdTech committee wants to see. FSRS's D/S/R arguably tells a cleaner story than HLR's weight vector.

Why FSRS over HLR as the *primary*: FSRS benchmarks more accurately than HLR and SM-2 on every public dataset, is actively maintained, and is open-source. HLR is the simpler, faster-to-fit baseline — fit it first, report it, then show FSRS beating it. (HLR practical note: fit the published Settles & Meeder 2016 objective, which adds a half-life term `(h_obs − h_pred)²` — probability-only MSE is unstable. Cite it as "simplified HLR" if you drop that term.)

- **Inputs already persisted**: `UserAnswer` (correctness, duration, switches, retries, timestamps), `last_reviewed_at`/`next_review_at`, `MasteryLevelLog` trajectory. No new event capture needed to start. Per-word one-hot embeddings are **not** used — the catalog is too sparse (see §4); features are word *attributes* (lexile, POS, question_type) + per-learner history, exactly what HLR's `w·x` consumes.
- **Target**: schedule `next_review_at` at a chosen target retention (e.g. 0.85–0.90) instead of `interval_days * learning_speed * factor`.
- **Method**: offline training pipeline → persisted model artifact (`weights.json` for HLR; D/S/R params for FSRS) → inference in `process_answer`. Evaluate with AUC/MAE on held-out recall.
- **Rollout**: shadow mode first — compute the model's proposed `next_review_at` alongside the current one and log the delta before letting it drive scheduling.
- **Data**: real usage from a growing cohort, augmented by a learner simulator built *after* the model is fitted (see data-scale + simulator notes below).

> ⚠️ **Interval selection bias — the make-or-break caveat for this track.** A decay slope cannot be identified from data with no variance in Δt.
>
> **Refined 2026-06-29** (the original "scheduler only ever shows a card at its due time" framing was too strong): in practice learners already review off-schedule. A review **backlog** (daily cap + `next_review_at ASC` ordering) means cards are frequently reviewed *late*, so observed Δt already has *some* natural variance — for free. But that natural variance has two problems:
> 1. **One-directional.** Backlog only produces *late* reviews (longer Δt). We rarely observe a word reviewed *early* (short Δt, where recall is still high) — exactly the region a scheduler targeting 0.85–0.90 retention cares about most.
> 2. **Confounded, not random.** Which cards fall into the backlog correlates with difficulty/engagement, so late reviews are a *biased* sample of delays. A curve fit to that variance partly reflects "what caused the backlog," not pure memory decay.
>
> **Fix: a small, bounded jitter weighted toward EARLY reviews** (review some cards a day or two before due), to add the short delays the backlog never produces *and* de-confound the sample. Build the jitter + logging into shadow mode from day one. Note: more learners does **not** fix this — it's a Δt-variance problem, independent of N.
>
> Pedagogically safe: SRS is robust to off-schedule review by design (FSRS itself assumes drift), and learners already review off-schedule daily via the backlog — a bounded early jitter is well inside what they already experience.

This is the most ambitious track and the reason the schema already uses a DateTimeField for `next_review_at` (sub-day precision) — the heuristic was always meant to be a placeholder for a real memory model.

### 3.5 Track E — Placement / cold-start adapter *(CUT from the capstone — 2026-06-29; retained as a future direction)*

> **Status (2026-06-29): removed from capstone scope.** Two reasons:
> 1. **Redundant with the existing scheduler.** Word sets are teacher/parent-assigned, and the response-quality scheduler already self-corrects: a word the learner already knows is answered fast-correct and promotes through the mastery levels quickly. A formal pre-test (CAT) buys a slightly faster start in exchange for real friction (sitting the child down before they can begin) — not worth it for assigned sets.
> 2. **Its main intellectual hook evaporated for the early audience.** The interesting part of placement was the fairness argument below (1D IRT is shaky for ESL learners with varied L1 / cognate transfer). But the early audience is **homogeneously Asian-L1**, so there is negligible Latinate-cognate advantage and that motivation largely disappears.
>
> Revisit if the user base becomes large and linguistically diverse, and if forced re-proving of known words becomes a real complaint. The spec below is retained for that future.

The goal would be to avoid forcing a learner to re-prove words they already know (Vygotsky ZPD: don't insult the learner) and to set a sensible starting `level` for new words.

**Use IRT-based Computerized Adaptive Testing (CAT), not a deep knowledge-tracing model, at our data scale.**

- A 2PL IRT CAT over a calibrated item bank picks the next item to maximize information about the learner's ability θ, converges in a few minutes, and is the standard, defensible EdTech placement method.
- Track C's `difficulty_index` / `discrimination_index` would become the IRT `b` / `a` parameters.
- Data-efficient: works with orders of magnitude less data than a Transformer KT model.

**Unidimensionality caveat (would go in the thesis if this were in scope).** 1D IRT assumes vocabulary is a single ability axis. For a linguistically diverse ESL population this is imperfect — L1-cognate transfer (a Spanish L1 learner aces Latinate "ameliorate/exacerbate" but fails Anglo-Saxon phrasal verbs like "put up with") and morphological familiarity introduce sub-strata, and a 1D θ can oscillate on such response patterns. **Defend it on decision stakes, not by denying the dimensionality**: placement is a coarse starting estimate that the FSRS scheduler self-corrects within the first few reviews. Cheap mitigations if oscillation bites: stratify the item bank (Latinate / Anglo-Saxon / phrasal) so the CAT samples across strata, and cap test length. *(Note 2026-06-29: this caveat is the reason placement was a defensible thesis topic; with a homogeneous-L1 early audience the caveat barely bites, which is part of why placement was cut rather than kept.)*

**DKT-for-placement is a future upgrade, not a v1.** A SAKT/DKT/AKT model *could* infer latent mastery of unseen words via cross-word transfer — but only with thousands of learners and many *overlapping* word exposures. At our scale (tens of learners, ~1 interaction per item) the item embeddings are unlearnable and it hits the same sparsity wall that disqualifies DeepFM (§4). Revisit once there's a real learner population.

### 3.6 Cold-start reality, data scale & the learner simulator

FSRS/HLR fitting assumes real learner volume and decay data with varied intervals. The honest state, to state plainly in the thesis rather than presenting the full architecture as if it runs from day one:

**Data scale (2026-06-29).** Currently 2 learners / 6,000+ responses. A wider cohort is being recruited — targeting **~20 learners and ~20k responses** (~1,000/learner). Still small for population-level claims and per-item IRT discrimination (keep "simple flags, full IRT future"), but ~1,000 responses/learner gives real per-learner depth for the decay model and stabler item *difficulty*. Enrollment is **rolling** — learners arrive both before and after the features go live, which gives a natural old-scheduler-baseline vs. shadow-mode contrast but also **uneven history length** per learner that the evaluation must account for.

**Learner simulator — build it AFTER the model, not before (2026-06-29).** Sequencing decision: the simulator is built once Track C item params and the Track D FSRS curve are fitted, *not* up front.
- *Why not first:* a simulator built first would invent a forgetting curve + item params from thin air, then fit a model to made-up data — circular, and the synthetic data wouldn't resemble what the real pipeline produces.
- *Built after:* seed synthetic learners from the *actually-fitted* FSRS params + real item difficulties, so they realistically extend the real cohort and stress-test cases the sparse real data can't cover. Honest limit: it can only confirm the system behaves sensibly on its own assumptions, not real-world effectiveness — so it belongs with the **evaluation** phase.
- *Lightweight exception:* throwaway synthetic data to verify the FSRS *fitting code* recovers known parameters is fine during the build — that's debugging the math, not the real simulator.

**Phase-0 mechanics (unchanged):**
- Seed item difficulties from LLM-estimated priors or the earliest `difficulty_index` values, refine as answers accrue.
- Run Track D in **shadow mode with early-weighted interval jitter** to *accumulate* the varied-Δt recall data the model needs — the heuristic EWMA keeps driving real schedules meanwhile.
- Promote the trained model to drive scheduling only after shadow-mode AUC/MAE and the interval coverage are adequate.

### Suggested sequencing for the capstone *(revised 2026-06-29)*

```
Track C (item quality / regeneration loop)  → self-contained, ships first; independently evaluable
Track D shadow mode + early-weighted jitter → reuses UserAnswer pipeline; the headline deliverable
Learner simulator + evaluation              → built AFTER C+D so it's seeded from the fitted system
Track B (retrieval tweaks)                  → quick wins, easy to A/B against Track D, if time
Track A (compression)                       → only if review-load reduction becomes a stated goal
Track E (IRT/CAT placement)                 → CUT from capstone scope; future direction only
```

Tracks C and D plus the simulator share an offline-analytics + evaluation harness; build it once.

---

## 4. Architecture decision record — models evaluated and rejected (2026-06-23)

Recorded so the capstone doesn't relitigate these. The core principle: **SRS scheduling is a survival/decay problem, not a recommendation or sequence-classification problem.** Match the model family to the question.

| Question | Right tool | Wrong tool |
|---|---|---|
| When does recall decay to θ? (scheduling / trajectory) | **FSRS / HLR** (decay models) | DeepFM, DKT |
| What is mastery of word X right now? (state estimation) | DKT/SAKT *(at scale)*, IRT *(at our scale)* | — |
| Where to place a new learner? (cold-start) | **IRT / CAT** | DKT (data-starved) |

> **Note (2026-06-29):** the cold-start / placement row is retained for completeness, but placement (Track E) is **cut from the capstone** — see §3.5. The live capstone question is the first row (scheduling).

### DeepFM — rejected for scheduling

A CTR/recommender architecture; mismatched to decay. In order of how disqualifying:

1. **Sparsity (decisive).** A learner touches a given word ~3–8 times ever; the user×item matrix is catastrophically sparse. Per-item factorization-machine embeddings cannot be learned and will overfit to the first one or two learners who saw the word. This alone rules it out.
2. **No native monotonicity.** Standard DNNs don't enforce P(recall) decreasing in Δt, so they can predict local "wobbles" that corrupt a target-retention solve. (Monotonic/lattice nets exist, but you'd be *engineering in* what FSRS/HLR give for free.)
3. **No analytical inverse.** Outputs P(correct | Δt) but scheduling needs Δt; inverting a black box means numerical root-finding. Mitigable (grid eval / async / precompute) — an annoyance, not fatal.
4. **Interpretability.** Hard to defend a dot-product-of-embeddings explanation to an education committee.

### DKT — rejected for *scheduling*, viable later for *state estimation*

DKT answers "does the learner know it **now**," not "when does it **decay**." Two reasons it's wrong for the scheduler, in order of how decisive:

- **Data scale (the decisive reason).** KT Transformers are trained on 10⁵–10⁸ interactions (ASSISTments, EdNet). Our scale (tens of learners, ~3–8 exposures per word) doesn't support training one, and using per-item embeddings reintroduces the exact sparsity problem that killed DeepFM — *more* data-hungry, not less.
- **Model-family fit (a preference, not a hard wall).** FSRS/HLR give monotonic decay + a closed-form interval solve for free. Vanilla DKT (Piech 2015) consumes an ordinal step sequence with no concept of elapsed wall-clock time — but **time-aware KT variants exist** (DAS3H, HawkesKT, DKT+forgetting), so clock-time is *not* a hard wall. With them you'd be *engineering in* what a purpose-built decay model provides by construction, at far higher data cost. (Be careful not to overstate this to an expert reviewer: "DKT can't do time" is false and beatable — the honest claim is data scale + model-family fit, not a time impossibility.)

Its legitimate future home is Track E state estimation / latent implicit credit, once learner volume is real.

