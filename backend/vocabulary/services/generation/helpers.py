"""Shared helpers for the generation pipeline."""
import hashlib
import logging

from django.db import close_old_connections, connection

from vocabulary.models import GenerationJob, GenerationJobLog
import vocabulary.services.llm_service as _llm_service

logger = logging.getLogger(__name__)

LEXILE_OFFSET = 0.85


def _content_lexile(job):
    """Return the Lexile level for generated content (15% below target)."""
    return int(job.target_lexile * LEXILE_OFFSET)


def _log_step(job, step, status, duration=None, input_data=None,
              output_data=None, error_message=''):
    """Create a GenerationJobLog entry for a pipeline step."""
    return GenerationJobLog.objects.create(
        job=job,
        step=step,
        status=status,
        duration_seconds=duration,
        input_data=input_data,
        output_data=output_data,
        error_message=error_message,
    )


def _prompt_hash(prompt_text):
    return hashlib.sha256((prompt_text or '').encode('utf-8')).hexdigest()[:12]


def _log_metadata(model=None, prompt_template=None, prompt_text=None, **extra):
    data = {
        key: value
        for key, value in {
            'model': model,
            'prompt_template': prompt_template,
            'prompt_hash': _prompt_hash(prompt_text) if prompt_text else None,
        }.items()
        if value not in (None, '')
    }
    data.update({key: value for key, value in extra.items() if value is not None})
    return data


def _close_old_connections_if_safe():
    if not connection.in_atomic_block:
        close_old_connections()


def _call_gemini_releasing_db(model, system_prompt, user_prompt):
    """Do not hold a MySQL connection open while waiting on a slow LLM call."""
    _close_old_connections_if_safe()
    try:
        return _llm_service.call_gemini(model, system_prompt, user_prompt)
    finally:
        _close_old_connections_if_safe()


def _call_anthropic_releasing_db(model, system_prompt, user_prompt):
    """Do not hold a MySQL connection open while waiting on a slow LLM call."""
    _close_old_connections_if_safe()
    try:
        return _llm_service.call_anthropic(model, system_prompt, user_prompt)
    finally:
        _close_old_connections_if_safe()


def _call_llm_releasing_db(model, system_prompt, user_prompt):
    """Route to the correct LLM backend based on model name."""
    if 'claude' in model or 'sonnet' in model or 'opus' in model or 'haiku' in model:
        return _call_anthropic_releasing_db(model, system_prompt, user_prompt)
    return _call_gemini_releasing_db(model, system_prompt, user_prompt)


def _call_llm_with_config(site_config: dict, system_prompt: str, user_prompt: str):
    """Route to the correct LLM backend based on site configuration dict.

    site_config keys: model, provider_type, base_url, api_key
    """
    _close_old_connections_if_safe()
    try:
        model = site_config['model']
        provider = site_config['provider_type']
        api_key = site_config.get('api_key') or None
        base_url = site_config.get('base_url') or None

        if provider == 'anthropic':
            return _llm_service.call_anthropic(
                model, system_prompt, user_prompt,
                api_key=api_key, base_url=base_url,
            )
        elif provider == 'openai_compatible':
            return _llm_service.call_gemini(
                model, system_prompt, user_prompt,
                api_key=api_key, base_url=base_url,
            )
        else:  # gemini_native
            return _llm_service.call_gemini(
                model, system_prompt, user_prompt,
                api_key=api_key, base_url=base_url,
            )
    finally:
        _close_old_connections_if_safe()


def _call_openai_image_releasing_db(prompt, size="1024x1024", reference_image=None):
    """Do not hold a MySQL connection open while waiting on image generation."""
    _close_old_connections_if_safe()
    try:
        return _llm_service.call_openai_image(prompt, size=size, reference_image=reference_image)
    finally:
        _close_old_connections_if_safe()


