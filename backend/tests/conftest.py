"""Shared pytest fixtures for the backend test suite."""
import os

import pytest
from django.conf import settings as django_settings
from django.core.cache import cache
from django.core.files.storage import default_storage
from django.utils.functional import empty


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


@pytest.fixture(autouse=True)
def isolated_generation_artifacts(tmp_path, monkeypatch):
    """Redirect GN/infographic substep artifacts to a per-test tmp dir.

    ``_graphic_novel_artifact_dir`` (graphic_novel_helpers.py) and
    ``_infographic_artifact_dir`` (step_infographic.py) both resolve the shared
    repo-level ``temp/generation_artifacts/`` from ``settings.BASE_DIR`` at call
    time, and every artifact read/write goes through one of them as a module
    global — so patching these two functions is the single seam that covers
    script substeps, restarts, and resume checks. Without this, pipeline tests
    overwrite the real artifacts of any job whose id they reuse (job_1's real
    artifacts were destroyed by fixture content this way).

    The wrapper re-roots the original function's return value under tmp_path
    instead of reimplementing the path layout, so slug/naming changes in the
    real code cannot silently desync the test redirect.
    """
    from vocabulary.services.generation import (
        graphic_novel_helpers,
        step_infographic,
    )

    real_root = os.path.abspath(os.path.join(
        django_settings.BASE_DIR, '..', 'temp', 'generation_artifacts',
    ))
    tmp_root = str(tmp_path / 'generation_artifacts')

    def _reroot(fn):
        def wrapper(*args, **kwargs):
            path = fn(*args, **kwargs)
            rel = os.path.relpath(path, real_root)
            if rel.startswith('..'):  # defensive: outside the artifact root
                return path
            return os.path.join(tmp_root, rel)
        return wrapper

    monkeypatch.setattr(
        graphic_novel_helpers, '_graphic_novel_artifact_dir',
        _reroot(graphic_novel_helpers._graphic_novel_artifact_dir),
    )
    monkeypatch.setattr(
        step_infographic, '_infographic_artifact_dir',
        _reroot(step_infographic._infographic_artifact_dir),
    )


@pytest.fixture(autouse=True)
def isolated_media_root(settings, tmp_path):
    """Point MEDIA_ROOT at a per-test tmp dir for every test.

    Media-writing tests (JPEG companions, GN page images, audiobook WAV/MP3)
    save through Django's default FileSystemStorage, which used to land them
    in the real ``backend/media/`` alongside persistent content. Django reads
    ``settings.MEDIA_ROOT`` lazily, but the storage instance caches it
    (``FileSystemStorage.base_location``/``location`` are cached properties),
    so the cached ``default_storage`` wrapper is reset too — otherwise
    whichever test first touched the storage would pin MEDIA_ROOT for the
    rest of the process.
    """
    settings.MEDIA_ROOT = str(tmp_path / 'media')
    default_storage._wrapped = empty
    yield
    default_storage._wrapped = empty


@pytest.fixture(autouse=True)
def isolated_llm_log_dir(tmp_path, monkeypatch):
    """Redirect LLM call logs to a per-test tmp dir.

    ``llm_service._log_llm_call`` writes to the module constant
    ``LLM_LOG_DIR`` (repo-level ``temp/llm_logs/``). Tests that exercise
    ``call_gemini``/``call_openai_image`` with mocked API clients run the real
    logging path and would otherwise scatter fixture logs there.
    """
    from vocabulary.services import llm_service

    monkeypatch.setattr(
        llm_service, 'LLM_LOG_DIR', str(tmp_path / 'llm_logs'),
    )
