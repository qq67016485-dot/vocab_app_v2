# AGENTS.md

## Project Overview

Grade 2–8 vocabulary learning web app with AI-generated instructional content, spaced repetition practice, and role-based access (admin, teacher, student). Target audience: ages 7–14, ESL learners.

Full architecture detail (endpoint payloads, field semantics, prompt-design rationale, migration history) lives in `docs/architecture-decisions.md` — consult it before modifying a subsystem; this file is the compressed summary. Keep both in sync when you change architecture.

## Tech Stack

- **Backend**: Django 5.2 + DRF 3.16, Python, MySQL (driver `pymysql`, registered as MySQLdb in `config/__init__.py` — do NOT add `mysqlclient`)
- **Frontend**: React 19 + Vite 7, plain CSS with theme system
- **LLMs**: Gemini (text + graphic novel scripts), OpenAI GPT-Image-2 (images), Qwen3 embeddings (SiliconFlow). Anthropic SDK wired for fallback; no active step uses it.
- **Auth**: Session-based with CSRF tokens

## Project Structure

```
backend/          Django project
  config/         Settings, URLs, authentication
  users/          User models & auth views
  vocabulary/     Main app (models, views, services, prompts)
    services/
      generation/           # 11-step AI content pipeline (modular package)
        orchestrator.py     # run/resume/restart pipeline
        step_word_lookup.py # Steps 1-2: lookup + dedup
        step_translations.py# Step 3
        step_questions.py   # Step 4
        step_sentence_write.py    # Step 5: sentence-writing questions
        step_packs.py       # Steps 6-7: primers + packs
        step_graphic_novel.py     # Steps 8-9 facade — re-exports from the 4 modules below
        graphic_novel_helpers.py  # Formatting, artifact I/O, substep runner
        graphic_novel_validators.py
        graphic_novel_script.py   # script substeps + restart engine
        graphic_novel_images.py
        step_infographic.py       # Steps 10-11: infographic (3 candidates)
        content_reuse.py    # Cross-wordset reuse of word-level content (Lexile window)
        helpers.py          # Shared LLM wrappers, logging
        llm_config_service.py # Cached DB lookup for per-step model/site config
        constants.py        # Models, step order, config
      generation_pipeline_service.py  # Backwards-compatible shim (re-exports)
      audiobook/            # On-demand read-along TTS (events/voices/tts_client/stitch/encode/generator/voice_director)
      canon_service.py      # Lexi Legends runtime canon loading
      llm_service.py        # Gemini + Claude + OpenAI API wrappers
      embedding_service.py  # Qwen3 embeddings for dedup
  tests/          pytest test suite (tests/users/, tests/vocabulary/)
  data/canon/     Lexi Legends runtime canon
  media/          Generated images
frontend/         React + Vite
  src/pages/      Role-based page components
  src/components/ Reusable UI components
    practice/     Per-question-type renderers split out of PracticeView (Choice/SentenceWrite/Scramble/CorrectFeedbackBlock)
  src/context/    UserContext, ThemeContext
  src/api/        Axios config with CSRF interceptor
docs/             Architecture docs, changelogs (new entries → changelog_after_July_20.md; CHANGELOG.md is a read-only archive), feature plans
```

## Development Commands

```bash
# Backend
cd backend
pip install -r requirements.txt
pip install -r requirements-dev.txt
python manage.py runserver 8001

# Frontend
cd frontend
npm install
npm run dev          # Dev server on port 5174

# Tests
cd backend
pytest                     # Run all backend tests
pytest tests/vocabulary/   # Main app test directory (also tests/users/)

# Lint (ESLint 9 flat config: frontend/eslint.config.js)
cd frontend
npm run lint
```

## Configuration

Backend requires `.env` (see `.env.example`):
- `DATABASE_URL` — MySQL connection string
- `GEMINI_API_KEY` / `GEMINI_BASE_URL` — text LLM. If base URL set, `call_gemini` routes through an OpenAI-compatible proxy; value must be the API root **without** `/chat/completions` (the SDK appends it)
- `GEMINI_TTS_API_KEY` / `GEMINI_TTS_BASE_URL` / `GEMINI_TTS_MODEL` — audiobook TTS. Separate config because audio needs the **native** generateContent API (a text proxy won't serve it). Key falls back to `GEMINI_API_KEY`; empty base URL = call Google directly; model defaults to `gemini-2.5-pro-preview-tts`
- `ANTHROPIC_API_KEY` / `ANTHROPIC_BASE_URL` — used when a step routes through an Anthropic site
- `OPENAI_API_KEY` / `OPENAI_BASE_URL` — GPT-Image-2 images
- `QWEN_API_KEY` — Qwen3 embeddings (SiliconFlow)
- `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`
- `COOKIE_SECURE` — marks session/CSRF cookies HTTPS-only. Default `False`; driven by this var, **not** `DEBUG` (a Secure cookie over plain HTTP is dropped by the browser → every authed request 403s). Set `True` only behind TLS. Prod runs HTTP, so it stays `False` there.
- `REST_FRAMEWORK['NUM_PROXIES'] = 1` — the login throttle keys on the nginx-provided client IP (last XFF hop); without it DRF keys on the full client-supplied XFF chain and the throttle is spoofable.

Which keys are actually needed depends on sites configured in the LLM Config admin page (`LLMSite` stores env-var names, resolved at runtime). `requirements.txt`: `pymysql` + `anthropic` + `google-genai` + `lameenc` (WAV→MP3, pure wheel — no ffmpeg). Frontend dev server proxies `/api` and `/media` to `localhost:8001`.

## Production Server

Live at **http://106.52.164.47** (Tencent Cloud, Ubuntu 24.04, 2 vCPU / 3.6 GB).

- nginx → serves `frontend/dist/`, proxies `/api` + `/admin` to gunicorn, serves `/media` + `/static`
- gunicorn (4 workers) via `unix:/run/vocab/vocab.sock`, systemd unit `vocab.service`. **Must run threaded workers** (`--worker-class gthread --threads 8`): the sentence-write judge does a 2–10s synchronous LLM round-trip in-request; sync workers would stall the box
- MySQL 8, database `vocab_app`, user `vocab`@localhost
- Static: `backend/staticfiles/` (run `collectstatic` after changes). Media: `backend/media/` (persistent — do not delete)

**Redeploy after code change** (on server, from `~/vocab_app_v2/backend`):
```bash
source venv/bin/activate
python manage.py migrate                   # if migrations changed
python manage.py collectstatic --noinput   # if static files changed
sudo systemctl restart vocab
```
Frontend: build locally (`npm run build`), then `scp -r frontend/dist ubuntu@106.52.164.47:~/vocab_app_v2/frontend/dist`.

**Server quirks**: GitHub clone unreliable — use `scp` from Windows. nvm blocked; Node via NodeSource apt. Socket must be `/run/vocab/vocab.sock` (not `/run/vocab.sock`). `chmod o+x /home/ubuntu` so nginx can traverse.

**Batch content generation** (24/7 unattended): `manage.py enqueue_generation --ids-file FILE` bulk-creates PENDING `GenerationJob` rows (idempotent; starts nothing), and `manage.py run_generation_queue` (the `vocab-generation.service` ExecStart, a separate process from gunicorn so web redeploys don't kill pipelines) claims PENDING jobs and runs them in-process. The runner counts ALL RUNNING jobs (including web-triggered) toward concurrency — don't trigger generation from the web UI during a batch. Transient-classified failures auto-resume with capped backoff (budgets persisted in `backend/data/generation_queue_state.json`, gitignored); a global outage breaker freezes the queue after N consecutive transient failures. Monitor: `journalctl -u vocab-generation -f`. Full detail: `docs/PLAN_batch_generation_queue.md`.

## Hard Rules (violations cause real bugs)

- **Active cloze reads must filter `novel__isnull=True, infographic__isnull=True`** (both FKs). Filtering only `novel` leaks staged infographic cloze to students. Staged cloze has exactly one FK set; promoted/active has both NULL.
- **Questions without `lexile_score` must be included** in practice/dashboard queries — never filter them out.
- **Serve-excluded questions are never served**: `is_serve_excluded=True` must be filtered everywhere in `NextPracticeWordView` — level pool, any-question fallback, and the has-suitable-question EXISTS probe (a word whose questions are all excluded is not due-eligible rather than 404ing).
- **Never exact-string-match LLM output**: character names vary across substeps ("Mr. Vidal" vs "groundskeeper Mr. Vidal") — match on distinctive name tokens (`_significant_name_tokens`). Cloze blanks vary in underscore count — use regex.
- **`call_gemini` / `call_anthropic` always return parsed JSON dicts, never strings** (forced JSON mode). Steps wanting prose must request named JSON fields; string methods on the result raise.
- **Prompts use soft guidance, not rigid mandates** — reserve hard limits for measurable constraints. Vocab words must stay semantically true to the story's resolution (no debunked labels/red herrings).
- Syllable breaks only insert middle dots into the exact spelling, never phonetic respelling ("sim·i·le" not "sim·i·lee"); `_sanitize_syllable_text` enforces on save.
- Step order + GN substep order are duplicated across 5 files (generation `constants.py`, `GenerationJobStatus.jsx`, StepKey enum, `generation_views.py`, PROJECT_CONTEXT) — keep in lockstep.
- **Selected GN/infographic candidates are immutable + selection is completeness-gated**: substep-restart views 409 on `is_selected=True` (engines raise ValueError as backstop); `select/` 400s unless the candidate is complete (GN: story pages + review page + page_count match + staged cloze; infographic: poster image + staged cloze).
- **Analytics logs stay out of `UserAnswer`**: near-miss typo attempts go to `TypoAttempt`, scheduling records to `SchedulingDecision` — an extra `UserAnswer` row would pollute daily-limit counts, session dedup, dashboards, learning patterns, and timing baselines.

## Architecture Summary

### Generation pipeline
- Modular package `vocabulary/services/generation/`; `generation_pipeline_service.py` is a re-export shim. 11 steps with per-step resume; `_reconstruct_context` rebuilds `words_data` from the WORD_LOOKUP log snapshot when dedup didn't complete. `restart_pipeline_from_step` resets `last_completed_step` before clearing (a failed restart no longer leaves resume reading COMPLETED over deleted content); its clears preserve content owned by other steps or live publications (sentence-write questions, selected novels + promoted cloze, selected infographics).
- Per-step dispatch: `[primary ×3, fallback ×1]` attempt list from `LLMStepConfig`; a recoverable attempt failure writes a transient FAILED log whose `output_data` carries `retry_message` + structured retry fields.
- `GenerationJob.content_types` (JSON, default `['graphic_novel']`) gates which formats a job generates; orchestrator skips steps of absent types. Wizard offers GN/infographic checkboxes.
- Dedup: cosine ≥ 0.90 on Qwen3 embeddings; `find_duplicate_definition` returns the **matched WordDefinition** (never snapshot an arbitrary sibling). Per-word persist is atomic (embedding fetched before the transaction); resume reuses attached words without re-embedding. Translations join on a per-object `term` field and attach to the snapshot-matched definition (`resolve_definition`).
- **Cross-wordset reuse** (`content_reuse.py`): word-level steps (QUESTION_GEN, SENTENCE_WRITE_GEN, PRIMER_GEN, TRANSLATION) skip words a prior job covered within ±`CONTENT_REUSE_LEXILE_TOLERANCE` (0.15) of this job's content Lexile, with per-step coverage rules; steps take `allow_reuse`, and `restart_pipeline_from_step` passes False (its clear removes only this job's rows — reuse would silently defeat a rerun). Pack-level steps never reuse. Preflight: `manage.py estimate_generation_reuse --ids-file FILE`.
- Question gen: batch = 2 words/call, idempotent per word (resume skips covered words); restart-from-QUESTION_GEN deletes all questions first (intentional full regen). A batch **fails** on a silently dropped word or unmapped `question_type`; batches are structurally validated before persisting (`_first_invalid_question`: correct answer among options, options unique) and regenerated in place up to 3 attempts.

### Graphic novels (steps 8–9)
- **3 candidates per pack** (`candidate_index`), each from an independent full workflow. Admin publishes via `POST /api/graphic-novels/{id}/select/` → `is_selected` + promotes that candidate's staged cloze. **No auto-select** — pack stays hidden from students until published. Selection is completeness-gated; losing candidates kept hidden.
- Single engine `restart_graphic_novel_from_substep(...)`; `_step_graphic_novel_script` loops packs × candidates, skips complete ones, resumes from the first substep lacking a COMPLETED log (the log is authoritative — artifacts write before validation; prior artifacts load only with their COMPLETED log, checked BEFORE the existing novel is deleted). A **selected candidate is never deleted by a resume**; persist is atomic; cloze joins pack words by term OR correct_answer with a coverage raise. The engine refuses (and the views 409) on `is_selected`, and purges the candidate's substep logs ≥ the start substep before re-running. Artifacts: `temp/generation_artifacts/job_{id}/pack_{id}_{slug}/cand_{i}/`.
- 6 Gemini substeps per candidate: team selector → router → scorer → cloze (`gn_cloze_gen`) → beat sheet → final script; system/user prompt split; 3 internal retries on the primary site only. World-context preamble (`prompts/graphic_novel_world_context.txt`) injected at runtime.
- Page count is deterministic from pack word count (`page_count_for_word_count`: ≤4 words → 5, else 6); the LLM's `page_count` is overridden.
- Substep restart: `POST /api/generation-jobs/{id}/restart-substep/` (`pack_id`, `substep`, optional `candidate_index`) — reruns from that substep, then orphan-fills ALL packs before marking COMPLETED. Job claimed atomically on every entry path (`_claim_job_for_restart`; views pass `already_claimed=True`).
- Story rules: Lexi Mini summons hard-capped 0–1/story; every vocab item needs a `pedagogical_anchor`; `complexity_budget` caps locations (page-count-aware) + ≤2 secondary characters; page 1 establishing panel; final page tension-before-resolution. Prompt JSON schemas put rationale/planning fields before decision fields (chain-of-thought ordering).
- Images: retry once then stop. Admin per-page **edit** (`POST .../edit-image/`) and **redraw** (`POST .../redraw-image/`), both async (202 + daemon thread, poll `image-status/`); result → `edited_image` + auto-select; every read path uses `display_image`. Students load best-effort JPEG companions (`student_image`); PNG stays source of truth. Backfill: `manage.py backfill_jpeg_images`.

### Infographics (steps 10–11)
- Single-page alternative to GN; mirrors the 3-candidate + admin-select model (`POST /api/infographics/{id}/select/`). Neutral modern-editorial style (data-viz explainer) — explicitly NOT a flashcard grid or children's storybook; no Lexi Legends canon; people de-emphasized.
- 2 substeps per candidate (`ig_design` → `ig_cloze`), attempts `[primary ×3, fallback ×1]` (GN substeps stay primary-only), then one poster render per candidate. The design LLM is art director: picks `layout_mode` (`panorama`/`gallery` — validator-enforced) + per-candidate `color_palette`/`style_prompt` so the 3 candidates diverge.
- Captions must USE each word in a sentence (glossary format rejected); `intro_text` must use every target word; `_mark_vocab_terms` wraps targets in `**markers**` so the image model bolds/accents them.
- Restart: `POST /api/generation-jobs/{id}/restart-infographic-substep/` — same guards as the GN restart (is_selected 409, COMPLETED-log gating, ≥-start-substep log purge); does NOT re-render the poster (re-run INFOGRAPHIC_IMAGE separately).

### Cloze staging & per-assignment content type
- Cloze is generated per candidate (staged) and promoted on selection — see Hard Rules for the FK filter. The active set is shared across content types (last published wins).
- `StudentWordSetAssignment.content_type` (GN/infographic, default GN) set by teacher in `AssignSetForm`; `instructional_service.get_pack_data` serves the chosen type's selected content, falling back to the other published type, then legacy stories.
- Assignment gated on published content: a type is offered only if some pack has an `is_selected` candidate of it; `assign/` POST rejects unavailable types (400).
- Student reader: `InfographicReader.jsx` routed on `story.type === 'infographic'`; widened student shell; Web Speech TTS button per word. Both readers (GN vocab panel + infographic word list) have a per-word "Show Translation" toggle, off by default (2026-08-27) — translations come from the pack payload's primer cards, frontend-only.

### Questions & sentence-writing
- 30 `QuestionType` enum members; the prompts actually generate **16** — 14 choice types from `question_generation_A/B.txt` + 2 sentence-write types (the other 14 are dormant, zero rows). Since 2026-08-27, generated explanations and judge hints must use simple English (short sentences; nothing harder than the target word).
- **Sentence-writing** (SENTENCE_WRITE_GEN) — the only LLM-judged (non-exact-match) type. GUIDED (L4, scenario + starter) and OPEN (L5) variants; OPEN's input carries the word's `guided_scenario` so it takes a different angle. **Guided-only floor**: content Lexile ≤ 600 → OPEN skipped, GUIDED attached to both L4+L5. Rubric anchors in `options`, `correct_answers=[]`; `QuestionSerializer` exposes a student-safe `sentence_write` payload (anchors/model sentence never leak).
- Judge (`services/sentence_evaluation_service.py`, step key `sentence_judge`): injection-hardened; structured correct/almost/incorrect + `error_type` + `hints` (array, hard-capped at 3). **Spelling is graded** (misspelling → `almost`/`spelling`; misspelled target word never `correct`); **grammar is notice-only** (one basic agreement error as an extra bullet, never changes the verdict). Revision loop server-tracked in session, keyed by question_id (Guided 3 / Open 2). Terminal outcomes score via `_classify_response_quality`: `productive_correct` (+5 XP) / `productive_recovered` (fragile) / `productive_missed` (−1, no demotion). Verdict persisted on `UserAnswer.judge_result`.
- **LLM-down = skip**: circuit breaker (3 consecutive failures → 5-min flag) excludes sentence-write types from `NextPracticeWordView`; submit-time failure discards without penalty. No back-to-back sentence-writes on the same word.

### Audiobook (on-demand, selected GN only)
- `GraphicNovelPageAudio` (OneToOne→page): stitched WAV + best-effort MP3 companion (`lameenc`, no ffmpeg); students stream MP3 via `student_audio`; admin review serves WAV.
- `services/audiobook/`: `events.build_page_events` → `voices.voice_for` (stable hero map; narrator gender-contrasts the team; supporting chars hashed into gender-matched pools) → `tts_client.synthesize` (**native** Gemini client using `GEMINI_TTS_*`, 120 s timeout, retries only transient errors) → `stitch` (stdlib `wave`; validates uniform rate/channels/16-bit) → `encode` (MP3). Regeneration deletes old files first.
- Voice director (`voice_director.direct_novel`, step key `audiobook_director`): one LLM call per novel → per-speaker Audio Profiles + inline TTS tags, cached in `novel.metadata['voice_director']` (sha1 of the events payload — script edits re-direct); slow-pace tags forbidden and stripped on read; failure degrades to bare transcript.
- API (admin, async): `POST /api/graphic-novels/{id}/generate-audio/` (400 unless selected) + `audio-status/` poll; per-page `regenerate-audio/` (400 on review pages). Busy claim set synchronously under `select_for_update`; polls sweep RUNNING rows older than 30 min → FAILED. Student UI: per-page Listen + Auto-read toggle (localStorage `gnReaderAutoplay`). Backfill: `manage.py backfill_audio_mp3`.

### LLM configuration
- `LLMSite` + `LLMStepConfig`: per-step site/model (primary + fallback), provider types `gemini_native` / `openai_compatible` / `anthropic`, keys as env-var references. Admin UI `/teacher/llm-config`. `llm_config_service.get_step_config(step_key)` — 5-min cache, invalidated on edit.
- **3 `LLMConfigSet` profiles**, exactly one active (app-enforced — MySQL lacks partial unique indexes; activation is atomic). Pipeline reads the active set; step-config API is set-scoped (`?set=<id>`, default active); admins can rename/activate but not create/delete. New step keys are seeded into all 3 sets by migration (precedents: 0033/0037/0039).
- `call_gemini`/`call_anthropic` accept `api_key`/`base_url` overrides; both return dicts (see Hard Rules). Anthropic `max_tokens` capped at 64000; native Gemini + TTS clients have explicit HttpOptions timeouts (600 s / 120 s — SDK default is no timeout).

### Admin review & job status UI
- `GenerationReview.jsx`: GN candidates as compare strip + detail (`PackGraphicNovels`); infographics via `PackInfographics`. Review endpoints return `graphic_novels`/`infographics` (all candidates, each with its cloze) + `graphic_novel`/`infographic` (selected or null); page payloads include `audio_url` (COMPLETED WAVs).
- The question tab (2026-08-27) shows per-question QA: shrunk CTT `difficulty_index`/`discrimination_index` + `qa_flags` (written by `manage.py compute_item_stats` — min-n guards, flag-for-review only, never auto-hides) and a Flag/Unflag button → `POST /api/questions/<id>/flag/` (admin; toggles `is_serve_excluded` — flag-to-hide, not delete). Deferred: batch LLM answer-verification (`verification_mismatch` flag, `BETA_IMPROVEMENTS.md` R1).
- `GenerationJobStatus.jsx` derives step status from `job.status` + `last_completed_step` — NOT the latest per-step log (a mid-retry step shows RUNNING + amber "Retrying"). The logs API exposes `output_data` only, so retry detail the UI needs must live there. The status view doubles as the stale-job watchdog: no log activity for 30 min → job FAILED (word set back to TO_GENERATE), and stale RUNNING GN-page + infographic image rows are swept → FAILED.
- Multi-substep steps (GN script: 6; infographic: 2) render per-candidate accordions via shared `renderSubstepAccordion`; per-substep restart buttons post to `restart-substep` / `restart-infographic-substep`.

### SRS / student-facing
- Response-quality-aware scheduling (fast/solid/slow affects intervals). Words go PENDING → READY on pack completion; only READY words enter SRS. Mastery 6–7 hidden from students (shown as "Mastered").
- **Submit-path integrity** (`PracticeService.process_answer`): `daily_question_limit` enforced on submit, not just serve (past cap → 429; retries exempt); non-READY word → 404; a word not yet due is masked-404'd (answer-replay guard). The `UserWordProgress` row (`select_for_update(of=('self',))`) and re-fetched `CustomUser` are locked before the streak/XP read-modify-write; the daily-limit count runs under the user-row lock. Client `duration_seconds`/`answer_switches` are clamped; `current_level_name` masked for hidden levels. `apply-bonuses/` requires `session_id` (atomic `cache.add` claim) and caps bonus XP at 30/user/day. Sentence-write judge calls bounded per-day (`sw_judge_calls` cache counter). Serve payload strips `explanation`/`example_sentence` pre-answer (`for_serve` serializer context); type-to-spell is derived client-side (`TERM_ANSWER_MC_TYPES`). Pure-typo submits don't maintain the streak; durations ≤ 1 s fall into the neutral 'solid' bucket. Full detail: `docs/architecture-decisions.md`.
- **Practice instrumentation logs (2026-08-27, migration 0042)**: near-miss typo attempts → append-only `TypoAttempt` (see Hard Rules). Every scored non-retry answer (incl. sentence-write terminal outcomes) also writes append-only `SchedulingDecision` (before/after level + learning_speed, quality rule, post-cap interval, next_review_at, due backlog, reserved jitter fields) for leakage-free decay-model replay. Retries write no SchedulingDecision but DO log TypoAttempts.
- Primer `kid_friendly_definition` is a concise 3–8 word phrase (also the review-page definition source; fallback `WordDefinition` truncated to 8 words). Review page: no story title, story characters used.
- Frontend `PracticeView.jsx` delegates each question type to `components/practice/` (`CorrectFeedbackBlock`, `SentenceWriteQuestion`, `ChoiceQuestion`, `ScrambleQuestion`). Submit has an `isSubmitting` ref double-tap guard; submit failures show a `submitError` banner (never `setFeedback({error})`, which traps the child in a dead form).

## Testing

- Backend: pytest + pytest-django + factory-boy, run from `backend/`. Frontend: no test framework yet.
- **Manual test seed**: `python manage.py seed_sentence_write_test [--reset]` seeds student `swtest`/`testpass123` with READY guided+open sentence-write questions (no generation run needed); the judge itself still needs a live `sentence_judge` LLM config.
- **Cache must be cleared between tests**: no `CACHES` setting → process-global `LocMemCache`; pytest-django rolls back DB but not cache, so cache-backed DB-derived state leaks (notably `llm_config_service`). `tests/conftest.py` has an autouse `cache.clear()` fixture — keep it. If a test "passes alone but fails in the suite," suspect cross-test state leak; verify the first failure with `pytest -x` before assuming flakiness.
- **Filesystem isolation**: autouse fixtures in `tests/conftest.py` redirect the GN/infographic artifact dirs, `MEDIA_ROOT`, and `LLM_LOG_DIR` to per-test `tmp_path` (a test run once destroyed the real job_1 artifacts). `GraphicNovelFactory.is_selected` defaults False (the hidden-until-published invariant); pass True explicitly for published-state tests.

## Code Conventions

- Backend: Django/DRF patterns — models → serializers → views → services; services hold business logic, views stay thin
- Frontend: functional components with hooks; plain CSS files, 5-theme student system (no CSS-in-JS)
- **Student CSS cascade**: `students.css` declares `@layer legacy,tokens,theme,base,components,pages`; `students/fixes.css` imports LAST in the `pages` layer and intentionally uses `!important` to own themed colors — a state color written in an earlier pages file (e.g. `practice.css`) without `!important` silently loses to fixes.css's neutral base rules. Brand-ish colors derive from `color-mix(in oklab, var(--primary) …)` (never hardcode the default indigo); semantic states (success/amber/danger) stay theme-independent; for small text keep the primary share ≤ ~55% vs near-black (mint/seafoam are the AA-contrast bottleneck). `prefers-reduced-motion` guard lives in `students/base.css`.
- Definition/example translation lookups are centralized in `vocabulary/utils.py` (`get_definition_translation(s)`) — import the shared helper, never add per-service copies
