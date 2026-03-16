"""Test harness helpers.

This repo has a few optional heavy/runtime dependencies (e.g. psycopg2, transformers).
In lightweight dev environments, we still want unit tests that don't require them
to be importable/collectable.
"""

from __future__ import annotations

import contextlib
import builtins
import os
import sys
import types
from typing import Any

import httpx

# ---------------------------------------------------------------------------
# 1) 仓库根路径注入 -- 所有 test 文件不再自己维护 ROOT_DIR / sys.path
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

os.environ.setdefault("SKIP_DB_INIT", "1")


def _install_psycopg2_stub() -> None:
    """Install a minimal psycopg2 stub so modules can be imported.

    Unit tests patch DB access (_connect) anyway, so a stub is enough to avoid
    import-time failures.
    """

    try:
        import psycopg2  # noqa: F401

        # Some environments may have a partial/broken psycopg2 module (or a
        # name collision) that lacks `extensions`, which our code references in
        # type annotations. In that case, fall back to a stub as well.
        if getattr(psycopg2, "extensions", None) is not None:
            return
    except ModuleNotFoundError:
        pass

    psycopg2 = types.ModuleType("psycopg2")

    extensions = types.ModuleType("psycopg2.extensions")

    class connection:  # pragma: no cover
        pass

    extensions.connection = connection  # type: ignore[attr-defined]

    def connect(*_args: Any, **_kwargs: Any):
        raise RuntimeError(
            "psycopg2 is not installed; tests must patch DB access (_connect)."
        )

    psycopg2.connect = connect  # type: ignore[attr-defined]

    extras = types.ModuleType("psycopg2.extras")

    class RealDictCursor:  # pragma: no cover
        pass

    extras.RealDictCursor = RealDictCursor  # type: ignore[attr-defined]

    psycopg2.extras = extras  # type: ignore[attr-defined]
    psycopg2.extensions = extensions  # type: ignore[attr-defined]

    # If a broken/partial psycopg2 is already imported, override it.
    sys.modules["psycopg2"] = psycopg2
    sys.modules["psycopg2.extras"] = extras
    sys.modules["psycopg2.extensions"] = extensions


_install_psycopg2_stub()


def _transformers_import_ok() -> bool:
    try:
        import transformers  # noqa: F401

        return True
    except Exception:
        # Version mismatch errors also land here.
        return False


_HAS_TRANSFORMERS = _transformers_import_ok()


def pytest_ignore_collect(collection_path, config):  # type: ignore[no-untyped-def]
    """Skip inference-heavy tests when transformers isn't usable.

    Tests are organized by functional domain in subdirectories:
    - analysis/: Analysis pipeline tests
    - requirements/: Requirements processing tests
    - inference/: Inference backend tests (many require transformers)
    - auth/: Authentication & authorization tests
    - agents/: Agent-related tests
    - management/: Project/product management tests
    - mobile/: Mobile-specific tests
    - fixtures/: Test data files and utility scripts
    """

    basename = None
    if hasattr(collection_path, "basename"):
        basename = getattr(collection_path, "basename")
        if callable(basename):
            basename = basename()
    if basename is None and hasattr(collection_path, "name"):
        basename = getattr(collection_path, "name")
    basename = str(basename)

    # Some tests require optional modules that may not exist in this checkout.
    optional_modules_by_test = {
        "test_api_provider.py": ["core.config"],
        "test_asr_service_decode_helpers.py": ["backend_inference_ASR"],
        "test_fastapi_asr_asr_contract.py": ["backend_inference_ASR"],
        "test_fastapi_asr_contract.py": ["backend_inference.routers.asr"],
    }
    if basename in optional_modules_by_test:
        import importlib

        for module_name in optional_modules_by_test[basename]:
            try:
                importlib.import_module(module_name)
            except (ImportError, ModuleNotFoundError):
                return True

    # These tests pull in backend_inference local HF engine (now in tests/inference/).
    if basename in {
        "test_tool_calls.py",
        "test_async_engine.py",
        "test_api_provider.py",
        "test_conflict.py",
        "test_traceability.py",
        "test_deepseek_thinking_tools.py",  # Also requires transformers
        "test_asr_service_decode_helpers.py",  # Requires backend_inference_ASR
    }:
        if not _HAS_TRANSFORMERS:
            return True

    # Also skip the ad-hoc postgres script test when psycopg2 isn't available.
    # This is now in tests/fixtures/test_postgres.py
    if basename == "test_postgres.py":
        return True

    return False


# ---------------------------------------------------------------------------
# 2) 统一 FastAPI async test helper
# ---------------------------------------------------------------------------

def build_test_app(
    *routers,
    dependency_overrides: dict[Any, Any] | None = None,
    include_error_handlers: bool = True,
):
    """Create a lightweight FastAPI app wired with the given router(s)."""
    from fastapi import FastAPI, HTTPException
    from fastapi.exceptions import RequestValidationError

    from backend_business.api.http.errors import (
        error_response_handler,
        validation_error_handler,
    )

    app = FastAPI()
    for router in routers:
        app.include_router(router)

    if dependency_overrides:
        for dep, override in dependency_overrides.items():
            app.dependency_overrides[dep] = override

    if include_error_handlers:
        app.add_exception_handler(RequestValidationError, validation_error_handler)
        app.add_exception_handler(HTTPException, error_response_handler)
        app.add_exception_handler(Exception, error_response_handler)

    return app


@contextlib.asynccontextmanager
async def async_client(app):
    """Yield an ``httpx.AsyncClient`` bound to the ASGI *app*."""
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# Make helpers available to all tests without per-file imports.
builtins.build_test_app = build_test_app  # type: ignore[attr-defined]
builtins.async_client = async_client  # type: ignore[attr-defined]
