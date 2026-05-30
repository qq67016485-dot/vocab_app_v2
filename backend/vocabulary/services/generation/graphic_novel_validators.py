"""Validators for graphic novel pipeline LLM responses.

Each substep's response goes through a validator that raises ValueError if
the structure or business rules are violated. Validators are pure functions
and depend only on small helpers from `graphic_novel_helpers`.
"""
import logging
from dataclasses import dataclass, field
from typing import Any

from vocabulary.services.generation.constants import (
    GRAPHIC_NOVEL_ALLOWED_INTEGRATION_MODES,
    GRAPHIC_NOVEL_ALLOWED_PAGE_COUNTS,
    GRAPHIC_NOVEL_PEDAGOGICAL_ANCHOR_TYPES,
    GRAPHIC_NOVEL_SCORING_DIMENSIONS,
    max_locations_for_page_count,
)
from vocabulary.services.generation.graphic_novel_helpers import (
    _count_direct_ink_uses,
    _expected_page_count_from_summary,
    _page_vocab_words,
    _target_terms_from_input,
    _text_terms_from_graphic_novel_page,
)

logger = logging.getLogger(__name__)


@dataclass
class SubstepContext:
    """Accumulated state passed to all validators uniformly."""
    target_terms: set = field(default_factory=set)
    winning_premise: dict = field(default_factory=dict)
    selected_away_team: list = field(default_factory=list)
    router_result: dict = field(default_factory=dict)

    @classmethod
    def from_input_summary(cls, input_summary: dict, **kwargs) -> 'SubstepContext':
        defaults = {
            'target_terms': _target_terms_from_input(input_summary),
            'winning_premise': (input_summary or {}).get('winning_premise', {}),
            'selected_away_team': (input_summary or {}).get('selected_away_team', []),
        }
        defaults.update(kwargs)
        return cls(**defaults)

    @property
    def expected_page_count(self) -> int:
        page_count = self.winning_premise.get('page_count')
        if page_count in GRAPHIC_NOVEL_ALLOWED_PAGE_COUNTS:
            return page_count
        from vocabulary.services.generation.constants import GRAPHIC_NOVEL_DEFAULT_PAGE_COUNT
        return GRAPHIC_NOVEL_DEFAULT_PAGE_COUNT


def _validate_words_data_covers_pack(pack, pack_words_data):
    target_terms = {
        text.lower()
        for text in pack.items.values_list('word__text', flat=True)
    }
    data_terms = {
        (wd.get('term') or '').lower()
        for wd in pack_words_data
    }
    missing_terms = target_terms - data_terms
    if missing_terms:
        raise ValueError(
            f"Graphic novel input is missing word data for pack '{pack.label}': {sorted(missing_terms)}"
        )


def _validate_graphic_novel_team_result(result, ctx=None):
    selected_away_team = result.get('selected_away_team')
    if not isinstance(selected_away_team, list) or not selected_away_team:
        raise ValueError("Graphic novel team selector must return selected_away_team as a non-empty list.")
    if not isinstance(result.get('vault_framing'), bool):
        raise ValueError("Graphic novel team selector must return boolean vault_framing.")


def _validate_vocab_integration_plan(premise):
    from vocabulary.services.generation.constants import (
        GRAPHIC_NOVEL_MAX_MINI_SUMMONS_PER_STORY,
        GRAPHIC_NOVEL_MAX_SECONDARY_CHARACTERS,
    )
    premise_id = premise.get('id', 'unknown')

    complexity_budget = premise.get('complexity_budget')
    if not isinstance(complexity_budget, dict):
        raise ValueError(
            f"Graphic novel router premise {premise_id} must include a complexity_budget object."
        )
    locations = complexity_budget.get('locations')
    if not isinstance(locations, list):
        raise ValueError(
            f"Graphic novel router premise {premise_id} complexity_budget.locations must be a list."
        )
    secondary_characters = complexity_budget.get('secondary_characters')
    if not isinstance(secondary_characters, list):
        raise ValueError(
            f"Graphic novel router premise {premise_id} complexity_budget.secondary_characters must be a list."
        )
    if len(secondary_characters) > GRAPHIC_NOVEL_MAX_SECONDARY_CHARACTERS:
        raise ValueError(
            f"Graphic novel router premise {premise_id} complexity_budget.secondary_characters has "
            f"{len(secondary_characters)} entries; max is {GRAPHIC_NOVEL_MAX_SECONDARY_CHARACTERS}."
        )
    problem_thread = complexity_budget.get('problem_thread')
    if not isinstance(problem_thread, str) or not problem_thread.strip():
        raise ValueError(
            f"Graphic novel router premise {premise_id} complexity_budget.problem_thread must be a non-empty string."
        )

    plan = premise.get('vocab_integration_plan')
    if not isinstance(plan, list) or not plan:
        raise ValueError(
            f"Graphic novel router premise {premise_id} must include a non-empty vocab_integration_plan list."
        )
    for item in plan:
        for field in ('term', 'story_role', 'integration_mode', 'uses_direct_ink'):
            if field not in item:
                raise ValueError(
                    f"Graphic novel router premise {premise_id} vocab_integration_plan item is missing {field}."
                )
        if item.get('integration_mode') not in GRAPHIC_NOVEL_ALLOWED_INTEGRATION_MODES:
            raise ValueError(
                f"Graphic novel router premise {premise_id} has unsupported integration_mode "
                f"'{item.get('integration_mode')}'."
            )
        if not isinstance(item.get('uses_direct_ink'), bool):
            raise ValueError(
                f"Graphic novel router premise {premise_id} uses_direct_ink must be boolean."
            )
        anchor = item.get('pedagogical_anchor')
        term = item.get('term', '<unknown>')
        if not isinstance(anchor, dict):
            raise ValueError(
                f"Graphic novel router premise {premise_id} term '{term}' must include a "
                f"pedagogical_anchor object with anchor_type and anchor_sketch."
            )
        anchor_type = anchor.get('anchor_type')
        if anchor_type not in GRAPHIC_NOVEL_PEDAGOGICAL_ANCHOR_TYPES:
            raise ValueError(
                f"Graphic novel router premise {premise_id} term '{term}' has unsupported "
                f"pedagogical_anchor.anchor_type '{anchor_type}'. Allowed: "
                f"{sorted(GRAPHIC_NOVEL_PEDAGOGICAL_ANCHOR_TYPES)}."
            )
        anchor_sketch = anchor.get('anchor_sketch')
        if not isinstance(anchor_sketch, str) or not anchor_sketch.strip():
            raise ValueError(
                f"Graphic novel router premise {premise_id} term '{term}' must include a "
                f"non-empty pedagogical_anchor.anchor_sketch string describing the teaching cue."
            )

    direct_ink_uses = _count_direct_ink_uses(plan)
    if direct_ink_uses > GRAPHIC_NOVEL_MAX_MINI_SUMMONS_PER_STORY:
        raise ValueError(
            f"Graphic novel router premise {premise_id} uses direct Ink {direct_ink_uses} times; "
            f"max is {GRAPHIC_NOVEL_MAX_MINI_SUMMONS_PER_STORY}."
        )

    total_ink_activations_planned = premise.get('total_ink_activations_planned')
    if not isinstance(total_ink_activations_planned, int) or total_ink_activations_planned < 0:
        raise ValueError(
            f"Graphic novel router premise {premise_id} must include total_ink_activations_planned as a non-negative integer."
        )
    if total_ink_activations_planned != direct_ink_uses:
        raise ValueError(
            f"Graphic novel router premise {premise_id} total_ink_activations_planned is {total_ink_activations_planned} "
            f"but vocab_integration_plan has {direct_ink_uses} uses_direct_ink=true entries."
        )

    mini_justification = premise.get('mini_justification')
    if total_ink_activations_planned > 0:
        if not isinstance(mini_justification, str) or not mini_justification.strip():
            raise ValueError(
                f"Graphic novel router premise {premise_id} has total_ink_activations_planned={total_ink_activations_planned} "
                f"but mini_justification is missing or empty. A Mini requires justification."
            )
    else:
        if mini_justification is not None:
            raise ValueError(
                f"Graphic novel router premise {premise_id} has total_ink_activations_planned=0 "
                f"but mini_justification is not null. Set it to null when no Mini is planned."
            )


def _validate_graphic_novel_router_result(result, ctx=None):
    premises = result.get('premises', [])
    if len(premises) != 3:
        raise ValueError(f"Graphic novel router must return exactly 3 premises; got {len(premises)}.")
    seen_ids = set()
    for idx, premise in enumerate(premises, 1):
        premise_id = premise.get('id')
        if not premise_id:
            raise ValueError(f"Graphic novel router premise {idx} is missing an id.")
        if premise_id in seen_ids:
            raise ValueError(f"Graphic novel router premise id '{premise_id}' is duplicated.")
        seen_ids.add(premise_id)
        for field in ('premise', 'protagonist_goal'):
            if not premise.get(field):
                raise ValueError(f"Graphic novel router premise {premise_id} is missing {field}.")
        if not (premise.get('central_thread') or premise.get('central_problem')):
            raise ValueError(f"Graphic novel router premise {premise_id} is missing central_thread.")
        page_count = premise.get('page_count')
        if page_count not in GRAPHIC_NOVEL_ALLOWED_PAGE_COUNTS:
            raise ValueError(
                f"Graphic novel router premise {premise_id} must include page_count in "
                f"{list(GRAPHIC_NOVEL_ALLOWED_PAGE_COUNTS)}; got {page_count!r}."
            )
        rationale = premise.get('page_count_rationale')
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError(
                f"Graphic novel router premise {premise_id} must include a non-empty page_count_rationale string."
            )
        _validate_vocab_integration_plan(premise)


def _validate_graphic_novel_scoring_result(result, ctx=None):
    router_result = (ctx.router_result if ctx else {}) or {}
    premises = router_result.get('premises', [])
    premise_ids = {premise.get('id') for premise in premises if premise.get('id')}
    scores = result.get('scores', [])
    for score in scores:
        missing_dimensions = GRAPHIC_NOVEL_SCORING_DIMENSIONS - set(score.keys())
        if missing_dimensions:
            raise ValueError(
                f"Graphic novel scorer score for {score.get('premise_id')} is missing dimensions "
                f"{sorted(missing_dimensions)}."
            )
    scored_ids = {score.get('premise_id') for score in scores if score.get('premise_id')}
    missing_scores = premise_ids - scored_ids
    if missing_scores:
        raise ValueError(
            f"Graphic novel scorer must score every router premise; missing {sorted(missing_scores)}."
        )
    winning_premise_id = result.get('winning_premise_id') or result.get('winning_premise', {}).get('id')
    if winning_premise_id not in premise_ids:
        raise ValueError("Graphic novel scorer must choose one winning premise from router premises.")


def _validate_beat_complexity(beat_sheet, ctx):
    """Check that the beat sheet honors the complexity_budget from the winning premise."""
    from vocabulary.services.generation.constants import GRAPHIC_NOVEL_DEFAULT_PAGE_COUNT
    page_count = ctx.expected_page_count if ctx else GRAPHIC_NOVEL_DEFAULT_PAGE_COUNT
    max_setting_keys = max_locations_for_page_count(page_count)
    setting_keys = {page.get('setting_key') for page in beat_sheet if page.get('setting_key')}
    if len(setting_keys) > max_setting_keys:
        raise ValueError(
            f"Graphic novel beat planner uses {len(setting_keys)} distinct setting_keys across "
            f"{page_count} pages; max is {max_setting_keys}. Found: {sorted(setting_keys)}."
        )

    winning_premise = (ctx.winning_premise if ctx else {}) or {}
    complexity_budget = winning_premise.get('complexity_budget') or {}
    secondary_characters = complexity_budget.get('secondary_characters') or []
    away_team = (ctx.selected_away_team if ctx else []) or []
    allowed_characters = {name for name in away_team} | {name for name in secondary_characters}
    if not allowed_characters:
        return
    introduced_characters = set()
    for page in beat_sheet:
        for name in page.get('characters_featured') or []:
            introduced_characters.add(name)
    extra = introduced_characters - allowed_characters
    if extra:
        raise ValueError(
            f"Graphic novel beat planner introduces characters not in the away team or "
            f"complexity_budget.secondary_characters: {sorted(extra)}. "
            f"Allowed: {sorted(allowed_characters)}."
        )


def _validate_graphic_novel_beat_result(result, ctx=None):
    from vocabulary.services.generation.constants import GRAPHIC_NOVEL_MAX_MINI_SUMMONS_PER_STORY
    page_count = ctx.expected_page_count if ctx else GRAPHIC_NOVEL_DEFAULT_PAGE_COUNT
    beat_sheet = result.get('beat_sheet', [])
    if len(beat_sheet) != page_count:
        raise ValueError(
            f"Graphic novel beat planner must return exactly {page_count} pages; got {len(beat_sheet)}."
        )
    page_numbers = [page.get('page') for page in beat_sheet]
    expected_numbers = list(range(1, page_count + 1))
    if page_numbers != expected_numbers:
        raise ValueError(
            f"Graphic novel beat planner pages must be numbered 1 through {page_count}."
        )
    for page in beat_sheet:
        page_number = page.get('page')
        if not isinstance(page.get('characters_featured'), list):
            raise ValueError(
                f"Graphic novel beat planner page {page_number} must include characters_featured list."
            )
        for field in ('setting_key', 'vault_zone'):
            if field not in page:
                raise ValueError(f"Graphic novel beat planner page {page_number} must include {field}.")
        if not isinstance(page.get('is_vault_page'), bool):
            raise ValueError(
                f"Graphic novel beat planner page {page_number} must include boolean is_vault_page."
            )

    _validate_beat_complexity(beat_sheet, ctx)

    review_artifact_type = str(result.get('review_artifact_type') or '').strip()
    if not review_artifact_type:
        logger.warning(
            "Graphic novel beat planner returned blank review_artifact_type; "
            "defaulting to Vault clue board."
        )
        result['review_artifact_type'] = 'Vault clue board'
    else:
        result['review_artifact_type'] = review_artifact_type
    ink_usage = result.get('ink_usage')
    if not isinstance(ink_usage, list):
        raise ValueError("Graphic novel beat planner must include ink_usage list.")
    for item in ink_usage:
        for field in ('term', 'page', 'uses_direct_ink', 'purpose'):
            if field not in item:
                raise ValueError(f"Graphic novel beat planner ink_usage item is missing {field}.")
        if not isinstance(item.get('uses_direct_ink'), bool):
            raise ValueError("Graphic novel beat planner ink_usage uses_direct_ink must be boolean.")
    direct_ink_uses = _count_direct_ink_uses(ink_usage)
    if direct_ink_uses > GRAPHIC_NOVEL_MAX_MINI_SUMMONS_PER_STORY:
        raise ValueError(
            f"Graphic novel beat planner uses direct Ink {direct_ink_uses} times; "
            f"max is {GRAPHIC_NOVEL_MAX_MINI_SUMMONS_PER_STORY}."
        )

    total_ink_activations_planned = result.get('total_ink_activations_planned')
    if not isinstance(total_ink_activations_planned, int) or total_ink_activations_planned < 0:
        raise ValueError(
            "Graphic novel beat planner must include total_ink_activations_planned as a non-negative integer."
        )
    if total_ink_activations_planned > GRAPHIC_NOVEL_MAX_MINI_SUMMONS_PER_STORY:
        raise ValueError(
            f"Graphic novel beat planner total_ink_activations_planned is {total_ink_activations_planned}; "
            f"max is {GRAPHIC_NOVEL_MAX_MINI_SUMMONS_PER_STORY}."
        )
    if total_ink_activations_planned != direct_ink_uses:
        raise ValueError(
            f"Graphic novel beat planner total_ink_activations_planned is {total_ink_activations_planned} "
            f"but ink_usage has {direct_ink_uses} uses_direct_ink=true entries."
        )

    target_terms = ctx.target_terms if ctx else set()
    role_terms = {
        term.lower()
        for term in result.get('vocab_roles', {}).keys()
        if term
    }
    missing_roles = target_terms - role_terms
    if missing_roles:
        raise ValueError(
            f"Graphic novel beat planner must assign vocab_roles for every target word; missing {sorted(missing_roles)}."
        )


def _validate_vocab_anchors(result, target_terms):
    anchors = result.get('vocab_anchors')
    if not isinstance(anchors, dict) or not anchors:
        raise ValueError(
            "Graphic novel final script must include a vocab_anchors object with one entry per target word."
        )
    anchored_terms = {term.lower() for term in anchors.keys() if term}
    missing = target_terms - anchored_terms
    if missing:
        raise ValueError(
            f"Graphic novel final script vocab_anchors is missing entries for: {sorted(missing)}."
        )
    for term, anchor in anchors.items():
        if not isinstance(anchor, dict):
            raise ValueError(
                f"vocab_anchors entry for '{term}' must be an object with anchor_type and anchor_text."
            )
        anchor_type = anchor.get('anchor_type')
        if anchor_type not in GRAPHIC_NOVEL_PEDAGOGICAL_ANCHOR_TYPES:
            raise ValueError(
                f"vocab_anchors entry for '{term}' has unsupported anchor_type '{anchor_type}'. "
                f"Allowed: {sorted(GRAPHIC_NOVEL_PEDAGOGICAL_ANCHOR_TYPES)}."
            )
        anchor_text = anchor.get('anchor_text')
        if not isinstance(anchor_text, str) or not anchor_text.strip():
            raise ValueError(
                f"vocab_anchors entry for '{term}' must include a non-empty anchor_text describing "
                f"the teaching cue present in the panel."
            )


def _validate_graphic_novel_script_result(result, ctx=None):
    from vocabulary.services.generation.constants import GRAPHIC_NOVEL_DEFAULT_PAGE_COUNT
    expected_page_count = ctx.expected_page_count if ctx else GRAPHIC_NOVEL_DEFAULT_PAGE_COUNT
    pages = result.get('pages', [])
    if len(pages) != expected_page_count:
        raise ValueError(
            f"Graphic novel final script must contain exactly {expected_page_count} story pages; "
            f"got {len(pages)}."
        )
    for idx, page_data in enumerate(pages, 1):
        panels = page_data.get('panels', [])
        if not panels:
            raise ValueError(f"Graphic novel page {idx} must include at least one panel.")
        if not isinstance(page_data.get('characters_featured'), list):
            raise ValueError(f"Graphic novel page {idx} must include characters_featured list.")
        for field in ('setting_key', 'vault_zone'):
            if field not in page_data:
                raise ValueError(f"Graphic novel page {idx} must include {field}.")
        if not isinstance(page_data.get('is_vault_page'), bool):
            raise ValueError(f"Graphic novel page {idx} must include boolean is_vault_page.")
    if ctx and ctx.target_terms:
        target_terms = ctx.target_terms
        used_terms = set()
        for page_data in pages:
            used_terms.update(word.lower() for word in _page_vocab_words(page_data))
            page_text = _text_terms_from_graphic_novel_page(page_data)
            used_terms.update(term for term in target_terms if term in page_text)
        missing_terms = target_terms - used_terms
        if missing_terms:
            raise ValueError(
                f"Graphic novel final script must use every target word; missing {sorted(missing_terms)}."
            )
        _validate_vocab_anchors(result, target_terms)


def _validate_graphic_novel_cloze_result(result, ctx=None):
    """Validate the dedicated cloze generation substep output."""
    cloze_items = result.get('cloze_items')
    if not isinstance(cloze_items, list) or not cloze_items:
        raise ValueError("Cloze generation must return a non-empty cloze_items list.")
    for idx, item in enumerate(cloze_items):
        if not item.get('term'):
            raise ValueError(f"Cloze item {idx} missing 'term'.")
        if not item.get('sentence_text') or '_' not in item.get('sentence_text', ''):
            raise ValueError(f"Cloze item {idx} must have sentence_text with a blank.")
        if not item.get('correct_answer'):
            raise ValueError(f"Cloze item {idx} missing 'correct_answer'.")
        distractors = item.get('distractors', [])
        if not isinstance(distractors, list) or len(distractors) < 2:
            raise ValueError(f"Cloze item {idx} must have at least 2 distractors.")
    if ctx and ctx.target_terms:
        target_terms = ctx.target_terms
        cloze_terms = {
            (item.get('term') or item.get('correct_answer') or '').lower()
            for item in cloze_items
        }
        missing = target_terms - cloze_terms
        if missing:
            raise ValueError(
                f"Cloze generation must include an item for every target word; "
                f"missing {sorted(missing)}."
            )
