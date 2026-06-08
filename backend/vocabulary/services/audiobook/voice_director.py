"""Voice director: one LLM call per novel that annotates the full script.

Reads every story page's speech events, sends them to an LLM configured under
the 'audiobook_director' step key, and returns per-character Audio Profile
blocks plus inline-tagged transcript lines. The result is cached in
novel.metadata['voice_director'] so individual page reruns don't re-call the
LLM.
"""
import json
import logging
import os
import re

from django.conf import settings

from vocabulary.services.audiobook import constants as C
from vocabulary.services.audiobook.events import build_page_events
from vocabulary.services.generation.helpers import _call_llm_with_config
from vocabulary.services.generation.llm_config_service import get_step_config

logger = logging.getLogger(__name__)

STEP_KEY = 'audiobook_director'

# Audio tag components that slow speech down. Gemini TTS honors these literally,
# and on top of the already-gentle kid-friendly delivery they make lines drag
# (e.g. Amara reading "[slowly] The lantern is too bright."). We strip them
# defensively so a stray tag from the director LLM — or one cached on an older
# novel — never reaches the TTS call. Emotion/pause cues are left untouched.
_SLOW_TAG_WORD_RE = re.compile(
    r'\b(?:very\s+)?(?:slow(?:ly)?|drawn[\s-]?out|one\s+word\s+at\s+a\s+time|'
    r'word\s+by\s+word|deliberately|draggingly)\b',
    re.IGNORECASE,
)


def _strip_slow_tags(text):
    """Remove slow-pace cues from inline `[...]` audio tags in `text`.

    Within each bracketed tag, drop comma-separated components that ask for
    slow delivery; if that empties the tag, remove the brackets entirely. Tags
    with no slow component (e.g. `[amazed]`, `[nervously, curious]`) pass
    through unchanged. Returns the cleaned, whitespace-normalized string.
    """
    if not text or '[' not in text:
        return text

    def _clean(match):
        inner = match.group(1)
        kept = [
            part.strip() for part in inner.split(',')
            if part.strip() and not _SLOW_TAG_WORD_RE.search(part)
        ]
        return f'[{", ".join(kept)}]' if kept else ''

    cleaned = re.sub(r'\[([^\[\]]*)\]', _clean, text)
    # Collapse any double spaces left where a tag was removed.
    return re.sub(r'\s{2,}', ' ', cleaned).strip()

_PROMPT_PATH = os.path.join(
    settings.BASE_DIR, 'vocabulary', 'prompts', 'audiobook_voice_director.txt',
)

_AGE_GUIDANCE = {
    '9yo': (
        'Younger audience — keep energy gentle and warm. '
        'Avoid jarring delivery; excitement is bouncy not intense.'
    ),
    '12yo': (
        'Older audience — more cinematic, confident delivery is fine. '
        'Characters can be more expressive and nuanced.'
    ),
}


def _load_system_prompt(age_band):
    with open(_PROMPT_PATH, 'r', encoding='utf-8') as f:
        template = f.read()
    guidance = _AGE_GUIDANCE.get(age_band, _AGE_GUIDANCE['9yo'])
    return template.format(age_band=age_band, age_guidance=guidance)


def _gender_map(novel):
    """Build {normalized_name: gender} from the novel's character list.

    Heroes also carry a fixed gender (see constants.HERO_GENDERS) so the
    director gets a consistent label even when the script omits it for a hero.
    Story-specific characters use the script-provided `gender` field.
    """
    mapping = dict(C.HERO_GENDERS)
    for char in (getattr(novel, 'characters', None) or []):
        name = str(char.get('name', '')).strip().lower()
        gender = str(char.get('gender', '')).strip().lower()
        if name and gender:
            mapping[name] = gender
    return mapping


def _build_events_payload(pages, novel=None):
    """Flatten all story pages into a list of event dicts for the LLM input.

    Each dialogue event carries the speaker's `gender` (when known) so the
    director can cast a gender-consistent voice and write matching notes.
    """
    genders = _gender_map(novel) if novel else {}
    rows = []
    for page in pages:
        for idx, event in enumerate(build_page_events(page)):
            row = {
                'page_number': page.page_number,
                'event_index': idx,
                'speaker': event['speaker'],
                'speaker_type': event['speaker_type'],
                'source': event['source'],
                'text': event['text'],
            }
            gender = genders.get(event['speaker'].strip().lower())
            if gender:
                row['gender'] = gender
            rows.append(row)
    return rows


def _index_directed_events(directed_events):
    """Return {(page_number, event_index): directed_text} for fast lookup.

    Slow-pace audio tags are stripped here (see `_strip_slow_tags`) so both
    freshly generated and previously cached director output are sanitized on
    the read path — no LLM re-run needed to fix an existing novel.
    """
    return {
        (e['page_number'], e['event_index']): _strip_slow_tags(e['directed_text'])
        for e in (directed_events or [])
        if 'page_number' in e and 'event_index' in e and 'directed_text' in e
    }


def direct_novel(novel, pages):
    """Call the voice director LLM for a novel and cache the result.

    Returns a direction dict:
        {
            'character_profiles': {'hugo': '# AUDIO PROFILE...', ...},
            'directed_index': {(page_number, event_index): directed_text, ...},
        }

    Falls back gracefully: if the LLM call fails or the cache is present,
    no call is made. Callers should treat a missing directed_text as meaning
    "use original text".
    """
    cached = (novel.metadata or {}).get('voice_director')
    if cached:
        logger.info('Voice director: using cached result for novel %s', novel.pk)
        return {
            'character_profiles': cached.get('character_profiles', {}),
            'directed_index': _index_directed_events(cached.get('directed_events', [])),
        }

    age_band = (novel.metadata or {}).get('age_band', C.DEFAULT_AGE_BAND)
    events_payload = _build_events_payload(pages, novel)
    if not events_payload:
        return {'character_profiles': {}, 'directed_index': {}}

    system_prompt = _load_system_prompt(age_band)
    user_prompt = json.dumps({'speech_events': events_payload}, ensure_ascii=False)

    try:
        step_cfg = get_step_config(STEP_KEY)
        result = _call_llm_with_config(step_cfg['primary'], system_prompt, user_prompt)
    except Exception as exc:  # noqa: BLE001
        logger.warning('Voice director LLM call failed for novel %s: %s', novel.pk, exc)
        return {'character_profiles': {}, 'directed_index': {}}

    if not isinstance(result, dict):
        logger.warning('Voice director returned non-dict for novel %s', novel.pk)
        return {'character_profiles': {}, 'directed_index': {}}

    # Persist to novel metadata so reruns skip the LLM call.
    novel.metadata = {**(novel.metadata or {}), 'voice_director': result}
    novel.save(update_fields=['metadata'])

    return {
        'character_profiles': result.get('character_profiles', {}),
        'directed_index': _index_directed_events(result.get('directed_events', [])),
    }
