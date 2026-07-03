# Changelog

All notable changes to Vocab App V2 are documented in this file.

## [Unreleased] - 2026-07-03 (sentence-writing judge strictness + feedback UX)

### Context
- Iterative tuning of the sentence-writing answer-time judge and student feedback UI, driven by manual testing (typos + grammar mistakes were being marked fully correct). All decisions made with the user. Pure prompt/service/frontend changes — no migration.

### Changed — Judge now grades spelling
- `sentence_judge.txt` gained a **Spelling** rubric rule: a clear letter-level misspelling — the target word ("gragile" for "fragile") **or any other word** ("wrop" for "wrap") — keeps a sentence from being `correct` → `almost` with the new `error_type='spelling'`. A misspelled *target word* can **never** be `correct` (the student hasn't produced the taught word). Spelling alone is never `incorrect`. Capitalization/punctuation/spacing are still forgiven. `spelling` added to `VALID_ERROR_TYPES` in `sentence_evaluation_service.py` (the frontend doesn't branch on `error_type`, and scoring keys off `verdict`/`quality_rule`, so the new value is additive).

### Changed — Grammar feedback is notice-only (never blocks)
- Grammar unrelated to the target word still never lowers the verdict or triggers `incorrect`. But the judge now surfaces **one** clear, basic subject–verb/be-verb agreement error ("I were"→"I was", "my friends asks"→"my friends ask") as a separate coaching bullet. It explicitly does NOT flag articles, prepositions, word-order wobble, or punctuation. Rationale (ESL pedagogy): focused feedback beats comprehensive correction; protect the affective filter on a *productive* task; and LLM grammar judgment on child ESL writing is too unreliable to gate on (spelling is objective, grammar isn't).

### Changed — Coaching hints are now a bullet array (max 3)
- The judge output moved from a single `hint` string to a **`hints` array of 1–3 bullets** (cap enforced server-side in `_normalize_verdict`, not just the prompt): bullet 1 = word-focused feedback per `error_type`, bullets 2–3 = distinct spelling/grammar tips only when real (never padded). A joined `hint` string is retained for back-compat, TTS, and `UserAnswer.judge_result`. `practice_views.py` returns `hints` in the pending-miss response, terminal response, and `judge_result` (defensive `.get`, so older/mocked verdicts without `hints` fall back to `[hint]`). Frontend renders 1 bullet as a plain line, 2–3 as a `<ul>`.

### Added — Student's sentence shown in feedback
- The textarea is cleared on submit (fresh rewrite), so neither the revision view nor the terminal panel showed what the student wrote. Added `swLastSentence` state (`PracticeView.jsx`) → a **"You wrote"** quote above the hint in the revision view and a **"Your sentence"** block on the terminal panel beside the example (the side-by-side comparison is the noticing moment). The kid-friendly definition anchor stays shown on **both** guided and open variants (kept deliberately — this is a production task, not a recall task).

### Added — Manual test harness
- `python manage.py seed_sentence_write_test [--student … --password … --reset]` seeds a student (`swtest`/`testpass123` by default) with 3 words carrying guided+open sentence-write questions and READY progress rows due now (guided served at L4, open at L5), so the student flow is exercisable **without** running the LLM generation pipeline. The judge itself still needs a live `sentence_judge` LLM config.

### Tests
- `test_sentence_write.py`: +3 (spelling `error_type` preserved through normalization, `hints` array cap-3 + join, legacy single-`hint` → one-bullet fallback); full sentence-write suite 28 passing. Frontend `npm run build` compiles, lint clean (0 errors, 8 accepted baseline warnings). Prompt edits apply immediately (template loaded per judge call).

## [Unreleased] - 2026-07-03 (student practice/instructional review: XP-farming + scoring-integrity hardening)

### Context
- Multi-agent review (correctness + security + frontend) of the student-facing practice and instructional layer: `practice_views.py`, `practice_service.py`, `instructional_views.py`, `instructional_service.py`, `sentence_evaluation_service.py`, plus `PracticeView.jsx` and its children. Theme: the answer-submit path trusted the client for things the serve path already guarded. Every finding fixed same-day — 1 CRITICAL, 3 HIGH, 3 MEDIUM, 8 LOW. Verified invariants (cloze double-FK filter, NULL-lexile inclusion, server-tracked sentence-write cap, anchor/model-sentence hiding, injection-hardened judge) all held.

### Fixed — Daily Limit Not Enforced on Submit (CRITICAL: unbounded XP/mastery farming)
- `daily_question_limit` was checked only in `NextPracticeWordView` (serve) and the sentence-write branch — the generic MC/typed-answer submit path never re-checked it. A client could replay `POST /practice/submit/` with a known `question_id` (reading `correct_answer` out of the first correct response) to farm unlimited XP, mastery points, and streak. The gate now lives inside `PracticeService.process_answer` itself (single source of truth): a non-retry submit past the limit raises `DailyLimitReached`, which both submit paths translate to **HTTP 429** `{daily_limit_reached: True}`. Retries are exempt (they create no `UserAnswer`).

### Fixed — PENDING-Word Scoring (HIGH: bypasses the primer gate)
- `AssignmentService` creates a `UserWordProgress` row for every word at assignment time, including words in still-locked (PENDING) packs. `process_answer` matched on `(user, word)` with no status check, so a guessed/enumerated `question_id` for a not-yet-unlocked word could be scored. `process_answer` now raises (→404) unless `instructional_status == 'READY'`, and `_handle_sentence_write` re-checks READY **before** the judge LLM call (cost guard).

### Fixed — Lost-Update Race on Mastery/XP (HIGH)
- `process_answer` read `UserWordProgress` and `CustomUser`, mutated them in Python, and saved without locking — two concurrent submits for the same word (double-tap, retry racing a submit) both read the old `mastery_points`/`xp_points` and one increment was lost. Now uses `select_for_update(of=('self',))` on the `UserWordProgress` row (deliberately NOT the joined `MasteryLevel`, which would serialize all students) and `select_for_update()` on the re-fetched user before the streak/XP read-modify-write.

### Fixed — Frontend Double-Submit + Dead-Form Trap (HIGH)
- `handleAnswerSubmission` (`PracticeView.jsx`) guarded only on `feedback`, which is set after the await — a rapid double-tap fired two scored submits. Added an `isSubmitting` ref (synchronous guard, matching the retry/sentence-write paths). Separately, a failed submit did `setFeedback({error})`, which both rendered the scored UI and permanently short-circuited the resubmit guard, trapping the child in a live-looking but dead form with no visible error. Failures now set a separate `submitError` banner and leave `feedback` null so resubmission works; 429s route to the finish screen.

### Fixed — Sentence-Write Judge Cost Amplification (MEDIUM)
- Non-terminal ("almost") misses call the judge LLM but record no `UserAnswer`, so they escaped the daily-answer counter — an abandon-and-cycle pattern across many words ran unbounded judge calls. `SubmitAnswerView` now keeps a per-day cache counter (`sw_judge_calls:{user_id}:{localdate}`, ~25h TTL) with budget `daily_question_limit × (max_revisions + 1)`; checked before the judge, incremented at the call. The give-up path is exempt (no LLM call).

### Fixed — Hidden Level Name Leaked + Session-Bonus Replay (MEDIUM)
- `process_answer` returned the raw `MasteryLevel.level_name`, so a word promoting to hidden level 6/7 exposed the internal tier name ("Long-Term Retention") instead of "Mastered" — now masked (`level.level_name if not level.is_hidden else "Mastered"`), matching `dashboard_service`.
- `ApplySessionBonusesView` had no per-session dedupe (each call stacked up to +10 XP). It now records applied `session_id`s (the client's session-start timestamp) in the Django session (last 20 kept) and returns `{already_applied: True}` with 0 XP on replay; `handleFinishSession` sends `session_id`.

### Fixed — LOW cleanups
- `SessionSummaryView` floors `start_time` to 24h ago (a session is same-day) — an epoch timestamp no longer forces a full scan of the user's answer history.
- `SubmitAnswerView` clamps client `duration_seconds` (0–3600) / `answer_switches` (0–100) via `_clamp_int` before they feed the response-quality classifier.
- `ClozeQuiz` primer modal got proper dialog semantics: focus-into-dialog on open, Tab focus trap, Escape-to-close, focus restore to the trigger.
- Consistent `tabIndex={feedbackReady?0:-1}` gating on ALL terminal "Next" buttons (post-Explain + sentence-write terminal); `applyTerminalStats` now sets `feedbackReady` for incorrect terminals too (per the focus-after-DOM-removal rule).
- `PrimerCard` audio effect returns a cleanup that pauses the previous `Audio` — no overlapping pronunciation on fast navigation.
- Dead `sessionStats.finalLevel`/`leveledUp` client state removed.
- `settings.py`: explicit `SESSION_COOKIE_SAMESITE='Lax'` + `CSRF_COOKIE_SAMESITE='Lax'` + `*_SECURE = not DEBUG` + `SESSION_COOKIE_HTTPONLY` — the cross-site defense for the CSRF-exempt session auth is now intentional, not an implicit Django default.
- **`PracticeView.jsx` decomposed** 1101 → 861 lines: the four `renderQuestionInput` branches extracted to `frontend/src/components/practice/` (`CorrectFeedbackBlock`, `SentenceWriteQuestion`, `ChoiceQuestion`, `ScrambleQuestion`). Behavior-preserving; verified via `npm run build` + lint clean.

### Tests
- Backend: +7 tests (daily-limit-blocks-submit, retry-still-allowed-at-limit, PENDING-word-rejected, hidden-level-name-masked, session-bonus idempotency, distinct-sessions-each-apply, judge-call-budget with give-up exemption, start_time-floored-to-24h); full run 225 passing. Frontend: `npm run build` compiles, lint clean (0 errors, 8 accepted baseline warnings).

## [Unreleased] - 2026-07-03 (generation-pipeline review round 2: remaining 4 HIGHs fixed)

### Context
- Second same-day pass closing the four HIGH findings left open by the review below. Same theme — resume/restart paths trusting incomplete state — this time in the graphic novel / infographic candidate machinery. One co-located MEDIUM (infographic cloze silent drop) was fixed in the same files; both content types got the fix since they mirror each other.

### Fixed — Substep Restart Trusted Unvalidated Artifacts (GN + infographic)
- `restart_graphic_novel_from_substep` reconstructed prior-substep context from on-disk artifacts by *presence* alone — but artifacts are written **before** validation, so a substep that failed validation leaves unvalidated output on disk. A manual admin restart from a later substep silently fed that garbage into the remaining workflow. Prior substeps now require their **COMPLETED log** (`_load_validated_prior_substeps`), matching the automatic resume path. The infographic engine (`restart_infographic_from_substep`) had the identical flaw for its design artifact and got the identical fix.
- Both engines also deleted the candidate's existing novel/infographic **before** checking prior artifacts — a bad restart target destroyed the candidate and then errored. Validation now runs first; a rejected restart leaves the candidate untouched.

### Fixed — Candidate Persistence Was Non-Atomic + Skip Check Too Weak (GN + infographic)
- `_persist_candidate_novel` (novel → pages → review page → cloze) and `_persist_candidate_infographic` (row → cloze) were separate writes; a mid-write failure stranded a half-persisted candidate that the resume skip-check (`pages.exists()` / row-exists) treated as complete — selectable but broken. Both are now wrapped in `transaction.atomic()`.
- The skip check itself was upgraded: GN completeness = story pages + review page + `metadata['page_count']` match + staged cloze exists (`_candidate_novel_is_complete`); infographic = staged cloze exists. Pre-atomic half-persisted candidates are regenerated instead of skipped. **Selected (published) candidates are never deleted by a resume**, even if they look incomplete — safe because selection *copies* staged cloze on promotion, so complete candidates always keep theirs.
- Co-located MEDIUM fixed: cloze persist silently `continue`d on terms it couldn't join to a pack word, while the validator accepts an item via `term` OR `correct_answer` — a validated candidate could end up with zero servable cloze for a word, forever. Persist now joins by term OR correct_answer and **raises if any pack word gets no staged cloze row** (FAILED log → normal retry); items for non-pack words are dropped with a warning.

### Fixed — Substep-Restart Race (status claim now atomic in the thread function)
- `restart_graphic_novel_substep` / `restart_infographic_substep` unconditionally stomped `job.status = RUNNING`; the concurrency guard lived only in the REST views. New `_claim_job_for_restart()` does an atomic `select_for_update` check-and-set at the top of both thread functions: a job already PENDING/RUNNING is skipped with a warning (status untouched) instead of two runs mutating the same novels/cloze. The views — which already claim the job under their own row lock before spawning the thread (their 409 is authoritative) — pass `already_claimed=True`; every other caller (shell, tests, future code) gets the guard by default.

### Verified — WordSet `words.clear()` on DEDUP Restart Is Correct As-Is
- The "clears the ENTIRE WordSet M2M" finding resolved as a confirmed invariant, not a bug: `word_set.words` is pipeline-derived state — `run_full_pipeline` clears it wholesale at the start of every run, and teacher `add_word`/`remove_word` are locked out once generation starts (`_is_word_set_locked`). Restarting DEDUP rebuilds the M2M from the job's WORD_LOOKUP snapshot. Documented at the clear site; no behavior change.

### Tests
- 13 new tests: `TestRestartGuardsAndPersistIntegrity` (GN: restart rejects missing COMPLETED log without deleting the candidate; half-persisted candidate regenerated; selected candidate never deleted; persist rolls back on cloze coverage gap; correct_answer join), `TestInfographicRestartGuardsAndPersistIntegrity` (the same five for infographics, plus coverage), and orchestrator running-guard tests (direct call skipped on RUNNING job; `already_claimed=True` honors the view's claim).

## [Unreleased] - 2026-07-03 (generation-pipeline code review: 2 critical + 2 high correctness fixes)

### Context
- Full multi-agent review of `vocabulary/services/generation/` (~5,300 lines, 16 files): 4 module-focused correctness passes + 1 security pass. Security came back clean (no injection/traversal/secret-leak issues; artifact paths slugified + integer IDs, keys resolved from env-var names at runtime and never persisted, all LLM-driven counts hard-capped). The correctness findings clustered around one theme: resume/restart paths trusting incomplete state. The four worst were fixed same-day; the rest are recorded below.

### Fixed — Dedup Persist Was Non-Atomic (duplicate Word rows on crash + resume)
- `_step_dedup_and_persist` created `Word` → `WordDefinition` → embedding (network call) → `DefinitionEmbedding` as separate writes. A crash mid-word left a Word without its embedding — invisible to embedding-based dedup (and `Word` has no unique text/POS constraint), so resume recreated it as a duplicate row. Now each word's writes commit in one `transaction.atomic()` block with the embedding fetched before the transaction opens.
- Resume fast-path added: words already attached to the job's word set with an exact-text definition match are reused with zero embedding calls (previously every resume re-embedded every already-persisted word). A legacy half-written word (definition/embedding missing) is repaired in place with a warning instead of duplicated.

### Fixed — Dedup Reuse Attached an Arbitrary Definition to the Snapshot
- `find_duplicate_definition` matched on embedding similarity but returned only the `Word`; the snapshot then exact-string-matched the definition text (almost always a miss — the whole point of embedding dedup is the text differs) and fell back to `word.definitions.first()`, i.e. the **lowest-Lexile** definition by model ordering. A reused word could carry a definition the job never generated, at the wrong reading level, into translations/questions/primers. The function now returns the highest-similarity `WordDefinition` above threshold and the snapshot records exactly that definition.

### Fixed — Silently Dropped Batch Words Never Got Questions (question gen + sentence-write)
- Neither `_step_generate_questions` nor `_step_generate_sentence_write` verified that every word sent in a batch came back with output. A word the LLM dropped (truncation, JSON-mode quirk) got no questions, no error, and — because resume tracks per-word rows, not batch expectations — was never retried. Both steps now diff persisted terms against the batch and raise on a gap (FAILED log → normal retry regenerates just that batch), mirroring the `missing_terms` check translations already had.

### Fixed — Unmapped `question_type` Created Permanently Invisible Questions
- `_step_generate_questions` persisted whatever `question_type` the LLM emitted; a type not in `QUESTION_TYPE_LEVEL` (typo, trailing whitespace, or a model choice added without updating constants) created the row but attached no `suitable_levels` — never served to any student, counted as success. The type is now whitespace-normalized and resolved to a seeded `MasteryLevel` *before* the row is created; an unmapped type (or missing MasteryLevel row) fails the batch.
- Tests: 8 new + 3 updated across `test_step_word_lookup` / `test_embedding_service` / `test_step_questions` / `test_sentence_write`; full suite 544 passing. A post-fix review pass confirmed no stale callers of the changed contracts (`find_duplicate_definition` now returns `WordDefinition`; `_definition_for_snapshot` no longer has the `.first()` fallback; `_persist_tasks` returns persisted terms).

### Known Issues — Remaining Review Findings (not yet fixed)
- The four HIGHs originally listed here (restart artifact trust, non-atomic candidate persist, WordSet-wide clear, substep-restart race) and the infographic-cloze silent drop were closed the same day — see the "round 2" entry above.
- **MEDIUM** translation completeness is per-term not per-field; GN vocab-usage validator uses substring containment ("art" credited by "started" — should be `\b`-bounded); `LLMConfigError` bypasses the retry/observability machinery; `temp/llm_logs/` + `temp/generation_artifacts/` grow without bound (3.6 GB production box — needs a retention cron); ~35 duplicated lines between GN image first-attempt/retry blocks.

## [Unreleased] - 2026-07-03 (code review: sentence-write hardening + hot-path performance pass)

### Fixed — Sentence-Write Revision Loop Is Now Server-Tracked (was client-spoofable)
- The revision loop shipped 2026-07-01 as "frontend-driven with backend cap validation", but the cap and the fragility decision were computed from a **client-posted `prior_attempts`** — a client that always claimed an empty history got (a) unlimited judge LLM calls (pending misses record no `UserAnswer`, so they also bypassed the daily limit) and (b) an undeserved first-try +5 XP after any number of real misses. Attempt history ({sentence, hint, verdict} per try) now lives server-side in the session (`SubmitAnswerView._SW_SESSION_KEY` — single key, resets when the question changes, same pattern as the typo-retry flag); the request body's `prior_attempts` is ignored. Judged submits are additionally gated on `daily_question_limit`. Pending responses return server-truth `attempts_used`/`revisions_left`, which the frontend now displays instead of tracking its own ref.
- **Judge circuit breaker also trips on `LLMConfigError`**: previously a missing/broken `sentence_judge` step config raised `SentenceJudgeUnavailable` *without* recording a failure, so the breaker never tripped and the picker kept serving sentence questions that could never be judged — since discarded attempts record no answer, the same word stayed first in due order and the student was stuck in a loop. Config errors now count toward the 3-failure threshold.
- **Frontend submit feedback** (`PracticeView.jsx`): the disabled/checking state was driven by a `useRef`, which never re-renders — the Submit button looked live during the 2–10s judge round-trip. Now `swBusy` state disables both buttons and shows "Checking…" (the ref stays as the re-entry guard); the attempt counter moved from a ref to `swAttempts` state fed by the server's `attempts_used`.
- Tests: 4 new view tests (cap not resettable by client state, no first-try bonus after a server-tracked miss, daily-limit gate, config-error breaker) + 2 rewritten to exercise the real multi-submit loop.

### Fixed — Retry Incremented `retry_count` on Every Historical Answer
- `PracticeService.process_answer`'s retry branch ran `.order_by('-answered_at').update(retry_count=F(...)+1)` — Django's `.update()` silently ignores `order_by`, so every historical `UserAnswer` for that user+question was incremented, corrupting retry analytics. Now fetches the latest row's pk and updates only that row. Test: `test_retry_increments_only_latest_answer`.

### Changed — Practice/Dashboard Hot-Path Performance (migration `0040_practice_hot_path_indexes`)
- **Due-words query** (the hottest in the app, `NextPracticeWordView` + `StudentDashboardView`): replaced the `word__questions__…` join + `DISTINCT` (multiplies each progress row by its ~30-60 questions, then dedup-sorts) with an `Exists()` subquery on Question; and removed the `.exists()`-then-`.first()` double execution (now `.first()` + None check).
- **Sargable date filters**: `answered_at__date=today` compiles to `DATE(CONVERT_TZ(col))` on MySQL — non-sargable, scans the student's entire answer history, at 4 sites (`practice_views`, `dashboard_views` ×2, `dashboard_service`). All now use a range filter via the new `start_of_local_day()` in `vocabulary/utils.py`.
- **Timing baseline cached**: `_get_timing_baseline` (an O(history) `UserAnswer⋈Question` scan inside every scoring transaction) is now cached per `(user_id, question_type)` for 10 min (`TIMING_BASELINE_CACHE_TTL`, `''` sentinel for "not enough samples").
- **Pack-open path** (`instructional_service.get_pack_data`): the old code prefetched all 3 candidates' pages+audio then bypassed the cache with `.filter(is_selected=True)`, re-querying pages and doing 1 query/page for audio + 2 queries/word for translations (~25-30 queries per pack open). Now uses filtered `Prefetch`es consumed as-is (selected novel with `pages`+`select_related('audio')`, selected infographic, promoted cloze) and batches translations via the new `get_definition_translations_for_words()` utils helper (2 queries total).
- **Admin review endpoints**: `GenerationJobContentView` and `WordSetContentView` carried two byte-identical ~120-line pack-serialization blocks that both defeated their own prefetches (`.select_related()` / `.filter()` on prefetched managers → fresh query per pack + 1 query per promoted cloze row, ~45 avoidable queries per load). Extracted into a shared `_review_packs_data()` with the prefetch shaped up front (`items__word__primer_content`) and cloze filtered in Python. Also removed the unused `input_words_lower`.
- **Indexes**: `UserWordProgress(user, instructional_status, next_review_at)` serves the due-query index-ordered with no filesort (replaces the redundant `(user, instructional_status)` two-column prefix); `Question(word, lexile_score)` makes the per-word lexile probe index-only.
- **Smaller wins**: `SubmitAnswerView` passes its already-fetched Question into `process_answer` (new optional `question=` param — one PK lookup saved per submit); `_pick_question` select-relates `word`/`word__primer_content` for the serializer; `/practice/next/?peek=true` (the frontend's session-goal availability check) returns `{available: true}` before question selection instead of running the full pipeline.
- **Ops note (CLAUDE.md)**: production gunicorn must run `--worker-class gthread --threads 8` — the sentence judge blocks a worker for a synchronous 2–10s LLM round-trip; with the default 3 sync workers, 3 concurrent judged submits would stall every request on the box.
- Tests: full backend suite passes (536). Frontend lint: 0 errors (8 accepted baseline warnings).

## [Unreleased] - 2026-07-03 (frontend lint errors fixed — 0 errors)

### Fixed — Cleared All 22 ESLint Errors Surfaced When the Config Was Added
- Follow-up to the "frontend ESLint config added" entry below, which surfaced 22 pre-existing errors + 8 warnings and explicitly left them for later. `npm run lint` now reports **0 errors** (8 warnings remain, see below). 14 files touched; changes are cleanup + one correctness fix, no intended behavior change.
- **`react-hooks/rules-of-hooks` in `GenerationWizard.jsx` (genuine bug)**: the `if (user?.role !== 'ADMIN') return …` early return sat *before* two `useCallback` hooks, so hooks were called in a different order for admins vs non-admins (React's cardinal rule violation). Moved the admin guard below all hooks.
- **Unused `catch` bindings** → optional catch binding (`catch {`) in ClozeQuiz, PrimerCard, ThemeSwitcher (also fixed its `no-empty`), GraphicNovelPageEditor, GenerationReview, GenerationWizard, LLMConfig, StudentDashboard, WordSetDetailView. The config uses ESLint's default `caughtErrors`, so an unused `(e)`/`(err)` errors — drop the binding when the handler doesn't use it.
- **Dead code removed**: unused `useRef` / `useUser` / `useNavigate` imports and their bindings (StudentDashboard, CommandCenter, GroupManagementView), an unused `fetchPacks` function and `stepLabel` var, and the write-only `swAttemptCount` state in PracticeView (value never read; dropped its two setter calls — `swPriorAttemptsRef.current.length` already tracks attempts).
- **8 warnings deliberately left** (behaviorally sensitive, not blind-fixable): 5 `react-hooks/exhaustive-deps` (missing `fetchNextQuestion` / `handleFinishSession` / `loadData` / `user?.id` — adding them risks re-fetch/render loops) and 2 `react-refresh/only-export-components` on `ThemeContext.jsx` / `UserContext.jsx` (each exports a component + a hook; dev-only fast-refresh cosmetic, would require splitting each context into two files).

## [Unreleased] - 2026-07-03 (sentence-writing: guided-only Lexile floor + prompt/judge tuning)

### Changed — Lower-Proficiency Readers Get Guided-Only Productive Practice
- Open (unscaffolded, L5) sentence-writing is too hard for younger / lower-proficiency ESL learners. New rule: when a word set's content Lexile (`_content_lexile` = `target_lexile × 0.85`) is **≤ 600** (`SENTENCE_WRITE_GUIDED_ONLY_MAX_LEXILE` in generation `constants.py`), the pipeline **skips the OPEN variant entirely** and attaches the GUIDED question (scenario + starter) to **both** mastery L4 and L5 — so those students still practice production at L5, always scaffolded. Above 600, guided→L4 / open→L5 as before.
- Implemented in `step_sentence_write.py` (not a prompt-level skip like `WORD_FORM_MC`): the open variant is a separate LLM call, so a prompt "return empty" would still burn the call each run/resume, and mastery levels are assigned in code — only code can make guided serve at L5. `_persist_tasks` now takes a list of levels. New-jobs/regeneration only.

### Changed — Sentence-Writing Prompt & Judge Quality Tuning (prompt-only)
- `sentence_write_guided.txt`: the starter rule now demands **semantic constraint** — the blank must carry meaning (prefer a causal "… because/so/until ___" second blank over a single open trailing blank), reject frames completable with generic filler ("I have a cat"), don't buy constraint with length at low Lexile. `usage_reasoning` must now name the generic completion the starter rules out (a per-word self-check). Rationale: the starter is only a *suggested opener* (student writes free text; the judge never sees the starter), so a weak starter points a scaffolded L4 child toward a judge-rejected sentence rather than corrupting grading.
- `sentence_write_open.txt` + `sentence_write_guided.txt`: the **model sentence** is now capped at/below `target_lexile_level` (it's shown to a stuck student).
- `sentence_judge.txt`: rubric #2 sharpened so **wrong part-of-speech** use ("I like foreign") is a real error, distinct from forgivable article/word-order slips. Grammar policy stays global in the judge, not sprinkled per-word into `acceptable_use_notes`.
- Tests: `test_sentence_write.py` updated (two "both variants" tests pinned to a high Lexile; new `test_guided_only_below_threshold_skips_open_and_serves_l4_and_l5`); 19 pass. Prompt-content edits take effect on the next `SENTENCE_WRITE_GEN` run; the judge edit applies immediately (template loaded per call).

## [Unreleased] - 2026-07-03 (frontend ESLint config added — lint now runnable)

### Fixed — Frontend Lint Runs Project-Wide Again
- The frontend had ESLint 9 and its flat-config plugins in `devDependencies` and a `lint` script (`eslint .`), but no `eslint.config.js`, so `npm run lint` / `npx eslint .` errored out with "couldn't find an eslint.config file". Earlier entries in this changelog noted frontend lint as "not runnable (repo has no ESLint v9 config, pre-existing)" — this closes that gap.
- Added `frontend/eslint.config.js`: standard Vite + React 19 ESLint 9 flat config wired to the installed plugins (`@eslint/js` recommended, `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh`), browser globals, `dist` ignored, and `no-unused-vars` allowing `^[A-Z_]`-prefixed names.
- Lint now runs across the whole project. The first run surfaced 22 pre-existing errors + 8 warnings (previously invisible), mostly unused `catch` bindings and unused imports; two `react-hooks/rules-of-hooks` errors in `GenerationWizard.jsx` (conditional `useCallback`) are genuine correctness risks left for a follow-up. No source files were changed by this entry.

## [Unreleased] - 2026-07-01 (sentence-writing questions — productive, LLM-judged)

### Added — Students Write Their Own Sentence, an LLM Judges It
- A new **productive** question type: instead of choosing an option, the student writes an original sentence using the target word. It is the first question type not auto-graded by exact string match — an LLM judge reads the sentence, returns a `correct`/`almost`/`incorrect` verdict, and (on a miss) a warm coaching hint that guides a revision without giving away the answer.
- **Two variants, gated to the top of the mastery ladder** (via `QUESTION_TYPE_LEVEL`): `SENTENCE_WRITE_GUIDED` at Level 4 (a concrete scenario + a sentence starter) and `SENTENCE_WRITE_OPEN` at Level 5 (a lighter "connect it to your own life" prompt, no starter). Both are mixed into the normal review queue at those levels. New skill tag `sentence_production`.
- **New pipeline step `SENTENCE_WRITE_GEN`** (now step 5 of 11, after `QUESTION_GEN`): `step_sentence_write.py` generates 2 questions per word (batch size 10, idempotent per word per variant on resume) from two independent prompts (`sentence_write_guided.txt` / `sentence_write_open.txt`). Lexile-aware — scenario readability plus a judge-leniency bar stored in each question's rubric anchors, so an 8-year-old's simple-but-correct sentence isn't marked against a 14-year-old's bar. Reuses the `Question` model (scenario→`question_text`, model sentence→`example_sentence`, rubric anchors→`options`, `correct_answers=[]`).
- **Answer-time judge** (`services/sentence_evaluation_service.py`, own LLM step key `sentence_judge`, admin-tunable in the LLM Config Matrix): prompt-injection-hardened (the student sentence is treated as data only), structured verdict + `error_type` + `hint`. The revision loop is frontend-driven with backend cap validation (Guided allows 3 revisions, Open 2); a "Show me an example" exit reveals the model sentence and scores gently. Only the terminal attempt is scored.
- **Scoring** reuses the response-quality machinery: first-try correct → full mastery point **+5 XP bonus**; correct after a genuine miss → fragile (shorter review interval); a genuine miss (give-up / revisions exhausted) → **softened** penalty (−1 point, no forced demotion). The judge verdict + feedback are persisted on `UserAnswer.judge_result` (new nullable JSON) for analytics and fairness auditing.
- **Resilience**: if the judge LLM is unavailable, a circuit breaker (3 consecutive failures → 5-min flag) makes the practice picker skip sentence-writing questions (students still get receptive questions), and a submit-time judge failure discards the attempt without penalty. Sentence-writing is also never served two sessions running for the same word.
- Scope: **new jobs only** — existing word sets gain these questions only when regenerated or via a `SENTENCE_WRITE_GEN` restart-step. Migrations `0038` (schema: 2 question types, the step + 2 config-set step keys, `UserAnswer.judge_result`) and `0039` (seed `sentence_write_gen` + `sentence_judge` into all 3 config sets, cloned from `question_gen`).
- Full design: `docs/feature_plan/design-sentence-writing-questions.md`. Tests: `backend/tests/vocabulary/test_sentence_write.py` (18); full backend suite passes (530).

## [Unreleased] - 2026-07-01 (assignment gated on published content type)

### Changed — Teachers Can Only Assign a Word Set That Has Published Content
- Previously the assign dialog always offered both "Graphic novel" and "Infographic" radios regardless of whether either format had actually been generated and admin-selected, so a teacher could assign a set whose chosen format was never published (the student then silently fell back to the other format, or saw nothing).
- The assign flow is now gated on **published (admin-selected) content**. A content type is offered only when at least one pack in the word set has a candidate of that type with `is_selected=True`. If the set has neither, it cannot be assigned at all.
- `teacher_views.py`: new helper `_available_content_types_for_word_set(word_set)` returns which of `graphic_novel`/`infographic` have a selected candidate. The `assignments/` GET action now returns `available_content_types`; the `assign/` POST action rejects (HTTP 400) when nothing is published, or when the submitted `content_type` isn't in the available list — this also guards direct API calls, not just the UI.
- `AssignSetForm.jsx`: reads `available_content_types`. Neither published → the whole form is replaced with a blocking notice (Close only). Exactly one published → that format is shown as a read-only label (no radio). Both published → the two radios render as before. The default respects the prefilled type from existing assignments but falls back to the first available type if that type was unpublished since.
- Tests: `test_assigns_word_set` updated to set up a selected graphic novel (the new gate requires it); full backend suite passes (127).

## [Unreleased] - 2026-06-26 (infographic style: tone down storybook feel → modern editorial infographic)

### Changed — Pushed the Infographic Look From Storybook Illustration Toward Modern Editorial Infographic
- Follow-up to the art-directed per-candidate style change (below, same day). The generated posters still read as children's-storybook illustrations; the user wanted them to look more like modern infographics. The fix is prompt-only — it retunes the art-direction language so the LLM composes editorial-infographic style phrases instead of warm storybook ones (no code-flow change).
- `infographic_image.txt`: line 1 reframed from "poster for children" to "for students … a modern editorial explainer infographic in the style of a professional magazine/museum/data-visualization graphic", with an explicit "NOT a children's storybook or picture-book illustration". `STYLE_LOCK` floor reworded: "kid-friendly educational vector/illustration" → "modern flat-vector editorial infographic", "rounded sans-serif" → "geometric sans-serif", plus a new negative clause ruling out storybook / fairy-tale / whimsical-cartoon looks (kept crisp, contemporary, informational).
- `infographic_design.txt`: role line now frames the deliverable as "a modern editorial explainer graphic … NOT a children's storybook"; the art-director style menus (step 7) dropped `TED-Ed animation style`, `stylized characters`, and `cohesive visual storytelling`, and added `clean diagrammatic design`, `data-visualization explainer look`, `simplified iconographic figures`, and `labeled callouts and connector lines`; "warm and inviting tones" → "confident editorial color blocking"; the family constraint now also bars a "children's storybook / picture-book / cartoon look". `color_palette` guidance dropped "kid-friendly … warm, inviting tones" for "a confident editorial feel".
- `step_infographic.py`: `DEFAULT_INFOGRAPHIC_STYLE` fallback reworded to the editorial-infographic vocabulary (Dribbble / Behance / NotebookLM / data-viz, geometric lettering, "Not a children's storybook or cartoon look").
- Audience guidance unchanged: still ESL ages 8–14, legible, uncluttered, go-easy-on-people. Asterisk vocab-emphasis and no-glossary rules untouched. No tests assert on the changed strings; existing `test_infographic.py` (21) unaffected. New candidates pick up the change on next generation; existing posters keep their stored `style_prompt` until regenerated.

## [Unreleased] - 2026-06-26 (infographic art-directed per-candidate style, NotebookLM aesthetic)

### Changed — Per-Candidate Art Direction So Infographic Candidates Don't All Look Alike
- A user-supplied analysis of NotebookLM infographics gave a curated art-style vocabulary. The goal was to adopt that aesthetic **without** making the 3 per-pack candidates look identical — the user emphasized "mix and match".
- Root cause of prior sameness: the design prompt's JSON schema emitted **no `style_prompt`**, so every candidate fell back to the single `DEFAULT_INFOGRAPHIC_STYLE` constant and shared one look. A heavier *fixed* style would have made this worse.
- `infographic_design.txt`: added an art-director step that has the LLM mix-and-match a **distinct** combination per candidate from three menus — CORE STYLE (modern vector illustration / TED-Ed / Dribbble-Behance / flat design with soft 3D shading), COLORS & LIGHTING (vibrant cohesive palette / soft gradients / warm inviting tones), DETAILS (clean outlines / smooth curves / banners-ribbons / floating text boxes / stylized chars) — emitting it as a new `style_prompt` field. `color_palette` guidance tightened to 3–5 specific vibrant colors, varied per poster. Each of the 3 candidates runs a separate design call, so they now diverge.
- `infographic_image.txt`: `{style_prompt}` now leads as the art direction; `STYLE_LOCK` slimmed from a heavy fixed style to a thin shared *floor* (kid-friendly vector, legible lettering, one unified piece, no photorealism / *photorealistic* 3D render / muddy colors — soft dimensional shading is allowed) that must not override the per-poster style. Line 1's hardcoded "National Geographic / museum poster" framing was neutralized so it no longer pulls every candidate toward one look.
- `step_infographic.py`: `DEFAULT_INFOGRAPHIC_STYLE` reworded to the new vocabulary (fallback for candidates lacking `style_prompt`, e.g. older ones). No code-flow change — `style_prompt` already flowed `design_result → Infographic.style_prompt → {style_prompt}`, it was just never populated. `style_prompt` is optional in the validator.
- Deliberate clarification vs the raw feedback: it said "flat design with soft 3D shading" while the old prompt banned "3D render" — kept the ban on *photorealistic* 3D render only, so soft dimensional shading/gradients are now allowed.
- Tests: no new tests; existing `test_infographic.py` (21) pass (`build_infographic_image_prompt` already covered).

## [Unreleased] - 2026-06-25 (infographic intro text teaches every target word)

### Changed — Infographic Intro Hook Now Uses Every Target Word
- The infographic's `intro_text` (the short paragraph students read above the poster) used the vocab words only optionally, so generated hooks often mentioned none of them. Students should be able to learn the words from reading that text too.
- `infographic_design.txt`: the `intro_text` instruction (and its JSON-schema description) now require the hook to **naturally use every target word in context** — one flowing mini-scenario in the same sequential-beats style as the captions, never defining them, kept at/below the target Lexile (allowed to grow to ~2–4 sentences so all words fit smoothly).
- `step_infographic.py`: `_validate_infographic_design_result` now rejects a design whose `intro_text` omits any target word (stem-tolerant match for plurals/`-ed`/`-ing`, shared with the caption check via the new `_term_in_text` helper). The design substep retries up to 3× internally, so a first-pass miss is re-rolled rather than published.
- Tests: fixture intro updated to use both words; new `test_rejects_intro_text_missing_a_target_word` in `test_infographic.py` (21 pass).

## [Unreleased] - 2026-06-25 (infographic student reader: full size + word pronunciation)

### Changed — Infographic Reader Matches Graphic Novel Size
- The student infographic poster rendered small (capped at 1000px) while the graphic novel reader widened the whole student shell to ~1792px. Since infographic posters are landscape 16:9, the reader can use the same size.
- `graphic-novel-reader.css`: added `[data-app="student"].app-shell:has(.infographic-reader)` → `max-width: min(1792px, 90vw)` (mirrors the GN reader's shell-widening rule) and dropped the `.infographic-reader` width cap; the poster image fills 100% width with `object-fit: contain` and no height cap (a full-width 16:9 image stays within the viewport).

### Added — Tap-to-Hear on Infographic Vocab Words
- Each vocab word in the list below the infographic now has a 🔊 button that pronounces it via the browser's built-in speech synthesis — the same `TextToSpeechButton` (Web Speech `speechSynthesis`, en-US, rate 0.8) already used in the graphic novel reader, practice, and primer views. No backend/TTS audio involved (distinct from the graphic novel audiobook pipeline).
- `InfographicReader.jsx` only; frontend lint not runnable (repo has no ESLint v9 config, pre-existing).

## [Unreleased] - 2026-06-25 (infographic content polish: drop filler subtitles, fewer people)

### Changed — Infographic Title Has No Subtitle
- The infographic title used a "Main Idea: Subtitle" format, but recent generations produced filler subtitles ("A Vocabulary Guide", "Vocabulary Words") that add no learning value.
- `infographic_design.txt` now asks for a single-line big-idea title (no colon, no subtitle, and bans generic vocab tags); `infographic_image.txt` no longer instructs the subtitle style and just renders the title as a bold heading.
- Safety net for prompt drift: `_clean_infographic_title()` in `step_infographic.py` strips a trailing generic subtitle (`: A Vocabulary Guide`, `— Vocabulary Words`, `: Vocabulary`, etc.) on persist, but only when meaningful text remains before the separator — a genuine subtitle like "The Solar System: A Tour of the Planets" is kept. Applies to new generations only (existing rows unchanged).

### Changed — Infographics De-emphasize People
- Learners fixate on faces and the image model often distorts human figures, pulling focus from the vocabulary. Both infographic prompts now lean away from people — **soft guidance, not a ban** (people are fine where natural).
- `infographic_design.txt`: each scene element favors objects/tools/places/animals/landscapes; the narrative thread can still be a person but "an object or animal often works better"; caption examples reworked to keep focus on the subject (e.g. the bean) rather than farmers/workers.
- `infographic_image.txt`: keep human figures few, small, and simple, with no large close-up faces.
- Tests: 7 new `_clean_infographic_title` cases + a persist-cleaning case in `test_infographic.py` (20 pass).

## [Unreleased] - 2026-06-25 (admin status: infographic design substep accordion)

### Fixed — "Infographic Design" Step Hid the Design Substep
- On the generation-job status page, the **Infographic Design** step row showed cloze-generation state, not design. Root cause: infographic generation runs two LLM substeps per candidate (`design` → `cloze`) that **both log under the single `INFOGRAPHIC_DESIGN` step** (`step_infographic.py`); the frontend keys logs by step (`logMap[log.step]`), so the row reflected whichever substep logged *last* (a cloze log), and the design substep was invisible. The graphic novel script step had had a per-candidate substep accordion all along; infographics had none.
- **Fix mirrors the GN substep treatment**:
  - Backend (`generation_views.py`): extracted the GN-specific substep serializer into a generic `_substep_statuses_for_step(job, step, substep_defs)` (and `_new_substep_map(substep_defs)`); added `INFOGRAPHIC_DESIGN_SUBSTEPS` (`design`/`cloze`) and a new `infographic_design_substeps` field on the job-status payload. `_graphic_novel_script_substep_statuses` is now a thin wrapper, so GN behavior is unchanged.
  - Frontend (`GenerationJobStatus.jsx`): generalized the substep accordion into `renderSubstepAccordion(substepData, previewSubsteps, allowRestart)` and rendered it under the `INFOGRAPHIC_DESIGN` step too, with `INFOGRAPHIC_SUBSTEPS` as the preview order. Infographic substeps render **read-only** (`allowRestart=false`) because the `restart-substep` API is graphic-novel-only — no infographic substep-restart endpoint exists yet.
- The Infographic Design step now expands into per-pack, per-candidate rows showing **Infographic Design** and **Infographic Cloze** separately, each with its own status.
- Verified against job 52 (infographic-only): serializer returns both substeps per candidate; full status view builds with the new field; 27 infographic + orchestrator tests pass. (Frontend lint not runnable — repo has no ESLint v9 config, pre-existing.)

### Added — Infographic Substep Restart (closes the gap left above)
- The substep accordion above was initially read-only because no infographic substep-restart API existed (only the GN one). Added the endpoint so an admin can regenerate a single infographic candidate from a chosen substep — matching the graphic novel ↻ button.
- **Endpoint**: `POST /api/generation-jobs/{id}/restart-infographic-substep/` (`pack_id` + `substep` ∈ {`design`,`cloze`} + optional `candidate_index`). `RestartInfographicSubstepView` mirrors `RestartGraphicNovelSubstepView`: validates against `VALID_INFOGRAPHIC_SUBSTEP_KEYS`, sets the job RUNNING, runs `orchestrator.restart_infographic_substep` in a daemon thread (202; **409** if already running; **404** for unknown pack/job).
- **Orchestrator** (`restart_infographic_substep`, re-exported via the `generation_pipeline_service` shim): regenerates the targeted candidate via `restart_infographic_from_substep`, then runs `_step_infographic_design` over **all** packs to fill any candidate the original run never reached (same orphan-fill guard as the GN substep restart). Does **not** re-render the poster image — the admin re-runs `INFOGRAPHIC_IMAGE` separately if needed.
- **Frontend** (`GenerationJobStatus.jsx`): `renderSubstepAccordion` now takes a `restartEndpoint` arg (GN → `restart-substep`, infographic → `restart-infographic-substep`; null disables the button); `handleSubstepRestart` posts to the given endpoint. The infographic accordion is now interactive.
- Tests: `TestRestartInfographicSubstep` (orphan-fill + failure→FAILED) in `test_orchestrator.py`; view tests for the payload split + endpoint validation/202/409 in `test_views.py`. 65 backend tests pass; frontend builds clean.

## [Unreleased] - 2026-06-24 (new content type: single-page infographic alongside graphic novels)

### Added — Infographic Content Type (NotebookLM-style explanatory poster)
- Some teachers who demoed the app disliked the multi-page graphic novels and wanted a single-page infographic with a short explanatory text. Added **infographic** as a second instructional content type, chosen per-assignment.
- **Model** (`migration 0036`): `Infographic` FK→WordPack mirrors `GraphicNovel` single-page — same 3-candidate + admin-select model (`unique_together=('pack','candidate_index')`, `is_selected`, no auto-select), `content` JSON (`layout_mode`/`big_idea`/`visual_structure`/`scene_description`/`scene_elements[]`/`entries[]`), single image with PNG+JPEG `display_image`/`student_image` variants. `StudentWordSetAssignment.content_type` (`graphic_novel`/`infographic`); `GenerationJob.content_types` (JSON, default `['graphic_novel']`) + `infographics_created` counter.
- **Shared cloze (CRITICAL)**: `ClozeItem` gains a nullable `infographic` FK alongside `novel`. Active/promoted cloze = **both FKs NULL**; staged = one set. All active-cloze reads updated to filter `novel__isnull=True, infographic__isnull=True` (instructional_service, both review endpoints, both selection services) — filtering only `novel__isnull=True` would leak staged infographic cloze to students. Active set is shared across content types (last published wins).
- **Pipeline** (`step_infographic.py`): two new steps appended to `PIPELINE_STEP_ORDER` — `INFOGRAPHIC_DESIGN` (per pack, 3 candidates × 2 substeps `ig_design`→`ig_cloze`) and `INFOGRAPHIC_IMAGE` (one poster per candidate). `orchestrator._run_step` skips a content type's steps when not in `job.content_types` (gates GN steps too). New `LLMStepConfig` keys `ig_design`/`ig_cloze` seeded across all 3 sets (`migration 0037`). Engine `restart_infographic_from_substep(...)`; artifacts under `…/pack_{id}_{slug}/infographic_cand_{i}/`.
- **Style — NotebookLM-class, not flashcards** (3 prompt iterations): the design LLM acts as art director and picks a `layout_mode` — `panorama` (one continuous landscape/map with a visual spine, for sequential packs) or `gallery` (vignettes in a creative framing device — never a plain grid — for disjointed packs). Captions USE each vocab word in a sequential narrative sentence (never `word: definition`; validator rejects the glossary format and requires the word in its caption); definitions live only in `entries` (study panel + cloze). `build_infographic_image_prompt` branches the image template's layout guidance on `layout_mode`. Title in "Main Idea: Subtitle" form; callout-line captions (not boxed). Prompts: `infographic_{design,cloze,image}.txt`.
- **Selection + serving**: `POST /api/infographics/{id}/select/` (`SelectInfographicCandidateView` → `infographic_selection_service.select_infographic_candidate`) mirrors GN select + promotes cloze. `instructional_service.get_pack_data` serves the student's assignment `content_type`, falling back to the other published type then legacy stories. Review endpoints return `infographics` (array) + `infographic` (selected/null).
- **Frontend**: `InfographicReader.jsx` (routed in `InstructionalFlow` on `story.type === 'infographic'`); content-type radio in `AssignSetForm.jsx`; content-types checkboxes in `GenerationWizard.jsx`; `PackInfographics` review section in `GenerationReview.jsx`; infographic steps in `GenerationJobStatus.jsx` (filtered by `job.content_types`).
- Tests: `tests/vocabulary/test_infographic.py` (selection/promotion, shared read-filter isolation, content-type serving + fallback, generation engine, glossary-caption rejection, layout-mode branch) + orchestrator content-type gating. Full backend suite passes; frontend builds clean.

## [Unreleased] - 2026-06-10 (admin review UI: redesigned for 3 graphic novel candidates)

### Changed — Teacher Portal Widened + Candidate-Aware Generation Views
- The admin generation views still rendered as if a pack had one graphic novel. With 3 candidates × 3 progress surfaces (review, planning substeps, image generation), each surface either repeated the same list 3× with no candidate label or stacked everything into a long vertical scroll. This redesign makes all three candidate-aware and uses the extra width.
- **Wider portal** (`frontend/src/styles/teacher.css`): `.t-shell` `max-width` 1400px → 1760px — more horizontal room for every teacher page, which the candidate views below depend on.
- **Candidate review** (`GenerationReview.jsx`): replaced the vertical stack of full `CandidateCard`s with a **compare strip + detail** layout. New `PackGraphicNovels` renders one compact `CandidateStripRow` per candidate (label, title, lexile/page count, a horizontal band of page thumbnails, Select button — selected outlined green, focused highlighted) above a full-width `CandidateDetail` panel showing the focused candidate's large page grid (280px min columns) with per-page edit/redraw + audio controls and its cloze. Clicking a row focuses it; focus defaults to the selected candidate (else first). All existing wiring (select, edit, redraw, novel- and page-level audio, cloze, "no candidate selected" warning) preserved.
- **Planning Substeps accordion** (`GenerationJobStatus.jsx`): each pack runs the 6 substeps once per candidate, but the accordion grouped only by pack — so the list repeated 3× with no way to tell which candidate an API call belonged to. Now grouped **by pack → by candidate**: new `renderCandidateSubsteps` nests each candidate's substeps under its own collapsible "Candidate N" header (completed candidates auto-collapse, failed ones get a red border + stay open). The per-substep restart (↻) now passes `candidate_index` to `restart-substep/` (endpoint already accepted it), and the in-flight key is `pack_candidate_substep` so restarting one candidate doesn't grey out the same row in the others.
- **Image-generation progress** (`GenerationJobStatus.jsx`): replaced the flat per-page list (pack × 3 candidates × 6-7 pages = 40+ stacked rows) with `GraphicNovelImageProgress` — pages grouped by pack → candidate, each candidate a single row with a `done/total` count and one small status chip per page (hover for page number/status/attempts/error). Status panel widened `maxWidth` 680 → 1000.
- **Backend** (`generation_views.py`): `_graphic_novel_image_page_statuses` now includes `candidate_index` per page; `_graphic_novel_script_substep_statuses` regroups logs by `(pack_id, candidate_index)` and returns a `candidates` array per pack (each with its own substep map), extracting `_new_substep_map()`. **Payload shape change** — the per-pack substep payload is now `{pack_id, pack_label, candidates: [{candidate_index, substeps: [...]}]}` instead of `{..., substeps: [...]}`; the new frontend reads `pack.candidates`, so backend + frontend must deploy together.
- Tests: `test_views.py::test_job_status_includes_graphic_novel_script_substeps` updated to the nested shape and asserts two candidates group separately. `TestGenerationViews` (32) passes.

## [Unreleased] - 2026-06-10 (tests: fix process-global cache leak between tests)

### Fixed — Test Isolation: Shared `LocMemCache` Leaked Config Across Tests
- Running the full `pytest` suite showed ~40 failures that all vanished when the affected files were run alone — the classic "passes alone, fails in suite" signature of a cross-test state leak (not flakiness, not a DB deadlock). Traced to the **first** real failure: `test_orchestrator.py::test_retries_default_model_then_uses_backup_model` expected the migration-seeded `DEFAULT_MODEL` but received `model-3-primary`.
- **Root cause**: the project has no `CACHES` setting, so Django falls back to the in-process `LocMemCache`. That cache is process-global and is **not** rolled back between tests the way the DB is (pytest-django only wraps DB transactions). `test_llm_config_sets.py` seeds `model-3-primary`/`model-3-fallback` into `llm_config_service`'s cache (key `llm_step_configs_all`, 5-min TTL); the stale entry then poisoned every later test that called `get_step_config`, cascading into dozens of downstream failures.
- **Fix** (`backend/tests/conftest.py`, new file): a project-wide autouse fixture that calls `cache.clear()` before and after every test, isolating the whole class of cache-leak bugs rather than just this one symptom. No production code changed.
- Verified: the two interacting files pass together (23), and the full suite is **482 passed** (was failing mid-run). The suggested "serialize threaded tests / add deadlock retry" was unnecessary — there was no deadlock.

## [Unreleased] - 2026-06-10 (graphic novel: 3 candidate novels per pack + admin selection)

### Added — Multi-Candidate Graphic Novels with Manual Publish Gate
- LLM generation variance meant a pack's single graphic novel could land anywhere on the quality curve (story idea, script, art) with no recourse short of a full regen. Now **each pack generates `GRAPHIC_NOVEL_CANDIDATE_COUNT = 3` independent candidate novels** — each from its own full team-selection→router→scorer→cloze→beat→script workflow, so they diverge in story, framing, and art — and an admin picks the best one to publish. Cost/time was explicitly accepted as a non-concern.
- **Schema** (migration `0035_graphic_novel_candidates`): `GraphicNovel` gained `candidate_index` (0-2) + `is_selected`, with `unique_together` changed `('pack','channel')` → `('pack','candidate_index')`. `channel` is now a dead column (always `'5page'`, kept pending removal — the name never meant page length). `ClozeItem` gained a nullable `novel` FK: `novel=None` = promoted/active (student-facing), `novel=<id>` = staged candidate cloze. Existing novels backfilled to `candidate_index=0, is_selected=True`; existing cloze stays `novel=None`.
- **No auto-select / publish gate**: until an admin selects a candidate, none is `is_selected`, so the pack's graphic novel + cloze are invisible to students (`instructional_service` reads `is_selected=True` and `cloze_items.filter(novel__isnull=True)`). The pack reads as not-yet-published — deliberate, so a human curates before students see it.
- **Selection API**: `POST /api/graphic-novels/<novel_id>/select/` (`SelectGraphicNovelCandidateView` → new `services/graphic_novel_selection_service.select_graphic_novel_candidate`). Sets `is_selected`, clears siblings, and **promotes** the chosen candidate's staged cloze to the pack's active set (deletes prior promoted rows, re-creates from the selected novel's). Idempotent + reversible. Losing candidates are kept (hidden). Audiobook stays manual — admin only triggers `generate-audio` on the selected novel.
- **Generation engine refactor** (`graphic_novel_script.py`): `restart_graphic_novel_from_substep(..., candidate_index)` is now the single per-candidate generation engine — both fresh runs and resume delegate to it, removing ~200 lines of duplicated workflow. `_step_graphic_novel_script` is pure orchestration (loops packs × candidates, skips complete candidates, resumes incomplete ones). Resume keys, COMPLETED logs, and on-disk artifacts are all keyed per-`(pack, candidate_index)`; artifacts live under `temp/generation_artifacts/job_<id>/pack_<id>_<slug>/cand_<i>/`. `restart-substep` API gained an optional `candidate_index` (default 0).
- **Images**: the GRAPHIC_NOVEL_IMAGES step now renders pages for **all** candidate novels (so the admin compares fully-rendered candidates), resetting cross-page continuity at each novel boundary.
- **Admin review** (`GenerationJobContentView`, `WordSetContentView`): return `graphic_novels` (array of all candidates, each with its own staged cloze) plus `graphic_novel` (the selected one, or null). **Frontend** (`GenerationReview.jsx`): each candidate renders as a `CandidateCard` with a "Select this candidate" button + selected badge; per-page image edit/redraw and audio controls operate within each candidate. `GenerationWizard.jsx` updated to the `graphic_novels` array shape.
- Tests: new `tests/vocabulary/test_graphic_novel_selection.py` (selection flips flags + promotes/replaces cloze, idempotent) and `TestGraphicNovelCandidates` in `test_step_graphic_novel_script.py` (3 unselected candidates, isolated artifacts, complete-candidate skip on rerun). Existing per-candidate workflow tests forced to single-candidate via an autouse fixture. All test files touched pass together (208).

## [Unreleased] - 2026-06-09 (audiobook: per-page regeneration in admin review)

### Added — Per-Page Read-Along Audio Regeneration (Admin Review)
- A graphic novel page can lose its audio when a single TTS API call fails mid-run — the novel finishes with a gap. The Generation Review page previously offered **only** a novel-level "Regen audio" button which, once any page had audio, forced `regenerate=true` and re-synthesized **every** page. There was no way to fill in just the one missing/failed page.
- The backend per-page endpoint `POST /api/graphic-novel-pages/<page_id>/regenerate-audio/` (async daemon thread, **202**/**409**, reuses the novel's cached voice direction so no extra LLM call) already existed — this change wires it into the admin UI.
- **Frontend** (`GraphicNovelPageEditor.jsx`): new `AudioRow` sub-component under each page card — the `<audio>` player (when present) plus a per-page button labelled "🔊 Generate audio" / "↺ Regen audio" / "⏳ Generating…" based on that page's audio status, with an inline "Audio failed" indicator (the error text shows in the tooltip). New props `audioStatus` / `audioError` / `onRegenAudio`.
- **Frontend** (`GenerationReview.jsx`): new `regeneratePageAudio(novelId, pageId, pageNumber)` callback — optimistically marks just that page `RUNNING`, POSTs the per-page endpoint, then reuses the existing novel-level `audio-status/` poll (its payload is already keyed per page). The content seed now carries `page_id` so the page entry can be matched on the optimistic update.
- The novel-level "Regen audio" button is unchanged and still available for a full re-synthesis.
- Tests: `tests/vocabulary/test_audiobook.py` adds `TestRegeneratePageAudioView` (4 cases: 202 success, 404 missing page, 409 when already running, and a worker test proving it regenerates one page without touching its siblings). **47 audiobook tests pass.**

## [Unreleased] - 2026-06-09 (primer: syllable breaks preserve spelling)

### Fixed — Primer Syllable Breakdowns No Longer Misspell Words
- Primer cards sometimes showed phonetically respelled syllable text (e.g. `sim·i·lee` for "simile", `ev·ry` for "every") instead of the word's real spelling. Root cause: `prompts/primer_generation.txt` explicitly instructed the LLM to use **phonetic (sound-based) syllable breaks rather than orthographic (spelling-based)** ones, with `ev·ry` given as a model answer — the prompt was asking for misspellings.
- **Prompt fix**: replaced the phonetic-preference guideline with a hard spelling-preservation rule — keep the word's exact spelling, only insert middle dots (·) between syllables, never add/drop/change letters; removing the dots must reproduce the word letter-for-letter (`sim·i·le` not `sim·i·lee`; `ev·er·y` not `ev·ry`).
- **Code safety net** (`services/generation/step_packs.py`): new pure helper `_sanitize_syllable_text(term, syllable_text)` runs on every primer save in `_step_generate_primers`. It strips separators (·, ., -) and compares the result to the actual word (case-insensitive, whitespace-insensitive); on mismatch it logs a warning and falls back to the correctly-spelled plain term, so a phonetic respelling can never reach students even if a future model ignores the prompt.
- Scope: affects only **newly generated** primer cards. Existing `PrimerCardContent.syllable_text` rows in the DB are unchanged (no backfill command added).
- Tests: `tests/vocabulary/test_step_packs.py` adds 2 integration cases (misspelled breakdown falls back, correct breakdown preserved) + a 7-case `TestSanitizeSyllableText` pure-unit class. **19 pack/primer tests pass.**

## [Unreleased] - 2026-06-09 (graphic novel: beat validator tolerates character-name variants)

### Fixed — Beat Complexity Validator No Longer Rejects Re-Labeled Secondary Characters
- A GRAPHIC_NOVEL_SCRIPT job failed with `Graphic novel beat planner introduces characters not in the away team or complexity_budget.secondary_characters: ['Mr. Vidal']. Allowed: ['Amara', 'groundskeeper Mr. Vidal'].` The beat sheet named a character `Mr. Vidal` while the winning premise listed the same person as `groundskeeper Mr. Vidal`. `_validate_beat_complexity` (`services/generation/graphic_novel_validators.py`) compared `characters_featured` against the allowed set with **exact string set-difference**, so a role-prefix difference for one character read as an unplanned new character and aborted the step.
- **Fix**: replaced exact matching with distinctive-name-token overlap. New helpers `_significant_name_tokens()` (lowercases, strips punctuation, drops role/title stopwords like `mr`, `groundskeeper`, `the`, `professor`, …) and `_name_matches_allowed()` (a featured name passes if its significant tokens overlap any allowed label's). `Mr. Vidal` → `{vidal}` now matches `groundskeeper Mr. Vidal` → `{vidal}`, while a genuinely new character (`Mr. Stranger` → `{stranger}`) is still rejected. This is the same LLM-surface-variation tolerance already used for cloze blanks and lexile lookups.
- Failed jobs can be recovered without code changes via `POST /api/generation-jobs/{id}/restart-substep/` (`pack_id` + the failed substep).
- Tests: existing beat/validator suites pass (51 graphic-novel/validator tests, 2 beat-complexity tests).

## [Unreleased] - 2026-06-08 (audiobook: student playback + MP3 companion)

### Added — Student Read-Along Playback Controls
- **Frontend** (`frontend/src/components/GraphicNovelReader.jsx`): students can now play the read-along audio while reading a graphic novel. Each page shows a **Listen / Pause** button (only when that page has audio) and an **Auto-read** toggle switch grouped beside it. With auto-read on, a page's audio starts automatically when the student lands on it — the first page and every manual page turn — while still requiring manual page turns (per-page only, no cross-page auto-advance). Audio always stops/resets when the page changes.
- The Auto-read preference is persisted in `localStorage` (`gnReaderAutoplay`, default **on**) so it carries across pages, packs, and sessions. Toggling the switch mid-page never interrupts audio already playing — it only affects the next page turn (implemented via an `autoplayRef` so the page-change effect reads the latest value without re-firing). The switch renders whenever the novel has any audio; the button only when the current page does. Styles in `frontend/src/styles/graphic-novel-reader.css`.
- Browser autoplay policy caveat: the very first auto-play when the reader opens may be blocked until a user gesture; a blocked `play()` degrades to the idle "Listen" state, and every subsequent page turn counts as a gesture so those auto-play reliably.

### Added — Compressed MP3 Companion (Students Stream MP3, WAV Stays Source of Truth)
- The stitched WAV is now converted to a compressed **MP3** (~64 kbps mono, roughly 6× smaller) right after the WAV is saved, mirroring the PNG→JPEG image-companion pattern. The WAV remains the source of truth for admin/review and regeneration; students stream the MP3.
- **Model** (`models.py`): new `GraphicNovelPageAudio.audio_mp3` FileField (`upload_to='graphic_novel_audio_mp3/'`) + a `student_audio` property returning `audio_mp3 or audio`. Migration `0034_graphicnovelpageaudio_audio_mp3_and_more`.
- **Encoder** (`services/audiobook/encode.py`): `wav_bytes_to_mp3_bytes()` uses **`lameenc`** — a pure binary-wheel LAME encoder — **not** ffmpeg/pydub, consistent with the "no ffmpeg/pydub on the box" constraint that already governs the WAV stitcher. Reads rate/width/channels from the WAV header; requires 16-bit PCM. Pinned `lameenc==1.8.2` in `requirements.txt`.
- **Generator** (`services/audiobook/generator.py`): `_save_mp3_companion()` runs after the WAV save **best-effort** — a conversion failure is logged and swallowed, never aborting the WAV (student path falls back to WAV via `student_audio`). `audio_mp3` added to the row's `save(update_fields=...)`.
- **Student serving** (`instructional_service.py`): the per-page `audio_url` in the student payload now resolves via `audio.student_audio.url` (MP3 preferred). Admin review endpoints unchanged (still serve WAV).
- **Backfill**: `python manage.py backfill_audio_mp3 [--dry-run]` converts existing COMPLETED WAV rows (idempotent; safely skips non-16-bit-PCM-WAV files). Must be run on **production** after deploy + migrate to give existing audio its MP3 companion (until then those pages fall back to WAV).

### Test
- `tests/vocabulary/test_audiobook.py`: new `TestWavToMp3` (encode + shrink, empty/non-WAV input raises); `test_all_pages_completed` now asserts the MP3 companion is produced and `student_audio` resolves to it. **43 audiobook / 70 audio+instructional tests pass.**

## [Unreleased] - 2026-06-07 (audiobook: voice reassignment + slow-pace tag fix)

### Changed — Finalized Hero Voices + Gender-Contrasting Narrator
- Reassigned the prebuilt Gemini TTS voices in `services/audiobook/constants.py` `HERO_VOICES`: **Hugo → Achird**, **Amara → Despina**, **Mei → Zephyr** (Leo stays **Puck**). Supersedes the first-draft picks (Amara=Kore, Mei=Fenrir, Hugo=Aoede).
- Replaced the age-band narrator (Sulafat 9yo / Charon 12yo) with a **gender-contrast rule** so the narrator never sounds like a hero: any female hero on the team → male narrator **Charon**; an all-male team → female narrator **Aoede**; unknown/empty team → Aoede default. Implemented as `voices.narrator_voice_for(novel)`, reading `novel.metadata['away_team']` against a new `HERO_GENDERS` map (Leo/Hugo male, Amara/Mei female, confirmed from the canon cast sheets). New constants `NARRATOR_VOICE_MALE`/`NARRATOR_VOICE_FEMALE`/`NARRATOR_VOICE_DEFAULT`; `NARRATOR_VOICE_BY_AGE` removed.
- Voices only change on (re)generation — existing WAVs and `voice_manifest` rows keep their old voices until the page is regenerated.

### Fixed — Voice Director No Longer Slows Lines Down
- The voice director LLM was tagging some lines with `[slowly]` (e.g. Amara on "The Flowers That Wake at Night" page 4), which Gemini TTS honors literally and which compounds the already-gentle kid-friendly pacing, making delivery drag.
- **Prompt** (`prompts/audiobook_voice_director.txt`): removed slow-pace tags from the allowed set and added an explicit PACING rule forbidding them (weight should come from emotion tags or the player's between-line pauses, never a slow tag).
- **Defensive sanitizer** (`voice_director.py`): `_index_directed_events` now runs every directed line through `_strip_slow_tags()`, which removes slow-pace cues (`slowly`, `very slowly`, `one word at a time`, `drawn-out`, `word by word`, …) from inline `[...]` tags — surgically (e.g. `[nervously, very slowly]` → `[nervously]`) and dropping a tag entirely if it becomes empty. Runs on the **read path**, so already-cached director output (this novel and any other) is cleaned without re-running the LLM; emotion tags like `[amazed]` pass through untouched.
- Tests: `tests/vocabulary/test_audiobook.py` updated for the new narrator rule (female/male/mixed/unknown team cases) — **32 passed**.

## [Unreleased] - 2026-06-07 (audiobook: fix missing play button on review page)

### Fixed — Admin Review Content Endpoints Now Expose `audio_url`
- After generating read-along audio, the `<audio>` player did not appear on the Generation Review page (`/teacher/generation-jobs/<id>`) until audio was re-triggered, even though the WAVs existed on disk. Root cause: `GenerationJobContentView` and `WordSetContentView` serialized every graphic-novel page field **except** the audio. The frontend player only renders when `audioUrl` is truthy, and on initial load that value comes from `page.audio_url` in the content payload — which was never sent. (The student `instructional_service` payload already carried `audio_url`; only the two **admin review** content endpoints were missing it.)
- **Backend** (`views/generation_views.py`): added a shared `_graphic_novel_page_review_payload()` helper that includes `audio_url` (the page's `audio` reverse-OneToOne URL when it exists and is `COMPLETED`, else `''`); both content endpoints now use it. Added `graphic_novels__pages__audio` to each endpoint's `prefetch_related` to avoid an N+1 on the audio relation.
- **Frontend** (`pages/admin/GenerationReview.jsx`): seed `audioState` from the loaded content (`seedAudioFromContent`) so existing per-page players render on first paint and the novel-level button reads "↺ Regen audio" instead of "🔊 Generate audio" without waiting for a poll.

## [Unreleased] - 2026-06-07 (audiobook: voice director LLM step)

### Added — Per-Novel Voice Director (LLM-Directed TTS Performance)
- Before synthesis, `services/audiobook/voice_director.py` makes **one LLM call per novel** (step key `audiobook_director`, configurable in the LLM Config Matrix). The LLM reads every page's speech events and returns (1) a short Audio Profile + Director's Notes block per speaker and (2) the full transcript with inline Gemini TTS audio tags (`[excitedly]`, `[whispers]`, etc.). Each TTS call then wraps the spoken line in the speaker's profile for richer, differentiated per-character performance.
- **Caching**: result stored in `novel.metadata['voice_director']` — per-page regeneration reuses the cached output without a new LLM call. Graceful degradation: any director failure falls back to the bare transcript text.
- **Migration `0033_audiobook_director_step_key`**: adds `audiobook_director` to `LLMStepConfig.StepKey` and seeds one row per config set (cloned from `gn_final_script`). Total step keys: 12.
- Prompt: `vocabulary/prompts/audiobook_voice_director.txt` (Audio Profile + Director's Notes format per the Gemini TTS prompting guide).
- `generator.generate_novel_audio` runs the director once before the synthesis loop; `_run_page_audio` in views loads the cached direction before single-page regen. `generate_page_audio` accepts `direction=` and uses per-speaker profiles as the TTS style prefix.

## [Unreleased] - 2026-06-07 (audiobook: dedicated TTS endpoint config + verified working)

### Fixed — TTS Routing Uses Dedicated `GEMINI_TTS_*` Settings
- The initial audiobook commit (below) read `settings.GEMINI_API_KEY`, which is **empty** in this deployment — the real Gemini key lives in the LLM Config Matrix (`GEMINI_API_KEY_Vector`), and audio modality needs the **native** generateContent API that an OpenAI-compatible text proxy does not serve. First live run failed with "GEMINI_API_KEY is not configured".
- Added dedicated, independently-configurable settings (`config/settings.py`, `.env.example`): `GEMINI_TTS_API_KEY` (falls back to `GEMINI_API_KEY`), `GEMINI_TTS_BASE_URL` (passed into the native `genai.Client` via `HttpOptions(base_url=...)`; empty = call Google directly), `GEMINI_TTS_MODEL` (default `gemini-2.5-pro-preview-tts`). `tts_client._client()` builds the client from these.
- **Verified working end-to-end**: novel 50 generated 6/6 pages through the Vector TTS proxy; output confirmed PCM 24kHz/16-bit/mono. The phase-1 "manual smoke test still pending" caveat below is now resolved.

## [Unreleased] - 2026-06-07 (graphic novel: read-along audiobook pipeline, phase 1)

### Added — On-Demand Per-Page Read-Along Audio (Gemini TTS)
- Goal: generate a read-along audio track for a completed graphic novel — **one stitched audio file per page** — on demand, using `gemini-2.5-pro-preview-tts`. Phase 1 delivers backend generation + storage + admin trigger/poll + serving the URL to students. The production rules live in `docs/feature_plan/lexi-legends-audiobook-production-bible.md`; the design in `docs/feature_plan/audiobook-pipeline-implementation-plan.md`.
- **Decisions**: separate **on-demand** job (not a 9th pipeline step); **per-event single-voice** TTS calls (one narration box or one dialogue line each), stitched with pauses; no per-event timing metadata yet.
- **Model** (`models.py`): new `GraphicNovelPageAudio` (OneToOne → `GraphicNovelPage`): `audio` (WAV FileField), `duration_ms`, `voice_manifest` (per-event voice assignments for debug/regen), `status` PENDING/RUNNING/COMPLETED/FAILED, `attempts`, `error`, timestamps. Migration `0032_graphicnovelpageaudio`. Kept separate from the page so audio is fully optional/regenerable and never touches image rows.
- **Service package** `services/audiobook/`: `constants.py` (voice map, age style prefixes, pause timings, PCM format), `events.py` (`build_page_events` — pure, walks `panel_descriptions` into ordered speech events with pauses), `voices.py` (`voice_for` — stable hero map + deterministic supporting-pool fallback by name hash; narrator varies by `age_band`), `tts_client.py` (isolated native `genai.Client` TTS call — the project's GEMINI_BASE_URL proxy can't do audio; parses sample rate from the response mime type; retries once), `stitch.py` (stdlib `wave` only — concat PCM + insert silence → one WAV; **no ffmpeg/pydub on the box**), `generator.py` (`generate_page_audio` / `generate_novel_audio` — continue-on-failure per page like the image step; skips the review page and already-COMPLETED pages unless `regenerate`).
- **Source of truth**: spoken text is read verbatim from `GraphicNovelPage.panel_descriptions` (`narration` + `dialogue[].speaker/.text`), confirmed to match the rendered images — no OCR.
- **Views/URLs** (`generation_views.py`, `urls.py`, admin-only, mirror the async edit-image pattern): `POST /api/graphic-novels/<novel_id>/generate-audio/` (`{regenerate}`) → **202** + daemon thread (409 if already RUNNING); `GET /api/graphic-novels/<novel_id>/audio-status/` poll target (per-page status + URLs); `POST /api/graphic-novel-pages/<page_id>/regenerate-audio/` for a single page.
- **Student serving** (`instructional_service.py`): each graphic-novel page in the student payload now carries `audio_url` (the COMPLETED audio's URL, else `''`); added `graphic_novels__pages__audio` to the prefetch.
- **Admin UI** (`pages/admin/GenerationReview.jsx`, `components/generation/GraphicNovelPageEditor.jsx`): a "Generate audio" / "Regen audio" button per novel with a 5s status poller, and an `<audio controls>` player on each page card when audio exists.

### Test
- `tests/vocabulary/test_audiobook.py` (new, **30 passed**): `build_page_events` ordering + pause assignment + age-band defaults; `voice_for` determinism + hero/supporting resolution; `stitch_pcm`/`silence_pcm` length math via `wave` round-trip; generator with a mocked TTS client (all-completed, skip-completed, regenerate, per-page failure isolation); view status codes (202 / 404 / 409 / status poll). Real-key TTS smoke test is manual (documented, not in CI) — the one assumption not verifiable offline (PCM 24kHz/16-bit/mono + voice quality).

## [Unreleased] - 2026-06-06 (LLM config: 3 selectable configuration sets)

### Added — Three LLM Config Sets With One Active
- Request: have **3 sets of step configurations**, be able to edit each set independently, and choose which set is active — the pipeline processes generation jobs using the active set's configs.
- **Model** (`models.py`): new `LLMConfigSet` (`name`, `position` 1-based unique, `is_active`). `LLMStepConfig` gained a `config_set` FK (CASCADE) and its uniqueness moved from `step_key` alone to `unique_together = (config_set, step_key)` — each set holds its own full copy of all 11 step configs.
- **Migration** `0031_llm_config_sets`: creates `LLMConfigSet`, seeds "Set 1/2/3" (Set 1 active), adds the FK as nullable, attaches pre-existing step configs to Set 1, **clones** them into Sets 2 & 3 (so all three are immediately usable), then makes the FK non-null and swaps in the new unique constraint. Reversible (collapses back to the active/first set's rows).
- **Single-active** is enforced in application logic (MySQL has no partial unique index): activating one set deactivates the others in the same request, and the API refuses to deactivate the active set.
- **Service** (`llm_config_service.py`): `get_step_config(step_key)` keeps its signature and now resolves rows from the active set (via new `get_active_set()`), so the orchestrator and all graphic-novel substep callers needed **zero** changes. Switching the active set takes effect on the next job/step (5-min cache, invalidated on any edit/activation).
- **API** (`llm_config_views.py`, `urls.py`): `GET /api/admin/llm-config-sets/` lists sets; `PUT /api/admin/llm-config-sets/<id>/` renames (`name`) and/or activates (`is_active: true`). Step-config GET/PUT are now set-scoped via `?set=<id>` (default = active set) and return `{set, configs}` instead of a bare list. Sites stay shared across sets. No create/delete (fixed at 3).
- **Frontend** (`pages/admin/LLMConfig.jsx`): the Step Configuration tab gained a set selector, an inline rename, and a "Make this set active" button; "Save All" writes to the currently selected set. The API Sites tab is unchanged.

### Test
- `tests/vocabulary/test_llm_config_sets.py` (new, **11 passed**): set listing + admin-only guard, activate-deactivates-others, refuse-deactivate-active, rename, set-scoped GET (default active + explicit `?set=`), set-scoped PUT isolation (editing one set leaves others untouched), invalid-site rejection, and the service reading/following the active set. Fixture clears seeded LLM rows first (the data migration seeds 3 sets into the test DB). Full backend suite: **408 passed** pre-existing + 11 new.

## [Unreleased] - 2026-06-06 (graphic novel: admin can redraw a page image)

### Added — "Redraw" Button Replays the Original Generation Payload
- Request: a button next to "Edit image" that re-runs a page's image with **exactly the same payload as the first generation attempt** — sometimes a second roll of the identical prompt clears artifacts in a bad image.
- **Redraw ≠ edit.** Edit feeds *this* page's own image plus an admin instruction into `images.edit`. Redraw rebuilds the page's *original generation* payload: the template-built prompt + the previous page as the continuity reference (`None` for page 1).
- **Refactor** (`services/generation/graphic_novel_images.py`): extracted `build_page_image_prompt(page)` (the review/normal-page prompt construction, formerly inline in `_step_graphic_novel_images`) and added `previous_page_reference_bytes(page)` (mirrors the pipeline's per-novel continuity reference). The image step now calls `build_page_image_prompt`, so the pipeline and redraw build the identical prompt — no behavior change to generation.
- **View** (`generation_views.RedrawGraphicNovelPageImageView`, `POST /api/graphic-novel-pages/<page_id>/redraw-image/`, admin-only, no body): validates (404 missing / 409 already RUNNING / 400 no image yet), builds the prompt + reads the previous-page reference **synchronously** (fail fast), sets the page `RUNNING`, hands the slow call to a daemon `threading.Thread`, returns **202**.
- **Worker** (`generation_views._run_page_image_redraw(page_id, prompt, reference_bytes)`): same shape as `_run_page_image_edit` — saves `edited_image` (+ best-effort JPEG companion), `use_edited_image=True`, appends `[REDRAW]` to `prompt_used`, status `COMPLETED`; on failure status `FAILED` + `generation_error`. Original `image` never overwritten; reversible via `select-image/`.
- **Poll**: reuses the existing `GET .../image-status/` endpoint (no new poll route).
- **Frontend** (`GraphicNovelPageEditor.jsx`): a "Redraw" button beside "Edit image"; the edit flow's poll loop was extracted into a shared `pollUntilDone()` helper used by both edit and redraw.

### Test
- `test_views.py`: added redraw coverage alongside the edit tests — 202 + `RUNNING` + worker args (asserts `None` reference for page 1), worker COMPLETED save into `edited_image` (original preserved, `[REDRAW]` tag), worker FAILED path, 409-when-running, 404-missing-page, 400-no-image, 403-for-student. Full `TestGenerationViews` class: **32 passed**.

## [Unreleased] - 2026-06-06 (graphic novel: page image editing is now asynchronous)

### Changed — Edit-Image No Longer Holds a Worker for the Image Call
- Request: stop the `edit-image/` endpoint from occupying a gunicorn worker for the ~30-60s OpenAI `images.edit` wait (only 3 workers in production, so two concurrent edits + traffic could starve the pool). Mirrors the existing async pattern used by `run-pipeline` / `resume` / `restart-substep`.
- **View** (`generation_views.py`): `EditGraphicNovelPageImageView.post` now validates the prompt, looks up the page, reads the reference image bytes synchronously (so an unreadable file still fails fast with 404), sets the page `generation_status=RUNNING` (+ `generation_started_at`, bumps `generation_attempts`, clears the error), and hands the slow image call to a daemon `threading.Thread`. Returns **202** with the `RUNNING` payload. Returns **409** if an edit is already `RUNNING` for the page.
- **Worker** (`generation_views._run_page_image_edit(page_id, edit_prompt, reference_bytes)`): module-level function holding the moved OpenAI call + file-save logic. Wrapped in `_close_old_connections_if_safe()` so it doesn't pin a MySQL connection during the wait. On success: saves `edited_image` (+ best-effort JPEG companion), `use_edited_image=True`, appends `[ADMIN EDIT]` to `prompt_used`, status `COMPLETED`. On failure: status `FAILED` + `generation_error` (no more 502 — the admin sees the error via polling).
- **Poll endpoint** `GET /api/graphic-novel-pages/<page_id>/image-status/` (`GraphicNovelPageImageStatusView`, admin-only): returns the standard page image payload for the frontend to poll.
- **Frontend** (`GraphicNovelPageEditor.jsx`): after the POST returns, polls `image-status/` every **10s** (`EDIT_POLL_INTERVAL`) until `generation_status` leaves `RUNNING`; on `COMPLETED` merges the result with cache-busted URLs and switches preview to edited, on `FAILED` surfaces `generation_error`. The card stays in a busy state with a "you can leave this page; the edit keeps running" hint, and the interval is cleared on unmount. `select-image/` is unchanged (synchronous instant DB flip).

### Test
- `test_views.py`: reworked the edit-image tests — happy path now patches `threading.Thread` and asserts 202 + `RUNNING` + worker args; new tests drive `_run_page_image_edit` directly for the COMPLETED save and the FAILED path; added 409-when-already-running and `image-status/` (200 + 403-for-student) tests. The select-back-to-original test now seeds the edited variant via the worker.

## [Unreleased] - 2026-06-05 (graphic novel: page count is deterministic from pack word count)

### Changed — Page Count No Longer an LLM Judgment; Derived From Word Count
- Request: make graphic novel length a fixed function of pack size — **≤4 words → 5 pages, >4 words → 6 pages** — instead of letting the router LLM choose per premise. Supersedes the 2026-06-04 length-bias rebalance below (the LLM no longer picks length, so the scorer-bias problem that prompted it no longer exists).
- **Constants** (`services/generation/constants.py`): added `GRAPHIC_NOVEL_WORD_COUNT_PAGE_THRESHOLD = 4` and `page_count_for_word_count(word_count)` (returns 6 if `word_count > threshold`, else 5), mirroring the existing `max_locations_for_page_count` pattern.
- **Script step** (`services/generation/graphic_novel_script.py`): both `_step_graphic_novel_script` and `restart_graphic_novel_from_substep` compute `required_page_count = page_count_for_word_count(len(pack_words_data))`, thread it into `base_input` + `input_summary` (so the router/scorer/cloze/beat/final prompts see it), and then **force** `winning_premise['page_count'] = required_page_count` regardless of what the model returned (the LLM's declared value is logged and overridden, never trusted). All downstream logic — template dispatch, `expected_page_count`, location ceilings — already keys off this single value, so forcing it is sufficient.
- **Router prompt** (`graphic_novel_router.txt`): the page-count section now states the length is fixed (`required_page_count`, given in the input, derived from word count); every premise must use it and size its plot to fit. Location budget made page-count-aware (≤2 for 5-page, ≤3 for 6-page).
- **Scorer prompt** (`graphic_novel_premise_scorer.txt`): replaced the "page length is neutral / prefer the shorter premise" comparison block (all premises now share one fixed length) with guidance to judge how well each uses that shared length; penalizes a premise that declares a `page_count` differing from `required_page_count`.
- **Design choice**: the Python override is the deterministic safety net — no new validator rejection path — so LLM disobedience cannot break the rule. Consistent with "reserve hard limits for measurable constraints, enforce in code" ([feedback_prompt-flexibility]).

### Test
- `test_step_graphic_novel_script.py`: new `TestPageCountForWordCount` (boundaries 4→5, 5→6); reworked the 6-page dispatch test to drive it with a **5-word pack** (the only way to force 6 pages now), using new multiword fixtures; the 5-page dispatch test (2-word pack) renamed to reflect word-count-driven selection.
- `generation_fixtures.py`: added `MULTIWORD_TERMS` / `MULTIWORD_LOOKUP_RESPONSE` and `build_multiword_cloze_response` / `build_multiword_six_page_beat_response` / `build_multiword_six_page_script_response` (cover all 5 terms in cloze, vocab_roles, page text, and vocab_anchors so the 6-page validators pass).
- Full vocabulary suite **380 passed**.

## [Unreleased] - 2026-06-05 (graphic novel: per-pack substep resume + no orphaned packs on restart)

### Fixed — Resuming a Mid-Pack Script Failure Restarted From Team Selection
- Symptom: when a graphic novel substep failed (e.g. premise scoring) and the admin clicked Resume, the pipeline re-ran that pack's GRAPHIC_NOVEL_SCRIPT step from the first substep (Team Selection), wasting LLM calls and producing a different story than the partially-completed run.
- **Root cause**: the per-pack `GraphicNovel` record is created only after all 6 substeps succeed, so `last_completed_step` never advances to GRAPHIC_NOVEL_SCRIPT and the per-pack loop had no substep-level memory — it always started at substep 0.
- **Fix** (`services/generation/graphic_novel_script.py`): `_step_graphic_novel_script` now computes `_resume_substep_index_for_pack(job, pack)` — the first substep without a COMPLETED log for that pack — and, when prior substep artifacts exist on disk, delegates to the existing `restart_graphic_novel_from_substep(...)` to resume from there. A fresh pack (nothing completed) still runs the full 6-call workflow from Team Selection. The COMPLETED log (not artifact presence) is authoritative, because `_run_graphic_novel_substep` writes the artifact *before* validation — a validation failure can leave a stale artifact without a COMPLETED log. No DB field, model, or migration change.

### Fixed — Per-Pack Substep Restart Orphaned Later Packs (job #48)
- Symptom (job #48, "To Drill or Not to Drill?"): the word set had two packs; only one graphic novel was created and the job was marked COMPLETED. Pack 53 ("Gas Crisis, Endless Sprawl") had no novel at all.
- **Root cause**: pack 52's beat-sheet substep failed, so the GRAPHIC_NOVEL_SCRIPT step raised before pack 53 ever started. The admin then used the per-substep restart (↻) on pack 52, and `restart_graphic_novel_substep` (`services/generation/orchestrator.py`) regenerated **only pack 52** and then unconditionally marked the **whole job** COMPLETED. A subsequent "Restart Step → Graphic Novel Images" only saw pack 52's novel and also completed. Pack 53 was silently dropped.
- **Fix** (`services/generation/orchestrator.py`): after the targeted single-pack restart, `restart_graphic_novel_substep` now runs `_step_graphic_novel_script(job, remaining_packs, words_data)` over **all** packs in the word set before marking COMPLETED. The script step's skip-guard leaves packs that already have a novel with pages untouched, so complete packs cost no extra LLM calls; only genuine gaps (like pack 53) are filled. If a remaining pack fails, the step raises and the job is correctly marked FAILED. The image step was already correct (queries `novel__pack__in=packs` and fails on any incomplete page), so the gap was purely script-side.
- **Note**: the code fix stands; job #48's stale data was intentionally left as-is (re-running any pack 52 substep restart, or a script-step restart, will now also generate pack 53's novel — then run images).

### Test
- `test_step_graphic_novel_script.py`: `TestStepGraphicNovelScriptResume` (resume from a failed `premise_scoring` makes exactly 4 follow-on LLM calls reusing team/router from disk and reproduces the saved `away_team`; a fresh pack still runs all 6 substeps).
- `test_orchestrator.py`: `TestRestartGraphicNovelSubstep` (a per-pack restart runs the full script step over both packs so the second is not orphaned; a failing remaining-pack script marks the job FAILED).
- Combined orchestrator + GN-script suites: **42 passed**.

## [Unreleased] - 2026-06-05 (generation: honest retry display + batch-resumable question generation)


### Fixed — Job Status Showed a False "Question Generation Error" While Still Retrying
- Symptom (job 48): the GenerationReview page rendered Question Generation as ✗ FAILED with a red "Error" while the backend pipeline was still running and recovering on the fallback site. The job was genuinely `RUNNING`; the display lied.
- **Root cause**: the orchestrator writes a transient `FAILED` `GenerationJobLog` on every recoverable retry attempt (the per-step attempt plan is `[primary, primary, fallback]`), and `last_completed_step` only advances after a step *fully* succeeds. The frontend (`GenerationJobStatus.jsx`) keyed each step's status on the *latest* log for that step, so a step mid-retry showed its last transient failure as if it were terminal.
- **Backend** (`services/generation/orchestrator.py`): new `_build_retry_payload(plan, failed_idx)` counts attempts *per site role* and writes structured fields (`failed_attempt`, `failed_site_role`, `next_attempt`, `next_site_role`, `failed_model`, `next_model`) plus a ready-made `retry_message` into the retry marker's `output_data` (the logs API exposes `output_data`, not `input_data`). Messages read e.g. "Attempt 1 on primary site (…) failed; retrying — attempt 2 on primary site (…)." and "…attempt 1 on fallback site (…)".
- **Frontend** (`GenerationJobStatus.jsx`): the active step is now derived from the authoritative `job.status` + `last_completed_step` (the step right after the last completed one) instead of the latest per-step log. While the job is RUNNING/PENDING that step renders RUNNING with an amber "Retrying" line showing `retry_message`; a red "Error" only shows for a genuinely terminal FAILED step.

### Added — Question Generation Resumes at Batch Granularity (no wasted calls, no duplicates)
- Request: when a question-generation run fails partway, the batches that already returned valid questions should stay in the DB, and resuming the job should skip those words instead of regenerating them.
- `_step_generate_questions` (`services/generation/step_questions.py`) is now idempotent per batch. Questions already commit per-batch (no transaction wraps the step), so the gap was only that resume/in-step-retry reran *all* batches — wasting LLM calls and creating duplicate questions for already-done words. The step now reads the job's existing `Question.word_id` set up front: a batch whose words are all present is **skipped**; a batch with only some words present (a partial prior attempt) has those stale rows deleted before regenerating. `questions_created` is recomputed as the job's total count, and the COMPLETED log records `batches_skipped`.
- Composes with all entry paths: fresh `run_full_pipeline` (empty set → generate all), `resume_pipeline` and the in-step `[primary, primary, fallback]` retry (skip completed, finish the rest), and `restart_pipeline_from_step` for QUESTION_GEN which still deletes all questions first for an intentional full regen.

### Docs
- Corrected stale facts in `PROJECT_CONTEXT.md` and `CLAUDE.md`: question batch size is **2** words per call (code: `QUESTION_BATCH_SIZE = 2`), not 3; admin status polling interval is **30 s** (`POLL_INTERVAL = 30000`), not 10 s.

### Test
- Added 3 orchestrator tests (`test_orchestrator.py`) for `_build_retry_payload` (per-role attempt counting, role-less image plan, logged retry message) and 3 question-step tests (`test_step_questions.py`: failed batch persists earlier batches, resume skips completed batches with no duplicates, counter/`batches_skipped` reflect totals). Full vocabulary suite **369 passed**.

## [Unreleased] - 2026-06-04 (graphic novel: page-count length bias rebalance)

### Changed — Stop the Scorer From Always Picking 6-Page Premises
- Investigation: on recent real-content runs the pipeline produced a 6-page graphic novel (+ review sheet) every time, never 5. Tracing the on-disk artifacts (router/scorer/beat/script JSON in `temp/generation_artifacts/`) confirmed the mechanism is sound — the winning premise's `page_count` flows correctly through to the beat sheet and final script in every run. The bias was in the **scoring rubric**, not the code: whenever a premise declared 6 pages, the scorer swept it 5/5/5/5/5 across all dimensions (vs 3s–4s for 5-page premises), because the extra page carried a richer plot and the rubric implicitly rewarded "more story" as higher narrative_clarity / visual_potential / pedagogical_clarity. The router also leaned toward writing its strongest idea at 6 pages.
- **Router** (`graphic_novel_router.txt`): added two soft nudges to the page-count section — frames 5 pages as the strong default for ESL readers (less text per page → easier word inference, 6 reserved for premises that genuinely need the room), and asks for a real mix across the 3 premises with at least one conceived as a clean 5-page story (not a trimmed-down 6-page idea) so the scorer has a strong short option to choose.
- **Scorer** (`graphic_novel_premise_scorer.txt`): added a "Page length is neutral, not a quality signal" block — page count is a self-chosen constraint, not a dimension to reward; judge each premise against what it attempts at its own length (a tight 5-page story is not "thin"); a more ambitious plot is only better if it still teaches every target word clearly; and a tiebreaker preferring the shorter premise when two are close.
- Phrasing follows the soft-guidance convention (prefer/default/aim, no hard mandates).
- **Scope**: prompt-text only — no Python, validator, or schema changes. Affects **new** generations only. The real test is the next few runs; expect the mix of 5- and 6-page novels to return.

### Test
- No new tests. The 28 script-step tests mock prompt loading and assert template selection (5- vs 6-page), not prompt content — all 28 pass.

## [Unreleased] - 2026-06-04 (graphic novel: re-establishing caption on location change)

### Changed — Bridge Magical/Instant Scene Changes with an Arrival Caption
- Reviewing job 47 / "The Empty Case" surfaced an awkward page 1 → page 2 transition: Amara teleports from the Vault to the community garden via the glowing leaf-tile, but page 2 opens in the garden with nothing telling the reader how she got there. For 8–14 ESL readers, an uninferable cut spends attention on "wait, how did she get here?" instead of on the vocab word.
- **Final-script prompts** (`graphic_novel_script.txt` + `graphic_novel_script_6page.txt`): extended the existing page-1 establishing-panel rule into a conditional **"re-establish on location change"** rule. When a page's location differs from the previous page **and** the reader can't infer the move by simple physical walking (a magical/instant transition like the leaf-tile, or a jump to a far/unrelated place), the page's first panel must open with one short caption re-establishing WHERE we are now and HOW the character arrived. Ordinary walkable moves in the same setting (classroom → hallway, kitchen → backyard) get **no** caption, so the 80-word page budget isn't wasted on redundancy. The decision test written into the prompt: *"could a reader assume the character just walked there?"* Caption wording is left open to the model — no canned template. A matching item was added to each prompt's self-check list.
- **Beat-sheet prompts** (`graphic_novel_beat_sheet.txt` + `..._6page.txt`): added a planning nudge tied to the per-page `setting_key` the beat sheet already tracks — when a page's `setting_key` differs from the prior page's via such a transition, note an arrival moment in `why_this_page_matters` so the script step has a planned beat to anchor the caption on.
- **Scope**: prompt-text only — no Python, validator, or schema changes. Affects **new** generations only; the existing job-47 novel needs its GRAPHIC_NOVEL_SCRIPT step re-run + page re-render (or a manual per-page image edit) to gain the caption.

### Test
- No new tests. The 28 existing script-step tests mock prompt loading and assert which template (5- vs 6-page) is selected, not prompt content, so they're unaffected — all 28 pass.

## [Unreleased] - 2026-06-01 (secondary character anchors never worked — bug fix)

### Fixed — Secondary Character Anchors Were Silently Dropped
- The secondary-character visual anchor feature (added 2026-05-28) had **never produced a single stored anchor**. Symptom that surfaced it: in job 46 / novel 40 ("The Muddy Rescue"), the secondary kid Toby drifted from a blue shirt on page 1 to a red shirt on page 6 — exactly the drift anchors exist to prevent.
- **Root cause**: the shared LLM wrappers (`call_gemini`, `call_anthropic`, and the OpenAI-compatible proxy path) **always force JSON mode** (`response_format={'type':'json_object'}`) and return a **parsed dict**, never a string. But `_generate_secondary_character_anchors` asked the model for "plain text, no JSON" and called `anchor_text.strip()` — raising `AttributeError: 'dict' object has no attribute 'strip'`. A broad `except Exception` swallowed it, logged a warning, and returned `{}`, so `novel.metadata['secondary_character_anchors']` was never written and every qualifying secondary character fell back to its bare script description (often missing outfit colors → image-model drift).
- **Fix** (`graphic_novel_helpers.py`): new `_format_anchor_design_lock(anchor_data) -> str` renders the dict's design-lock sections into a stable `KEY: value` text block (canonical order: AGE_AND_BODY, FACE_AND_HAIR, OUTFIT_LOCK, COLOR_PRIORITY, NEGATIVE_LOCK), passes a plain string through unchanged (defensive), and returns `''` for unexpected types. The consumer now formats the response, stores non-trivial anchors, and logs a warning (instead of crashing) when an anchor is empty/too short.
- **Prompt** (`prompts/secondary_character_anchor.txt`): rewritten to request a **JSON object** with the five named string fields, matching what the wrapper actually returns, instead of "plain text, no JSON".
- **Scope**: fix affects **new** generation only. Existing novels rendered with drift (e.g. novel 40) need the GRAPHIC_NOVEL_SCRIPT step re-run for the pack (repopulates the anchor into metadata) followed by page-image regeneration.

### Test
- Added `TestFormatAnchorDesignLock` (4 cases: dict rendering + section order, plain-string passthrough, unexpected-type → `''`, blank-section skipping) and `TestGenerateSecondaryCharacterAnchors` (2 cases: dict response → stored anchor regression, LLM failure → no raise) in `test_step_graphic_novel_script.py`.
- Full backend suite **379 passed**.

## [Unreleased] - 2026-05-31 (low-hanging-fruit cleanup: media, indexes, dedup, UX)

### Chore — Stop Tracking Generated Media in Git
- `backend/media/` held 396 generated files (AI page images + LLM output logs, ~893 MB) committed to the repo, bloating clones and every diff. Untracked the whole tree via `git rm -r --cached backend/media` (files stay on disk) and added it to the root `.gitignore`, keeping the two subdirectories (`generated_images/`, `graphic_novels/`) via `.gitkeep` so Django still has somewhere to write on a fresh clone.
- Note: this stops *future* growth only. The ~893 MB still lives in git history; reclaiming it needs a history rewrite (`git filter-repo`), deferred as a separate, more disruptive operation.

### Perf — Indexes on Hot Query Paths
- Added composite indexes (migration `0030_useranswer_..._idx_and_more`) on the two most-queried models:
  - `UserWordProgress`: `(user, next_review_at)` for the "due for review" practice/dashboard query, and `(user, instructional_status)` for READY/PENDING filtering.
  - `UserAnswer` (previously had no indexes): `(user, answered_at)` for activity/accuracy queries, `(user, is_correct)` for frequent-mistakes/challenging-words, and `(question, answered_at)` for per-word answer history (struggle-word detection).
- Closes the `UserWordProgress` + `UserAnswer` portion of BETA_IMPROVEMENTS item #6. `Question.word` index remains pending.

### Refactor — Dedup Definition-Translation Lookup
- Three services (`dashboard_service`, `practice_service`, `instructional_service`) each carried a near-identical private `_get_translation` / `_get_translations_for_primer` doing the same ContentType + Translation lookup. Consolidated into `vocabulary/utils.py`: `get_definition_translations(word, language, fields=(...))` (returns a dict of field→translated string) and the single-field wrapper `get_definition_translation(word, language)`. Removed the now-unused `ContentType` / `Translation` / `WordDefinition` imports from the affected services.

### Fixed — Replace Blocking alert() Calls with Inline UI
- Swapped the five native `alert()` dialogs in the teacher flows for inline error/success banners using the existing `t-message` styles:
  - `GroupManagementView`: save/delete errors now render in a banner (no more raw `JSON.stringify` dump).
  - `GroupFormModal`: name-required validation shows inline.
  - `CommandCenter` + `StudentFormModal`: save errors propagate into the modal's existing error slot (the parent handler re-throws; the modal catches).
  - `BulkStudentFormModal`: success shows an inline banner and auto-closes after a short delay instead of a blocking alert.

### Verification
- `manage.py check` clean; full backend suite **373 passed**; frontend `npm run build` compiles clean.

## [Unreleased] - 2026-05-31 (student-facing JPEG page images)

### Added — Lightweight JPEG Companions for Students
- Graphic novel page PNGs average ~3.3 MB each, which is slow to load over mobile data. Every page now gets a smaller JPEG companion (~0.5 MB, ~15% of the PNG — measured 287 MB → 42.6 MB across 85 existing pages) that **students** load instead. The PNG stays the source of truth for admins, image editing, and cross-page style continuity.
- **Model** (`GraphicNovelPage`): new `image_jpeg` and `edited_image_jpeg` ImageFields mirroring `image` / `edited_image`, plus a `student_image` property that returns the JPEG of the currently displayed variant, falling back to that variant's PNG when no JPEG exists. Migration `0029_graphicnovelpage_edited_image_jpeg_and_more`.
- **Conversion helper** (`vocabulary/services/image_utils.py`, new): `png_to_jpeg_bytes(png_bytes, quality=85)` opens with Pillow, flattens any alpha onto white, converts to RGB, and writes an optimized JPEG. Pillow is now a **runtime** dependency (added to `requirements.txt`; it was previously dev-only).
- **JPEG written alongside every PNG save**, all best-effort (a conversion failure never aborts PNG generation): the generation pipeline (`graphic_novel_images.py`, both the main and retry save blocks), the admin edit-image view (`edited_image_jpeg`), and a skip-path backfill (`backfill_page_jpegs`) that fills missing JPEGs when a job resumes over already-rendered pages.
- **Only the student read path changed**: `instructional_service.py` now serves `student_image`. All admin payloads (review/status/content views, edit/select endpoints) still serve the PNG via `display_image`. The student reader (`GraphicNovelReader.jsx`) needed no change — it already reads `image_url`. The `select-image` endpoint needs no file work since both JPEGs already exist; it just flips `use_edited_image`.
- **Backfill command** (`vocabulary/management/commands/backfill_jpeg_images.py`, new): idempotent, `--dry-run` supported. Converts every page that has a PNG but no matching JPEG. Pages whose PNG file is missing from disk are skipped (not errors).

### Test
- 12 new tests (`tests/vocabulary/test_jpeg_companion.py`): PNG→JPEG conversion (RGBA flatten, RGB passthrough, size reduction, invalid-input errors), `student_image` variant selection + PNG fallback, backfill idempotency, and the generation pipeline saving a JPEG companion. Full suite: 373 passed.

## [Unreleased] - 2026-05-31 (admin per-page image editing + variant selection)

### Added — Edit & Choose Graphic Novel Page Images
- Admins can now refine any single graphic novel page image from the GenerationReview screen, without re-running the pipeline.
- **Edit endpoint** `POST /api/graphic-novel-pages/<page_id>/edit-image/` (admin-only): takes `{"prompt": "..."}`, re-renders the page through OpenAI's existing `images.edit` path (the same call used for cross-page style continuity), passing the **currently displayed** image as the visual reference. Synchronous (~30-60s, one billed GPT-Image-2 call). Returns both variant URLs + which is active.
- **Select endpoint** `POST /api/graphic-novel-pages/<page_id>/select-image/` with `{"variant": "original"｜"edited"}` (admin-only): flips which stored variant is shown. Reversible; validates an edited image exists before selecting it.
- **Model** (`GraphicNovelPage`): new `edited_image` (ImageField) and `use_edited_image` (Boolean) fields, plus `display_image` and `has_edited_image` properties. **The original `image` is never overwritten** — edits land in `edited_image`. Migration `0028_graphicnovelpage_edited_image_and_more`.
- **Read paths updated to `display_image`** so the admin's choice propagates everywhere: student instructional flow (`instructional_service.py`), both content serializers + the per-page status helper (`generation_views.py`), and the pipeline's cross-page continuity reference (`graphic_novel_images.py`).
- **Frontend** (`GraphicNovelPageEditor.jsx`, new): per-page card with an edit-prompt box and an Original/Edited variant picker (✓ marks the live variant). `GenerationReview.jsx` renders it and merges edited pages back into state with cache-busted image URLs.

### Added — Click-to-Zoom Page Thumbnails
- On the GenerationReview Packs tab, graphic novel page thumbnails are now clickable. Clicking opens a fullscreen lightbox showing the currently previewed variant (original/edited) at full size, so admins can inspect detail that is hard to judge from the small thumbnail. Closes on backdrop click, the × button, or Escape. Implemented as a local `ImageLightbox` component inside `GraphicNovelPageEditor.jsx` — no new route, API, or shared CSS.

### Chore — Repository Hygiene
- Added a root `.gitignore` covering `temp/`, `tmp/`, machine-local Claude settings (`.claude/settings.local.json`), and standard Python/Node build output. Removed the 67 previously tracked `temp/llm_logs` files and `.claude/settings.local.json` from version control (kept on disk) so generated LLM logs and per-developer state stop polluting history.

### Fixed — Stale-Job Timeout Detection Test
- `test_stale_running_job_marks_running_graphic_page_failed` set job activity to 20 minutes ago, but `STALE_JOB_THRESHOLD_SECONDS` is 1800 (30 min), so the job correctly stayed RUNNING and the assertion failed. This is the "1 pre-existing unrelated failure" referenced in prior changelog entries. Bumped the test's log/page timestamps to 31 minutes so they're past the threshold. The view code was correct; only the test timing was wrong.

### Test
- 5 new edit/select endpoint tests (success preserves original + stores edit, variant round-trip, select-edited-without-edit 400, unknown-variant 400, student-forbidden 403). Full `TestGenerationViews` + `TestInstructionalPackView` suites pass with no remaining known failures.

## [Unreleased] - 2026-05-30 (admin UI pipeline-order sync)

### Fixed — Admin Views Now Reflect Current Pipeline Order
- **Generation Job status view** (`GenerationJobStatus.jsx`): the step list and the "Restart Step" dropdown showed `Pack Creation` before `Primer Generation`, contradicting the backend `PIPELINE_STEP_ORDER` (which runs `PRIMER_GEN` before `PACK_CREATION`). Reordered the frontend `PIPELINE_STEPS` constant to match.
- **Graphic Novel substep accordion**: the script step now always renders a collapsible accordion. Before the pipeline reaches the step (no per-pack data yet), it shows a "Planning Substeps (preview)" list of all 6 canonical substeps as PENDING, so the workflow is visible ahead of time. A new frontend `GRAPHIC_NOVEL_SUBSTEPS` constant mirrors `services/generation/constants.py`.
- **Generation view substep skeleton** (`generation_views.py`): `GRAPHIC_NOVEL_SCRIPT_SUBSTEPS` was missing `cloze_generation` (added at index 3 in the 2026-05-29 cloze separation). Aligned it with the canonical 6-substep order; this also enables the working cloze restart button.
- **LLM Config step matrix** (`/teacher/llm-config`): the Step Configuration tab rendered steps **alphabetically** (`order_by('step_key')`), scrambling the GN substeps (Beat Sheet, Cloze, Final Script, Premise Scoring, Router…). `llm_config_views.py` now sorts both the GET and PUT responses by `LLMStepConfig.StepKey` enum declaration order via a `_STEP_KEY_ORDER` index map, so the table follows true execution order.
- **`LLMStepConfig.StepKey` enum** (`models.py`): swapped `PACK_CREATION` and `PRIMER_GEN` so the enum declaration order matches pipeline execution order. Migration `0027_alter_llmstepconfig_step_key` (choices metadata only — no column or data change).

## [Unreleased] - 2026-05-30 (resume word-loss fix)

### Fixed — Pipeline Resume Losing Words After Mid-Dedup Failure
- When the dedup step failed partway through (e.g., embedding API timeout after processing 2 of 6 words), resuming the pipeline would only carry forward the partially-persisted words instead of the full set.
- Root cause: `_reconstruct_context` built `words_data` from the incomplete `word_set.words` when no completed DEDUP log existed, ignoring the full word list available in the WORD_LOOKUP log.
- Fix: `_reconstruct_context` now falls back to the WORD_LOOKUP log's `word_lookup_snapshot` when no completed DEDUP log is found. Added `_latest_word_lookup_snapshot()` helper in `step_word_lookup.py`.

## [Unreleased] - 2026-05-30 (pipeline clarity refactor)

### Refactor — Prompt & Validator Consolidation
- **World context preamble extracted**: the ~60-word Lexi Legends world paragraph that was duplicated across 7 graphic novel prompt files now lives in a single `prompts/graphic_novel_world_context.txt`. Runtime injection happens in `_run_graphic_novel_substep` (between role line and step instructions). Prompt templates are shorter and world-rule changes need only one edit.
- **Scorer prompt parameterized**: `graphic_novel_premise_scorer.txt` no longer hardcodes "5 pages". Each premise is evaluated against its declared `page_count` (5 or 6). Location ceiling is page-count-aware (≤2 for 5-page, ≤3 for 6-page). Directly improves scoring quality for 6-page premises.
- **Uniform validator context**: introduced `SubstepContext` dataclass in `graphic_novel_validators.py`. All graphic novel validators now accept `(result, ctx=None)` uniformly. Eliminated all lambda closures and ad-hoc `*_validator_summary` dicts from `graphic_novel_script.py`. Context holds `target_terms`, `winning_premise`, `selected_away_team`, `router_result`.
- **Placeholder comments removed**: 9 dead `# __PLACEHOLDER__` comments cleaned from `graphic_novel_script.py` and `graphic_novel_images.py`.

### Test
- 250 tests passing (1 pre-existing unrelated failure in stale-job timeout detection view).

## [Unreleased] - 2026-05-29 (cloze generation separated)

### Changed — Cloze Generation as Dedicated Substep
- Cloze quiz generation moved out of the Final Script + Self-Check substep into its own dedicated substep (`cloze_generation`, index 3 in `GRAPHIC_NOVEL_SUBSTEPS`).
- Runs after premise scoring using only the winning premise + vocabulary words as context (no dependency on beat sheet or final script).
- New prompt template: `backend/vocabulary/prompts/graphic_novel_cloze.txt`.
- New LLM step config key: `gn_cloze_gen` (seeded via migration 0026).
- New validator: `_validate_graphic_novel_cloze_result` in `graphic_novel_validators.py`.
- Artifact file: `03b_cloze_generation.json` in the pack artifact directory.
- Final script prompts (5-page and 6-page) no longer mention or return `cloze_items`.
- Substep order is now: team_selection → router_premises → premise_scoring → cloze_generation → beat_sheet_vocab_roles → final_script_self_check (6 substeps total).
- Motivation: cleaner script generation prompt lets the LLM focus purely on narrative craft, improving script quality.

### Test
- All 335 tests passing (1 pre-existing unrelated failure in stale-job timeout detection).

## [Unreleased] - 2026-05-29 (pipeline reorder + definition consolidation)

### Changed — Pipeline Step Order
- Swapped Primer Generation (now step 5) and Pack Creation (now step 6) so that Pack Creation is adjacent to the graphic novel steps it feeds.

### Changed — Review Definitions Consolidated into Primer Step
- Primer `kid_friendly_definition` changed from 1-2 sentence definitions to concise 3-8 word phrases suitable for vocabulary review cards.
- Removed `review_definitions` generation from the graphic novel script prompt (both 5-page and 6-page variants).
- Review page image generation now reads definitions from `PrimerCardContent.kid_friendly_definition` instead of `novel.metadata['review_definitions']`.
- Fallback: if a word has no `PrimerCardContent`, truncates `WordDefinition` to 8 words (unchanged).

## [Unreleased] - 2026-05-29 (graphic novel module split)

### Refactor — Split `step_graphic_novel.py` into Four Sibling Modules
- The 2003-line `vocabulary/services/generation/step_graphic_novel.py` was split into four files grouped by responsibility, with the original path kept as a thin re-export facade.
  - `graphic_novel_helpers.py` (~540 lines) — formatting helpers, artifact I/O, substep runner, character-color constants, secondary-character anchor generation, small pure helpers.
  - `graphic_novel_validators.py` (~400 lines) — every `_validate_*` function (team, router, scoring, beat, beat-complexity, vocab-anchors, script).
  - `graphic_novel_script.py` (~820 lines) — `_step_graphic_novel_script` and `restart_graphic_novel_from_substep`.
  - `graphic_novel_images.py` (~310 lines) — `_step_graphic_novel_images`.
  - `step_graphic_novel.py` (~95 lines) — facade that re-exports the public surface used by `__init__.py`, `orchestrator.py`, `generation_pipeline_service.py`, and the test suite.
- No behavior change. Public import paths (e.g. `from vocabulary.services.generation.step_graphic_novel import _step_graphic_novel_script, _validate_graphic_novel_router_result, _find_secondary_characters_needing_anchors, ...`) continue to work unchanged.

### Test
- Full graphic novel test module (`tests/vocabulary/test_generation_pipeline_service.py`) green: 57 passing, no test edits required.

## [Unreleased] - 2026-05-28

### Added — LLM Configuration Matrix (Admin)
- **LLMSite model**: defines API proxy endpoints with name, base URL, provider type (`gemini_native` / `openai_compatible` / `anthropic`), and API key env var reference. Keys stay in `.env`; the model stores only the env var name and resolves at runtime.
- **LLMStepConfig model**: maps each of 10 text-generation pipeline steps to a primary and fallback site+model pair. Steps: `word_lookup`, `translation`, `question_gen`, `pack_creation`, `primer_gen`, `gn_team_selection`, `gn_router_premises`, `gn_premise_scoring`, `gn_beat_sheet`, `gn_final_script`.
- **Admin UI** at `/teacher/llm-config` (two tabs: Sites management, Step Configuration matrix). Accessible via "LLM Config" button in the navbar for admin users.
- **API endpoints**: `GET/POST /api/admin/llm-sites/`, `PUT/DELETE /api/admin/llm-sites/<id>/`, `GET/PUT /api/admin/llm-step-configs/`.
- **llm_config_service.py**: cached lookup layer (5-min TTL) providing `get_step_config(step_key)` → `{primary: {model, provider_type, base_url, api_key}, fallback: {...}}`. Raises `LLMConfigError` if no config exists for a step.
- **Pipeline dispatch refactored**: orchestrator builds `[primary, primary, fallback]` attempt list from DB config instead of hardcoded constants. Each graphic novel substep looks up its own config independently.
- `call_gemini()` and `call_anthropic()` now accept optional `api_key` and `base_url` overrides (backwards-compatible).
- `call_anthropic()` now handles empty `user_prompt` by collapsing system prompt into the user message (matches Gemini proxy behavior; fixes 500 errors when routing steps with empty user_prompt to Anthropic).
- Migration `0025_llm_config` creates tables and seeds one default Gemini site with all 10 steps configured (primary: `gemini-3.1-pro-preview`, fallback: `gemini-3-pro-preview`).

### Test
- Updated `TestRunFullPipeline` assertions to match new config-dict dispatch (347 tests passing).

## [Unreleased] - 2026-05-28 (secondary character anchors)

### Added — Secondary Character Visual Anchors
- After the final script step, an extra LLM call generates a detailed visual reference sheet (~150 words covering body, face/hair, outfit, color priority, negative constraints) for secondary characters who have dialogue AND appear on non-consecutive pages. Prevents visual drift when a character skips a page and the image model has no prior reference.
- Detection logic: `_find_secondary_characters_needing_anchors(result)` scans the script output for non-hero characters with speech on non-consecutive pages.
- Storage: `novel.metadata['secondary_character_anchors']` — dict of `{name: anchor_text}`. No migration needed.
- Image prompt lookup (`_characters_for_graphic_novel_page`) now checks `LEXI_CHARACTERS` first (hero → canon injection), then stored anchors, then falls back to the brief `novel.characters` entry. Eliminates spurious "Unknown character name" warnings for LLM-invented secondary characters.
- Prompt template: `backend/vocabulary/prompts/secondary_character_anchor.txt`.
- Uses `gn_final_script` LLM config (same model that wrote the script).

### Test
- Added `TestFindSecondaryCharactersNeedingAnchors` (5 cases): empty pages, hero-only, speaking secondary with gap, non-speaking secondary, consecutive-only secondary.
- **Caveat (discovered 2026-06-01):** these tests covered detection only, not the LLM call + storage path — which was broken from this commit until the 2026-06-01 fix above (the call returned a dict, not the assumed plain-text string, and the result was silently dropped).

## [Unreleased] - 2026-05-29

### Change — Unified 5/6-Page Graphic Novel Pipeline (Replaces Dual-Channel Architecture)
- Each pack now generates **one** graphic novel at a length the router LLM picks per premise (5 or 6 pages). The 6-page admin-only channel is removed.
- Router prompt: each candidate premise now declares `page_count_rationale` (one sentence) followed by `page_count` ∈ {5, 6}. Chain-of-thought ordering — rationale appears before the numeric decision.
- Scorer carries the winning premise's `page_count` forward; beat-sheet and final-script substeps dispatch to the matching prompt template via `GRAPHIC_NOVEL_BEAT_SHEET_TEMPLATES = {5: 'graphic_novel_beat_sheet', 6: 'graphic_novel_beat_sheet_6page'}` and the same shape for `_SCRIPT_TEMPLATES`.
- Pipeline trimmed from 10 to **8 steps**. Removed `GN_6PAGE_SCRIPT` / `GN_6PAGE_IMAGES` from `PIPELINE_STEP_ORDER`. Enum values stay on `GenerationJobLog.Step` so old log rows remain readable; no current code path emits them.
- Removed `GRAPHIC_NOVEL_6PAGE_ENABLED` setting and `GRAPHIC_NOVEL_6PAGE_SUBSTEPS` constant. Deleted `_step_graphic_novel_script_6page` and `_step_graphic_novel_images_6page`.
- Validators collapsed: one `_validate_graphic_novel_beat_result` (and one `_validate_graphic_novel_script_result`) reads expected length from `input_summary['winning_premise']['page_count']`. Router validator `_validate_graphic_novel_router_result` now requires a non-empty `page_count_rationale` and `page_count` ∈ {5, 6} on every premise.
- Plot complexity caps now scale by chosen length via `max_locations_for_page_count(page_count)` helper (≤2 for 5-page, ≤3 for 6-page). Existing `GRAPHIC_NOVEL_MAX_LOCATIONS_5PAGE` / `_6PAGE` constants kept as the helper's source of truth. Per the user's call, the router has full latitude on length — no hard rules tying length to location count or secondary characters.
- `GraphicNovel.channel` field stays as a vestigial column (always `'5page'` for new rows). `unique_together = ('pack', 'channel')` retained. No DB migration; the field is harmless and a later cleanup migration can drop it.
- `restart_graphic_novel_from_substep` recovers `winning_premise.page_count` from the saved router/scorer artifact and uses it for template dispatch on rerun.
- `resume_pipeline` now treats a job whose `last_completed_step` is no longer in `PIPELINE_STEP_ORDER` (e.g. an in-flight job stamped `GN_6PAGE_*` before this change) as fully complete.
- `novel.metadata['page_count']` is the new source of truth for downstream readers; `instructional_service.py` is unchanged because it iterates the saved page rows, not a fixed length.
- `_run_graphic_novel_substep` extended with optional `prompt_template_name` override so the substep config record can stay length-neutral while individual calls swap templates.

### Test
- Added `TestRouterValidatorPageCount` (6 cases): accepts baseline; rejects missing/invalid/string `page_count`; rejects missing/blank `page_count_rationale`.
- Added `TestStepGraphicNovelScriptTemplateDispatch` (2 cases): verifies that `winning_premise.page_count == 5` invokes the 5-page beat-sheet/script templates and `== 6` invokes the 6-page templates; both also assert `novel.metadata['page_count']` is persisted.
- Removed legacy `_step_graphic_novel_script_6page` / `_step_graphic_novel_images_6page` mocks. Full backend suite green (347 passing).

## [Unreleased] - 2026-05-27 (afternoon)

### Change — Graphic Novel Pedagogy Remediation (Moves 1/2/3)
- **Move 1 — Pedagogical anchor contract.** Every router `vocab_integration_plan` item must now declare a `pedagogical_anchor = {anchor_type, anchor_sketch}` with `anchor_type` from `{demonstrated_action, near_synonym, category_example, visible_referent}`. Final script propagates these into per-page `vocab_anchors`. Constant: `GRAPHIC_NOVEL_PEDAGOGICAL_ANCHOR_TYPES`. Validator `_validate_vocab_integration_plan` rejects premises lacking the anchor.
- **Move 2 — Plot complexity caps.** Each premise now carries `complexity_budget = {locations, secondary_characters, problem_thread}`. Hard caps: 5-page ≤2 locations / ≤2 secondary characters; 6-page ≤3 locations. Single-thread requirement enforced. Beat-sheet validator `_validate_beat_complexity` checks `setting_keys` count and that `characters_featured ⊆ away_team ∪ secondary_characters`. Constants: `GRAPHIC_NOVEL_MAX_LOCATIONS_5PAGE`, `GRAPHIC_NOVEL_MAX_LOCATIONS_6PAGE`, `GRAPHIC_NOVEL_MAX_SECONDARY_CHARACTERS`.
- **Move 3 — Mini cap tightened.** `GRAPHIC_NOVEL_MAX_MINI_SUMMONS_PER_STORY` reduced from 2 to 1. Most vocab now integrates through dialogue/narration/world logic; the single allowed Mini is reserved for the most concrete/abstract word in the pack.
- **Shades removed.** `shades_present` is no longer a team-selector flag or a downstream prompt input. The literal field survives only on legacy `GraphicNovel.metadata` rows (migration `0023_graphic_novel_lexi_legends_metadata`).
- **Scorer dimensions overhaul.** `GRAPHIC_NOVEL_SCORING_DIMENSIONS` rewritten to `{narrative_clarity, visual_potential, vocabulary_integration, pedagogical_clarity, character_fit}`. Old dimensions (`narrative_engagement`, `ip_coherence`, `ink_over_reliance`, `originality`) dropped to refocus on ESL teaching value.
- **Doc clarifications.** Graphic novel script step is Gemini `gemini-3.1-pro-preview` (not Claude Opus — that mention in CLAUDE.md/README/PROJECT_CONTEXT had been stale since the 2026-05-24 model switch). The Anthropic SDK and `ANTHROPIC_API_KEY` remain wired for fallback / future use; the dispatcher in `helpers.py` only routes to Anthropic when the model name contains `claude`/`sonnet`/`opus`/`haiku`.

### Test
- Updated `tests/vocabulary/test_generation_pipeline_service.py` fixtures for the new contracts (44/44 pipeline tests passing).
- Fixed `tests/vocabulary/test_llm_service.py::TestCallAnthropic` after a previous switch from `client.messages.create` to `client.messages.stream` left the mocks pointing at the wrong API. Added a `_make_stream_mock` helper that builds the streaming context-manager chain.

## [Unreleased] - 2026-05-27

### Fix — Gemini Proxy Routing & Timeout Handling
- `call_gemini` now branches on `GEMINI_BASE_URL`: when set, uses the **OpenAI SDK** against the proxy's `chat.completions` endpoint; when empty, uses the `google.genai` SDK natively. Fixes 403 errors from OpenAI-compatible proxies (e.g., `api.b.ai`) that only allow `/v1/chat/completions`, `/v1/messages`, `/v1/models` paths and rejected the native `:generateContent` calls the Google SDK was emitting.
- Empty `user_prompt` is now collapsed into a single user message before sending to the proxy. Several pipeline steps (`step_questions`, `step_packs`) pass the full prompt as `system_prompt` with an empty user message, which the proxy rejected with `400 "at least one contents field is required"`.
- `GEMINI_BASE_URL` value normalized — trailing `/chat/completions` is stripped automatically since the OpenAI SDK appends it.
- OpenAI SDK auto-retries disabled (`max_retries=0`) and explicit `timeout=600.0` set on the proxy client. Previously the SDK's hidden 2 retries stacked on top of orchestrator retries, turning a single failed call into three sequential 200-second proxy roundtrips before bubbling the error.
- Reduced `QUESTION_BATCH_SIZE` from 6 → 3 in `step_questions.py`. Smaller batches finish faster and reduce 502 Bad Gateway risk from upstream proxy timeouts on long LLM calls.

### Change — Lexi Mini System (Replaces Ink VFX)
- Replaced the abstract Ink-VFX vocabulary mechanic with the **Lexi Mini system**: writing a vocab word now summons a temporary monochromatic creature that physically acts out the word's definition (Hugo→Dependable golems, Leo→Mischievous imps, Amara→Scholarly moths/sphinxes, Mei→Agile foxes/wyverns)
- Hard cap: 0–2 Mini summons per story; most vocab still integrates through dialogue, narration, or world logic
- Tool changes: Hugo's flat paintbrush → orange **carpenter's pencil**; Leo's spray can → cyan **chunky wax crayon**. Amara's golden quill and Mei's multicolor marker unchanged.
- New rule: writing tools only appear on-page during a Lexi Mini summon. In zero-Mini panels, tools are not visible.
- Removed all Ink failure states (wobble/sag/drip/fade) — every Mini summon succeeds. Failure states were confusing for ESL learners and unrenderable in static panels.
- **Folio fully removed** from canon, prompt pipeline, and review page logic. `folio_present` flag removed from team selector validation and `novel_metadata`. UI mascot decisions deferred — kept out of the generation pipeline.
- Pipeline: `GRAPHIC_NOVEL_ALLOWED_INTEGRATION_MODES` constant replaced `direct_ink_activation` with `lexi_mini_summon`. JSON field names `uses_direct_ink` and `ink_usage` retained for backwards compatibility (old novels in DB still render unchanged).
- Default `review_artifact_type` fallback: `Vault clue board` (was `Folio field guide`).
- Updated all 8 character prompt-injection files (Hugo/Leo/Amara/Mei × 9yo/12yo): replaced `INK_VFX_LOCK` with `LEXI_MINI_LOCK`, added tool-visibility rule, removed aerosol/paintbrush/failure language.
- Updated runtime canon: `team-selector-summaries.md`, `script-character-sheets.md`, `vault-zones-script.md` cleared of Folio and old tool references.
- Deleted `backend/data/canon/cast/folio/` directory.

### Refactor — Canon Files Relocated
- Moved runtime canon files from `docs/feature_plan/runtime_canon/lexi_legends/` to `backend/data/canon/`
- Moved `lexi-legends-cast-bible.md` from `docs/feature_plan/` to `backend/data/canon/`
- Updated `canon_service.py` path constants to resolve from `backend/data/canon/`
- Updated all skill files (setting-building-pipeline, review-canon-sheets, character-building-pipeline) to reference new paths

## [Unreleased] - 2026-05-25

### Feature — Dual-Channel Graphic Novel Generation
- Added 6-page graphic novel channel that runs alongside the existing 5-page pipeline
- Each generation job now produces two graphic novels per pack: 5-page (student-facing) and 6-page (admin-only)
- `GraphicNovel` model changed from OneToOneField to ForeignKey with `channel` field ('5page'/'6page') and `unique_together` constraint
- 6-page channel runs its own independent 5-substep pipeline (team selection → router → scorer → beat sheet → final script) with dedicated prompts
- 6-page channel generates images via OpenAI GPT-Image-2 (same as 5-page)
- 6-page channel skips cloze item creation (5-page channel already creates them)
- Added `GRAPHIC_NOVEL_6PAGE_ENABLED` setting (default: True) to enable/disable the 6-page channel
- New pipeline steps: `GN_6PAGE_SCRIPT` and `GN_6PAGE_IMAGES` (steps 9-10)
- Student-facing instructional service only serves `channel='5page'` novels
- New prompt templates: `graphic_novel_beat_sheet_6page.txt`, `graphic_novel_script_6page.txt`

### Fix — 6-Page Image Generation
- Fixed `_step_graphic_novel_images_6page` passing wrong keyword argument (`previous_image_path=`) to `_call_openai_image_releasing_db`; now correctly passes `reference_image=` with image bytes (matching 5-page behavior)
- Fixed orchestrator retry logic logging wrong model name (`gemini-3.1-pro-preview`) for image steps; now correctly logs `gpt-image-2`
- Fixed 6-page image filenames: changed from `{vocab_words}_{pack_id}_6p{N}.png` to `{title_slug}_6p_page_{N}.png` to match 5-page naming convention
- Fixed `Unknown vault zone requested: 'review-artifact'` warning: review pages now skip vault zone lookup entirely (they use their own `review_artifact_type` prompt field)
- Fixed `Duplicate entry for key 'vocabulary_graphicnovel_pack_id_channel_uniq'` on pipeline resume: added defensive delete before novel creation for both channels to handle edge cases where the top-of-loop guard passes but a stale record exists

## [Unreleased] - 2026-05-24

### Fix — Translation Step Reliability
- Translation prompt now returns `term` field in each output object, enabling primary-key-based matching instead of fragile substring matching on `source_text`
- Translation matching logic rewritten: looks up word by `term` (case-insensitive) rather than iterating all words with substring `in` checks
- Validation changed from "all source_text pairs matched" to "all expected terms have translations"

### Improvement — Primer Syllable Accuracy
- Added explicit single-syllable rule to primer prompt: output word as-is without dot characters
- Added phonetic syllable preference: use sound-based breaks over spelling-based when they differ (benefits ESL learners)

### Optimization — Graphic Novel Prompt Round 2 (Log Audit)
- Applied chain-of-thought JSON ordering: `team_rationale` moved before boolean decisions in team selector; `arc_planning` and `vocab_page_assignments` added before `beat_sheet` array in beat sheet prompt
- Added `total_ink_activations_planned` counter before vocab arrays in router (per premise) and beat sheet prompts to enforce the max-2 Ink activation limit
- Added `vocab_page_assignments` checklist in beat sheet — LLM assigns words to pages before generating the beat sheet, reducing word-dropping
- Beat sheet `page_turn_question` explicitly defined as `null` for Page 5 (removes ambiguous free-text workaround)
- Replaced "K-8" with "ages 8–14" across all 5 graphic novel prompt files
- Switched graphic novel script model from `claude-sonnet-4-6` to `gemini-3.1-pro-preview` (better structured JSON output)
- Added `_call_llm_releasing_db()` routing helper that picks Gemini or Anthropic backend based on model name
- Made `collapse_markdown()` public in `canon_service.py`; applied it to full visual character sheets before embedding in script step JSON (removes `\n`/`##` noise from serialized prompts)
- Router: moved `vocab_integration_plan` before `premise` paragraph — forces model to plan vocab mechanics before writing narrative
- Scorer: added `dimension_rankings` scratchpad as first key — model ranks premises per dimension before assigning numeric scores
- Beat sheet: moved `vocab_roles` and `ink_usage` before `beat_sheet` array — model defines Ink mechanics before writing page beats
- Final script: added per-page `page_planning` object before `panels` — model verifies text budget, target words, layout, and shot scales before generating panel content
- Canon: added Ink mechanic examples (success + failure per character) to `team-selector-summaries.md` and `script-character-sheets.md` to ground Ink as a linguistic puzzle mechanic

## [Unreleased] - 2026-05-23

### Change — Graphic Novel Creative Flexibility Revision
- Pack grouping prompt: replaced prescriptive `story_engine_hint` (closed list of action-heavy engines) with free-text `narrative_approach` field; reframed grouping criteria around situational cohesion instead of conflict/plot mechanics; added explicit 5-page length warning
- Router prompt: replaced `story_engine` → `narrative_approach`, `central_problem` → `central_thread`; broadened agency definition; added 5-page complexity warning; expanded narrative approach examples (observational, slice-of-life, etc.)
- Scorer prompt: replaced `narrative_engagement` → `narrative_clarity` (rewards clarity over momentum); replaced "flat pacing" penalty with "too many plot beats for 5 pages"; updated winning premise schema
- Beat sheet prompt: relaxed "hook + build momentum" to "draw in + develop the situation"; added arc shape examples for observational/slice-of-life; replaced `anti_flatness_guard` with `narrative_coherence`
- Team selector: added `sample_team_options()` coin flip — all-solo or all-dual options (forced 50/50 split); biased `shades_present` toward false (only for genuinely confusable meanings); biased `vault_framing` to require earning its page space
- Pipeline code: propagated field renames (`story_engine` → `narrative_approach`), updated validation to accept `central_thread`

### Fix — Graphic Novel Script Retry and Validation
- Fixed `_text_terms_from_graphic_novel_page` crash when LLM returns `null` for narration/dialogue text fields (used `or ''` instead of `.get(key, '')` which doesn't handle explicit null)
- Fixed orchestrator retry restarting entire 5-substep flow from team_selection on final script failure; substeps now retry internally (1 retry per substep) and orchestrator runs GRAPHIC_NOVEL_SCRIPT only once
- Added substep-level restart: `POST /api/generation-jobs/{id}/restart-substep/` accepts `pack_id` and `substep` key, loads prior substep artifacts from disk, and re-runs from the target substep onward
- Frontend: each graphic novel substep row now shows a restart button (visible when job is not running)

### Optimization — Graphic Novel Prompt Restructuring
- All 5 script substeps now use system/user prompt split (instructions in system, data in user message)
- Removed `rulebook` and `learning_behavior` from all script step payloads (irrelevant to story generation)
- Created `team-selector-summaries.md` — purpose-built hero summaries + pairing dynamics for team selection
- Created `script-character-sheets.md` — narrative-only character info for router/scorer/beat sheet (no visual specs)
- Created `vault-summary-premises.md` — condensed vault context for premise generation (~30 lines vs ~200)
- Team selector now receives world primer, filtered hero summaries, and filtered pairing dynamics (only for teams in options)
- Router/scorer/beat sheet use lightweight `router_lexi_context` instead of full visual sheets
- Final script step retains full visual sheets + vault spec (needed for image generation downstream)
- Pairing dynamics converted from raw markdown to structured format across all steps
- Image prompts: panel content formatted as prose (not raw JSON), synopsis trimmed for pages 2+, setting context added for non-vault pages, vocabulary highlighting uses per-character Ink colors
- Added `canon_service.py` functions: `load_team_selector_heroes()`, `load_team_selector_dynamics()`, `load_script_character_sheets()`, `load_vault_summary_premises()`
- `_format_graphic_novel_prompt()` is now dead code (all steps pass templates directly)

## [Unreleased] - 2026-05-22

### Refactor — Generation Pipeline Modularization
- Split `generation_pipeline_service.py` (2094 lines) into `vocabulary/services/generation/` package:
  - `orchestrator.py` — pipeline run/resume/restart control flow
  - `step_word_lookup.py` — steps 1-2: word lookup + dedup
  - `step_translations.py` — step 3: translations
  - `step_questions.py` — step 4: question generation
  - `step_packs.py` — steps 5-6: pack creation + primers
  - `step_graphic_novel.py` — steps 7-8: graphic novel script + images
  - `helpers.py` — shared LLM wrappers, logging utilities
  - `constants.py` — model names, step order, config constants
- Old import path (`vocabulary.services.generation_pipeline_service`) preserved via backwards-compatible shim
- Test patches updated to target actual module locations (`llm_service`, `embedding_service`, `orchestrator`)
- Fixed stale test assertion for canon character prompt injection content

### Graphic Novel Pipeline — Canon Service Integration
- Added `canon_service.py`: loads runtime canon files (character sheets, Vault specs, rulebook, pairing dynamics) into LLM prompts for visual and narrative consistency
- Beat sheet and script calls now receive full character `.md` sheets, Vault script context, rulebook, and learning behavior plan
- Image prompts now receive compact character design locks (`_prompt_injection.txt`) instead of LLM-invented descriptions
- Added STYLE_LOCK to `graphic_novel_page.txt` and `graphic_novel_review_page.txt` to prevent rendering style drift
- Vault page image prompts now use full Vault image specs + zone-specific overlays instead of a 3-line stub
- Team selector receives pairing dynamics from the cast bible for chemistry-aware team selection
- Team options randomized to 3 candidates (from 10) to encourage variety
- Added path traversal guards: character name allowlist and vault zone allowlist

## [Unreleased] - 2026-05-16

### Graphic Novel Reader UX Improvements
- Expanded reader width from 1080px to min(1792px, 90vw) so page images display closer to native resolution
- Vocabulary cards now shown by default on each page (previously required tapping the image)
- Page navigation (arrows, keyboard, swipe, dots) no longer hides vocabulary cards
- Merged title row and footer into a single sticky toolbar: page count + title on the left, page dots in the center, "Done Reading" button on the right
- Removed the instructional header (pack name + step label) to save vertical space
- "Done Reading" button now uses green color and fades in after a 3-second delay on the last page to encourage reading before advancing

## [Unreleased] - 2026-05-15

### Bug Fixes
- Fixed review scheduling: `NextPracticeWordView` now includes questions with NULL `lexile_score` in the Lexile filter (matching `StudentDashboardView`), so newly learned words appear for same-day review even when their questions lack a Lexile score
- Fixed cloze blank fill: `ClozeQuiz` now splits on 3+ underscores (`/_{3,}/`) instead of exactly 7, so graphic novel cloze items with varying blank lengths render correctly
- Fixed TTS auto-play on type-in retry: after a successful retry submission via Enter, feedback buttons use `tabIndex={-1}` until ready, preventing the Enter keyup from activating the Explain button and triggering text-to-speech

## [Unreleased] - 2026-05-14

### Graphic Novel Instructional Flow
- Replaced new full-pipeline micro-story generation with AI-generated graphic novels for the instructional Read step
- Added `GraphicNovel` and `GraphicNovelPage` models plus migration `0018_graphic_novel`; each page stores one complete 1792x1024 landscape comic image and panel metadata
- Added migration `0019_graphic_novel_page_status` so each `GraphicNovelPage` tracks image-generation status, attempts, error text, start time, and completion time
- Added `GenerationJob.graphic_novels_created` and new pipeline log steps `GRAPHIC_NOVEL_SCRIPT` and `GRAPHIC_NOVEL_IMAGES`
- Updated `PIPELINE_STEP_ORDER` to run `GRAPHIC_NOVEL_SCRIPT` and `GRAPHIC_NOVEL_IMAGES` after `PRIMER_GEN`; legacy `STORY_CLOZE_GEN` remains available for existing logs/manual use but is no longer used for new full-pipeline content
- Added `graphic_novel_script.txt` and `graphic_novel_page.txt` prompt templates
- `call_openai_image()` now accepts a `size` parameter; graphic novel pages request `1792x1024`
- `GET /api/instructional/packs/<pack_id>/` now returns `story.type = "graphic_novel"` with page data for new packs and falls back to `story.type = "micro_story"` for legacy packs
- Added `GraphicNovelReader` with 16:9 page display, arrow/keyboard/swipe navigation, page dots, tap-to-open vocabulary overlay, and final-page completion
- Removed the old per-word visual generation path end to end: model fields, generated image records, practice/review UI, API payloads, stale prompts, and related tests.
- Updated admin generation status/review surfaces to display `Graphic Novel Script` and `Graphic Novel Images` instead of the legacy `Story & Cloze Generation` label, and to expose generated graphic novel page data in review payloads
- `GET /api/generation-jobs/<id>/` now includes `graphic_novel_image_pages` so the admin status page can show per-page `PENDING`/`RUNNING`/`COMPLETED`/`FAILED` progress for `GRAPHIC_NOVEL_IMAGES`
- `GRAPHIC_NOVEL_IMAGES` now skips completed page images, marks each page attempt independently, and fails the step if any page remains failed; Resume retries only missing/failed pages instead of starting from page 1
- Added explicit backend progress logging around graphic novel script and page image generation; LLM/image prompt logs continue to be written to `temp/llm_logs/`
- Released Django/MySQL connections before and after slow Gemini/OpenAI calls in the background generation pipeline, and closed background-thread connections when pipeline/resume/restart exits, to avoid connection exhaustion during long graphic novel image generation
- Slowed the admin generation status polling interval from 3 seconds to 10 seconds to reduce database pressure while jobs are running; stale running jobs now record a FAILED log and reset the word set out of `GENERATING`
- Added factories and focused tests for graphic novel models, generation steps, instructional API fallback, and OpenAI image size compatibility

## [Unreleased] - 2026-05-13

### Response-Quality-Aware Scheduling
- `PracticeService` now classifies first-attempt answer quality using persisted `UserAnswer.duration_seconds`, `UserAnswer.answer_switches`, and `Question.question_type`
- Correct answers use per-learner, per-question-type timing baselines only after 15 valid samples from the latest 50 first-attempt answers, filtering to `1 < duration_seconds < 100`
- Correct answers without enough timing history use the previous behavior as `unclassified_correct`
- Answer qualities now include `fast_correct`, `solid_correct`, `slow_correct`, `switched_correct`, `typo_retry_correct`, `incorrect`, and `unclassified_correct`
- `learning_speed` still uses an EMA, but each quality has its own quality value and immediate interval factor
- Incorrect answers always use the `incorrect` schedule adjustment, even without timing history
- Replaced the 0.5-day minimum review interval with a 1-day minimum so a student does not see the same word again on the same day
- Fragile correct answers may still promote, but if promotion happens, the next interval is capped by the old-level schedule
- Typo retries are now tracked server-side in the Django session after an `is_typo` response; the next first-attempt correct answer for that question becomes `typo_retry_correct`
- `/api/practice/submit/` responses now include scheduling metadata: `response_quality`, `is_fragile`, `review_interval_days`, `next_review_at`, and `schedule_reason`

## [Unreleased] - 2026-05-01

### Mastery Schedule & Hidden Long-Term Levels
- Added `MasteryLevel.is_hidden` and migration `0017_hidden_mastery_level`
- Current mastery schedule: Level 1 `1d/2pts`, Level 2 `3d/4pts`, Level 3 `7d/7pts`, Level 4 `10d/10pts`, Level 5 `17d/15pts`, Level 6 `30d/25pts` hidden, Level 7 `60d/999pts` hidden
- Level 6 and 7 words are rolled into the student-facing Mastered accordion/list instead of appearing as separate levels
- Student dashboard daily/weekly mastery deltas ignore transitions that stay within the displayed Mastered bucket, including 5->6, 6->7, 7->6, and 6->5
- Practice questions for hidden levels ignore `Question.suitable_levels` and may use any question for the word within the student's Lexile range

### Generation Pipeline Reliability & Observability
- Set content-generation default model to `gemini-3.1-pro-preview` with backup model `gemini-3-pro-preview`
- Added per-step retry policy for Gemini-backed content steps: one retry with the current model, then one retry with the backup model
- Retry attempts are persisted as `GenerationJobLog` entries with attempt/model/next_model/error details
- Resume endpoint now writes a fresh RUNNING job log before starting the background thread so status polling does not immediately mark resumed jobs stale

## [Unreleased] 鈥?2026-04-30

### Image Generation Pipeline 鈥?Educational Value Rewrite
- Removed Hoyoverse/Genshin Impact aesthetic framing from creative direction and image generation prompts
- Added "Definition Clarity Check" instruction: LLM must verify a child could guess the word's meaning from the image alone
- Scenes now grounded in real-world contexts (gym, nature, classroom) instead of fantasy/elemental settings
- Anime cel-shading retained as rendering style only, not compositional driver

### Image Generation Pipeline 鈥?Creative Direction Step (prior unreleased)
- Word lookup step now classifies each word into an image category
- Image generation switched from Gemini to OpenAI GPT-Image-2

---

## [Unreleased] 鈥?2026-04-23

### Daily Goal System
- Teacher-configurable daily goal bounds per student (`daily_goal_min`, `daily_goal_max`)
- Daily goal adjustment prompt with `last_goal_prompt_date` tracking
- New `StudentGoalPromptView` endpoint (`POST /student/goal-prompt-shown/`)
- Default daily question limit changed from 20 to 30
- Goal bounds validation in `StudentCreateUpdateSerializer` (min >= 10, min <= limit <= max)
- Dashboard API returns `daily_goal_min`, `daily_goal_max`, `last_goal_prompt_date`

### Student Names
- Added `first_name` and `last_name` fields to student serializers (User, TeacherStudent, StudentCreateUpdate, Roster)
- Bulk student creation now accepts `first_name` and `last_name`

### Practice Session Rework
- Scaffolded retry system: `is_retry` flag on answer submission skips mastery/XP updates, increments `retry_count` on UserAnswer
- Lexile filtering now includes `lexile_score__isnull=True` questions (fallback for unscored questions)
- Streak tracking uses `timezone.localdate()` instead of `date.today()` for timezone correctness
- Redesigned PracticeView with improved layout and interaction flow

### Curriculum & Level Model Changes
- Level now has a ForeignKey to Curriculum (scoped levels per program)
- Level `name` uniqueness changed from global to `unique_together = [('curriculum', 'name')]`
- `LevelViewSet` supports `?curriculum_id=` query param filtering
- WordSetFormSerializer resolves `curriculum_name` and `level_name` via `get_or_create`
- Removed `unit_or_chapter` from WordSet serializers

### Mastery Level Interval Update
- Spaced repetition intervals changed: Level 1: 0鈫?d, Level 2: 1鈫?d, Level 3: 3鈫?d, Level 4: 7鈫?0d, Level 5: 14鈫?0d
- Data migration with reversible `revert_intervals`

### Image Generation Config
- Separate `IMAGE_API_KEY` and `IMAGE_BASE_URL` settings (defaults to Gemini credentials)

### Frontend Overhaul
- Simplified GenerationWizard, GenerationReview, and GenerationJobStatus components
- Streamlined CommandCenter, StudentProgressDashboard, and WordSetDetailView
- Refactored form modals with SearchableSelect component for curriculum/level dropdowns
- New `teacher.css` stylesheet
- Updated student styles: dashboard, practice, feedback, and component CSS
- Improved MicroStoryView and PrimerCard rendering
- Navbar and layout adjustments for Student and Teacher views

### Migrations
- `0002_add_daily_goal_bounds` 鈥?daily_goal_min, daily_goal_max, last_goal_prompt_date on CustomUser
- `0010_level_curriculum_alter_level_name_and_more` 鈥?Level FK to Curriculum, scoped uniqueness
- `0012_add_retry_count_to_useranswer` 鈥?retry_count field on UserAnswer
- `0013_update_mastery_level_intervals` 鈥?updated spaced repetition intervals

- `0017_hidden_mastery_level` - adds hidden long-term mastery levels and updates the current spaced repetition schedule

### Tests
- Expanded test coverage: views, serializers, models, adapted services, embedding service

---

## [0.6.0] 鈥?2026-04-06

### Beta Readiness 鈥?Bookmarks, Generation Requests, UX Fixes

**Teacher workflow:**
- Word set bookmarks with toggle (star) button and Bookmarked tab
- 4-tab word set list: My Sets / Bookmarked / Public / All
- "Request Generation" button for teachers, with admin queue page
- Generation queue badge in admin navbar (polls every 60s)
- Already-assigned indicators in assign modal
- Live word count in word set form textarea
- Toast notifications replace alert() for assign success

**Security & stability:**
- Login rate limiting (5/min per IP via AnonRateThrottle)
- Global React ErrorBoundary with reload fallback
- `.env.example` template for onboarding

**Code quality (from /simplify):**
- Toast uses `{type, text}` object instead of fragile string matching
- `canRequestGeneration` checks `input_words` existence
- `WordInfo` moved outside component to avoid re-creation per render
- CSS `!important` replaced with proper specificity
- Empty catch blocks now log errors
- Backend `input_words` check uses `isinstance`

---

## [0.5.0] 鈥?2026-04-03

### New Question Types, Picture-Word Match, Type-to-Spell, Typo Detection

- 8 new question types (REVERSE_DEFINITION_MC, SYNONYM_IN_CONTEXT_MC, etc.)
- Picture-word match generation pipeline step
- Type-to-spell mode for higher Lexile students
- Damerau-Levenshtein typo detection with retry-without-penalty

**Code quality (from /simplify):**
- Fix race condition where typo could prematurely end practice session
- Batch N+1 queries in image and picture-match generation steps
- Replace per-word `ORDER BY RANDOM()` with pre-fetched distractor pool
- Move `QUESTION_TYPE_LEVEL` to `constants.py` alongside related mappings
- Move inline imports to top-level, add focus handler debounce

---

## [0.4.0] 鈥?2026-03-24

### Generation Pipeline Quality & Token Reduction

**Pipeline-wide:**
- Switch from Claude Opus to Gemini 3.1 Pro for all text generation
- Add `call_gemini()` text generation function to llm_service
- Apply 15% Lexile offset so scaffolding text is easier than target vocab
- Add 512x512 square image generation with low resolution setting

**Step 1 鈥?Word Lookup:**
- Remove per-word `source_context` from JSON output to save tokens
- Build `source_context` from job metadata instead

**Step 3 鈥?Translation:**
- Rewrite prompt with two strategies: native equivalent for definitions, natural translation for example sentences
- Include term in items list for better context

**Step 4 鈥?Questions:**
- Remove redundant WORD ENRICHMENT step that duplicated Steps 1 and 3
- Pass full definition and `example_sentence` from Step 1 directly
- Simplify output format: flat term + questions instead of nested word array

**Step 5 鈥?Pack Grouping:**
- Add creative writer and curriculum architect roles
- Add `text_type` field (fiction/narrative_nonfiction) to WordPack model
- LLM evaluates word nature and assigns best text type per pack
- Change max words per pack from 5 to 6 with balanced distribution

**Step 6 鈥?Primers:**
- Calibrate kid-friendly definitions to target Lexile level
- Add Lexile band guidelines (below 600L through above 1000L)

**Step 7 鈥?Stories:**
- Rewrite prompt for engaging fiction and narrative non-fiction
- Fiction: high-stakes show-don't-tell scenes
- Narrative non-fiction: fascinating hooks and real-world contexts

**Step 8 鈥?Images:**
- Square 1:1 aspect ratio prompt for vocabulary cards
- Low resolution (512x512) for faster generation

---

## [0.3.1] 鈥?2026-03-14

### Pipeline & Image Fixes

- Auto-approve generated images, skip manual review step
- Update image generation model to `gemini-3.1-flash-image-preview`
- Clear existing words before running generation pipeline (prevents duplicates on re-run)
- Fix Gemini API call: combine system and user prompts when user_prompt is empty

---

## [0.3.0] 鈥?2026-03-13

### Student Dashboard Polish & Practice UI

- Per-tier gradient badges (Bronze/Silver/Gold/Platinum/Diamond)
- Flame/snowflake icons for streak and freeze stats
- Freeze info popup explaining streak freeze mechanic
- Fix settings panel button styles overridden by global CSS
- Practice session CSS rewrite to match mockup (gradient header, rounded cards, feedback chips)
- StudentNavbar added to practice session route
- LLM call logging to `temp/llm_logs/`
- Fix: preserve completed pack progress when re-assigning word sets

---

## [0.2.0] 鈥?2026-03-01

### Complete Generation Pipeline & Practice Bug Fixes

- 8-step AI content generation pipeline (word lookup, dedup, translations, questions, packs, primers, stories/cloze, images) with resume support
- Incremental word addition to existing generated word sets
- Generation wizard with live status polling and review/approve UI
- Fix spaced repetition: exclude already-answered words from session and dashboard due count
- Fix teacher roster due count to match student view (filter by READY status)
- Add Vite proxy for `/media` to serve generated images in dev

---

## [0.1.1] 鈥?2026-02-28

### Admin Generation UI (Phase 5)

- Generation wizard, job progress monitor, and content review pages
- Backend endpoints for fetching generated content and bulk-approving images

---

## [0.1.0] 鈥?2026-02-28

### Full-Stack Rebuild (Phases 1鈥?)

- Initial full-stack rebuild of Vocab App V2
- Django backend with REST API
- React frontend with Vite
- User management (teachers, students, groups)
- Word set CRUD and assignment workflow
- Spaced repetition practice engine
- Student and teacher dashboards
