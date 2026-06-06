"""Slice a graphic novel page into ordered speech events.

Pure functions over `GraphicNovelPage.panel_descriptions` — no I/O, no DB
writes — so this is cheap to unit-test. Each event is one narration box or one
dialogue line, in reading order (panel order, narration before dialogue within
a panel), carrying the pause that should follow it.
"""
from vocabulary.services.audiobook import constants as C


def _age_band(novel):
    band = (getattr(novel, 'metadata', None) or {}).get('age_band')
    return band if band in C.AGE_STYLE_PREFIX else C.DEFAULT_AGE_BAND


def _pause_after(source, age_band):
    if source == 'narration':
        return C.PAUSE_AFTER_NARRATION_MS.get(age_band, C.PAUSE_AFTER_NARRATION_MS['9yo'])
    return C.PAUSE_AFTER_DIALOGUE_MS.get(age_band, C.PAUSE_AFTER_DIALOGUE_MS['9yo'])


def _speaker_type(speaker):
    name = (speaker or '').strip().lower()
    if name == C.NARRATOR_SPEAKER:
        return 'narrator'
    if name in C.HERO_VOICES:
        return 'recurring_hero'
    return 'story_specific_character'


def build_page_events(page):
    """Return an ordered list of speech-event dicts for one page.

    Event shape:
        {speaker, speaker_type, text, source, vocab_words, panel_number,
         pause_after_ms}

    The last event on the page gets the longer page-end pause instead of its
    normal trailing pause, and the last event in each non-final panel gets the
    inter-panel gutter pause. Panels with no spoken text contribute nothing.
    """
    age_band = _age_band(page.novel)
    panels = sorted(
        page.panel_descriptions or [],
        key=lambda p: p.get('panel_number', 0),
    )

    events = []
    panel_last_index = []  # index into `events` of the last event of each panel

    for panel in panels:
        panel_number = panel.get('panel_number', 0)
        vocab_words = panel.get('vocab_words') or []
        produced = False

        narration = (panel.get('narration') or '').strip()
        if narration:
            events.append({
                'speaker': C.NARRATOR_SPEAKER,
                'speaker_type': 'narrator',
                'text': narration,
                'source': 'narration',
                'vocab_words': vocab_words,
                'panel_number': panel_number,
                'pause_after_ms': _pause_after('narration', age_band),
            })
            produced = True

        for line in panel.get('dialogue') or []:
            text = (line.get('text') or '').strip()
            if not text:
                continue
            speaker = (line.get('speaker') or '').strip() or 'Unknown'
            events.append({
                'speaker': speaker,
                'speaker_type': _speaker_type(speaker),
                'text': text,
                'source': 'dialogue',
                'vocab_words': vocab_words,
                'panel_number': panel_number,
                'pause_after_ms': _pause_after('dialogue', age_band),
            })
            produced = True

        if produced:
            panel_last_index.append(len(events) - 1)

    if not events:
        return events

    # Inter-panel gutter pause after the last event of every panel except the
    # final panel; the very last event gets the page-end pause.
    gutter = C.PAUSE_BETWEEN_PANELS_MS.get(age_band, C.PAUSE_BETWEEN_PANELS_MS['9yo'])
    page_end = C.PAUSE_PAGE_END_MS.get(age_band, C.PAUSE_PAGE_END_MS['9yo'])
    for idx in panel_last_index[:-1]:
        events[idx]['pause_after_ms'] = gutter
    events[panel_last_index[-1]]['pause_after_ms'] = page_end

    return events
