# Changelog (after 2026-07-20)

All notable changes to Vocab App V2 from 2026-07-20 onward are documented in this file.
The pre-2026-07-20 history lives in [`CHANGELOG.md`](CHANGELOG.md) — that file is now a
read-only archive; do not add entries there.

## [Unreleased] - 2026-08-27 (practice instrumentation + item-quality flags + reader L1 toggle)

### Context
- From the research-review plan (`docs/validated-improvement-opportunities-2026-08-27.md`, Steps 0–3): stop two data leaks the capstone's decay-model evaluation depends on, add item-quality flagging at CTT scope (Assignment 4 Decision 7 — CTT, not IRT), simplified-English feedback rules, and an on-demand L1 translation toggle in both student readers. Batch LLM answer-verification (N3) and the achievements word-bank (T17) were deliberately deferred — see `BETA_IMPROVEMENTS.md` R1/R2.

### Added
- `TypoAttempt` model (migration `0042`): append-only log of near-miss typo attempts, written before the typo early-return in `process_answer` (`practice_service.py`). Deliberately a separate table, not an `UserAnswer` flag — daily-limit counts, session dedup, dashboards, learning patterns, and timing baselines are all untouched. Closes the MNAR gap: longer intervals produce more near-misses, so observed recall was biased upward with elapsed time.
- `SchedulingDecision` model (migration `0042`): append-only per-answer scheduling log (mastery level + `learning_speed` before/after, `response_quality_rule`, post-fragile-cap `intended_interval_days`, `next_review_at`, `due_backlog_size`, reserved nullable jitter fields). Written only for scored non-retry answers, including sentence-write terminal outcomes. Enables chronological, leakage-free replay for the capstone's decay-model evaluation.
- `compute_item_stats` management command: shrunk difficulty `(correct + 8m)/(n + 8)` toward the question-type mean (NULL when n < 5); point-biserial discrimination against leave-one-out ability proxy (n ≥ 10, shrunk toward 0 for 10 ≤ n < 20); writes `qa_flags` (`too_easy` p>0.9 / `too_hard` p<0.2 / `low_discrimination` d<0.2) + `qa_checked_at` on `Question` (migration `0043`); per-question-type aggregate report (stdout + optional JSON); `--gradient` mode prints the L1–L5 delayed-accuracy (≥24h gap) gradient check. Flag-for-review only — never auto-hides.
- `POST /api/questions/<id>/flag/` (admin-only): toggles `is_serve_excluded`. `NextPracticeWordView` excludes flagged questions in the level pool, the any-question fallback, AND the has-suitable-question EXISTS probe (a word whose questions are all excluded is simply not due-eligible instead of 404ing). Generation Review question tab shows per-question p/d values, flag chips, "Excluded" state, and a Flag/Unflag button.

### Changed
- `question_generation_A.txt` / `question_generation_B.txt`: the `explanation` field spec now requires simple, easy English (short sentences, everyday words, never a word harder than the target word). `sentence_judge.txt`: same simplicity rule for hint bullets. Applies to newly generated/regenerated content only; originals backed up to `temp/prompt_backups/2026-08-27/`.
- Student readers: per-word "Show Translation" toggle (off by default) in the GraphicNovelReader vocab panel and InfographicReader word list — the pack payload already carried `definition_translation`, so this is frontend-only (InfographicReader joins structured entries to primer cards by normalized term).

### Removed
- Unreachable reveal-and-move-on branch in `ChoiceQuestion.jsx` (`wrongOptions.length >= choices.length` could never hold — a correct option never lands in `wrongOptions`); replaced with a comment documenting the design (option elimination self-terminates; type-to-spell shows the answer in the read-only reference options).

### Tests
- 32 new backend tests (7 instrumentation in `test_adapted_services.py::TestPracticeInstrumentation` + 25 item QA in `test_item_stats.py`); full suite 736 passed. Frontend lint 0 errors; `vite build` green.

## [Unreleased] - 2026-08-26 (infographic pipeline robustness fixes)

### Context
- An analysis of the infographic pipeline against two external infographic skills (`docs/infographic-pipeline-vs-skills-analysis.md` §4) surfaced five robustness bugs. The worst: a full-step restart from INFOGRAPHIC_DESIGN deleted **published** infographics — the GN clear preserved selected candidates, the infographic clear didn't, despite a comment claiming they mirrored.

### Fixed
- `orchestrator.py` INFOGRAPHIC_DESIGN clear now filters `is_selected=False` — `restart_pipeline_from_step(job, INFOGRAPHIC_DESIGN)` no longer unpublishes live student content. Also recounts remaining infographics + cloze instead of zeroing (mirrors the GN branch).
- `orchestrator.py` INFOGRAPHIC_IMAGE clear resets `image_jpeg` too — `student_image` prefers the JPEG, so a stale one was served in the clear→re-render window.
- `step_infographic.py` `_run_infographic_substep` attempt plan is now `[primary ×3, fallback ×1]` (new optional `fallback_site_config` param, wired at both `restart_infographic_from_substep` call sites) — the configured fallback LLM site was previously never used for `ig_design`/`ig_cloze`, so a down primary hard-failed the step despite a configured fallback.
- `step_infographic.py` design validator now requires `layout_mode` ∈ {panorama, gallery} — an invalid/missing value used to silently render with panorama guidance. (`reading_level` stays unchecked by design.)
- `generation_views.py` job-status stale sweep (30-min no-activity) now also sweeps RUNNING `Infographic` rows → FAILED, mirroring the GN page sweep — a worker restart mid-render no longer leaves a poster displayed as RUNNING forever.

### Deferred
- The dead `edited_image`/`use_edited_image`/`edited_image_jpeg` schema on `Infographic` (no edit/redraw/select-image endpoints exist) — shipping those endpoints is a feature (GN pages are the template), not a bug fix. Tracked in the analysis doc's roadmap.

### Tests
- 7 new tests in `tests/vocabulary/test_infographic.py` (fallback attempt plan ×2, layout_mode validation ×2, design clear preserves selected + counts, image clear resets JPEG, stale sweep); 2 existing failure-path tests updated for the 4th (fallback) attempt. 44 passed in the file; full suite 704 passed.

## [Unreleased] - 2026-07-31 (book-neutral wordset discovery: design + corpus analysis — docs only, no code)

### Context
- Exploratory design session on legal exposure: the current catalog is book-coupled (`WordSet.title` is the book title, `source_text` stores book passages, `Word.source_context` stamps "From {book}"). Owner plans a book-neutral catalog: pre-generated anonymized packs found via search, with no book→content mapping stored anywhere. Nothing implemented yet.

### Added (docs + analysis only)
- `docs/feature_plan/design-book-neutral-wordset-discovery.md` — v2 design doc: five legal design principles; two-tier model (shared platform packs with amortized GN/infographic content vs. private teacher sets with library word-level content only); two-call grounded book lookup (native Gemini grounding client + forced-JSON extraction); gloss-embedding sense disambiguation (Qwen3); TTL query cache (never persist query strings); data-minimization plan (scrub `source_text`/`input_source_*` on job completion, stop stamping `source_context`, log retention); open decisions incl. program-reader trademark sensitivity (Learning A-Z sells adjacent vocab products).
- Corpus analysis of RAZ levels I–Y (`C:\project\wordset_extract\vocab_by_book - final.csv`, 1,212 books) — scripts in `temp/python-tmp/` (`analyze_raz_vocab.py`, report `raz_report.txt`, `estimate_cleanse_drop.py`, `sim_lemmatized.py`): **6,342 unique words** (5,460 lemmatized, −13.9%; 6.7% multi-word entries, 3.1% proper nouns; 64% singletons). Coverage simulation (6-word packs, co-occurrence-seeded, per level): **~2,100 packs at r≈1 / ~4,100 at r≈2 / ~6,150 at r≈3**; 2-pack-union median coverage 100% (levels I–P) / 83–92% (U–Y); 3-pack median 100% everywhere; single-pack ≥60% mathematically impossible for 12+-word glossaries. Pure frequency-greedy packing collapses per-book coverage to ~17% (packs must be co-occurrence-aware); merging adjacent levels saves nothing. Extrapolation for RAZ+Wonders+ReadingExplorer: library ~7–9k words, ~8k packs at r≈2.
- Lemmatization barely changes pack counts (2,066/4,102/6,095 vs raw — packs scale with glossary incidences, not unique words), but shrinks the word-level content library ~14%.

### Notes
- `nltk` (+ wordnet/omw-1.4 corpora) installed into `backend/venv` for this analysis only — deliberately **not** in `requirements.txt`; becomes a real dependency only if the library build / P1 simulation ships.
- P0 legal-hygiene items (serializer scrubbing, `source_context` wipe, source-field nulling) are design-doc §8, not yet code. Related pending item: `BETA_IMPROVEMENTS.md` #17 (log/artifact retention).

## [Unreleased] - 2026-07-31 (sentence-write open variant sees the guided scenario)

### Context
- GUIDED and OPEN sentence-write tasks are generated in separate LLM calls (guided first, then open), and the open call's input carried only term/POS/definition/example — so the two scenarios for the same word could come out near-duplicates (prod example: the "route" guided and open tasks both ask about the trip to school).

### Changed
- `step_sentence_write.py`: the OPEN variant's input JSON now includes each pending word's `guided_scenario` (new `_guided_scenarios_by_word_id` — latest GUIDED row per word, so this run's fresh rows win and resume/reuse falls back to the row practice pooling would serve). Empty string when no guided task exists. No extra LLM calls; the guided input is unchanged.
- `sentence_write_open.txt`: INPUT documents `guided_scenario`; design rule 1 now requires a clearly different situation/angle from the guided scenario when it is non-empty.
- 2 new tests in `tests/vocabulary/test_sentence_write.py` (open input carries the guided scenario + guided input does not; resume path uses the existing guided row). 30 passed in the file.

## [Unreleased] - 2026-07-31 (question-gen structural validation + prompt QC)

### Context
- A review of all 4,159 generated questions against item-writing literature (Haladyna et al. 2002 MC item-writing guidelines; the Savaal question-generation paper; arXiv:2507.05629 LLM retrieval-practice study; Tan et al. 2025 IJATE LLM-AIG scoping review) found structural defects the pipeline never checked: one live question whose correct answer is not among its options (id 2893 — grading is exact-match, so it can never be graded correct), two with duplicated option texts (ids 3569/3570), and the correct answer uniquely the longest option in 37% of items (a cue the client-side option shuffle does not neutralize). The 94.5% option-index-0 positional bias IS neutralized by the client Fisher-Yates shuffle (`PracticeView`) — no action taken.

### Added
- **Structural item validation in question generation** (`_first_invalid_question` in `step_questions.py`): before any row of a batch is persisted, every question must have ≥2 unique options, non-empty `correct_answers`, and every correct answer must appear among the options under grading's exact normalization (`PracticeService.normalize_answer` — strip/lowercase/punctuation). A failing batch is regenerated in place up to `QUESTION_BATCH_MAX_ATTEMPTS = 3` LLM calls (re-rolling the A/B prompt per attempt); exhaustion raises ValueError → FAILED. The in-step loop is required because validation errors are deterministic-classified — the queue runner never auto-resumes them.
- 8 new tests in `tests/vocabulary/test_step_questions.py` (regeneration on missing-answer / duplicate-options, exhaustion-fails-without-rows, helper unit tests incl. punctuation tolerance). 17 passed in the file; 52 neighboring generation tests green.

### Changed
- `question_generation_A.txt` / `question_generation_B.txt`: new Enforcement bullet "All options should have **similar length and specificity**." (targets the 37% longest-option cue; the correct answer may still be the longest when the distractors keep pace). Otherwise hygiene only: the fields list is numbered 1/2/3 again in both files, and a stray `- -` bullet was fixed in B. No other prompt content changed.

### Notes
- No migration, API, or frontend changes. Validation protects new generations only — the 3 known-broken live rows (2893, 3569, 3570) remain in the DB pending a cleanup pass.
- Deliberately not done (the papers argue against): an LLM "make distractors harder" second pass and an LLM item-quality self-judge (Savaal: ambiguity / judge misalignment); 3× overgenerate-and-filter (arXiv:2507.05629) — cost, when deterministic validation catches the same defect class.
- Recorded but unfixed findings: no empirical item-difficulty report (165 `UserAnswer` rows exist); sentence-write GUIDED vs OPEN scenarios for the same word are near-duplicates (separate calls never see each other); legacy jobs 3/4/17/19/20 predate the 0.85 content-Lexile offset (~500 `lexile_score` values on the old convention); the L1–L2 Tier-3 mandate can produce obscure look-alike traps (e.g. "Calvary" vs "cavalry").

## [Unreleased] - 2026-07-20 (batch generation queue)

### Context
- Needed to run content generation for ~200 word sets unattended (24/7) on the production box. The web trigger (`TriggerGenerationView`) spawns daemon threads inside gunicorn workers — every redeploy/OOM silently kills in-flight pipelines and leaves jobs stuck RUNNING. The LLM proxy also has short outages, and the in-step `[primary ×3, fallback ×1]` retries fire back-to-back, so a 10-minute outage used to fail a whole 40-minute job.

### Added
- `manage.py enqueue_generation --ids-file FILE [--content-types ...]` — bulk-creates PENDING `GenerationJob` rows from a word-set ID file (idempotent; skips missing/GENERATED/active-job/empty-word sets; mirrors the web trigger's locked duplicate-guard). Does not start anything.
- `manage.py run_generation_queue` — long-running queue runner (new systemd unit `vocab-generation.service`, `Restart=always`, ExecStart `--concurrency 2 --resume-stale`). Claims PENDING jobs N at a time (`select_for_update`) and runs `run_full_pipeline` in its own process — web redeploys no longer kill batch jobs. Counts ALL RUNNING jobs toward concurrency (don't web-trigger during a batch).
- Three-layer retry for unreliable LLM proxies: (1) existing in-step attempts; (2) per-job auto-resume via `resume_pipeline` for **transient-classified** failures (`classify_error` on `error_message` — 429/5xx/timeout/connection/SDK markers; deterministic errors like validation/completeness never auto-retry) with capped backoff 5/10/20/30… min, budget 8/job; (3) a global **outage breaker** that freezes claims + resume timers 15 min after 3 consecutive transient failures. Budgets persist in `backend/data/generation_queue_state.json` (gitignored); `--resume-stale` resumes jobs stuck RUNNING from a dead process.
- `tests/vocabulary/test_generation_queue.py` — 35 tests (enqueue guards, claim order/concurrency, classification, backoff, exhaustion, breaker, state persistence, stale resume; synchronous-thread seam, no LLM calls). Full suite: 658 passed.

### Notes
- No migrations, no changes to existing web code — deploying is `scp` of the two new command files + the systemd unit; gunicorn restart not required.
- As-built doc: `docs/PLAN_batch_generation_queue.md` (rewritten from the draft plan; lists what was deliberately not built — CSV import, status command, service memory limits).

## [Unreleased] - 2026-07-20 (cross-wordset content reuse)

### Context
- Batch generation covers hundreds of word sets with heavy word overlap. Dedup (step 2) already attached the shared `Word`/`WordDefinition`, but every downstream word-level step regenerated anyway: questions + sentence-writes (their skip checks were scoped to `generation_job=job`), translations (re-paid the LLM call and could misattach to another job's definition via `definitions.first()`), and primers (shared OneToOne row silently overwritten at every Lexile). Pack-level steps (packs, graphic novels, infographics) bind the word combination and still always generate.

### Added
- `vocabulary/services/generation/content_reuse.py` — reuse keyed on the content Lexile (`target_lexile × 0.85`); a prior job's content is reused when its content Lexile is within ±`CONTENT_REUSE_LEXILE_TOLERANCE` (new setting, default `0.15`) of the new job's. Provenance: questions derive it from `generation_job` (NULL-job rows never reused); primers get a new `generated_content_lexile` stamp (migration `0041`; legacy NULL rows regenerate); translations are Lexile-independent, keyed to definition + language.
- Per-step skips: QUESTION_GEN requires full coverage (≥3 choice questions × levels 1–5, sentence-writes excluded) from in-window jobs; SENTENCE_WRITE_GEN additionally requires the same variant mode (guided-only ≤600 vs guided+open — a cross-mode row has the wrong variant set); PRIMER_GEN skips in-window primers; TRANSLATION sends only untranslated definitions. Steps log `words_reused`/`primers_reused`/`translations_reused` in `output_data`.
- `manage.py estimate_generation_reuse --ids-file FILE` — read-only preflight reporting per-set and total reusable words/questions/sentence-writes/primers/translations before a batch run (upper bound: actual reuse still gated on the dedup embedding match).
- `tests/vocabulary/test_content_reuse.py` — 29 tests (window math, per-level coverage, variant modes, primer stamping, translation attach target, step-level skip/regenerate/`allow_reuse=False`).

### Changed
- The four word-level step functions take `allow_reuse=True`; the orchestrator threads it through, and `restart_pipeline_from_step` passes `False` — the manual restart clears only this job's rows, so reuse would otherwise silently defeat an explicit rerun.
- Translations now attach to the `WordDefinition` matching the job's dedup-snapshot text (`resolve_definition`) instead of `definitions.first()`, fixing misattachment on shared multi-definition words.
- Question/sentence-write resume skips are now per-word (a mixed batch sends only uncovered words) instead of deleting and regenerating partially completed batches.

### Notes
- Migration `0041_primercardcontent_generated_content_lexile` — run `migrate` on deploy; no static/frontend changes.
- Reuse was already serve-safe: `NextPracticeWordView` pools questions by word job-agnostically with a per-student Lexile filter, and `UserWordProgress` is per (user, word) across word sets.
