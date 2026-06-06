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
# get fixed picks; the narrator varies by age band. Story-specific speakers
# fall back to SUPPORTING_VOICE_POOL, assigned deterministically by name.
NARRATOR_VOICE_BY_AGE = {
    '9yo': 'Sulafat',   # warm storytelling
    '12yo': 'Charon',   # informative, more cinematic
}
NARRATOR_VOICE_DEFAULT = 'Sulafat'

HERO_VOICES = {
    'leo': 'Puck',      # upbeat
    'amara': 'Kore',    # firm, measured
    'mei': 'Fenrir',    # excitable
    'hugo': 'Aoede',    # breezy, gentle
}

# Deterministic pool for story-specific (non-hero) speakers. Order matters:
# selection hashes the speaker name into this list so a given character keeps
# one voice for the whole novel.
SUPPORTING_VOICE_POOL = (
    'Zephyr',       # bright
    'Leda',         # youthful
    'Orus',         # firm
    'Enceladus',    # breathy
    'Aoede',        # breezy
    'Charon',       # informative
)

NARRATOR_SPEAKER = 'narrator'

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
