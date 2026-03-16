"""CI guard: prevent TestClient and file-level sys.path hacks from creeping back."""

import pathlib
import re

_TESTS_DIR = pathlib.Path(__file__).parent


def _collect_fastapi_contract_files():
    return sorted(_TESTS_DIR.rglob("test_fastapi_*.py"))


def test_no_testclient_in_contract_tests():
    violations = []
    for path in _collect_fastapi_contract_files():
        text = path.read_text(encoding="utf-8")
        if "TestClient" in text:
            violations.append(str(path.relative_to(_TESTS_DIR)))
    assert violations == [], (
        f"TestClient found in contract test files (use httpx.AsyncClient instead): {violations}"
    )


def test_no_root_dir_or_sys_path_in_contract_tests():
    pattern = re.compile(r"ROOT_DIR|sys\.path\.insert")
    violations = []
    for path in _collect_fastapi_contract_files():
        text = path.read_text(encoding="utf-8")
        if pattern.search(text):
            violations.append(str(path.relative_to(_TESTS_DIR)))
    assert violations == [], (
        f"ROOT_DIR / sys.path.insert found in contract test files "
        f"(use tests/conftest.py instead): {violations}"
    )
