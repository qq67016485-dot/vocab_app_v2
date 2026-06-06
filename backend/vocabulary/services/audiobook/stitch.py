"""Stitch per-event PCM clips into a single WAV file with pauses.

All Gemini TTS clips for a page share one PCM format (rate/width/channels), so
we can concatenate raw frames and splice in silence without any transcoding —
stdlib `wave` only, no ffmpeg/pydub. Output is a single WAV byte string.
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
    """Concatenate (pcm_bytes, pause_after_ms) pairs into one WAV.

    Args:
        clips_with_pauses: ordered iterable of (pcm_bytes, pause_after_ms).
            Empty/None pcm entries are skipped (their pause is still honored).

    Returns:
        (wav_bytes, duration_ms): the WAV file bytes and total duration.
    """
    pcm = bytearray()
    for clip, pause_ms in clips_with_pauses:
        if clip:
            pcm.extend(clip)
        if pause_ms:
            pcm.extend(silence_pcm(pause_ms, sample_rate, sample_width, channels))

    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(sample_width)
        wav.setframerate(sample_rate)
        wav.writeframes(bytes(pcm))

    total_frames = len(pcm) // (sample_width * channels) if sample_width and channels else 0
    duration_ms = int(total_frames * 1000 / sample_rate) if sample_rate else 0
    return buffer.getvalue(), duration_ms
