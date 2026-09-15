# Code Review — 2026-07-19

Full-project review: all backend Python (~17.5k LOC excl. tests), full frontend (~7.4k LOC), test suite (~10k LOC, 568 tests), config/deployment. Doc precedence applied (newer wins): `AGENTS.md` (2026-07-19) > `docs/architecture-decisions.md` (2026-07-04) > `docs/PROJECT_CONTEXT.md` / `BETA_IMPROVEMENTS.md` (2026-07-03).

Overall: the architecture is sound and the documented "hard rules" are mostly honored in code. Weaknesses cluster in **concurrency/atomicity, async-job lifecycle, and input validation**.

Status legend: ✅ fixed · ⏳ deferred (listed at the end)

---

## Critical

1. ✅ **`restart_pipeline_from_step` never resets `last_completed_step` — failed restart + resume marks a gutted job COMPLETED.** `orchestrator.py:471-553` clears all outputs for the rerun range (questions, primers, packs → cascading novels/cloze) but leaves `last_completed_step` at its pre-restart value (often `INFOGRAPHIC_IMAGE`). If the first restarted step exhausts retries, `resume_pipeline` computes `remaining_steps = []` from the stale value and marks the now-empty job COMPLETED. Fix: set `last_completed_step` to the step before `start_step` when clearing.

## High

2. ✅ **Login rate limiting illusory** — `LoginRateThrottle` extends `AnonRateThrottle`; with `NUM_PROXIES` unset DRF keys the throttle on the entire client-supplied `X-Forwarded-For` string. Rotating XFF = unlimited password guesses (`user_views.py:13-14`; confirmed against DRF 3.16.1 `throttling.py:23-40`). Fix: `'NUM_PROXIES': 1` (+ nginx should overwrite XFF, not append).

3. ✅ **`apply-bonuses/` unbounded XP faucet** (`practice_views.py:568-587`). `session_id` client-chosen and optional — replaying with fresh ids (or none) grants `min(max_focus_streak,10)` XP per call forever; `max_focus_streak` client-supplied, never validated. Fix: require `session_id`, atomic claim, cap bonus XP per user/day.

4. ✅ **Stuck-RUNNING = permanent 409 for edit/redraw/audio.** Busy-guards check `RUNNING` set by daemon threads; every `systemctl restart vocab` kills them mid-flight, and `_run_page_image_edit`/`_run_page_image_redraw` only catch OpenAI exceptions (storage/DB failure propagates) → page/novel/infographic 409s forever (`generation_views.py:956-1163,1210-1235,1485-1536`; `audiobook/generator.py:66-73`). Stale sweeper only covers pipeline jobs. Fix: sweep stale RUNNING rows in status polls; wrap whole worker bodies in `except Exception` → FAILED; set RUNNING synchronously under row lock before spawning.

5. ✅ **Stale COMPLETED substep logs defeat log-authoritative resume** (`graphic_novel_script.py:63-140`, `step_infographic.py:142-185`). Logs append-only; a failed mid-chain restart leaves an overwritten *unvalidated* artifact + stale COMPLETED log → next pass feeds garbage into the final script. Fix: delete/supersede logs for substeps ≥ start index at engine start.

6. ✅ **Manual substep-restart can delete the published candidate** — engine's `filter(candidate_index=...).delete()` has no `is_selected` guard; only pipeline-resume skip-guard protects published content. Related: GN testing-restart clear deletes selected candidates and *all* cloze incl. promoted, but not substep logs/artifacts (so it also doesn't actually regenerate); infographic branch preserves promoted cloze — unintended asymmetry (`orchestrator.py:143-168`). Fix: 409/skip on selected; mirror the promoted-cloze preservation.

7. ✅ **Generation wizard crashes on every current job** — `GenerationWizard.jsx:200` `q.options.map(...)` unguarded; sentence-write questions carry *object* options, returned raw by both content endpoints. `GenerationReview.jsx` already handles both shapes.

8. ✅ **`QUESTION_GEN` testing-clear deletes sentence-write questions too** (`orchestrator.py:109-112`) — solo restart (`include_subsequent=False`) regenerates only regular questions and marks COMPLETED: SW questions silently gone.

9. ✅ **No HTTP timeout on native `genai.Client`** (`tts_client.py:41-45`, `llm_service.py:277`) — per-request `timeout=None` disables httpx timeouts; a stuck call hangs the daemon thread forever (→ finding 4). Fix: `HttpOptions(timeout=...)`.

10. ✅ **Answer replay defeats SRS** (`practice_service.py:299-516`) — any known `question_id` for a READY word re-scorable non-retry up to the daily cap; no due-ness check. Related race: daily-limit count check runs *before* the user-row lock (`practice_service.py:346-355`) → K parallel submits overshoot by K−1. Fix: reject non-retry submits when `next_review_at` beyond serve cutoff; move count after `select_for_update`.

11. ✅ **GN reader leaks audio on page turn** (`GraphicNovelReader.jsx:42-56`) — `key={audioUrl}` remounts `<audio>`; the effect pauses the *new* element; the old one (GC-rooted while playing) narrates over the new page. Auto-read defaults ON.

12. ✅ **Tests write into real `temp/generation_artifacts/` and `backend/media/`** — no fixture redirects either; confirmed damage: `temp/generation_artifacts/job_1/` now holds test-fixture content (real job_1 artifacts destroyed), `backend/media/graphic_novels/p.png` is a test artifact. Fix: autouse fixtures redirecting artifact root + `MEDIA_ROOT` to `tmp_path`; delete leaked files.

13. ✅ **Roster dashboard loads every incorrect answer ever for the whole roster** (`dashboard_service.py:210-218`), truncates to 30/user in Python. Same unbounded pattern in `get_student_progress` §4 (`:97-112`). Fix: window function / bounded subqueries.

## Medium

14. ✅ **Answer leak in serve payload** — `QuestionSerializer` ships `explanation`, `example_sentence`, `correct_answer_is_term` pre-answer (`serializers.py:137-141`); answer readable in raw API response for word-answer MC types. Fix: strip in serve context (submit response already returns them post-answer).

15. ✅ **Anthropic fallback dead** — `call_anthropic` `max_tokens=600000` (non-thinking) exceeds every Claude model's cap (64–128k) → hard 400 (`llm_service.py:122`).

16. ✅ **`LLMConfigSet` activation race** — deactivate-others + save without transaction/lock → two or zero active sets; `get_active_set` silently falls back to lowest-position set, masking misconfig (`llm_config_views.py:166-176`, `llm_config_service.py:39-45`).

17. ✅ **Job-creation race** — `TriggerGenerationView` check-then-create unlocked → double-click spawns two pipelines on one word set (`generation_views.py:432-497`). Also: edit/redraw/audio busy-checks non-atomic; `generate-audio` doesn't set RUNNING before spawning → double paid work.

18. ✅ **Audiobook "selected candidate only" not enforced** in view or UI (`generation_views.py:1466`) — TTS spend burnable on all 3 candidates.

19. ⏳ **`UserAnswer.question` CASCADE** — intentional question-wipe on QUESTION_GEN restart destroys answer history incl. `judge_result` (`models.py:275`). Deferred: needs archive/soft-delete design.

20. ✅ **Translations attach to `definitions.first()`, not the dedup-matched definition** (`step_translations.py:70`) — wrong-sense translations for multi-definition words; same bug class as the 2026-07-03 dedup fix.

21. ✅ **`Level` unique_together with nullable `curriculum`** unenforceable in MySQL → duplicate `(NULL,name)` rows → `MultipleObjectsReturned` 500; update path ignores `instance.curriculum` (`serializers.py:275-290`, `models.py:342-344`).

22. ✅ **Per-worker caches** — `sw_judge_calls` budget + judge circuit breaker are per-process under LocMemCache → ~4× documented bound on the 4-worker prod box; failure counter not atomic. Fix: atomic add/incr (documented as per-worker approximation).

23. ✅ **Selection not gated on completeness** — selecting a candidate with empty staged cloze silently wipes the pack's active cloze in a 200 response (`graphic_novel_selection_service.py:50-79` + infographic twin). Fix: 400 when incomplete.

24. ✅ **Validator cluster** (GN/infographic): script-coverage substring matching false-PASSes ("art" in "start"); router rejects page counts the pipeline would override anyway (burns all 3 attempts); infographic glossary check false-FAILs on legit captions ("the art-room glowed" for term "art"); team validator doesn't enforce offered coin-flip options; final-script `page_number` sequence unchecked → cryptic IntegrityError at persist.

25. ✅ **`duration_seconds=0` → `fast_correct`** — inflates intervals/learning speed for missing telemetry (`practice_service.py:257-275`); view comment claims out-of-range → solid bucket, false at the low end.

26. ✅ **`request_generation` missing ownership check** — teacher B can flip teacher A's public set to GENERATION_REQUESTED, locking the owner out (`teacher_views.py:285-306`).

27. ✅ **Student passwords unvalidated** — `AUTH_PASSWORD_VALIDATORS` configured but never invoked (create/PATCH-reset/bulk).

28. ✅ **Frontend**: no mid-session 401/403 handling (session expiry → misleading "check your connection"); GN swipe also toggles vocab panel; `GenerationJobStatus` dies permanently on one poll error; CommandCenter refetches whole roster on every row click; `AssignSetForm` renders "no published content" blocking state on a network error; `GenerationReview` doesn't refresh promoted cloze after select; audio status poll stops during voice-director phase; `GraphicNovelPageEditor` poll stale closure + overlapping intervals.

29. ✅ **N+1 / unbounded queries** — word-set list `word_count` per row; word-set detail 2 queries/word; assignment per-student×per-word `get_or_create` (~1.8k queries); frequent-mistakes per-row word lookups.

30. ✅ **Audio integrity** — stitch splices clips with mismatched rate/channels without validation (silent corruption); regen leaves orphaned WAV/MP3s on the 3.6 GB box; voice-director cache never invalidates on script edit (tags misalign); `sw_attempts` single session slot resets the server revision cap when questions interleave.

31. ✅ **Test gaps on hard rules** — lexile-NULL inclusion untested; assign content-type 400 guards untested; login throttle untested; back-to-back SW untested; `test_graphic_novel_one_to_one_pack` codifies the pre-candidate model.

## Low

32. ✅ **Validation → 500s**: non-numeric `pack_id`/`question_id`/`start_time` → uncaught `ValueError`/`TypeError`; `candidate_index` not range-checked (junk 4th+ candidates); `words` list, pack label/order, bulk-student rows, `input_words` shape unvalidated.

33. ✅ **Stuck states/misc views**: `select-image` no RUNNING guard (clobbered by in-flight worker); substep status derivation relies on unordered queryset; `_audio_row_payload` returns stale WAV after FAILED regen; per-page regen doesn't reject review pages; speech-less pages left PENDING forever (comment claims COMPLETED-empty); `_normalize_verdict` allows `correct`+empty hints / inconsistent error_type; typo-only interaction grants streak; typo flag not restored on 429; `LLMConfigSet` activate truthiness (`"true"`/`1` ignored); bulk step-config PUT non-atomic + missing rows silently skipped; `get_active_set` docstring lies (never None while sets exist).

34. ⏳ **Dead/misleading code** (partially fixed): `metadata['beat_sheet']` never persisted; `ApproveGenerationJobView` no-op stub; `_expected_page_count_from_summary`, `_call_llm_releasing_db`, unused `model=` retry kwarg, `generateMessage` state, `TeacherStudentDetailView`, `users/views.py` stubs; `channel` column (documented dead).

35. ✅ **UX/pedagogy**: daily limit/streaks roll at UTC midnight (08:00 Beijing for zh-CN students) — documented, deferred; missed words can't resurface same-day (`MIN_REVIEW_INTERVAL_DAYS=1`) — deferred (pedagogical decision); retry-submit failures silent; dead settings gear on practice page; welcome message `Math.random()` at render; translation-visibility timer stacking; accordion loading race; modal a11y (Escape/focus) except ClozeQuiz exemplar.

36. ✅ **Ops**: `anthropic`/`google-genai` unpinned in `requirements.txt`; LLM log timestamps collide within a second + signed image URLs written to disk; `temp/llm_logs`/artifacts unbounded (BETA #17, still open); `Translation.object_id` PositiveIntegerField vs BigAutoField PKs — deferred (harmless until 4.2B rows); embedding service no retry + stale "Qwen 2.5" docstring.

37. ✅ **Test hygiene**: `GraphicNovelFactory.is_selected=True` default fights hidden-until-published invariant; stale `qwen2.5` embedding version string; suite runs against real MySQL with no note; stray tests in wrong classes; `mock_anthropic` naming leftovers.

## Doc-vs-code contradictions found

- `AGENTS.md` "selected candidate never deleted by a resume" — true only for pipeline resume; manual substep restart + GN testing restart both deleted published candidates (fixed, #6).
- `AGENTS.md` "apply-bonuses idempotent per session_id" / "cap not spoofable" / judge budget — weaker in reality: client-chosen ids, interleave-reset session slot, per-worker caches (fixed/mitigated, #3/#22/#30).
- `AGENTS.md` cloze select "sets both FKs NULL" — implementation *copies* staged rows into new double-NULL rows (mechanism differs, behavior fine).
- `AGENTS.md` "each substep retries 3× internally" — actually 3 total attempts (1 + 2 retries).
- `BETA_IMPROVEMENTS.md` stale both directions: #3 login throttling "Done" but bypassable (fixed, #2); #10 LOGGING now exists; #19 cookie text predates `COOKIE_SECURE`.
- Watchdog constant 1800s vs "15 minutes" in user-facing texts (`generation_views.py`) — fixed.
- README wizard "pipeline/questions-only/instructional-only modes" — no such mode selector exists.
- Migrations 0038/0040 carry `# Generated by Django 6.0.5` headers; runtime is Django 5.2.7 — environment drift.

## Verified solid (no action needed)

Cloze double-FK filter correct at every read/promote site; lexile-NULL questions included everywhere; submit-path row locking (`select_for_update(of=('self',))` on MySQL 8) and XP/streak atomicity correct; admin/role enforcement total (all 27 generation + LLM-config endpoints); substep-restart claim protocol matches docs; persist + cloze promotion atomic with coverage raises; `makemigrations --check` clean; no XSS surface in frontend; sentence-write judge hardening/normalization rigorous; step-order copies across all 5 files in lockstep; 568-test suite contract-faithful (dict-returning LLM mocks, no network).

## Deferred items (not fixed in this pass)

- #19 `UserAnswer` CASCADE on question regen — needs archive/soft-delete design decision.
- UTC-midnight daily boundaries (streaks/limits) — needs product timezone decision for the student base.
- `MIN_REVIEW_INTERVAL_DAYS=1` same-day resurfacing of missed words — pedagogical decision.
- Pagination on list endpoints, global throttling, health check, DRF exception handler, Docker, frontend tests, LLM log retention — already tracked in `BETA_IMPROVEMENTS.md`.
- Dead-code cleanup (#34 leftovers), accessibility overhaul (modal wrapper, keyboard operability), `Translation.object_id` type widening, orphaned-file cleanup job (noted in #30 fix but no retroactive GC).
