"""
Low-level LLM wrapper service.

Provides:
- call_anthropic(model, system_prompt, user_prompt) — Call Claude, return parsed JSON
- call_gemini_image(prompt) — Call Gemini image generation, return raw image bytes
- load_prompt_template(name) — Load a .txt prompt template from vocabulary/prompts/
"""
import json
import os
import re
import base64
import logging

import anthropic
from google import genai
from google.genai import types
from django.conf import settings

logger = logging.getLogger(__name__)

PROMPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'prompts',
)


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

    Args:
        model: Model name (e.g., 'claude-sonnet-4-20250514')
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

    message = client.messages.create(
        model=model,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    raw = message.content[0].text
    logger.debug("Raw response (first 2000 chars):\n%s", raw[:2000])

    return _extract_json(raw)


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


def call_gemini_image(prompt):
    """
    Generate an image using the Gemini API.

    Args:
        prompt: Text prompt describing the image to generate.

    Returns:
        bytes: Raw image bytes (PNG).
    """
    client_kwargs = {'api_key': settings.GEMINI_API_KEY}
    if settings.GEMINI_BASE_URL:
        client_kwargs['http_options'] = types.HttpOptions(base_url=settings.GEMINI_BASE_URL)
    client = genai.Client(**client_kwargs)

    logger.info("Generating image via Gemini")
    logger.debug("Image prompt: %s", prompt)

    response = client.models.generate_content(
        model="gemini-2.5-flash-image",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
        ),
    )

    image_part = response.candidates[0].content.parts[0]
    image_data = image_part.inline_data.data

    if isinstance(image_data, bytes):
        return image_data
    return base64.b64decode(image_data)
