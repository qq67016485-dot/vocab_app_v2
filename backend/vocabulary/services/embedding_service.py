"""
Embedding service for semantic deduplication of word definitions.
Uses SiliconFlow API with Qwen3-Embedding-8B.

Provides:
- get_embedding(text) — Calls embedding API, returns vector (list of floats)
- cosine_similarity(vec_a, vec_b) — Compute cosine similarity between two vectors
- find_duplicate_definition(word_text, pos, definition_text) — Full dedup check
"""
import math
import logging
import time

import requests

from django.conf import settings

from vocabulary.models import Word, DefinitionEmbedding

logger = logging.getLogger(__name__)

# Pause before the single retry of a transient embedding API failure.
RETRY_BACKOFF_SECONDS = 2


def _call_embedding_api(text):
    """Call the SiliconFlow embedding API and return the raw vector.

    Retries once after a short backoff on transient failures (429, 5xx,
    connection/timeout); a 4xx or other hard failure raises immediately.
    """
    for attempt in (0, 1):
        try:
            response = requests.post(
                settings.QWEN_BASE_URL,
                headers={
                    "Authorization": f"Bearer {settings.QWEN_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.QWEN_EMBEDDING_MODEL,
                    "input": text,
                    "encoding_format": "float",
                    "dimensions": settings.QWEN_EMBEDDING_DIMENSIONS,
                },
                timeout=30,
            )
            response.raise_for_status()
            break
        except requests.RequestException as exc:
            status = getattr(exc.response, 'status_code', None)
            transient = (
                isinstance(exc, (requests.ConnectionError, requests.Timeout))
                or status == 429
                or (status is not None and status >= 500)
            )
            if attempt == 1 or not transient:
                raise
            logger.warning(
                "Embedding API transient failure (%s); retrying in %ss",
                exc, RETRY_BACKOFF_SECONDS,
            )
            time.sleep(RETRY_BACKOFF_SECONDS)
    try:
        data = response.json()
        return data["data"][0]["embedding"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"Malformed embedding API response: {exc}") from exc


def get_embedding(text):
    """
    Generate a vector embedding for the given text via Qwen3
    (settings.QWEN_EMBEDDING_MODEL, default Qwen/Qwen3-Embedding-8B).

    Returns:
        list[float]: The embedding vector.
    """
    return _call_embedding_api(text)


def cosine_similarity(vec_a, vec_b):
    """
    Compute cosine similarity between two vectors.

    Returns:
        float: Similarity score between -1.0 and 1.0.
    """
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    magnitude_a = math.sqrt(sum(a * a for a in vec_a))
    magnitude_b = math.sqrt(sum(b * b for b in vec_b))

    if magnitude_a == 0 or magnitude_b == 0:
        return 0.0

    return dot_product / (magnitude_a * magnitude_b)


def find_duplicate_definition(word_text, pos, definition_text):
    """
    Check if a word definition already exists using vector similarity.

    Looks for existing Word records with the same text + POS, then compares
    definition embeddings using cosine similarity. Returns the best-matching
    definition (not just the word) so callers snapshot the definition that
    actually matched — a word can carry several definitions at different
    Lexile levels, and picking any other one attaches the wrong definition,
    example sentence, and Lexile score to the job.

    Args:
        word_text: The word text (e.g., "bright")
        pos: Part of speech (e.g., "adjective")
        definition_text: The incoming definition to check

    Returns:
        WordDefinition | None: The most similar existing definition at or
        above the similarity threshold (its .word is the deduplicated Word),
        else None.
    """
    existing_words = Word.objects.filter(text=word_text, part_of_speech=pos)
    if not existing_words.exists():
        return None

    incoming_embedding = get_embedding(definition_text)
    threshold = settings.EMBEDDING_SIMILARITY_THRESHOLD

    best_defn = None
    best_similarity = None
    for word in existing_words:
        for defn in word.definitions.all():
            try:
                stored_embedding = defn.embedding.embedding
            except DefinitionEmbedding.DoesNotExist:
                continue

            similarity = cosine_similarity(incoming_embedding, stored_embedding)
            if similarity >= threshold and (
                best_similarity is None or similarity > best_similarity
            ):
                best_similarity = similarity
                best_defn = defn

    if best_defn is not None:
        logger.info(
            "Duplicate found: '%s' (%s) — definition id=%s similarity %.4f >= %.4f",
            word_text, pos, best_defn.id, best_similarity, threshold,
        )
    return best_defn
