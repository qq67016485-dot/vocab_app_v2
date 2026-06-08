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


def narrator_voice_for(novel):
    """Pick the narrator voice to contrast the hero team's gender.

    Heroes and narrator should sound distinct, so:
      - any female hero on the team (female-only or mixed) -> male narrator
      - an all-male team                                   -> female narrator
      - unknown/empty team                                 -> default narrator

    The team comes from `novel.metadata['away_team']` (a list of hero names).
    Unrecognized names are ignored when judging gender.
    """
    away_team = (getattr(novel, 'metadata', None) or {}).get('away_team') or []
    genders = {
        C.HERO_GENDERS.get((name or '').strip().lower())
        for name in away_team
    }
    genders.discard(None)

    if not genders:
        return C.NARRATOR_VOICE_DEFAULT
    if 'female' in genders:
        return C.NARRATOR_VOICE_MALE
    return C.NARRATOR_VOICE_FEMALE


def _gender_for_speaker(speaker_key, novel):
    """Look up a story-specific speaker's gender from `novel.characters`.

    The final script emits one entry per character with a `gender` field. We
    match on the (normalized) name and return 'male'/'female' when the label is
    clear, else None so callers fall back to the combined supporting pool. Older
    novels generated before gender was emitted simply yield None.
    """
    for char in (getattr(novel, 'characters', None) or []):
        if str(char.get('name', '')).strip().lower() == speaker_key:
            gender = str(char.get('gender', '')).strip().lower()
            return gender if gender in C.SUPPORTING_GENDER_POOLS else None
    return None


def _supporting_voice_for(speaker_key, novel):
    """Deterministic supporting-pool slot for a story-specific speaker.

    Uses the gender-matched pool when the script labeled the character's gender,
    otherwise the combined fallback pool. The speaker name is hashed into the
    chosen pool so the same character keeps one voice across every page.
    """
    gender = _gender_for_speaker(speaker_key, novel)
    pool = C.SUPPORTING_GENDER_POOLS.get(gender, C.SUPPORTING_VOICE_POOL)
    digest = hashlib.sha1(speaker_key.encode('utf-8')).hexdigest()
    return pool[int(digest, 16) % len(pool)]


def voice_for(speaker, novel):
    """Return the prebuilt voice name for `speaker` within `novel`.

    Resolution order: narrator (gender-contrasts the hero team) -> hero map ->
    gender-matched supporting-pool slot keyed by the speaker name.
    """
    name = (speaker or '').strip().lower()

    if name == C.NARRATOR_SPEAKER:
        return narrator_voice_for(novel)

    if name in C.HERO_VOICES:
        return C.HERO_VOICES[name]

    return _supporting_voice_for(name, novel)


def style_prefix_for(novel):
    """Natural-language performance direction prepended to each line."""
    return C.AGE_STYLE_PREFIX.get(age_band_for(novel), C.AGE_STYLE_PREFIX_DEFAULT)
