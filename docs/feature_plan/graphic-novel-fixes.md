# Graphic Novel Generation Fixes

Based on review of "What Pell Heard" (6-page generation run, 2026-05-23).
Informed by multi-perspective review: graphic novel writer, art director, and 10-year-old reader.

---

## Issues & Planned Changes

### 1. Vocabulary word highlight color lost in warm caption tones (P1)

**Consensus**: All three reviewers flagged this. The kid couldn't tell which words to focus on. The art director called it the biggest readability failure. The writer noted it undermines the pedagogical goal.

**Problem**: Orange-highlighted vocab words (#FF8A2A, Hugo's Ink color) blend into the gold/yellow caption text tones, making them indistinguishable from surrounding text.

**File**: `backend/vocabulary/services/generation/step_graphic_novel.py` (highlighting builder, ~lines 140-172)

**Change**: Keep orange for vocab word highlights (matches Hugo's signature hue). Change surrounding caption/narration text color directive from "glowing gold" to white or light cream on a cooler-toned caption background. The overall page palette skews warm — vocab highlights need a cool-neutral surround to pop.

---

### 2. Page 1 lacks orientation / context-setting panel (P1)

**Consensus**: All three reviewers flagged this. The kid was lost for two pages. The writer identified missing story structure. The art director noted the absence of an establishing shot.

**Problem**: Page 1 jumps straight into action without introducing characters, setting, or situation. Young readers have no anchor.

**File**: `backend/vocabulary/prompts/graphic_novel_script.txt`

**Change**: Add instruction that page 1 must open with an establishing beat:
- Panel 1: wide/establishing shot that shows WHERE (setting) and WHO (characters), with a brief caption grounding the situation
- This panel acts as the "once upon a time" moment before the inciting action
- Keep it to one panel — don't burn the whole page on setup

---

### 3. Review page definitions cut off (P1)

**Consensus**: All three reviewers flagged this. Kid was frustrated. Art director called text overflow in a final deliverable unacceptable.

**Problem**: Definitions are truncated to the first 8 words (`step_graphic_novel.py`, ~lines 175-186), which can cut mid-sentence. Combined with limited caption box space, definitions become unreadable.

**File**: `backend/vocabulary/services/generation/step_graphic_novel.py` + `backend/vocabulary/prompts/graphic_novel_script.txt`

**Change**: Generate purpose-written short definitions (3-6 words, complete phrases) during the script step rather than mechanically truncating longer definitions. The script LLM already understands the word meanings in context — ask it to produce a compact gloss for each word specifically for the review page. Fallback: character limit (~40 chars) breaking at word boundaries.

---

### 4. Folio appears only on final page with no narrative setup (P2)

**Consensus**: All three flagged. Kid said "where did that come from?" Writer called it a narrative break. Art director noted introducing a new character on the last page is confusing.

**Problem**: Folio is hardcoded as the review page character but doesn't appear in any story pages, making its presence feel arbitrary and disconnected.

**File**: `backend/vocabulary/services/generation/step_graphic_novel.py` (~lines 872-884)

**Change**: Remove Folio from the review page entirely unless Folio appeared in the story. The review page should use the story's own characters and visual language. If Hugo is the featured character, the word cards could be presented as things Hugo painted — tying the review to the narrative rather than introducing an unfamiliar mascot.

---

### 5. Review page layout — title disjointed from word cards (P2)

**Consensus**: Writer + art director + kid ("looks like homework"). The page feels like two separate design elements sharing space rather than a unified composition.

**Problem**: The story title floats separately from the vocabulary word cards. No visual container or hierarchy connects them.

**File**: `backend/vocabulary/prompts/graphic_novel_review_page.txt`

**Change**:
- Title centered directly above word cards as a unified header, connected by a shared background band or decorative border
- Word cards should feel like they belong to the story world (e.g., "Hugo painted these words" or presented as in-world artifacts matching the story's setting)
- Add instruction: the review page should feel like the story's epilogue, not a separate worksheet

---

### 6. Hugo's brush rendered with a cap (P2)

**Consensus**: Art director (prop continuity error) + kid (logic break). A capped brush can't paint.

**Problem**: Page 5, panel 3 shows Hugo's brush with a cap on. This breaks immersion and logical consistency.

**Files**:
- `docs/feature_plan/runtime_canon/lexi_legends/cast/hugo/9_years_old_Hugo.md`
- `docs/feature_plan/runtime_canon/lexi_legends/cast/hugo/12_years_old_Hugo.md`

**Change**: Add DO NOT rule to both character sheets: "The brush NEVER has a cap, cover, or sheath. The bristle head is always exposed and ready to paint."

---

### 7. Story-to-review transition is abrupt (P3)

**Consensus**: Writer + kid. The story ends and immediately becomes a vocabulary quiz with no bridging moment.

**Problem**: Page 5 resolves the story, then page 6 is a flat vocabulary list. There's no narrative closure or transition that makes the review feel like part of the reading experience.

**Files**:
- `backend/vocabulary/prompts/graphic_novel_script.txt`
- `backend/vocabulary/prompts/graphic_novel_review_page.txt`

**Change**:
- In the script prompt: page 5 should end with a reflective/closing beat (not just plot resolution) that naturally leads toward "look at what we learned"
- In the review page prompt: include a short bridging caption at the top that connects back to the story (e.g., a character reflecting on the events), making the review feel like an epilogue rather than an appendix

---

### 8. Page 5 resolution feels rushed (P3)

**Consensus**: Writer noted the emotional payoff needs one more beat of tension before landing.

**Problem**: The conflict resolves too quickly on page 5. The pacing through pages 2-4 builds well, but the climax is compressed.

**File**: `backend/vocabulary/prompts/graphic_novel_script.txt`

**Change**: Add pacing guidance: "Page 5 should not rush the resolution. Allow at least one panel for the moment of tension/uncertainty BEFORE the resolution lands. The reader needs to feel the stakes before relief."

---

## Implementation Status

All items implemented on 2026-05-24.

**Phase 1 — Quick fixes**
1. Hugo brush cap DO NOT rule — added to both character sheets
2. Vocab highlight color contrast — caption text changed from "glowing gold" to white/cream

**Phase 2 — Script prompt improvements**
3. Page 1 establishing panel — script prompt updated
4. Page 5 pacing guidance — script prompt updated
5. Story-to-review bridging beat — script + review prompts updated

**Phase 3 — Review page overhaul**
6. Review page layout unification — review prompt rewritten (no title, epilogue feel, in-world artifacts)
7. Purpose-written short definitions — 3-8 word definitions generated in primer step (`PrimerCardContent.kid_friendly_definition`); review page reads from primer with 8-word `WordDefinition` fallback (originally in script output as `review_definitions`, moved to primer step 2026-05-29)
8. Folio conditional via `folio_present` flag — team selector decides; same mechanism as `shades_present`/`vault_framing`; Folio's character sheet loaded only when true

> **Superseded (2026-05-27):** item #8's `folio_present` mechanism no longer exists. The Lexi Mini migration removed Folio entirely from canon, the prompt pipeline, and review-page logic — `folio_present` is no longer a team-selector flag, and the review page now always uses the story's own characters and an in-world artifact (default fallback `Vault clue board`, was `Folio field guide`). The original intent of #8 (no unfamiliar mascot dropped onto the last page) is fully satisfied, just by removal rather than by a conditional flag. See [Lexi_Mini_Plan.md](./Lexi_Mini_Plan.md) and [CHANGELOG.md](../CHANGELOG.md#unreleased---2026-05-27).
