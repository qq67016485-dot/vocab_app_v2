"""Resolve a speaker name to a stable prebuilt Gemini TTS voice.

Heroes and the narrator get fixed picks; story-specific speakers are assigned
deterministically from a pool by hashing their (normalized) name, so the same
character keeps one voice across every page of a novel without needing to
persist a per-novel mapping.
"""
import hashlib

from vocabulary.services.audiobook import constants as C


def age_band_for(novel):
    band = (getattr(novel, 'metadata', None) or {}).get('age_band')
    return band if band in C.AGE_STYLE_PREFIX else C.DEFAULT_AGE_BAND


def voice_for(speaker, novel):
    """Return the prebuilt voice name for `speaker` within `novel`.

    Resolution order: narrator (age-dependent) -> hero map -> deterministic
    supporting-pool slot keyed by the speaker name.
    """
    name = (speaker or '').strip().lower()

    if name == C.NARRATOR_SPEAKER:
        return C.NARRATOR_VOICE_BY_AGE.get(age_band_for(novel), C.NARRATOR_VOICE_DEFAULT)

    if name in C.HERO_VOICES:
        return C.HERO_VOICES[name]

    # Stable hash so the same supporting character always lands on one voice.
    digest = hashlib.sha1(name.encode('utf-8')).hexdigest()
    slot = int(digest, 16) % len(C.SUPPORTING_VOICE_POOL)
    return C.SUPPORTING_VOICE_POOL[slot]


def style_prefix_for(novel):
    """Natural-language performance direction prepended to each line."""
    return C.AGE_STYLE_PREFIX.get(age_band_for(novel), C.AGE_STYLE_PREFIX_DEFAULT)
