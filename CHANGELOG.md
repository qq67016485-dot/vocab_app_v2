# Changelog

All notable changes to Vocab App V2 are documented in this file.

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
