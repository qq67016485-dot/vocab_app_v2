# Quality Improvement: Graphic Novel Script Generation Prompts

## Implementation Status

**Implemented (Phase 1, prompt-only).** All four prompt changes are live in the current templates:
- **Router** (`graphic_novel_router.txt`): the "prefer a different narrative approach per premise" preference is present (phrased against the free-text `narrative_approach` field, since `story_engine` was retired in the 2026-05-23 creative-flexibility revision). The page-count section was rebalanced 2026-06-04 (see below) to default toward 5 pages for ESL readers and request a genuine 5/6 mix across premises.
- **Scorer** (`graphic_novel_premise_scorer.txt`): forced comparative ranking, `thinking` field, calibration anchors (5=exceptional … 1=flawed), and per-premise `flatness_reason` are all in the schema. One deviation: the strongest/weakest spread requirement is "≥2 points on at least **2** dimensions" (plan said 3) — relaxed in line with [feedback_prompt-flexibility]; the formulaic-pattern cap is present. A "Page length is neutral, not a quality signal" block was added 2026-06-04 (see below) so 6-page premises stop out-scoring 5-page ones on plot richness alone.
- **Beat sheet** (`graphic_novel_beat_sheet.txt` + `..._6page.txt`): "Emotional pacing" section with the in-page register-shift guidance, alternative arc shapes, the per-page `pacing_note` enum (`breath|build|turn|release|launch`), and the pacing→panel-count mapping.
- **Final script** (`graphic_novel_script.txt` + `..._6page.txt`): "Dialogue craft" and "Visual storytelling" sections, the layout/shot-scale variety requirements, and matching self-check items.

No code changes were required, as planned — scorer still emits the five active dimension keys (note: the dimension set was overhauled on 2026-05-27 to `{narrative_clarity, visual_potential, vocabulary_integration, pedagogical_clarity, character_fit}`; the "7 dimension keys" in the verification note below predates that change). The "Out of Scope" items remain unimplemented (see [graphic-novel-pipeline-followups.md](./graphic-novel-pipeline-followups.md) for which are now candidate work).

---

## Context

The 5-step graphic novel script pipeline (team selector → router → scorer → beat sheet → final script) produces good output but tends toward formulaic patterns: mystery + ticking clock structures, uniformly high scorer ratings, similar emotional registers across runs, and dialogue that's functional but lacks craft. The goal is a general quality uplift across narrative variety, emotional depth, visual storytelling, and dialogue craft — while preserving the strong vocabulary integration and character consistency that already works well.

## Changes

### Phase 1: Prompt Improvements (no code changes needed)

#### 1. Router (`backend/vocabulary/prompts/graphic_novel_router.txt`)

- it is prefered that each of the 3 premises uses a different `story_engine` add this preference into the prompt


#### 2. Scorer (`backend/vocabulary/prompts/graphic_novel_premise_scorer.txt`)

Add forced comparative ranking before scoring:
- "Before scoring, rank the 3 premises from strongest to weakest on each dimension. Then assign scores consistent with your ranking. The strongest and weakest must differ by at least 2 points on at least 3 dimensions."

Add a `thinking` field to the output schema (brief comparative reasoning before scores — can be discarded downstream but forces the model to reason before committing to numbers).

Add scoring calibration with concrete anchors:
- 5 = exceptional (rare), 4 = strong, 3 = competent but predictable, 2 = structural weakness, 1 = flawed
- Formulaic pattern penalties: all conflicts resolved by understanding word meaning caps engagement at 3

Add `flatness_reason` field per premise (one sentence explaining what could make the story flat).

#### 3. Beat Sheet (`backend/vocabulary/prompts/graphic_novel_beat_sheet.txt`)

Add "Emotional pacing guidance:" section — reframed as breathing *panels within pages* (not full breathing pages, since 5 pages can't spare one):
- At least 2 of the 5 pages should contain a register shift within the page (e.g., one quiet/humorous panel within an otherwise building page)
- Offer alternative arc shapes beyond setup → rising → rising → climax → resolution


Add `pacing_note` field per page: `"breath" | "build" | "turn" | "release" | "launch"`.

Connect pacing_note to panel count guidance:
- "breath" → 1-2 panels (give art room to breathe)
- "build" → 3-4 panels (progressive momentum)
- "turn" → 2-3 panels (dramatic shift needs space)
- "release" → 2-3 panels (resolution landing)
- "launch" → 2-3 panels (dynamic energy)

#### 4. Final Script (`backend/vocabulary/prompts/graphic_novel_script.txt`)

Add "Dialogue craft:" section:
- Vary rhythm: mix short punchy lines (2-5 words) with longer ones (8-12 words)
- Allow interruptions (—), trailing off (...), single-word reactions
- Avoid "As you know, Bob" exposition
- Let silence work: panels with no dialogue where expression carries the beat

Expand "Visual variety:" into "Visual storytelling:" with:
- At least 2 different layout structures across 5 pages, with panel count varying between 1-4. Recommended layouts (all use rectangular, axis-aligned divisions):
  - Equal grid (2x2)
  - Dominant panel (60-70% of page) + 1-2 smaller panels
  - Horizontal banner + panels below or above
  - Splash page with inset panel(s)
  - Vertical split (tall panel + stacked panels)
- Each page must include at least 2 different shot scales. One panel per page should serve as the visual anchor


### Out of Scope (future work)

- Adding `emotional_depth` as a new scoring dimension (would require constants.py change)
- Context trimming / new canon file for visual reference
- Character emotion readability mandate (every panel specifies facial expression + body language)
- Negative space mandate for speech bubble placement
- Visual vocabulary demonstration (target word shown visually, not just spoken)

### Phase 2 follow-up (shipped 2026-06-04): page-count length-bias rebalance

> **Superseded 2026-06-05.** Page count is no longer an LLM judgment, so the length-bias problem this section addressed no longer exists. Page count is now derived deterministically from the pack's word count (`page_count_for_word_count`: ≤4 words → 5 pages, >4 → 6); the router/scorer are told the `required_page_count` and the pipeline forces it. The "5 as default / page length is neutral / prefer the shorter premise" prompt language described below was removed. See [design-graphic-novel.md](./design-graphic-novel.md) and CHANGELOG 2026-06-05. Preserved here as the historical rationale.

A separate quality issue surfaced after Phase 1: real-content runs always produced 6-page novels, never 5. The page-count plumbing was confirmed correct against on-disk artifacts (the winning premise's `page_count` reaches the beat sheet and script intact); the bias lived in the scorer rubric, which rewarded the richer plot a 6th page allows. Two prompt-only edits, both soft-guidance phrased per [feedback_prompt-flexibility]:

- **Router**: page-count section now frames 5 pages as the strong ESL default (less text per page → easier word inference; 6 reserved for premises that need the room) and asks for a genuine mix across the 3 premises, with at least one conceived as a clean 5-page story rather than a trimmed 6-page idea.
- **Scorer**: added a "Page length is neutral, not a quality signal" block — don't reward a premise for the richer plot extra pages allow; judge each premise at its own chosen length (a tight 5-page story isn't "thin"); ambition only counts if it still teaches every word clearly; prefer the shorter premise on a near tie.

No code/schema change; the 28 script-step tests (template-selection only) still pass. Effectiveness is observational — check that the 5/6 mix returns over the next several generations.

## Files to Modify

- `backend/vocabulary/prompts/graphic_novel_router.txt`
- `backend/vocabulary/prompts/graphic_novel_premise_scorer.txt`
- `backend/vocabulary/prompts/graphic_novel_beat_sheet.txt`
- `backend/vocabulary/prompts/graphic_novel_script.txt`

No code changes needed — all improvements are prompt-only. 

## Verification

1. Run the existing test suite: `cd backend && pytest tests/vocabulary/test_generation_pipeline_service.py -v`
2. Verify no validation errors — scorer still outputs the same 7 dimension keys
3. Run a full generation job through the admin UI with a test word set
