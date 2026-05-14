# Changelog

All notable changes to Vocab App V2 are documented in this file.

## [Unreleased] - 2026-05-14

### Graphic Novel Instructional Flow
- Replaced new full-pipeline micro-story generation with AI-generated graphic novels for the instructional Read step
- Added `GraphicNovel` and `GraphicNovelPage` models plus migration `0018_graphic_novel`; each page stores one complete 1792x1024 landscape comic image and panel metadata
- Added `GenerationJob.graphic_novels_created` and new pipeline log steps `GRAPHIC_NOVEL_SCRIPT` and `GRAPHIC_NOVEL_IMAGES`
- Updated `PIPELINE_STEP_ORDER` to run `GRAPHIC_NOVEL_SCRIPT` and `GRAPHIC_NOVEL_IMAGES` after `PRIMER_GEN`; legacy `STORY_CLOZE_GEN` remains available for existing logs/manual use but is no longer used for new full-pipeline content
- Added `graphic_novel_script.txt` and `graphic_novel_page.txt` prompt templates
- `call_openai_image()` now accepts a `size` parameter; graphic novel pages request `1792x1024`, while existing vocabulary card images keep the default `1024x1024`
- `GET /api/instructional/packs/<pack_id>/` now returns `story.type = "graphic_novel"` with page data for new packs and falls back to `story.type = "micro_story"` for legacy packs
- Added `GraphicNovelReader` with 16:9 page display, arrow/keyboard/swipe navigation, page dots, tap-to-open vocabulary overlay, and final-page completion
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
- Generation status UI now shows the CREATIVE_DIRECTION step and switches to RUNNING immediately after resume
- OpenAI image generation now writes exact final image prompts to `temp/llm_logs/`; prompts remain stored on `GeneratedImage.prompt_used`

## [Unreleased] — 2026-04-30

### Image Generation Pipeline — Educational Value Rewrite
- Rewrote all 3 creative direction prompts (`creative_direction_character.txt`, `creative_direction_action.txt`, `creative_direction_elemental.txt`) to prioritize definition clarity over stylistic flourish
- Removed Hoyoverse/Genshin Impact aesthetic framing from creative direction and image generation prompts
- Added "Definition Clarity Check" instruction: LLM must verify a child could guess the word's meaning from the image alone
- Scenes now grounded in real-world contexts (gym, nature, classroom) instead of fantasy/elemental settings
- Anime cel-shading retained as rendering style only, not compositional driver
- Rewrote `image_master_style.txt` to emphasize definition as the most prominent visual element
- Updated `image_generation.txt` fallback prompt for consistency

### Image Generation Pipeline — Creative Direction Step (prior unreleased)
- Added 10-step pipeline (was 8): new CREATIVE_DIRECTION (step 8) and PICTURE_MATCH_GEN (step 10)
- Added `image_category` field on Word model (9 categories: EMOTION_STATE, DYNAMIC_ACTION, INVISIBLE_PROCESS, SENSORY_TRAIT, SPATIAL_RELATION, ABSTRACT_METAPHOR, PORTABLE_OBJECT, EPIC_SCALE, ICONIC_CHARACTER)
- Added `visual_scene` field on WordDefinition model
- Word lookup step now classifies each word into an image category
- Creative direction step routes words to category-specific prompts and generates visual_scene descriptions
- Image generation switched from Gemini to OpenAI GPT-Image-2
- Migration `0015_add_image_category_to_word`, `0016_add_visual_scene_and_creative_direction_step`

---

## [Unreleased] — 2026-04-23

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
- Spaced repetition intervals changed: Level 1: 0→1d, Level 2: 1→3d, Level 3: 3→7d, Level 4: 7→10d, Level 5: 14→20d
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
- `0002_add_daily_goal_bounds` — daily_goal_min, daily_goal_max, last_goal_prompt_date on CustomUser
- `0010_level_curriculum_alter_level_name_and_more` — Level FK to Curriculum, scoped uniqueness
- `0011_backfill_picture_word_match_lexile` — backfill lexile scores on PICTURE_WORD_MATCH questions
- `0012_add_retry_count_to_useranswer` — retry_count field on UserAnswer
- `0013_update_mastery_level_intervals` — updated spaced repetition intervals

- `0017_hidden_mastery_level` - adds hidden long-term mastery levels and updates the current spaced repetition schedule

### Tests
- Expanded test coverage: views, serializers, models, adapted services, embedding service

---

## [0.6.0] — 2026-04-06

### Beta Readiness — Bookmarks, Generation Requests, UX Fixes

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

## [0.5.0] — 2026-04-03

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

## [0.4.0] — 2026-03-24

### Generation Pipeline Quality & Token Reduction

**Pipeline-wide:**
- Switch from Claude Opus to Gemini 3.1 Pro for all text generation
- Add `call_gemini()` text generation function to llm_service
- Apply 15% Lexile offset so scaffolding text is easier than target vocab
- Add 512x512 square image generation with low resolution setting

**Step 1 — Word Lookup:**
- Remove per-word `source_context` from JSON output to save tokens
- Build `source_context` from job metadata instead

**Step 3 — Translation:**
- Rewrite prompt with two strategies: native equivalent for definitions, natural translation for example sentences
- Include term in items list for better context

**Step 4 — Questions:**
- Remove redundant WORD ENRICHMENT step that duplicated Steps 1 and 3
- Pass full definition and `example_sentence` from Step 1 directly
- Simplify output format: flat term + questions instead of nested word array

**Step 5 — Pack Grouping:**
- Add creative writer and curriculum architect roles
- Add `text_type` field (fiction/narrative_nonfiction) to WordPack model
- LLM evaluates word nature and assigns best text type per pack
- Change max words per pack from 5 to 6 with balanced distribution

**Step 6 — Primers:**
- Calibrate kid-friendly definitions to target Lexile level
- Add Lexile band guidelines (below 600L through above 1000L)

**Step 7 — Stories:**
- Rewrite prompt for engaging fiction and narrative non-fiction
- Fiction: high-stakes show-don't-tell scenes
- Narrative non-fiction: fascinating hooks and real-world contexts

**Step 8 — Images:**
- Square 1:1 aspect ratio prompt for vocabulary cards
- Low resolution (512x512) for faster generation

---

## [0.3.1] — 2026-03-14

### Pipeline & Image Fixes

- Auto-approve generated images, skip manual review step
- Update image generation model to `gemini-3.1-flash-image-preview`
- Clear existing words before running generation pipeline (prevents duplicates on re-run)
- Fix Gemini API call: combine system and user prompts when user_prompt is empty

---

## [0.3.0] — 2026-03-13

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

## [0.2.0] — 2026-03-01

### Complete Generation Pipeline & Practice Bug Fixes

- 8-step AI content generation pipeline (word lookup, dedup, translations, questions, packs, primers, stories/cloze, images) with resume support
- Incremental word addition to existing generated word sets
- Generation wizard with live status polling and review/approve UI
- Fix primer card images (query GeneratedImage model, not empty URLField)
- Fix spaced repetition: exclude already-answered words from session and dashboard due count
- Fix teacher roster due count to match student view (filter by READY status)
- Add Vite proxy for `/media` to serve generated images in dev

---

## [0.1.1] — 2026-02-28

### Admin Generation UI (Phase 5)

- Generation wizard, job progress monitor, and content review pages
- Backend endpoints for fetching generated content and bulk-approving images

---

## [0.1.0] — 2026-02-28

### Full-Stack Rebuild (Phases 1–4)

- Initial full-stack rebuild of Vocab App V2
- Django backend with REST API
- React frontend with Vite
- User management (teachers, students, groups)
- Word set CRUD and assignment workflow
- Spaced repetition practice engine
- Student and teacher dashboards
