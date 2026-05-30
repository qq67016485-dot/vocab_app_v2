# Plan: Integrate Lexi Legends IP into Graphic Novel Pipeline (Phase 1)

## Context

The vocabulary app generates AI graphic novels for each word pack using a 4-call Claude Sonnet workflow (router → scorer → beat sheet → script) followed by GPT-Image-2 image generation. Currently, stories have no recurring characters, world-building, or visual consistency across packs.

The Lexi Legends IP introduces 4 recurring heroes (Leo, Amara, Mei, Hugo) + a mascot (Folio), a shared universe (The Vault + Story Realms), a magic system (Ink = writing-based magic powered by vocabulary understanding), and age-appropriate visual presentations (9yo / 12yo). Phase 1 wraps this IP around the existing pipeline without adding game mechanics.

Runtime canon assets already exist at `docs/feature_plan/runtime_canon/lexi_legends/` — character sheets, prompt injection files, setting specs, and design rules ready for use.

---

## Implementation Steps

### Step 1: Canon Loading Service

**New file:** `backend/vocabulary/services/canon_service.py`

Responsibilities:
- Determine age band from Lexile (threshold: 800 → below = 9yo, above = 12yo)
- Generate 3 random Away Team options (from 6 pairings + 4 solo = 10 possible teams)
- Load character sheets (`.md` for script calls, `.txt` for image prompts) by name + age
- Load compact image-only character injections (~200 tokens each, stripped of behavioral/story notes)
- Load pairing dynamics for selected team (from cast bible)
- Load Vault/setting specs when needed
- Load rulebook + learning behavior plan
- Extract compact character summaries for the router call

```python
# Key functions
determine_age_band(target_lexile: int) -> str
generate_away_team_options(count: int = 3) -> list[AwayTeam]
load_canon_payload(target_lexile: int) -> CanonPayload
load_team_canon(heroes: list[str], age_band: str) -> TeamCanon
load_vault_canon() -> VaultCanon
get_character_image_injection(character: str, age_band: str) -> str  # compact ~200 token version
get_pairing_dynamics(heroes: list[str]) -> str  # returns dynamics text for the pair
```

**Config addition** in `backend/config/settings.py`:
```python
RUNTIME_CANON_DIR = os.path.join(BASE_DIR, '..', 'docs', 'feature_plan', 'runtime_canon', 'lexi_legends')
LEXI_LEGENDS_AGE_LEXILE_THRESHOLD = 800
```

---

### Step 2: Data Model Migration

Add `metadata` JSONField to `GraphicNovel` model:

```python
metadata = models.JSONField(
    default=dict, blank=True,
    help_text='IP metadata: away_team, age_band, vault_framing, shades_present, review_artifact_type',
)
```

Stores per-novel: `away_team` (hero list), `age_band`, `vault_framing` (bool), `shades_present` (bool), `review_artifact_type` (string).

Add page-level routing fields to `GraphicNovelPage` so image generation does not infer character/setting state from prose or temporary beat-sheet artifacts:

```python
characters_featured = models.JSONField(default=list, blank=True)
setting_key = models.CharField(max_length=80, blank=True, default='')
vault_zone = models.CharField(max_length=80, blank=True, default='')
is_vault_page = models.BooleanField(default=False)
```

The final script output must include these fields on every story page, and `_step_graphic_novel_script()` persists them directly when creating each `GraphicNovelPage`.

---

### Step 3: New Prompt Templates (7 files)

Create IP-aware prompts for the active v1 pipeline. Rollback is handled through source control, not a runtime switch.

#### Workflow Change: 5-Call Pipeline (was 4)

The router is split into two calls to avoid overloading a single LLM invocation with too many decisions:

```
Call 1: Team Selector — picks away team + vault framing + shades (structural decisions)
Call 2: Premise Generator — generates 3 premises tailored to the locked team's dynamics
Call 3: Premise Scorer — scores and picks the best premise
Call 4: Beat Sheet — plans 5-page arc with vocab roles
Call 5: Final Script — generates complete script with panels and cloze items
```

**Why split the router:** The original plan asked one call to simultaneously select a team, decide world-building toggles, AND generate 3 creative premises. This produces generic premises that aren't tailored to the selected team's dynamics. By locking the team first, the premise generator can leverage specific pairing dynamics (e.g., Leo+Amara = "improvisation meets research") to produce better-fitting stories.

#### Information Flow Strategy

**Progressive detail loading** — inject only what each step needs:

| Call | Canon Injected | Token Budget |
|------|---------------|--------------|
| Team Selector (Call 1) | World rules, Ink system, 3 team options with pairing dynamics, character summaries (name + identity + color + learning approach) | ~2K tokens |
| Premise Generator (Call 2) | World rules, locked team with full pairing dynamics, character summaries, Ink system | ~2.5K tokens |
| Scorer (Call 3) | Same as premise generator + 3 premises | ~3K tokens |
| Beat Sheet (Call 4) | Full character sheets (.md) for selected heroes + Folio, Vault script rules (if framing), learning behavior plan, Ink over-reliance guardrail | ~4-6K tokens |
| Script (Call 5) | Compact visual specs (.txt) for image-friendly descriptions, rulebook constraints, review artifact type | ~3K tokens |
| Image prompts | Compact image-only character locks (~200 tokens/char), STYLE_LOCK, optional Vault/zone injection | ~600-900 tokens total |

#### Ink Over-Reliance Guardrail

The IP's magic system creates a tempting shortcut where every word's plot role becomes "hero writes it with Ink and something happens." This satisfies the letter of "vocabulary meaning affects the plot" while hollowing out the spirit.

**Constraint injected at Calls 2, 3, and 4:**
> No more than 2 of the target words may be resolved through direct Ink writing/activation. At least half the vocabulary words must matter through dialogue, character reasoning, narration, or story-world logic — not through magical Ink activation. Ink is one tool among many; understanding is the real power.

**Scorer adds criterion:** `ink_over_reliance` (1-5) — penalizes premises where every word's integration plan is "hero uses Ink to write it."


#### Template Details

| File | Key Changes |
|------|-------------|
| `lexi_legends_graphic_novel_team_selector.txt` | Receives 3 team options with pairing dynamics + character summaries. Outputs: `selected_away_team`, `vault_framing`, `shades_present`, `team_rationale` |
| `lexi_legends_graphic_novel_router.txt` | Receives locked team + pairing dynamics. Generates 3 premises tailored to that team. Includes Ink over-reliance constraint. |
| `lexi_legends_graphic_novel_premise_scorer.txt` | Scoring criteria: `narrative_engagement`, `visual_potential`, `vocabulary_integration`, `character_fit`, `ip_coherence`, `ink_over_reliance`, `originality` |
| `lexi_legends_graphic_novel_beat_sheet.txt` | Receives full character sheets for selected heroes + Folio, Vault rules, learning behavior plan, Ink guardrail. Outputs: beat sheet with `characters_featured` per page, `ink_usage` moments (max 2 direct Ink activations), `review_artifact_type` |
| `lexi_legends_graphic_novel_script.txt` | Receives compact visual specs, rulebook constraints. Characters array uses canonical descriptions with `ink_color` and `ink_style` |
| `lexi_legends_graphic_novel_page.txt` | Per-page character injections (only chars on this page), STYLE_LOCK block, optional Vault/zone injection, Ink as decorative VFX, age-band visual direction |
| `lexi_legends_graphic_novel_review_page.txt` | Folio injection only, artifact type from beat sheet, no full team injection |

#### STYLE_LOCK Block (prepended to every image prompt)

Without an explicit style anchor, GPT-Image-2 will drift between cel-shaded, painterly, and semi-realistic rendering across pages. Every page prompt begins with:

```
STYLE_LOCK: Consistent digital comic art. Clean ink outlines, flat color fills with
soft cel-shading, warm lighting. No photorealism, no watercolor, no 3D rendering.
Line weight: medium. Color saturation: high. Expressive faces, clear silhouettes.
```

#### Per-Page Character Injection (not per-novel)

Character design locks are injected **only for characters who appear on that specific page**, not for the entire away team on every page. This:
- Keeps prompt length under control (~200 tokens per character × 1-2 characters = 200-400 tokens)
- Prevents GPT-Image-2 from inserting absent characters into scenes
- Reserves token budget for scene composition and panel content

The image step reads persisted `GraphicNovelPage.characters_featured` to determine which character locks to inject. It does not infer characters from `panel_descriptions`.

#### Structured Ink + Scoring Schemas

Router premises must include:

```json
"vocab_integration_plan": [
  {
    "term": "word",
    "story_role": "plot role, not a definition",
    "integration_mode": "visual_clue",
    "uses_direct_ink": false
  }
]
```

Allowed `integration_mode` values: `dialogue`, `reasoning`, `narration`, `world_logic`, `direct_ink_activation`, `visual_clue`, `character_action`.

Scorer entries must include all dimensions: `narrative_engagement`, `visual_potential`, `vocabulary_integration`, `character_fit`, `ip_coherence`, `ink_over_reliance`, `originality`.

Beat sheet output must include `ink_usage`:

```json
"ink_usage": [
  {
    "term": "word",
    "page": 1,
    "uses_direct_ink": false,
    "purpose": "The word helps the hero reason through a clue."
  }
]
```

Validators count `uses_direct_ink == true` and reject router/beat outputs with more than 2 direct Ink activations.

---

### Step 4: Pipeline Service Integration

**File:** `backend/vocabulary/services/generation_pipeline_service.py`

#### 4a. Update `GRAPHIC_NOVEL_SUBSTEPS` (now 5 steps)

```python
GRAPHIC_NOVEL_SUBSTEPS = [
    {'key': 'team_selection', 'label': 'Team Selection', 'template': 'lexi_legends_graphic_novel_team_selector', 'filename': '01_team_selection.json'},
    {'key': 'router_premises', 'label': 'Router + Premises', 'template': 'lexi_legends_graphic_novel_router', 'filename': '02_router_premises.json'},
    {'key': 'premise_scoring', 'label': 'Premise Scoring', 'template': 'lexi_legends_graphic_novel_premise_scorer', 'filename': '03_premise_scoring.json'},
    {'key': 'beat_sheet_vocab_roles', 'label': 'Beat Sheet + Vocab Roles', 'template': 'lexi_legends_graphic_novel_beat_sheet', 'filename': '04_beat_sheet_vocab_roles.json'},
    {'key': 'final_script_self_check', 'label': 'Final Script + Self-Check', 'template': 'lexi_legends_graphic_novel_script', 'filename': '05_final_script_self_check.json'},
]
```

#### 4b. Modify `_step_graphic_novel_script`:

```
1. Load CanonPayload at start (age band, team options, summaries, pairing dynamics, rulebook)
2. Per pack:
   a. Call 1 (Team Selector): inject 3 team options with pairing dynamics, character summaries
   b. Extract selected_away_team, vault_framing, shades_present
   c. Load TeamCanon for selected heroes + Folio at determined age band
   d. Load VaultCanon if vault_framing = true
   e. Call 2 (Premise Generator): inject locked team + pairing dynamics + Ink guardrail
      → generates 3 premises tailored to this team
   f. Call 3 (Scorer): pass premises + IP scoring criteria (including ink_over_reliance)
   g. Call 4 (Beat Sheet): pass full character sheets (heroes + Folio), vault rules,
      learning behavior plan, Ink guardrail (max 2 direct activations)
   h. Call 5 (Script): pass compact visual specs, review artifact type, rulebook constraints
   i. Store IP metadata on GraphicNovel record
```

#### 4c. Modify `_step_graphic_novel_images`:

```
1. Read novel.metadata (away_team, age_band, vault_framing)
2. Load team's image injections (compact ~200 token versions)
3. Load vault image prompt if vault_framing
4. Per page:
   a. Read characters/setting routing from persisted page fields (`characters_featured`, `setting_key`, `vault_zone`, `is_vault_page`)
   b. Assemble prompt in order:
      1) STYLE_LOCK block
      2) Page composition + layout (panel count, layout description)
      3) Panel content + scene descriptions
      4) Character design locks (ONLY for characters on this page)
      5) Setting injection (if page is in Vault)
      6) Vocabulary in speech bubbles/captions; Ink VFX as decorative color (last line)
   c. Ink VFX = atmospheric character-colored glow, not legible text
```

#### 4d. New helper functions:

Implementation update: `_characters_on_page()` should read `page.characters_featured`, and `_page_is_in_vault()` should read `page.is_vault_page`. Do not infer these values from panel prose or temporary beat-sheet files.
- `_build_lexi_legends_image_prompt(page, template, team_canon, vault_canon, metadata)` → assembled prompt with correct ordering
- `_characters_on_page(page, metadata)` → list of character names on this specific page (reads panel_descriptions)
- `_page_is_in_vault(page, metadata)` → bool (checks beat sheet's vault_pages)
- `_get_style_lock()` → returns the STYLE_LOCK block string

---

### Step 5: Validation Updates

Update existing validators in `generation_pipeline_service.py`:

Implementation update: validators should use structured fields instead of parsing prose. Router and beat validation count `uses_direct_ink == true` and reject more than 2 direct Ink activations. Scorer validation requires every explicit scorer dimension, including `ink_over_reliance`. Final script validation requires every page to include `characters_featured`, `setting_key`, `vault_zone`, and `is_vault_page`.

- `_validate_graphic_novel_team_result`: require `selected_away_team` (must be one of the 3 provided options), `vault_framing`, `shades_present`
- `_validate_graphic_novel_router_result`: require 3 premises with structured `vocab_integration_plan`; validate allowed `integration_mode`; reject more than 2 `uses_direct_ink == true`
- `_validate_graphic_novel_scoring_result`: require every scorer dimension, including `ink_over_reliance`
- `_validate_graphic_novel_beat_result`: check `characters_featured`, `setting_key`, `vault_zone`, and `is_vault_page` per page; require `review_artifact_type`; validate structured `ink_usage`; reject more than 2 direct Ink activations
- `_validate_graphic_novel_script_result`: require every final script page to include `characters_featured`, `setting_key`, `vault_zone`, and `is_vault_page`

---

### Step 6: Tests

- Unit tests for `canon_service.py`: age band logic, team generation (randomness + validity), file loading, summary extraction
- Integration test: mock Claude/GPT-Image calls, verify correct canon is injected at each step
- Verify GraphicNovel.metadata is populated correctly after script step
- Verify `GraphicNovelPage` page-routing fields are persisted from final script output
- Verify router and beat validators count direct Ink from structured `uses_direct_ink`
- Verify scorer validator requires all explicit scoring dimensions
- Verify image prompts inject only page-listed characters and include Vault/zone context only for Vault pages

---

## Critical Files

| File | Action |
|------|--------|
| `backend/vocabulary/services/canon_service.py` | **CREATE** |
| `backend/vocabulary/services/generation_pipeline_service.py` | MODIFY |
| `backend/vocabulary/models.py` | MODIFY (add metadata field) |
| `backend/config/settings.py` | MODIFY (add canon config) |
| `backend/vocabulary/prompts/lexi_legends_graphic_novel_team_selector.txt` | **CREATE** |
| `backend/vocabulary/prompts/lexi_legends_graphic_novel_router.txt` | **CREATE** |
| `backend/vocabulary/prompts/lexi_legends_graphic_novel_premise_scorer.txt` | **CREATE** |
| `backend/vocabulary/prompts/lexi_legends_graphic_novel_beat_sheet.txt` | **CREATE** |
| `backend/vocabulary/prompts/lexi_legends_graphic_novel_script.txt` | **CREATE** |
| `backend/vocabulary/prompts/lexi_legends_graphic_novel_page.txt` | **CREATE** |
| `backend/vocabulary/prompts/lexi_legends_graphic_novel_review_page.txt` | **CREATE** |
| `backend/tests/vocabulary/test_canon_service.py` | **CREATE** |

---

## Existing Assets to Reuse

| Asset | Location | Used In |
|-------|----------|---------|
| Character prompt injections (.txt) | `docs/feature_plan/runtime_canon/lexi_legends/cast/{name}/` | Source for compact image injections (~200 token trimmed versions) |
| Character full sheets (.md) | Same directory | Beat sheet + script calls (personality, dialogue voice, learning behavior) |
| Pairing dynamics | `docs/feature_plan/lexi-legends-cast-bible.md` (Pairing Dynamics section) | Team selector + premise generator (extracted into canon service) |
| Vault image prompt | `docs/.../settings/the-vault-image-prompt.txt` | Image prompts for Vault pages |
| Vault script rules | `docs/.../settings/the-vault-script.md` | Beat sheet call |
| Vault zones script | `docs/.../settings/vault-zones-script.md` | Beat sheet call |
| Zone image prompts | `docs/.../settings/vault-zone-*-image-prompt.txt` | Image prompts for zone pages |
| Rulebook | `docs/.../rulebook.md` | Script call constraints |
| Learning behavior plan | `docs/.../script-learning-behavior-plan.md` | Beat sheet call |
| `load_prompt_template()` | `backend/vocabulary/services/llm_service.py` | Reuse as-is |
| `_format_graphic_novel_prompt()` | `generation_pipeline_service.py:1502` | Reuse as-is |
| `_call_anthropic_releasing_db()` | `generation_pipeline_service.py` | Reuse as-is |
| `_call_openai_image_releasing_db()` | `generation_pipeline_service.py` | Reuse as-is |

---

## Verification

1. `python manage.py makemigrations && python manage.py migrate` — clean migration
2. `pytest backend/tests/` — all existing tests pass
3. `pytest backend/tests/vocabulary/test_canon_service.py -v` — canon service tests pass
4. Manual integration test via admin wizard:
   - Router output includes `selected_away_team` and `vault_framing`
   - Beat sheet references canonical characters by name
   - Script output has characters with `ink_color`/`ink_style`
   - Image prompts contain character design locks prepended
   - GraphicNovel.metadata is populated
   - Generated images show consistent character appearances across pages
