"""Guardrails for FastAPI contract tests."""

from __future__ import annotations

from pathlib import Path
import re


_TESTS_DIR = Path(__file__).resolve().parent
_FASTAPI_CONTRACT_FILES = sorted(_TESTS_DIR.rglob("test_fastapi_*.py"))


def _find_offenders(pattern: str) -> list[str]:
    regex = re.compile(pattern)
    offenders: list[str] = []
    for path in _FASTAPI_CONTRACT_FILES:
        if regex.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path))
    return offenders


def _format_error(title: str, offenders: list[str]) -> str:
    lines = [title, *offenders]
    return "\n".join(lines)


def test_fastapi_contracts_do_not_use_testclient() -> None:
    offenders = _find_offenders(r"\bTestClient\b")
    assert not offenders, _format_error(
        "test_fastapi_*.py must not use TestClient:", offenders
    )


def test_fastapi_contracts_do_not_use_file_level_sys_path_hacks() -> None:
    offenders = _find_offenders(r"\bROOT_DIR\b|sys\.path\.insert\s*\(")
    assert not offenders, _format_error(
        "test_fastapi_*.py must not define ROOT_DIR/sys.path.insert(...):", offenders
    )


def test_fastapi_contracts_do_not_construct_raw_async_client() -> None:
    offenders = _find_offenders(
        r"httpx\.AsyncClient\(transport\s*=\s*httpx\.ASGITransport\("
    )
    assert not offenders, _format_error(
        "test_fastapi_*.py must use shared async_client(...) helper:", offenders
    )
