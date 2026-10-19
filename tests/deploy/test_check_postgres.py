import os
from pathlib import Path
from unittest.mock import MagicMock, patch

# Loading application settings must not leak .env values into other tests.
with patch.dict(os.environ):
    from deploy import check_postgres


def test_check_connects_with_timeout_and_closes(monkeypatch):
    connect = MagicMock()
    monkeypatch.setattr(check_postgres.psycopg2, "connect", connect)
    assert check_postgres.main() == 0
    connect.assert_called_once_with(check_postgres.settings.POSTGRES_DSN, connect_timeout=5)
    cursor = connect.return_value.cursor.return_value.__enter__.return_value
    cursor.execute.assert_called_once_with("SELECT 1")
    connect.return_value.close.assert_called_once()


def test_connection_failure_returns_nonzero_without_password(monkeypatch, capsys):
    connect = MagicMock(side_effect=check_postgres.psycopg2.OperationalError("secret"))
    monkeypatch.setattr(check_postgres.psycopg2, "connect", connect)
    assert check_postgres.main() == 1
    output = capsys.readouterr()
    assert "PostgreSQL" in output.err
    assert "secret" not in output.err


def test_query_failure_closes_connection(monkeypatch):
    connect = MagicMock()
    cursor = connect.return_value.cursor.return_value.__enter__.return_value
    cursor.execute.side_effect = check_postgres.psycopg2.OperationalError("disconnected")
    monkeypatch.setattr(check_postgres.psycopg2, "connect", connect)
    assert check_postgres.main() == 1
    connect.return_value.close.assert_called_once()


def test_windows_launcher_requires_existing_readiness_script():
    root = Path(__file__).resolve().parents[2]
    launcher = (root / "deploy/start.ps1").read_text(encoding="utf-8-sig")
    assert 'Join-Path $BASE_DIR "deploy/check_postgres.py"' in launcher
    assert (root / "deploy/check_postgres.py").is_file()
    assert 'throw "[start] PostgreSQL readiness script not found:' in launcher
