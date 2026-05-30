"""Constants shared across generation pipeline modules."""
from vocabulary.models import GenerationJobLog

DEFAULT_MODEL = 'gemini-3.1-pro-preview'
BACKUP_MODEL = 'gemini-3-pro-preview'
GRAPHIC_NOVEL_SCRIPT_MODEL = 'gemini-3.1-pro-preview'
GRAPHIC_NOVEL_IMAGE_MODEL = 'gpt-image-2'

PIPELINE_STEP_ORDER = [
    GenerationJobLog.Step.WORD_LOOKUP,
    GenerationJobLog.Step.DEDUP,
    GenerationJobLog.Step.TRANSLATION,
    GenerationJobLog.Step.QUESTION_GEN,
    GenerationJobLog.Step.PRIMER_GEN,
    GenerationJobLog.Step.PACK_CREATION,
    GenerationJobLog.Step.GRAPHIC_NOVEL_SCRIPT,
    GenerationJobLog.Step.GRAPHIC_NOVEL_IMAGES,
]

GRAPHIC_NOVEL_SUBSTEPS = [
    {
        'key': 'team_selection',
        'label': 'Team Selection',
        'template': 'graphic_novel_team_selector',
        'filename': '01_team_selection.json',
    },
    {
        'key': 'router_premises',
        'label': 'Router + Premises',
        'template': 'graphic_novel_router',
        'filename': '02_router_premises.json',
    },
    {
        'key': 'premise_scoring',
        'label': 'Premise Scoring',
        'template': 'graphic_novel_premise_scorer',
        'filename': '03_premise_scoring.json',
    },
    {
        'key': 'cloze_generation',
        'label': 'Cloze Generation',
        'template': 'graphic_novel_cloze',
        'filename': '03b_cloze_generation.json',
    },
    {
        'key': 'beat_sheet_vocab_roles',
        'label': 'Beat Sheet + Vocab Roles',
        'template': 'graphic_novel_beat_sheet',
        'filename': '04_beat_sheet_vocab_roles.json',
    },
    {
        'key': 'final_script_self_check',
        'label': 'Final Script + Self-Check',
        'template': 'graphic_novel_script',
        'filename': '05_final_script_self_check.json',
    },
]

# Length-specific prompt templates that the beat-sheet and final-script substeps
# dispatch to based on winning_premise.page_count. The base substep config above
# names the 5-page (default) template; the runtime swaps in the 6-page template
# when needed.
GRAPHIC_NOVEL_BEAT_SHEET_TEMPLATES = {
    5: 'graphic_novel_beat_sheet',
    6: 'graphic_novel_beat_sheet_6page',
}
GRAPHIC_NOVEL_SCRIPT_TEMPLATES = {
    5: 'graphic_novel_script',
    6: 'graphic_novel_script_6page',
}
GRAPHIC_NOVEL_ALLOWED_PAGE_COUNTS = (5, 6)
GRAPHIC_NOVEL_DEFAULT_PAGE_COUNT = 5

LEXI_LEGENDS_AGE_LEXILE_THRESHOLD = 800

GRAPHIC_NOVEL_ALLOWED_INTEGRATION_MODES = {
    'dialogue',
    'reasoning',
    'narration',
    'world_logic',
    'lexi_mini_summon',
    'visual_clue',
    'character_action',
}

GRAPHIC_NOVEL_PEDAGOGICAL_ANCHOR_TYPES = {
    'demonstrated_action',
    'near_synonym',
    'category_example',
    'visible_referent',
}

GRAPHIC_NOVEL_SCORING_DIMENSIONS = {
    'narrative_clarity',
    'visual_potential',
    'vocabulary_integration',
    'pedagogical_clarity',
    'character_fit',
}

GRAPHIC_NOVEL_MAX_MINI_SUMMONS_PER_STORY = 1
GRAPHIC_NOVEL_MAX_LOCATIONS_5PAGE = 2
GRAPHIC_NOVEL_MAX_LOCATIONS_6PAGE = 3
GRAPHIC_NOVEL_MAX_SECONDARY_CHARACTERS = 2


def max_locations_for_page_count(page_count: int) -> int:
    if page_count == 6:
        return GRAPHIC_NOVEL_MAX_LOCATIONS_6PAGE
    return GRAPHIC_NOVEL_MAX_LOCATIONS_5PAGE
