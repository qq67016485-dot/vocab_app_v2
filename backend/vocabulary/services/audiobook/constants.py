"""Constants for the read-along audiobook pipeline.

Voice assignments, age-band style guidance, pause timing, and the PCM audio
format are centralized here so the generator, voice resolver, and stitcher all
agree. See docs/feature_plan/lexi-legends-audiobook-production-bible.md for the
production rules these encode.
"""

# --- Audio format -----------------------------------------------------------
# Gemini TTS returns raw little-endian PCM. The documented default is 24 kHz,
# 16-bit, mono. tts_client parses the actual rate from the response mime type
# (e.g. "audio/L16;rate=24000") and falls back to this when absent.
TTS_MODEL = 'gemini-2.5-pro-preview-tts'
PCM_SAMPLE_RATE = 24000
PCM_SAMPLE_WIDTH = 2  # bytes (16-bit)
PCM_CHANNELS = 1

# --- Voice catalog ----------------------------------------------------------
# Stable per-character voices so a speaker never drifts between pages. Heroes
# get fixed picks. The narrator is chosen to CONTRAST the hero team's gender so
# narrator and heroes stay distinct: an all-male team gets the female narrator
# and any team with a female hero (female-only or mixed) gets the male narrator.
# Story-specific speakers fall back to SUPPORTING_VOICE_POOL, assigned
# deterministically by name.
NARRATOR_VOICE_MALE = 'Charon'     # informative, cinematic
NARRATOR_VOICE_FEMALE = 'Aoede'    # warm storytelling
# Used when the hero team is unknown (no away_team metadata / no recognized
# hero): fall back to the warm storytelling voice.
NARRATOR_VOICE_DEFAULT = NARRATOR_VOICE_FEMALE

HERO_VOICES = {
    'leo': 'Puck',        # upbeat
    'amara': 'Despina',   # smooth
    'mei': 'Zephyr',      # bright
    'hugo': 'Achird',     # friendly
}

# Hero genders drive narrator selection (see narrator rule above). Keep in sync
# with the LEXI_CHARACTERS canon set.
HERO_GENDERS = {
    'leo': 'male',
    'hugo': 'male',
    'amara': 'female',
    'mei': 'female',
}

# Gendered pools for story-specific (non-hero) speakers. A secondary character's
# gender comes from the final script's `characters[].gender`; the speaker name is
# hashed into the matching pool so the character keeps ONE gender-appropriate
# voice across every page. An unknown/neutral/unlabeled gender (e.g. older novels
# generated before gender was emitted) falls back to the combined pool, which
# preserves the prior name-hash behavior.
SUPPORTING_VOICE_POOL_MALE = (
    'Orus',         # firm
    'Enceladus',    # breathy
    'Iapetus',      # clear
    'Umbriel',      # easy-going
)
SUPPORTING_VOICE_POOL_FEMALE = (
    'Leda',         # youthful
    'Aoede',        # breezy
    'Callirrhoe',   # easy-going
    'Achernar',     # soft
)
# Combined fallback for unknown/neutral gender. Order matters: selection hashes
# the speaker name into this list so a given character keeps one voice.
SUPPORTING_VOICE_POOL = SUPPORTING_VOICE_POOL_FEMALE + SUPPORTING_VOICE_POOL_MALE

NARRATOR_SPEAKER = 'narrator'

# Map the gender label a secondary character carries in the final script's
# `characters[].gender` to a supporting voice pool. Anything that is not clearly
# male or female (e.g. 'nonbinary', 'unknown', '', a creature) uses the combined
# fallback pool so behavior matches pre-gender novels.
SUPPORTING_GENDER_POOLS = {
    'male': SUPPORTING_VOICE_POOL_MALE,
    'female': SUPPORTING_VOICE_POOL_FEMALE,
}

# --- Age-band performance prefixes ------------------------------------------
# Prepended to a line as natural-language style direction (Gemini TTS honors a
# leading instruction). Keeps voices fixed while steering tone/pace by age.
AGE_STYLE_PREFIX = {
    '9yo': (
        'Read warmly and clearly for a 9-year-old, at a gentle, slightly slower '
        'pace, with friendly expression. Pronounce every word distinctly. '
        'Say only the quoted line:'
    ),
    '12yo': (
        'Read naturally and expressively for a 12-year-old, with confident, '
        'cinematic delivery and clear pronunciation. Say only the quoted line:'
    ),
}
AGE_STYLE_PREFIX_DEFAULT = AGE_STYLE_PREFIX['9yo']

# --- Pause timing (milliseconds) --------------------------------------------
# From the production bible's Read-Along Timing section. 9yo prefers the longer
# end of each range; 12yo the shorter (except suspense/page-end).
PAUSE_AFTER_DIALOGUE_MS = {'9yo': 400, '12yo': 250}
PAUSE_AFTER_NARRATION_MS = {'9yo': 700, '12yo': 450}
PAUSE_BETWEEN_PANELS_MS = {'9yo': 1500, '12yo': 1000}
PAUSE_PAGE_END_MS = {'9yo': 2500, '12yo': 2000}

DEFAULT_AGE_BAND = '9yo'
