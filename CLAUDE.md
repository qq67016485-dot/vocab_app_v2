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
  tests/          pytest test suite
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
pytest               # Run all backend tests
pytest tests/test_views/ -v  # Specific test directory

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
- `COOKIE_SECURE` — marks session/CSRF cookies HTTPS-only. Default `False`; driven by this var, **not** `DEBUG` (a Secure cookie over plain HTTP is dropped by the browser → every authed request 403s). Set `True` only behind TLS. Prod at `106.52.164.47` runs HTTP, so it stays `False` there.
- `REST_FRAMEWORK['NUM_PROXIES'] = 1` — the login throttle keys on the nginx-provided client IP (last XFF hop); without it DRF keys on the full client-supplied XFF chain and the throttle is spoofable. Student passwords are validated with Django's `validate_password` on create/reset/bulk (was unvalidated).

Which keys are actually needed depends on sites configured in the LLM Config admin page (`LLMSite` stores env-var names, resolved at runtime). `requirements.txt`: `pymysql` + `anthropic` + `google-genai` + `lameenc` (WAV→MP3, pure wheel — no ffmpeg). Frontend dev server proxies `/api` and `/media` to `localhost:8001`.

## Production Server

Live at **http://106.52.164.47** (Tencent Cloud, Ubuntu 24.04, 2 vCPU / 3.6 GB).

- nginx → serves `frontend/dist/`, proxies `/api` + `/admin` to gunicorn, serves `/media` + `/static`
- gunicorn (4 workers) via `unix:/run/vocab/vocab.sock`, systemd unit `vocab.service`. **Must run threaded workers** (`--worker-class gthread --threads 8`, set in the unit's ExecStart): the sentence-write judge does a 2–10s synchronous LLM round-trip in-request; sync workers would stall the box
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

**Batch content generation** (24/7 unattended): two management commands + a dedicated systemd unit `vocab-generation.service` (separate from gunicorn, so web redeploys no longer kill in-flight pipelines — the web trigger's daemon threads still die on worker restart).
- `manage.py enqueue_generation --ids-file FILE [--content-types ...]` — bulk-creates PENDING `GenerationJob` rows for word-set IDs (one per line); idempotent, skips GENERATED sets and sets with an active job. Does not start anything.
- `manage.py run_generation_queue [--concurrency 2] [--resume-stale] [--max-transient-retries 8] [--outage-threshold 3] [--outage-cooldown 15] [--state-file PATH]` — long-running runner (the service's ExecStart) that claims PENDING jobs N at a time and calls `run_full_pipeline` in-process. PENDING `GenerationJob.status` is the queue; the runner counts ALL RUNNING jobs (including web-triggered) toward concurrency, so don't trigger generation from the web UI during a batch.
- Retry policy for unreliable LLM proxies: (1) existing in-step attempts, then (2) per-job auto-resume via `resume_pipeline` for **transient-classified** failures (`classify_error` on `error_message`: 429/5xx/timeout/connection markers) with capped backoff 5/10/20/30… min up to the retry budget — deterministic errors (validation/completeness/schema) are never auto-retried; then (3) a global **outage breaker** that freezes claims + resume timers after N consecutive transient failures. Budgets persist in `backend/data/generation_queue_state.json` (gitignored, written on every transition), so restarts/reboots don't reset them; `--resume-stale` resumes jobs stuck RUNNING from a dead process. Monitor with `journalctl -u vocab-generation -f`.

## Hard Rules (violations cause real bugs)

- **Active cloze reads must filter `novel__isnull=True, infographic__isnull=True`** (both FKs). Filtering only `novel` leaks staged infographic cloze to students. Staged cloze has exactly one FK set; promoted/active has both NULL.
- **Questions without `lexile_score` must be included** in practice/dashboard queries — never filter them out.
- **Never exact-string-match LLM output**: character names vary across substeps ("Mr. Vidal" vs "groundskeeper Mr. Vidal") — match on distinctive name tokens (`_significant_name_tokens`). Cloze blanks vary in underscore count — use regex.
- **`call_gemini` / `call_anthropic` always return parsed JSON dicts, never strings** (forced JSON mode). Steps wanting prose must request named JSON fields; string methods on the result raise.
- **Prompts use soft guidance, not rigid mandates** — reserve hard limits for measurable constraints. Vocab words must stay semantically true to the story's resolution (no debunked labels/red herrings).
- Syllable breaks only insert middle dots into the exact spelling, never phonetic respelling ("sim·i·le" not "sim·i·lee"); `_sanitize_syllable_text` enforces on save.
- Step order + GN substep order are duplicated across 5 files (generation `constants.py`, `GenerationJobStatus.jsx`, StepKey enum, `generation_views.py`, PROJECT_CONTEXT) — keep in lockstep.
- **Selected GN/infographic candidates are immutable + selection is completeness-gated**: substep-restart views 409 on `is_selected=True` (engines raise ValueError as backstop); `select/` 400s unless the candidate is complete (GN: story pages + review page + page_count match + staged cloze; infographic: poster image + staged cloze).

## Architecture Summary

### Generation pipeline
- Modular package `vocabulary/services/generation/`; `generation_pipeline_service.py` is a re-export shim. 11 steps with per-step resume; `_reconstruct_context` rebuilds `words_data` from the WORD_LOOKUP log snapshot when dedup didn't complete. `restart_pipeline_from_step` resets `last_completed_step` to the step before `start_step` when clearing (a failed restart no longer leaves a stale value that resume would read as COMPLETED); its QUESTION_GEN clear preserves sentence-write questions, the GN-script clear preserves selected novels + promoted cloze, and the INFOGRAPHIC_DESIGN clear preserves selected infographics (2026-08-26 fix — it previously deleted them, unpublishing live content). The INFOGRAPHIC_IMAGE clear resets `image_jpeg` alongside `image` (`student_image` prefers the JPEG — a stale companion was served in the re-render window).
- Per-step dispatch: `[primary ×3, fallback ×1]` attempt list from `LLMStepConfig`; a recoverable attempt failure writes a transient FAILED log whose `output_data` carries `retry_message` + structured retry fields.
- `GenerationJob.content_types` (JSON, default `['graphic_novel']`) gates which formats a job generates; orchestrator skips steps of absent types. Wizard offers GN/infographic checkboxes.
- Dedup: cosine ≥ 0.90 on Qwen3 embeddings; `find_duplicate_definition` returns the **matched WordDefinition** (never snapshot an arbitrary sibling definition). Per-word persist is atomic (embedding fetched before the transaction); resume reuses already-attached words without re-embedding. Translations join on a per-object `term` field, not substring match, and attach to the snapshot-matched definition (`resolve_definition`), not `definitions.first()`.
- **Cross-wordset reuse** (`content_reuse.py`): word-level steps (QUESTION_GEN, SENTENCE_WRITE_GEN, PRIMER_GEN, TRANSLATION) skip words a prior job already covered when the authoring job's content Lexile is within ±`CONTENT_REUSE_LEXILE_TOLERANCE` (default 0.15) of this job's. Question reuse needs full coverage (≥3 choice questions × L1–5 from in-window jobs; NULL-`generation_job` rows never count); sentence-write also needs the same variant mode (guided-only ≤600 vs guided+open); primers are stamped with `generated_content_lexile` (legacy NULL regenerates); translations only check definition+language. Steps take `allow_reuse`; `restart_pipeline_from_step` passes False (its clear only removes this job's rows, so reuse would silently defeat a rerun). Pack-level steps never reuse. Preflight: `manage.py estimate_generation_reuse --ids-file FILE`.
- Question gen: batch = 2 words/call (`QUESTION_BATCH_SIZE`), idempotent per word — resume skips covered words, a mixed batch sends only its uncovered words, no duplicates. `restart_pipeline_from_step` for QUESTION_GEN deletes all questions first (intentional full regen). Question-gen + sentence-write **fail the batch** on a silently dropped word or an unmapped `question_type` (dropped words are never retried otherwise; unmapped types create student-invisible questions). Batches are structurally validated **before persisting** (`_first_invalid_question`: correct answer must be among the options — grading is exact-match — and options must be unique); a failing batch is regenerated in place (up to `QUESTION_BATCH_MAX_ATTEMPTS` = 3 calls, re-rolling prompt A/B), then the step fails.

### Graphic novels (steps 8–9)
- **3 candidates per pack** (`candidate_index`, `unique_together('pack','candidate_index')`), each from an independent full workflow. Admin publishes via `POST /api/graphic-novels/{id}/select/` → sets `is_selected`, clears siblings, promotes that candidate's staged cloze. **No auto-select** — pack stays hidden from students until published. Selection is completeness-gated (400 on incomplete candidates — an empty staged cloze can no longer wipe the pack's active cloze). Losing candidates kept hidden. `channel` is a dead column.
- Single engine `restart_graphic_novel_from_substep(job, pack_id, substep_key, words_data, candidate_index)`; `_step_graphic_novel_script` loops packs × candidates, skips complete candidates, resumes incomplete ones from the first substep lacking a COMPLETED log (the log is authoritative; artifacts write before validation — prior-substep artifacts are only loaded when their COMPLETED log exists, checked BEFORE the candidate's existing novel is deleted). "Complete" = story pages + review page + `metadata['page_count']` match + staged cloze (`_candidate_novel_is_complete`); a **selected candidate is never deleted by a resume**. `_persist_candidate_novel` is atomic; cloze joins pack words by term OR correct_answer and fails the candidate if a pack word gets no cloze row. Artifacts: `temp/generation_artifacts/job_{id}/pack_{id}_{slug}/cand_{i}/`. The engine refuses (ValueError; the views 409) when the candidate `is_selected`, and purges that candidate's substep logs ≥ the start substep before re-running — stale append-only COMPLETED logs previously let unvalidated artifacts pass as authoritative.
- 6 Gemini substeps per candidate: team selector (coin-flip solo/dual) → router → scorer → cloze (`gn_cloze_gen`) → beat sheet → final script. System/user prompt split; each substep retries 3× internally on the primary site only. World-context preamble (`prompts/graphic_novel_world_context.txt`) injected at runtime — not in templates.
- Page count is deterministic from pack word count (`page_count_for_word_count`: ≤4 words → 5, else 6); the LLM's `page_count` is overridden; router/scorer are told the fixed length.
- Substep restart: `POST /api/generation-jobs/{id}/restart-substep/` (`pack_id`, `substep`, optional `candidate_index`) — reruns from that substep, then runs the full script step over ALL packs (orphan-fill) before marking COMPLETED. Both restart thread functions claim the job atomically (`_claim_job_for_restart`: select_for_update check-and-set; PENDING/RUNNING job → skip); the views claim under their own row lock and pass `already_claimed=True`.
- Canon in `backend/data/canon/` loads via `canon_service.py`, split by purpose (team-selector summaries / script sheets / vault premises / full visual sheets collapsed).
- Story rules: Lexi Mini summons hard-capped 0–1/story; every vocab item needs a `pedagogical_anchor`; `complexity_budget` caps locations (page-count-aware) + ≤2 secondary characters; page 1 establishing panel; final page tension-before-resolution; re-establishing caption only when a location change isn't walkable-inferable; free-text `narrative_approach` + `central_thread` (non-conflict narratives allowed).
- Validators take `(result, ctx: SubstepContext)`. Prompt JSON schemas use chain-of-thought ordering — rationale/planning fields precede decision fields.
- Images: retry once then stop (no skipping ahead). Vocab words render in the character's Ink color; caption text white/cream, never gold/yellow. Secondary characters with dialogue + non-consecutive appearances get an LLM-generated visual anchor sheet in `novel.metadata['secondary_character_anchors']`.
- Admin per-page **edit** (`POST .../edit-image/`, admin prompt + current image) and **redraw** (`POST .../redraw-image/`, replays original generation payload via `build_page_image_prompt` + previous-page reference). Both async: 202 + daemon thread, poll `GET .../image-status/` (409 if busy); result → `edited_image` + auto-select; `select-image/` flips the variant synchronously. Every read path uses `display_image`. Busy check-and-set is atomic (`select_for_update`); worker bodies mark the page FAILED on ANY exception (previously only provider errors were caught); `image-status/` sweeps RUNNING rows older than 30 min → FAILED (daemon threads die with the gunicorn worker on every redeploy).
- Students load JPEG companions (`student_image`, ~6.7× smaller; best-effort write alongside every PNG via `image_utils.png_to_jpeg_bytes`); PNG stays source of truth for admin/editing/continuity. Backfill: `manage.py backfill_jpeg_images`.

### Infographics (steps 10–11)
- Single-page alternative to GN (migrations 0036/0037); mirrors the 3-candidate + admin-select model (`POST /api/infographics/{id}/select/` → `infographic_selection_service`). Neutral modern-editorial style (NotebookLM/data-viz explainer) — explicitly NOT a flashcard grid and NOT a children's storybook; no Lexi Legends canon; people de-emphasized (small, few, no close-up faces).
- 2 substeps per candidate in `step_infographic.py` (`ig_design` → `ig_cloze`, premise-free), then one poster render per candidate. Substep attempts are `[primary ×3, fallback ×1]` (2026-08-26 fix — the fallback site was previously never used; GN substeps stay primary-only). Design LLM acts as art director: picks `layout_mode` (`panorama` = continuous scene with a visual spine; `gallery` = vignettes in a creative framing device, never a plain grid) and emits per-candidate `color_palette` + `style_prompt` (mixed-and-matched from menus so the 3 candidates diverge; `DEFAULT_INFOGRAPHIC_STYLE` is the fallback). The validator requires `layout_mode` ∈ {panorama, gallery} — an invalid value used to silently render with panorama guidance.
- Captions must USE each word in a sentence — validator rejects `word: definition` glossary format; `intro_text` must use every target word (stem-tolerant); `_mark_vocab_terms` wraps target words in `**markers**` so the image model bolds/accents them (asterisks never printed).
- Restart: `POST /api/generation-jobs/{id}/restart-infographic-substep/` (`pack_id`, `substep` ∈ {design, cloze}, optional `candidate_index`) — orphan-fill + claim guard like the GN one; restart-from-cloze requires the design substep's COMPLETED log (checked before deleting the candidate); persist is atomic with the same cloze coverage raise; skip check = staged cloze exists, selected never deleted; does NOT re-render the poster (re-run INFOGRAPHIC_IMAGE separately). Same is_selected 409 and ≥-start-substep log purge as the GN engine.
- Prompts: `infographic_design.txt` / `infographic_cloze.txt` / `infographic_image.txt`. Artifacts: `…/infographic_cand_{i}/`.

### Cloze staging & per-assignment content type
- Cloze is generated per candidate (staged) and promoted on selection — see Hard Rules for the FK filter. The active set is shared across content types (last published wins).
- `StudentWordSetAssignment.content_type` (GN/infographic, default GN) set by teacher in `AssignSetForm`; `instructional_service.get_pack_data` serves the chosen type's selected content, falling back to the other published type, then legacy stories.
- Assignment gated on published content: `teacher_views._available_content_types_for_word_set` — a type is offered only if some pack has an `is_selected` candidate of it; `assign/` POST rejects unavailable types (400); the form blocks/labels accordingly.
- Student reader: `InfographicReader.jsx` routed on `story.type === 'infographic'`; widened student shell; Web Speech TTS button per word.

### Questions & sentence-writing
- **Sentence-writing** (SENTENCE_WRITE_GEN, migrations 0038/0039) — the only LLM-judged (non-exact-match) type. Two variants/word: GUIDED (L4, scenario + starter) and OPEN (L5), skill `sentence_production`, batch 10, idempotent per word/variant, Lexile-aware. The variants are separate LLM calls (guided first); the OPEN call's input JSON carries the word's `guided_scenario` (`_guided_scenarios_by_word_id` — latest GUIDED row per word) so the open scenario takes a clearly different angle. **Guided-only floor**: content Lexile ≤ 600 → OPEN skipped, GUIDED attached to both L4+L5 (code-assigned, not a prompt skip). Reuses `Question` model: rubric anchors in `options`, `correct_answers=[]`; `QuestionSerializer` strips anchors/model sentence and exposes a student-safe `sentence_write` payload.
- Judge (`services/sentence_evaluation_service.py`, step key `sentence_judge`): injection-hardened, structured correct/almost/incorrect verdict + `error_type` + coaching `hints` (**array, 1–3 bullets**; `_normalize_verdict` hard-caps at 3, keeps a joined `hint` for back-compat/TTS/`judge_result`). **Spelling is graded** (2026-07-03): a clear misspelling of the target word or any word can't be `correct` → `almost`/`spelling` (new `error_type`); a misspelled target word is never `correct`; caps/punctuation forgiven. **Grammar is notice-only**: never changes the verdict, but one clear basic agreement error ("I were"→"I was") is surfaced as an extra bullet (never articles/prepositions/punctuation). Definition anchor shown on BOTH variants; student's own sentence shown in the revision view + terminal panel. Revision loop **server-tracked in session, keyed by question_id** (Guided 3 / Open 2; client `prior_attempts` ignored — interleaving questions no longer resets the cap). Judged submits gated on `daily_question_limit`. Terminal step scores via `_classify_response_quality`: `productive_correct` (first try, +5 XP), `productive_recovered` (fragile), `productive_missed` (softened: −1, no demotion, fragile). Verdict persisted on `UserAnswer.judge_result`.
- **LLM-down = skip**: circuit breaker (3 consecutive failures → 5-min flag) excludes sentence-write types from `NextPracticeWordView`; submit-time failure discards without penalty. No back-to-back sentence-writes on the same word. New-jobs-only. Design: `docs/feature_plan/design-sentence-writing-questions.md`.

### Audiobook (on-demand, selected GN only)
- `GraphicNovelPageAudio` (OneToOne→page): stitched WAV + best-effort MP3 companion (`lameenc`, no ffmpeg); students stream MP3 via `student_audio` (falls back to WAV); admin review serves WAV.
- `services/audiobook/`: `events.build_page_events` (panel_descriptions → speech events) → `voices.voice_for` (stable hero map Leo=Puck/Amara=Despina/Mei=Zephyr/Hugo=Achird; narrator gender-contrasts the team; supporting chars hashed into gender-matched pools via the script's `characters[].gender`) → `tts_client.synthesize` (shared module-level **native** `genai.Client` using `GEMINI_TTS_*` settings — an OpenAI-compatible text proxy cannot serve audio; 120 s HttpOptions timeout, retries only transient 429/5xx/timeout errors) → `stitch` (stdlib `wave`) → `encode` (MP3). `stitch_pcm` validates uniform rate/channels/16-bit across clips (a mismatch used to silently corrupt the whole page's audio); regeneration deletes the old files before saving (no orphan accumulation).
- Voice director (`voice_director.direct_novel`, step key `audiobook_director`): one LLM call per novel produces per-speaker Audio Profiles + inline TTS tags; cached in `novel.metadata['voice_director']` so per-page regen reuses it (cache carries an events-payload sha1 — a script edit/regeneration re-directs instead of misaligning tags); slow-pace tags forbidden in prompt AND stripped on read; director failure degrades to bare transcript.
- API (admin, async like edit-image): `POST /api/graphic-novels/{id}/generate-audio/` → 202 + `audio-status/` poll; per-page `POST /api/graphic-novel-pages/{id}/regenerate-audio/`. Generation continues on per-page failure. Manual only — the view enforces it (400 on non-selected candidates, 400 on review pages) and the UI renders audio controls only on the selected candidate; audio-status polls sweep RUNNING rows older than 30 min → FAILED, and the busy claim is set synchronously under `select_for_update` before the thread spawns. Student UI: per-page Listen + Auto-read toggle (localStorage `gnReaderAutoplay`). Backfill: `manage.py backfill_audio_mp3`.

### LLM configuration
- `LLMSite` + `LLMStepConfig`: per-step site/model (primary + fallback), provider types `gemini_native` / `openai_compatible` / `anthropic`, keys as env-var references. Admin UI `/teacher/llm-config`. `llm_config_service.get_step_config(step_key)` — 5-min cache, invalidated on edit.
- **3 `LLMConfigSet` profiles**, exactly one active (app-enforced; MySQL lacks partial unique indexes). Pipeline reads the active set; `get_step_config()` signature unchanged. Step-config API is set-scoped (`?set=<id>`, default active); sites shared across sets; admin can rename/activate but not create/delete. Activation applies on the next job/step. Activation is atomic (`transaction.atomic` + `select_for_update`); step-config PUT is `update_or_create` per step (a missing seed row used to silently no-op); `get_active_set` logs a warning when falling back to the lowest-position set.
- `call_gemini`/`call_anthropic` accept `api_key`/`base_url` overrides; empty `user_prompt` collapses into the user message. See Hard Rules: they return dicts. Anthropic `max_tokens` is capped at 64000 (600000/128000 400'd against every current Claude model — the fallback path was dead); native Gemini + TTS clients have explicit HttpOptions timeouts (600 s / 120 s — the SDK default is no timeout).

### Admin review & job status UI
- `GenerationReview.jsx`: GN candidates as compare strip + detail (`PackGraphicNovels`); infographics via `PackInfographics`. Review endpoints return `graphic_novels`/`infographics` (all candidates, each with its cloze) + `graphic_novel`/`infographic` (selected or null); page payloads include `audio_url` (COMPLETED WAVs) via `_graphic_novel_page_review_payload()`.
- `GenerationJobStatus.jsx` derives step status from `job.status` + `last_completed_step` — NOT the latest per-step log (a mid-retry step shows RUNNING + amber "Retrying"). The logs API exposes `output_data` only, so retry detail the UI needs must live there. The status view doubles as the stale-job watchdog: no log activity for 30 min → job FAILED (word set back to TO_GENERATE), and stale RUNNING GN-page + infographic image rows are swept → FAILED (infographics added 2026-08-26).
- Multi-substep steps (GN script: 6 substeps; infographic: design→cloze) render per-candidate accordions via shared `renderSubstepAccordion`, fed by `_substep_statuses_for_step(job, step, substep_defs)`; per-substep restart buttons post to `restart-substep` / `restart-infographic-substep`.

### SRS / student-facing
- Response-quality-aware scheduling (fast/solid/slow affects intervals). Words go PENDING → READY on pack completion; only READY words enter SRS. Mastery 6–7 hidden from students (shown as "Mastered").
- **Submit-path integrity** (`PracticeService.process_answer`): `daily_question_limit` is enforced here, not just on serve — a non-retry submit past the cap raises `DailyLimitReached` → 429 (retries exempt); a non-READY word raises → 404 (the sentence-write path re-checks READY before the judge LLM call). The `UserWordProgress` row (`select_for_update(of=('self',))`, NOT the shared `MasteryLevel`) and the re-fetched `CustomUser` are locked before the streak/XP read-modify-write (closes the lost-update race). Client `duration_seconds`/`answer_switches` are clamped; `current_level_name` is masked to "Mastered" for hidden levels. `apply-bonuses/` requires `session_id`, claims it atomically (`cache.add`), and caps bonus XP at 30/user/day (was an unbounded replayable faucet); `session-summary` floors `start_time` to 24h. Sentence-write judge calls are also bounded per-day (`sw_judge_calls` cache counter = `daily_limit × (max_revisions+1)`, give-up exempt). `NextPracticeWordView` strips `explanation`/`example_sentence`/`correct_answer_is_term` from the serve payload (`for_serve` serializer context — the answer was readable pre-answer in the raw response); submit still returns them post-answer, and type-to-spell is derived client-side from `question_type` (`TERM_ANSWER_MC_TYPES` in PracticeView). A non-retry submit for a word whose `next_review_at` is beyond the serve cutoff is masked-404'd (answer-replay guard — closes same-day mastery farming); the daily-limit count runs under the user-row lock; durations ≤ 1 s fall into the neutral 'solid' bucket (0s was classified fast_correct); pure-typo submits no longer maintain the streak.
- Primer `kid_friendly_definition` is a concise 3–8 word phrase (also the review-page definition source; fallback `WordDefinition` truncated to 8 words). Review page: no story title, story characters used.
- Frontend `PracticeView.jsx` delegates each question type to `components/practice/` (`CorrectFeedbackBlock`, `SentenceWriteQuestion`, `ChoiceQuestion`, `ScrambleQuestion`). Submit has an `isSubmitting` ref double-tap guard; submit failures show a `submitError` banner (never `setFeedback({error})`, which traps the child in a dead form).

## Testing

- Backend: pytest + pytest-django + factory-boy, run from `backend/`. Frontend: no test framework yet.
- **Manual test seed**: `python manage.py seed_sentence_write_test [--reset]` seeds student `swtest`/`testpass123` with READY guided+open sentence-write questions (no generation run needed) to exercise the student practice flow; the judge itself still needs a live `sentence_judge` LLM config.
- **Cache must be cleared between tests**: no `CACHES` setting → process-global `LocMemCache`; pytest-django rolls back DB but not cache, so cache-backed DB-derived state leaks (notably `llm_config_service`). `tests/conftest.py` has an autouse `cache.clear()` fixture — keep it. If a test "passes alone but fails in the suite," suspect cross-test state leak; verify the first failure with `pytest -x` before assuming flakiness.
- **Filesystem isolation**: autouse fixtures in `tests/conftest.py` redirect the GN/infographic artifact dirs, `MEDIA_ROOT`, and `LLM_LOG_DIR` to per-test `tmp_path` — before these, pipeline/media tests wrote into the real `temp/generation_artifacts/` and `backend/media/` (a test run destroyed the real job_1 artifacts). `GraphicNovelFactory.is_selected` defaults False (hidden-until-published invariant); pass True explicitly for published-state tests.

## Code Conventions

- Backend: Django/DRF patterns — models → serializers → views → services; services hold business logic, views stay thin
- Frontend: functional components with hooks; plain CSS files, 5-theme student system (no CSS-in-JS)
- **Student CSS cascade**: `students.css` declares `@layer legacy,tokens,theme,base,components,pages`; `students/fixes.css` imports LAST in the `pages` layer and intentionally uses `!important` to own themed colors — a state color written in an earlier pages file (e.g. `practice.css`) without `!important` silently loses to fixes.css's neutral base rules. Brand-ish colors derive from `color-mix(in oklab, var(--primary) …)` (never hardcode the default indigo); semantic states (success/amber/danger) stay theme-independent; for small text keep the primary share ≤ ~55% vs near-black (mint/seafoam are the AA-contrast bottleneck). `prefers-reduced-motion` guard lives in `students/base.css`.
- Definition/example translation lookups are centralized in `vocabulary/utils.py` (`get_definition_translation(s)`) — import the shared helper, never add per-service copies
