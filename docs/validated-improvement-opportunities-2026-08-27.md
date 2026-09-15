# Validated Improvement Opportunities — Research × Codebase Verification

Date: 2026-08-27 (revised twice same day — reconciled against the capstone plan, then
updated with design-review decisions; see the decision log at the end)
Scope: analysis only — no code changes were made.

This report deep-dives every opportunity from `research-paper-analysis-2026-08-27.md`
(T1–T20, N1–N9) and verifies each against the actual codebase (docs + source). It was
then reconciled against the already-planned capstone work:

- `Zhuang_Patrick_Final_Proposal_Draft.md` (2026-08-08) — predictive memory layer
  (primary), item-quality monitoring loop + LLM feedback audit (secondary)
- `Zhuang_Patrick_Assignment4_Draft.md` (2026-07-15) — authoritative capstone scope:
  **Decision 7: "CTT for item quality, not IRT"** (§3.6); item loop evaluation =
  shrunk difficulty posteriors, **"aggregate by question type where per-item data are
  sparse"** (§3.8); risk table: "Per-item n too small → aggregate by question type"
- `docs/feature_plan/srs-current-state-and-roadmap.md` — app-side Tracks A–E
- `C:\assignment\capstone\FSRS_test\SCHEDULER-DESIGN-NOTES.md` (2026-08-14) — band
  architecture + dynamic-points decisions from the completed FSRS fitting
- `C:\assignment\capstone\ENGINEERING-BACKLOG.md` — instrumentation prerequisites

Each item carries: **research strength**, **code verdict** (IMPLEMENTED / PARTIAL /
MISSING, with file:line evidence), and **status** (capstone-planned, design-decided,
on hold, or open).

## Verdict summary

| ID | Opportunity | Research | Code verdict | Status |
|----|-------------|----------|--------------|--------|
| T1 | Recall/production-weighted practice mix | Strong | **PARTIAL** — uniform random within level; productive share 0% at L1–3, ~25% at L4–5, ~12% at hidden L6–7 | Partially planned — band architecture (recognition L1–3 / production L4–5) + Track B interleaving |
| T2 | Learner-side gate for productive types | Strong | **PARTIAL** — implicit per-word gate via levels; no explicit receptive-success gate | Within band architecture; dynamic-points is the planned alternative to gates |
| T3 | Item analytics (difficulty/discrimination) | Strong | **MISSING** — `difficulty_index`/`discrimination_index` are dead schema | **PLANNED — Track C, CTT-scope (see Step 1)** |
| T4 | Semantic distractor checks | Strong | **PARTIAL** — strong prompt-level distractor engineering; zero computational checks | **ON HOLD (design decision)** — distractor quality is context-dependent; embedding similarity judged inadequate |
| T5 | Cognitive-load budget | Strong | **PARTIAL** — reduced-motion CSS global; autoplaying audio unbudgeted | Open |
| T6 | Coordinated multimodal bundle | Strongest | **IMPLEMENTED** | — |
| T7 | Varied contexts per word | Strong | **PARTIAL** — guided→open divergence only | Open |
| T8 | Post-mastery stagnation / novelty | Medium | **PARTIAL** — passive next-pack prompt only | Open (post-Track-D) |
| T9 | Productive evidence for top mastery | Strong | **MISSING** — pure cumulative points, any type | Planned in altered form — dynamic evidence-weighted points (scheduler notes §2.4), deliberately not a hard gate |
| T10 | Flip-card self-test mode | Medium | **MISSING** | Watchlist |
| T11 | Graduated feedback + deeper hint tier | Strong | **PARTIAL** — retry loop real; revision-loop hints already graduate across attempts | **Design-validated** — deeper on-demand tier dropped (see decision log); audit planned (capstone secondary) |
| T12 | Verify L1–L5 difficulty gradient | Strong | **MISSING** — never validated against response data | **PLANNED — Track C** (gradient check on delayed accuracy, aggregate-level) |
| T13 | L1-translation recall question type | Extrapolation | **MISSING** — no translation-based question type | Not planned |
| T14 | Exposure tracking across contexts | Medium | **MISSING** — no per-word exposure counters | Scheduling-decision log planned (backlog #2) — scheduling-side only |
| T15 | Word-frequency-band metadata | Weak-Medium | **MISSING** — `Tag` M2M never populated | Watchlist |
| T16 | Morphology/word-family + collocations | Strong (g=1.14) | **PARTIAL** — collocation + word-form *questions* exist; no word-family *teaching* content | Open; safe to build (Track A shelving was about credit transfer, not content) |
| T17 | Word-bank growth widget | Medium | **PARTIAL** — totals + per-level deltas exist; no headline stat, no per-set map | **ON HOLD (design decision)** — visible counters + badges approved, needs UI redesign first |
| T18 | Cultural-diversity check | Weak (qual) | **MISSING** | Partially planned — cultural bias is in the feedback-audit rubric; content-side open |
| T19 | Early-interval sanity check | Medium (descoped) | **IMPLEMENTED** — 1/3/7/10/17/30/60 ladder + learning-speed + 1-day floor | Superseded by Track D |
| T20 | Cognate highlighting | Weak, population-gated | **MISSING** — inapplicable: early audience homogeneously Asian-L1 | Correctly rejected |
| N1 | Multiple-choice glosses in reader | Strong (2 metas) | **MISSING** — passive definition panels only | **DROPPED (design decision)** — reading stays stress-free; cloze quiz already provides the retrieval moment |
| N2 | L1 prominence in reader + feedback | Strong | **PARTIAL** — translations plumbed but key surfaces never render them | Reader toggle: evidence-backed, pending decision; feedback surface: resolved differently (simplified-English explanations — see decision log) |
| N3 | Independent answer-verification pass | Medium | **MISSING** | **APPROVED as batch job** — run post-generation at low system usage, not inline |
| N4 | Question review actions + safety screen | Medium | **PARTIAL** — read-only question tab; no flag/delete; no safety screen | Partially planned — Track C flags → regeneration with human review; review-UI actions needed to act on flags |
| N5 | Delayed-retention metric | Strong | **MISSING** — data exists, no query | Partially planned — "secure/fragile/forgotten" states (Track D interface); plain delayed-accuracy KPI open |
| N6 | Time-on-task KPI + extra-practice path | Strong (dose-response) | **PARTIAL** — `PracticeSession` is a dead table; hard 429 cap | Open (post-Track-D; cap changes interact with backlog dynamics) |
| N7 | Mobile-first student experience | Medium | **PARTIAL** — responsive breakpoints exist; desktop-first shell | Open |
| N8 | Teacher mediation of reading | Medium (child lit) | **PARTIAL** — strong analytics; nothing for guided reading | Plain-language scheduling explanation planned (proposal §6 Interface); guided-reading mode open |
| N9 | No competitive mechanics | Medium | **IMPLEMENTED** — none exist | — |

---

## What the capstone plan already covers — and the deltas this report adds

### Track C (item-quality loop) ≈ T3 + T12 + N4 — PLANNED, at confirmed CTT scope
Assignment 4, Decision 7: **"CTT for item quality, not IRT."** Proportion-correct and
point-biserial suit small samples; guards = minimum response count, shrinkage, and
flag-for-review over auto-regeneration. Evaluation (§3.8): shrunk difficulty posteriors
before/after regeneration (target difficulty ~0.5–0.7, discrimination > 0.2), and
**"aggregate by question type where per-item data are sparse"** — i.e., the per-type
stratification this report recommended is already capstone policy.
Verification note for the proposal: it lists "psychometric fields already in the schema"
as a feasibility strength — confirmed, but the fields are **dead** (`models.py:228-235`,
never written), so the compute path is genuinely greenfield, as the plan assumes.
Remaining deltas from the research corpus, re-scoped for small data:
1. **MI-distractor alarm** (Susanti: a distractor whose pick rate rises with learner
   mastery is defective) — only as a count-gated flag (compute where per-option n clears
   a threshold; silent otherwise), or deferred until volume accrues. Do not report
   per-item distractor stats at n≈10.
2. **L1–L5 gradient check on delayed accuracy** (Webb 2020: same-session accuracy
   measures format difficulty, not learning) — aggregates across many items per level,
   so feasible even at small per-item n.

### Track D (predictive scheduling) — supersedes T19; changes the context for T1/T2/T9
Established results (scheduler notes §1): frozen adult FSRS does not transfer
(AUC ≈ 0.52); recalibrated FSRS best (AUC 0.56–0.59, pooled log-loss gain CI excludes
zero); HLR lands almost exactly on current pacing (ratio 1.01); **over-review at L1–2**
(99.4% accuracy before promotion to L3). Retention target r = 0.85; shadow mode;
early-weighted jitter (IRB-gated).
Consequences:
- **T19 closed** — ladder verified in code; interval-shape answered by the model ladder.
- **T9 revised to match the agreed direction (§2.4)**: productive evidence should
  *weight* progress (evidence-weighted points +2/+1/+0.5 by predicted R), not hard-gate
  it — calibration is too modest (AUC ≈ 0.60) for a sole arbiter, and a gate change
  alters the data-generating process mid-study. Sequencing: shadow data → FSRS intervals
  → dynamic gate as its own A/B. The research case (Webb 2020's form-recall decay;
  Savva's g=0.54) supports giving productive success *more weight*, which the dynamic-
  points design expresses. The hard-gate version is withdrawn.
- **T2 within the band architecture (§2.5)**: bands already encode recognition-before-
  production per word. Open remainder: an explicit receptive-accuracy check before
  production unlock, and the serve-fallback edge case (`practice_views.py:145-146` can
  serve sentence-write below L4).
- **T1's L6–7 dilution** (~12% productive share at hidden levels) is a known, accepted
  design ("mixed, any in-range question" band) with asymmetric production ratings
  planned (§2.6: judge-passed = Good; failed = never Again). Open remainder:
  within-level type weighting below L6 (Track B interleaving partly addresses).
- **N5 partially planned**: "secure, fragile, forgotten" word states for parents/
  teachers come from the predictive model. Not planned: a plain delayed-retention
  accuracy KPI (accuracy on reviews ≥24h after last correct) — cheap alongside.

### LLM feedback audit ≈ T11 (measurement half) + T18 (feedback half) — PLANNED
~50 stratified verdicts, two independent raters, rubric = discouraging tone /
overcorrection / incorrect grammar judgment / **cultural bias** / age-inappropriate
content, Cohen's κ (Assignment 4 §3.8, proposal §6). Covers measurement of judge
quality and cultural bias on the feedback side. Not covered: content-side cultural
diversity (T18's original scope: GN/infographic scenarios) — open.

### Engineering backlog — instrumentation prerequisites (binding)
Priority-0 items gate all analytics below and are time-critical (data accruing now is
unrecoverable):
1. **Persist near-miss typo attempts** — currently no row at all (MNAR bias on the
   interval variable the decay models estimate). Fix: `was_typo_near_miss` flag on
   `UserAnswer`; scoring unchanged. **[Approved for near-term work]**
2. **Append-only `SchedulingDecision` log** — intended vs realized interval, queue
   state, before/after mastery; without it, schedule and behavior can't be separated.
   **[Approved for near-term work]**
3. **Child-written sentences in plaintext `temp/llm_logs/`** (1,581 files as of
   2026-07-29, no retention limit) — live inconsistency with the proposal's §8
   encryption claim. **[ON HOLD — comprehensive privacy pass planned later]**
Also planned: first-attempt verdict persistence (productive items), additive interval
jitter with logged propensities, question-type covariate for the `order_by('?')`
instrument-drift confound, benchmark-comparable metrics.

---

## Near-term work (Steps 0–3), after the design review

### Step 0 — Fix the data leaks
- Persist near-miss typo attempts (`was_typo_near_miss` on `UserAnswer`; keep the early
  return for scoring — only add the write).
- Append-only `SchedulingDecision` table written on every scored answer: user, word,
  timestamps, mastery level + learning speed before/after, response-quality rule,
  intended interval, next_review_at, jitter fields, queue position, due backlog size.
- ~~LLM-log redaction/retention~~ — **on hold**; comprehensive privacy pass later.

### Step 1 — Item-quality flagging at capstone scope (CTT, not IRT)
- Offline job populating `difficulty_index` (first-attempt proportion correct) and
  `discrimination_index` (point-biserial) from `UserAnswer`, with minimum-response-count
  guards and shrinkage; **flag-for-review, not auto-regeneration**.
- Aggregate by question type where per-item data are sparse (capstone policy); evaluate
  flagged→regenerated items via shrunk difficulty posteriors (target ~0.5–0.7,
  discrimination > 0.2).
- L1–L5 gradient check on **delayed** accuracy (aggregate across items per level).
- MI-distractor alarm: count-gated or deferred until volume accrues.
- **Batch answer-verification pass (approved, as a batch job)**: an independent LLM call
  re-solves generated questions and flags key mismatches — run **post-generation in
  off-peak windows**, not inline in the pipeline. Fits the existing review flow: flagged
  items go to the admin review surface.
- Review-UI flag/delete actions on the question tab (currently read-only,
  `GenerationReview.jsx:253-281`) so flags are actionable.
- ~~Embedding-based distractor similarity reject~~ — **on hold** (distractor quality is
  context-dependent; embedding similarity judged inadequate for it).

### Step 2 — Feedback: small, confirmed fixes only
- **Simplified-English explanation rule** (replaces the L1-in-feedback idea): ensure
  generated explanations (and judge hints) use easy, modified English appropriate to the
  content Lexile. A prompt-level constraint; evidence-consistent (Shute 2008: feedback
  must not overwhelm; Susanti: over-hard wording backfires). The L1-in-error-feedback
  surface stays unused (double-edged for higher-fluency learners; see decision log).
- **Dead-code cleanup**: the unreachable Next escape at `ChoiceQuestion.jsx:92`
  (`wrongOptions.length >= choices.length` can never hold with one correct option).
  Functionality is fine as designed — wrong options are disabled when struck out
  (`ChoiceQuestion.jsx:82`), so MC self-terminates at the correct answer, and
  type-to-spell shows the answer among the read-only reference options
  (`PracticeView.jsx:629-634`). Remove the dead branch or leave with a comment.
- ~~On-demand "tell me more" judge tier~~ — **dropped**: the revision loop already
  delivers graduated hints across attempts (judge is told not to repeat hints), which is
  Jeon's graduated-assistance design; long text is a barrier at ages 7–14.

### Step 3 — Student-facing surfaces
- ~~MC glosses in the reader~~ — **dropped**: the reading phase is deliberately a
  stress-free engagement puller, and the cloze quiz immediately after the story already
  provides the evaluative retrieval moment for every target word in story context.
  Furenes' child evidence (interruptive interactivity costs comprehension) supports the
  current design.
- **Reader L1 translation toggle** — evidence-backed (Yanagisawa 2020: L1 glosses beat
  L2 at all proficiencies, no proficiency interaction; Furenes: on-demand delivery
  avoids the comprehension cost; Montero Perez 2022: L1 subtitles are a distinct,
  useful support). Recommended: available behind a toggle, **off by default**, reusing
  the translations the pack payload already carries (`instructional_service.py:69-90`).
  Pending final decision.
- **Achievements word-bank** — approved in principle (very visible counters + badges +
  per-set mastery map; personal only, no competition per Zhang & Hasim). **On hold**
  pending a student-UI redesign pass.

---

## Later / post-Track-D items (not for the next several weeks)

- **T7 distinct-context prompts** — prompt-only change ("each item situates the word in
  a different setting") + serve-time preference for unseen scenarios. Low risk, can slip
  in earlier if convenient.
- **T16 word-family content in primers** — root + 1–3 derivatives + one affix note
  (Silverman g=1.14). Prompt-level addition to `primer_generation.txt`; no scheduling
  interaction.
- **N5 delayed-retention KPI** on teacher dashboards — one aggregation query; pairs
  naturally with Track D's word states.
- **T5 audio load budget** — student-facing sound/quiet toggle; one dominant audio
  channel at a time (auto-read default ON is evidence-backed for young grades; keep it
  user-controllable).
- **N6 time-on-task persistence + extra-practice path** — after Track D; daily-cap
  changes interact with backlog dynamics the scheduler relies on.
- **T8 novelty injection** — after FSRS intervals land; scheduler notes predict level
  labels read lower under FSRS spacing, which changes how stagnation feels.
- **N7 mobile shell polish** — padding/nav/swipe pass.
- **N8 guided-reading/teacher-mediation mode** — roadmap item.
- **T10 flip-card mode, T14 exposure tracking, T15 frequency bands, T18 content-side
  cultural-diversity guidance** — watchlist.

## Not recommended (evidence, codebase, plan, or design review says no)

- **T20 cognate highlighting** — early audience is homogeneously Asian-L1 (the same
  rationale that cut placement/Track E); EN–ZH cognates are rare.
- **Expanding-interval SRS math / hand-tuned intervals** — closed twice over (Kim & Webb:
  equal ≈ expanding; Track D supersedes tuning). Verified ladder: 1/3/7/10/17/30/60.
- **Hard productive gates on promotion** — withdrawn for dynamic evidence-weighted
  points (scheduler notes §2.4); gates would corrupt the training signal mid-study.
- **Track A word-relationship compression** — shelved for Track D data-purity conflict.
- **Competitive mechanics** — verified absent (N9); Zhang & Hasim's competition
  drawbacks support keeping it that way.
- **N1 inline MC glosses, T11 deeper-hint tier, L1-in-error-feedback** — dropped in
  design review (see log below).

---

## Design-review decision log (2026-08-27)

Decisions made in review of Steps 0–3, with the reasoning recorded:

1. **Privacy/logging item held.** Typo persistence + `SchedulingDecision` log proceed;
   the LLM-log redaction/retention waits for a dedicated privacy pass. Note: this leaves
   the proposal §8 encryption-at-rest claim inconsistent with the system in the meantime.
2. **Item quality stays at CTT scope.** Confirmed against Assignment 4 (Decision 7:
   proportion-correct + point-biserial, min-count guards, shrinkage, flag-for-review;
   aggregation by question type when sparse). The data reality supports it: few
   questions will exceed ~10 responses in the next 12 months, so full IRT is
   unidentifiable. This report's per-type stratification delta was already capstone
   policy; the MI-distractor alarm is count-gated or deferred; the gradient check runs
   on delayed, aggregate accuracy.
3. **Embedding distractor check held.** Distractor goodness is context-dependent —
   semantic similarity to the key is not a reliable defect signal.
4. **Answer verification approved, reshaped.** An independent LLM re-solve of generated
   questions runs as a **batch job in off-peak windows**, not inline in generation —
   flags feed the existing review flow.
5. **L1 in error feedback: not adopted.** Rationale (user's, endorsed here): at higher
   mastery levels errors concern usage/connotation, not the meaning link, so L1
   translation doesn't address the failure; for higher-fluency learners L1 is a
   double-edged sword; and the research base for L1 *in error feedback specifically* is
   thin (the L1>L2 glossing result is about reading, not feedback; Jeon favors graduated
   hints over answer-giving). Adopted alternative: **ensure explanations and judge hints
   are written in easy, modified English** (consistent with Shute 2008 and Susanti's
   readability finding).
6. **Reveal-and-move-on: design validated, no change.** Wrong options disable when
   struck out, so MC questions self-terminate at the correct answer; type-to-spell shows
   the answer among the read-only reference options. No deadlock exists. Residual:
   remove or comment the unreachable escape at `ChoiceQuestion.jsx:92`.
7. **"Tell me more" tier: dropped.** Default hint length is deliberately capped for
   young readers, and the revision loop already graduates hint content across attempts —
   the graduated-assistance pattern (Jeon) is already implemented.
8. **Reader MC glosses: dropped.** Reading is the app's stress-free engagement phase;
   the cloze quiz that follows already provides per-word evaluative retrieval in story
   context; interruptive interactivity carries a documented comprehension cost for young
   readers (Furenes 2021).
9. **Reader L1 toggle: leaning yes, pending.** Meta-analytic support for L1 gloss
   availability (Yanagisawa 2020, no proficiency interaction); on-demand and
   off-by-default keeps the stress-free and double-edge concerns addressed.
10. **Achievements widget: approved, on hold.** Very visible counters + badges +
    per-set map, personal/non-competitive; blocked on a student-UI redesign pass.
