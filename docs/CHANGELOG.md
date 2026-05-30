# Changelog

All notable changes to Vocab App V2 are documented in this file.

## [Unreleased] - 2026-05-31 (admin per-page image editing + variant selection)

### Added — Edit & Choose Graphic Novel Page Images
- Admins can now refine any single graphic novel page image from the GenerationReview screen, without re-running the pipeline.
- **Edit endpoint** `POST /api/graphic-novel-pages/<page_id>/edit-image/` (admin-only): takes `{"prompt": "..."}`, re-renders the page through OpenAI's existing `images.edit` path (the same call used for cross-page style continuity), passing the **currently displayed** image as the visual reference. Synchronous (~30-60s, one billed GPT-Image-2 call). Returns both variant URLs + which is active.
- **Select endpoint** `POST /api/graphic-novel-pages/<page_id>/select-image/` with `{"variant": "original"｜"edited"}` (admin-only): flips which stored variant is shown. Reversible; validates an edited image exists before selecting it.
- **Model** (`GraphicNovelPage`): new `edited_image` (ImageField) and `use_edited_image` (Boolean) fields, plus `display_image` and `has_edited_image` properties. **The original `image` is never overwritten** — edits land in `edited_image`. Migration `0028_graphicnovelpage_edited_image_and_more`.
- **Read paths updated to `display_image`** so the admin's choice propagates everywhere: student instructional flow (`instructional_service.py`), both content serializers + the per-page status helper (`generation_views.py`), and the pipeline's cross-page continuity reference (`graphic_novel_images.py`).
- **Frontend** (`GraphicNovelPageEditor.jsx`, new): per-page card with an edit-prompt box and an Original/Edited variant picker (✓ marks the live variant). `GenerationReview.jsx` renders it and merges edited pages back into state with cache-busted image URLs.

### Fixed — Stale-Job Timeout Detection Test
- `test_stale_running_job_marks_running_graphic_page_failed` set job activity to 20 minutes ago, but `STALE_JOB_THRESHOLD_SECONDS` is 1800 (30 min), so the job correctly stayed RUNNING and the assertion failed. This is the "1 pre-existing unrelated failure" referenced in prior changelog entries. Bumped the test's log/page timestamps to 31 minutes so they're past the threshold. The view code was correct; only the test timing was wrong.

### Test
- 5 new edit/select endpoint tests (success preserves original + stores edit, variant round-trip, select-edited-without-edit 400, unknown-variant 400, student-forbidden 403). Full `TestGenerationViews` + `TestInstructionalPackView` suites pass with no remaining known failures.

## [Unreleased] - 2026-05-30 (admin UI pipeline-order sync)

### Fixed — Admin Views Now Reflect Current Pipeline Order
- **Generation Job status view** (`GenerationJobStatus.jsx`): the step list and the "Restart Step" dropdown showed `Pack Creation` before `Primer Generation`, contradicting the backend `PIPELINE_STEP_ORDER` (which runs `PRIMER_GEN` before `PACK_CREATION`). Reordered the frontend `PIPELINE_STEPS` constant to match.
- **Graphic Novel substep accordion**: the script step now always renders a collapsible accordion. Before the pipeline reaches the step (no per-pack data yet), it shows a "Planning Substeps (preview)" list of all 6 canonical substeps as PENDING, so the workflow is visible ahead of time. A new frontend `GRAPHIC_NOVEL_SUBSTEPS` constant mirrors `services/generation/constants.py`.
- **Generation view substep skeleton** (`generation_views.py`): `GRAPHIC_NOVEL_SCRIPT_SUBSTEPS` was missing `cloze_generation` (added at index 3 in the 2026-05-29 cloze separation). Aligned it with the canonical 6-substep order; this also enables the working cloze restart button.
- **LLM Config step matrix** (`/teacher/llm-config`): the Step Configuration tab rendered steps **alphabetically** (`order_by('step_key')`), scrambling the GN substeps (Beat Sheet, Cloze, Final Script, Premise Scoring, Router…). `llm_config_views.py` now sorts both the GET and PUT responses by `LLMStepConfig.StepKey` enum declaration order via a `_STEP_KEY_ORDER` index map, so the table follows true execution order.
- **`LLMStepConfig.StepKey` enum** (`models.py`): swapped `PACK_CREATION` and `PRIMER_GEN` so the enum declaration order matches pipeline execution order. Migration `0027_alter_llmstepconfig_step_key` (choices metadata only — no column or data change).

## [Unreleased] - 2026-05-30 (resume word-loss fix)

### Fixed — Pipeline Resume Losing Words After Mid-Dedup Failure
- When the dedup step failed partway through (e.g., embedding API timeout after processing 2 of 6 words), resuming the pipeline would only carry forward the partially-persisted words instead of the full set.
- Root cause: `_reconstruct_context` built `words_data` from the incomplete `word_set.words` when no completed DEDUP log existed, ignoring the full word list available in the WORD_LOOKUP log.
- Fix: `_reconstruct_context` now falls back to the WORD_LOOKUP log's `word_lookup_snapshot` when no completed DEDUP log is found. Added `_latest_word_lookup_snapshot()` helper in `step_word_lookup.py`.

## [Unreleased] - 2026-05-30 (pipeline clarity refactor)

### Refactor — Prompt & Validator Consolidation
- **World context preamble extracted**: the ~60-word Lexi Legends world paragraph that was duplicated across 7 graphic novel prompt files now lives in a single `prompts/graphic_novel_world_context.txt`. Runtime injection happens in `_run_graphic_novel_substep` (between role line and step instructions). Prompt templates are shorter and world-rule changes need only one edit.
- **Scorer prompt parameterized**: `graphic_novel_premise_scorer.txt` no longer hardcodes "5 pages". Each premise is evaluated against its declared `page_count` (5 or 6). Location ceiling is page-count-aware (≤2 for 5-page, ≤3 for 6-page). Directly improves scoring quality for 6-page premises.
- **Uniform validator context**: introduced `SubstepContext` dataclass in `graphic_novel_validators.py`. All graphic novel validators now accept `(result, ctx=None)` uniformly. Eliminated all lambda closures and ad-hoc `*_validator_summary` dicts from `graphic_novel_script.py`. Context holds `target_terms`, `winning_premise`, `selected_away_team`, `router_result`.
- **Placeholder comments removed**: 9 dead `# __PLACEHOLDER__` comments cleaned from `graphic_novel_script.py` and `graphic_novel_images.py`.

### Test
- 250 tests passing (1 pre-existing unrelated failure in stale-job timeout detection view).

## [Unreleased] - 2026-05-29 (cloze generation separated)

### Changed — Cloze Generation as Dedicated Substep
- Cloze quiz generation moved out of the Final Script + Self-Check substep into its own dedicated substep (`cloze_generation`, index 3 in `GRAPHIC_NOVEL_SUBSTEPS`).
- Runs after premise scoring using only the winning premise + vocabulary words as context (no dependency on beat sheet or final script).
- New prompt template: `backend/vocabulary/prompts/graphic_novel_cloze.txt`.
- New LLM step config key: `gn_cloze_gen` (seeded via migration 0026).
- New validator: `_validate_graphic_novel_cloze_result` in `graphic_novel_validators.py`.
- Artifact file: `03b_cloze_generation.json` in the pack artifact directory.
- Final script prompts (5-page and 6-page) no longer mention or return `cloze_items`.
- Substep order is now: team_selection → router_premises → premise_scoring → cloze_generation → beat_sheet_vocab_roles → final_script_self_check (6 substeps total).
- Motivation: cleaner script generation prompt lets the LLM focus purely on narrative craft, improving script quality.

### Test
- All 335 tests passing (1 pre-existing unrelated failure in stale-job timeout detection).

## [Unreleased] - 2026-05-29 (pipeline reorder + definition consolidation)

### Changed — Pipeline Step Order
- Swapped Primer Generation (now step 5) and Pack Creation (now step 6) so that Pack Creation is adjacent to the graphic novel steps it feeds.

### Changed — Review Definitions Consolidated into Primer Step
- Primer `kid_friendly_definition` changed from 1-2 sentence definitions to concise 3-8 word phrases suitable for vocabulary review cards.
- Removed `review_definitions` generation from the graphic novel script prompt (both 5-page and 6-page variants).
- Review page image generation now reads definitions from `PrimerCardContent.kid_friendly_definition` instead of `novel.metadata['review_definitions']`.
- Fallback: if a word has no `PrimerCardContent`, truncates `WordDefinition` to 8 words (unchanged).

## [Unreleased] - 2026-05-29 (graphic novel module split)

### Refactor — Split `step_graphic_novel.py` into Four Sibling Modules
- The 2003-line `vocabulary/services/generation/step_graphic_novel.py` was split into four files grouped by responsibility, with the original path kept as a thin re-export facade.
  - `graphic_novel_helpers.py` (~540 lines) — formatting helpers, artifact I/O, substep runner, character-color constants, secondary-character anchor generation, small pure helpers.
  - `graphic_novel_validators.py` (~400 lines) — every `_validate_*` function (team, router, scoring, beat, beat-complexity, vocab-anchors, script).
  - `graphic_novel_script.py` (~820 lines) — `_step_graphic_novel_script` and `restart_graphic_novel_from_substep`.
  - `graphic_novel_images.py` (~310 lines) — `_step_graphic_novel_images`.
  - `step_graphic_novel.py` (~95 lines) — facade that re-exports the public surface used by `__init__.py`, `orchestrator.py`, `generation_pipeline_service.py`, and the test suite.
- No behavior change. Public import paths (e.g. `from vocabulary.services.generation.step_graphic_novel import _step_graphic_novel_script, _validate_graphic_novel_router_result, _find_secondary_characters_needing_anchors, ...`) continue to work unchanged.

### Test
- Full graphic novel test module (`tests/vocabulary/test_generation_pipeline_service.py`) green: 57 passing, no test edits required.

## [Unreleased] - 2026-05-28

### Added — LLM Configuration Matrix (Admin)
- **LLMSite model**: defines API proxy endpoints with name, base URL, provider type (`gemini_native` / `openai_compatible` / `anthropic`), and API key env var reference. Keys stay in `.env`; the model stores only the env var name and resolves at runtime.
- **LLMStepConfig model**: maps each of 10 text-generation pipeline steps to a primary and fallback site+model pair. Steps: `word_lookup`, `translation`, `question_gen`, `pack_creation`, `primer_gen`, `gn_team_selection`, `gn_router_premises`, `gn_premise_scoring`, `gn_beat_sheet`, `gn_final_script`.
- **Admin UI** at `/teacher/llm-config` (two tabs: Sites management, Step Configuration matrix). Accessible via "LLM Config" button in the navbar for admin users.
- **API endpoints**: `GET/POST /api/admin/llm-sites/`, `PUT/DELETE /api/admin/llm-sites/<id>/`, `GET/PUT /api/admin/llm-step-configs/`.
- **llm_config_service.py**: cached lookup layer (5-min TTL) providing `get_step_config(step_key)` → `{primary: {model, provider_type, base_url, api_key}, fallback: {...}}`. Raises `LLMConfigError` if no config exists for a step.
- **Pipeline dispatch refactored**: orchestrator builds `[primary, primary, fallback]` attempt list from DB config instead of hardcoded constants. Each graphic novel substep looks up its own config independently.
- `call_gemini()` and `call_anthropic()` now accept optional `api_key` and `base_url` overrides (backwards-compatible).
- `call_anthropic()` now handles empty `user_prompt` by collapsing system prompt into the user message (matches Gemini proxy behavior; fixes 500 errors when routing steps with empty user_prompt to Anthropic).
- Migration `0025_llm_config` creates tables and seeds one default Gemini site with all 10 steps configured (primary: `gemini-3.1-pro-preview`, fallback: `gemini-3-pro-preview`).

### Test
- Updated `TestRunFullPipeline` assertions to match new config-dict dispatch (347 tests passing).

## [Unreleased] - 2026-05-28 (secondary character anchors)

### Added — Secondary Character Visual Anchors
- After the final script step, an extra LLM call generates a detailed visual reference sheet (~150 words covering body, face/hair, outfit, color priority, negative constraints) for secondary characters who have dialogue AND appear on non-consecutive pages. Prevents visual drift when a character skips a page and the image model has no prior reference.
- Detection logic: `_find_secondary_characters_needing_anchors(result)` scans the script output for non-hero characters with speech on non-consecutive pages.
- Storage: `novel.metadata['secondary_character_anchors']` — dict of `{name: anchor_text}`. No migration needed.
- Image prompt lookup (`_characters_for_graphic_novel_page`) now checks `LEXI_CHARACTERS` first (hero → canon injection), then stored anchors, then falls back to the brief `novel.characters` entry. Eliminates spurious "Unknown character name" warnings for LLM-invented secondary characters.
- Prompt template: `backend/vocabulary/prompts/secondary_character_anchor.txt`.
- Uses `gn_final_script` LLM config (same model that wrote the script).

### Test
- Added `TestFindSecondaryCharactersNeedingAnchors` (5 cases): empty pages, hero-only, speaking secondary with gap, non-speaking secondary, consecutive-only secondary.

## [Unreleased] - 2026-05-29

### Change — Unified 5/6-Page Graphic Novel Pipeline (Replaces Dual-Channel Architecture)
- Each pack now generates **one** graphic novel at a length the router LLM picks per premise (5 or 6 pages). The 6-page admin-only channel is removed.
- Router prompt: each candidate premise now declares `page_count_rationale` (one sentence) followed by `page_count` ∈ {5, 6}. Chain-of-thought ordering — rationale appears before the numeric decision.
- Scorer carries the winning premise's `page_count` forward; beat-sheet and final-script substeps dispatch to the matching prompt template via `GRAPHIC_NOVEL_BEAT_SHEET_TEMPLATES = {5: 'graphic_novel_beat_sheet', 6: 'graphic_novel_beat_sheet_6page'}` and the same shape for `_SCRIPT_TEMPLATES`.
- Pipeline trimmed from 10 to **8 steps**. Removed `GN_6PAGE_SCRIPT` / `GN_6PAGE_IMAGES` from `PIPELINE_STEP_ORDER`. Enum values stay on `GenerationJobLog.Step` so old log rows remain readable; no current code path emits them.
- Removed `GRAPHIC_NOVEL_6PAGE_ENABLED` setting and `GRAPHIC_NOVEL_6PAGE_SUBSTEPS` constant. Deleted `_step_graphic_novel_script_6page` and `_step_graphic_novel_images_6page`.
- Validators collapsed: one `_validate_graphic_novel_beat_result` (and one `_validate_graphic_novel_script_result`) reads expected length from `input_summary['winning_premise']['page_count']`. Router validator `_validate_graphic_novel_router_result` now requires a non-empty `page_count_rationale` and `page_count` ∈ {5, 6} on every premise.
- Plot complexity caps now scale by chosen length via `max_locations_for_page_count(page_count)` helper (≤2 for 5-page, ≤3 for 6-page). Existing `GRAPHIC_NOVEL_MAX_LOCATIONS_5PAGE` / `_6PAGE` constants kept as the helper's source of truth. Per the user's call, the router has full latitude on length — no hard rules tying length to location count or secondary characters.
- `GraphicNovel.channel` field stays as a vestigial column (always `'5page'` for new rows). `unique_together = ('pack', 'channel')` retained. No DB migration; the field is harmless and a later cleanup migration can drop it.
- `restart_graphic_novel_from_substep` recovers `winning_premise.page_count` from the saved router/scorer artifact and uses it for template dispatch on rerun.
- `resume_pipeline` now treats a job whose `last_completed_step` is no longer in `PIPELINE_STEP_ORDER` (e.g. an in-flight job stamped `GN_6PAGE_*` before this change) as fully complete.
- `novel.metadata['page_count']` is the new source of truth for downstream readers; `instructional_service.py` is unchanged because it iterates the saved page rows, not a fixed length.
- `_run_graphic_novel_substep` extended with optional `prompt_template_name` override so the substep config record can stay length-neutral while individual calls swap templates.

### Test
- Added `TestRouterValidatorPageCount` (6 cases): accepts baseline; rejects missing/invalid/string `page_count`; rejects missing/blank `page_count_rationale`.
- Added `TestStepGraphicNovelScriptTemplateDispatch` (2 cases): verifies that `winning_premise.page_count == 5` invokes the 5-page beat-sheet/script templates and `== 6` invokes the 6-page templates; both also assert `novel.metadata['page_count']` is persisted.
- Removed legacy `_step_graphic_novel_script_6page` / `_step_graphic_novel_images_6page` mocks. Full backend suite green (347 passing).

## [Unreleased] - 2026-05-27 (afternoon)

### Change — Graphic Novel Pedagogy Remediation (Moves 1/2/3)
- **Move 1 — Pedagogical anchor contract.** Every router `vocab_integration_plan` item must now declare a `pedagogical_anchor = {anchor_type, anchor_sketch}` with `anchor_type` from `{demonstrated_action, near_synonym, category_example, visible_referent}`. Final script propagates these into per-page `vocab_anchors`. Constant: `GRAPHIC_NOVEL_PEDAGOGICAL_ANCHOR_TYPES`. Validator `_validate_vocab_integration_plan` rejects premises lacking the anchor.
- **Move 2 — Plot complexity caps.** Each premise now carries `complexity_budget = {locations, secondary_characters, problem_thread}`. Hard caps: 5-page ≤2 locations / ≤2 secondary characters; 6-page ≤3 locations. Single-thread requirement enforced. Beat-sheet validator `_validate_beat_complexity` checks `setting_keys` count and that `characters_featured ⊆ away_team ∪ secondary_characters`. Constants: `GRAPHIC_NOVEL_MAX_LOCATIONS_5PAGE`, `GRAPHIC_NOVEL_MAX_LOCATIONS_6PAGE`, `GRAPHIC_NOVEL_MAX_SECONDARY_CHARACTERS`.
- **Move 3 — Mini cap tightened.** `GRAPHIC_NOVEL_MAX_MINI_SUMMONS_PER_STORY` reduced from 2 to 1. Most vocab now integrates through dialogue/narration/world logic; the single allowed Mini is reserved for the most concrete/abstract word in the pack.
- **Shades removed.** `shades_present` is no longer a team-selector flag or a downstream prompt input. The literal field survives only on legacy `GraphicNovel.metadata` rows (migration `0023_graphic_novel_lexi_legends_metadata`).
- **Scorer dimensions overhaul.** `GRAPHIC_NOVEL_SCORING_DIMENSIONS` rewritten to `{narrative_clarity, visual_potential, vocabulary_integration, pedagogical_clarity, character_fit}`. Old dimensions (`narrative_engagement`, `ip_coherence`, `ink_over_reliance`, `originality`) dropped to refocus on ESL teaching value.
- **Doc clarifications.** Graphic novel script step is Gemini `gemini-3.1-pro-preview` (not Claude Opus — that mention in CLAUDE.md/README/PROJECT_CONTEXT had been stale since the 2026-05-24 model switch). The Anthropic SDK and `ANTHROPIC_API_KEY` remain wired for fallback / future use; the dispatcher in `helpers.py` only routes to Anthropic when the model name contains `claude`/`sonnet`/`opus`/`haiku`.

### Test
- Updated `tests/vocabulary/test_generation_pipeline_service.py` fixtures for the new contracts (44/44 pipeline tests passing).
- Fixed `tests/vocabulary/test_llm_service.py::TestCallAnthropic` after a previous switch from `client.messages.create` to `client.messages.stream` left the mocks pointing at the wrong API. Added a `_make_stream_mock` helper that builds the streaming context-manager chain.

## [Unreleased] - 2026-05-27

### Fix — Gemini Proxy Routing & Timeout Handling
- `call_gemini` now branches on `GEMINI_BASE_URL`: when set, uses the **OpenAI SDK** against the proxy's `chat.completions` endpoint; when empty, uses the `google.genai` SDK natively. Fixes 403 errors from OpenAI-compatible proxies (e.g., `api.b.ai`) that only allow `/v1/chat/completions`, `/v1/messages`, `/v1/models` paths and rejected the native `:generateContent` calls the Google SDK was emitting.
- Empty `user_prompt` is now collapsed into a single user message before sending to the proxy. Several pipeline steps (`step_questions`, `step_packs`) pass the full prompt as `system_prompt` with an empty user message, which the proxy rejected with `400 "at least one contents field is required"`.
- `GEMINI_BASE_URL` value normalized — trailing `/chat/completions` is stripped automatically since the OpenAI SDK appends it.
- OpenAI SDK auto-retries disabled (`max_retries=0`) and explicit `timeout=600.0` set on the proxy client. Previously the SDK's hidden 2 retries stacked on top of orchestrator retries, turning a single failed call into three sequential 200-second proxy roundtrips before bubbling the error.
- Reduced `QUESTION_BATCH_SIZE` from 6 → 3 in `step_questions.py`. Smaller batches finish faster and reduce 502 Bad Gateway risk from upstream proxy timeouts on long LLM calls.

### Change — Lexi Mini System (Replaces Ink VFX)
- Replaced the abstract Ink-VFX vocabulary mechanic with the **Lexi Mini system**: writing a vocab word now summons a temporary monochromatic creature that physically acts out the word's definition (Hugo→Dependable golems, Leo→Mischievous imps, Amara→Scholarly moths/sphinxes, Mei→Agile foxes/wyverns)
- Hard cap: 0–2 Mini summons per story; most vocab still integrates through dialogue, narration, or world logic
- Tool changes: Hugo's flat paintbrush → orange **carpenter's pencil**; Leo's spray can → cyan **chunky wax crayon**. Amara's golden quill and Mei's multicolor marker unchanged.
- New rule: writing tools only appear on-page during a Lexi Mini summon. In zero-Mini panels, tools are not visible.
- Removed all Ink failure states (wobble/sag/drip/fade) — every Mini summon succeeds. Failure states were confusing for ESL learners and unrenderable in static panels.
- **Folio fully removed** from canon, prompt pipeline, and review page logic. `folio_present` flag removed from team selector validation and `novel_metadata`. UI mascot decisions deferred — kept out of the generation pipeline.
- Pipeline: `GRAPHIC_NOVEL_ALLOWED_INTEGRATION_MODES` constant replaced `direct_ink_activation` with `lexi_mini_summon`. JSON field names `uses_direct_ink` and `ink_usage` retained for backwards compatibility (old novels in DB still render unchanged).
- Default `review_artifact_type` fallback: `Vault clue board` (was `Folio field guide`).
- Updated all 8 character prompt-injection files (Hugo/Leo/Amara/Mei × 9yo/12yo): replaced `INK_VFX_LOCK` with `LEXI_MINI_LOCK`, added tool-visibility rule, removed aerosol/paintbrush/failure language.
- Updated runtime canon: `team-selector-summaries.md`, `script-character-sheets.md`, `vault-zones-script.md` cleared of Folio and old tool references.
- Deleted `backend/data/canon/cast/folio/` directory.

### Refactor — Canon Files Relocated
- Moved runtime canon files from `docs/feature_plan/runtime_canon/lexi_legends/` to `backend/data/canon/`
- Moved `lexi-legends-cast-bible.md` from `docs/feature_plan/` to `backend/data/canon/`
- Updated `canon_service.py` path constants to resolve from `backend/data/canon/`
- Updated all skill files (setting-building-pipeline, review-canon-sheets, character-building-pipeline) to reference new paths

## [Unreleased] - 2026-05-25

### Feature — Dual-Channel Graphic Novel Generation
- Added 6-page graphic novel channel that runs alongside the existing 5-page pipeline
- Each generation job now produces two graphic novels per pack: 5-page (student-facing) and 6-page (admin-only)
- `GraphicNovel` model changed from OneToOneField to ForeignKey with `channel` field ('5page'/'6page') and `unique_together` constraint
- 6-page channel runs its own independent 5-substep pipeline (team selection → router → scorer → beat sheet → final script) with dedicated prompts
- 6-page channel generates images via OpenAI GPT-Image-2 (same as 5-page)
- 6-page channel skips cloze item creation (5-page channel already creates them)
- Added `GRAPHIC_NOVEL_6PAGE_ENABLED` setting (default: True) to enable/disable the 6-page channel
- New pipeline steps: `GN_6PAGE_SCRIPT` and `GN_6PAGE_IMAGES` (steps 9-10)
- Student-facing instructional service only serves `channel='5page'` novels
- New prompt templates: `graphic_novel_beat_sheet_6page.txt`, `graphic_novel_script_6page.txt`

### Fix — 6-Page Image Generation
- Fixed `_step_graphic_novel_images_6page` passing wrong keyword argument (`previous_image_path=`) to `_call_openai_image_releasing_db`; now correctly passes `reference_image=` with image bytes (matching 5-page behavior)
- Fixed orchestrator retry logic logging wrong model name (`gemini-3.1-pro-preview`) for image steps; now correctly logs `gpt-image-2`
- Fixed 6-page image filenames: changed from `{vocab_words}_{pack_id}_6p{N}.png` to `{title_slug}_6p_page_{N}.png` to match 5-page naming convention
- Fixed `Unknown vault zone requested: 'review-artifact'` warning: review pages now skip vault zone lookup entirely (they use their own `review_artifact_type` prompt field)
- Fixed `Duplicate entry for key 'vocabulary_graphicnovel_pack_id_channel_uniq'` on pipeline resume: added defensive delete before novel creation for both channels to handle edge cases where the top-of-loop guard passes but a stale record exists

## [Unreleased] - 2026-05-24

### Fix — Translation Step Reliability
- Translation prompt now returns `term` field in each output object, enabling primary-key-based matching instead of fragile substring matching on `source_text`
- Translation matching logic rewritten: looks up word by `term` (case-insensitive) rather than iterating all words with substring `in` checks
- Validation changed from "all source_text pairs matched" to "all expected terms have translations"

### Improvement — Primer Syllable Accuracy
- Added explicit single-syllable rule to primer prompt: output word as-is without dot characters
- Added phonetic syllable preference: use sound-based breaks over spelling-based when they differ (benefits ESL learners)

### Optimization — Graphic Novel Prompt Round 2 (Log Audit)
- Applied chain-of-thought JSON ordering: `team_rationale` moved before boolean decisions in team selector; `arc_planning` and `vocab_page_assignments` added before `beat_sheet` array in beat sheet prompt
- Added `total_ink_activations_planned` counter before vocab arrays in router (per premise) and beat sheet prompts to enforce the max-2 Ink activation limit
- Added `vocab_page_assignments` checklist in beat sheet — LLM assigns words to pages before generating the beat sheet, reducing word-dropping
- Beat sheet `page_turn_question` explicitly defined as `null` for Page 5 (removes ambiguous free-text workaround)
- Replaced "K-8" with "ages 8–14" across all 5 graphic novel prompt files
- Switched graphic novel script model from `claude-sonnet-4-6` to `gemini-3.1-pro-preview` (better structured JSON output)
- Added `_call_llm_releasing_db()` routing helper that picks Gemini or Anthropic backend based on model name
- Made `collapse_markdown()` public in `canon_service.py`; applied it to full visual character sheets before embedding in script step JSON (removes `\n`/`##` noise from serialized prompts)
- Router: moved `vocab_integration_plan` before `premise` paragraph — forces model to plan vocab mechanics before writing narrative
- Scorer: added `dimension_rankings` scratchpad as first key — model ranks premises per dimension before assigning numeric scores
- Beat sheet: moved `vocab_roles` and `ink_usage` before `beat_sheet` array — model defines Ink mechanics before writing page beats
- Final script: added per-page `page_planning` object before `panels` — model verifies text budget, target words, layout, and shot scales before generating panel content
- Canon: added Ink mechanic examples (success + failure per character) to `team-selector-summaries.md` and `script-character-sheets.md` to ground Ink as a linguistic puzzle mechanic

## [Unreleased] - 2026-05-23

### Change — Graphic Novel Creative Flexibility Revision
- Pack grouping prompt: replaced prescriptive `story_engine_hint` (closed list of action-heavy engines) with free-text `narrative_approach` field; reframed grouping criteria around situational cohesion instead of conflict/plot mechanics; added explicit 5-page length warning
- Router prompt: replaced `story_engine` → `narrative_approach`, `central_problem` → `central_thread`; broadened agency definition; added 5-page complexity warning; expanded narrative approach examples (observational, slice-of-life, etc.)
- Scorer prompt: replaced `narrative_engagement` → `narrative_clarity` (rewards clarity over momentum); replaced "flat pacing" penalty with "too many plot beats for 5 pages"; updated winning premise schema
- Beat sheet prompt: relaxed "hook + build momentum" to "draw in + develop the situation"; added arc shape examples for observational/slice-of-life; replaced `anti_flatness_guard` with `narrative_coherence`
- Team selector: added `sample_team_options()` coin flip — all-solo or all-dual options (forced 50/50 split); biased `shades_present` toward false (only for genuinely confusable meanings); biased `vault_framing` to require earning its page space
- Pipeline code: propagated field renames (`story_engine` → `narrative_approach`), updated validation to accept `central_thread`

### Fix — Graphic Novel Script Retry and Validation
- Fixed `_text_terms_from_graphic_novel_page` crash when LLM returns `null` for narration/dialogue text fields (used `or ''` instead of `.get(key, '')` which doesn't handle explicit null)
- Fixed orchestrator retry restarting entire 5-substep flow from team_selection on final script failure; substeps now retry internally (1 retry per substep) and orchestrator runs GRAPHIC_NOVEL_SCRIPT only once
- Added substep-level restart: `POST /api/generation-jobs/{id}/restart-substep/` accepts `pack_id` and `substep` key, loads prior substep artifacts from disk, and re-runs from the target substep onward
- Frontend: each graphic novel substep row now shows a restart button (visible when job is not running)

### Optimization — Graphic Novel Prompt Restructuring
- All 5 script substeps now use system/user prompt split (instructions in system, data in user message)
- Removed `rulebook` and `learning_behavior` from all script step payloads (irrelevant to story generation)
- Created `team-selector-summaries.md` — purpose-built hero summaries + pairing dynamics for team selection
- Created `script-character-sheets.md` — narrative-only character info for router/scorer/beat sheet (no visual specs)
- Created `vault-summary-premises.md` — condensed vault context for premise generation (~30 lines vs ~200)
- Team selector now receives world primer, filtered hero summaries, and filtered pairing dynamics (only for teams in options)
- Router/scorer/beat sheet use lightweight `router_lexi_context` instead of full visual sheets
- Final script step retains full visual sheets + vault spec (needed for image generation downstream)
- Pairing dynamics converted from raw markdown to structured format across all steps
- Image prompts: panel content formatted as prose (not raw JSON), synopsis trimmed for pages 2+, setting context added for non-vault pages, vocabulary highlighting uses per-character Ink colors
- Added `canon_service.py` functions: `load_team_selector_heroes()`, `load_team_selector_dynamics()`, `load_script_character_sheets()`, `load_vault_summary_premises()`
- `_format_graphic_novel_prompt()` is now dead code (all steps pass templates directly)

## [Unreleased] - 2026-05-22

### Refactor — Generation Pipeline Modularization
- Split `generation_pipeline_service.py` (2094 lines) into `vocabulary/services/generation/` package:
  - `orchestrator.py` — pipeline run/resume/restart control flow
  - `step_word_lookup.py` — steps 1-2: word lookup + dedup
  - `step_translations.py` — step 3: translations
  - `step_questions.py` — step 4: question generation
  - `step_packs.py` — steps 5-6: pack creation + primers
  - `step_graphic_novel.py` — steps 7-8: graphic novel script + images
  - `helpers.py` — shared LLM wrappers, logging utilities
  - `constants.py` — model names, step order, config constants
- Old import path (`vocabulary.services.generation_pipeline_service`) preserved via backwards-compatible shim
- Test patches updated to target actual module locations (`llm_service`, `embedding_service`, `orchestrator`)
- Fixed stale test assertion for canon character prompt injection content

### Graphic Novel Pipeline — Canon Service Integration
- Added `canon_service.py`: loads runtime canon files (character sheets, Vault specs, rulebook, pairing dynamics) into LLM prompts for visual and narrative consistency
- Beat sheet and script calls now receive full character `.md` sheets, Vault script context, rulebook, and learning behavior plan
- Image prompts now receive compact character design locks (`_prompt_injection.txt`) instead of LLM-invented descriptions
- Added STYLE_LOCK to `graphic_novel_page.txt` and `graphic_novel_review_page.txt` to prevent rendering style drift
- Vault page image prompts now use full Vault image specs + zone-specific overlays instead of a 3-line stub
- Team selector receives pairing dynamics from the cast bible for chemistry-aware team selection
- Team options randomized to 3 candidates (from 10) to encourage variety
- Added path traversal guards: character name allowlist and vault zone allowlist

## [Unreleased] - 2026-05-16

### Graphic Novel Reader UX Improvements
- Expanded reader width from 1080px to min(1792px, 90vw) so page images display closer to native resolution
- Vocabulary cards now shown by default on each page (previously required tapping the image)
- Page navigation (arrows, keyboard, swipe, dots) no longer hides vocabulary cards
- Merged title row and footer into a single sticky toolbar: page count + title on the left, page dots in the center, "Done Reading" button on the right
- Removed the instructional header (pack name + step label) to save vertical space
- "Done Reading" button now uses green color and fades in after a 3-second delay on the last page to encourage reading before advancing

## [Unreleased] - 2026-05-15

### Bug Fixes
- Fixed review scheduling: `NextPracticeWordView` now includes questions with NULL `lexile_score` in the Lexile filter (matching `StudentDashboardView`), so newly learned words appear for same-day review even when their questions lack a Lexile score
- Fixed cloze blank fill: `ClozeQuiz` now splits on 3+ underscores (`/_{3,}/`) instead of exactly 7, so graphic novel cloze items with varying blank lengths render correctly
- Fixed TTS auto-play on type-in retry: after a successful retry submission via Enter, feedback buttons use `tabIndex={-1}` until ready, preventing the Enter keyup from activating the Explain button and triggering text-to-speech

## [Unreleased] - 2026-05-14

### Graphic Novel Instructional Flow
- Replaced new full-pipeline micro-story generation with AI-generated graphic novels for the instructional Read step
- Added `GraphicNovel` and `GraphicNovelPage` models plus migration `0018_graphic_novel`; each page stores one complete 1792x1024 landscape comic image and panel metadata
- Added migration `0019_graphic_novel_page_status` so each `GraphicNovelPage` tracks image-generation status, attempts, error text, start time, and completion time
- Added `GenerationJob.graphic_novels_created` and new pipeline log steps `GRAPHIC_NOVEL_SCRIPT` and `GRAPHIC_NOVEL_IMAGES`
- Updated `PIPELINE_STEP_ORDER` to run `GRAPHIC_NOVEL_SCRIPT` and `GRAPHIC_NOVEL_IMAGES` after `PRIMER_GEN`; legacy `STORY_CLOZE_GEN` remains available for existing logs/manual use but is no longer used for new full-pipeline content
- Added `graphic_novel_script.txt` and `graphic_novel_page.txt` prompt templates
- `call_openai_image()` now accepts a `size` parameter; graphic novel pages request `1792x1024`
- `GET /api/instructional/packs/<pack_id>/` now returns `story.type = "graphic_novel"` with page data for new packs and falls back to `story.type = "micro_story"` for legacy packs
- Added `GraphicNovelReader` with 16:9 page display, arrow/keyboard/swipe navigation, page dots, tap-to-open vocabulary overlay, and final-page completion
- Removed the old per-word visual generation path end to end: model fields, generated image records, practice/review UI, API payloads, stale prompts, and related tests.
- Updated admin generation status/review surfaces to display `Graphic Novel Script` and `Graphic Novel Images` instead of the legacy `Story & Cloze Generation` label, and to expose generated graphic novel page data in review payloads
- `GET /api/generation-jobs/<id>/` now includes `graphic_novel_image_pages` so the admin status page can show per-page `PENDING`/`RUNNING`/`COMPLETED`/`FAILED` progress for `GRAPHIC_NOVEL_IMAGES`
- `GRAPHIC_NOVEL_IMAGES` now skips completed page images, marks each page attempt independently, and fails the step if any page remains failed; Resume retries only missing/failed pages instead of starting from page 1
- Added explicit backend progress logging around graphic novel script and page image generation; LLM/image prompt logs continue to be written to `temp/llm_logs/`
- Released Django/MySQL connections before and after slow Gemini/OpenAI calls in the background generation pipeline, and closed background-thread connections when pipeline/resume/restart exits, to avoid connection exhaustion during long graphic novel image generation
- Slowed the admin generation status polling interval from 3 seconds to 10 seconds to reduce database pressure while jobs are running; stale running jobs now record a FAILED log and reset the word set out of `GENERATING`
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

## [Unreleased] 鈥?2026-04-30

### Image Generation Pipeline 鈥?Educational Value Rewrite
- Removed Hoyoverse/Genshin Impact aesthetic framing from creative direction and image generation prompts
- Added "Definition Clarity Check" instruction: LLM must verify a child could guess the word's meaning from the image alone
- Scenes now grounded in real-world contexts (gym, nature, classroom) instead of fantasy/elemental settings
- Anime cel-shading retained as rendering style only, not compositional driver

### Image Generation Pipeline 鈥?Creative Direction Step (prior unreleased)
- Word lookup step now classifies each word into an image category
- Image generation switched from Gemini to OpenAI GPT-Image-2

---

## [Unreleased] 鈥?2026-04-23

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
- Spaced repetition intervals changed: Level 1: 0鈫?d, Level 2: 1鈫?d, Level 3: 3鈫?d, Level 4: 7鈫?0d, Level 5: 14鈫?0d
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
- `0002_add_daily_goal_bounds` 鈥?daily_goal_min, daily_goal_max, last_goal_prompt_date on CustomUser
- `0010_level_curriculum_alter_level_name_and_more` 鈥?Level FK to Curriculum, scoped uniqueness
- `0012_add_retry_count_to_useranswer` 鈥?retry_count field on UserAnswer
- `0013_update_mastery_level_intervals` 鈥?updated spaced repetition intervals

- `0017_hidden_mastery_level` - adds hidden long-term mastery levels and updates the current spaced repetition schedule

### Tests
- Expanded test coverage: views, serializers, models, adapted services, embedding service

---

## [0.6.0] 鈥?2026-04-06

### Beta Readiness 鈥?Bookmarks, Generation Requests, UX Fixes

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

## [0.5.0] 鈥?2026-04-03

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

## [0.4.0] 鈥?2026-03-24

### Generation Pipeline Quality & Token Reduction

**Pipeline-wide:**
- Switch from Claude Opus to Gemini 3.1 Pro for all text generation
- Add `call_gemini()` text generation function to llm_service
- Apply 15% Lexile offset so scaffolding text is easier than target vocab
- Add 512x512 square image generation with low resolution setting

**Step 1 鈥?Word Lookup:**
- Remove per-word `source_context` from JSON output to save tokens
- Build `source_context` from job metadata instead

**Step 3 鈥?Translation:**
- Rewrite prompt with two strategies: native equivalent for definitions, natural translation for example sentences
- Include term in items list for better context

**Step 4 鈥?Questions:**
- Remove redundant WORD ENRICHMENT step that duplicated Steps 1 and 3
- Pass full definition and `example_sentence` from Step 1 directly
- Simplify output format: flat term + questions instead of nested word array

**Step 5 鈥?Pack Grouping:**
- Add creative writer and curriculum architect roles
- Add `text_type` field (fiction/narrative_nonfiction) to WordPack model
- LLM evaluates word nature and assigns best text type per pack
- Change max words per pack from 5 to 6 with balanced distribution

**Step 6 鈥?Primers:**
- Calibrate kid-friendly definitions to target Lexile level
- Add Lexile band guidelines (below 600L through above 1000L)

**Step 7 鈥?Stories:**
- Rewrite prompt for engaging fiction and narrative non-fiction
- Fiction: high-stakes show-don't-tell scenes
- Narrative non-fiction: fascinating hooks and real-world contexts

**Step 8 鈥?Images:**
- Square 1:1 aspect ratio prompt for vocabulary cards
- Low resolution (512x512) for faster generation

---

## [0.3.1] 鈥?2026-03-14

### Pipeline & Image Fixes

- Auto-approve generated images, skip manual review step
- Update image generation model to `gemini-3.1-flash-image-preview`
- Clear existing words before running generation pipeline (prevents duplicates on re-run)
- Fix Gemini API call: combine system and user prompts when user_prompt is empty

---

## [0.3.0] 鈥?2026-03-13

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

## [0.2.0] 鈥?2026-03-01

### Complete Generation Pipeline & Practice Bug Fixes

- 8-step AI content generation pipeline (word lookup, dedup, translations, questions, packs, primers, stories/cloze, images) with resume support
- Incremental word addition to existing generated word sets
- Generation wizard with live status polling and review/approve UI
- Fix spaced repetition: exclude already-answered words from session and dashboard due count
- Fix teacher roster due count to match student view (filter by READY status)
- Add Vite proxy for `/media` to serve generated images in dev

---

## [0.1.1] 鈥?2026-02-28

### Admin Generation UI (Phase 5)

- Generation wizard, job progress monitor, and content review pages
- Backend endpoints for fetching generated content and bulk-approving images

---

## [0.1.0] 鈥?2026-02-28

### Full-Stack Rebuild (Phases 1鈥?)

- Initial full-stack rebuild of Vocab App V2
- Django backend with REST API
- React frontend with Vite
- User management (teachers, students, groups)
- Word set CRUD and assignment workflow
- Spaced repetition practice engine
- Student and teacher dashboards
