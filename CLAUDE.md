# CLAUDE.md

## Project Overview

K-8 vocabulary learning web app with AI-generated instructional content, spaced repetition practice, and role-based access (admin, teacher, student). Target audience: ages 8–14, ESL learners.

## Tech Stack

- **Backend**: Django 5.2 + DRF 3.16, Python, MySQL
- **Frontend**: React 19 + Vite 7, plain CSS with theme system
- **LLMs**: Gemini (text generation + graphic novel scripts), OpenAI GPT-Image-2 (images), Qwen3 (embeddings via SiliconFlow). Anthropic SDK is wired for fallback but no active step uses it today.
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
- `ANTHROPIC_API_KEY` — Used when any pipeline step is configured to route through an Anthropic site
- `ANTHROPIC_BASE_URL` — Optional proxy for Anthropic API
- `OPENAI_API_KEY` — GPT-Image-2 for graphic novel images
- `OPENAI_BASE_URL` — Optional proxy for OpenAI API
- `QWEN_API_KEY` — Qwen3 embeddings via SiliconFlow
- `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`

Note: Which API keys are actually needed depends on which sites are configured in the LLM Configuration admin page. The `LLMSite` model references env var names; the backend resolves them at runtime.

MySQL driver: `pymysql` (pure Python, installed as MySQLdb via `config/__init__.py`). No C compiler needed.

Frontend dev server proxies `/api` and `/media` to `localhost:8001`.

## Key Architecture Decisions

- Spaced repetition uses response-quality-aware scheduling (fast/solid/slow affects intervals)
- Words transition PENDING → READY after instructional pack completion; only READY words enter SRS
- Mastery levels 6-7 are hidden from students (rolled into "Mastered" on dashboard)
- Generation pipeline is a modular package at `vocabulary/services/generation/`; the old single-file path (`generation_pipeline_service.py`) is a backwards-compatible shim that re-exports everything
- Generation pipeline has 8 steps with per-step resume capability. `_reconstruct_context` rebuilds `words_data` from the WORD_LOOKUP log's `word_lookup_snapshot` when dedup hasn't completed (prevents word loss on mid-dedup failures).
- Unified graphic novel generation: each pack produces one graphic novel at a length (5 or 6 pages) chosen by the router LLM per premise. Each premise declares `page_count_rationale` + `page_count` ∈ {5, 6}; the scorer picks a winner and carries the length forward; beat-sheet and final-script substeps dispatch to the matching prompt template via `GRAPHIC_NOVEL_BEAT_SHEET_TEMPLATES` / `GRAPHIC_NOVEL_SCRIPT_TEMPLATES` dicts.
- `GraphicNovel` model uses ForeignKey to WordPack with vestigial `channel` field (always `'5page'` for new rows; kept for legacy compatibility) and `unique_together = ('pack', 'channel')`. `novel.metadata['page_count']` stores the chosen length.
- Student-facing code (`instructional_service.py`) iterates saved `GraphicNovelPage` rows (length-agnostic)
- Graphic novel script substeps retry individually on failure (1 retry per substep); the orchestrator does not retry the entire GRAPHIC_NOVEL_SCRIPT step
- Substep-level restart is available via `POST /api/generation-jobs/{id}/restart-substep/` (accepts `pack_id` + `substep` key); loads prior substep artifacts from disk to reconstruct context
- Graphic novel script uses a 6-call Gemini workflow (team selector → router → scorer → cloze generation → beat sheet → final script) using per-step LLM config from the DB
- Cloze generation is a dedicated substep (index 3 in `GRAPHIC_NOVEL_SUBSTEPS`) that runs after premise scoring using only the winning premise + vocabulary words as context. It does NOT depend on the beat sheet or final script. Prompt: `graphic_novel_cloze.txt`. Config key: `gn_cloze_gen`. Artifact: `03b_cloze_generation.json`.
- Canon files from `backend/data/canon/` are loaded at runtime into script and image prompts via `canon_service.py`
- Canon is split by purpose: `team-selector-summaries.md` (team selection), `script-character-sheets.md` (narrative-only for router/scorer/beat sheet), `vault-summary-premises.md` (condensed vault for premises), full visual sheets collapsed via `collapse_markdown()` (final script + images)
- Script substeps use system/user prompt split — instructions in system, data in user message. No `{input_json}` template substitution for these steps.
- World context preamble: the shared Lexi Legends world paragraph lives in `prompts/graphic_novel_world_context.txt` and is injected at runtime by `_run_graphic_novel_substep` (inserted between the role line and step-specific instructions). Individual prompt templates do NOT contain the world context — edit the shared file to change world rules.
- Validator context: all graphic novel validators accept `(result, ctx=None)` where `ctx` is a `SubstepContext` dataclass (defined in `graphic_novel_validators.py`). The dataclass accumulates `target_terms`, `winning_premise`, `selected_away_team`, and `router_result`. Use `SubstepContext.from_input_summary(input_summary, **overrides)` to construct. No lambda closures for validators.
- Image prompts use prose panel formatting, per-character Ink color highlighting, and trimmed synopsis for pages 2+
- Vocab highlighting in image prompts: vocab words render in character's Ink color (orange for Hugo); surrounding caption text must be white/cream (never gold/yellow) for contrast
- Review page has no story title; uses story characters; review definitions sourced from `PrimerCardContent.kid_friendly_definition` (3-8 word phrases generated in primer step); fallback truncation of `WordDefinition` at 8 words
- Script prompt requires page 1 establishing panel (WHO/WHERE/WHAT) and final-page tension-before-resolution pacing (the final page is whichever the router chose — page 5 or page 6)
- The two beat-sheet prompt files (`graphic_novel_beat_sheet.txt` and `..._6page.txt`) and the two script files stay separate; runtime template dispatch picks the right one based on `winning_premise.page_count`. The 6-page beat sheet adds a "deepen" pacing note. `page_turn_question` is null for the final page.
- Pack grouping uses free-text `narrative_approach` (not a fixed engine list); downstream steps use `central_thread` (not `central_problem`) to allow non-conflict narratives
- Prompt schema ordering uses chain-of-thought: rationale/planning fields appear before decision fields (team_rationale before booleans, arc_planning + vocab_page_assignments before beat_sheet)
- Router schema: `vocab_integration_plan` appears before `premise` paragraph so model plans vocab mechanics before writing narrative
- Scorer schema: `dimension_rankings` scratchpad appears before `scores` array so model ranks premises per dimension before assigning numbers
- Beat sheet schema: `vocab_roles` and `ink_usage` appear before `beat_sheet` array so model defines Ink mechanics before writing page beats
- Final script schema: per-page `page_planning` object appears before `panels` array so model verifies text budget, target words, layout, and shot scales before generating panel content
- Canon files include per-character Lexi Mini examples in `team-selector-summaries.md` and `script-character-sheets.md` — grounds vocab integration as creature-summon mechanic, not generic magic
- Vocab semantic accuracy: target words must remain semantically true to the story's final resolution — never used as false accusations, rumors, or red herrings that get debunked (ESL learners build definitions from story outcomes)
- Lexi Mini summon limit (max 1 per story) enforced via `total_ink_activations_planned` counter declared before vocab arrays in router and beat_sheet. Constant: `GRAPHIC_NOVEL_MAX_MINI_SUMMONS_PER_STORY = 1` in `services/generation/constants.py`. JSON field name `total_ink_activations_planned` kept for backwards compat; semantically counts Mini summons.
- Team selection coin-flips solo vs dual hero teams via `sample_team_options()`; also decides `vault_framing`. Folio was fully removed (2026-05-27); `folio_present` is no longer a flag and the Folio character sheet is no longer loaded. Shades were fully removed (2026-05-27 prompt remediation); `shades_present` is no longer a flag in the team selector or downstream prompts (only survives as a DB metadata field on legacy rows via migration `0023`).
- Lexi Mini system (2026-05-27): writing a vocab word with a hero's tool summons a temporary monochromatic creature that physically acts out the definition. Tools (Hugo's carpenter's pencil, Leo's wax crayon, Amara's quill, Mei's marker) only appear on-page during a Mini summon. Hard cap of 0–1 Minis per story; most vocab integrates through dialogue/narration/world logic. No failure states — every summon succeeds. `GRAPHIC_NOVEL_ALLOWED_INTEGRATION_MODES` uses `lexi_mini_summon` (was `direct_ink_activation`); JSON keys `uses_direct_ink` and `ink_usage` retained for backwards compat.
- Vocab pedagogical anchors (2026-05-27): every router `vocab_integration_plan` item must carry a `pedagogical_anchor` of `{anchor_type, anchor_sketch}` where `anchor_type` ∈ `{demonstrated_action, near_synonym, category_example, visible_referent}` (`GRAPHIC_NOVEL_PEDAGOGICAL_ANCHOR_TYPES`). The final script propagates these into `vocab_anchors` on the page payload. Validator `_validate_vocab_integration_plan` rejects premises missing the anchor.
- Plot complexity caps (2026-05-27): each premise carries a `complexity_budget = {locations, secondary_characters, problem_thread}`. Location cap scales by chosen length via `max_locations_for_page_count(page_count)` helper — ≤2 for 5-page (`GRAPHIC_NOVEL_MAX_LOCATIONS_5PAGE`), ≤3 for 6-page (`GRAPHIC_NOVEL_MAX_LOCATIONS_6PAGE`); ≤2 secondary characters (`GRAPHIC_NOVEL_MAX_SECONDARY_CHARACTERS`). Beat-sheet validator `_validate_beat_complexity` enforces `setting_keys` count and `characters_featured ⊆ away_team ∪ secondary_characters`.
- Scoring dimensions (2026-05-27): `GRAPHIC_NOVEL_SCORING_DIMENSIONS = {narrative_clarity, visual_potential, vocabulary_integration, pedagogical_clarity, character_fit}`. Old dimensions (`narrative_engagement`, `ip_coherence`, `ink_over_reliance`, `originality`) were dropped to refocus the scorer on ESL teaching value. Scorer evaluates each premise against its own declared page_count (not a hardcoded 5); location ceiling is page-count-aware.
- Graphic novel image generation retries once on failure then stops; does not skip to later pages
- Admin per-page image editing (post-generation): `POST /api/graphic-novel-pages/{id}/edit-image/` (`{prompt}`) re-renders one page via OpenAI `images.edit` using the currently displayed image as reference; result saved to `GraphicNovelPage.edited_image` (original in `image` is never overwritten) and auto-selected. `POST /api/graphic-novel-pages/{id}/select-image/` (`{variant: original|edited}`) flips `use_edited_image`. Both admin-only, synchronous. Every read path uses the `display_image` property (edited if selected+present, else original), so the choice propagates to students, review, status, and cross-page continuity. UI: `GraphicNovelPageEditor.jsx`. Migration `0028`.
- Secondary character visual anchors: after the final script step, an extra LLM call generates a detailed visual reference sheet (~150 words) for secondary characters who have dialogue AND appear on non-consecutive pages. Stored in `novel.metadata['secondary_character_anchors']` (dict of `{name: anchor_text}`). Image prompt lookup (`_characters_for_graphic_novel_page`) checks `LEXI_CHARACTERS` first (hero → canon injection), then stored anchors (secondary → expanded description), then falls back to the brief `novel.characters` entry. Prompt template: `prompts/secondary_character_anchor.txt`. Uses `gn_final_script` config (no separate step key).
- LLM Configuration Matrix: `LLMSite` + `LLMStepConfig` models allow admins to configure which API site and model each pipeline step uses (primary + fallback). `llm_config_service.get_step_config(step_key)` returns cached config (5-min TTL). Provider types: `gemini_native`, `openai_compatible`, `anthropic`. Admin UI at `/teacher/llm-config`. API keys stored as env var references, resolved at runtime. Step keys include `gn_cloze_gen` for the dedicated cloze generation substep.
- Pipeline dispatch: orchestrator builds `[primary, primary, fallback]` attempt list from `LLMStepConfig` DB rows. Each graphic novel substep has its own config key. `_call_llm_with_config(site_config, system_prompt, user_prompt)` routes by `provider_type` field.
- `call_gemini` and `call_anthropic` accept optional `api_key`/`base_url` overrides for per-call routing. Empty `user_prompt` is collapsed into the user message for both Gemini proxy and Anthropic (prevents "messages is required" errors).
- Question generation batch size is 3 words per LLM call (reduced from 6) to avoid proxy timeout on slow models.
- Deduplication uses cosine similarity ≥ 0.92 on Qwen3 embeddings
- Translation step uses `term`-based matching (not substring matching on source_text); prompt returns `term` field in each translation object for reliable join
- Primer `kid_friendly_definition` is a concise 3-8 word phrase (not a sentence); used both on student primer cards and as the review page definition source
- Primer syllable breaks use phonetic (sound-based) splitting; single-syllable words output without dots
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
