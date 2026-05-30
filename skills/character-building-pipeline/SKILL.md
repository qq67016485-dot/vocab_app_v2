---
name: character-building-pipeline
description: Use when generating or revising Lexi Legends runtime character sheets through the full character-building workflow: draft the sheet, run graphic-novel writer and art-director reviews, apply targeted revisions, then run review-canon-sheets and apply final canon/pedagogy/model-readiness fixes.
---

# Character Building Pipeline

## Overview

Use this skill to produce production-ready Lexi Legends runtime character sheets through a stepped draft-review-revision pipeline. The pipeline is designed for standalone Markdown sheets under `backend/data/canon/cast/<character>/`.

This skill may create or revise visual/audio sheets, but the current default is a cast visual sheet. Keep the generated sheet as the runtime payload unit: do not add separate prompt capsules unless the user asks.

## Pipeline

### 1. Confirm Scope From The Request

Identify:

- Character name.
- Age band: `9 years old` or `12 years old`.
- Sheet type: usually `visual`; use `audio` only if requested.
- Target path for current visual runtime sheets, using `backend/data/canon/cast/<character>/<age>_<Character>.md`, for example `backend/data/canon/cast/amara/9_years_old_Amara.md`.
- Whether the user wants a new sheet, a revision, or a full pipeline run.

If the request clearly asks for this pipeline, continue without asking extra questions unless a required character/Age Presentation is missing.

### 2. Load Local Canon

Read only the context needed for the target:

- `backend/data/canon/rulebook.md`
- Existing same-character sheets, if any.
- Similar completed sheets, usually Leo and Amara for style and depth.
- `backend/data/canon/lexi-legends-cast-bible.md` for character role anchors.
- `docs/feature_plan/lexi-legends-visual-production-bible.md` for visual sheets.
- `docs/feature_plan/lexi-legends-audiobook-production-bible.md` only for audio sheets.

Prefer local project docs over memory.

### 3. Generate The Initial Sheet

Draft or update the sheet at the canonical runtime path.

For cast visual sheets, use this structure unless the user requests otherwise:

```md
# [Character] ([9 years old or 12 years old]) Visual Sheet

Runtime use: script generation and image generation
Age: [9 years old or 12 years old]
Payload rule: load this entire sheet when [Character] ([9 years old or 12 years old]) appears in a story

## Core Identity
## Story Role & Personality
## Dialogue Voice
## Physical Design
## Outfit
## [Signature Tool]
## Color Palette
## Panel Priority
## Ink VFX
## Realm Adaptation
## Do Not
```

Generation standards:

- Make Age Presentation direction standalone; do not rely on comparison to another sheet.
- Include concrete face, skin tone, hair, height, build, outfit, prop, palette, and silhouette anchors.
- Keep personality/story role compact but useful for script generation.
- Include sample phrases as inspiration, not mandatory lines.
- Make Ink meaning-driven and readable.
- Protect target vocabulary words from decorative over-styling.
- Keep character signatures stable across age bands.
- Avoid pair dynamics and solo-strength sections unless the user asks.

Use `apply_patch` for manual edits. Do not change backend prompts, models, migrations, or frontend UI in this workflow.

### 4. Run Two Creative Review Agents

This pipeline includes explicit authorization to use two read-only subagents for review. Spawn them in parallel after the initial sheet exists.

Graphic Novel Writer prompt:

```text
You are reviewing `<TARGET_SHEET>` as an expert graphic novel writer. Do not edit files. Read the target sheet and relevant local canon if useful. Evaluate whether the character works as a recurring graphic-novel character for Lexi Legends: story role, personality, emotional arc potential, dialogue voice, childlike agency, conflict/flaw, comedy, and whether the sheet gives a script generator enough usable story fuel without becoming formulaic. Flag overlap with existing heroes and any wording likely to create repetitive stories. Return prioritized findings with concrete rewrite suggestions.
```

Graphic Novel Art Director prompt:

```text
You are reviewing `<TARGET_SHEET>` as an expert graphic novel art director. Do not edit files. Read the target sheet and relevant local canon if useful. Evaluate whether the sheet is sufficient for stable image generation and panel-to-panel consistency: silhouette, face, hair, headgear, outfit construction, color hierarchy, writing-tool props, Ink VFX, action readability, age read, and Do Not constraints. Flag ambiguity, drift risks, overdesigned details, panel clarity issues, and anything likely to confuse image models. Return prioritized findings with concrete rewrite suggestions.
```

While agents run, do a local pass against the rulebook and nearby sheets.

### 5. Consolidate Creative Feedback

Do not blindly apply every suggestion. Consolidate by impact:

- Must fix: drift risks, age-read problems, signature contradictions, role overlap, repeated-story risks.
- Useful tweak: sharper wording, clearer panel behavior, better catch phrases, stronger emotional motivation.
- Defer: ideas that belong in a broader story guide, learning guide, or future audio sheet.
- Reject: suggestions that conflict with user decisions, brand signatures, or runtime-sheet compactness.

Prefer changes that make the character more distinct without making the sheet bloated.

### 6. Apply Creative Revisions

Use targeted edits. Preserve the user's chosen formatting, encoding, punctuation, and separators unless the user confirms a real display problem.

Common revisions:

- Reframe an archetype that pulls toward the wrong genre.
- Broaden a story role that over-cues one plot type.
- Make a flaw distinct from other heroes.
- Add a real emotional reason behind the flaw.
- Lock silhouette, hair, face, headgear, outfit geometry, and prop handling.
- Reduce VFX noise around readable words.
- Strengthen Do Not constraints for likely model failures.

Reread changed sections before continuing.

### 7. Run `review-canon-sheets`

After creative revisions, use the project skill at `skills/review-canon-sheets/SKILL.md` on the revised sheet.

Follow that skill's workflow:

- Prompt-engineering/model-instruction lens.
- Reading/literacy curriculum lens.
- Child-development and representation lens.

By default, run this as a local three-lens review. Spawn the `review-canon-sheets` specialist agents only when the user explicitly asks for another delegated canon review.

### 8. Apply Canon Review Revisions

Apply only the canon-review changes that materially improve runtime reliability, pedagogy, age realism, or representation.

Typical fixes:

- Make instructions more model-sticky and less ambiguous.
- Separate decorative effects from target vocabulary lettering.
- Reframe flaws without removing story tension.
- Add compact word-learning behavior without turning the visual sheet into a pedagogy guide.
- Move identity details into physical design/palette rather than brand-signature shorthand when needed.
- Add child-realism lines when a character reads too polished or adult.

### 9. Verify

Before final response:

- Confirm the target file exists at the canonical runtime path.
- Reread the changed sections.
- Check `git status --short -- <target path>`.
- For docs-only work, say tests were not needed.
- Mention any deferred follow-up, such as creating a 12 years old version or audio sheet.

## Output Shape

For an implemented pipeline run, final response should be short:

- File changed.
- Review passes performed.
- Most important improvements.
- Verification.

For a review-only pipeline run, return:

- Consolidated findings.
- Targeted edit plan.
- Acceptance checks.
