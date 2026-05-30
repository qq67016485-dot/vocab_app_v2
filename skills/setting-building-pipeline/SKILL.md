---
name: setting-building-pipeline
description: "Use when generating, revising, splitting, reviewing, or syncing Lexi Legends runtime setting canon sheets. Supports image-generation sheets, script-generation sheets, combined setting sheets, asset-production simplification passes, bible synchronization, and the full setting-building workflow: draft, persona review, targeted revision, canon/model-readiness review, and verification."
---

# Setting Building Pipeline

## Overview

Use this skill to produce production-ready Lexi Legends runtime setting sheets under `backend/data/canon/settings/`.

Settings are not just background descriptions. They are runtime source-of-truth payloads that keep script generation, image generation, future game art, and bible summaries aligned. The main goal is to prevent drift while preserving Story Realm flexibility.

Prefer split sheets for major recurring settings:

- `*-image.md` for visual source of truth and image generation.
- `*-script.md` for scene behavior, story function, and script generation.

Use a combined `*.md` sheet only when the setting or system is compact enough to stay prompt-friendly and does not need separate image/script payloads. If a legacy combined sheet exists, do not extend it by default; create or update the split runtime files unless the user asks to preserve the combined format.

Top-level bibles are compressed routing and summary documents. Runtime setting sheets win when exact visual or script behavior is needed.

## Operating Principles

- Simple but specific beats ornate. Use clean shape language, stable silhouettes, exact material/palette anchors, and tight object budgets.
- Design for image generation and future game assets. Prefer modular kits, repeated geometry, broad readable surfaces, and few hero props over dense decorative set dressing.
- Protect prompt size. If a sheet is becoming long, split image and script payloads instead of making one giant canon file. Remove repeated bible prose from runtime sheets.
- Keep visual drift controls explicit: module count, active object count, scale anchors, negative space, palette hierarchy, and clear Do Not rules.
- Keep script drift controls explicit: entry/exit logic, story function, optional versus required elements, age treatment, and vocabulary/Ink behavior.
- Sync compressed bibles after runtime canon changes. Update only what the bibles need to route future prompts; do not copy the full sheet into a bible.
- Search for stale terms after revisions. Rename labels that imply the wrong asset, such as a table when the canon now requires a floor platform.

## Default Core Setting Sheets

When the user asks to create the core Lexi Legends setting sheets without naming specific targets, build this batch:

| Sheet | Target path | Runtime use | Purpose |
| --- | --- | --- | --- |
| The Vault Image | `backend/data/canon/settings/the-vault-image.md` | image generation | Stable home-base visuals, architecture, modular asset kit, palette, lighting, panel rules. |
| The Vault Script | `backend/data/canon/settings/the-vault-script.md` | script generation | Stable home-base story function, scene behavior, portal logic, review/setup use. |
| Vault Zones | `backend/data/canon/settings/vault-zones.md` | image and script, split if large | Reading Stacks, Map Platform, Ink Well, Field Desk, Quiet Nook, and how zones differ without bloating the Vault. |
| Portals & Story Objects | `backend/data/canon/settings/portals-and-story-objects.md` | image and script, split if large | Physical story-bearing objects that open Story Realms without becoming ornate portal machinery. |
| Ink VFX System | `backend/data/canon/settings/ink-vfx-system.md` | image and script | Universal writing-based Ink rules shared across character-specific Ink styles. |
| Shades | `backend/data/canon/settings/shades.md` | image and script | Optional shadow/static/page-glitch antagonists and age-safe visual behavior. |
| Lexi Monster Design System | `backend/data/canon/settings/lexi-monster-design-system.md` | image and script | Rules for generating story-specific vocabulary manifestations without creating one fixed monster. |
| Review Artifact System | `backend/data/canon/settings/review-artifact-system.md` | image and script | Sixth-page in-world artifact rules that keep vocabulary readable without becoming worksheets. |

Optional follow-up sheets, when needed:

- `backend/data/canon/settings/story-realm-visual-adapter.md`
- `backend/data/canon/settings/vault-interface-objects.md`
- Per-realm setting sheets for recurring Story Realms.

## Pipeline

### 1. Confirm Scope From The Request

Identify:

- Setting item or batch name.
- Sheet category: `environment`, `zone set`, `object/interface system`, `VFX system`, `optional antagonist`, `creature design system`, `review artifact system`, or `bible sync`.
- Runtime use: `image generation`, `script generation`, `combined`, or `sync only`.
- Target path or path pair under `backend/data/canon/settings/`, using lowercase kebab-case filenames.
- Whether the user wants a new sheet, a revision, a split of an existing sheet, a bible sync, a review-only pass, or a full pipeline run.
- Whether old bible summaries must be updated after the runtime change.

If the request clearly asks for this pipeline, continue without asking extra questions unless the target cannot be inferred.

### 2. Load Local Canon

Read only the context needed for the target:

- `backend/data/canon/rulebook.md`
- `docs/feature_plan/lexi-legends-setting-bible.md`
- `docs/feature_plan/lexi-legends-visual-production-bible.md`
- `docs/feature_plan/lexi-legends-audiobook-production-bible.md` when script, ambience, narration, or sound behavior is affected.
- Existing setting sheets, including the image/script pair if either exists.
- Relevant cast sheets only when the setting item directly interacts with hero readability, Ink, Folio projections, review artifacts, or signature tools.
- `backend/data/canon/lexi-legends-cast-bible.md` when the setting could obscure hero signatures or when bible sync may touch Folio/Vault interface wording.

Prefer local project docs over memory.

### 3. Choose The Runtime Payload Shape

Use an image sheet when the setting appears visually or controls visual consistency.

Use a script sheet when the setting controls scene entry, story structure, emotional tone, portal behavior, review setup, or recurring interactions.

Split image and script sheets when any of these are true:

- The setting is recurring or core to the IP.
- The combined file would be too large to place beside character sheets in one API prompt.
- Visual details and script behavior are both substantial.
- The sheet needs game-asset or image-generation constraints.
- A user says the combined file is too big for API calls.

Use a combined sheet only when the total payload can remain compact and the setting does not need different instructions for image and script generation.

Prompt-size guidance:

- Keep image sheets focused on drift prevention, not prose worldbuilding.
- Prefer about 1,200 to 2,400 words for a major image sheet.
- If a combined setting sheet grows past about 2,400 words, split it or trim repeated script/visual material.
- Avoid duplicate prompt capsules inside runtime sheets unless the user specifically asks.

### 4. Use The Right Sheet Template

For image-generation setting sheets:

```md
# [Setting Item] Image Sheet

Runtime use: image generation
Payload rule: load this sheet when [setting item] appears visually or when its architecture/object system is visible

## Critical Rules
## Core Visual Identity
## Spatial Blueprint / Object Blueprint
## Modular Visual Kit
## Materials, Palette & Lighting
## Scale & Composition
## Hero Readability / Text Readability
## Panel Priority
## Visual Constraints
```

For script-generation setting sheets:

```md
# [Setting Item] Script Sheet

Runtime use: script generation
Payload rule: load this sheet when [setting item] affects scene setup, plot behavior, review framing, or recurring interaction

## Core Story Function
## How It Appears In Scenes
## Stable Rules
## Vocabulary, Ink, And Language Behavior
## Age Presentation Treatment
## Variation Rules
## Optional Uses
## Do Not
```

For compact combined sheets:

```md
# [Setting Item] Setting Sheet

Runtime use: script generation and image generation
Payload rule: load this sheet when [setting item] appears or controls a visual/story system

## Core Identity
## Story Function
## Visual Design
## Materials, Palette & Lighting
## Scale & Composition
## Behavior Rules
## Word, Ink, And Language Behavior
## Age Presentation Treatment
## Variation Rules
## Do Not
```

Add optional sections only when they solve a drift problem:

- `## Zone Rules` for multi-zone sheets.
- `## Object Families` for portals, story objects, tools, devices, and interfaces.
- `## Failure And Success States` for Ink, Shades, review artifacts, and portals.
- `## Semantic Design Logic` for Lexi Monsters.
- `## Review Page Layout Rules` for review artifacts.
- `## Interaction With Recurring Heroes` when the setting could obscure signature outfits, tools, or Ink colors.

### 5. Draft Or Revise The Sheet

Make each runtime sheet standalone. Assume the model may receive this sheet without the full bible.

Generation standards:

- Name the stable identity in concrete terms: silhouette, architecture or object geometry, material hierarchy, palette, lighting, iconography, and surface detail.
- Separate stable canon from story-specific variation.
- Define script behavior separately from image behavior when the setting needs both.
- Keep vocabulary, Ink, readable English, and child agency central where relevant.
- Protect target words and definitions from decorative over-styling.
- Avoid requiring Shades, Lexi Monsters, or The Vault in every story unless the sheet is about that item.
- Keep palette and VFX relationships clear, especially Folio blue-white, Leo cyan, Amara gold, Mei multicolor Ink, Hugo orange, Vault warm light, and Shade charcoal/violet.
- Use `apply_patch` for manual edits. Do not change backend prompts, models, migrations, or frontend UI in this workflow.

Asset-production standards:

- Define 3 to 6 reusable modules for major environments or object systems.
- Limit panels to a small number of modules and one active story object unless the user asks for a maximal scene.
- Use broad negative space, clean silhouettes, and scale anchors.
- Avoid dense prop fields, tiny labels, decorative machinery clusters, complex fake mechanisms, and unique one-off objects that must be redesigned in every panel.
- If a setting feels expensive to model, animate, or render as a game location, simplify the style before adding more lore.

### 6. Run Persona Reviews

By default, run these as local review lenses. Use read-only subagents only when the user explicitly asks for agents, delegation, or parallel review.

Graphic Novel World Writer lens:

```text
Review `<TARGET_SHEET_OR_BATCH>` as an expert graphic novel world writer for Lexi Legends. Evaluate whether the setting gives script generation reusable story fuel while preserving flexibility: story function, emotional tone, childlike wonder, vocabulary-driven action, optional-conflict handling, and avoidance of formula. Flag places where the setting could become a classroom, generic fantasy, fixed plot template, or over-explained lesson. Return prioritized findings with concrete rewrite suggestions.
```

Graphic Novel Art Director lens:

```text
Review `<TARGET_SHEET_OR_BATCH>` as an expert graphic novel art director for Lexi Legends. Evaluate whether the setting is sufficient for stable image generation: silhouette, architecture or object geometry, materials, lighting, palette hierarchy, scale, VFX behavior, text readability, age-band treatment, panel clarity, and Do Not constraints. Flag ambiguity, drift risks, overdesigned details, visual contradictions, and anything likely to confuse image models. Return prioritized findings with concrete rewrite suggestions.
```

Game Art / Asset Production Designer lens:

```text
Review `<TARGET_SHEET_OR_BATCH>` as a game art and asset-production designer. Evaluate whether the setting can become a reusable game module: modularity, object budget, repeated geometry, negative space, collision/readability, UI clarity, asset count, animation burden, and how many unique objects must be built. Flag expensive detail, over-specific props, hard-to-reuse layouts, and places where simpler futuristic or graphic shapes would reduce drift. Return prioritized findings with concrete rewrite suggestions.
```

Prompt Payload / Model Readiness Editor lens:

```text
Review `<TARGET_SHEET_OR_BATCH>` as a prompt payload editor. Evaluate whether the sheet can be loaded with character sheets and other setting sheets in one API call: length, duplication, instruction priority, stable terminology, image/script separation, and whether old bible summaries should be synced. Flag bloated prose, repeated details, ambiguous labels, and stale references. Return prioritized findings with concrete rewrite suggestions.
```

For large multi-sheet batches, add a continuity pass:

```text
Review `<TARGET_SHEET_BATCH>` as a Lexi Legends setting continuity editor. Check shared terminology, palette relationships, how Ink differs from Folio projections and Shade effects, how portals differ from review artifacts, and whether any sheet accidentally makes optional elements mandatory. Return prioritized cross-sheet findings with concrete rewrite suggestions.
```

### 7. Consolidate Feedback

Do not blindly apply every suggestion. Consolidate by impact:

- Must fix: drift risks, text-readability problems, palette contradictions, optional elements becoming mandatory, setting identity becoming generic, age-safety issues, excessive asset complexity, prompt bloat, or conflicts with recurring hero signatures.
- Useful tweak: sharper shape language, clearer material rules, better variation boundaries, stronger panel priority, better success/failure states, tighter module definitions.
- Defer: ideas that belong in story prompts, individual Story Realm bibles, specific Lexi Monster sheets, future game asset briefs, or concept art prompts.
- Reject: suggestions that conflict with user decisions, current runtime canon, compactness, or the open-ended Story Realm model.

Prefer changes that make the setting more visually distinct without locking every story into the same plot or forcing expensive art assets.

### 8. Apply Targeted Revisions

Use targeted edits. Preserve the user's chosen formatting, encoding, punctuation, and separators unless the user confirms a real display problem.

Common revisions:

- Add shape-language anchors for environments, objects, or VFX.
- Clarify modular asset kits, material hierarchy, palette, lighting, and scale.
- Separate readable vocabulary text from decorative marks.
- Add panel-priority and object-budget rules for crowded scenes.
- Add age-presentation treatment for density, scariness, clue subtlety, and review-page complexity.
- Clarify what can vary by Story Realm and what must remain stable.
- Strengthen Do Not constraints for likely model failures.
- Remove wording that turns an optional system into a required plot device.
- Rename stale terms that imply the wrong art asset or behavior.

Reread changed sections before continuing.

### 9. Run Canon And Pedagogy Review

After creative revisions, use the project skill at `skills/review-canon-sheets/SKILL.md` on the revised sheet or batch.

Follow that skill's workflow:

- Prompt-engineering/model-instruction lens.
- Reading/literacy curriculum lens.
- Child-development and representation lens.

By default, run this as a local three-lens review. Spawn specialist agents only when the user explicitly asks for another delegated canon review.

For setting sheets, pay special attention to:

- Whether word meaning, context, and semantic precision remain visually actionable.
- Whether the sheet supports vocabulary learning without creating worksheet pages.
- Whether scary or tense elements stay age-safe.
- Whether spaces and artifacts invite child agency instead of adult authority.
- Whether the model can load the sheet alone and still preserve the intended visual identity.

### 10. Sync Compressed Bibles

When runtime setting canon changes, update old bibles only as needed:

- `docs/feature_plan/lexi-legends-setting-bible.md` for universe/source routing, story function, and compressed setting summaries.
- `docs/feature_plan/lexi-legends-visual-production-bible.md` for image-generation summary, palette anchors, prompt capsules, and visual constraints.
- `docs/feature_plan/lexi-legends-audiobook-production-bible.md` only when ambience, narration, sound, or script-facing behavior changed.
- `backend/data/canon/lexi-legends-cast-bible.md` only when hero/Folio interface wording or readability constraints changed.

Bible sync rules:

- Make bibles point to split runtime files as the exact source of truth.
- Keep bible changes compact. Do not paste the full runtime sheet.
- Update stale labels and prompt capsules.
- Search for old terminology after edits.
- If a runtime change is image-only, do not force audio/cast changes.

### 11. Batch Consistency Pass

For the default core setting batch, run one final cross-sheet pass before the final response:

- Image and script files use matching setting names but do not duplicate unnecessary detail.
- The Vault and Vault Zones do not contradict each other.
- The Vault uses `Map Platform`, not `Map Table`, unless the user intentionally restores a table.
- Ink VFX does not conflict with character-specific Ink identities.
- Shades remain optional, age-safe, non-gory, and non-violent.
- Lexi Monsters remain optional and story-specific.
- Review artifacts remain in-world and readable, not textbook appendices.
- Portals and story objects begin from physical story-bearing objects, not empty-space swirls.
- Palette relationships stay clear across Vault light, Folio projections, hero Ink, portal glow, and Shade static.

### 12. Verify

Before final response:

- Confirm each target file exists at the canonical runtime path.
- Reread the changed sections.
- Search for stale terms introduced by older canon.
- Check `git status --short -- <target paths>`.
- Run skill validation after editing this skill itself.
- For docs-only work, say tests were not needed.
- Mention any deferred follow-up, such as optional Story Realm visual adapter sheets, specific per-story Lexi Monster sheets, or concept art generation from the image sheet.

## Concept Art Handoff

When the user asks to generate concept art for a setting, use the image sheet only, not the script sheet or compressed bible, unless the user explicitly asks for a merged prompt. If the image sheet is long, extract the critical visual identity, modular kit, material/palette, scale/composition, and Do Not constraints into a concise image prompt.

## Output Shape

For an implemented pipeline run, final response should be short:

- Files changed.
- Review passes performed.
- Most important improvements.
- Verification.

For a review-only pipeline run, return:

- Consolidated findings.
- Targeted edit plan.
- Acceptance checks.
