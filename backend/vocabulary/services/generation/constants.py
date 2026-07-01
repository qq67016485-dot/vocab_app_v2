"""Constants shared across generation pipeline modules."""
from vocabulary.models import GenerationJobLog

DEFAULT_MODEL = 'gemini-3.1-pro-preview'
BACKUP_MODEL = 'gemini-3-pro-preview'
GRAPHIC_NOVEL_SCRIPT_MODEL = 'gemini-3.1-pro-preview'
GRAPHIC_NOVEL_IMAGE_MODEL = 'gpt-image-2'

# Number of independent graphic novel candidates generated per pack. An admin
# picks one to publish; the others are kept (hidden) for reconsideration. Each
# candidate reruns the full team-selection→script workflow, so they diverge in
# story, art, and framing — countering per-call LLM variance.
GRAPHIC_NOVEL_CANDIDATE_COUNT = 3

PIPELINE_STEP_ORDER = [
    GenerationJobLog.Step.WORD_LOOKUP,
    GenerationJobLog.Step.DEDUP,
    GenerationJobLog.Step.TRANSLATION,
    GenerationJobLog.Step.QUESTION_GEN,
    GenerationJobLog.Step.PRIMER_GEN,
    GenerationJobLog.Step.PACK_CREATION,
    GenerationJobLog.Step.GRAPHIC_NOVEL_SCRIPT,
    GenerationJobLog.Step.GRAPHIC_NOVEL_IMAGES,
    GenerationJobLog.Step.INFOGRAPHIC_DESIGN,
    GenerationJobLog.Step.INFOGRAPHIC_IMAGE,
]

# Content-type keys used by GenerationJob.content_types to gate which
# instructional formats a job generates. An empty/legacy list means graphic
# novel only (the historical behaviour before infographics existed).
CONTENT_TYPE_GRAPHIC_NOVEL = 'graphic_novel'
CONTENT_TYPE_INFOGRAPHIC = 'infographic'
ALLOWED_CONTENT_TYPES = (CONTENT_TYPE_GRAPHIC_NOVEL, CONTENT_TYPE_INFOGRAPHIC)


def job_generates_content_type(job, content_type):
    """Whether ``job`` should generate ``content_type``.

    An empty ``content_types`` (legacy jobs created before the field existed)
    means graphic novel only.
    """
    types = job.content_types or []
    if not types:
        return content_type == CONTENT_TYPE_GRAPHIC_NOVEL
    return content_type in types


# Number of independent infographic candidates generated per pack — mirrors the
# graphic novel candidate model so an admin picks the best of several rolls.
INFOGRAPHIC_CANDIDATE_COUNT = 3

# Infographic generation substeps (design → cloze). Far lighter than the graphic
# novel workflow: neutral educational style, no canon/team selection.
INFOGRAPHIC_SUBSTEPS = [
    {
        'key': 'design',
        'label': 'Infographic Design',
        'template': 'infographic_design',
        'filename': '01_infographic_design.json',
        'config_key': 'ig_design',
    },
    {
        'key': 'cloze',
        'label': 'Infographic Cloze',
        'template': 'infographic_cloze',
        'filename': '02_infographic_cloze.json',
        'config_key': 'ig_cloze',
    },
]
INFOGRAPHIC_IMAGE_MODEL = 'gpt-image-2'

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

# Page count is derived deterministically from the number of words in the pack
# (not chosen by the router LLM): packs with more than this many words get the
# longer 6-page format so there is room to anchor every target word.
GRAPHIC_NOVEL_WORD_COUNT_PAGE_THRESHOLD = 4


def max_locations_for_page_count(page_count: int) -> int:
    if page_count == 6:
        return GRAPHIC_NOVEL_MAX_LOCATIONS_6PAGE
    return GRAPHIC_NOVEL_MAX_LOCATIONS_5PAGE


def page_count_for_word_count(word_count: int) -> int:
    """Map a pack's word count to its graphic novel page count.

    Up to and including the threshold → 5 pages; more than the threshold → 6.
    This is authoritative: the router LLM is told the required length, but the
    pipeline forces this value regardless of what the model returns.
    """
    if word_count > GRAPHIC_NOVEL_WORD_COUNT_PAGE_THRESHOLD:
        return 6
    return 5
