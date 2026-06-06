"""LLM step configuration service with caching."""
import logging
from typing import Any

from django.core.cache import cache

logger = logging.getLogger(__name__)

CACHE_KEY = 'llm_step_configs_all'
CACHE_TTL = 300  # 5 minutes


class LLMConfigError(Exception):
    pass


def get_step_config(step_key: str) -> dict[str, Any]:
    """Return primary and fallback site configs for a pipeline step, read from
    the currently active config set.

    Returns:
        {
            'primary': {'model': ..., 'provider_type': ..., 'base_url': ..., 'api_key': ...},
            'fallback': {'model': ..., 'provider_type': ..., 'base_url': ..., 'api_key': ...},
        }

    Raises:
        LLMConfigError: If no active set exists or it has no config for the step.
    """
    configs = _get_all_configs()
    if step_key not in configs:
        raise LLMConfigError(
            f"No LLM configuration found for step '{step_key}' in the active set. "
            f"Configure it in the admin LLM Config page."
        )
    return configs[step_key]


def get_active_set():
    """Return the active LLMConfigSet, or None if somehow none is active."""
    from vocabulary.models import LLMConfigSet
    return (
        LLMConfigSet.objects.filter(is_active=True).order_by('position').first()
        or LLMConfigSet.objects.order_by('position').first()
    )


def invalidate_cache() -> None:
    cache.delete(CACHE_KEY)


def _get_all_configs() -> dict[str, dict]:
    configs = cache.get(CACHE_KEY)
    if configs is not None:
        return configs
    configs = _load_from_db()
    cache.set(CACHE_KEY, configs, CACHE_TTL)
    return configs


def _load_from_db() -> dict[str, dict]:
    from vocabulary.models import LLMStepConfig

    active = get_active_set()
    if active is None:
        raise LLMConfigError(
            "No active LLM config set found. Activate one in the admin LLM Config page."
        )

    configs = {}
    qs = (
        LLMStepConfig.objects
        .filter(config_set=active)
        .select_related('primary_site', 'fallback_site')
    )
    for row in qs:
        configs[row.step_key] = {
            'primary': _site_to_dict(row.primary_site, row.primary_model),
            'fallback': _site_to_dict(row.fallback_site, row.fallback_model),
        }
    return configs


def _site_to_dict(site, model: str) -> dict[str, Any]:
    return {
        'model': model,
        'provider_type': site.provider_type,
        'base_url': site.base_url or '',
        'api_key': site.resolve_api_key(),
    }
