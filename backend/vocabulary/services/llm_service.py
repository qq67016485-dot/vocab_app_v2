"""
Low-level LLM wrapper service.

Provides:
- call_anthropic(model, system_prompt, user_prompt) — Call Claude, return parsed JSON
- call_gemini(model, system_prompt, user_prompt) — Call Gemini, return parsed JSON
- call_openai_image(prompt) — Call OpenAI GPT-Image-2, return raw image bytes
- load_prompt_template(name) — Load a .txt prompt template from vocabulary/prompts/
"""
import json
import os
import re
import base64
import logging
from datetime import datetime

import anthropic
from google import genai
from google.genai import types
from django.conf import settings

logger = logging.getLogger(__name__)

PROMPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'prompts',
)

# Directory for LLM call logs
LLM_LOG_DIR = os.path.join(settings.BASE_DIR, '..', 'temp', 'llm_logs')


def _log_llm_call(label, system_prompt, user_prompt, raw_response, error=None):
    """Write the full input/output of an LLM call to a timestamped log file."""
    try:
        os.makedirs(LLM_LOG_DIR, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        status = 'ERROR' if error else 'OK'
        filename = f'{ts}_{label}_{status}.txt'
        filepath = os.path.join(LLM_LOG_DIR, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f'=== LLM CALL LOG ===\n')
            f.write(f'Timestamp: {ts}\n')
            f.write(f'Label: {label}\n')
            f.write(f'Status: {status}\n')
            if error:
                f.write(f'Error: {error}\n')
            f.write(f'\n=== SYSTEM PROMPT ===\n')
            f.write(system_prompt or '(empty)')
            f.write(f'\n\n=== USER PROMPT ===\n')
            f.write(user_prompt or '(empty)')
            f.write(f'\n\n=== RAW RESPONSE ===\n')
            f.write(raw_response or '(empty)')
            f.write('\n')
        logger.info("LLM call logged to %s", filepath)
    except Exception as e:
        logger.warning("Failed to write LLM log: %s", e)


def load_prompt_template(name):
    """
    Load a prompt template file from vocabulary/prompts/{name}.txt.

    Args:
        name: Template name without .txt extension.

    Returns:
        str: The template content with {variable} placeholders.

    Raises:
        FileNotFoundError: If the template file doesn't exist.
    """
    filepath = os.path.join(PROMPTS_DIR, f'{name}.txt')
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()


def call_anthropic(model, system_prompt, user_prompt):
    """
    Call the Anthropic API and return parsed JSON from the response.

    Handles markdown code fences and embedded JSON extraction.
    Supports both standard and thinking models (e.g., claude-opus-4-6-thinking).

    Args:
        model: Model name.
        system_prompt: System prompt string.
        user_prompt: User prompt string.

    Returns:
        dict: Parsed JSON from the LLM response.

    Raises:
        ValueError: If JSON cannot be extracted from the response.
    """
    kwargs = {'api_key': settings.ANTHROPIC_API_KEY}
    if settings.ANTHROPIC_BASE_URL:
        kwargs['base_url'] = settings.ANTHROPIC_BASE_URL
    client = anthropic.Anthropic(**kwargs)

    logger.info("Calling Anthropic model=%s", model)
    logger.debug("User prompt:\n%s", user_prompt)

    is_thinking_model = 'thinking' in model

    create_kwargs = {
        'model': model,
        'max_tokens': 128000 if is_thinking_model else 600000,
        'messages': [{"role": "user", "content": f"{system_prompt}\n\n{user_prompt}"}],
    }

    if is_thinking_model:
        create_kwargs['thinking'] = {
            'type': 'enabled',
            'budget_tokens': 12000,
        }
    else:
        create_kwargs['system'] = system_prompt
        create_kwargs['messages'] = [{"role": "user", "content": user_prompt}]

    # Use streaming to avoid timeout on long-running requests
    raw = ''
    with client.messages.stream(**create_kwargs) as stream:
        for event in stream:
            pass
        message = stream.get_final_message()

    # Extract text from response — thinking models return thinking + text blocks
    for block in message.content:
        if block.type == 'text':
            raw = block.text
            break

    logger.debug("Raw response (first 2000 chars):\n%s", raw[:2000])

    try:
        parsed = _extract_json(raw)
        _log_llm_call(model, system_prompt, user_prompt, raw)
        return parsed
    except ValueError as e:
        _log_llm_call(model, system_prompt, user_prompt, raw, error=str(e))
        raise


def _extract_json(raw):
    """Extract JSON from LLM response text, handling code fences and surrounding text."""
    stripped = raw.strip()

    # Strip markdown code fences
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        lines = lines[1:]  # remove opening fence line
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()

    # Try direct parse
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in the text
    match = re.search(r'\{[\s\S]*\}', stripped)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(
        f"Could not parse JSON from LLM response. Raw (first 500 chars): {raw[:500]}"
    )


def call_gemini(model, system_prompt, user_prompt):
    """
    Call the Gemini API and return parsed JSON from the response.

    Args:
        model: Model name (e.g., 'gemini-3.1-pro-preview').
        system_prompt: System instruction string.
        user_prompt: User prompt string.

    Returns:
        dict: Parsed JSON from the LLM response.

    Raises:
        ValueError: If JSON cannot be extracted from the response.
    """
    client_kwargs = {'api_key': settings.GEMINI_API_KEY}
    if settings.GEMINI_BASE_URL:
        client_kwargs['http_options'] = types.HttpOptions(base_url=settings.GEMINI_BASE_URL)
    client = genai.Client(**client_kwargs)

    logger.info("Calling Gemini model=%s", model)
    logger.debug("User prompt:\n%s", user_prompt)

    # Combine system and user prompts into contents (Gemini requires non-empty contents)
    combined_prompt = f"{system_prompt}\n\n{user_prompt}".strip()

    config = types.GenerateContentConfig(
        response_mime_type='application/json',
    )

    response = client.models.generate_content(
        model=model,
        contents=combined_prompt,
        config=config,
    )

    raw = response.text or ''
    logger.debug("Raw response (first 2000 chars):\n%s", raw[:2000])

    try:
        parsed = _extract_json(raw)
        _log_llm_call(model, system_prompt, user_prompt, raw)
        return parsed
    except ValueError as e:
        _log_llm_call(model, system_prompt, user_prompt, raw, error=str(e))
        raise


def call_openai_image(prompt: str, size: str = "1024x1024", reference_image: bytes | None = None) -> bytes:
    """
    Generate an image using OpenAI's GPT-Image-2 model.

    Args:
        prompt: Text prompt describing the image to generate.
        size: Image dimensions requested from the API.
        reference_image: Optional PNG bytes of a previous page to use as
            a style/continuity reference via the images.edit endpoint.

    Returns:
        bytes: Raw image bytes (PNG).
    """
    import openai

    model = "gpt-image-2"
    api_key = settings.OPENAI_API_KEY
    client_kwargs = {'api_key': api_key}
    if settings.OPENAI_BASE_URL:
        client_kwargs['base_url'] = settings.OPENAI_BASE_URL
    client = openai.OpenAI(**client_kwargs)

    logger.info("Generating image via OpenAI %s (reference=%s)", model, bool(reference_image))
    logger.debug("Image prompt: %s", prompt)

    try:
        if reference_image:
            response = client.images.edit(
                model=model,
                image=reference_image,
                prompt=prompt,
                n=1,
                size=size,
            )
        else:
            response = client.images.generate(
                model=model,
                prompt=prompt,
                n=1,
                size=size,
            )

        image_item = response.data[0]
        if image_item.b64_json:
            image_bytes = base64.b64decode(image_item.b64_json)
            _log_llm_call(
                f'{model}_image',
                'OpenAI image generation',
                prompt,
                f'Image generated successfully from b64_json ({len(image_bytes)} bytes).',
            )
            return image_bytes

        import httpx
        img_response = httpx.get(image_item.url, follow_redirects=True, timeout=60)
        img_response.raise_for_status()
        _log_llm_call(
            f'{model}_image',
            'OpenAI image generation',
            prompt,
            f'Image generated successfully from URL: {image_item.url}',
        )
        return img_response.content
    except Exception as e:
        _log_llm_call(
            f'{model}_image',
            'OpenAI image generation',
            prompt,
            '',
            error=str(e),
        )
        raise
