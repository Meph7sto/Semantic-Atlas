import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from backend_business.config import settings


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


class DBService:
    """
    轻量级 PostgreSQL 存储：
    - 保存追溯分析（单对、批量）的输入与输出 JSON
    - 保存解析后的 transcript spans
    - 提供列表/详情/统计
    """

    def __init__(self, dsn: str):
        self.dsn = dsn
        self._init_db()

    def _connect(self) -> psycopg2.extensions.connection:
        return psycopg2.connect(self.dsn)

    def _init_db(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS trace_analysis (
                        id SERIAL PRIMARY KEY,
                        analysis_type TEXT NOT NULL,              -- relation | batch
                        title TEXT NOT NULL,
                        description TEXT NOT NULL,
                        input_json TEXT NOT NULL,
                        output_json TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute("CREATE INDEX IF NOT EXISTS idx_trace_created_at ON trace_analysis(created_at)")
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS spans (
                        span_id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        start_ms INTEGER,
                        end_ms INTEGER,
                        speaker TEXT,
                        text TEXT NOT NULL,
                        asr_confidence REAL,
                        meta_json TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    "ALTER TABLE spans ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
                )
                cur.execute(
                    "ALTER TABLE spans ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
                )
                cur.execute("CREATE INDEX IF NOT EXISTS idx_spans_session_id ON spans(session_id)")

                # ========================
                # Phase 2 Tables
                # ========================

                # context_runs: 记录一次 Phase2 运行
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS context_runs (
                        context_run_id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        options_snapshot JSONB,
                        status TEXT NOT NULL DEFAULT 'RUNNING',
                        stats JSONB,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute("CREATE INDEX IF NOT EXISTS idx_context_runs_session_id ON context_runs(session_id)")

                # span_links: 稀疏关联矩阵（边表）
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS span_links (
                        id SERIAL PRIMARY KEY,
                        context_run_id TEXT NOT NULL REFERENCES context_runs(context_run_id) ON DELETE CASCADE,
                        source_span_id TEXT NOT NULL REFERENCES spans(span_id) ON DELETE CASCADE,
                        target_span_id TEXT NOT NULL REFERENCES spans(span_id) ON DELETE CASCADE,
                        relation_type TEXT NOT NULL CHECK (relation_type IN ('continuation', 'elaboration', 'dependency', 'same_topic', 'conflict')),
                        strength REAL NOT NULL CHECK (strength >= 0 AND strength <= 1),
                        note TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        UNIQUE(context_run_id, source_span_id, target_span_id, relation_type)
                    )
                    """
                )
                cur.execute("CREATE INDEX IF NOT EXISTS idx_span_links_context_run ON span_links(context_run_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_span_links_source ON span_links(source_span_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_span_links_target ON span_links(target_span_id)")

                # bundles: 上下文包
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS bundles (
                        bundle_id TEXT PRIMARY KEY,
                        context_run_id TEXT NOT NULL REFERENCES context_runs(context_run_id) ON DELETE CASCADE,
                        session_id TEXT NOT NULL,
                        order_index INTEGER NOT NULL,
                        status TEXT NOT NULL DEFAULT 'READY',
                        context_summary TEXT,
                        meta JSONB,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute("ALTER TABLE bundles ADD COLUMN IF NOT EXISTS context_run_id TEXT")
                cur.execute("ALTER TABLE bundles ADD COLUMN IF NOT EXISTS session_id TEXT")
                cur.execute("ALTER TABLE bundles ADD COLUMN IF NOT EXISTS order_index INTEGER")
                cur.execute("ALTER TABLE bundles ADD COLUMN IF NOT EXISTS status TEXT")
                cur.execute("ALTER TABLE bundles ADD COLUMN IF NOT EXISTS context_summary TEXT")
                cur.execute("ALTER TABLE bundles ADD COLUMN IF NOT EXISTS meta JSONB")
                cur.execute(
                    "ALTER TABLE bundles ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
                )
                cur.execute(
                    """
                    DO $$
                    BEGIN
                        IF EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_name = 'bundles'
                              AND column_name = 'bundle_type'
                              AND is_nullable = 'NO'
                        ) THEN
                            ALTER TABLE bundles
                                ALTER COLUMN bundle_type DROP NOT NULL;
                        END IF;
                    END $$;
                    """
                )
                cur.execute("CREATE INDEX IF NOT EXISTS idx_bundles_context_run ON bundles(context_run_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_bundles_session_id ON bundles(session_id)")

                # bundle_items: bundle 内 span 映射
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS bundle_items (
                        id SERIAL PRIMARY KEY,
                        bundle_id TEXT NOT NULL REFERENCES bundles(bundle_id) ON DELETE CASCADE,
                        span_id TEXT NOT NULL REFERENCES spans(span_id) ON DELETE CASCADE,
                        span_ref TEXT NOT NULL,
                        order_index INTEGER NOT NULL,
                        UNIQUE(bundle_id, span_ref),
                        UNIQUE(bundle_id, span_id)
                    )
                    """
                )
                cur.execute("CREATE INDEX IF NOT EXISTS idx_bundle_items_bundle ON bundle_items(bundle_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_bundle_items_span ON bundle_items(span_id)")

                # 兼容旧表结构：补齐 spans 外键
                cur.execute(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1
                            FROM pg_constraint c
                            JOIN pg_attribute a
                                ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
                            WHERE c.conrelid = 'span_links'::regclass
                              AND c.contype = 'f'
                              AND a.attname = 'source_span_id'
                        ) THEN
                            ALTER TABLE span_links
                                ADD CONSTRAINT fk_span_links_source_span
                                FOREIGN KEY (source_span_id) REFERENCES spans(span_id) ON DELETE CASCADE;
                        END IF;
                        IF NOT EXISTS (
                            SELECT 1
                            FROM pg_constraint c
                            JOIN pg_attribute a
                                ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
                            WHERE c.conrelid = 'span_links'::regclass
                              AND c.contype = 'f'
                              AND a.attname = 'target_span_id'
                        ) THEN
                            ALTER TABLE span_links
                                ADD CONSTRAINT fk_span_links_target_span
                                FOREIGN KEY (target_span_id) REFERENCES spans(span_id) ON DELETE CASCADE;
                        END IF;
                        IF NOT EXISTS (
                            SELECT 1
                            FROM pg_constraint c
                            JOIN pg_attribute a
                                ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
                            WHERE c.conrelid = 'bundle_items'::regclass
                              AND c.contype = 'f'
                              AND a.attname = 'span_id'
                        ) THEN
                            ALTER TABLE bundle_items
                                ADD CONSTRAINT fk_bundle_items_span
                                FOREIGN KEY (span_id) REFERENCES spans(span_id) ON DELETE CASCADE;
                        END IF;
                        IF NOT EXISTS (
                            SELECT 1
                            FROM pg_constraint c
                            JOIN pg_attribute a
                                ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
                            WHERE c.conrelid = 'bundles'::regclass
                              AND c.contype = 'f'
                              AND a.attname = 'context_run_id'
                        ) THEN
                            ALTER TABLE bundles
                                ADD CONSTRAINT fk_bundles_context_run
                                FOREIGN KEY (context_run_id) REFERENCES context_runs(context_run_id) ON DELETE CASCADE;
                        END IF;
                    END $$;
                    """
                )

                # ========================
                # Phase 3: Requirements L123 Table
                # ========================
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS requirements_l123 (
                        req_id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        level TEXT NOT NULL CHECK (level IN ('L1', 'L2', 'L3')),
                        text TEXT NOT NULL CHECK (char_length(text) >= 10 AND char_length(text) <= 500),
                        fingerprint TEXT NOT NULL UNIQUE,
                        anchor_span_id TEXT REFERENCES spans(span_id) ON DELETE CASCADE,
                        r INTEGER,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute("CREATE INDEX IF NOT EXISTS idx_requirements_l123_session ON requirements_l123(session_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_requirements_l123_level ON requirements_l123(level)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_requirements_l123_fingerprint ON requirements_l123(fingerprint)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_requirements_l123_anchor_span ON requirements_l123(anchor_span_id)")

                # ========================
                # Low-level Requirements Table (底层需求占位表)
                # ========================
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS low_level_requirements (
                        req_id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        text TEXT NOT NULL,
                        source TEXT,
                        meta JSONB,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute("CREATE INDEX IF NOT EXISTS idx_low_level_requirements_session ON low_level_requirements(session_id)")

                # ========================
                # Conflict Analysis Table (冲突检测结果表)
                # ========================
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS conflict_analysis (
                        id SERIAL PRIMARY KEY,
                        session_id TEXT,
                        requirement_a TEXT NOT NULL,
                        requirement_b TEXT NOT NULL,
                        is_conflict BOOLEAN NOT NULL,
                        raw_response TEXT,
                        result_json JSONB,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute("CREATE INDEX IF NOT EXISTS idx_conflict_analysis_session ON conflict_analysis(session_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_conflict_analysis_created_at ON conflict_analysis(created_at)")

                # ========================
                # Classification Analysis Table (需求分类结果表)
                # ========================
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS classification_analysis (
                        id SERIAL PRIMARY KEY,
                        session_id TEXT,
                        requirements JSONB NOT NULL,
                        predictions JSONB NOT NULL,
                        label_distribution JSONB,
                        total INTEGER,
                        result_json JSONB,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute("CREATE INDEX IF NOT EXISTS idx_classification_analysis_session ON classification_analysis(session_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_classification_analysis_created_at ON classification_analysis(created_at)")

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
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO trace_analysis(analysis_type, title, description, input_json, output_json, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
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
                return int(cur.fetchone()[0])

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
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO trace_analysis(analysis_type, title, description, input_json, output_json, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
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
                return int(cur.fetchone()[0])

    def list_requirements(self, page: int = 1, per_page: int = 10) -> Dict[str, Any]:
        page = max(1, int(page))
        per_page = max(1, min(200, int(per_page)))
        offset = (page - 1) * per_page

        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT COUNT(1) AS c FROM trace_analysis")
                total = cur.fetchone()["c"]
                cur.execute(
                    """
                    SELECT id, title, description, created_at::text AS created_at
                    FROM trace_analysis
                    ORDER BY id DESC
                    LIMIT %s OFFSET %s
                    """,
                    (per_page, offset),
                )
                rows = cur.fetchall()

        return {
            "requirements": rows,
            "total": total,
            "pages": (total + per_page - 1) // per_page,
            "current_page": page,
        }

    def get_requirement_detail(self, requirement_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, analysis_type, title, description, input_json, output_json, created_at::text AS created_at
                    FROM trace_analysis
                    WHERE id = %s
                    """,
                    (int(requirement_id),),
                )
                row = cur.fetchone()
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
            with conn.cursor() as cur:
                cur.execute("DELETE FROM trace_analysis WHERE id = %s", (int(requirement_id),))
                return cur.rowcount > 0

    def statistics(self) -> Dict[str, Any]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT COUNT(1) AS c FROM trace_analysis")
                total = cur.fetchone()["c"]
                cur.execute("SELECT analysis_type, COUNT(1) AS c FROM trace_analysis GROUP BY analysis_type")
                type_rows = cur.fetchall()

        return {
            "total_requirements": total,
            "analysis_type_stats": {r["analysis_type"]: r["c"] for r in type_rows},
        }

    def save_conflict_batch(
        self,
        session_id: Optional[str],
        conflicts: List[Dict[str, Any]],
    ) -> List[int]:
        """
        批量保存冲突检测结果
        conflicts: List[{
            'requirement_a': str,
            'requirement_b': str,
            'is_conflict': bool,
            'raw_response': str,
            'data': dict (可选，完整的响应数据)
        }]
        """
        if not conflicts:
            return []

        record_ids = []
        with self._connect() as conn:
            with conn.cursor() as cur:
                for conflict in conflicts:
                    result_json = conflict.get("data") or conflict.get("raw_response") or {}
                    if isinstance(result_json, str):
                        try:
                            result_json = json.loads(result_json)
                        except Exception:
                            result_json = {"raw": result_json}

                    cur.execute(
                        """
                        INSERT INTO conflict_analysis (
                            session_id, requirement_a, requirement_b,
                            is_conflict, raw_response, result_json, created_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (
                            session_id,
                            conflict.get("requirement_a", ""),
                            conflict.get("requirement_b", ""),
                            bool(conflict.get("is_conflict", False)),
                            conflict.get("raw_response", ""),
                            json.dumps(result_json, ensure_ascii=False),
                            _utc_now_iso(),
                        ),
                    )
                    record_ids.append(int(cur.fetchone()[0]))

        return record_ids

    def save_classification(
        self,
        session_id: Optional[str],
        requirements: List[str],
        predictions: List[Dict[str, Any]],
        label_distribution: Optional[Dict[str, Any]] = None,
        total: Optional[int] = None,
        result_json: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        保存需求分类结果
        """
        if result_json is None:
            result_json = {
                "predictions": predictions,
                "label_distribution": label_distribution,
                "total": total,
            }

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO classification_analysis (
                        session_id, requirements, predictions,
                        label_distribution, total, result_json, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        session_id,
                        json.dumps(requirements, ensure_ascii=False),
                        json.dumps(predictions, ensure_ascii=False),
                        json.dumps(label_distribution, ensure_ascii=False) if label_distribution else None,
                        total,
                        json.dumps(result_json, ensure_ascii=False),
                        _utc_now_iso(),
                    ),
                )
                return int(cur.fetchone()[0])

    def upsert_spans(self, spans: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not spans:
            return {"upserted_count": 0, "inserted": 0, "updated": 0, "conflicts": []}

        span_ids = [span["span_id"] for span in spans]
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT span_id, text FROM spans WHERE span_id = ANY(%s)", (span_ids,))
                existing_rows = cur.fetchall()
                existing_text = {row[0]: row[1] for row in existing_rows}

                to_insert: List[Dict[str, Any]] = []
                to_update: List[Dict[str, Any]] = []
                conflicts: List[Dict[str, Any]] = []

                for span in spans:
                    current_text = existing_text.get(span["span_id"])
                    if current_text is None:
                        to_insert.append(span)
                    elif current_text == span["text"]:
                        to_update.append(span)
                    else:
                        conflicts.append(
                            {
                                "span_id": span["span_id"],
                                "existing_text": current_text,
                                "incoming_text": span["text"],
                            }
                        )

                if to_insert:
                    cur.executemany(
                        """
                        INSERT INTO spans (
                            span_id, session_id, start_ms, end_ms, speaker, text,
                            asr_confidence, meta_json, created_at, updated_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                        """,
                        [
                            (
                                span["span_id"],
                                span["session_id"],
                                span["start_ms"],
                                span["end_ms"],
                                span["speaker"],
                                span["text"],
                                span.get("asr_confidence"),
                                span.get("meta_json"),
                            )
                            for span in to_insert
                        ],
                    )

                if to_update:
                    cur.executemany(
                        """
                        UPDATE spans
                        SET session_id = %s,
                            start_ms = %s,
                            end_ms = %s,
                            speaker = %s,
                            text = %s,
                            asr_confidence = %s,
                            meta_json = %s,
                            updated_at = NOW()
                        WHERE span_id = %s
                        """,
                        [
                            (
                                span["session_id"],
                                span["start_ms"],
                                span["end_ms"],
                                span["speaker"],
                                span["text"],
                                span.get("asr_confidence"),
                                span.get("meta_json"),
                                span["span_id"],
                            )
                            for span in to_update
                        ],
                    )

        return {
            "upserted_count": len(to_insert) + len(to_update),
            "inserted": len(to_insert),
            "updated": len(to_update),
            "conflicts": conflicts,
        }


if os.environ.get("SKIP_DB_INIT") == "1":
    db_service = None
else:
    db_service = DBService(dsn=settings.POSTGRES_DSN)
