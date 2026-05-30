# Lexi Legends Pipeline Integration — Implementation Review

Reviewed: 2026-05-22

## Status

The 5-call pipeline structure, data model, validators, and tests are implemented and syntactically valid. The core workflow runs. All high-priority gaps have been resolved via `canon_service.py` (2026-05-22).

---

## What's Done

- 5-call pipeline: team selector → router → scorer → beat sheet → script
- `GraphicNovel.metadata` JSONField (away_team, age_band, vault_framing, shades_present, review_artifact_type)
- Page-level routing fields on `GraphicNovelPage` (characters_featured, setting_key, vault_zone, is_vault_page)
- Per-page character filtering via `_characters_for_graphic_novel_page()`
- Ink over-reliance guardrail: validators enforce max 2 `uses_direct_ink` in router and beat sheet
- `ink_over_reliance` scoring dimension in scorer
- Structured `vocab_integration_plan` with `integration_mode` enum
- Ink VFX described as decorative in image prompt template
- Review page uses `review_artifact_type` from metadata
- Tests: happy path (5 calls), failed substep, too many Ink uses, missing scorer dimensions, missing vocab roles

---

## High Priority Gaps

### 1. No runtime canon file loading

**Plan says:** Load character sheets (.md) into beat sheet/script calls. Load compact image-only character injections (~200 tokens) into image prompts. Load Vault specs, rulebook, and learning behavior plan from `docs/feature_plan/runtime_canon/lexi_legends/`.

**Status: RESOLVED (2026-05-22)** — `canon_service.py` loads all canon files. Full `.md` sheets injected into beat sheet + script calls via `lexi_context`. Compact `_prompt_injection.txt` files injected into image prompts via `_characters_for_graphic_novel_page()`.

### 2. No STYLE_LOCK in image prompts

**Plan says:** Prepend a STYLE_LOCK block to every image prompt to prevent rendering style drift across pages.

**Status: RESOLVED (2026-05-22)** — Fixed STYLE_LOCK block added to `graphic_novel_page.txt` and `graphic_novel_review_page.txt`.

---

## Medium Priority Gaps

### 3. Team options: all 10 passed instead of 3 random

**Plan says:** Use RNG to pick 3 candidate team compositions, then let the team selector pick the best fit.

**Status: RESOLVED (2026-05-22)** — `random.sample(ALL_TEAM_OPTIONS, 3)` now picks 3 from 10.

### 4. Setting context is a stub

**Plan says:** Load detailed Vault image prompt from runtime canon for pages set in The Vault.

**Status: RESOLVED (2026-05-22)** — `_format_graphic_novel_setting_context()` now calls `load_vault_image_prompt(vault_zone)` which loads the full Vault image prompt + zone-specific overlay.

### 5. Pairing dynamics not injected

**Plan says:** Load pairing dynamics from cast bible and pass to team selector + premise generator so the LLM can leverage specific team chemistry.

**Status: RESOLVED (2026-05-22)** — `load_pairing_dynamics()` parses the cast bible and injects all pair dynamics into `team_input`. For 2-hero teams, specific pair dynamics are also added to `lexi_context`.

---

## Low Priority / Deferred

### 6. No separate canon_service.py

**Status: RESOLVED (2026-05-22)** — `backend/vocabulary/services/canon_service.py` created with all loading functions, `lru_cache`, path traversal guards, and graceful fallbacks.

### 7. Template naming uses no prefix

Plan said `lexi_legends_graphic_novel_*.txt`; implementation uses `graphic_novel_*.txt` (replaced in-place). This is consistent with the plan's updated note that rollback is via source control. No action needed.

---

## Suggested Implementation Order

All items completed 2026-05-22:

1. ~~Canon service (file loading infrastructure)~~ ✓
2. ~~Inject character sheets into beat sheet + script calls~~ ✓
3. ~~Inject character image locks into image prompts (per-page)~~ ✓
4. ~~Add STYLE_LOCK to image templates~~ ✓
5. ~~Inject Vault specs into image prompts for vault pages~~ ✓
6. ~~Inject pairing dynamics into team selector + router~~ ✓
7. ~~Randomize team options to 3~~ ✓
