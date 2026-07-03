# CLAUDE.md

## Project Overview

K-8 vocabulary learning web app with AI-generated instructional content, spaced repetition practice, and role-based access (admin, teacher, student). Target audience: ages 8–14, ESL learners.

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
  src/context/    UserContext, ThemeContext
  src/api/        Axios config with CSRF interceptor
docs/             Architecture docs, changelogs, feature plans
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

Which keys are actually needed depends on sites configured in the LLM Config admin page (`LLMSite` stores env-var names, resolved at runtime). `requirements.txt`: `pymysql` + `anthropic` + `google-genai` + `lameenc` (WAV→MP3, pure wheel — no ffmpeg). Frontend dev server proxies `/api` and `/media` to `localhost:8001`.

## Production Server

Live at **http://106.52.164.47** (Tencent Cloud, Ubuntu 24.04, 2 vCPU / 3.6 GB).

- nginx → serves `frontend/dist/`, proxies `/api` + `/admin` to gunicorn, serves `/media` + `/static`
- gunicorn (3 workers) via `unix:/run/vocab/vocab.sock`, systemd unit `vocab.service`. **Must run threaded workers** (`--worker-class gthread --threads 8`): the sentence-write judge does a 2–10s synchronous LLM round-trip in-request; sync workers would stall the box
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

## Hard Rules (violations cause real bugs)

- **Active cloze reads must filter `novel__isnull=True, infographic__isnull=True`** (both FKs). Filtering only `novel` leaks staged infographic cloze to students. Staged cloze has exactly one FK set; promoted/active has both NULL.
- **Questions without `lexile_score` must be included** in practice/dashboard queries — never filter them out.
- **Never exact-string-match LLM output**: character names vary across substeps ("Mr. Vidal" vs "groundskeeper Mr. Vidal") — match on distinctive name tokens (`_significant_name_tokens`). Cloze blanks vary in underscore count — use regex.
- **`call_gemini` / `call_anthropic` always return parsed JSON dicts, never strings** (forced JSON mode). Steps wanting prose must request named JSON fields; string methods on the result raise.
- **Prompts use soft guidance, not rigid mandates** — reserve hard limits for measurable constraints. Vocab words must stay semantically true to the story's resolution (no debunked labels/red herrings).
- Syllable breaks only insert middle dots into the exact spelling, never phonetic respelling ("sim·i·le" not "sim·i·lee"); `_sanitize_syllable_text` enforces on save.
- Step order + GN substep order are duplicated across 5 files (generation `constants.py`, `GenerationJobStatus.jsx`, StepKey enum, `generation_views.py`, PROJECT_CONTEXT) — keep in lockstep.

## Architecture Summary

### Generation pipeline
- Modular package `vocabulary/services/generation/`; `generation_pipeline_service.py` is a re-export shim. 11 steps with per-step resume; `_reconstruct_context` rebuilds `words_data` from the WORD_LOOKUP log snapshot when dedup didn't complete.
- Per-step dispatch: `[primary ×3, fallback ×1]` attempt list from `LLMStepConfig`; a recoverable attempt failure writes a transient FAILED log whose `output_data` carries `retry_message` + structured retry fields.
- `GenerationJob.content_types` (JSON, default `['graphic_novel']`) gates which formats a job generates; orchestrator skips steps of absent types. Wizard offers GN/infographic checkboxes.
- Dedup: cosine ≥ 0.92 on Qwen3 embeddings; `find_duplicate_definition` returns the **matched WordDefinition** (never snapshot an arbitrary sibling definition). Per-word persist is atomic (embedding fetched before the transaction); resume reuses already-attached words without re-embedding. Translations join on a per-object `term` field, not substring match.
- Question gen: batch = 2 words/call (`QUESTION_BATCH_SIZE`), idempotent per batch — resume skips fully-generated batches, no duplicates. `restart_pipeline_from_step` for QUESTION_GEN deletes all questions first (intentional full regen). Question-gen + sentence-write **fail the batch** on a silently dropped word or an unmapped `question_type` (dropped words are never retried otherwise; unmapped types create student-invisible questions).

### Graphic novels (steps 8–9)
- **3 candidates per pack** (`candidate_index`, `unique_together('pack','candidate_index')`), each from an independent full workflow. Admin publishes via `POST /api/graphic-novels/{id}/select/` → sets `is_selected`, clears siblings, promotes that candidate's staged cloze. **No auto-select** — pack stays hidden from students until published. Losing candidates kept hidden. `channel` is a dead column.
- Single engine `restart_graphic_novel_from_substep(job, pack_id, substep_key, words_data, candidate_index)`; `_step_graphic_novel_script` loops packs × candidates, skips complete candidates, resumes incomplete ones from the first substep lacking a COMPLETED log (the log is authoritative; artifacts write before validation — prior-substep artifacts are only loaded when their COMPLETED log exists, checked BEFORE the candidate's existing novel is deleted). "Complete" = story pages + review page + `metadata['page_count']` match + staged cloze (`_candidate_novel_is_complete`); a **selected candidate is never deleted by a resume**. `_persist_candidate_novel` is atomic; cloze joins pack words by term OR correct_answer and fails the candidate if a pack word gets no cloze row. Artifacts: `temp/generation_artifacts/job_{id}/pack_{id}_{slug}/cand_{i}/`.
- 6 Gemini substeps per candidate: team selector (coin-flip solo/dual) → router → scorer → cloze (`gn_cloze_gen`) → beat sheet → final script. System/user prompt split; each substep retries 3× internally on the primary site only. World-context preamble (`prompts/graphic_novel_world_context.txt`) injected at runtime — not in templates.
- Page count is deterministic from pack word count (`page_count_for_word_count`: ≤4 words → 5, else 6); the LLM's `page_count` is overridden; router/scorer are told the fixed length.
- Substep restart: `POST /api/generation-jobs/{id}/restart-substep/` (`pack_id`, `substep`, optional `candidate_index`) — reruns from that substep, then runs the full script step over ALL packs (orphan-fill) before marking COMPLETED. Both restart thread functions claim the job atomically (`_claim_job_for_restart`: select_for_update check-and-set; PENDING/RUNNING job → skip); the views claim under their own row lock and pass `already_claimed=True`.
- Canon in `backend/data/canon/` loads via `canon_service.py`, split by purpose (team-selector summaries / script sheets / vault premises / full visual sheets collapsed).
- Story rules: Lexi Mini summons hard-capped 0–1/story; every vocab item needs a `pedagogical_anchor`; `complexity_budget` caps locations (page-count-aware) + ≤2 secondary characters; page 1 establishing panel; final page tension-before-resolution; re-establishing caption only when a location change isn't walkable-inferable; free-text `narrative_approach` + `central_thread` (non-conflict narratives allowed).
- Validators take `(result, ctx: SubstepContext)`. Prompt JSON schemas use chain-of-thought ordering — rationale/planning fields precede decision fields.
- Images: retry once then stop (no skipping ahead). Vocab words render in the character's Ink color; caption text white/cream, never gold/yellow. Secondary characters with dialogue + non-consecutive appearances get an LLM-generated visual anchor sheet in `novel.metadata['secondary_character_anchors']`.
- Admin per-page **edit** (`POST .../edit-image/`, admin prompt + current image) and **redraw** (`POST .../redraw-image/`, replays original generation payload via `build_page_image_prompt` + previous-page reference). Both async: 202 + daemon thread, poll `GET .../image-status/` (409 if busy); result → `edited_image` + auto-select; `select-image/` flips the variant synchronously. Every read path uses `display_image`.
- Students load JPEG companions (`student_image`, ~6.7× smaller; best-effort write alongside every PNG via `image_utils.png_to_jpeg_bytes`); PNG stays source of truth for admin/editing/continuity. Backfill: `manage.py backfill_jpeg_images`.

### Infographics (steps 10–11)
- Single-page alternative to GN (migrations 0036/0037); mirrors the 3-candidate + admin-select model (`POST /api/infographics/{id}/select/` → `infographic_selection_service`). Neutral modern-editorial style (NotebookLM/data-viz explainer) — explicitly NOT a flashcard grid and NOT a children's storybook; no Lexi Legends canon; people de-emphasized (small, few, no close-up faces).
- 2 substeps per candidate in `step_infographic.py` (`ig_design` → `ig_cloze`, premise-free), then one poster render per candidate. Design LLM acts as art director: picks `layout_mode` (`panorama` = continuous scene with a visual spine; `gallery` = vignettes in a creative framing device, never a plain grid) and emits per-candidate `color_palette` + `style_prompt` (mixed-and-matched from menus so the 3 candidates diverge; `DEFAULT_INFOGRAPHIC_STYLE` is the fallback).
- Captions must USE each word in a sentence — validator rejects `word: definition` glossary format; `intro_text` must use every target word (stem-tolerant); `_mark_vocab_terms` wraps target words in `**markers**` so the image model bolds/accents them (asterisks never printed).
- Restart: `POST /api/generation-jobs/{id}/restart-infographic-substep/` (`pack_id`, `substep` ∈ {design, cloze}, optional `candidate_index`) — orphan-fill + claim guard like the GN one; restart-from-cloze requires the design substep's COMPLETED log (checked before deleting the candidate); persist is atomic with the same cloze coverage raise; skip check = staged cloze exists, selected never deleted; does NOT re-render the poster (re-run INFOGRAPHIC_IMAGE separately).
- Prompts: `infographic_design.txt` / `infographic_cloze.txt` / `infographic_image.txt`. Artifacts: `…/infographic_cand_{i}/`.

### Cloze staging & per-assignment content type
- Cloze is generated per candidate (staged) and promoted on selection — see Hard Rules for the FK filter. The active set is shared across content types (last published wins).
- `StudentWordSetAssignment.content_type` (GN/infographic, default GN) set by teacher in `AssignSetForm`; `instructional_service.get_pack_data` serves the chosen type's selected content, falling back to the other published type, then legacy stories.
- Assignment gated on published content: `teacher_views._available_content_types_for_word_set` — a type is offered only if some pack has an `is_selected` candidate of it; `assign/` POST rejects unavailable types (400); the form blocks/labels accordingly.
- Student reader: `InfographicReader.jsx` routed on `story.type === 'infographic'`; widened student shell; Web Speech TTS button per word.

### Questions & sentence-writing
- **Sentence-writing** (SENTENCE_WRITE_GEN, migrations 0038/0039) — the only LLM-judged (non-exact-match) type. Two variants/word: GUIDED (L4, scenario + starter) and OPEN (L5), skill `sentence_production`, batch 10, idempotent per word/variant, Lexile-aware. **Guided-only floor**: content Lexile ≤ 600 → OPEN skipped, GUIDED attached to both L4+L5 (code-assigned, not a prompt skip). Reuses `Question` model: rubric anchors in `options`, `correct_answers=[]`; `QuestionSerializer` strips anchors/model sentence and exposes a student-safe `sentence_write` payload.
- Judge (`services/sentence_evaluation_service.py`, step key `sentence_judge`): injection-hardened, structured correct/almost/incorrect verdict + `error_type` + coaching hint. Revision loop **server-tracked in session** (Guided 3 / Open 2; client `prior_attempts` ignored — cap not spoofable). Judged submits gated on `daily_question_limit`. Terminal step scores via `_classify_response_quality`: `productive_correct` (first try, +5 XP), `productive_recovered` (fragile), `productive_missed` (softened: −1, no demotion, fragile). Verdict persisted on `UserAnswer.judge_result`.
- **LLM-down = skip**: circuit breaker (3 consecutive failures → 5-min flag) excludes sentence-write types from `NextPracticeWordView`; submit-time failure discards without penalty. No back-to-back sentence-writes on the same word. New-jobs-only. Design: `docs/feature_plan/design-sentence-writing-questions.md`.

### Audiobook (on-demand, selected GN only)
- `GraphicNovelPageAudio` (OneToOne→page): stitched WAV + best-effort MP3 companion (`lameenc`, no ffmpeg); students stream MP3 via `student_audio` (falls back to WAV); admin review serves WAV.
- `services/audiobook/`: `events.build_page_events` (panel_descriptions → speech events) → `voices.voice_for` (stable hero map Leo=Puck/Amara=Despina/Mei=Zephyr/Hugo=Achird; narrator gender-contrasts the team; supporting chars hashed into gender-matched pools via the script's `characters[].gender`) → `tts_client.synthesize` (isolated **native** `genai.Client` using `GEMINI_TTS_*` settings — an OpenAI-compatible text proxy cannot serve audio) → `stitch` (stdlib `wave`) → `encode` (MP3).
- Voice director (`voice_director.direct_novel`, step key `audiobook_director`): one LLM call per novel produces per-speaker Audio Profiles + inline TTS tags; cached in `novel.metadata['voice_director']` so per-page regen reuses it; slow-pace tags forbidden in prompt AND stripped on read; director failure degrades to bare transcript.
- API (admin, async like edit-image): `POST /api/graphic-novels/{id}/generate-audio/` → 202 + `audio-status/` poll; per-page `POST /api/graphic-novel-pages/{id}/regenerate-audio/`. Generation continues on per-page failure. Manual only — trigger on the selected candidate. Student UI: per-page Listen + Auto-read toggle (localStorage `gnReaderAutoplay`). Backfill: `manage.py backfill_audio_mp3`.

### LLM configuration
- `LLMSite` + `LLMStepConfig`: per-step site/model (primary + fallback), provider types `gemini_native` / `openai_compatible` / `anthropic`, keys as env-var references. Admin UI `/teacher/llm-config`. `llm_config_service.get_step_config(step_key)` — 5-min cache, invalidated on edit.
- **3 `LLMConfigSet` profiles**, exactly one active (app-enforced; MySQL lacks partial unique indexes). Pipeline reads the active set; `get_step_config()` signature unchanged. Step-config API is set-scoped (`?set=<id>`, default active); sites shared across sets; admin can rename/activate but not create/delete. Activation applies on the next job/step.
- `call_gemini`/`call_anthropic` accept `api_key`/`base_url` overrides; empty `user_prompt` collapses into the user message. See Hard Rules: they return dicts.

### Admin review & job status UI
- `GenerationReview.jsx`: GN candidates as compare strip + detail (`PackGraphicNovels`); infographics via `PackInfographics`. Review endpoints return `graphic_novels`/`infographics` (all candidates, each with its cloze) + `graphic_novel`/`infographic` (selected or null); page payloads include `audio_url` (COMPLETED WAVs) via `_graphic_novel_page_review_payload()`.
- `GenerationJobStatus.jsx` derives step status from `job.status` + `last_completed_step` — NOT the latest per-step log (a mid-retry step shows RUNNING + amber "Retrying"). The logs API exposes `output_data` only, so retry detail the UI needs must live there.
- Multi-substep steps (GN script: 6 substeps; infographic: design→cloze) render per-candidate accordions via shared `renderSubstepAccordion`, fed by `_substep_statuses_for_step(job, step, substep_defs)`; per-substep restart buttons post to `restart-substep` / `restart-infographic-substep`.

### SRS / student-facing
- Response-quality-aware scheduling (fast/solid/slow affects intervals). Words go PENDING → READY on pack completion; only READY words enter SRS. Mastery 6–7 hidden from students (shown as "Mastered").
- Primer `kid_friendly_definition` is a concise 3–8 word phrase (also the review-page definition source; fallback `WordDefinition` truncated to 8 words). Review page: no story title, story characters used.

## Testing

- Backend: pytest + pytest-django + factory-boy, run from `backend/`. Frontend: no test framework yet.
- **Cache must be cleared between tests**: no `CACHES` setting → process-global `LocMemCache`; pytest-django rolls back DB but not cache, so cache-backed DB-derived state leaks (notably `llm_config_service`). `tests/conftest.py` has an autouse `cache.clear()` fixture — keep it. If a test "passes alone but fails in the suite," suspect cross-test state leak; verify the first failure with `pytest -x` before assuming flakiness.

## Code Conventions

- Backend: Django/DRF patterns — models → serializers → views → services; services hold business logic, views stay thin
- Frontend: functional components with hooks; plain CSS files, 5-theme student system (no CSS-in-JS)
- Definition/example translation lookups are centralized in `vocabulary/utils.py` (`get_definition_translation(s)`) — import the shared helper, never add per-service copies
