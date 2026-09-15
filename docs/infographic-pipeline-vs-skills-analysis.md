# Infographic Pipeline vs. External Skills — Analysis & Experiment Roadmap

Date: 2026-08-26 · Status: analysis only, no code changes made

**Scope.** Compared the in-repo infographic generation pipeline (steps 10–11: `ig_design` → `ig_cloze` → poster render, 3 candidates, admin select) against two external "skills" found in `C:\Users\admin\infographic-skills`:

- **`baoyu-infographic`** (v1.117.4) — an interactive infographic generator built on a **21-layout × 22-style orthogonal matrix**, with per-layout and per-style prompt-fragment files, a content-analysis framework, and a structured-content intermediate format.
- **`infographic-skill`** (高密度信息大图 v4.0) — a Chinese "high-density info poster" generator: 10 copy-paste-ready style prompt templates (fixed sections: STYLE / COLOR PALETTE w/ hex / LAYOUT / TYPOGRAPHY / AVOID), a 6–7-module density doctrine, NanoBanana backend, 2K/4K portrait output.

**Decisions locked in with the requester (2026-08-26):**

1. Style: move to **curated variety** (a small set of kid-appropriate style definitions, not the full 22-style matrix, not the status-quo single style).
2. Layout: adopt a **curated layout set** (a few archetypes with concrete prompt fragments, server-rotated across candidates).
3. Priority axes: **visual quality & diversity, pipeline robustness, pedagogical content**. (Rendered-output verification was explicitly *not* prioritized.)
4. Deliverable: analysis + roadmap structured as a **3-condition experiment** — (1) add style+layout variety, (2) no variety but skill-informed quality improvements, (3) current pipeline + bug fixes only — to determine empirically which produces the best posters.

---

## 1. Current pipeline — what we have

### 1.1 Flow (verified in code)

- Wizard posts `content_types` including `infographic`; orchestrator skips steps 10–11 otherwise (`orchestrator.py:261-268`).
- **INFOGRAPHIC_DESIGN** (`step_infographic.py:576`): loops packs × 3 candidates; per candidate two substeps, 3 attempts each on the **primary site only**:
  - `ig_design` (`:424-435`) — input `{pack_label, text_type, target_lexile, words}`; validated by `_validate_infographic_design_result` (`:482`).
  - `ig_cloze` (`:437-448`) — input = same + full design JSON; validated by the shared GN cloze validator.
  - Persist is atomic; staged cloze FK'd to the candidate; fails if any pack word has no cloze (`:317-324`).
- **INFOGRAPHIC_IMAGE** (`:781`): one GPT-Image-2 render per candidate at `1792x1024`, prompt assembled by `build_infographic_image_prompt` (`:750`) from the design JSON; PNG + best-effort JPEG; per-candidate continue-on-failure, step raises if any failed, orchestrator retries the step once more.
- **Selection**: completeness-gated (`display_image` + staged cloze), promotes staged cloze to active (shared with GN — last published wins).
- **Restart**: `restart-infographic-substep/` with orphan-fill, is_selected 409, ≥-start-substep log purge. Does not re-render posters.

### 1.2 Prompt architecture (current pipeline)

- `infographic_design.txt` — art-director prompt. Two `layout_mode`s (panorama / gallery), six `visual_structure` enums (`journey_path|map|cutaway|cycle|timeline|labeled_scene`), style composed from **four free-text menus** (core style / colors / composition / details, "pick 2–3 terms each"). Anti-glossary rule, people de-emphasis, `intro_text` must use every word.
- `infographic_image.txt` — STYLE_LOCK + layout guidance (two server-side constants `_PANORAMA_GUIDANCE` / `_GALLERY_GUIDANCE`, `:730-747`) + marked vocab terms (`**term**` → bold/accent, asterisks never printed) + palette + scene elements.
- `infographic_cloze.txt` — minimal; independent practice sentences, 7-underscore blanks, 2 distractors.

### 1.3 Validators (current pipeline)

Glossary-format rejection (regex on `term:` / `term -`), caption-must-contain-term (stem-tolerant), intro_text full coverage, full pack coverage in `entries` + `vocab_terms` anchoring. **Not validated**: `layout_mode`/`visual_structure` enum membership (invalid `layout_mode` silently renders as panorama, `:755`), `reading_level`, palette sanity, distractor POS/uniqueness, the 7-underscore format. No post-render check of any kind.

### 1.4 The core weakness the skills speak to

**Candidate diversity is purely aspirational.** All 3 candidates receive *byte-identical* design inputs (`base_input`, `:411-416`) — no `candidate_index`, no assigned layout/style, no "previous candidates chose X" signal. The only differentiator is LLM temperature. In practice the 3 "candidates" can converge to the same layout_mode, palette family, and style terms, which defeats the purpose of the compare-and-select review flow. (GN candidates diverge structurally via independent premise router/scorer; infographics have no equivalent.)

---

## 2. What the two skills actually contain

### 2.1 baoyu-infographic

- **Orthogonal matrix**: layout (information architecture) × style (aesthetics), freely combined. Each of the 21 layouts has a file with `Structure / Best For / Visual Elements / Text Placement / Recommended Pairings` (e.g. `layouts/bento-grid.md`). Each of the 22 styles has a file with `Color Palette` (**with hex codes**), `Visual Elements`, `Typography`, `Style Enforcement`, `Avoid`, `Best For` (e.g. `styles/hand-drawn-edu.md`).
- **Workflow**: analyze content (type classification → layout/style mapping table, learning objectives, audience, complexity) → structured-content intermediate (sections with verbatim data + exact text labels) → recommend 3–5 layout×style combos → **mandatory human confirmation** → assemble prompt from base template + layout fragment + style fragment → generate, retry once on failure.
- **Prompt assembly** (`references/base-prompt.md`): slots for layout, style, aspect ratio, language, layout guidelines, style guidelines, content, exact text labels.
- **Notable policies**: prompt persisted to a file before rendering (reproducibility); never patch a rendered bitmap programmatically — regenerate from a corrected prompt instead, preserving flawed candidates for comparison; never substitute SVG/HTML for raster.

### 2.2 infographic-skill (high-density)

- **10 style templates**, each a self-contained prompt block with five fixed sections: `STYLE REQUIREMENTS` (aesthetic+mood), `COLOR PALETTE` (hex), `LAYOUT`, `ELEMENTS`, `TYPOGRAPHY`, plus an `AVOID` negative list. Highly concrete, directly paste-able.
- **Density doctrine**: every poster must have 6–7 modules, each with concrete data/brands/parameters; module archetypes (brand array, comparison ladder, parameter standards, pitfalls, checklist).
- Fixed params: portrait 3:4, 2K/4K, NanoBanana (`gemini` image model); explicit quality checklist (content/visual/technical).
- Target audience is adult social-media "干货" content — pedagogically mismatched with ages 7–14 ESL vocabulary.

---

## 3. Gap analysis — what to borrow, mapped to our components

### 3.1 Directly transferable (the point of Conditions 1 & 2)

| Skill concept | Pipeline gap it fixes | Integration point |
|---|---|---|
| Per-candidate **assigned** layout×style (their "recommend 3 combos" step) | Identical inputs → lookalike candidates (§1.4) | New `ig_layout` router substep picks a content-fit layout shortlist per pack; server assigns layouts + distinct styles per candidate (§5, Condition 1) |
| Per-layout prompt fragments (`Text Placement`, `Visual Elements`) | Only 2 layout guidance constants; `visual_structure` enum has no per-value guidance | New fragment files, e.g. `prompts/infographic/layouts/<key>.txt`, loaded like `graphic_novel_world_context.txt` |
| Style definition format: AESTHETIC / MOOD / COLOR PALETTE (hex) / LAYOUT / ELEMENTS / TYPOGRAPHY / AVOID | Our style menus are loose adjectives; LLM-composed `style_prompt` quality varies; `DEFAULT_INFOGRAPHIC_STYLE` + STYLE_LOCK can drift | Rewrite style guidance as structured definitions; **hex palettes instead of named colors** (image models follow hex far more reliably) |
| Explicit `AVOID` negative lists per style | Our image prompt has global prohibitions only (no grids, no speech bubbles) | Per-style avoid sections appended to the image prompt |
| Quality checklists | No design-time equivalents of "is every module concrete" | Cheap additions to `_validate_infographic_design_result`: layout/style enum membership, palette format, distractor sanity in the cloze validator |

### 3.2 Borrow lightly / adapt

- **Learning-objective framing** (baoyu analysis framework): our `big_idea` field is the embryo; the design prompt could require it to state what a *viewer understands* after reading, not just a topic sentence. Their audience/complexity analysis is mostly N/A — our audience (ages 7–14 ESL) and complexity (Lexile) are fixed inputs already.
- **Content-type → layout mapping** (their classification table): we already pass `text_type` into the design input; Condition 1 implements this as an LLM router substep (§5) rather than a static `text_type` map — `text_type` is too coarse on its own (word-level semantics within a text type vary).
- **"Never patch the bitmap, regenerate instead"**: already aligned — we keep losing candidates and never post-process text. No action.
- **Prompt persistence**: already done (`ig.prompt_used`). No action.

### 3.3 Do NOT borrow (with reasons)

- **High-density doctrine (6–7 data-packed modules)**: cognitively wrong for ages 7–14 ESL vocabulary; conflicts with our scene-based "word used in context" pedagogy and the people/sparsity rules.
- **Portrait 3:4 / 2K–4K defaults**: our reader UI is landscape; `1792x1024` stays. (If text legibility becomes the bottleneck later, raising render resolution is a separate lever.)
- **Backend swap to NanoBanana/Gemini image**: orthogonal to this analysis; GPT-Image-2 stays.
- **Mandatory human confirmation gate**: our pipeline is unattended/batch by design; the admin select step is already the human gate.
- **Verbatim-data preservation doctrine**: irrelevant — we generate content, not summarize sources.
- **Full 21×22 matrix**: maintenance burden and off-brand risk; the curated subset is the whole point of Condition 1.
- **Reference-image intake**: no current use case (could matter later for brand consistency).

### 3.4 What we already do better than both skills

3-candidate staged selection with completeness gating, atomic persist, cloze staging/promotion, substep-level resume with artifact logs, per-step LLM site/model config, unattended retry/backoff machinery. The skills are single-shot interactive prompt kits; **the borrow is prompt content + the diversity mechanism, not architecture.**

---

## 4. Robustness bugs found (Condition 3 scope — verified in code)

> **Status 2026-08-26: fixed.** #1, #2, #4, #5 and the `layout_mode` half of #6 are fixed and tested (see `changelog_after_July_20.md`, 2026-08-26 entry). #3 (dead `edited_image` schema) stays deferred — shipping edit/redraw endpoints is a feature, not a bug fix. The `reading_level` half of #6 remains unchecked by design (self-reported hint, nothing consumes it for gating).

1. **Full-step restart deletes published infographics.** *(fixed 2026-08-26)* `_clear_testing_outputs_for_step` INFOGRAPHIC_DESIGN branch did `Infographic.objects.filter(pack__in=packs).delete()` with **no `is_selected=False` filter** (`orchestrator.py:171-177`). The GN branch directly above explicitly preserves selected candidates (`:150-155`) and the comment falsely claims the two mirror each other. `restart_pipeline_from_step(job, INFOGRAPHIC_DESIGN)` **unpublishes live student content**. Fix: add `is_selected=False`.
2. **Fallback LLM site never used** *(fixed 2026-08-26)* for `ig_design`/`ig_cloze` — both substeps read `get_step_config(...)['primary']` only (`step_infographic.py:428,441`), unlike word-level steps' `[primary×3, fallback×1]` plan (`orchestrator.py:314-317`). A down primary site hard-fails the step despite configured fallback.
3. **Dead image-variant schema on `Infographic`.** *(deferred — feature, not a bug fix)* `edited_image` / `use_edited_image` / `edited_image_jpeg` exist (`models.py:745-756`) and `display_image` honors them (`:781-793`), but there are **no edit/redraw/select-image endpoints for infographics** (all `edited_image` view code is GN-page-only). Admins cannot fix a bad poster short of full candidate regeneration. Either ship the endpoints (GN pages are the template) or accept the dead fields. Tracked in `BETA_IMPROVEMENTS.md` #20.
4. **INFOGRAPHIC_IMAGE clear doesn't reset `image_jpeg`** *(fixed 2026-08-26)* (`orchestrator.py:179-188` reset `image` only). `student_image` prefers `image_jpeg`, so a stale JPEG can be served in the clear→re-render window.
5. **No stale-RUNNING sweep for infographics.** *(fixed 2026-08-26 — the job-status view's stale sweep now covers them)* GN pages get a 30-min RUNNING→FAILED sweep via `image-status/`; infographics have no such endpoint — a gunicorn restart mid-render leaves `generation_status=RUNNING` forever (harmless in practice only because the skip check keys on `ig.image`).
6. **Unvalidated enums**: an invalid `layout_mode` silently renders as panorama (`step_infographic.py:755`); `reading_level` is stored unchecked. *(layout_mode validation fixed 2026-08-26; `reading_level` stays unchecked by design.)*

---

## 5. Roadmap — the 3-condition experiment

Goal: same packs, three generation treatments, blind admin comparison → pick the winner (or a hybrid).

### Condition 1 — Curated variety (style + layout)

**What changes:** candidates stop being free-form; the server assigns each candidate a distinct (layout, style) pair.

- **Curated layout set (~6)**, mapped from our existing `visual_structure` vocabulary + baoyu archetypes, each with a concrete fragment file (structure, text placement, visual elements):
  - `panorama` (≈ current panorama / labeled_scene) — keep
  - `gallery` (≈ current gallery / bento-grid cousin) — keep
  - `journey` (≈ journey_path / winding-roadmap)
  - `map` (≈ isometric-map)
  - `hub-spoke` (central scene with radiating word vignettes — strong fit for a single theme + N words)
  - `cycle` (circular-flow, for process/cycle word sets)
- **Curated style set (~5)**, adapted from baoyu definitions, all passing the "not childish, modern-editorial" bar, each written in the skill's 5-section format with **hex palettes**:
  1. `modern-editorial` — current house style, deepened with concrete palette/typography/avoid-list
  2. `hand-drawn-edu` — macaron pastels, wobble lines, stick figures (baoyu's education-targeted style, nearly as-is)
  3. `chalkboard` — classic educational, strong text contrast
  4. `flat-vector` — corporate-memphis-adjacent, geometric, vibrant but clean
  5. `paper-craft` — craft-handmade collage warmth
  - Explicitly excluded: kawaii, claymation, pixel-art, cyberpunk, Y2K (off-brand / text-hostile).
- **Mechanism**: content-driven layout selection via a new **`ig_layout` router substep**, run once per pack before the candidate loop (decision 2026-08-26: layout must fit the content, NOT be blindly rotated; styles, being cosmetic, are still server-assigned for guaranteed divergence). This mirrors baoyu's Step 1 analysis → Step 3 combo recommendation, and the GN pipeline's team-selector → router pattern.
  - Input: `{pack_label, text_type, target_lexile, words}` (terms + definitions).
  - Output (CoT-ordered, per project convention): `{rationale, content_structure, best_layout, alternates[0-2]}` from the curated set. Validator checks enum membership, distinctness, ≤2 alternates. Empty alternates is legal — if only one layout genuinely fits, all candidates use it and diversity comes from style + scene.
  - Failure handling: same as other substeps (3 attempts on the primary site, transient FAILED log, auto-resume) — no special casing.
  - **Candidate assignment**: candidate 0 → `best_layout`; candidates 1–2 → the alternates (falling back to `best_layout` when the shortlist is short). Styles: 3 distinct picks per pack from the assigned layout's vetted pairings (table below). The design prompt receives the assigned layout+style fragments as constraints ("You are designing candidate N with THIS layout and THIS style") instead of choosing freely. Fragments live in `prompts/infographic/layouts/*.txt` + `styles/*.txt`; the pairing table is data (constant/JSON), so re-vetting is a one-line change.
  - **Reproducibility**: assignment is a pure function of the persisted router artifact + `candidate_index`, so design-substep restarts keep the original assignment; restarting from `ig_layout` re-routers the pack and reassigns all unselected candidates.
  - **Integration cost** (substep additions touch lockstep spots): `INFOGRAPHIC_SUBSTEPS` in `step_infographic.py`, the allowed-substep list in the restart-infographic-substep view (`generation_views.py`), the accordion defs in `GenerationJobStatus.jsx`, an `LLMStepConfig` seed for the new config key, and a new `prompts/infographic_layout.txt`.

  Pre-vetted layout→style pairings (3 distinct styles assigned per pack from the assigned layout's row):

  | Layout | Vetted styles | Fit notes |
  |--------|---------------|-----------|
  | panorama | modern-editorial, paper-craft | Default scene; current house look stays in the pool |
  | hub-spoke | hand-drawn-edu, flat-vector, chalkboard | Central theme + radiating word vignettes |
  | journey | paper-craft, modern-editorial | Narrative-leaning sets |
  | map | flat-vector, modern-editorial | Spatial word fields |
  | gallery | chalkboard, hand-drawn-edu | Modular vignettes; highest caption legibility |
  | cycle | modern-editorial, flat-vector | Process/cycle sets |
- **Validator additions**: layout/style enum membership (fail loud, not silent-panorama).

### Condition 2 — No variety, skill-informed quality only

**What changes:** keep panorama/gallery + single house style; rewrite the guidance with the skills' depth.

- Rewrite `DEFAULT_INFOGRAPHIC_STYLE` / STYLE_LOCK in the 5-section format (AESTHETIC / MOOD / hex COLOR PALETTE / ELEMENTS / TYPOGRAPHY / AVOID).
- Expand `_PANORAMA_GUIDANCE` / `_GALLERY_GUIDANCE` into full per-layout fragments (text placement, element treatment).
- Hex palette in `color_palette` (validate 3–5 hex codes) instead of named colors.
- Strengthen `big_idea` toward a learning-objective statement; add the cheap validator items (enum membership, distractor sanity in the cloze validator).
- Candidates still differ only by temperature — this condition isolates *prompt quality* from *diversity*.

### Condition 3 — Control (bug fixes only)

- ~~Apply the §4 fixes~~ **Done 2026-08-26** (#1, #2, #4, #5, `layout_mode` validation; #3 deferred as a feature).
- Prompts untouched.

### Experiment protocol

1. **Sample**: 6–9 packs spanning text types (narrative/informational), word counts (4/6/8), and Lexile bands (≤600 / 600–800 / 800+). Existing already-generated packs are fine — reuse keeps word-level content constant across conditions.
2. **Run**: for each pack, generate 3 candidates under each condition (9 posters/pack). Conditions 1–2 need per-condition prompt/config isolation — simplest honest implementation is three short-lived branches (or a feature flag on the design step) run as separate jobs against copies of the same packs; do **not** publish any of it to students.
3. **Evaluate blind**: strip condition labels; admins rate each poster 1–5 on:
   - Text legibility & spelling accuracy (GPT-Image-2 text rendering under each style)
   - Vocab pedagogy: captions use words naturally, marked words visibly emphasized
   - Age appeal (7–14) without childishness
   - Brand/editorial fit
   - Layout clarity (eye-path, findability of each word's anchor)
   Also record **generation failure/retry rate per condition** (complex layouts + heavy-text styles may fail more — that's a real cost).
4. **Decide**: pre-commit to a rule, e.g. a condition wins if it leads on pedagogy+legibility without losing >0.5 avg on brand fit; otherwise Condition 2 (quality) + Condition 1's combo assignment for the *style* axis only is the expected hybrid fallback.
5. **Cost control**: poster renders only (no word-level regeneration). 9 packs × 9 renders = 81 GPT-Image-2 calls at `1792x1024` — plug in the current per-image price before running; trim to 6 packs if needed.

### Effort estimates (rough)

| Work item | Size |
|---|---|
| Bug fixes §4 (#1, #2, #4, #5, `layout_mode` validation) — **done 2026-08-26** | S — ~0.5 day |
| §4 #3 (infographic edit/redraw endpoints, mirroring GN pages) — optional, defer | M — 2–3 days |
| Condition 2 (prompt/constant rewrite + validator additions + tests) | S–M — 1–2 days |
| Condition 1 (`ig_layout` router substep + lockstep integration, fragment files, assignment mechanism, design-prompt restructure, validators, tests) | M — 3–5 days |
| Experiment harness (pack copies, feature flag/branches, rating sheet) | S — ~1 day |
| Human evaluation | 1–2 hours per reviewer |

### Sequencing

1. ~~Land Condition 3 bug fixes first~~ (**done 2026-08-26** — they were prerequisites for trusting any experiment output, #1 especially, since experiment jobs will use restarts).
2. Build Condition 2 (it's a strict subset of Condition 1's prompt work).
3. Build Condition 1 on top.
4. Run the experiment, then fold the winner back as the default and update `AGENTS.md` / `docs/architecture-decisions.md` accordingly.

---

## Appendix — key references

- Pipeline: `backend/vocabulary/services/generation/step_infographic.py` (substeps `:424-448`, validators `:455-569`, image prompt `:700-768`, render `:781-866`); `backend/vocabulary/services/generation/orchestrator.py:140-188`; prompts in `backend/vocabulary/prompts/infographic_{design,cloze,image}.txt`.
- Skills: `C:\Users\admin\infographic-skills\baoyu-infographic\SKILL.md` + `references/` (base-prompt, analysis-framework, structured-content-template, 21 `layouts/*.md`, 22 `styles/*.md`); `C:\Users\admin\infographic-skills\infographic-skill\high-density-infographic-skill.md`.
- Style fragment exemplar worth copying almost verbatim: `baoyu-infographic/references/styles/hand-drawn-edu.md`.
- Layout fragment exemplar: `baoyu-infographic/references/layouts/bento-grid.md`.
