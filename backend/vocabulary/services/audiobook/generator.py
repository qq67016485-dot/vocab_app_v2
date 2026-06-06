"""Generate read-along audio for graphic novel pages.

Walks a page's speech events, synthesizes each line with its speaker's voice,
stitches the clips into one WAV, and records the result on the page's
`GraphicNovelPageAudio` row. Per-page failures are isolated so a novel-level run
can continue and a later retry can fill gaps (mirrors the image step).
"""
import logging

from django.core.files.base import ContentFile
from django.utils import timezone

from vocabulary.models import GraphicNovelPage, GraphicNovelPageAudio
from vocabulary.services.audiobook import constants as C
from vocabulary.services.audiobook.events import build_page_events
from vocabulary.services.audiobook.stitch import stitch_pcm
from vocabulary.services.audiobook.tts_client import synthesize
from vocabulary.services.audiobook.voices import style_prefix_for, voice_for
from vocabulary.services.generation.helpers import _close_old_connections_if_safe

logger = logging.getLogger(__name__)


def _audio_filename(page):
    base = ''.join(
        c if c.isalnum() else '_' for c in (page.novel.title or '').lower()
    ).strip('_')[:60] or 'graphic_novel'
    return f'{base}_page_{page.page_number}.wav'


def generate_page_audio(page):
    """Synthesize + stitch one page's audio onto its GraphicNovelPageAudio row.

    Returns the audio row. Raises on synthesis/stitch failure (caller records
    terminal state). The row is created on demand if missing.
    """
    audio_row, _ = GraphicNovelPageAudio.objects.get_or_create(page=page)
    audio_row.status = GraphicNovelPageAudio.Status.RUNNING
    audio_row.attempts = (audio_row.attempts or 0) + 1
    audio_row.error = ''
    audio_row.started_at = timezone.now()
    audio_row.completed_at = None
    audio_row.save(update_fields=[
        'status', 'attempts', 'error', 'started_at', 'completed_at',
    ])

    events = build_page_events(page)
    style_prefix = style_prefix_for(page.novel)

    clips_with_pauses = []
    manifest_events = []
    sample_rate = C.PCM_SAMPLE_RATE

    # Release the DB connection while waiting on the (slow) TTS calls.
    _close_old_connections_if_safe()
    try:
        for event in events:
            voice = voice_for(event['speaker'], page.novel)
            pcm, rate = synthesize(event['text'], voice, style_prefix)
            sample_rate = rate  # all clips share the model's rate
            clips_with_pauses.append((pcm, event['pause_after_ms']))
            manifest_events.append({
                'speaker': event['speaker'],
                'speaker_type': event['speaker_type'],
                'voice': voice,
                'source': event['source'],
                'panel_number': event['panel_number'],
                'chars': len(event['text']),
            })
    finally:
        _close_old_connections_if_safe()

    wav_bytes, duration_ms = stitch_pcm(clips_with_pauses, sample_rate=sample_rate)

    audio_row.audio.save(_audio_filename(page), ContentFile(wav_bytes), save=False)
    audio_row.duration_ms = duration_ms
    audio_row.voice_manifest = {
        'age_band': (page.novel.metadata or {}).get('age_band', C.DEFAULT_AGE_BAND),
        'sample_rate': sample_rate,
        'event_count': len(manifest_events),
        'events': manifest_events,
    }
    audio_row.status = GraphicNovelPageAudio.Status.COMPLETED
    audio_row.error = ''
    audio_row.completed_at = timezone.now()
    audio_row.save(update_fields=[
        'audio', 'duration_ms', 'voice_manifest', 'status', 'error', 'completed_at',
    ])
    return audio_row


def _mark_failed(page, exc):
    audio_row, _ = GraphicNovelPageAudio.objects.get_or_create(page=page)
    audio_row.status = GraphicNovelPageAudio.Status.FAILED
    audio_row.error = str(exc)
    audio_row.completed_at = timezone.now()
    audio_row.save(update_fields=['status', 'error', 'completed_at'])
    return audio_row


def generate_novel_audio(novel_id, regenerate=False):
    """Generate audio for every story page of a novel. Continue-on-failure.

    Skips the review page (no narration/dialogue). Skips pages that already have
    COMPLETED audio unless `regenerate` is True. Returns a summary dict.
    """
    pages = list(
        GraphicNovelPage.objects
        .filter(novel_id=novel_id, is_review_page=False)
        .select_related('novel')
        .order_by('page_number')
    )

    created, skipped, failed = 0, 0, []
    for page in pages:
        existing = getattr(page, 'audio', None)
        if (not regenerate and existing
                and existing.status == GraphicNovelPageAudio.Status.COMPLETED
                and existing.audio):
            skipped += 1
            continue

        # A page with no spoken text produces no audio; mark it COMPLETED-empty.
        if not build_page_events(page):
            skipped += 1
            continue

        try:
            generate_page_audio(page)
            created += 1
        except Exception as exc:  # noqa: BLE001 - isolate per-page failures
            logger.error(
                'Audio generation failed for novel %s page %s: %s',
                novel_id, page.page_number, exc,
            )
            _mark_failed(page, exc)
            failed.append(page.page_number)

    return {
        'novel_id': novel_id,
        'pages_created': created,
        'pages_skipped': skipped,
        'failed_pages': failed,
    }
