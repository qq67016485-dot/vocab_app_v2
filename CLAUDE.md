# CLAUDE.md

## Project Overview

K-8 vocabulary learning web app with AI-generated instructional content, spaced repetition practice, and role-based access (admin, teacher, student). Target audience: ages 8–14, ESL learners.

## Tech Stack

- **Backend**: Django 5.2 + DRF 3.16, Python, MySQL
- **Frontend**: React 19 + Vite 7, plain CSS with theme system
- **LLMs**: Gemini (text generation + graphic novel scripts), OpenAI GPT-Image-2 (images), Qwen3 (embeddings via SiliconFlow). Anthropic SDK is wired for fallback but no active step currently uses it.
- **Auth**: Session-based with CSRF tokens

## Project Structure

```
backend/          Django project
  config/         Settings, URLs, authentication
  users/          User models & auth views
  vocabulary/     Main app (models, views, services, prompts)
    services/
      generation/           # 8-step AI content pipeline (modular package)
        orchestrator.py     # run/resume/restart pipeline
        step_word_lookup.py # Steps 1-2: lookup + dedup
        step_translations.py# Step 3
        step_questions.py   # Step 4
        step_packs.py       # Steps 5-6: primers + packs
        step_graphic_novel.py     # Steps 7-8 facade — re-exports from the 4 modules below
        graphic_novel_helpers.py  # Formatting, artifact I/O, substep runner, small pure helpers
        graphic_novel_validators.py # All _validate_* functions for graphic novel substeps
        graphic_novel_script.py   # _step_graphic_novel_script + restart_graphic_novel_from_substep
        graphic_novel_images.py   # _step_graphic_novel_images
        helpers.py          # Shared LLM wrappers, logging
        llm_config_service.py # Cached DB lookup for per-step model/site config
        constants.py        # Models, step order, config
      generation_pipeline_service.py  # Backwards-compatible shim (re-exports)
      canon_service.py      # Lexi Legends runtime canon loading
      llm_service.py        # Gemini + Claude + OpenAI API wrappers
      embedding_service.py  # Qwen3 embeddings for dedup
  tests/          pytest test suite
  data/canon/     Lexi Legends runtime canon (character sheets, settings, rulebook)
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

# Lint
cd frontend
npx eslint src/
```

## Configuration

Backend requires `.env` file (see `.env.example`):
- `DATABASE_URL` — MySQL connection string
- `GEMINI_API_KEY` — API key for Gemini (used by `call_gemini`; also used as the auth key when routing through `GEMINI_BASE_URL`)
- `GEMINI_BASE_URL` — Optional. If set, `call_gemini` routes through an **OpenAI-compatible proxy** (e.g., `https://api.b.ai/v1`). The SDK appends `/chat/completions` automatically, so the value must be the API root without that suffix.
- `GEMINI_TTS_API_KEY` / `GEMINI_TTS_BASE_URL` / `GEMINI_TTS_MODEL` — Read-along audiobook TTS, separate from the text Gemini config because audio needs the **native** generateContent API (an OpenAI-compatible text proxy does not serve it). `GEMINI_TTS_API_KEY` falls back to `GEMINI_API_KEY`; leave `GEMINI_TTS_BASE_URL` empty to call Google directly or point it at a proxy that serves native Gemini TTS; `GEMINI_TTS_MODEL` defaults to `gemini-2.5-pro-preview-tts`.
- `ANTHROPIC_API_KEY` — Used when any pipeline step is configured to route through an Anthropic site
- `ANTHROPIC_BASE_URL` — Optional proxy for Anthropic API
- `OPENAI_API_KEY` — GPT-Image-2 for graphic novel images
- `OPENAI_BASE_URL` — Optional proxy for OpenAI API
- `QWEN_API_KEY` — Qwen3 embeddings via SiliconFlow
- `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`

Note: Which API keys are actually needed depends on which sites are configured in the LLM Configuration admin page. The `LLMSite` model references env var names; the backend resolves them at runtime.

MySQL driver: `pymysql` (pure Python, installed as MySQLdb via `config/__init__.py`). No C compiler needed.
`requirements.txt` lists `pymysql` + `anthropic` + `google-genai` + `lameenc` (WAV→MP3 audiobook encoding, pure binary wheel — no ffmpeg) — do NOT add `mysqlclient` (requires C compiler, not used).

Frontend dev server proxies `/api` and `/media` to `localhost:8001`.

## Production Server

Live at **http://106.52.164.47** (Tencent Cloud, Ubuntu 24.04, 2 vCPU / 3.6 GB).

- nginx → serves `frontend/dist/`, proxies `/api` + `/admin` to gunicorn, serves `/media` + `/static`
- gunicorn (3 workers) via `unix:/run/vocab/vocab.sock`, systemd unit `vocab.service`
- MySQL 8, database `vocab_app`, user `vocab`@localhost
- Static files: `backend/staticfiles/` (run `collectstatic` after changes)
- Media files: `backend/media/` (persistent — do not delete)

**Redeploy after code change:**
```bash
# On server, from ~/vocab_app_v2/backend
source venv/bin/activate
python manage.py migrate           # if migrations changed
python manage.py collectstatic --noinput  # if static files changed
sudo systemctl restart vocab
```
Frontend change: rebuild locally (`npm run build`), then `scp -r frontend/dist ubuntu@106.52.164.47:~/vocab_app_v2/frontend/dist`.

**Server quirks:** GitHub git clone unreliable (HTTP/2 drops); use `scp` from Windows. nvm blocked; Node installed via NodeSource apt. Socket must be at `/run/vocab/vocab.sock` (not `/run/vocab.sock`). Run `chmod o+x /home/ubuntu` so nginx can traverse the home dir.

## Key Architecture Decisions

- Spaced repetition uses response-quality-aware scheduling (fast/solid/slow affects intervals)
- Words transition PENDING → READY after instructional pack completion; only READY words enter SRS
- Mastery levels 6-7 are hidden from students (rolled into "Mastered" on dashboard)
- Generation pipeline is a modular package at `vocabulary/services/generation/`; `generation_pipeline_service.py` is a backwards-compatible re-export shim
- 8 steps with per-step resume. `_reconstruct_context` rebuilds `words_data` from the WORD_LOOKUP log's `word_lookup_snapshot` when dedup hasn't completed (prevents word loss on mid-dedup failures)
- Unified graphic novel: each pack produces one novel at a length **derived deterministically from the pack's word count** — `page_count_for_word_count(n)` in `services/generation/constants.py` returns 5 for ≤4 words and 6 for >4 (threshold `GRAPHIC_NOVEL_WORD_COUNT_PAGE_THRESHOLD = 4`). `_step_graphic_novel_script` / `restart_graphic_novel_from_substep` compute `required_page_count`, pass it into the router/scorer/beat/final prompts (so premises are designed for that length), and then **force** `winning_premise['page_count'] = required_page_count` regardless of what the LLM returned. The router prompt is told the required length (every premise must use it); the scorer treats length as fixed and equal across premises. Beat-sheet and final-script substeps dispatch to the matching template via `GRAPHIC_NOVEL_BEAT_SHEET_TEMPLATES` / `GRAPHIC_NOVEL_SCRIPT_TEMPLATES`. The 5- and 6-page prompt files stay separate (6-page beat sheet adds a "deepen" note; `page_turn_question` is null for the final page)
- `GraphicNovel` FK→WordPack with a vestigial `channel` field (always `'5page'`) and `unique_together = ('pack', 'channel')`; `novel.metadata['page_count']` stores the length. Student-facing code (`instructional_service.py`) iterates saved `GraphicNovelPage` rows (length-agnostic)
- 6-call Gemini workflow per pack: team selector (coin-flips solo/dual via `sample_team_options()`, decides `vault_framing`) → router → scorer → cloze → beat sheet → final script, each with its own DB config key. Substeps use a system/user prompt split (instructions in system, data in user) — no `{input_json}` substitution. Each substep retries up to 3 attempts internally (`max_retries=2` on the configured primary site, no fallback site); the orchestrator does NOT retry the whole GRAPHIC_NOVEL_SCRIPT step
- Cloze generation is a dedicated substep (index 3) after scoring, using only the winning premise + vocab words (independent of beat sheet/final script). Prompt `graphic_novel_cloze.txt`, config key `gn_cloze_gen`, artifact `03b_cloze_generation.json`
- Per-pack resume: `_step_graphic_novel_script` resumes each pack from the first substep without a COMPLETED log (`_resume_substep_index_for_pack`), reusing prior on-disk artifacts — a job that failed mid-pack resumes at the failed substep, not team selection. A fresh pack runs the full workflow. The COMPLETED log is authoritative (artifacts write before validation, so a stale artifact can exist without one)
- Substep restart: `POST /api/generation-jobs/{id}/restart-substep/` (`pack_id` + `substep`) reconstructs context from prior artifacts and reruns from that substep, then runs the full script step over ALL packs before marking the job COMPLETED — filling packs the original run never reached. The skip-guard leaves complete packs untouched; a remaining-pack failure marks the job FAILED
- Canon files in `backend/data/canon/` load at runtime via `canon_service.py`, split by purpose: `team-selector-summaries.md` (team selection), `script-character-sheets.md` (narrative-only for router/scorer/beat sheet), `vault-summary-premises.md` (condensed vault for premises), full visual sheets collapsed via `collapse_markdown()` (final script + images). Per-character Lexi Mini examples ground vocab as a creature-summon mechanic, not generic magic
- World context preamble lives in `prompts/graphic_novel_world_context.txt`, injected at runtime by `_run_graphic_novel_substep` between the role line and step instructions — individual templates do NOT contain it
- Validators take `(result, ctx=None)` where `ctx` is a `SubstepContext` dataclass (`graphic_novel_validators.py`) accumulating `target_terms`/`winning_premise`/`selected_away_team`/`router_result`; build via `SubstepContext.from_input_summary(...)`. No lambda closures
- Image prompts: prose panel formatting, trimmed synopsis for pages 2+, per-character Ink-color highlighting — vocab words render in the character's Ink color (orange for Hugo) while surrounding caption text stays white/cream (never gold/yellow, for contrast)
- Review page: no story title; uses story characters; definitions from `PrimerCardContent.kid_friendly_definition` (fallback: `WordDefinition` truncated to 8 words)
- Script pacing: page 1 needs a WHO/WHERE/WHAT establishing panel; the final page (5 or 6) uses tension-before-resolution. Re-establishing caption on location change — when a page's location changes via a move the reader can't infer by simple walking (magical/instant or a far jump), the first panel opens with a short caption re-establishing WHERE and HOW the character arrived; ordinary walkable moves get none (saves the 80-word budget). Prompt decision test: "could a reader assume the character just walked there?"
- Pack grouping uses free-text `narrative_approach` (not a fixed engine list); downstream uses `central_thread` (not `central_problem`) to allow non-conflict narratives
- Prompt schemas use chain-of-thought field ordering: rationale/planning fields precede decision fields. Router `vocab_integration_plan` before the `premise` paragraph; scorer `dimension_rankings` scratchpad before `scores`; beat sheet `vocab_roles` + `ink_usage` before the `beat_sheet` array; final script per-page `page_planning` before `panels`; team_rationale before booleans
- Vocab semantic accuracy: target words must stay semantically true to the story's resolution — never false accusations, rumors, or red herrings that get debunked (ESL learners build meaning from outcomes)
- Lexi Mini system: writing a vocab word with a hero's tool (Hugo's carpenter's pencil, Leo's wax crayon, Amara's quill, Mei's marker) summons a temporary monochromatic creature that acts out the definition; tools only appear on-page during a summon. Hard cap 0–1 Minis/story (`GRAPHIC_NOVEL_MAX_MINI_SUMMONS_PER_STORY = 1` in `constants.py`), enforced via the `total_ink_activations_planned` counter declared before vocab arrays in router + beat sheet. Most vocab integrates through dialogue/narration/world logic; every summon succeeds (no failure states). `GRAPHIC_NOVEL_ALLOWED_INTEGRATION_MODES` uses `lexi_mini_summon`; JSON keys `uses_direct_ink`/`ink_usage`/`total_ink_activations_planned` kept for backwards compat
- Pedagogical anchors: every router `vocab_integration_plan` item carries `pedagogical_anchor = {anchor_type, anchor_sketch}` with `anchor_type` ∈ `GRAPHIC_NOVEL_PEDAGOGICAL_ANCHOR_TYPES` ({demonstrated_action, near_synonym, category_example, visible_referent}); final script propagates these into `vocab_anchors`. `_validate_vocab_integration_plan` rejects premises missing the anchor
- Plot complexity caps: each premise carries `complexity_budget = {locations, secondary_characters, problem_thread}`. Location cap scales by length via `max_locations_for_page_count()` (≤2 for 5-page, ≤3 for 6-page); ≤2 secondary characters. `_validate_beat_complexity` enforces `setting_keys` count and `characters_featured ⊆ away_team ∪ secondary_characters`
- Scoring dimensions: `GRAPHIC_NOVEL_SCORING_DIMENSIONS = {narrative_clarity, visual_potential, vocabulary_integration, pedagogical_clarity, character_fit}`. All premises share the same `required_page_count`, so the scorer judges how well each uses that fixed length (length is not a differentiator); location ceiling is page-count-aware
- Graphic novel image generation retries once on failure then stops (does not skip to later pages)
- Admin per-page image editing: `POST /api/graphic-novel-pages/{id}/edit-image/` (`{prompt}`) re-renders one page via OpenAI `images.edit` using the displayed image as reference; result saved to `edited_image` (original `image` never overwritten) and auto-selected. `POST .../select-image/` (`{variant}`) flips `use_edited_image`. Both admin-only. The edit is **asynchronous**: the view validates + reads the reference bytes synchronously, sets the page `RUNNING`, then runs the slow image call in a daemon thread (`_run_page_image_edit`) so no gunicorn worker is held for the ~30-60s wait; it returns **202** (or **409** if an edit is already running). The frontend polls `GET .../image-status/` every 10s until `COMPLETED`/`FAILED`. `select-image/` stays synchronous (instant DB flip). Every read path uses the `display_image` property, so the choice propagates to students/review/status/continuity. UI: `GraphicNovelPageEditor.jsx` (click-to-zoom `ImageLightbox`)
- Admin per-page image **redraw**: `POST /api/graphic-novel-pages/{id}/redraw-image/` (no body) replays the page's *original generation* payload — the template-built prompt (`build_page_image_prompt(page)`) + the previous page as the continuity reference (`previous_page_reference_bytes(page)`, both in `graphic_novel_images.py`) — to get a fresh roll of the same prompt when an image came out bad. Distinct from edit (which uses *this* page's image + an admin instruction). Shares the async machinery: validates + builds the payload synchronously, sets `RUNNING`, runs `_run_page_image_redraw` in a daemon thread, returns **202** (or **409** if busy), frontend polls the same `image-status/`. Result saves to `edited_image` + auto-selects (`prompt_used` tagged `[REDRAW]`), so the original is preserved and reversible via the variant picker. `build_page_image_prompt` was extracted from `_step_graphic_novel_images` so the pipeline and redraw stay in lockstep. UI: a "Redraw" button beside "Edit image" in `GraphicNovelPageEditor.jsx` (shared `pollUntilDone` helper)
- Student JPEG companions: page PNGs stay the source of truth (admin, editing, continuity); students load a smaller JPEG (~6.7× smaller) to save mobile bandwidth. `GraphicNovelPage` has `image_jpeg` + `edited_image_jpeg`; `student_image` returns the displayed variant's JPEG (falls back to its PNG). A JPEG writes best-effort alongside every PNG save (generation + edit-image + skip-path backfill via `backfill_page_jpegs`); conversion via `services/image_utils.py::png_to_jpeg_bytes` (quality 85, alpha flattened onto white; Pillow is a runtime dep) and a failure never aborts PNG generation. Only the student read path uses `student_image`; admin payloads serve PNG via `display_image`. Backfill: `python manage.py backfill_jpeg_images [--dry-run]` (idempotent)
- Read-along audiobook (on-demand): `GraphicNovelPageAudio` (OneToOne→`GraphicNovelPage`, migration `0032`) stores **one stitched WAV per page** in `audio` plus a compressed **MP3 companion** in `audio_mp3` (migration `0034`). Service package `services/audiobook/`: `events.build_page_events` (pure — `panel_descriptions` → ordered speech events, one narration box / dialogue line each, with pauses), `voices.voice_for` (stable hero map Leo=Puck/Amara=Despina/Mei=Zephyr/Hugo=Achird; narrator **gender-contrasts the hero team** — any female hero on the team → male narrator Charon, all-male team → female narrator Aoede, unknown team → Aoede default, via `narrator_voice_for()` reading `metadata['away_team']` + the `HERO_GENDERS` map; supporting (story-specific) chars are hashed into a **gender-matched** pool — the final script emits `characters[].gender` ("male"/"female"/"neutral"), `voices._supporting_voice_for()` reads that to pick `SUPPORTING_VOICE_POOL_MALE`/`SUPPORTING_VOICE_POOL_FEMALE`, and an unknown/neutral/unlabeled gender (e.g. older novels) falls back to the combined `SUPPORTING_VOICE_POOL`), `tts_client.synthesize` (isolated **native** `genai.Client` — audio modality needs Gemini's native generateContent API, which an OpenAI-compatible text proxy does NOT serve; uses dedicated settings `GEMINI_TTS_API_KEY`/`GEMINI_TTS_BASE_URL`/`GEMINI_TTS_MODEL`, NOT `settings.GEMINI_API_KEY` which is empty here — the real Gemini key lives in the LLM Config Matrix; `GEMINI_TTS_BASE_URL` is passed via `HttpOptions(base_url=...)`, empty = call Google directly; parses sample rate from the response mime type; retries once), `stitch` (stdlib `wave` only — no ffmpeg/pydub on the box), `encode.wav_bytes_to_mp3_bytes` (WAV→MP3 via **`lameenc`**, a pure binary-wheel LAME encoder — again no ffmpeg/pydub; ~64 kbps mono, ~6× smaller; pinned `lameenc==1.8.2`), `generator.generate_novel_audio` (continue-on-failure per page; skips review page + already-COMPLETED unless `regenerate`). The MP3 is written **best-effort** by `generator._save_mp3_companion` right after the WAV save — a conversion failure is logged and never aborts the WAV. Model: `gemini-2.5-pro-preview-tts`. Spoken text comes verbatim from `panel_descriptions` (no OCR). API (admin, async like edit-image): `POST /api/graphic-novels/{id}/generate-audio/` → 202 + daemon thread (409 if running), `GET .../audio-status/` poll, `POST /api/graphic-novel-pages/{id}/regenerate-audio/`. Student payload (`instructional_service`) carries `audio_url` via the `student_audio` property (**MP3 preferred**, falls back to WAV). The two admin **review** content endpoints (`GenerationJobContentView`, `WordSetContentView`) serialize `audio_url` from the WAV (`audio.url`) per page (via the shared `_graphic_novel_page_review_payload()` helper, COMPLETED audio only) so the inline `<audio>` player shows on page load — not just after a fresh generate-audio poll. Admin UI: button + poller in `GenerationReview.jsx` (seeds `audioState` from loaded content), `<audio>` per page in `GraphicNovelPageEditor.jsx`. **Student UI** (`GraphicNovelReader.jsx`): per-page Listen/Pause button + an **Auto-read** toggle (persisted in `localStorage` `gnReaderAutoplay`, default on; auto-starts each page's audio on arrival, per-page only, no auto-advance; toggling never interrupts the playing page via an `autoplayRef`). Backfill existing WAV rows with `python manage.py backfill_audio_mp3 [--dry-run]` (idempotent; skips non-16-bit-PCM-WAV). Deferred: per-event timing/highlight sync, Opus, ambience/SFX, cross-page auto-advance. Production rules: `docs/feature_plan/lexi-legends-audiobook-production-bible.md`
- Audiobook voice director: before synthesis, `services/audiobook/voice_director.py::direct_novel(novel, pages)` makes **one LLM call per novel** (step key `audiobook_director`, configurable in the LLM Config Matrix; seeded by migration `0033`, cloned from `gn_final_script`). It sends all pages' speech events (each dialogue event carries the speaker's `gender` — from `characters[].gender`, or `HERO_GENDERS` for heroes — so the director casts and notes gender-consistently) and gets back (a) a short Audio Profile + Director's Notes block per speaker and (b) the transcript with inline Gemini TTS audio tags (`[excitedly]`/`[whispers]`/…) per `prompts/audiobook_voice_director.txt`. Result cached in `novel.metadata['voice_director']` so per-page regen reuses it (no extra LLM call). `generate_page_audio(page, direction=...)` uses the speaker's profile block as the TTS `style_prefix` and speaks the tagged line; any director failure degrades gracefully to the bare transcript. The prompt file escapes literal `{...}` braces (it's `.format()`-substituted for `age_band`/`age_guidance` only). The prompt forbids slow-pace tags (`[slowly]`, `[one word at a time]`, etc.) because they stack on the already-gentle kid delivery and make lines drag; `_index_directed_events` additionally strips any slow-pace cue from the directed text via `_strip_slow_tags()` on the read path, so both fresh and already-cached director output are sanitized without an LLM re-run (emotion tags like `[amazed]` are kept)
- Secondary character visual anchors: after the final script, an extra LLM call generates a ~150-word visual reference sheet for secondary characters with dialogue AND non-consecutive appearances, stored in `novel.metadata['secondary_character_anchors']`. The call returns parsed JSON (wrappers always return dicts — see `call_gemini` note), so `_format_anchor_design_lock()` renders the design-lock sections (AGE_AND_BODY, FACE_AND_HAIR, OUTFIT_LOCK, COLOR_PRIORITY, NEGATIVE_LOCK) into a `KEY: value` block. Image lookup (`_characters_for_graphic_novel_page`) checks `LEXI_CHARACTERS` first (hero canon), then stored anchors, then the brief `novel.characters` entry. Prompt `prompts/secondary_character_anchor.txt`; uses `gn_final_script` config
- LLM Configuration Matrix: `LLMSite` + `LLMStepConfig` let admins set the API site + model (primary + fallback) per pipeline step. `llm_config_service.get_step_config(step_key)` returns cached config (5-min TTL). Provider types: `gemini_native`, `openai_compatible`, `anthropic`. Admin UI `/teacher/llm-config`. API keys stored as env-var references, resolved at runtime. Each graphic novel substep has its own config key (incl. `gn_cloze_gen`); the on-demand audiobook voice director uses `audiobook_director`
- LLM config sets: there are **3 `LLMConfigSet` profiles** (seeded by migration `0031`, named "Set 1/2/3"), each holding its own full copy of the 12 `LLMStepConfig` rows (`unique_together = (config_set, step_key)`; the 12th, `audiobook_director`, was added by migration `0033`). Exactly one set is active (`is_active`, enforced in app logic — MySQL has no partial unique index); the pipeline reads the active set's configs. `get_step_config()` keeps its signature and resolves rows from the active set (via `get_active_set()`), so orchestrator/GN callers are unchanged. Activation takes effect on the **next job/step** (5-min cache, invalidated on any edit/activation). Sites are shared across all sets. API: `GET /admin/llm-config-sets/`, `PUT /admin/llm-config-sets/{id}/` (rename via `name`, activate via `is_active:true` — deactivates the others; cannot deactivate the active set). Step-config GET/PUT are set-scoped via `?set=<id>` (default = active set) and return `{set, configs}`. Admin can only edit/rename/activate sets — no create/delete. Frontend: set selector + rename + "Make active" controls on the Step Configuration tab in `LLMConfig.jsx`
- Pipeline dispatch: orchestrator builds a `[primary, primary, primary, fallback]` attempt list from `LLMStepConfig` (3 attempts on the primary site, then 1 on the fallback site). `_call_llm_with_config(site_config, system_prompt, user_prompt)` routes by `provider_type`. On a recoverable attempt failure it writes a transient `FAILED` log whose `output_data` carries a per-site-role `retry_message` + structured fields (`failed_attempt`, `failed_site_role`, `next_attempt`, `next_site_role`, `failed_model`, `next_model`) via `_build_retry_payload(plan, failed_idx)`; attempts count *within each site role*
- Job status UI truth: `GenerationJobStatus.jsx` derives each step's status from the authoritative `job.status` + `last_completed_step` (active step = the one right after it), NOT the latest per-step log. A step mid-retry shows RUNNING + an amber "Retrying" line; a red "Error" only shows for a terminal FAILED step. The logs API exposes `output_data` but NOT `input_data`, so any retry detail the UI needs must live in `output_data`
- `call_gemini` and `call_anthropic` accept optional `api_key`/`base_url` overrides for per-call routing. Empty `user_prompt` is collapsed into the user message (prevents "messages is required"). **Both always return parsed JSON (a `dict`), never a raw string** — they force JSON mode. Any step wanting prose must request a JSON object with named fields and format the dict itself; calling `.strip()`/string methods on the result raises
- Question generation batch size is 2 words per LLM call (`QUESTION_BATCH_SIZE` in `step_questions.py`; small to avoid proxy timeout on slow models). Idempotent per batch: questions commit as each batch succeeds (no wrapping transaction), and resume/retry reads the job's existing `Question.word_id` set and skips batches whose words are all generated (clearing only partial batches) — no reprocessing or duplicates. `questions_created` is recomputed as the job total; COMPLETED log records `batches_skipped`. `restart_pipeline_from_step` for QUESTION_GEN still deletes all questions first (intentional full regen)
- Deduplication uses cosine similarity ≥ 0.92 on Qwen3 embeddings
- Translation step uses `term`-based matching (not substring matching on source_text); prompt returns a `term` field per object for reliable join
- Primer `kid_friendly_definition` is a concise 3-8 word phrase (not a sentence); used on primer cards and as the review-page definition source. Syllable breaks use phonetic (sound-based) splitting; single-syllable words output without dots
- Questions without `lexile_score` must be included in practice/dashboard queries (don't filter them out)

## Testing

- Backend: pytest + pytest-django + factory-boy
- Run `pytest` from `backend/` directory
- Frontend: no test framework yet

## Code Conventions

- Backend follows Django/DRF patterns: models → serializers → views → services
- Services handle business logic; views are thin
- Frontend uses functional components with hooks
- CSS uses plain files with a 5-theme student system (no CSS-in-JS)
- Cloze blanks from LLM vary in underscore count — use regex matching, not exact string match
- Definition/example translation lookups are centralized in `vocabulary/utils.py` (`get_definition_translation` / `get_definition_translations`) — import the shared helper instead of adding a per-service ContentType+Translation lookup
