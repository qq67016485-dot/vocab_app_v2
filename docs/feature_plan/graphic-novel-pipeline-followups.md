# Graphic Novel Pipeline — Follow-up Work

Created 2026-06-04, from an audit comparing the implemented pipeline (`backend/vocabulary/services/generation/`) against the six graphic-novel feature plans in this folder. The plans themselves are now fully implemented or superseded; this doc collects the **remaining** work that surfaced during the audit — small correctness/cleanup items first, then the larger deferred quality and architecture items.

Each item lists scope, the relevant file(s), and a rough size. Nothing here is a known production-breaking bug; these are robustness, hygiene, and quality improvements.

---

## A. Code correctness & cleanup (small, low-risk)

### A1. End-of-run incomplete-page check is not channel-filtered
**File:** `backend/vocabulary/services/generation/graphic_novel_images.py` (~line 351)
**Size:** XS

The main image loop queries pages with `novel__pack__in=packs, novel__channel='5page'` (line 121), but the final `incomplete_pages` recomputation (line 351) filters only by `novel__pack__in=packs` — it drops the `channel='5page'` filter. On any pack that still has a legacy non-`5page` novel row, a stale/incomplete legacy page could make the step report failure even though every current-channel page succeeded. Add `novel__channel='5page'` to the closing query so it matches the loop.

### A2. `generation_attempts` double-increment on image retry
**File:** `backend/vocabulary/services/generation/graphic_novel_images.py` (~lines 173, 272)
**Size:** XS

`generation_attempts` is incremented once when a page attempt starts (line 173) and again inside the `except` retry branch (line 272). A single failed-then-retried page therefore inflates its attempt count. Decide on one increment point (preferably once per actual API call) so the persisted count and the "attempt N" log messages are accurate. Verify against `test_step_graphic_novel_images` expectations.

### A3. Dead import / unused helper `_expected_page_count_from_summary`
**Files:** `graphic_novel_validators.py` (line 20 import), `graphic_novel_helpers.py` (definition), `step_graphic_novel.py` (re-export)
**Size:** XS

Validators read expected length from `SubstepContext.expected_page_count`; `_expected_page_count_from_summary` is imported but never called, and has no live caller anywhere. Either remove it (and its import + facade re-export) or, if kept as a public helper, document why. Pure cleanup — confirm no test imports it before deleting.

### A4. Restart path duplicates the main script step's context assembly
**File:** `backend/vocabulary/services/generation/graphic_novel_script.py` (`restart_graphic_novel_from_substep` vs `_step_graphic_novel_script`)
**Size:** M

`restart_graphic_novel_from_substep` re-implements almost all of the main step's context building (team/router context, `page_count` clamp, persistence, review-page creation, cloze save). They are functionally equivalent today but drift-prone — e.g. the restart path builds an extra `final_validator_summary` while the main path passes `input_summary`. Extract the shared per-pack assembly + persistence into helper functions both paths call, so a future change to one can't silently desync the other. This is the recurring sync-point risk already tracked in memory ([[project_pipeline-step-order-sync-points]]).

**Update (2026-06-05):** the coupling deepened — `_step_graphic_novel_script` now *calls* `restart_graphic_novel_from_substep` for per-pack resume (resume from the first incomplete substep), and `restart_graphic_novel_substep` (orchestrator) now calls `_step_graphic_novel_script` to fill orphaned packs after a single-pack restart. The two paths invoke each other, so the extraction is now higher value: a desync between their per-pack assembly would surface in both resume and restart flows.

### A5. Stray prompt-file copy in version control candidate
**File:** `backend/vocabulary/prompts/word_lookup - 副本.txt` (untracked)
**Size:** XS

An accidental "副本" (copy) of `word_lookup.txt` is sitting in the prompts dir (shows in `git status` as untracked). Not graphic-novel-specific, but it's in the prompt-loading directory. Delete it (confirm it isn't referenced) so it can't be loaded by mistake or committed.

---

## B. Deferred prompt-quality items (from prompt-quality-improvement-plan.md "Out of Scope")

These were explicitly parked when the Phase-1 prompt improvements shipped. They remain unimplemented and are the natural next quality pass. All are prompt + (where noted) small schema/constants changes.

### B1. `emotional_depth` (or similar) as a scoring dimension
**Files:** `constants.py` (`GRAPHIC_NOVEL_SCORING_DIMENSIONS`), `graphic_novel_premise_scorer.txt`, `graphic_novel_validators.py`
**Size:** S

Adding a dimension requires touching the constant, the scorer prompt schema, and `_validate_graphic_novel_scoring_result`. Worth doing alongside any other scorer change to amortize the test churn. Keep the set small — the 2026-05-27 overhaul deliberately trimmed to five ESL-focused dimensions.

### B2. Character-emotion readability mandate
**Files:** `graphic_novel_script.txt` + `..._6page.txt`
**Size:** S (prompt-only)

Require every panel to specify facial expression + body language for on-panel characters, so the image model gets explicit emotion cues instead of inferring them. Pairs well with B4.

### B3. Visual vocabulary demonstration
**Files:** `graphic_novel_script.txt` + `..._6page.txt`, possibly `graphic_novel_page.txt`
**Size:** S–M (prompt-only)

Encourage the target word to be *shown* (a visible referent or demonstrated action in the panel art) rather than only appearing in caption/dialogue text. Overlaps with the existing `pedagogical_anchor` contract (`demonstrated_action` / `visible_referent` anchor types) — this would push those anchors through to the panel/image layer rather than stopping at the page payload.

### B4. Negative-space mandate for speech-bubble placement
**Files:** `graphic_novel_page.txt`, `graphic_novel_script.txt`
**Size:** S (prompt-only)

GPT-Image-2 frequently crowds bubbles over faces/action. Add layout guidance reserving negative space for text so bubbles don't occlude the focal subject.

### B5. Context trimming / dedicated visual-reference canon file
**Files:** `canon_service.py`, final-script + image prompts
**Size:** M

Final script + image prompts currently embed full collapsed visual sheets. A purpose-built compact visual-reference file (like the existing `team-selector-summaries.md` / `script-character-sheets.md` split) would cut tokens on the image path. Measure token impact before committing.

---

## C. Larger / strategic (not yet planned)

### C1. Drop the vestigial `GraphicNovel.channel` column
**Files:** `models.py`, a new migration, every `channel='5page'` reference in `graphic_novel_script.py` / `graphic_novel_images.py` / `orchestrator.py`
**Size:** M

Since the dual-channel architecture was removed (2026-05-29), `channel` is always `'5page'` and `unique_together = ('pack', 'channel')` is effectively `('pack',)`. A cleanup migration could drop `channel` and switch `GraphicNovel.pack` back to a `OneToOneField`, removing the hardcoded `'5page'` filters scattered through the GN modules (which also removes the root cause of A1). Deferred because it touches the model + a data migration and needs a careful check of legacy rows; do it as a dedicated change, not bundled with feature work.

### C2. Lexi Mini "Phase 2" game-progression hooks
**Source:** [Lexi_Mini_Plan.md](./Lexi_Mini_Plan.md) §6
**Size:** out of current scope

The Mini plan frames Phase 1 (comics) as priming Phase 2 (collect/nurture/battle "Lexi Monsters"). No pipeline work is needed now; noted here so the design intent isn't lost. Folio's UI-mascot role was also explicitly *deferred* (not cancelled) when Folio was removed from generation — revisit if/when a UI mascot is reintroduced.

---

## Verification checklist (for whoever picks these up)

- `cd backend && python manage.py check` — clean
- `cd backend && pytest tests/vocabulary/test_step_graphic_novel_script.py tests/vocabulary/test_generation_pipeline_service.py -v` — script/substep + pipeline tests
- For A1/A2 specifically: re-run the image-step tests and confirm attempt counts / failure reporting match expectations
- `cd backend && python manage.py makemigrations --check --dry-run` — for C1 (and any constants change that alters seeded `LLMStepConfig` rows)
- Remember the **step-order sync points** ([[project_pipeline-step-order-sync-points]]): `GRAPHIC_NOVEL_SUBSTEPS` is duplicated in `constants.py`, `generation_views.py` (`GRAPHIC_NOVEL_SCRIPT_SUBSTEPS` / `VALID_SUBSTEP_KEYS`), the frontend `GRAPHIC_NOVEL_SUBSTEPS` constant, the `LLMStepConfig.StepKey` enum, and `PROJECT_CONTEXT.md`. Any substep change must update all of them in lockstep.

