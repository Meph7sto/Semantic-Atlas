# PostgreSQL 增删改查逻辑占位符
# 此模块将来用于处理所有与 PostgreSQL 数据库交互的操作
import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from backend_business.config import settings


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


class DBService:
    """
    轻量级 SQLite 存储：
    - 保存追溯分析（单对、批量）的输入与输出 JSON
    - 提供列表/详情/统计
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trace_analysis (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    analysis_type TEXT NOT NULL,              -- relation | batch
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    input_json TEXT NOT NULL,
                    output_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_trace_created_at ON trace_analysis(created_at)")
            conn.commit()

    def save_relation(
        self,
        high_level_requirement: str,
        low_level_requirement: str,
        output: Dict[str, Any],
        title: Optional[str] = None,
    ) -> int:
        input_payload = {
            "high_level_requirement": high_level_requirement,
            "low_level_requirement": low_level_requirement,
        }
        if title is None:
            title = output.get("summary") or "关系追溯分析"

        desc = f"顶层需求: {high_level_requirement}\n\n底层需求: {low_level_requirement}"

        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO trace_analysis(analysis_type, title, description, input_json, output_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "relation",
                    str(title)[:200],
                    desc,
                    json.dumps(input_payload, ensure_ascii=False),
                    json.dumps(output, ensure_ascii=False),
                    _utc_now_iso(),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def save_batch(
        self,
        high_level_requirements: List[str],
        low_level_requirements: List[str],
        output: Dict[str, Any],
        title: Optional[str] = None,
    ) -> int:
        input_payload = {
            "high_level_requirements": high_level_requirements,
            "low_level_requirements": low_level_requirements,
        }
        if title is None:
            title = output.get("summary") or "批量关系追溯分析"

        desc = f"批量分析：顶层 {len(high_level_requirements)} 个，底层 {len(low_level_requirements)} 个"

        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO trace_analysis(analysis_type, title, description, input_json, output_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "batch",
                    str(title)[:200],
                    desc,
                    json.dumps(input_payload, ensure_ascii=False),
                    json.dumps(output, ensure_ascii=False),
                    _utc_now_iso(),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def list_requirements(self, page: int = 1, per_page: int = 10) -> Dict[str, Any]:
        page = max(1, int(page))
        per_page = max(1, min(200, int(per_page)))
        offset = (page - 1) * per_page

        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(1) AS c FROM trace_analysis").fetchone()["c"]
            rows = conn.execute(
                """
                SELECT id, title, description, created_at
                FROM trace_analysis
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                (per_page, offset),
            ).fetchall()

        return {
            "requirements": [dict(r) for r in rows],
            "total": total,
            "pages": (total + per_page - 1) // per_page,
            "current_page": page,
        }

    def get_requirement_detail(self, requirement_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, analysis_type, title, description, input_json, output_json, created_at
                FROM trace_analysis
                WHERE id = ?
                """,
                (int(requirement_id),),
            ).fetchone()
        if not row:
            return None

        out = dict(row)
        try:
            out["input"] = json.loads(out.pop("input_json"))
        except Exception:
            out["input"] = {}
        try:
            out["output"] = json.loads(out.pop("output_json"))
        except Exception:
            out["output"] = {}
        return out

    def delete_requirement(self, requirement_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM trace_analysis WHERE id = ?", (int(requirement_id),))
            conn.commit()
            return cur.rowcount > 0

    def statistics(self) -> Dict[str, Any]:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(1) AS c FROM trace_analysis").fetchone()["c"]
            type_rows = conn.execute(
                "SELECT analysis_type, COUNT(1) AS c FROM trace_analysis GROUP BY analysis_type"
            ).fetchall()

        return {
            "total_requirements": total,
            "analysis_type_stats": {r["analysis_type"]: r["c"] for r in type_rows},
        }


db_service = DBService(db_path=settings.DB_PATH)