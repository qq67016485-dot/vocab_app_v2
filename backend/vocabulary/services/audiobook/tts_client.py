"""Isolated Gemini TTS call — the only place that touches the audio API.

Uses the native `google.genai` client (audio modality is served by Gemini's
native generateContent API, not an OpenAI-compatible chat proxy). Credentials
and endpoint come from the dedicated GEMINI_TTS_* settings so the TTS endpoint
can be pointed at its own proxy independent of text-generation routing. Returns
raw little-endian PCM plus the sample rate parsed from the response mime type,
so the stitcher never hardcodes a rate.
"""
import logging
import re

from django.conf import settings
from google import genai
from google.genai import types

from vocabulary.services.audiobook import constants as C

logger = logging.getLogger(__name__)


class TTSError(RuntimeError):
    """Raised when speech synthesis fails or returns no audio."""


def _client():
    """Native genai client for TTS.

    Uses the dedicated GEMINI_TTS_* settings (falling back to the main Gemini
    key) so the TTS endpoint can be pointed at a proxy that serves the native
    generateContent audio API, independent of the text-generation routing.
    """
    api_key = settings.GEMINI_TTS_API_KEY or settings.GEMINI_API_KEY
    if not api_key:
        raise TTSError(
            'No TTS API key configured. Set GEMINI_TTS_API_KEY (or GEMINI_API_KEY) '
            'in the backend .env.'
        )
    base_url = settings.GEMINI_TTS_BASE_URL or None
    if base_url:
        return genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(base_url=base_url),
        )
    return genai.Client(api_key=api_key)


def _rate_from_mime(mime_type, default=C.PCM_SAMPLE_RATE):
    """Parse the sample rate from a mime type like 'audio/L16;rate=24000'."""
    if not mime_type:
        return default
    match = re.search(r'rate=(\d+)', mime_type)
    return int(match.group(1)) if match else default


def _extract_audio(response):
    """Pull (pcm_bytes, mime_type) out of a TTS generate_content response."""
    candidates = getattr(response, 'candidates', None) or []
    for candidate in candidates:
        content = getattr(candidate, 'content', None)
        parts = getattr(content, 'parts', None) or []
        for part in parts:
            inline = getattr(part, 'inline_data', None)
            if inline and getattr(inline, 'data', None):
                return inline.data, getattr(inline, 'mime_type', None)
    return None, None


def _synthesize_once(client, text, voice_name):
    config = types.GenerateContentConfig(
        response_modalities=['AUDIO'],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name=voice_name,
                ),
            ),
        ),
    )
    response = client.models.generate_content(
        model=settings.GEMINI_TTS_MODEL or C.TTS_MODEL,
        contents=text,
        config=config,
    )
    pcm, mime = _extract_audio(response)
    if not pcm:
        raise TTSError(f'TTS returned no audio for voice {voice_name!r}.')
    return pcm, _rate_from_mime(mime)


def synthesize(text, voice_name, style_prefix=''):
    """Synthesize one line. Returns (pcm_bytes, sample_rate). Retries once.

    `style_prefix` is natural-language performance direction prepended to the
    quoted line; the model speaks only the quoted text.
    """
    prompt = f'{style_prefix} "{text}"' if style_prefix else text
    client = _client()
    try:
        return _synthesize_once(client, prompt, voice_name)
    except Exception as first_exc:  # noqa: BLE001 - retry once, then surface
        logger.warning('TTS attempt failed for voice %s: %s', voice_name, first_exc)
        try:
            return _synthesize_once(client, prompt, voice_name)
        except Exception as retry_exc:  # noqa: BLE001
            raise TTSError(
                f'TTS failed for voice {voice_name!r} after retry: {retry_exc}'
            ) from retry_exc
