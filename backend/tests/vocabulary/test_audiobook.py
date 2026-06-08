"""Tests for the read-along audiobook pipeline.

Covers the pure-logic layers (events, voices, stitch) and the view endpoints
with a mocked TTS client so no real API calls are made.
"""
import io
import wave
from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from vocabulary.models import GraphicNovel, GraphicNovelPage, GraphicNovelPageAudio
from vocabulary.services.audiobook.constants import (
    DEFAULT_AGE_BAND, HERO_VOICES, NARRATOR_VOICE_FEMALE, NARRATOR_VOICE_MALE,
    NARRATOR_VOICE_DEFAULT,
    PAUSE_AFTER_DIALOGUE_MS, PAUSE_AFTER_NARRATION_MS, PAUSE_PAGE_END_MS,
    PAUSE_BETWEEN_PANELS_MS,
)
from vocabulary.services.audiobook.events import build_page_events
from vocabulary.services.audiobook.stitch import silence_pcm, stitch_pcm
from vocabulary.services.audiobook.voices import voice_for


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_novel(metadata=None, characters=None):
    novel = MagicMock(spec=GraphicNovel)
    novel.metadata = metadata or {'age_band': '9yo'}
    novel.title = 'Test Novel'
    novel.characters = characters or []
    return novel


def _make_page(panel_descriptions, metadata=None, is_review=False):
    page = MagicMock(spec=GraphicNovelPage)
    page.panel_descriptions = panel_descriptions
    page.novel = _make_novel(metadata)
    page.is_review_page = is_review
    page.page_number = 1
    return page


def _short_pcm(sample_rate=24000, channels=1, sample_width=2, duration_ms=10):
    """Tiny valid PCM chunk (10 ms silence by default)."""
    frame_count = int(sample_rate * duration_ms / 1000)
    return b'\x00' * (frame_count * sample_width * channels)


# ---------------------------------------------------------------------------
# events.py
# ---------------------------------------------------------------------------

class TestBuildPageEvents:
    def test_empty_panels_returns_no_events(self):
        page = _make_page([])
        assert build_page_events(page) == []

    def test_narration_only_panel(self):
        page = _make_page([{'panel_number': 1, 'narration': 'Once upon a time.',
                             'dialogue': [], 'vocab_words': []}])
        events = build_page_events(page)
        assert len(events) == 1
        e = events[0]
        assert e['speaker'] == 'narrator'
        assert e['text'] == 'Once upon a time.'
        assert e['source'] == 'narration'

    def test_dialogue_after_narration_in_same_panel(self):
        page = _make_page([{
            'panel_number': 1,
            'narration': 'She looked up.',
            'dialogue': [{'speaker': 'Amara', 'text': 'I see it.'}],
            'vocab_words': ['see'],
        }])
        events = build_page_events(page)
        assert events[0]['source'] == 'narration'
        assert events[1]['speaker'] == 'Amara'
        assert events[1]['speaker_type'] == 'recurring_hero'
        assert 'see' in events[1]['vocab_words']

    def test_multi_panel_gutter_pause(self):
        panels = [
            {'panel_number': 1, 'narration': 'First.', 'dialogue': [], 'vocab_words': []},
            {'panel_number': 2, 'narration': 'Second.', 'dialogue': [], 'vocab_words': []},
        ]
        events = build_page_events(_make_page(panels))
        assert len(events) == 2
        gutter = PAUSE_BETWEEN_PANELS_MS['9yo']
        page_end = PAUSE_PAGE_END_MS['9yo']
        assert events[0]['pause_after_ms'] == gutter
        assert events[1]['pause_after_ms'] == page_end

    def test_single_panel_gets_page_end_pause(self):
        page = _make_page([{'panel_number': 1, 'narration': 'Only.', 'dialogue': [], 'vocab_words': []}])
        events = build_page_events(page)
        assert events[-1]['pause_after_ms'] == PAUSE_PAGE_END_MS['9yo']

    def test_narration_pause_applied(self):
        page = _make_page([{'panel_number': 1, 'narration': 'Only.', 'dialogue': [], 'vocab_words': []}])
        events = build_page_events(page)
        # Single panel last event overridden to page_end; base narration pause not visible here
        # Test inter-panel: with two panels the first event keeps narration pause→gutter override
        panels = [
            {'panel_number': 1, 'narration': 'A.', 'dialogue': [], 'vocab_words': []},
            {'panel_number': 2, 'narration': 'B.', 'dialogue': [], 'vocab_words': []},
        ]
        events2 = build_page_events(_make_page(panels))
        assert events2[0]['pause_after_ms'] == PAUSE_BETWEEN_PANELS_MS['9yo']

    def test_dialogue_pause_on_non_last_event(self):
        """Within a panel with narration + dialogue, narration gets gutter if last in panel."""
        panels = [
            {'panel_number': 1,
             'narration': 'A.',
             'dialogue': [{'speaker': 'Leo', 'text': 'Yes.'}],
             'vocab_words': []},
            {'panel_number': 2, 'narration': 'B.', 'dialogue': [], 'vocab_words': []},
        ]
        events = build_page_events(_make_page(panels))
        # panel 1's last event is the Leo dialogue → gets gutter pause
        assert events[1]['pause_after_ms'] == PAUSE_BETWEEN_PANELS_MS['9yo']

    def test_skips_blank_dialogue_text(self):
        page = _make_page([{'panel_number': 1, 'narration': '',
                             'dialogue': [{'speaker': 'Hugo', 'text': ''}],
                             'vocab_words': []}])
        assert build_page_events(page) == []

    def test_unknown_age_band_defaults(self):
        page = _make_page([{'panel_number': 1, 'narration': 'Hi.', 'dialogue': [], 'vocab_words': []}],
                          metadata={'age_band': 'unknown'})
        events = build_page_events(page)
        assert events[-1]['pause_after_ms'] == PAUSE_PAGE_END_MS[DEFAULT_AGE_BAND]

    def test_panels_sorted_by_number(self):
        panels = [
            {'panel_number': 3, 'narration': 'Third.', 'dialogue': [], 'vocab_words': []},
            {'panel_number': 1, 'narration': 'First.', 'dialogue': [], 'vocab_words': []},
        ]
        events = build_page_events(_make_page(panels))
        assert events[0]['text'] == 'First.'


# ---------------------------------------------------------------------------
# voices.py
# ---------------------------------------------------------------------------

class TestVoiceFor:
    def test_narrator_female_team_uses_male_narrator(self):
        novel = _make_novel({'age_band': '9yo', 'away_team': ['Amara']})
        assert voice_for('narrator', novel) == NARRATOR_VOICE_MALE

    def test_narrator_male_team_uses_female_narrator(self):
        novel = _make_novel({'age_band': '9yo', 'away_team': ['Hugo']})
        assert voice_for('narrator', novel) == NARRATOR_VOICE_FEMALE

    def test_narrator_mixed_team_uses_male_narrator(self):
        novel = _make_novel({'age_band': '9yo', 'away_team': ['Leo', 'Mei']})
        assert voice_for('narrator', novel) == NARRATOR_VOICE_MALE

    def test_narrator_unknown_team_uses_default(self):
        novel = _make_novel({'age_band': '9yo'})
        assert voice_for('narrator', novel) == NARRATOR_VOICE_DEFAULT

    def test_hero_amara(self):
        assert voice_for('Amara', _make_novel()) == HERO_VOICES['amara']

    def test_hero_case_insensitive(self):
        assert voice_for('LEO', _make_novel()) == HERO_VOICES['leo']

    def test_supporting_deterministic(self):
        novel = _make_novel()
        v1 = voice_for('Dr. Okafor', novel)
        v2 = voice_for('Dr. Okafor', novel)
        assert v1 == v2

    def test_different_supporting_speakers_can_differ(self):
        novel = _make_novel()
        # Not guaranteed to differ but high probability; just check no crash
        voice_for('Speaker A', novel)
        voice_for('Speaker B', novel)

    def test_male_secondary_uses_male_pool(self):
        from vocabulary.services.audiobook.constants import SUPPORTING_VOICE_POOL_MALE
        novel = _make_novel(characters=[{'name': 'Toby', 'gender': 'male'}])
        assert voice_for('Toby', novel) in SUPPORTING_VOICE_POOL_MALE

    def test_female_secondary_uses_female_pool(self):
        from vocabulary.services.audiobook.constants import SUPPORTING_VOICE_POOL_FEMALE
        novel = _make_novel(characters=[{'name': 'Nadia', 'gender': 'female'}])
        assert voice_for('Nadia', novel) in SUPPORTING_VOICE_POOL_FEMALE

    def test_secondary_gender_is_stable(self):
        novel = _make_novel(characters=[{'name': 'Toby', 'gender': 'male'}])
        assert voice_for('Toby', novel) == voice_for('Toby', novel)

    def test_unlabeled_secondary_uses_combined_pool(self):
        from vocabulary.services.audiobook.constants import SUPPORTING_VOICE_POOL
        novel = _make_novel(characters=[{'name': 'Toby', 'visual_description': 'A boy.'}])
        assert voice_for('Toby', novel) in SUPPORTING_VOICE_POOL

    def test_neutral_gender_falls_back_to_combined_pool(self):
        from vocabulary.services.audiobook.constants import SUPPORTING_VOICE_POOL
        novel = _make_novel(characters=[{'name': 'Sprite', 'gender': 'neutral'}])
        assert voice_for('Sprite', novel) in SUPPORTING_VOICE_POOL


# ---------------------------------------------------------------------------
# voice_director.py — gender in events payload
# ---------------------------------------------------------------------------

class TestVoiceDirectorEventsPayload:
    def test_secondary_gender_attached_to_dialogue_event(self):
        from vocabulary.services.audiobook.voice_director import _build_events_payload
        novel = _make_novel(characters=[{'name': 'Toby', 'gender': 'male'}])
        page = _make_page([{
            'panel_number': 1,
            'narration': 'A quiet street.',
            'dialogue': [{'speaker': 'Toby', 'text': 'Wait for me!'}],
            'vocab_words': [],
        }])
        page.novel = novel
        rows = _build_events_payload([page], novel)
        toby = next(r for r in rows if r['speaker'] == 'Toby')
        assert toby['gender'] == 'male'
        narration = next(r for r in rows if r['source'] == 'narration')
        assert 'gender' not in narration  # narrator carries no character gender

    def test_hero_gender_attached_from_canon(self):
        from vocabulary.services.audiobook.voice_director import _build_events_payload
        novel = _make_novel()  # no script-provided characters
        page = _make_page([{
            'panel_number': 1,
            'narration': '',
            'dialogue': [{'speaker': 'Amara', 'text': 'I see it.'}],
            'vocab_words': [],
        }])
        page.novel = novel
        rows = _build_events_payload([page], novel)
        amara = next(r for r in rows if r['speaker'] == 'Amara')
        assert amara['gender'] == 'female'

    def test_unlabeled_secondary_has_no_gender_key(self):
        from vocabulary.services.audiobook.voice_director import _build_events_payload
        novel = _make_novel(characters=[{'name': 'Toby'}])
        page = _make_page([{
            'panel_number': 1,
            'narration': '',
            'dialogue': [{'speaker': 'Toby', 'text': 'Hi.'}],
            'vocab_words': [],
        }])
        page.novel = novel
        rows = _build_events_payload([page], novel)
        toby = next(r for r in rows if r['speaker'] == 'Toby')
        assert 'gender' not in toby


# ---------------------------------------------------------------------------
# stitch.py
# ---------------------------------------------------------------------------

class TestStitchPcm:
    def test_empty_clips_produces_valid_wav(self):
        wav_bytes, dur = stitch_pcm([])
        assert dur == 0
        buf = io.BytesIO(wav_bytes)
        with wave.open(buf, 'rb') as w:
            assert w.getnframes() == 0

    def test_silence_correct_length(self):
        pcm = silence_pcm(100)  # 100 ms at 24kHz 16-bit mono
        expected = int(24000 * 0.1) * 2 * 1
        assert len(pcm) == expected

    def test_stitch_duration_matches_wav_header(self):
        clip = _short_pcm()
        wav_bytes, dur = stitch_pcm([(clip, 0)])
        buf = io.BytesIO(wav_bytes)
        with wave.open(buf, 'rb') as w:
            assert w.getnframes() > 0
            actual_dur = int(w.getnframes() * 1000 / w.getframerate())
        assert actual_dur == dur

    def test_pause_adds_frames(self):
        clip = _short_pcm(duration_ms=10)
        _, dur_no_pause = stitch_pcm([(clip, 0)])
        _, dur_with_pause = stitch_pcm([(clip, 500)])
        assert dur_with_pause > dur_no_pause

    def test_none_clip_skipped(self):
        _, dur = stitch_pcm([(None, 200)])
        assert dur == 200


# ---------------------------------------------------------------------------
# encode.py (WAV -> MP3)
# ---------------------------------------------------------------------------

class TestWavToMp3:
    def test_encodes_to_mp3_and_shrinks(self):
        from vocabulary.services.audiobook.encode import wav_bytes_to_mp3_bytes
        # ~1s of silence is enough for the MP3 frame header to appear.
        wav_bytes, _ = stitch_pcm([(_short_pcm(duration_ms=1000), 0)])
        mp3_bytes = wav_bytes_to_mp3_bytes(wav_bytes)
        assert mp3_bytes
        # MP3 frame sync word (0xFFE) or an ID3 tag at the start.
        assert mp3_bytes[:3] == b'ID3' or mp3_bytes[0] == 0xFF
        assert len(mp3_bytes) < len(wav_bytes)

    def test_empty_input_raises(self):
        from vocabulary.services.audiobook.encode import wav_bytes_to_mp3_bytes
        with pytest.raises(ValueError):
            wav_bytes_to_mp3_bytes(b'')

    def test_non_wav_input_raises(self):
        from vocabulary.services.audiobook.encode import wav_bytes_to_mp3_bytes
        with pytest.raises(ValueError):
            wav_bytes_to_mp3_bytes(b'not a wav file at all')


# ---------------------------------------------------------------------------
# Views (mocked TTS)
# ---------------------------------------------------------------------------

@pytest.fixture
def admin_client(db):
    from tests.factories import AdminUserFactory
    user = AdminUserFactory()
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def novel_with_pages(db):
    from tests.factories import (
        WordPackFactory, GraphicNovelFactory, GraphicNovelPageFactory,
    )
    pack = WordPackFactory()
    novel = GraphicNovelFactory(pack=pack)
    pages = [
        GraphicNovelPageFactory(
            novel=novel,
            page_number=i,
            panel_descriptions=[{
                'panel_number': 1,
                'narration': f'Page {i} narration.',
                'dialogue': [],
                'vocab_words': [],
            }],
        )
        for i in range(1, 4)
    ]
    return novel, pages


FAKE_PCM = _short_pcm()


def _fake_synthesize(text, voice_name, style_prefix=''):
    return FAKE_PCM, 24000


class TestGenerateNovelAudio:
    """Exercise the generator synchronously (the threaded view is just plumbing)."""

    @patch('vocabulary.services.audiobook.generator.synthesize', side_effect=_fake_synthesize)
    def test_all_pages_completed(self, _mock, novel_with_pages):
        from vocabulary.services.audiobook.generator import generate_novel_audio
        novel, pages = novel_with_pages
        summary = generate_novel_audio(novel.id)
        assert summary['pages_created'] == 3
        assert summary['failed_pages'] == []
        for page in pages:
            audio = GraphicNovelPageAudio.objects.get(page=page)
            assert audio.status == GraphicNovelPageAudio.Status.COMPLETED
            assert audio.duration_ms > 0
            assert audio.audio
            # MP3 companion is generated best-effort alongside the WAV.
            assert audio.audio_mp3
            assert audio.audio_mp3.name.endswith('.mp3')
            # Students get the MP3 via student_audio.
            assert audio.student_audio.name == audio.audio_mp3.name

    @patch('vocabulary.services.audiobook.generator.synthesize', side_effect=_fake_synthesize)
    def test_skips_already_completed(self, _mock, novel_with_pages):
        from vocabulary.services.audiobook.generator import generate_novel_audio
        novel, _ = novel_with_pages
        generate_novel_audio(novel.id)
        summary = generate_novel_audio(novel.id)  # second run
        assert summary['pages_created'] == 0
        assert summary['pages_skipped'] == 3

    @patch('vocabulary.services.audiobook.generator.synthesize', side_effect=_fake_synthesize)
    def test_regenerate_reruns(self, _mock, novel_with_pages):
        from vocabulary.services.audiobook.generator import generate_novel_audio
        novel, _ = novel_with_pages
        generate_novel_audio(novel.id)
        summary = generate_novel_audio(novel.id, regenerate=True)
        assert summary['pages_created'] == 3

    @patch('vocabulary.services.audiobook.generator.synthesize',
           side_effect=RuntimeError('boom'))
    def test_per_page_failure_isolated(self, _mock, novel_with_pages):
        from vocabulary.services.audiobook.generator import generate_novel_audio
        novel, pages = novel_with_pages
        summary = generate_novel_audio(novel.id)
        assert summary['pages_created'] == 0
        assert len(summary['failed_pages']) == 3
        for page in pages:
            audio = GraphicNovelPageAudio.objects.get(page=page)
            assert audio.status == GraphicNovelPageAudio.Status.FAILED


class TestGenerateAudioView:
    def test_returns_202(self, admin_client, novel_with_pages):
        novel, _ = novel_with_pages
        url = reverse('graphic-novel-generate-audio', kwargs={'novel_id': novel.id})
        with patch('vocabulary.views.generation_views._run_novel_audio'):
            resp = admin_client.post(url, {}, format='json')
        assert resp.status_code == status.HTTP_202_ACCEPTED

    def test_404_for_missing_novel(self, admin_client, db):
        url = reverse('graphic-novel-generate-audio', kwargs={'novel_id': 99999})
        resp = admin_client.post(url, {}, format='json')
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_409_when_already_running(self, admin_client, novel_with_pages):
        novel, pages = novel_with_pages
        audio, _ = GraphicNovelPageAudio.objects.get_or_create(page=pages[0])
        audio.status = GraphicNovelPageAudio.Status.RUNNING
        audio.save()
        url = reverse('graphic-novel-generate-audio', kwargs={'novel_id': novel.id})
        resp = admin_client.post(url, {}, format='json')
        assert resp.status_code == status.HTTP_409_CONFLICT


class TestAudioStatusView:
    @patch('vocabulary.services.audiobook.tts_client.synthesize', side_effect=_fake_synthesize)
    def test_status_returns_per_page_data(self, _mock, admin_client, novel_with_pages):
        novel, _ = novel_with_pages
        url = reverse('graphic-novel-audio-status', kwargs={'novel_id': novel.id})
        resp = admin_client.get(url)
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data['novel_id'] == novel.id
        assert len(resp.data['pages']) == 3

    def test_404_for_missing_novel(self, admin_client, db):
        url = reverse('graphic-novel-audio-status', kwargs={'novel_id': 99999})
        resp = admin_client.get(url)
        assert resp.status_code == status.HTTP_404_NOT_FOUND
