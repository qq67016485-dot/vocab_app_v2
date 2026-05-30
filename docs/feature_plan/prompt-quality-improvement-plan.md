# Quality Improvement: Graphic Novel Script Generation Prompts

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
