# vocab_app_v2 — Project Context

## Overview

A full-stack vocabulary learning application for K-8 students. Teachers create word sets, an AI pipeline generates instructional content (definitions, questions, stories, images), and students learn through a structured instructional flow (Primer → Story → Cloze Quiz) followed by spaced-repetition practice.

**Tech stack:** Django 5.2 + Django REST Framework (backend), React 19 + Vite 7 (frontend), MySQL database, session-based auth with CSRF tokens.

**Roles:** ADMIN (full access + AI generation), TEACHER (student/content management), STUDENT (learning + practice).

---

## Project Structure

```
vocab_app_v2/
├── backend/
│   ├── config/                    # Django project settings
│   │   ├── settings.py            # DB, CORS, DRF, LLM API keys, tier config
│   │   ├── urls.py                # /admin/, /api/ → vocabulary.urls
│   │   └── authentication.py      # CsrfExemptSessionAuthentication
│   ├── users/
│   │   └── models.py              # CustomUser (extends AbstractUser), StudentGroup
│   ├── vocabulary/
│   │   ├── models.py              # All domain models (see Models section)
│   │   ├── views/                 # API views organized by domain
│   │   │   ├── user_views.py      # Auth: login, logout, CSRF, user detail
│   │   │   ├── practice_views.py  # SRS practice: next word, submit answer, session summary
│   │   │   ├── dashboard_views.py # Student dashboard, teacher roster, student progress
│   │   │   ├── instructional_views.py  # Pack data, pack completion
│   │   │   ├── teacher_views.py   # Word/WordSet/Curriculum CRUD, student management
│   │   │   ├── group_views.py     # Student group CRUD
│   │   │   └── generation_views.py # AI pipeline: trigger, status, review, approve
│   │   ├── services/
│   │   │   ├── practice_service.py           # Answer processing, XP, mastery, streaks
│   │   │   ├── dashboard_service.py          # Roster analytics, learning patterns
│   │   │   ├── instructional_service.py      # Pack data assembly for students
│   │   │   ├── assignment_service.py         # Word set → student assignment
│   │   │   ├── generation_pipeline_service.py # 8-step AI content pipeline
│   │   │   ├── llm_service.py               # Claude + Gemini API wrappers
│   │   │   └── embedding_service.py          # Qwen3 embeddings for dedup
│   │   ├── prompts/               # LLM prompt templates (.txt files)
│   │   ├── serializers.py         # DRF serializers
│   │   ├── urls.py                # All API route registrations
│   │   ├── constants.py           # Question type → skill tag mappings
│   │   ├── permissions.py         # IsAdmin, IsTeacherOrAdmin, IsStudent
│   │   └── admin.py               # Django admin registrations
│   ├── tests/
│   │   ├── factories.py           # factory-boy factories for all models
│   │   ├── users/test_models.py
│   │   └── vocabulary/            # test_views, test_models, test_serializers, test_services
│   ├── requirements.txt
│   ├── pytest.ini
│   └── .env                       # DATABASE_URL, API keys (gitignored)
├── frontend/
│   ├── src/
│   │   ├── App.jsx                # Route definitions
│   │   ├── main.jsx               # Entry: UserProvider → ThemeProvider → App
│   │   ├── api/axiosConfig.js     # Axios instance, CSRF interceptor
│   │   ├── context/
│   │   │   ├── UserContext.jsx     # Auth state, login/logout/refresh
│   │   │   └── ThemeContext.jsx    # Student theme (5 themes, localStorage)
│   │   ├── pages/
│   │   │   ├── student/           # Dashboard, PracticeView, InstructionalFlow
│   │   │   ├── teacher/           # CommandCenter, WordSets, Groups, StudentProgress
│   │   │   ├── admin/             # GenerationWizard, GenerationReview
│   │   │   └── shared/            # LearningPatternsView
│   │   ├── components/            # Reusable UI (see Components section)
│   │   ├── hooks/                 # useTranslationVisibility
│   │   ├── constants/skillTags.js # Skill tag display names (student/teacher variants)
│   │   ├── styles/                # Plain CSS, student theme system
│   │   └── assets/sounds/         # correct.mp3, incorrect.mp3
│   ├── vite.config.js             # Port 5174, proxy /api + /media → localhost:8001
│   └── package.json               # React 19, axios, react-router-dom 7
```

---

## Data Models

### Core Vocabulary
- **Word** — `text`, `part_of_speech`, `source_context`, M2M `tags`
- **WordDefinition** — FK→Word, `definition_text`, `example_sentence`, `lexile_score`
- **DefinitionEmbedding** — OneToOne→WordDefinition, `embedding` (JSONField vector), `model_version` (Qwen3-Embedding-8B)
- **Translation** — Generic FK (ContentType), `field_name`, `language`, `translated_text`. Supports translating any model's text fields.

### Curriculum & Word Sets
- **Curriculum** — `name`
- **Level** — `name`, `order`
- **WordSet** — `title`, `unit_or_chapter`, `description`, `source_text`, `target_lexile`, `input_words` (JSONField), `generation_status` (DRAFT/TO_GENERATE/GENERATING/GENERATED), FK→Curriculum, FK→Level, FK→creator, M2M→Word
- **StudentWordSetAssignment** — FK→user, FK→WordSet, FK→assigned_by

### Instructional Layer
- **WordPack** — FK→WordSet, `label`, `order`. Groups ~5 words for instructional sequence.
- **WordPackItem** — FK→WordPack, FK→Word, `order`
- **PrimerCardContent** — OneToOne→Word, `syllable_text`, `kid_friendly_definition`, `example_sentence`
- **MicroStory** — FK→WordPack, `story_text` (target words in `**bold**`), `reading_level` (Lexile)
- **ClozeItem** — FK→WordPack, FK→Word, `sentence_text` (with `_______` blank), `correct_answer`, `distractors`
- **GeneratedImage** — FK→Word, `image` (ImageField), `prompt_used`, `status` (PENDING_REVIEW/APPROVED/REJECTED)
- **StudentPackCompletion** — FK→user, FK→WordPack. Completing a pack flips words from PENDING→READY.
### Mastery & Spaced Repetition
- **MasteryLevel** — `level_id` (PK), `level_name`, `interval_days`, `points_to_promote`
  - Level 1 (Novice): 0 days, 2 points
  - Level 2 (Beginner): 1 day, 3 points
  - Level 3 (Intermediate): 3 days, 4 points
  - Level 4 (Advanced): 7 days, 5 points
  - Level 5 (Mastered): 14 days, 6 points
- **UserWordProgress** — FK→user, FK→Word, FK→MasteryLevel, `mastery_points`, `next_review_date`, `last_reviewed_at`, `instructional_status` (READY/PENDING)
- **MasteryLevelLog** — FK→user, FK→Word, old_level, new_level, timestamp

### Questions & Practice
- **Question** — FK→Word, `question_type` (21 types), `question_text`, `options` (JSON), `correct_answers` (JSON), `explanation`, `lexile_score`, `difficulty_index`, `discrimination_index`, M2M→MasteryLevel (`suitable_levels`), FK→GenerationJob
- **PracticeSession** — FK→user, `start_time`, `end_time`
- **UserAnswer** — FK→PracticeSession, FK→user, FK→Question, `user_answer`, `is_correct`, `duration_seconds`, `answer_switches`, `answered_at`

### Generation Pipeline
- **GenerationJob** — FK→WordSet, FK→created_by, `job_type` (FULL_PIPELINE/QUESTIONS_ONLY/INSTRUCTIONAL_ONLY), `status` (PENDING/RUNNING/COMPLETED/FAILED/PARTIALLY_COMPLETED), `input_words` (JSON), `target_lexile`, `target_language`, counters (words/questions/primers/stories/cloze/images created), `last_completed_step` (for resume), `error_message`
- **GenerationJobLog** — FK→GenerationJob, `step`, `status`, `input_data`, `output_data`, `error_message`, `duration_seconds`

### Users
- **CustomUser** (extends AbstractUser) — `role` (ADMIN/TEACHER/STUDENT), `native_language`, `daily_question_limit` (default 20), `lexile_min`/`lexile_max`, M2M `students` (teacher→student), `current_practice_streak`, `last_practice_date`, `streak_freezes_available`, `xp_points`, `level`
- **StudentGroup** — FK→teacher, M2M→students, `name`, `description`

---

## 8-Step AI Content Generation Pipeline

The pipeline runs as a background thread, triggered by an admin via the GenerationWizard. Each step logs to GenerationJobLog. The pipeline supports resume from the last completed step on failure.

| Step | Name | What It Does |
|------|------|--------------|
| 1 | WORD_LOOKUP | LLM defines each word (POS, definition, example, source_context). Normalizes plurals/tense. |
| 2 | DEDUP | Embedding-based deduplication (cosine similarity ≥ 0.92). Creates Word, WordDefinition, DefinitionEmbedding. Reuses existing words if found. |
| 3 | TRANSLATION | LLM translates definition_text and example_sentence to target_language. Creates Translation records. |
| 4 | QUESTION_GEN | LLM generates 15 questions per word (3 per mastery level 1-5) in batches of 6 words. Creates Question records with suitable_levels M2M. |
| 5 | PACK_CREATION | LLM groups words into thematic packs of ~5. Creates WordPack + WordPackItem. For incremental jobs, adds new words to existing packs. |
| 6 | PRIMER_GEN | LLM generates syllable_text + kid_friendly_definition (under 600L). Creates PrimerCardContent. |
| 7 | STORY_CLOZE_GEN | LLM generates 80-150 word micro-story per pack + cloze items. Creates MicroStory + ClozeItem. Skips packs that already have stories. |
| 8 | IMAGE_GEN | Gemini generates one image per word. Creates GeneratedImage with PENDING_REVIEW status. Continues on individual failures. |

**LLM models used:** Claude claude-opus-4-6-thinking (steps 1-7), Gemini gemini-2.5-flash-image (step 8), Qwen3-Embedding-8B via SiliconFlow (step 2 embeddings).

**Prompt templates** are in `vocabulary/prompts/`: `word_lookup.txt`, `question_generation.txt`, `translation.txt`, `pack_grouping.txt`, `primer_generation.txt`, `story_cloze_generation.txt`.

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
| POST | `/api/practice/submit/` | Submit answer → mastery update, XP, streak |
| POST | `/api/practice/session-summary/` | Strengths/weaknesses for a session |
| POST | `/api/practice/apply-bonuses/` | Apply focus streak XP bonus |

### Student Dashboard
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/student/dashboard/` | Words due, streak, mastery breakdown, session goal |
| GET | `/api/student/words-by-level/<level_id>/` | Words at a mastery level |
| GET | `/api/student/learning-patterns/` | Error pattern analysis |
| GET | `/api/student/assigned-sets/` | Assigned word sets with packs and completion status |
### Instructional
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/instructional/packs/<pack_id>/` | Full pack data: primer cards (with images), Lexile-matched story, cloze items |
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
| POST | `/api/word-sets/<id>/add-words/` | Incremental: add new words + generate |
| GET | `/api/word-sets/<id>/latest-job/` | Most recent generation job |
| GET | `/api/word-sets/<id>/content/` | All generated content for word set |
| GET | `/api/generation-jobs/<id>/` | Job status |
| GET | `/api/generation-jobs/<id>/logs/` | Step-by-step logs |
| GET | `/api/generation-jobs/<id>/content/` | Content generated by this job |
| POST | `/api/generation-jobs/<id>/approve/` | Bulk-approve pending images |
| POST | `/api/generation-jobs/<id>/resume/` | Resume failed pipeline |

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
1. `NextPracticeWordView` finds words where `next_review_date ≤ today`, `instructional_status = READY`, within student's Lexile range, excluding words already answered in the current session.
2. Selects a question matching the word's current mastery level and Lexile range.
3. `PracticeService.process_answer()` processes the answer atomically:
   - Correct: +1 mastery point. If points ≥ `points_to_promote`, promote to next level, reset points.
   - Incorrect: -2 mastery points (min 0). If points < 0 at level > 1, demote to previous level.
   - Updates `next_review_date = today + level.interval_days`.
   - Awards XP: 5 base + 5 bonus (level ≥ 4) + 2 for new mastery.
   - Logs level changes to MasteryLevelLog.
4. Session summary analyzes strengths (correct words) and weaknesses (incorrect words + skill tags).

### Instructional Flow (Primer → Story → Cloze)
1. Teacher assigns a word set to students → creates UserWordProgress with `instructional_status=PENDING` for words in packs, `READY` for words not in packs.
2. Student opens a pack → `InstructionalPackView` returns primer cards (with approved images), a Lexile-matched story, and cloze items.
3. Student completes the 3-step flow (Primer → Story → Cloze Quiz).
4. On completion, `CompletePackView` flips all PENDING words in the pack to READY with `next_review_date=today`, making them available for SRS practice.

### XP & Level System
- Tier progression: BRONZE (1-20, 200 XP/level), SILVER (21-40, 300), GOLD (41-60, 400), PLATINUM (61-80, 500), DIAMOND (81+, 600).
- XP sources: correct answers (5-12 XP), focus streak bonus (up to 10 XP per session).
- Practice streak: consecutive days practiced. Freeze awarded every 3 days (max 5 freezes).

### Question Types (21 types across 8 skill categories)
| Category | Types |
|----------|-------|
| Definition Recall | DEFINITION_MC_SINGLE, DEFINITION_TRUE_FALSE, DEFINITION_MATCHING |
| Context & Nuance | CONTEXT_MC_SINGLE, CONTEXT_FILL_IN_BLANK, CONNOTATION_SORTING, DIALOGUE_COMPLETION_MC |
| Synonym & Antonym | SYNONYM_MC_SINGLE/MULTI/MATCHING, ANTONYM_MC_SINGLE/MATCHING, ODD_ONE_OUT_MC_SINGLE |
| Word Forms | WORD_FORM_MC, WORD_FORM_FILL_IN_BLANK |
| Syntax & Grammar | SENTENCE_SCRAMBLE |
| Spelling | SPELLING_FILL_IN_BLANK |
| Collocation & Usage | COLLOCATION_MC_SINGLE/FILL_IN_BLANK/MATCHING |
| Conceptual Association | CONCEPTUAL_ASSOCIATION_MC_SINGLE |

### Incremental Word Addition
When a word set already has `generation_status=GENERATED`, the admin can add new words via the "Add Words" flow. This creates a GenerationJob with only the new words, and the pipeline:
- Skips words already in the word set (case-insensitive dedup)
- Adds new words to existing packs (or creates new packs if needed)
- Skips story/cloze generation for packs that already have stories
- Only generates content for the new words

---

## Configuration

### Environment Variables (`.env`)
- `DATABASE_URL` — MySQL connection string
- `ANTHROPIC_API_KEY` / `ANTHROPIC_BASE_URL` — Claude API
- `GEMINI_API_KEY` / `GEMINI_BASE_URL` — Gemini API (image generation)
- `QWEN_API_KEY` / `QWEN_BASE_URL` — SiliconFlow Qwen3 embeddings

### Key Settings (`config/settings.py`)
- `AUTH_USER_MODEL = 'users.CustomUser'`
- `CORS_ALLOWED_ORIGINS = ['http://localhost:5174']`
- `EMBEDDING_SIMILARITY_THRESHOLD = 0.92`
- `GENERATION_WORDS_PER_PACK = 5`
- `GENERATION_DEFAULT_LEXILE = 650`
- `SUPPORTED_LANGUAGES`: zh-CN, zh-TW, ja, ko, es, vi, th, ar, pt, fr

### Development
- Backend: `python manage.py runserver 8001`
- Frontend: `npm run dev` (Vite on port 5174, proxies `/api` and `/media` to 8001)
- Tests: `pytest` (backend, with pytest-django + factory-boy)
- Django check: `python manage.py check`
- Frontend build: `npx vite build`

