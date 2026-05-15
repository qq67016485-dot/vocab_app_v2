# vocab_app_v2 鈥?Project Context

## Overview

A full-stack vocabulary learning application for K-8 students. Teachers create word sets, an AI pipeline generates instructional content (definitions, questions, graphic novels, and cloze items), and students learn through a structured instructional flow (Primer 鈫?Graphic Novel 鈫?Cloze Quiz; legacy packs may still show Micro Story) followed by spaced-repetition practice.

**Tech stack:** Django 5.2 + Django REST Framework (backend), React 19 + Vite 7 (frontend), MySQL database, session-based auth with CSRF tokens.

**Roles:** ADMIN (full access + AI generation), TEACHER (student/content management), STUDENT (learning + practice).

---

## Project Structure

```
vocab_app_v2/
鈹溾攢鈹€ backend/
鈹?  鈹溾攢鈹€ config/                    # Django project settings
鈹?  鈹?  鈹溾攢鈹€ settings.py            # DB, CORS, DRF, LLM API keys, tier config
鈹?  鈹?  鈹溾攢鈹€ urls.py                # /admin/, /api/ 鈫?vocabulary.urls
鈹?  鈹?  鈹斺攢鈹€ authentication.py      # CsrfExemptSessionAuthentication
鈹?  鈹溾攢鈹€ users/
鈹?  鈹?  鈹斺攢鈹€ models.py              # CustomUser (extends AbstractUser), StudentGroup
鈹?  鈹溾攢鈹€ vocabulary/
鈹?  鈹?  鈹溾攢鈹€ models.py              # All domain models (see Models section)
鈹?  鈹?  鈹溾攢鈹€ views/                 # API views organized by domain
鈹?  鈹?  鈹?  鈹溾攢鈹€ user_views.py      # Auth: login, logout, CSRF, user detail
鈹?  鈹?  鈹?  鈹溾攢鈹€ practice_views.py  # SRS practice: next word, submit answer, session summary
鈹?  鈹?  鈹?  鈹溾攢鈹€ dashboard_views.py # Student dashboard, teacher roster, student progress
鈹?  鈹?  鈹?  鈹溾攢鈹€ instructional_views.py  # Pack data, pack completion
鈹?  鈹?  鈹?  鈹溾攢鈹€ teacher_views.py   # Word/WordSet/Curriculum CRUD, student management
鈹?  鈹?  鈹?  鈹溾攢鈹€ group_views.py     # Student group CRUD
鈹?  鈹?  鈹?  鈹斺攢鈹€ generation_views.py # AI pipeline: trigger, status, review
鈹?  鈹?  鈹溾攢鈹€ services/
鈹?  鈹?  鈹?  鈹溾攢鈹€ practice_service.py           # Answer processing, XP, mastery, streaks
鈹?  鈹?  鈹?  鈹溾攢鈹€ dashboard_service.py          # Roster analytics, learning patterns
鈹?  鈹?  鈹?  鈹溾攢鈹€ instructional_service.py      # Pack data assembly for students
鈹?  鈹?  鈹?  鈹溾攢鈹€ assignment_service.py         # Word set 鈫?student assignment
鈹?  鈹?  鈹?  鈹溾攢鈹€ generation_pipeline_service.py # 8-step AI content pipeline
鈹?  鈹?  鈹?  鈹溾攢鈹€ llm_service.py               # Gemini + OpenAI API wrappers
鈹?  鈹?  鈹?  鈹斺攢鈹€ embedding_service.py          # Qwen3 embeddings for dedup
鈹?  鈹?  鈹溾攢鈹€ prompts/               # LLM prompt templates (.txt files)
鈹?  鈹?  鈹溾攢鈹€ serializers.py         # DRF serializers
鈹?  鈹?  鈹溾攢鈹€ urls.py                # All API route registrations
鈹?  鈹?  鈹溾攢鈹€ constants.py           # Question type 鈫?skill tag mappings
鈹?  鈹?  鈹溾攢鈹€ permissions.py         # IsAdmin, IsTeacherOrAdmin, IsStudent
鈹?  鈹?  鈹斺攢鈹€ admin.py               # Django admin registrations
鈹?  鈹溾攢鈹€ tests/
鈹?  鈹?  鈹溾攢鈹€ factories.py           # factory-boy factories for all models
鈹?  鈹?  鈹溾攢鈹€ users/test_models.py
鈹?  鈹?  鈹斺攢鈹€ vocabulary/            # test_views, test_models, test_serializers, test_services
鈹?  鈹溾攢鈹€ requirements.txt
鈹?  鈹溾攢鈹€ pytest.ini
鈹?  鈹斺攢鈹€ .env                       # DATABASE_URL, API keys (gitignored)
鈹溾攢鈹€ frontend/
鈹?  鈹溾攢鈹€ src/
鈹?  鈹?  鈹溾攢鈹€ App.jsx                # Route definitions
鈹?  鈹?  鈹溾攢鈹€ main.jsx               # Entry: UserProvider 鈫?ThemeProvider 鈫?App
鈹?  鈹?  鈹溾攢鈹€ api/axiosConfig.js     # Axios instance, CSRF interceptor
鈹?  鈹?  鈹溾攢鈹€ context/
鈹?  鈹?  鈹?  鈹溾攢鈹€ UserContext.jsx     # Auth state, login/logout/refresh
鈹?  鈹?  鈹?  鈹斺攢鈹€ ThemeContext.jsx    # Student theme (5 themes, localStorage)
鈹?  鈹?  鈹溾攢鈹€ pages/
鈹?  鈹?  鈹?  鈹溾攢鈹€ student/           # Dashboard, PracticeView, InstructionalFlow
鈹?  鈹?  鈹?  鈹溾攢鈹€ teacher/           # CommandCenter, WordSets, Groups, StudentProgress
鈹?  鈹?  鈹?  鈹溾攢鈹€ admin/             # GenerationWizard, GenerationReview
鈹?  鈹?  鈹?  鈹斺攢鈹€ shared/            # LearningPatternsView
鈹?  鈹?  鈹溾攢鈹€ components/            # Reusable UI (see Components section)
鈹?  鈹?  鈹溾攢鈹€ hooks/                 # useTranslationVisibility
鈹?  鈹?  鈹溾攢鈹€ constants/skillTags.js # Skill tag display names (student/teacher variants)
鈹?  鈹?  鈹溾攢鈹€ styles/                # Plain CSS, student theme system
鈹?  鈹?  鈹斺攢鈹€ assets/sounds/         # correct.mp3, incorrect.mp3
鈹?  鈹溾攢鈹€ vite.config.js             # Port 5174, proxy /api + /media 鈫?localhost:8001
鈹?  鈹斺攢鈹€ package.json               # React 19, axios, react-router-dom 7
```

---

## Data Models

### Core Vocabulary
- **Word** - `text`, `part_of_speech`, `source_context`, M2M `tags`
- **WordDefinition** - FK to Word, `definition_text`, `example_sentence`, `lexile_score`
- **DefinitionEmbedding** 鈥?OneToOne鈫扺ordDefinition, `embedding` (JSONField vector), `model_version` (Qwen3-Embedding-8B)
- **Translation** 鈥?Generic FK (ContentType), `field_name`, `language`, `translated_text`. Supports translating any model's text fields.

### Curriculum & Word Sets
- **Curriculum** 鈥?`name`
- **Level** 鈥?`name`, `order`
- **WordSet** 鈥?`title`, `unit_or_chapter`, `description`, `source_text`, `target_lexile`, `input_words` (JSONField), `generation_status` (DRAFT/TO_GENERATE/GENERATING/GENERATED), FK鈫扖urriculum, FK鈫扡evel, FK鈫抍reator, M2M鈫扺ord
- **StudentWordSetAssignment** 鈥?FK鈫抲ser, FK鈫扺ordSet, FK鈫抋ssigned_by

### Instructional Layer
- **WordPack** 鈥?FK鈫扺ordSet, `label`, `text_type` (fiction/narrative_nonfiction), `order`. Groups ~6 words for instructional sequence.
- **WordPackItem** 鈥?FK鈫扺ordPack, FK鈫扺ord, `order`
- **PrimerCardContent** 鈥?OneToOne鈫扺ord, `syllable_text`, `kid_friendly_definition`, `example_sentence`
- **GraphicNovel** 鈥?OneToOne鈫扺ordPack, `title`, `synopsis`, `style_prompt`, `reading_level`, `created_at`. New generated packs use this as the Story/Read step.
- **GraphicNovelPage** 鈥?FK鈫扜raphicNovel, `page_number`, `image`, `prompt_used`, page image generation tracking (`generation_status`, `generation_attempts`, `generation_error`, `generation_started_at`, `generation_completed_at`), `panel_count`, `layout_description`, `panel_descriptions` (JSON accessibility/tooltip metadata), `vocab_words_used`. Each record stores one complete 1792x1024 landscape comic page image containing 1-4 panels.
- **MicroStory** 鈥?FK鈫扺ordPack, `story_text` (target words in `**bold**`), `reading_level` (Lexile). Legacy format retained so existing word sets keep working.
- **ClozeItem** 鈥?FK鈫扺ordPack, FK鈫扺ord, `sentence_text` (with `_______` blank), `correct_answer`, `distractors`
- **StudentPackCompletion** 鈥?FK鈫抲ser, FK鈫扺ordPack. Completing a pack flips words from PENDING鈫扲EADY.
### Mastery & Spaced Repetition
- **MasteryLevel** 鈥?`level_id` (PK), `level_name`, `interval_days`, `points_to_promote`
  - Fields include `is_hidden`; hidden levels are used for long-term scheduling but not exposed as separate student-facing mastery labels.
  - Level 1 (Novice): 1 day, promotes at 2 points
  - Level 2 (Familiar): 3 days, promotes at 4 points
  - Level 3 (Confident): 7 days, promotes at 7 points
  - Level 4 (Proficient): 10 days, promotes at 10 points
  - Level 5 (Mastered): 17 days, promotes at 15 points
  - Level 6 (Long-Term Retention): 30 days, promotes at 25 points, hidden from student-facing level labels
  - Level 7 (Long-Term Mastery): 60 days, promotes at 999 points, hidden terminal level
  - Student dashboards roll hidden level 6 and 7 words into the visible Mastered bucket. Daily/weekly deltas ignore transitions that stay inside that displayed bucket, so 5->6, 6->7, 7->6, and 6->5 do not reveal hidden levels.
- **UserWordProgress** 鈥?FK鈫抲ser, FK鈫扺ord, FK鈫扢asteryLevel, `mastery_points`, `next_review_at` (DateTimeField), `last_reviewed_at`, `learning_speed` (adaptive multiplier, default 1.0), `instructional_status` (READY/PENDING)
- **MasteryLevelLog** 鈥?FK鈫抲ser, FK鈫扺ord, old_level, new_level, timestamp

### Questions & Practice
- **Question** 鈥?FK鈫扺ord, `question_type` (28 types), `question_text`, `options` (JSON), `correct_answers` (JSON), `explanation`, `lexile_score`, `difficulty_index`, `discrimination_index`, M2M鈫扢asteryLevel (`suitable_levels`), FK鈫扜enerationJob
- **PracticeSession** 鈥?FK鈫抲ser, `start_time`, `end_time`
- **UserAnswer** 鈥?FK鈫扨racticeSession, FK鈫抲ser, FK鈫扱uestion, `user_answer`, `is_correct`, `duration_seconds`, `answer_switches`, `answered_at`, `retry_count`. Persisted first-attempt durations and answer switches are used for response-quality scheduling baselines.

### Generation Pipeline
- **GenerationJob** 鈥?FK鈫扺ordSet, FK鈫抍reated_by, `job_type` (FULL_PIPELINE/QUESTIONS_ONLY/INSTRUCTIONAL_ONLY), `status` (PENDING/RUNNING/COMPLETED/FAILED/PARTIALLY_COMPLETED), `input_words` (JSON), `target_lexile`, `target_language`, counters (words/questions/primers/stories/graphic_novels/cloze created), `last_completed_step` (for resume), `error_message`
- **GenerationJobLog** 鈥?FK鈫扜enerationJob, `step`, `status`, `input_data`, `output_data`, `error_message`, `duration_seconds`

### Users
- **CustomUser** (extends AbstractUser) 鈥?`role` (ADMIN/TEACHER/STUDENT), `native_language`, `daily_question_limit` (default 30), `daily_goal_min`, `daily_goal_max`, `last_goal_prompt_date`, `lexile_min`/`lexile_max`, M2M `students` (teacher鈫抯tudent), `current_practice_streak`, `last_practice_date`, `streak_freezes_available`, `xp_points`, `level`
- **StudentGroup** 鈥?FK鈫抰eacher, M2M鈫抯tudents, `name`, `description`

---

## 8-Step AI Content Generation Pipeline

The pipeline runs as a background thread, triggered by an admin via the GenerationWizard. Each step logs to GenerationJobLog. The pipeline supports resume from the last completed step on failure. Gemini-backed content steps use an automatic fallback policy: first attempt with `gemini-3.1-pro-preview`, one retry with the same model, then one retry with `gemini-3-pro-preview`. Retry attempts are also written to `GenerationJobLog` with attempt/model/next_model/error details.

| Step | Name | What It Does |
|------|------|--------------|
| 1 | WORD_LOOKUP | LLM defines each word (POS, definition, example sentence). Normalizes plurals/tense. |
| 2 | DEDUP | Embedding-based deduplication (cosine similarity 鈮?0.92). Creates Word, WordDefinition, DefinitionEmbedding. Reuses existing words if found. |
| 3 | TRANSLATION | LLM translates definition_text and example_sentence to target_language. Creates Translation records. |
| 4 | QUESTION_GEN | LLM generates 15 questions per word (3 per mastery level 1-5) in batches of 6 words. Creates Question records with suitable_levels M2M. |
| 5 | PACK_CREATION | LLM groups words into thematic packs of ~6. Creates WordPack + WordPackItem. On resume, adds any unpacked generated words to existing packs. |
| 6 | PRIMER_GEN | LLM generates syllable_text + kid_friendly_definition (under 600L). Creates PrimerCardContent. |
| 7A | GRAPHIC_NOVEL_SCRIPT | Gemini generates one graphic novel script per pack plus cloze items. Creates GraphicNovel, GraphicNovelPage metadata, and ClozeItem. Skips packs that already have a graphic novel. |
| 7B | GRAPHIC_NOVEL_IMAGES | OpenAI GPT-Image-2 generates one 1792x1024 landscape image per GraphicNovelPage. Each page tracks `PENDING`/`RUNNING`/`COMPLETED`/`FAILED`, attempts, and errors. The step saves successful pages, fails if any page fails, and Resume retries only missing/failed pages. This is the final active step for new full-pipeline generation. |

`STORY_CLOZE_GEN` remains a valid `GenerationJobLog.Step` enum for legacy/manual testing history, but it is no longer part of `PIPELINE_STEP_ORDER` for new full-pipeline generation.

**LLM models used:** Gemini `gemini-3.1-pro-preview` is the default for content-generation steps 1, 3-7A; `gemini-3-pro-preview` is the backup model after one same-model retry. OpenAI GPT-Image-2 generates graphic novel page images in step 7B. Qwen3-Embedding-8B via SiliconFlow handles step 2 embeddings.

**Prompt templates** are in `vocabulary/prompts/`: `word_lookup.txt`, `question_generation_A.txt`, `question_generation_B.txt`, `translation.txt`, `pack_grouping.txt`, `primer_generation.txt`, `graphic_novel_script.txt`, `graphic_novel_page.txt`, `story_cloze_generation.txt` (legacy/manual).

**Generation logs:** LLM text calls and OpenAI graphic novel page image calls write full prompt/response or prompt/status logs to `temp/llm_logs/`. Graphic novel page prompts are stored on `GraphicNovelPage.prompt_used`. `GRAPHIC_NOVEL_IMAGES` also writes per-page RUNNING progress logs with page id, pack label, page number, and attempt.

**Long-running job DB handling:** Generation runs in a background thread and can spend minutes inside Gemini/OpenAI calls. The pipeline releases stale Django/MySQL connections before and after slow LLM/image calls, and closes old connections when full-pipeline, resume, or restart execution exits. This prevents background generation from holding database connections while the admin status page polls job/log endpoints.

**Admin status polling:** `GenerationJobStatus` polls `/api/generation-jobs/<id>/` and `/api/generation-jobs/<id>/logs/` every 10 seconds. The status and logs views display the new `Graphic Novel Script` and `Graphic Novel Images` step labels plus per-page image status from `graphic_novel_image_pages`. If a job stalls for 15 minutes with no log activity, the status endpoint marks the job FAILED, records a FAILED log for the active step, resets the word set out of `GENERATING`, and marks any RUNNING graphic novel page FAILED. Resume then restarts from `GRAPHIC_NOVEL_IMAGES` when `last_completed_step` is `GRAPHIC_NOVEL_SCRIPT`; completed pages are skipped and only missing/failed pages are retried.

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
| POST | `/api/practice/submit/` | Submit answer 鈫?mastery update, XP, streak, response-quality scheduling metadata |
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
| POST | `/api/instructional/packs/<pack_id>/complete/` | Mark pack complete 鈫?flips words PENDING鈫扲EADY |

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

---

## Key Business Logic

### Spaced Repetition (Practice Flow)
1. `NextPracticeWordView` finds words where `next_review_at 鈮?now`, `instructional_status = READY`, with questions in the student's Lexile range or with NULL Lexile score, excluding words already answered in the current session.
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
   - Awards XP: 5 base + 5 bonus (level 鈮?4) + 2 for new mastery.
   - Logs level changes to MasteryLevelLog.
   - Student-facing mastery statistics suppress logs where the displayed level does not change, such as transitions among Mastered and hidden levels 6-7.
   - Retries (`is_retry=True`) skip mastery/XP updates and only increment `retry_count`.
   - Submit responses include scheduling metadata: `response_quality`, `is_fragile`, `review_interval_days`, `next_review_at`, and `schedule_reason`.
4. Session summary analyzes strengths (correct words) and weaknesses (incorrect words + skill tags).

### Instructional Flow (Primer 鈫?Graphic Novel/Micro Story 鈫?Cloze)
1. Teacher assigns a word set to students 鈫?creates UserWordProgress with `instructional_status=PENDING` for words in packs, `READY` for words not in packs.
2. Student opens a pack 鈫?`InstructionalPackView` returns primer cards (with approved images), `story.type`, and cloze items. New packs prefer `graphic_novel` pages; legacy packs return `micro_story`.
3. Student completes the 3-step flow. `GraphicNovelReader` shows one 16:9 page image at a time with arrow/keyboard/swipe navigation, page dots, and a tap-to-open vocabulary overlay. Legacy `MicroStoryView` still renders bold target words with tooltips.
4. On completion, `CompletePackView` flips all PENDING words in the pack to READY with `next_review_at=now`, making them available for SRS practice.

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
- `DATABASE_URL` 鈥?MySQL connection string
- `GEMINI_API_KEY` / `GEMINI_BASE_URL` 鈥?Gemini API (text generation in pipeline)
- `OPENAI_API_KEY` / `OPENAI_BASE_URL` 鈥?OpenAI API (GPT-Image-2 image generation)
- `QWEN_API_KEY` / `QWEN_BASE_URL` 鈥?SiliconFlow Qwen3 embeddings

### Key Settings (`config/settings.py`)
- `AUTH_USER_MODEL = 'users.CustomUser'`
- `CORS_ALLOWED_ORIGINS = ['http://localhost:5174']`
- `EMBEDDING_SIMILARITY_THRESHOLD = 0.92`
- `GENERATION_WORDS_PER_PACK = 6`
- `GENERATION_DEFAULT_LEXILE = 650`
- `SUPPORTED_LANGUAGES`: zh-CN, zh-TW, ja, ko, es, vi, th, ar, pt, fr

### Development
- Backend: `python manage.py runserver 8001`
- Frontend: `npm run dev` (Vite on port 5174, proxies `/api` and `/media` to 8001)
- Tests: `pytest` (backend, with pytest-django + factory-boy)
- Django check: `python manage.py check`
- Frontend build: `npx vite build`

