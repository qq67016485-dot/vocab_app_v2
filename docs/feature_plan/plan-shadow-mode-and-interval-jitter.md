# Plan: Shadow-Mode Predictive Scheduling, Interval Jitter & Supporting Instrumentation

> **Status: proposed (2026-09-10).** Implementation plan for the commitments made in the
> mentor reply (`C:\assignment\capstone\reply-to-dr-jiang-feedback-draft.md`) and the
> pre-specification in `C:\assignment\capstone\ENGINEERING-BACKLOG.md` +
> `FSRS_test\SCHEDULER-DESIGN-NOTES.md`. Companion to `srs-current-state-and-roadmap.md`
> (Track D §3.4) — that doc is the *why*; this one is the *how*, in build order.
> Each phase lists the stakeholder payoff (learners / teachers / parents / researcher)
> so scope decisions can be made on product value, not just research need.
>
> **Hard sequencing constraint (from the reply §7):** propensity logging must be live
> *before* any lateness-aware scheduling change, because once the realized gap enters
> the state update, jitter is no longer neutral. Phases 1–5 change no learner-facing
> scheduling behavior. Phase 6 (jitter) is IRB-gated. Phase 8 is post-validation only.

## 0. Goals & non-goals

**Goals**
1. Make the reply's analysis operationalization computable on prospective data
   (sentence-write first-attempt verdicts; per-level base rates).
2. Ship the shadow-mode harness: every scored answer logs what each memory model
   *would* predict/schedule, with no behavior change (roadmap Track D rollout step).
3. Ship the IRB-gated randomized interval jitter exactly as pre-specified
   ({−1, 0, +1, +2} days, known propensities, guardrails, stopping rules).
4. Take one cheap scheduling win already justified by the analysis (overdue weighting).

**Non-goals** (unchanged from the roadmap): Track A (relationship compression), Track E
(placement/CAT), any live model-driven scheduling before shadow validation, DKT/DeepFM.

---

## 1. Sentence-write first-attempt verdict persistence

**Gap found during reply validation (2026-09-10):** the reply §4 promises "only the
judge's *first-attempt* verdict counts (correct or almost = 1, incorrect = 0, regardless
of later recovery)." The app does not persist per-attempt verdicts: the revision loop's
history lives in the Django session (`SubmitAnswerView._SW_SESSION_KEY`) and is cleared
at terminal; `UserAnswer.judge_result` keeps only the terminal verdict, `attempts`
count, and `gave_up` (`practice_views.py:444-455`). `is_correct` is terminal-only
(`verdict == 'correct'`), so "almost = 1" is not expressible from logged data either.

**Change:** at terminal scoring (both the judged path and the give-up path), copy the
session-held attempt history into the terminal `judge_result` before
`_clear_sw_state`:

```python
judge_result = {
    ...,  # existing keys unchanged
    'attempt_verdicts': [a['verdict'] for a in prior_attempts] + [verdict['verdict']],
    'attempt_error_types': [a.get('error_type') for a in prior_attempts] + [verdict['error_type']],
}
```

- No migration — `judge_result` is a nullable JSONField. `attempt_verdicts[0]` is the
  first-attempt verdict the analysis codes; `UserAnswer.is_correct` semantics are
  unchanged (app logic untouched).
- Do **not** persist the raw sentence text (privacy floor; the session already holds it
  only transiently). Verdicts + error types suffice for the operationalization.
- Files: `backend/vocabulary/views/practice_views.py` (`_handle_sentence_write`,
  give-up path at ~`:364-375`, terminal path at ~`:432-455`).
- Tests: extend `backend/tests/vocabulary/test_sentence_write.py` — recovered-after-
  incorrect and recovered-after-almost cases produce the expected `attempt_verdicts`.
- **Payoff:** researcher — the promised outcome coding becomes real; learners — enables
  honest "first try vs. recovered" feedback later; no learner-facing change now.

## 2. Per-mastery-level empirical base rates

The reply's "(i) probabilistic stand-in" (per-level empirical first-attempt correctness)
is also the **interim predicted-correctness source for the jitter guardrail** (Phase 6)
until a validated model exists, and a cheap teacher-facing stat.

**Change:** management command `compute_level_base_rates` (sibling of
`compute_item_stats`), computing per (mastery level, trailing 90-day window) first-
attempt accuracy with min-n guards, written to a small table
(`LevelBaseRate(level, window_end, n, accuracy)`). Reuse `compute_item_stats.py`'s
min-n/flag-for-review conventions.

- Teacher/admin display is a *deferred optional* — the table is the deliverable; a
  dashboard read can follow once numbers stabilize.
- Files: new `backend/vocabulary/management/commands/compute_level_base_rates.py`,
  new model in `vocabulary/models.py` (+ migration).
- **Payoff:** teachers — "students typically forget X% at this stage" context;
  researcher — the incumbent stand-in for the report's decomposition; jitter guardrail
  gets a defensible interim probability.

## 3. Overdue-weighted retrieval (Track B, now justified)

The delay-ratio null result (reply §3: the incumbent's own delay ratio carries no
recoverable signal, p = 0.16–0.37) plus the scheduler's memorylessness means **serve
order is the only lever that responds to lateness at all**. Today the due pool is served
strictly oldest-due-first (`NextPracticeWordView`, due query per roadmap §1.1), so a word
2 days late on a 3-day interval competes equally with one 2 days late on a 17-day
interval — the former is far more at risk.

**Change:** order the due pool by overdue *ratio* — `(now − next_review_at) /
current_interval` descending — instead of `next_review_at ASC`. The current interval is
recoverable from the latest `SchedulingDecision.intended_interval_days` (fall back to
`level.interval_days` when absent). Keep every existing filter untouched (Hard Rules:
`is_serve_excluded`, lexile-or-NULL gate, READY-only, session dedup, daily cap).

- Behind a per-user or settings flag for a soft rollout; `reason_category` stays a
  display label.
- Files: `backend/vocabulary/views/practice_views.py` (due-query ordering only).
- Tests: serve-order tests with two overdue words at different intervals.
- **Payoff:** learners — most-at-risk words rescued before forgetting completes;
  parents — slightly steadier session composition; zero downside risk (order-only).

## 4. Shadow-mode prediction logging

The core of Track D: for every scored non-retry answer, log what each model **would**
predict and schedule — no behavior change. Two implementation options:

- **(a) In-request (rejected for now):** compute in `process_answer`. Requires per-
  (user, word) shadow state in the request path and adds failure modes to a hardened
  submit path.
- **(b) Batch replay (recommended):** a management command `compute_shadow_predictions`
  (cron/systemd, e.g. nightly) that replays new `SchedulingDecision` rows through
  py-fsrs + HLR, exactly as `capstone_fsrs_calibration.ipynb` does, and appends to a
  `ShadowPrediction` table. The notebook's replay conventions carry over directly:
  per-(user, word) card state, `review_card` returns an updated **copy** (store it
  back), tz-aware UTC timestamps, ≥24h-gap eligibility for scoring (but state advances
  on every event), retention target `DESIRED_RETENTION = 0.85`.

**Schema:**

```
ShadowPrediction
  scheduling_decision  FK → SchedulingDecision (unique)   # 1:1 join point
  model                char   # 'fsrs_frozen' | 'fsrs_recal' | 'hlr'
  p_correct            float  # model P(correct) at the realized gap
  proposed_interval    float  # days, solved at r = 0.85
  shadow_stability     float null                       # FSRS rows
  shadow_difficulty    float null                       # FSRS rows
  created_at           auto
ShadowModelState                                       # replay state, batch-only
  user, word, model, state_json, updated_at            # FSRS card / HLR counts
```

- Fitted parameters ship as a versioned artifact: copy `FSRS_test/outputs/
  fitted_parameters.json` into `backend/data/` (or a `ShadowModelArtifact` table if
  hot-swapping is wanted later — overkill now). Record the artifact version/hash on each
  `ShadowPrediction` row so refits stay distinguishable.
- The command must be idempotent (skip decisions already predicted) and tolerant of a
  missing artifact (log + exit 0 — shadow is best-effort, never a cron-page).
- **Payoff:** researcher — the prospective apples-to-apples dataset; teachers/parents —
  nothing visible yet, but this is the pipeline that eventually powers "predicted to
  forget" surfaces; learners — indirect (validates Phase 8).

## 5. Consent records (observation ≠ randomization)

The reply's guardrail "observation and randomization are separate consent checkboxes"
needs schema before any non-family participant exists. `CustomUser` currently has no
consent fields (verified 2026-09-10).

**Change:** `ConsentRecord(user, kind, granted, form_version, recorded_at, recorded_by)`
with `kind ∈ {'observation', 'randomization'}`, append-only (revocation = new row with
`granted=False`; effective consent = latest row per (user, kind)). Admin-entered at
first (paper/e-sign forms); a parent-facing checkbox UI is a separate later task tied to
the family-trial flow (`family-trial-self-serve-learning.md`).

- Jitter eligibility (Phase 6) requires effective `randomization` consent; analytics on
  SchedulingDecision/ShadowPrediction rows for the study requires `observation`.
- The IRB consent/assent drafts themselves live in the capstone workspace and need the
  randomization language added there — docs-side, not this repo.
- **Payoff:** parents — real, granular choice; researcher — the pre-spec is implementable
  as written.

## 6. Randomized interval jitter (IRB-GATED — ships dark)

Pre-specified in the reply §7 and ENGINEERING-BACKLOG:102-106. Build it behind a flag so
code review and tests happen now; enablement waits on IRB approval.

**Cohort (pre-specified, reproducible):** table `JitterCohort(user, word, enrolled_at,
rng_seed)` — an explicit management command `enroll_jitter_cohort --proportion p --seed
s` samples eligible (user, word) pairs once, records the seed, and writes rows. An
explicit table (not a hash) because the report must enumerate exactly which pairs were
eligible, and enrollment must be stable across deploys.

**Apply point:** `PracticeService.process_answer`, after the fragile cap and the
`max(MIN_REVIEW_INTERVAL_DAYS, …)` floor (`practice_service.py:511-526`), before
`next_review_at` is set:

1. Gate: flag on + pair in `JitterCohort` + effective randomization consent + answer is
   scored/non-retry.
2. Draw offset uniformly from {−1, 0, +1, +2} (nominal per-draw probability 0.25).
3. **Guardrail:** if offset > 0 and predicted correctness < 0.75, the push-later is
   vetoed and the applied offset becomes 0. Predicted correctness source: recalibrated
   FSRS from Phase 4 if available for this pair, else the Phase 2 level base rate
   (labeled in the log via which source was used — see semantics below).
4. Realized interval = max(1, intended + applied offset).

**Logging semantics (exact — the off-policy validity depends on it):**

- `intended_interval_days` keeps its current meaning: post-fragile-cap, **pre-jitter**.
- `jitter_offset_days` = the **applied** offset (post-guardrail), 0 when vetoed.
- `jitter_probability` = the probability of the *applied* offset under the policy,
  i.e. 0.25 normally, and P(applied = 0) = P(draw = 0) + P(draw > 0 ∧ veto) when the
  guardrail was active — compute it at draw time, not in post-processing.
- Realized interval = intended + applied; `next_review_at` reflects it (already does).
- Recommendation: add `jitter_drawn_offset_days` (small migration) so a vetoed draw is
  distinguishable from a drawn 0 — the pre-spec's "log the draw" requires it. Do this in
  the same migration as the cohort table rather than piggy-backing on 0042's reserved
  fields alone.
- `due_backlog_size` and all other `SchedulingDecision` writes are unchanged.

**Kill switch:** a settings flag checked before the gate; flipping it off mid-study
leaves already-written rows valid (their propensities are logged).

- Tests: draw distribution over a seeded RNG; floor at 1 day; guardrail veto path;
  consent-gated no-op path; flag-off no-op; `intended_interval_days` untouched by jitter.
- **Payoff:** researcher — the Δt-variance the decay slope needs (the roadmap §3.4
  caveat); learners — protected by the 0.75 floor and stopping rules; parents — bounded,
  consented, stoppable.

## 7. Stopping-rule monitoring

The pre-spec ties stopping to "falling accuracy, lost streaks, session abandonment, or
child/parent frustration reports."

**Change:** management command `jitter_health_report` (run alongside Phase 4's cron)
computing, per consented/jittered user vs. their own pre-enrollment baseline and the
non-jittered cohort: rolling 7-day first-attempt accuracy, streak breaks
(`CustomUser.current_practice_streak` resets), session abandonment (sessions started
with < N answers completed — `PracticeSession` rows), and daily-limit exhaustion rate.
Thresholds are pre-registered numbers, set in the command's constants and recorded in
the report text. Output: console + a row in a `JitterHealthLog` table so the IRB file
has an audit trail.

- Frustration reports arrive by humans, not telemetry: document an admin procedure
  (report → immediate flag-off for that user + IRB note). No UI in v1.
- **Payoff:** parents/learners — harm detection with teeth; researcher — the stopping
  rule is demonstrated, not just asserted.

## 8. (GATED FUTURE — post-validation) Lateness-aware scheduling / band architecture

Not built in this plan; recorded so the gate is explicit. Only after Phase 4's shadow
data shows a validated model (and Phase 6 has produced Δt variance):

- Intervals respond to the realized gap (today: memoryless — `practice_service.py` has
  no elapsed-time term by design).
- Band architecture per SCHEDULER-DESIGN-NOTES §2.5–2.6: recalibrated FSRS drives
  recognition levels (L1–3), the heuristic stays on production levels (L4–5) with FSRS
  shadow-observing, FSRS resumes at L6+; production failures never map to FSRS "Again"
  (the asymmetric-rating rule the heuristic already implements as `productive_missed`
  = −1, no demotion).
- **Dependency reminder:** once the realized gap enters the state update, jitter shifts
  the schedule's state — valid off-policy estimation then requires Phase 6's logged
  propensities. Do not start Phase 8 before Phase 6 has run.

---

## Cross-cutting requirements

- **Migrations:** Phase 1 none (JSONField); Phases 2, 4, 5, 6, 7 each add a table —
  separate migrations, separate deploys.
- **Tests:** pytest from `backend/`; honor `tests/conftest.py`'s autouse
  `cache.clear()` and the filesystem-redirect fixtures. Every gate path (flag off,
  consent absent, artifact missing) gets a no-op test.
- **Docs sync on each ship:** `docs/changelog_after_July_20.md` entry (CHANGELOG.md is
  an archive), `docs/architecture-decisions.md` for design decisions, `AGENTS.md` if a
  documented behavior changes, and `C:\assignment\capstone\ENGINEERING-BACKLOG.md`
  status marks.
- **Deploy:** standard redeploy (`migrate`, `collectstatic` if static touched,
  `sudo systemctl restart vocab`); Phase 4/7 commands get cron or systemd timers
  documented in `production-redeploy-quick-reference.md`.
- **Prod safety:** shadow replay and health reports run in the generation-host process
  or off-peak cron, never inside gunicorn request handling; jitter changes at most
  ±2 days of scheduling and is flag-controlled.

## Sequencing summary

| Phase | Deliverable | Behavior change | Gate |
|---|---|---|---|
| 1 | `attempt_verdicts` in `judge_result` | none | — |
| 2 | `compute_level_base_rates` + table | none | — |
| 3 | overdue-ratio serve ordering | serve order | flag, soft rollout |
| 4 | `ShadowPrediction` + batch replay | none | artifact present |
| 5 | `ConsentRecord` | none (admin-entered) | — |
| 6 | jitter cohort + offsets + guardrail | ±1/+2-day intervals for cohort | **IRB approval** + flag + consent |
| 7 | `jitter_health_report` + audit log | none | with 6 |
| 8 | lateness-aware / band architecture | scheduling itself | shadow validation + 6 |
