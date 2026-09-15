"""Stitch per-event PCM clips into a single WAV file with pauses.

All Gemini TTS clips for a page are expected to share one PCM format
(rate/width/channels) — validated here, because splicing mismatched clips
would stamp the whole WAV with one rate and play every clip at the wrong
speed with no error. With a uniform format we can concatenate raw frames and
splice in silence without any transcoding — stdlib `wave` only, no
ffmpeg/pydub. Output is a single WAV byte string.
"""
import io
import wave

from vocabulary.services.audiobook import constants as C


def silence_pcm(duration_ms, sample_rate=C.PCM_SAMPLE_RATE,
                sample_width=C.PCM_SAMPLE_WIDTH, channels=C.PCM_CHANNELS):
    """Return raw PCM silence of `duration_ms` for the given format."""
    if duration_ms <= 0:
        return b''
    frame_count = int(sample_rate * duration_ms / 1000)
    return b'\x00' * (frame_count * sample_width * channels)


def stitch_pcm(clips_with_pauses, sample_rate=C.PCM_SAMPLE_RATE,
               sample_width=C.PCM_SAMPLE_WIDTH, channels=C.PCM_CHANNELS):
    """Concatenate (pcm_bytes, pause_after_ms, sample_rate) triples into one WAV.

    Args:
        clips_with_pauses: ordered iterable of (pcm_bytes, pause_after_ms,
            sample_rate) triples. Empty/None pcm entries are skipped (their
            pause is still honored).

    Returns:
        (wav_bytes, duration_ms): the WAV file bytes and total duration.

    Raises:
        ValueError: if the clips are not uniform 16-bit PCM at `sample_rate`
            (a mismatch must fail the page, not produce slow/fast audio).
    """
    # lameenc (encode.py) consumes 16-bit PCM; anything else is silently misread.
    if sample_width != 2:
        raise ValueError(
            f'stitch_pcm expects 16-bit PCM (sample width 2), got {sample_width}.'
        )
    frame_bytes = sample_width * channels

    pcm = bytearray()
    for clip, pause_ms, clip_rate in clips_with_pauses:
        if clip:
            if clip_rate != sample_rate:
                raise ValueError(
                    f'Clip sample rate {clip_rate} does not match the others '
                    f'({sample_rate}); refusing to splice mismatched PCM.'
                )
            if len(clip) % frame_bytes:
                raise ValueError(
                    f'Clip length {len(clip)} is not a whole number of '
                    f'{frame_bytes}-byte frames.'
                )
            pcm.extend(clip)
        if pause_ms:
            pcm.extend(silence_pcm(pause_ms, sample_rate, sample_width, channels))

    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(sample_width)
        wav.setframerate(sample_rate)
        wav.writeframes(bytes(pcm))

    total_frames = len(pcm) // frame_bytes
    duration_ms = int(total_frames * 1000 / sample_rate) if sample_rate else 0
    return buffer.getvalue(), duration_ms
