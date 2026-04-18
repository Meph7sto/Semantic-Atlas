"""Filesystem-backed skill storage primitives."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import shutil

from backend_business.config import settings


class SkillStore:
    """Read/write helper for `.agent_skills/<target>/current.md` files."""

    CURRENT_FILENAME = "current.md"

    def __init__(self, root_path: str | Path | None = None) -> None:
        self.root_path = Path(root_path or settings.AGENT_EXPERIENCE_ROOT)

    def ensure_root(self) -> Path:
        self.root_path.mkdir(parents=True, exist_ok=True)
        return self.root_path

    def ensure_target(self, target_id: str) -> Path:
        target_dir = self.ensure_root() / str(target_id).strip()
        target_dir.mkdir(parents=True, exist_ok=True)
        self.build_archive_dir(target_id).mkdir(parents=True, exist_ok=True)
        return target_dir

    def ensure_targets(self, target_ids: list[str] | tuple[str, ...]) -> list[Path]:
        return [self.ensure_target(target_id) for target_id in target_ids]

    def build_current_path(self, target_id: str) -> Path:
        return self.ensure_target(target_id) / self.CURRENT_FILENAME

    def build_archive_dir(self, target_id: str) -> Path:
        return (self.ensure_root() / str(target_id).strip() / "archive")

    def read_current(self, target_id: str) -> str | None:
        current_path = self.build_current_path(target_id)
        if not current_path.exists():
            return None
        return current_path.read_text(encoding="utf-8")

    def write_current(
        self,
        target_id: str,
        content: str,
        *,
        archive_existing: bool = True,
        archived_at: datetime | None = None,
    ) -> Path:
        current_path = self.build_current_path(target_id)
        if archive_existing and current_path.exists():
            self.archive_current(target_id, archived_at=archived_at)
        current_path.write_text(content, encoding="utf-8")
        return current_path

    def archive_current(
        self,
        target_id: str,
        *,
        archived_at: datetime | None = None,
    ) -> Path | None:
        current_path = self.build_current_path(target_id)
        if not current_path.exists():
            return None

        archive_dir = self.build_archive_dir(target_id)
        base_name = _format_timestamp(archived_at)
        archive_path = archive_dir / f"{base_name}.md"
        suffix = 1
        while archive_path.exists():
            archive_path = archive_dir / f"{base_name}_{suffix}.md"
            suffix += 1
        shutil.copy2(current_path, archive_path)
        return archive_path

    def list_archives(self, target_id: str) -> list[Path]:
        archive_dir = self.build_archive_dir(target_id)
        return sorted(
            path for path in archive_dir.glob("*.md") if path.is_file()
        )

    def restore_archive(
        self,
        target_id: str,
        *,
        archive_name: str | None = None,
        archive_path: str | Path | None = None,
        archived_at: datetime | None = None,
    ) -> Path:
        current_path = self.build_current_path(target_id)
        resolved_archive_path = self._resolve_archive_path(
            target_id=target_id,
            archive_name=archive_name,
            archive_path=archive_path,
        )
        if resolved_archive_path is None or not resolved_archive_path.exists():
            raise FileNotFoundError(f"archive not found for target '{target_id}'")
        if current_path.exists():
            self.archive_current(target_id, archived_at=archived_at)
        shutil.copy2(resolved_archive_path, current_path)
        return current_path

    def _resolve_archive_path(
        self,
        *,
        target_id: str,
        archive_name: str | None,
        archive_path: str | Path | None,
    ) -> Path | None:
        if archive_path is not None:
            return Path(archive_path)
        archives = self.list_archives(target_id)
        if archive_name:
            for candidate in archives:
                if candidate.name == archive_name:
                    return candidate
            return None
        if not archives:
            return None
        return archives[-1]


def _format_timestamp(value: datetime | None) -> str:
    timestamp = value or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    else:
        timestamp = timestamp.astimezone(timezone.utc)
    return timestamp.strftime("%Y%m%dT%H%M%SZ")
