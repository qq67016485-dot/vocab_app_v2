---
name: review-canon-sheets
description: Use when reviewing or revising Lexi Legends runtime canon sheets, character visual/audio sheets, setting sheets, production bibles, or model-payload docs through the three-specialist lens of prompt engineering, literacy curriculum, and child development.
---

# Review Canon Sheets

## Overview

Use this skill to run a reusable three-specialist review and targeted edit workflow for Lexi Legends canon sheets. The goal is not to make the sheet more literary; it is to make it more reliable as runtime instructions for script, image, and audio generation while preserving educational value and age-appropriate character design.

This skill applies to Markdown strategy assets under paths such as `backend/data/canon/`, especially character visual sheets, character audio sheets, setting sheets, and companion production bibles.

## Workflow

1. Read the target sheet first.
2. Read any relevant local context the user mentions, usually:
   - `backend/data/canon/rulebook.md`
   - `docs/feature_plan/lexi-legends-visual-production-bible.md`
   - `docs/feature_plan/lexi-legends-audiobook-production-bible.md`
   - nearby 9 years old/12 years old sheets for the same character, only when comparison is useful.
3. If the user explicitly asks for a "team", "agents", "three-agent review", or similar delegated review, spawn three read-only reviewers:
   - Prompt Engineer
   - Reading/Literacy Curriculum Designer
   - Child Development Specialist
4. While reviewers run, do a local pass on the sheet for concrete edit opportunities.
5. Consolidate the feedback into a practical plan. Group items by impact instead of reviewer name when possible.
6. Apply edits only when the user asks to implement or when the current turn clearly calls for edits. Use `apply_patch` for manual file changes.
7. Verify by rereading the changed sections and checking the relevant files exist. For docs-only work, tests are usually unnecessary.

If the user did not explicitly authorize sub-agents, do not spawn them. Instead, apply the same three lenses locally and say that this is a local three-lens review.

## Reviewer Lenses

### Prompt Engineer

Evaluate the sheet as model instructions, not as a creative document. Look for:

- Ambiguous wording that a model may interpret literally or inconsistently.
- Directives likely to be lost in a long payload.
- Phrases the model may over-index on, such as fantasy labels, costume details, or abstract traits.
- Conflicts between positive instructions and "do not" rules.
- Negative constraints that should be paired with clear positive alternatives.
- Missing standalone anchors, especially Age Presentation descriptions that rely on comparison words like "older", "younger", "taller", or "more mature".
- Payload bloat that makes the most important production constraints less sticky.

### Reading/Literacy Curriculum Designer

Evaluate whether the sheet supports vocabulary acquisition without turning stories into worksheets. Look for:

- Word magic that depends on meaning, context, evidence, and semantic precision.
- Character behavior that models useful learning strategies, such as testing context clues, word parts, contrasts, connotation, tone, and revision.
- Productive uncertainty: characters may be wrong, partial, or hesitant, but the story should show how they move forward.
- Vocabulary that changes the plot through solving, revealing, repairing, transforming, clarifying, or connecting.
- Risks of modeling avoidance, random guessing, definition dumping, or spelling-only magic.

For visual sheets, keep pedagogy compact. Add only the visual behavior needed for script/image consistency, and place fuller learning models in a separate script-facing guide when needed.

### Child Development Specialist

Evaluate age fit, emotional realism, and representation. Look for:

- Whether the character reads as a real 9-year-old or 12-year-old rather than an adult miniature or fantasy archetype.
- Emotional behaviors that allow uncertainty, embarrassment, enthusiasm, hesitation, humor, recovery, and peer dynamics.
- Dialogue voice that fits the age band.
- Traits that may accidentally code stereotypes, adultification, or hierarchy.
- Physical descriptions that are specific enough for visual consistency but do not frame racialized traits as costumes, props, or brand-signature accessories.
- Whether flaws create story tension without making the child seem broken, incapable, or morally lesser.

## Consolidation Rules

- Prioritize user-stated preferences over reviewer suggestions.
- Separate findings into: must fix, useful tweak, defer to another document, and reject.
- Keep runtime sheets focused. The full sheet is the payload unit, so avoid adding prompt capsules unless the user asks for them.
- Preserve the user's chosen encoding, separators, punctuation, and formatting unless the user confirms a real display problem.
- Do not make global rewrites when targeted edits solve the issue.
- Keep skin tone, hair texture, and body details in physical design and palette sections for production consistency. Avoid putting them in shorthand "visual signature" lines unless the user specifically wants that framing.
- For visual sheets, make Age Presentation directions standalone. Do not rely on comparison to another version that may not be loaded.
- For audio sheets, focus on performance, pacing, emotional range, pronunciation, and delivery. Settings usually need ambience/SFX guidance rather than a speaking voice.

## Edit Patterns

Use small, direct additions when they solve a model-risk:

- Add a modern grounding line when a costume stack could drift into fantasy mage, superhero, or historical costume.
- Split decorative effects from readable vocabulary lettering.
- Reframe flaws so they remain flaws but point toward growth.
- Add one sentence of child realism when a character reads too composed, adult, or polished.
- Move identity details out of brand-signature shorthand and into physical design or palette sections.
- Add "not a full pedagogy section" notes when the sheet only needs compact visual/script behavior.

## Suggested Agent Prompts

Use these only when the user explicitly asks for delegated review.

Prompt Engineer:

```text
Review the target Lexi Legends runtime canon sheet as instructions to a generation model, not as a creative document. Do not edit files. Flag ambiguity, instruction conflicts, over-index risks, long-context stickiness, Age Presentation wording that is not standalone, unreliable Do Not phrasing, and payload bloat. Return prioritized findings and concrete rewrite suggestions.
```

Reading/Literacy Curriculum Designer:

```text
Review the target Lexi Legends runtime canon sheet for educational value in a vocabulary-learning graphic novel product. Do not edit files. Evaluate whether the character or setting supports vocabulary acquisition through context, word parts, semantic precision, productive uncertainty, and story consequences. Flag anything that models avoidance, random guessing, definition dumping, or spelling-only magic. Return prioritized findings and concrete rewrite suggestions.
```

Child Development Specialist:

```text
Review the target Lexi Legends runtime canon sheet for age appropriateness, emotional realism, dialogue fit, and representation concerns for 9 years old around age 9 or 12 years old around age 12. Do not edit files. Flag adultification, stereotypes, unrealistic composure, unclear flaw framing, and physical-description framing problems. Return prioritized findings and concrete rewrite suggestions.
```

## Output Shape

When proposing edits, use:

- Summary of the strongest risks.
- Consolidated plan with targeted changes.
- Deferred items for separate guides, such as script-learning behavior.
- Acceptance checks.

When implementing edits, keep the final response short:

- Files changed.
- What changed at a high level.
- Verification performed.
