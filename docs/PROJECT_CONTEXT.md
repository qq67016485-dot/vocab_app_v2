# vocab_app_v2 — Project Context

## Overview

A full-stack vocabulary learning application for ESL students ages 8–14. Teachers create word sets, an AI pipeline generates instructional content (definitions, questions, graphic novels, and cloze items), and students learn through a structured instructional flow (Primer → Graphic Novel → Cloze Quiz; legacy packs may still show Micro Story) followed by spaced-repetition practice.

**Tech stack:** Django 5.2 + Django REST Framework (backend), React 19 + Vite 7 (frontend), MySQL database, session-based auth with CSRF tokens.

**Roles:** ADMIN (full access + AI generation), TEACHER (student/content management), STUDENT (learning + practice).

---

## Project Structure

```
vocab_app_v2/
├── backend/
│  ├── config/                    # Django project settings
│  │  ├── settings.py            # DB, CORS, DRF, LLM API keys, tier config
│  │  ├── urls.py                # /admin/, /api/ → vocabulary.urls
│  │  └── authentication.py      # CsrfExemptSessionAuthentication
│  ├── users/
│  │  └── models.py              # CustomUser (extends AbstractUser), StudentGroup
│  ├── vocabulary/
│  │  ├── models.py              # All domain models (see Models section)
│  │  ├── views/                 # API views organized by domain
│  │  │  ├── user_views.py      # Auth: login, logout, CSRF, user detail
│  │  │  ├── practice_views.py  # SRS practice: next word, submit answer, session summary
│  │  │  ├── dashboard_views.py # Student dashboard, teacher roster, student progress
│  │  │  ├── instructional_views.py  # Pack data, pack completion
│  │  │  ├── teacher_views.py   # Word/WordSet/Curriculum CRUD, student management
│  │  │  ├── group_views.py     # Student group CRUD
│  │  │  └── generation_views.py # AI pipeline: trigger, status, review
│  │  ├── services/
│  │  │  ├── generation/                    # 8-step AI content pipeline (modular package)
│  │  │  │  ├── orchestrator.py           # run/resume/restart pipeline
│  │  │  │  ├── step_word_lookup.py       # Steps 1-2: lookup + dedup
│  │  │  │  ├── step_translations.py      # Step 3
│  │  │  │  ├── step_questions.py         # Step 4
│  │  │  │  ├── step_packs.py             # Steps 5-6: primers + packs
│  │  │  │  ├── step_graphic_novel.py     # Steps 7-8 facade (re-exports from the 4 modules below)
│  │  │  │  ├── graphic_novel_helpers.py  # Formatting, artifact I/O, substep runner, helpers
│  │  │  │  ├── graphic_novel_validators.py # All _validate_* functions for substeps
│  │  │  │  ├── graphic_novel_script.py   # _step_graphic_novel_script + restart entry point
│  │  │  │  ├── graphic_novel_images.py   # _step_graphic_novel_images
│  │  │  │  ├── helpers.py                # Shared LLM wrappers, logging
│  │  │  │  └── constants.py              # Models, step order, config
│  │  │  ├── generation_pipeline_service.py # Backwards-compat shim (re-exports)
│  │  │  ├── audiobook/                     # On-demand read-along audio (Gemini TTS)
│  │  │  │  ├── events.py                  # panel_descriptions → ordered speech events
│  │  │  │  ├── voice_director.py          # per-novel LLM call: profiles + tagged transcript
│  │  │  │  ├── voices.py                  # speaker → prebuilt voice resolution
│  │  │  │  ├── tts_client.py              # isolated native Gemini TTS call
│  │  │  │  ├── stitch.py                  # stdlib wave PCM concatenation
│  │  │  │  ├── generator.py               # per-page/per-novel orchestration
│  │  │  │  └── constants.py               # voice map, pauses, PCM format
│  │  │  ├── practice_service.py           # Answer processing, XP, mastery, streaks
│  │  │  ├── dashboard_service.py          # Roster analytics, learning patterns
│  │  │  ├── instructional_service.py      # Pack data assembly for students
│  │  │  ├── assignment_service.py         # Word set → student assignment
│  │  │  ├── canon_service.py              # Lexi Legends runtime canon file loading
│  │  │  ├── llm_service.py               # Gemini + OpenAI API wrappers
│  │  │  └── embedding_service.py          # Qwen3 embeddings for dedup
│  │  ├── prompts/               # LLM prompt templates (.txt files)
│  │  ├── serializers.py         # DRF serializers
│  │  ├── urls.py                # All API route registrations
│  │  ├── constants.py           # Question type → skill tag mappings
│  │  ├── utils.py               # Shared helpers: definition-translation lookup (get_definition_translation(s)), local-day/XP tier helpers
│  │  ├── permissions.py         # IsAdmin, IsTeacherOrAdmin, IsStudent
│  │  └── admin.py               # Django admin registrations
│  ├── tests/
│  │  ├── factories.py           # factory-boy factories for all models
│  │  ├── users/test_models.py
│  │  └── vocabulary/            # test_views, test_models, test_serializers, test_services
│  ├── data/
│  │  └── canon/                 # Lexi Legends runtime canon (character sheets, settings, rulebook)
│  ├── requirements.txt
│  ├── pytest.ini
│  └── .env                       # DATABASE_URL, API keys (gitignored)
├── frontend/
│  ├── src/
│  │  ├── App.jsx                # Route definitions
│  │  ├── main.jsx               # Entry: UserProvider → ThemeProvider → App
│  │  ├── api/axiosConfig.js     # Axios instance, CSRF interceptor
│  │  ├── context/
│  │  │  ├── UserContext.jsx     # Auth state, login/logout/refresh
│  │  │  └── ThemeContext.jsx    # Student theme (5 themes, localStorage)
│  │  ├── pages/
│  │  │  ├── student/           # Dashboard, PracticeView, InstructionalFlow
│  │  │  ├── teacher/           # CommandCenter, WordSets, Groups, StudentProgress
│  │  │  ├── admin/             # GenerationWizard, GenerationReview
│  │  │  └── shared/            # LearningPatternsView
│  │  ├── components/            # Reusable UI (see Components section)
│  │  ├── hooks/                 # useTranslationVisibility
│  │  ├── constants/skillTags.js # Skill tag display names (student/teacher variants)
│  │  ├── styles/                # Plain CSS, student theme system
│  │  └── assets/sounds/         # correct.mp3, incorrect.mp3
│  ├── vite.config.js             # Port 5174, proxy /api + /media → localhost:8001
│  └── package.json               # React 19, axios, react-router-dom 7
```

---

## Data Models

### Core Vocabulary
- **Word** - `text`, `part_of_speech`, `source_context`, M2M `tags`
- **WordDefinition** - FK to Word, `definition_text`, `example_sentence`, `lexile_score`
- **DefinitionEmbedding** — OneToOne→WordDefinition, `embedding` (JSONField vector), `model_version` (Qwen3-Embedding-8B)
- **Translation** — Generic FK (ContentType), `field_name`, `language`, `translated_text`. Supports translating any model's text fields.

### Curriculum & Word Sets
- **Curriculum** — `name`
- **Level** — `name`, `order`
- **WordSet** — `title`, `unit_or_chapter`, `description`, `source_text`, `target_lexile`, `input_words` (JSONField), `generation_status` (DRAFT/TO_GENERATE/GENERATING/GENERATED), FK→Curriculum, FK→Level, FK→creator, M2M→Word
- **StudentWordSetAssignment** — FK→user, FK→WordSet, FK→assigned_by

### Instructional Layer
- **WordPack** — FK→WordSet, `label`, `text_type` (fiction/narrative_nonfiction), `order`. Groups ~6 words for instructional sequence.
- **WordPackItem** — FK→WordPack, FK→Word, `order`
- **PrimerCardContent** — OneToOne→Word, `syllable_text`, `kid_friendly_definition`, `example_sentence`
- **GraphicNovel** — FK→WordPack, `channel` ('5page' kept as vestigial field for legacy rows; new novels always save as '5page'), `title`, `synopsis`, `style_prompt`, `reading_level`, `metadata` (JSONField — stores `page_count` ∈ {5, 6}, derived deterministically from the pack's word count: ≤4 words → 5 pages, >4 → 6), `created_at`. `unique_together = ('pack', 'channel')`. New generated packs use this as the Story/Read step.
- **GraphicNovelPage** — FK→GraphicNovel, `page_number`, `image` (the original generated PNG), `edited_image` (admin-edited PNG variant; the original in `image` is never overwritten), `use_edited_image` (Boolean — when True and an edited image exists, the edited variant is shown everywhere), `image_jpeg` / `edited_image_jpeg` (lightweight JPEG companions of `image` / `edited_image`, served only to students to save mobile bandwidth), `prompt_used`, page image generation tracking (`generation_status`, `generation_attempts`, `generation_error`, `generation_started_at`, `generation_completed_at`), `panel_count`, `layout_description`, `panel_descriptions` (JSON accessibility/tooltip metadata), `vocab_words_used`. Properties: `display_image` returns the selected PNG variant (edited if selected+present, else original) — used by admins and cross-page continuity; `student_image` returns the JPEG of the displayed variant, falling back to that variant's PNG when no JPEG exists — used by the student instructional flow; `has_edited_image` is truthy when an edit exists. **Admin/editing read paths use `display_image` and the student read path uses `student_image`, so the admin's variant choice drives what everyone sees while students always get the smaller JPEG.** Each record stores one complete 1792x1024 landscape comic page image containing 1-4 panels.
- **GraphicNovelPageAudio** — OneToOne→GraphicNovelPage, `audio` (stitched WAV FileField — source of truth, served to admin/review), `audio_mp3` (compressed MP3 companion of the WAV, served to students), `duration_ms`, `voice_manifest` (JSON — per-event voice assignments for debug/regen), `status` (PENDING/RUNNING/COMPLETED/FAILED), `attempts`, `error`, timestamps. One row per page holds the on-demand read-along audio (one stitched WAV per page, plus its MP3 companion). Property `student_audio` returns the MP3 when present, falling back to the WAV (mirrors the PNG/JPEG `student_image` pattern). Kept separate from the page so audio is fully optional/regenerable and never touches image rows. See the read-along audiobook pipeline below.
- **MicroStory** — FK→WordPack, `story_text` (target words in `**bold**`), `reading_level` (Lexile). Legacy format retained so existing word sets keep working.
- **ClozeItem** — FK→WordPack, FK→Word, `sentence_text` (with `_______` blank), `correct_answer`, `distractors`
- **StudentPackCompletion** — FK→user, FK→WordPack. Completing a pack flips words from PENDING→READY.
### Mastery & Spaced Repetition
- **MasteryLevel** — `level_id` (PK), `level_name`, `interval_days`, `points_to_promote`
  - Fields include `is_hidden`; hidden levels are used for long-term scheduling but not exposed as separate student-facing mastery labels.
  - Level 1 (Novice): 1 day, promotes at 2 points
  - Level 2 (Familiar): 3 days, promotes at 4 points
  - Level 3 (Confident): 7 days, promotes at 7 points
  - Level 4 (Proficient): 10 days, promotes at 10 points
  - Level 5 (Mastered): 17 days, promotes at 15 points
  - Level 6 (Long-Term Retention): 30 days, promotes at 25 points, hidden from student-facing level labels
  - Level 7 (Long-Term Mastery): 60 days, promotes at 999 points, hidden terminal level
  - Student dashboards roll hidden level 6 and 7 words into the visible Mastered bucket. Daily/weekly deltas ignore transitions that stay inside that displayed bucket, so 5->6, 6->7, 7->6, and 6->5 do not reveal hidden levels.
- **UserWordProgress** — FK→user, FK→Word, FK→MasteryLevel, `mastery_points`, `next_review_at` (DateTimeField), `last_reviewed_at`, `learning_speed` (adaptive multiplier, default 1.0), `instructional_status` (READY/PENDING). Indexed on `(user, next_review_at)` (due-for-review query) and `(user, instructional_status)`.
- **MasteryLevelLog** — FK→user, FK→Word, old_level, new_level, timestamp

### Questions & Practice
- **Question** — FK→Word, `question_type` (28 types), `question_text`, `options` (JSON), `correct_answers` (JSON), `explanation`, `lexile_score`, `difficulty_index`, `discrimination_index`, M2M→MasteryLevel (`suitable_levels`), FK→GenerationJob
- **PracticeSession** — FK→user, `start_time`, `end_time`
- **UserAnswer** — FK→PracticeSession, FK→user, FK→Question, `user_answer`, `is_correct`, `duration_seconds`, `answer_switches`, `answered_at`, `retry_count`. Persisted first-attempt durations and answer switches are used for response-quality scheduling baselines. Indexed on `(user, answered_at)`, `(user, is_correct)`, and `(question, answered_at)` for dashboard analytics and per-word history lookups.

### Generation Pipeline
- **GenerationJob** — FK→WordSet, FK→created_by, `job_type` (FULL_PIPELINE/QUESTIONS_ONLY/INSTRUCTIONAL_ONLY), `status` (PENDING/RUNNING/COMPLETED/FAILED/PARTIALLY_COMPLETED), `input_words` (JSON), `target_lexile`, `target_language`, counters (words/questions/primers/stories/graphic_novels/cloze created), `last_completed_step` (for resume), `error_message`
- **GenerationJobLog** — FK→GenerationJob, `step`, `status`, `input_data`, `output_data`, `error_message`, `duration_seconds`

### LLM Configuration
- **LLMConfigSet** — `name`, `position` (unique, 1-based), `is_active` (exactly one active, enforced in app logic). There are **3 sets**, seeded by migration `0031` ("Set 1/2/3", Set 1 active). The pipeline reads step configs from the active set; admins can edit/rename any set and switch which one is active. No create/delete (fixed at 3).
- **LLMSite** — `name` (unique), `base_url` (blank for native SDK), `api_key_env_var` (env var name), `provider_type` (gemini_native/openai_compatible/anthropic). Shared across all config sets.
- **LLMStepConfig** — FK→`config_set`, `step_key` (one of 12 text step keys), FK→primary_site, `primary_model`, FK→fallback_site, `fallback_model`. `unique_together = (config_set, step_key)` — each set holds its own full copy of all 12 step configs. The `StepKey` enum is declared in pipeline-execution order (`word_lookup` → `translation` → `question_gen` → `primer_gen` → `pack_creation` → `gn_team_selection` → `gn_router_premises` → `gn_premise_scoring` → `gn_cloze_gen` → `gn_beat_sheet` → `gn_final_script` → `audiobook_director`); the admin step-config API returns rows in this order (not alphabetical) so the UI matrix mirrors the pipeline. `audiobook_director` is the on-demand voice-director call (not part of the 8-step generation pipeline); seeded into all 3 sets by migration `0033`.

### Users
- **CustomUser** (extends AbstractUser) — `role` (ADMIN/TEACHER/STUDENT), `native_language`, `daily_question_limit` (default 30), `daily_goal_min`, `daily_goal_max`, `last_goal_prompt_date`, `lexile_min`/`lexile_max`, M2M `students` (teacher→student), `current_practice_streak`, `last_practice_date`, `streak_freezes_available`, `xp_points`, `level`
- **StudentGroup** — FK→teacher, M2M→students, `name`, `description`

---

## 8-Step AI Content Generation Pipeline

The pipeline runs as a background thread, triggered by an admin via the GenerationWizard. Each step logs to GenerationJobLog. The pipeline supports resume from the last completed step on failure. Model and site selection is configured per-step via the **LLM Configuration Matrix** (admin UI at `/teacher/llm-config`): each step has a primary and fallback site+model pair stored in `LLMStepConfig`. There are **3 config sets** (`LLMConfigSet`), one active at a time; the pipeline reads the active set's configs (switching sets takes effect on the next job/step, via the 5-min `llm_config_service` cache). The orchestrator builds a `[primary, primary, fallback]` attempt list per step. On a recoverable attempt failure it writes a transient `FAILED` log carrying a `retry_message` + structured attempt fields in `output_data` (via `_build_retry_payload`), so the status UI can show an honest "Retrying" state rather than a false failure. Image steps (GPT-Image-2) retry once with the same model and are not part of the configurable matrix.

For the multi-pack GRAPHIC_NOVEL_SCRIPT step, resume is per-pack and per-substep: when a job fails mid-pack, resuming picks each pack up at the first substep without a COMPLETED log (reusing the prior substeps' on-disk artifacts) rather than restarting from team selection. The per-pack substep-restart endpoint (`restart-substep`) regenerates one pack from a chosen substep and then runs the full script step across **all** packs before completing — so a pack the original run never reached (because an earlier pack failed) is filled in instead of silently left without a novel.

| Step | Name | What It Does |
|------|------|--------------|
| 1 | WORD_LOOKUP | LLM defines each word (POS, definition, example sentence). Normalizes plurals/tense. |
| 2 | DEDUP | Embedding-based deduplication (cosine similarity ≤0.92). Creates Word, WordDefinition, DefinitionEmbedding. Reuses existing words if found. |
| 3 | TRANSLATION | LLM translates definition_text and example_sentence to target_language. Creates Translation records. |
| 4 | QUESTION_GEN | LLM generates 15 questions per word (3 per mastery level 1-5) in batches of 2 words (`QUESTION_BATCH_SIZE`). Creates Question records with suitable_levels M2M. Idempotent per batch: questions commit as each batch succeeds, and resume/retry skips batches whose words already have questions for this job (clearing only partial batches) — no wasted LLM calls, no duplicates. |
| 5 | PRIMER_GEN | LLM generates syllable_text + kid_friendly_definition (concise 3-8 word phrase). Creates PrimerCardContent. Definitions also serve as the review page vocabulary source. |
| 6 | PACK_CREATION | LLM groups words into situation-aware packs of ~6 for downstream graphic novels (free-text `narrative_approach` per pack). Creates WordPack + WordPackItem. If existing packs are missing generated words during a rerun, validates a replacement LLM grouping before replacing the old pack structure. Sequential fallback is testing-only and is logged with a quality warning. |
| 7 | GRAPHIC_NOVEL_SCRIPT | Gemini `gemini-3.1-pro-preview` runs a 6-call planning pipeline per pack: team selection (coin-flip solo/dual, decides `vault_framing`), router/premises, premise scoring, cloze generation (dedicated substep using only the winning premise + vocab words), beat sheet/vocab roles, and final script/self-check. **Page count is derived deterministically from the pack's word count — `page_count_for_word_count(n)` returns 5 for ≤4 words and 6 for >4 (threshold `GRAPHIC_NOVEL_WORD_COUNT_PAGE_THRESHOLD = 4`).** The router and scorer prompts are told this `required_page_count` so premises are designed for it, but the pipeline then forces `winning_premise['page_count'] = required_page_count` regardless of the LLM's output. The beat-sheet and final-script substeps dispatch to the matching prompt template via `GRAPHIC_NOVEL_BEAT_SHEET_TEMPLATES` / `GRAPHIC_NOVEL_SCRIPT_TEMPLATES` (`{5: 'graphic_novel_beat_sheet', 6: 'graphic_novel_beat_sheet_6page'}` and the same for script). One `GraphicNovel` is created per pack (`channel='5page'`, vestigial), with N story `GraphicNovelPage` rows (N = forced page_count) plus 1 review page, and `ClozeItem`. `novel.metadata['page_count']` records the length. Intermediate JSON artifacts are written under `temp/generation_artifacts/`. Vocab integration uses the **Lexi Mini system**: 0–1 Mini summon per story max — when a hero writes a vocab word with their tool (Hugo's carpenter's pencil, Leo's wax crayon, Amara's quill, Mei's marker), it hatches a temporary creature that physically acts out the definition. Most vocab integrates through dialogue/narration/world logic without summoning a Mini. Each vocab item must declare a `pedagogical_anchor` (`demonstrated_action`, `near_synonym`, `category_example`, or `visible_referent`) so ESL learners can derive meaning from the page. Plot complexity caps scale by length via `max_locations_for_page_count(page_count)` (≤2 for 5-page, ≤3 for 6-page) and ≤2 secondary characters with a single problem thread. |
| 8 | GRAPHIC_NOVEL_IMAGES | OpenAI GPT-Image-2 generates one 1792x1024 landscape image per `GraphicNovelPage`, including the vocabulary review page. Length-agnostic — iterates the saved page rows. Each page tracks `PENDING`/`RUNNING`/`COMPLETED`/`FAILED`, attempts, and errors. The step saves successful pages (and a smaller JPEG companion in `image_jpeg` for students, best-effort), fails if any page fails or remains incomplete, and Resume retries only missing/failed pages (also backfilling any missing JPEG on skipped pages). **Post-generation, admins can refine any single page from the review screen via the edit-image endpoint (uses the current image as a reference) and toggle between the original and edited variant — see Admin Image Editing below.** |

`STORY_CLOZE_GEN` remains a valid `GenerationJobLog.Step` enum for historical logs, but it is legacy-only and is not part of `PIPELINE_STEP_ORDER` or active restart targets. `GN_6PAGE_SCRIPT` and `GN_6PAGE_IMAGES` likewise stay in the enum so old log rows remain readable, but no current code path emits them. Existing `MicroStory` records still render through the student fallback.

**LLM models used:** Configurable per-step via `LLMStepConfig` (admin UI). Default seed: Gemini `gemini-3.1-pro-preview` primary / `gemini-3-pro-preview` fallback for all 12 text step keys (the `gn_cloze_gen` substep was seeded by migration 0026; the on-demand `audiobook_director` voice-director step by migration 0033). OpenAI GPT-Image-2 generates graphic novel page images in step 8 (not configurable). Qwen3-Embedding-8B via SiliconFlow handles step 2 embeddings. The `llm_config_service.get_step_config(step_key)` cache layer resolves site+model at runtime; `_call_llm_with_config()` routes by provider type (`gemini_native` / `openai_compatible` / `anthropic`).

**Prompt templates** are in `vocabulary/prompts/`: `word_lookup.txt`, `question_generation_A.txt`, `question_generation_B.txt`, `translation.txt`, `pack_grouping.txt`, `primer_generation.txt`, `graphic_novel_team_selector.txt`, `graphic_novel_router.txt`, `graphic_novel_premise_scorer.txt`, `graphic_novel_beat_sheet.txt`, `graphic_novel_beat_sheet_6page.txt`, `graphic_novel_script.txt`, `graphic_novel_script_6page.txt`, `graphic_novel_page.txt`, `graphic_novel_review_page.txt`, `audiobook_voice_director.txt` (read-along voice director), and `story_cloze_generation.txt` (legacy-only). The two `_6page` files are dispatched by the forced `page_count` (derived from the pack's word count), not by a separate channel.

**Generation logs:** LLM text calls and OpenAI graphic novel page image calls write full prompt/response or prompt/status logs to `temp/llm_logs/`. Step logs store compact metadata such as model, prompt template/hash, counts, fallback flags, warnings, and artifact paths. Graphic novel planning artifacts are saved as temp JSON files under `temp/generation_artifacts/job_<job_id>/pack_<pack_id>_<slug>/`; DB logs keep only references and summaries. Graphic novel page prompts are stored on `GraphicNovelPage.prompt_used`. `GRAPHIC_NOVEL_IMAGES` also writes per-page RUNNING progress logs with page id, pack label, page number, and attempt.

**Long-running job DB handling:** Generation runs in a background thread and can spend minutes inside Gemini/OpenAI calls. The pipeline releases stale Django/MySQL connections before and after slow LLM/image calls, and closes old connections when full-pipeline, resume, or restart execution exits. This prevents background generation from holding database connections while the admin status page polls job/log endpoints.

**Admin status polling:** `GenerationJobStatus` polls `/api/generation-jobs/<id>/` and `/api/generation-jobs/<id>/logs/` every 30 seconds. Per-step status is derived from the authoritative `job.status` + `last_completed_step` (the active step is the one right after `last_completed_step`), not from the latest per-step log — so a step that is mid-retry renders RUNNING with a "Retrying" detail (from the retry marker's `retry_message`) instead of a false FAILED. The status and logs views display the `Graphic Novel Script` and `Graphic Novel Images` step labels plus per-page image status from `graphic_novel_image_pages`. If a job stalls for 15 minutes with no log activity, the status endpoint marks the job FAILED, records a FAILED log for the active step, resets the word set out of `GENERATING`, and marks any RUNNING graphic novel page FAILED. Resume then restarts from `GRAPHIC_NOVEL_IMAGES` when `last_completed_step` is `GRAPHIC_NOVEL_SCRIPT`; completed pages are skipped and only missing/failed pages are retried. Jobs whose `last_completed_step` is the now-removed `GN_6PAGE_*` value are treated as fully complete by `resume_pipeline`.

**Admin image editing (post-generation):** From the GenerationReview screen, an admin can refine any individual page image without re-running the pipeline. Each page card (`GraphicNovelPageEditor.jsx`) has an "Edit image" box: the admin types an instruction and `POST /api/graphic-novel-pages/<page_id>/edit-image/` re-renders the page through OpenAI's `images.edit` endpoint, passing the **currently displayed** image as the visual reference. The result is stored in `GraphicNovelPage.edited_image` (the original in `image` is never overwritten) and auto-selected (`use_edited_image=True`). The card then shows an Original/Edited variant picker; `POST /api/graphic-novel-pages/<page_id>/select-image/` with `{"variant": ...}` flips `use_edited_image`. Because every read path uses the `display_image` property, the selected variant is what students see in the reader. Both endpoints are admin-only. The edit is **asynchronous**: the endpoint validates the prompt and reads the reference image synchronously, marks the page `RUNNING`, then runs the ~30-60s image call in a background thread (`_run_page_image_edit`) and returns **202** immediately (or **409** if an edit is already in progress), so a slow image call never ties up a gunicorn worker. The card polls `GET /api/graphic-novel-pages/<page_id>/image-status/` every 10s until the page reports `COMPLETED` (merges the new image) or `FAILED` (shows the error). The `select-image/` switch stays synchronous (an instant DB flip), reversible, and neither file is deleted. The card's thumbnail is click-to-zoom: clicking it opens a fullscreen lightbox showing the currently previewed variant at full size (closes on backdrop click, the × button, or Escape) — useful for inspecting fine detail before deciding whether to edit. The lightbox is a local component inside `GraphicNovelPageEditor.jsx` (no separate route or API).

**Admin image redraw (post-generation):** Beside "Edit image" each page card has a **"Redraw"** button (no prompt input). Unlike an edit — which feeds *this* page's own image plus an admin instruction into `images.edit` — a redraw replays the page's **original generation payload**: the template-built prompt (`build_page_image_prompt(page)`) plus the **previous page** as the continuity reference (`previous_page_reference_bytes(page)`, both in `graphic_novel_images.py`). It is a fresh roll of the exact same prompt, for when an image came out garbled and a second attempt may clean it up. `POST /api/graphic-novel-pages/<page_id>/redraw-image/` takes no body. It shares all of the edit flow's async machinery: validates + builds the payload synchronously, marks the page `RUNNING`, runs the slow call in a background thread (`_run_page_image_redraw`), returns **202** (or **409** if an image op is already running), and the card polls the same `image-status/` endpoint. The result lands in `edited_image` and is auto-selected (`prompt_used` tagged `[REDRAW]`), so the original `image` is preserved and the change is reversible via the same variant picker. `build_page_image_prompt` was extracted out of the pipeline's `_step_graphic_novel_images` so generation and redraw always build the identical prompt. Admin-only.

**Student-facing JPEG companions:** PNG page images are large (~3.3 MB each) and slow to load on mobile data, so every PNG gets a smaller JPEG companion (~0.5 MB, ~15% of the PNG) that students load instead. The PNG remains the source of truth for admins, editing, and cross-page style continuity. `GraphicNovelPage` carries `image_jpeg` / `edited_image_jpeg` alongside the PNG fields; the `student_image` property returns the JPEG of the currently displayed variant (falling back to the PNG if no JPEG exists yet). JPEGs are written best-effort alongside every PNG save — during generation (`graphic_novel_images.py`), during admin edits (`edit-image`), and via a skip-path backfill on resume — using `services/image_utils.py::png_to_jpeg_bytes` (quality 85, alpha flattened onto white). A conversion failure never blocks PNG generation. Only the student read path (`instructional_service.py`) uses `student_image`; all admin payloads still serve the PNG via `display_image`. Existing rows are backfilled with `python manage.py backfill_jpeg_images` (idempotent, supports `--dry-run`).

---

## API Endpoints

### Auth
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/csrf/` | Get CSRF token |
| POST | `/api/login/` | Login (username/password) |
| POST | `/api/logout/` | Logout |
| GET | `/api/user/` | Current user details |

### Practice (Student)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/practice/next/?session_start=<iso>` | Next due word (respects daily limit, Lexile range, session dedup, instructional_status=READY) |
| POST | `/api/practice/submit/` | Submit answer → mastery update, XP, streak, response-quality scheduling metadata |
| POST | `/api/practice/session-summary/` | Strengths/weaknesses for a session |
| POST | `/api/practice/apply-bonuses/` | Apply focus streak XP bonus |

### Student Dashboard
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/student/dashboard/` | Words due, streak, mastery breakdown, session goal; hidden levels 6-7 are rolled into Mastered |
| GET | `/api/student/words-by-level/<level_id>/` | Words at a mastery level; level 5 also returns hidden level 6-7 words |
| GET | `/api/student/learning-patterns/` | Error pattern analysis |
| GET | `/api/student/assigned-sets/` | Assigned word sets with packs and completion status |
### Instructional
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/instructional/packs/<pack_id>/` | Full pack data: primer cards (with images), `story.type` discriminator (`graphic_novel` pages for new packs, `micro_story` fallback for legacy packs), cloze items |
| POST | `/api/instructional/packs/<pack_id>/complete/` | Mark pack complete → flips words PENDING→READY |

### Teacher
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/teacher/roster/?group_id=<id>` | Class roster with 3-day activity, snapshots |
| GET/POST | `/api/teacher/students/` | List/create students |
| POST | `/api/teacher/students/bulk/` | Bulk create up to 10 students |
| GET/PATCH/DELETE | `/api/teacher/students/<pk>/` | Student CRUD |
| GET | `/api/teacher/students/<id>/progress/` | Detailed student progress |
| GET | `/api/teacher/students/<id>/learning-patterns/` | Student error patterns |

### Content Management (ViewSet routes)
| Method | Path | Description |
|--------|------|-------------|
| GET/POST | `/api/word-sets/` | List/create word sets |
| GET/PATCH/DELETE | `/api/word-sets/<id>/` | Word set CRUD |
| POST | `/api/word-sets/<id>/assign/` | Assign to students/groups |
| POST | `/api/word-sets/<id>/add_word/` | Add word to set |
| POST | `/api/word-sets/<id>/remove_word/` | Remove word from set |
| GET/POST | `/api/word-sets/<id>/packs/` | List/create packs |
| PATCH/DELETE | `/api/word-sets/<id>/packs/<pack_id>/` | Update/delete pack |
| GET | `/api/words/` | List all words |
| GET | `/api/curricula/` | List curricula |
| GET | `/api/levels/` | List levels |
| GET/POST/PATCH/DELETE | `/api/groups/` | Student group CRUD |

### Generation (Admin only)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/word-sets/<id>/generate/` | Start full pipeline |
| POST | `/api/word-sets/<id>/add-words/` | Deprecated/blocked: generated word sets are immutable |
| GET | `/api/word-sets/<id>/latest-job/` | Most recent generation job |
| GET | `/api/word-sets/<id>/content/` | All generated content for word set |
| GET | `/api/generation-jobs/<id>/` | Job status, counters, stale-job check, and `graphic_novel_image_pages` per-page progress |
| GET | `/api/generation-jobs/<id>/logs/` | Step-by-step logs, including `output_data` for page-level progress messages |
| GET | `/api/generation-jobs/<id>/content/` | Content generated by this job, including graphic novel page metadata/images/status for generated packs |
| POST | `/api/generation-jobs/<id>/approve/` | Compatibility action; images are auto-approved by generation |
| POST | `/api/generation-jobs/<id>/resume/` | Resume failed pipeline and record fresh RUNNING activity |
| POST | `/api/generation-jobs/<id>/restart-step/` | Restart the pipeline from a specific top-level step |
| POST | `/api/generation-jobs/<id>/restart-substep/` | Restart a graphic novel script substep for one pack, then fill any packs that never got a novel |
| POST | `/api/graphic-novel-pages/<page_id>/edit-image/` | Re-generate a page image from an edit prompt, using the current image as a visual reference. Stores the result in `edited_image` (original preserved) and auto-selects it. Body: `{"prompt": "..."}`. Asynchronous: validates synchronously, runs the image call in a background thread, returns **202** with the page `RUNNING`. Returns **409** if an edit is already running. |
| POST | `/api/graphic-novel-pages/<page_id>/redraw-image/` | Re-run the page's **original generation** payload (template-built prompt + previous page as reference) for a fresh roll of the same prompt — distinct from edit. No body. Stores the result in `edited_image` (original preserved) and auto-selects it (`prompt_used` tagged `[REDRAW]`). Asynchronous, same machinery as edit: returns **202** with the page `RUNNING` (or **409** if an image op is already running); poll `image-status/`. |
| GET | `/api/graphic-novel-pages/<page_id>/image-status/` | Poll target for the async edit/redraw: returns the page's image state (variant URLs + `generation_status`). The admin UI polls this every 10s until `COMPLETED`/`FAILED`. |
| POST | `/api/graphic-novel-pages/<page_id>/select-image/` | Choose which stored variant students see. Body: `{"variant": "original"｜"edited"}`. Reversible; neither file is deleted. Synchronous (instant DB flip). |
| POST | `/api/graphic-novels/<novel_id>/generate-audio/` | Generate read-along audio for every story page of a novel. Body: `{"regenerate": bool}`. Asynchronous: validates synchronously, runs TTS in a background thread, returns **202** (or **409** if a run is already in progress). |
| GET | `/api/graphic-novels/<novel_id>/audio-status/` | Poll target for audio generation: per-page `{status, audio_url, duration_ms, error}`. Admin UI polls every 5s. |
| POST | `/api/graphic-novel-pages/<page_id>/regenerate-audio/` | Re-run audio generation for a single page (async; **409** if that page is already running). |

### LLM Configuration (Admin only)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/admin/llm-config-sets/` | List the 3 config sets (id, name, position, is_active) |
| PUT | `/api/admin/llm-config-sets/<id>/` | Rename (`name`) and/or activate (`is_active: true` — deactivates the others; refuses to deactivate the active set) |
| GET/POST | `/api/admin/llm-sites/` | List/create LLM API sites (shared across sets) |
| PUT/DELETE | `/api/admin/llm-sites/<id>/` | Update/delete a site |
| GET/PUT | `/api/admin/llm-step-configs/` | List/bulk-update step-to-site+model mappings for a set. Set-scoped via `?set=<id>` (default = active set); returns `{set, configs}` |

---

## Frontend Routes

| Path | Component | Role |
|------|-----------|------|
| `/login` | Login | Public |
| `/student/dashboard` | StudentDashboard | STUDENT |
| `/student/practice` | PracticeView | STUDENT |
| `/student/learning-patterns` | LearningPatternsView | STUDENT |
| `/student/instructional/:packId` | InstructionalFlow | STUDENT |
| `/teacher/command-center` | CommandCenter | TEACHER, ADMIN |
| `/teacher/word-sets` | WordSetListView | TEACHER, ADMIN |
| `/teacher/word-sets/:setId` | WordSetDetailView | TEACHER, ADMIN |
| `/teacher/groups` | GroupManagementView | TEACHER, ADMIN |
| `/teacher/students/:studentId/progress` | StudentProgressDashboard | TEACHER, ADMIN |
| `/teacher/students/:studentId/patterns` | LearningPatternsView | TEACHER, ADMIN |
| `/teacher/generate/:setId` | GenerationWizard | ADMIN |
| `/teacher/generation-jobs/:jobId` | GenerationReview | ADMIN |
| `/teacher/llm-config` | LLMConfig | ADMIN |

---

## Key Business Logic

### Spaced Repetition (Practice Flow)
1. `NextPracticeWordView` finds words where `next_review_at ≤now`, `instructional_status = READY`, with questions in the student's Lexile range or with NULL Lexile score, excluding words already answered in the current session.
2. Selects a question matching the word's current mastery level and Lexile range. Hidden levels 6 and 7 ignore `suitable_levels` and can use any question for the word within the student's Lexile range.
3. `PracticeService.process_answer()` processes the answer atomically:
   - Correct: +1 mastery point. If accumulated points reach the current level's `points_to_promote`, promote to the next level.
   - Promotion uses accumulated mastery points; points are not reset on promotion.
   - Incorrect: -2 mastery points (min 0). If points fall below the previous level's promotion threshold, demote to the previous level.
   - Classifies response quality for non-retry submissions. Correct answers use a per-learner, per-question-type timing baseline only after 15 valid historical samples from the latest 50 persisted `UserAnswer` rows, filtering to `1 < duration_seconds < 100`.
   - Correct answers without enough timing history use `unclassified_correct`, which preserves the previous quality value of 1.2 and no interval factor.
   - When a baseline exists, fast/solid/slow correct answers are classified using the 25th and 80th percentile duration thresholds. A correct answer with `answer_switches > 0` is `switched_correct`.
   - Near-miss spelling typos return `is_typo=True` without recording an attempt. `SubmitAnswerView` stores a short-lived Django session flag, and the next first-attempt correct answer for that user/question becomes `typo_retry_correct`.
   - Updates `learning_speed` (adaptive multiplier): `0.3 * quality + 0.7 * old_speed`. Quality/interval factors are: fast correct `1.25/1.15`, solid correct `1.10/1.00`, slow correct `0.85/0.85`, switched correct `0.90/0.85`, typo-retry correct `0.90/0.85`, incorrect `0.50/0.50`, unclassified correct `1.20/1.00`.
   - Updates `next_review_at = now + timedelta(days=max(1.0, interval_days * learning_speed * interval_factor))`. The 1-day minimum prevents same-day repeat reviews.
   - Fragile correct answers can still promote, but if they promote, the next interval is capped at `old_level_interval_days * old_learning_speed` before applying the 1-day floor.
   - Awards XP: 5 base + 5 bonus (level ≤4) + 2 for new mastery.
   - Logs level changes to MasteryLevelLog.
   - Student-facing mastery statistics suppress logs where the displayed level does not change, such as transitions among Mastered and hidden levels 6-7.
   - Retries (`is_retry=True`) skip mastery/XP updates and only increment `retry_count`.
   - Submit responses include scheduling metadata: `response_quality`, `is_fragile`, `review_interval_days`, `next_review_at`, and `schedule_reason`.
4. Session summary analyzes strengths (correct words) and weaknesses (incorrect words + skill tags).

### Instructional Flow (Primer → Graphic Novel/Micro Story → Cloze)
1. Teacher assigns a word set to students → creates UserWordProgress with `instructional_status=PENDING` for words in packs, `READY` for words not in packs.
2. Student opens a pack → `InstructionalPackView` returns primer cards (with approved images), `story.type`, and cloze items. New packs prefer `graphic_novel` pages; legacy packs return `micro_story`.
3. Student completes the 3-step flow. `GraphicNovelReader` shows one 16:9 page image at a time (the lightweight JPEG companion, served via `student_image` to keep mobile load times low) with arrow/keyboard/swipe navigation, a sticky toolbar (title, page dots, "Done Reading" button), and a vocabulary overlay shown by default on each page. The "Done Reading" button appears with a 3-second delay on the last page to encourage reading before advancing. Legacy `MicroStoryView` still renders bold target words with tooltips.
4. On completion, `CompletePackView` flips all PENDING words in the pack to READY with `next_review_at=now`, making them available for SRS practice.

### Read-Along Audiobook (on-demand, admin-triggered — NOT a pipeline step)
- A completed graphic novel can have read-along audio generated per page (phase 1). The admin triggers it from the Generation Review page (`POST /api/graphic-novels/<id>/generate-audio/`); it runs in a background thread and the UI polls `audio-status/`. The same page also offers **per-page regeneration**: each page card in `GraphicNovelPageEditor.jsx` has its own Generate/Regen-audio button (`POST /api/graphic-novel-pages/<page_id>/regenerate-audio/`) so a single page whose TTS call failed mid-run can be refilled without re-synthesizing the whole novel; it reuses the same `audio-status/` poller and the novel's cached voice direction (no extra LLM call).
- **Voice director (one LLM call per novel)**: before synthesis, `voice_director.direct_novel(novel, pages)` sends every page's speech events to an LLM (configured under the `audiobook_director` step key) and gets back (1) a short Audio Profile + Director's Notes block per speaker and (2) the transcript with inline audio tags (`[excitedly]`, `[whispers]`, …) per the Gemini TTS prompting guide. The result is cached in `novel.metadata['voice_director']`, so per-page regeneration reuses it without a new LLM call. Each TTS call then uses the speaker's profile as its style prefix and speaks the tagged line. Degrades gracefully: any director failure falls back to the bare transcript text. Prompt `prompts/audiobook_voice_director.txt`. The prompt forbids slow-pace tags (`[slowly]`, `[one word at a time]`, …) — they compound the already-gentle kid-friendly delivery and make lines drag — and `_index_directed_events` strips any slow-pace cue from the directed text on the read path (`_strip_slow_tags()`), so even previously-cached director output is sanitized without re-running the LLM.
- Service package `backend/vocabulary/services/audiobook/`: `events.build_page_events` (pure — walks a page's `panel_descriptions` into ordered speech events, one narration box or dialogue line each, with pauses), `voice_director.direct_novel` (the per-novel director call described above), `voices.voice_for` (stable hero→prebuilt-voice map — Leo=Puck, Amara=Despina, Mei=Zephyr, Hugo=Achird; the narrator voice **contrasts the hero team's gender** so narrator and heroes stay distinct — any female hero on the team gives the male narrator Charon, an all-male team gives the female narrator Aoede, unknown team falls back to Aoede — resolved by `narrator_voice_for()` from `metadata['away_team']` + a `HERO_GENDERS` map; supporting characters hashed into a pool), `tts_client.synthesize` (isolated **native** `genai.Client` TTS call using the dedicated `GEMINI_TTS_*` settings; parses the sample rate from the response mime type; retries once), `stitch` (stdlib `wave` only — concatenates per-event PCM + silence into one WAV; no ffmpeg/pydub dependency), `encode.wav_bytes_to_mp3_bytes` (compresses the stitched WAV to a ~64 kbps mono MP3 via **`lameenc`** — a pure binary-wheel LAME encoder, again no ffmpeg/pydub), `generator.generate_novel_audio` (runs the director once, then continue-on-failure per page; skips the review page and already-COMPLETED pages unless `regenerate`).
- Spoken text is read verbatim from `panel_descriptions` (`narration` + `dialogue[].speaker/.text`) — no OCR. Output is one stitched WAV per page (24kHz/16-bit/mono), stored on `GraphicNovelPageAudio.audio`; right after the WAV is saved, `generator._save_mp3_companion` encodes a compressed MP3 to `audio_mp3` **best-effort** (a conversion failure is logged and never aborts the WAV — the student path falls back to the WAV via `student_audio`). The student instructional payload exposes `audio_url` per page using `student_audio` (MP3 preferred), so students stream the smaller file; the admin **review** content endpoints (`GenerationJobContentView`, `WordSetContentView`) keep serving the WAV via `audio.url` (shared `_graphic_novel_page_review_payload()` helper, COMPLETED audio only) so the inline player on the Generation Review page shows on load rather than only after a fresh generate-audio poll. Verified working end-to-end 2026-06-07 against the Vector TTS proxy.
- **Student playback** (`frontend/src/components/GraphicNovelReader.jsx`): each page shows a Listen/Pause button (when that page has audio) plus an **Auto-read** toggle switch (persisted in `localStorage` as `gnReaderAutoplay`, default on). With auto-read on, a page's audio starts automatically on arrival (including the first page and every manual page turn); audio resets/stops whenever the page changes (per-page only — no auto-advance). Toggling the switch mid-page never interrupts what is already playing (it only affects the next page turn, via an `autoplayRef`). The switch renders whenever the novel has any audio; the button only when the current page does.
- **Backfill**: existing pre-MP3 WAV rows get their MP3 companion via `python manage.py backfill_audio_mp3 [--dry-run]` (idempotent; skips anything that is not a 16-bit PCM WAV). Migration `0034_graphicnovelpageaudio_audio_mp3_and_more` adds the `audio_mp3` field.
- Model: `gemini-2.5-pro-preview-tts` (configurable via `GEMINI_TTS_MODEL`). Encoder dependency: `lameenc` (pinned in `requirements.txt`). Deferred: per-event timing/highlight sync, Opus encoding, ambience/SFX, cross-page auto-advance. Full production rules: `docs/feature_plan/lexi-legends-audiobook-production-bible.md`.

### XP & Level System
- Tier progression: BRONZE (1-20, 200 XP/level), SILVER (21-40, 300), GOLD (41-60, 400), PLATINUM (61-80, 500), DIAMOND (81+, 600).
- XP sources: correct answers (5-12 XP), focus streak bonus (up to 10 XP per session).
- Practice streak: consecutive days practiced. Freeze awarded every 3 days (max 5 freezes).

### Question Types (28 types across 8 skill categories)
| Category | Types |
|----------|-------|
| Definition Recall | DEFINITION_MC_SINGLE, DEFINITION_TRUE_FALSE, DEFINITION_MATCHING, REVERSE_DEFINITION_MC |
| Context & Nuance | CONTEXT_MC_SINGLE, CONTEXT_FILL_IN_BLANK, CONNOTATION_SORTING, DIALOGUE_COMPLETION_MC, NUANCE_CONTRAST_MC |
| Synonym & Antonym | SYNONYM_MC_SINGLE/MULTI/MATCHING, SYNONYM_IN_CONTEXT_MC, REVERSE_SYNONYM_IN_CONTEXT_MC, ANTONYM_MC_SINGLE/MATCHING, ODD_ONE_OUT_MC_SINGLE |
| Word Forms | WORD_FORM_MC, WORD_FORM_FILL_IN_BLANK |
| Syntax & Grammar | SENTENCE_SCRAMBLE |
| Spelling | SPELLING_FILL_IN_BLANK |
| Collocation & Usage | COLLOCATION_MC_SINGLE/FILL_IN_BLANK/MATCHING, REVERSE_COLLOCATION_MC |
| Conceptual Association | CONCEPTUAL_ASSOCIATION_MC_SINGLE, APPLICATION_MC, REVERSE_ASSOCIATION_MC |

### Word Set Immutability
Teachers/admins can add, remove, or change words before generation starts. Once a word set enters the generation lifecycle (`GENERATION_REQUESTED`, `GENERATING`, or `GENERATED`), the word set is locked and its words, packs, and details cannot be mutated. To add more words after generation, create a new word set.

---

## Configuration

### Environment Variables (`.env`)
- `DATABASE_URL` — MySQL connection string
- `GEMINI_API_KEY` / `GEMINI_BASE_URL` — Gemini API (word lookup, translations, pack grouping, primers, and question generation)
- `GEMINI_TTS_API_KEY` / `GEMINI_TTS_BASE_URL` / `GEMINI_TTS_MODEL` — read-along audiobook TTS, kept separate from the text Gemini config because audio needs the **native** generateContent API (an OpenAI-compatible text proxy usually does not serve it). `GEMINI_TTS_API_KEY` falls back to `GEMINI_API_KEY` if unset; leave `GEMINI_TTS_BASE_URL` empty to call Google directly, or point it at a proxy that serves the native Gemini TTS endpoint; `GEMINI_TTS_MODEL` defaults to `gemini-2.5-pro-preview-tts`.
- `ANTHROPIC_API_KEY` / `ANTHROPIC_BASE_URL` — Claude API (graphic novel script planning)
- `OPENAI_API_KEY` / `OPENAI_BASE_URL` — OpenAI API (GPT-Image-2 image generation)
- `QWEN_API_KEY` / `QWEN_BASE_URL` — SiliconFlow Qwen3 embeddings

### Key Settings (`config/settings.py`)
- `AUTH_USER_MODEL = 'users.CustomUser'`
- `CORS_ALLOWED_ORIGINS` — dev: `['http://localhost:5174']`; production: also includes `'http://106.52.164.47'`
- `CSRF_TRUSTED_ORIGINS` — same as above; must include production origin or login fails
- `EMBEDDING_SIMILARITY_THRESHOLD = 0.92`
- `GENERATION_WORDS_PER_PACK = 6`
- `GENERATION_DEFAULT_LEXILE = 650`
- `SUPPORTED_LANGUAGES`: zh-CN, zh-TW, ja, ko, es, vi, th, ar, pt, fr

### Development
- Backend: `python manage.py runserver 8001`
- Frontend: `npm run dev` (Vite on port 5174, proxies `/api` and `/media` to 8001)
- Tests: `pytest` (backend, with pytest-django + factory-boy)
- Django check: `python manage.py check`
- Backfill student JPEG companions for existing page images: `python manage.py backfill_jpeg_images [--dry-run]`
- Frontend build: `npx vite build`

