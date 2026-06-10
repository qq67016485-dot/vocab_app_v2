"""Shared pytest fixtures for the backend test suite."""
import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def clear_caches():
    """Reset Django's cache around every test.

    The project has no CACHES setting, so Django falls back to the in-process
    LocMemCache. Unlike the database (rolled back per test by pytest-django),
    that cache is process-global and persists across tests. Services that cache
    DB-derived state — notably ``llm_config_service`` (key ``llm_step_configs_all``,
    5-min TTL) — would otherwise leak one test's seeded config into the next,
    so a test that seeds ``model-3-primary`` poisons a later test that expects
    the migration-seeded default model. Clearing before and after isolates them.
    """
    cache.clear()
    yield
    cache.clear()
