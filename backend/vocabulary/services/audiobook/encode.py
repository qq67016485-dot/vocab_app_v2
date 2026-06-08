"""WAV -> MP3 conversion for the read-along audiobook.

Produces a compressed MP3 companion of a page's stitched WAV. The WAV stays the
source of truth (admin/review, regeneration); students load the smaller MP3 to
save mobile bandwidth, mirroring the PNG/JPEG image companion pattern.

Uses `lameenc` (a pure binary-wheel LAME encoder) rather than ffmpeg/pydub, so
there is no system binary to install on the box — consistent with the WAV
stitcher, which uses only the stdlib `wave` module.
"""
import io
import wave

import lameenc

# Mono speech at 24 kHz compresses cleanly at a modest bitrate; 64 kbps keeps
# the read-along clearly intelligible at roughly 6x smaller than 16-bit PCM.
DEFAULT_MP3_BITRATE_KBPS = 64
# LAME quality: 0 = best/slowest, 9 = worst/fastest. 2 is high quality and fast
# enough for the one-off per-page conversion.
DEFAULT_LAME_QUALITY = 2


def wav_bytes_to_mp3_bytes(wav_bytes, bitrate_kbps=DEFAULT_MP3_BITRATE_KBPS,
                           quality=DEFAULT_LAME_QUALITY):
    """Convert WAV file bytes to MP3 bytes.

    Reads the sample rate / width / channel count straight from the WAV header
    (the stitcher writes 16-bit mono PCM, but we honor whatever the file says)
    and re-encodes the raw frames with LAME.

    Raises ValueError if the input cannot be decoded as a 16-bit PCM WAV.
    """
    if not wav_bytes:
        raise ValueError("No WAV bytes provided for MP3 conversion.")

    try:
        with wave.open(io.BytesIO(wav_bytes), 'rb') as wav:
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            sample_rate = wav.getframerate()
            pcm = wav.readframes(wav.getnframes())
    except Exception as exc:  # noqa: BLE001 - normalize decode failures
        raise ValueError(f"Could not read WAV for MP3 conversion: {exc}") from exc

    # lameenc consumes 16-bit PCM; anything else would be silently misread.
    if sample_width != 2:
        raise ValueError(
            f"MP3 conversion expects 16-bit PCM WAV, got sample width {sample_width}."
        )

    try:
        encoder = lameenc.Encoder()
        encoder.set_bit_rate(bitrate_kbps)
        encoder.set_in_sample_rate(sample_rate)
        encoder.set_channels(channels)
        encoder.set_quality(quality)
        mp3 = encoder.encode(pcm)
        mp3 += encoder.flush()
        return bytes(mp3)
    except Exception as exc:  # noqa: BLE001 - normalize encode failures
        raise ValueError(f"Could not encode WAV to MP3: {exc}") from exc
