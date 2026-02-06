"""Test harness helpers.

This repo has a few optional heavy/runtime dependencies (e.g. psycopg2, transformers).
In lightweight dev environments, we still want unit tests that don't require them
to be importable/collectable.
"""

from __future__ import annotations

import sys
import types
from typing import Any


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
    """Skip inference-heavy tests when transformers isn't usable."""

    if _HAS_TRANSFORMERS:
        return False

    basename = None
    if hasattr(path, "basename"):
        basename = getattr(path, "basename")
        if callable(basename):
            basename = basename()
    if basename is None and hasattr(path, "name"):
        basename = getattr(path, "name")

    # These tests pull in backend_inference local HF engine.
    if str(basename) in {
        "test_tool_calls.py",
        "test_async_engine.py",
        "test_api_provider.py",
        "test_conflict.py",
        "test_traceability.py",
    }:
        return True

    # Also skip the ad-hoc postgres script test when psycopg2 isn't available.
    if str(basename) == "test_postgres.py":
        return True

    return False
