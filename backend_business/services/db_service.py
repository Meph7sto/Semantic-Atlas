import json
import os
import uuid
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
                        session_id TEXT,
                        analysis_type TEXT NOT NULL,              -- relation | batch
                        title TEXT NOT NULL,
                        description TEXT NOT NULL,
                        input_json TEXT NOT NULL,
                        output_json TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    "ALTER TABLE trace_analysis ADD COLUMN IF NOT EXISTS session_id TEXT"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_trace_created_at ON trace_analysis(created_at)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_trace_session_id ON trace_analysis(session_id)"
                )
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
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_spans_session_id ON spans(session_id)"
                )

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
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_context_runs_session_id ON context_runs(session_id)"
                )

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
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_span_links_context_run ON span_links(context_run_id)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_span_links_source ON span_links(source_span_id)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_span_links_target ON span_links(target_span_id)"
                )

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
                cur.execute(
                    "ALTER TABLE bundles ADD COLUMN IF NOT EXISTS context_run_id TEXT"
                )
                cur.execute(
                    "ALTER TABLE bundles ADD COLUMN IF NOT EXISTS session_id TEXT"
                )
                cur.execute(
                    "ALTER TABLE bundles ADD COLUMN IF NOT EXISTS order_index INTEGER"
                )
                cur.execute("ALTER TABLE bundles ADD COLUMN IF NOT EXISTS status TEXT")
                cur.execute(
                    "ALTER TABLE bundles ADD COLUMN IF NOT EXISTS context_summary TEXT"
                )
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
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_bundles_context_run ON bundles(context_run_id)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_bundles_session_id ON bundles(session_id)"
                )

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
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_bundle_items_bundle ON bundle_items(bundle_id)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_bundle_items_span ON bundle_items(span_id)"
                )

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
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_requirements_l123_session ON requirements_l123(session_id)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_requirements_l123_level ON requirements_l123(level)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_requirements_l123_fingerprint ON requirements_l123(fingerprint)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_requirements_l123_anchor_span ON requirements_l123(anchor_span_id)"
                )

                # ========================
                # Low-level Requirements Table (L4 底层需求表)
                # ========================
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS low_level_requirements (
                        req_id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        source_top_id TEXT,
                        source_top_text TEXT,
                        text TEXT NOT NULL,
                        component TEXT,
                        acceptance_criteria JSONB,
                        test_method TEXT,
                        interfaces JSONB,
                        data_contracts JSONB,
                        error_handling JSONB,
                        nfr JSONB,
                        open_questions JSONB,
                        evidence_ids JSONB,
                        confidence REAL,
                        source TEXT,
                        meta JSONB,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                # 扩展旧表字段（必须先补齐字段，再建索引）
                cur.execute(
                    "ALTER TABLE low_level_requirements ADD COLUMN IF NOT EXISTS source_top_id TEXT"
                )
                cur.execute(
                    "ALTER TABLE low_level_requirements ADD COLUMN IF NOT EXISTS source_top_text TEXT"
                )
                cur.execute(
                    "ALTER TABLE low_level_requirements ADD COLUMN IF NOT EXISTS component TEXT"
                )
                cur.execute(
                    "ALTER TABLE low_level_requirements ADD COLUMN IF NOT EXISTS acceptance_criteria JSONB"
                )
                cur.execute(
                    "ALTER TABLE low_level_requirements ADD COLUMN IF NOT EXISTS test_method TEXT"
                )
                cur.execute(
                    "ALTER TABLE low_level_requirements ADD COLUMN IF NOT EXISTS interfaces JSONB"
                )
                cur.execute(
                    "ALTER TABLE low_level_requirements ADD COLUMN IF NOT EXISTS data_contracts JSONB"
                )
                cur.execute(
                    "ALTER TABLE low_level_requirements ADD COLUMN IF NOT EXISTS error_handling JSONB"
                )
                cur.execute(
                    "ALTER TABLE low_level_requirements ADD COLUMN IF NOT EXISTS nfr JSONB"
                )
                cur.execute(
                    "ALTER TABLE low_level_requirements ADD COLUMN IF NOT EXISTS open_questions JSONB"
                )
                cur.execute(
                    "ALTER TABLE low_level_requirements ADD COLUMN IF NOT EXISTS evidence_ids JSONB"
                )
                cur.execute(
                    "ALTER TABLE low_level_requirements ADD COLUMN IF NOT EXISTS confidence REAL"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_low_level_requirements_session ON low_level_requirements(session_id)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_low_level_requirements_source_top ON low_level_requirements(source_top_id)"
                )

                # ========================
                # Low-level to Top Requirements Mapping (多对多映射表)
                # ========================
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS low_level_requirement_links (
                        req_id TEXT NOT NULL REFERENCES low_level_requirements(req_id) ON DELETE CASCADE,
                        session_id TEXT NOT NULL,
                        top_req_id TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (req_id, top_req_id)
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_low_level_requirement_links_session ON low_level_requirement_links(session_id)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_low_level_requirement_links_top ON low_level_requirement_links(top_req_id)"
                )

                # ========================
                # Conflict Analysis Table (冲突检测结果表)
                # ========================
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS conflict_analysis (
                        id SERIAL PRIMARY KEY,
                        batch_id TEXT,
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
                cur.execute(
                    "ALTER TABLE conflict_analysis ADD COLUMN IF NOT EXISTS batch_id TEXT"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_conflict_analysis_session ON conflict_analysis(session_id)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_conflict_analysis_batch ON conflict_analysis(batch_id)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_conflict_analysis_created_at ON conflict_analysis(created_at)"
                )

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
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_classification_analysis_session ON classification_analysis(session_id)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_classification_analysis_created_at ON classification_analysis(created_at)"
                )

                # ========================
                # Requirements Management (Monitor)
                # ========================

                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS manage_projects (
                        project_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        description TEXT,
                        status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
                        created_by TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )

                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS manage_requirements (
                        req_id TEXT PRIMARY KEY,
                        project_id TEXT NOT NULL REFERENCES manage_projects(project_id) ON DELETE CASCADE,
                        requirement_type TEXT NOT NULL CHECK (requirement_type IN ('top_level', 'low_level', 'task')),
                        status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'under_review', 'confirmed', 'in_progress', 'completed', 'archived')),
                        title TEXT NOT NULL,
                        description TEXT,
                        priority TEXT,
                        assignee TEXT,
                        tags JSONB,
                        due_date TEXT,
                        parent_id TEXT REFERENCES manage_requirements(req_id) ON DELETE SET NULL,
                        order_index INTEGER NOT NULL DEFAULT 0,
                        source_req_id TEXT,
                        source_level TEXT,
                        custom_fields JSONB,
                        created_by TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_by TEXT,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        deleted BOOLEAN NOT NULL DEFAULT FALSE
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_manage_requirements_project ON manage_requirements(project_id)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_manage_requirements_parent ON manage_requirements(parent_id)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_manage_requirements_type ON manage_requirements(requirement_type)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_manage_requirements_status ON manage_requirements(status)"
                )

                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS manage_test_cases (
                        test_case_id TEXT PRIMARY KEY,
                        project_id TEXT NOT NULL REFERENCES manage_projects(project_id) ON DELETE CASCADE,
                        title TEXT NOT NULL,
                        description TEXT,
                        status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'deprecated')),
                        source TEXT,
                        created_by TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_manage_test_cases_project ON manage_test_cases(project_id)"
                )

                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS manage_requirement_test_links (
                        link_id SERIAL PRIMARY KEY,
                        requirement_id TEXT NOT NULL REFERENCES manage_requirements(req_id) ON DELETE CASCADE,
                        test_case_id TEXT NOT NULL REFERENCES manage_test_cases(test_case_id) ON DELETE CASCADE,
                        link_type TEXT NOT NULL DEFAULT 'verification',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        UNIQUE(requirement_id, test_case_id)
                    )
                    """
                )

                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS manage_milestones (
                        milestone_id TEXT PRIMARY KEY,
                        project_id TEXT NOT NULL REFERENCES manage_projects(project_id) ON DELETE CASCADE,
                        name TEXT NOT NULL,
                        description TEXT,
                        message TEXT,
                        milestone_type TEXT NOT NULL DEFAULT 'regular' CHECK (milestone_type IN ('regular', 'baseline', 'branch', 'merge')),
                        is_baseline BOOLEAN NOT NULL DEFAULT FALSE,
                        sprint TEXT,
                        version TEXT,
                        tags JSONB,
                        created_by TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        metadata JSONB
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_manage_milestones_project ON manage_milestones(project_id)"
                )

                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS manage_milestone_nodes (
                        snapshot_id TEXT PRIMARY KEY,
                        milestone_id TEXT NOT NULL REFERENCES manage_milestones(milestone_id) ON DELETE CASCADE,
                        requirement_id TEXT NOT NULL,
                        requirement_type TEXT,
                        status TEXT,
                        title TEXT,
                        description TEXT,
                        parent_id TEXT,
                        order_index INTEGER,
                        snapshot_data JSONB,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_manage_milestone_nodes_milestone ON manage_milestone_nodes(milestone_id)"
                )

                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS manage_milestone_relations (
                        id SERIAL PRIMARY KEY,
                        milestone_id TEXT NOT NULL REFERENCES manage_milestones(milestone_id) ON DELETE CASCADE,
                        parent_id TEXT NOT NULL,
                        child_id TEXT NOT NULL,
                        order_index INTEGER NOT NULL DEFAULT 0
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_manage_milestone_relations_milestone ON manage_milestone_relations(milestone_id)"
                )

                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS manage_milestone_edges (
                        id SERIAL PRIMARY KEY,
                        project_id TEXT NOT NULL REFERENCES manage_projects(project_id) ON DELETE CASCADE,
                        from_milestone_id TEXT NOT NULL REFERENCES manage_milestones(milestone_id) ON DELETE CASCADE,
                        to_milestone_id TEXT NOT NULL REFERENCES manage_milestones(milestone_id) ON DELETE CASCADE,
                        relation_type TEXT NOT NULL,
                        message TEXT,
                        created_by TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_manage_milestone_edges_project ON manage_milestone_edges(project_id)"
                )

                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS manage_branches (
                        branch_id TEXT PRIMARY KEY,
                        project_id TEXT NOT NULL REFERENCES manage_projects(project_id) ON DELETE CASCADE,
                        base_milestone_id TEXT NOT NULL REFERENCES manage_milestones(milestone_id) ON DELETE RESTRICT,
                        name TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'under_review', 'merged', 'closed')),
                        created_by TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        metadata JSONB
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_manage_branches_project ON manage_branches(project_id)"
                )

                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS manage_change_sets (
                        change_id TEXT PRIMARY KEY,
                        branch_id TEXT NOT NULL REFERENCES manage_branches(branch_id) ON DELETE CASCADE,
                        change_type TEXT NOT NULL CHECK (change_type IN ('added', 'modified', 'deleted', 'moved')),
                        requirement_id TEXT,
                        before_data JSONB,
                        after_data JSONB,
                        created_by TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_manage_change_sets_branch ON manage_change_sets(branch_id)"
                )

                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS manage_impact_reports (
                        report_id TEXT PRIMARY KEY,
                        branch_id TEXT NOT NULL REFERENCES manage_branches(branch_id) ON DELETE CASCADE,
                        summary TEXT,
                        detail_json JSONB,
                        status TEXT NOT NULL DEFAULT 'pending',
                        created_by TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_manage_impact_reports_branch ON manage_impact_reports(branch_id)"
                )

                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS manage_merge_logs (
                        merge_id TEXT PRIMARY KEY,
                        branch_id TEXT NOT NULL REFERENCES manage_branches(branch_id) ON DELETE CASCADE,
                        target_milestone_id TEXT REFERENCES manage_milestones(milestone_id) ON DELETE SET NULL,
                        status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'conflicts', 'merged', 'failed')),
                        summary TEXT,
                        created_by TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_manage_merge_logs_branch ON manage_merge_logs(branch_id)"
                )

                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS manage_reviews (
                        review_id TEXT PRIMARY KEY,
                        branch_id TEXT NOT NULL REFERENCES manage_branches(branch_id) ON DELETE CASCADE,
                        status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'changes_requested')),
                        reviewer TEXT,
                        comment TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_manage_reviews_branch ON manage_reviews(branch_id)"
                )

                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS manage_audit_logs (
                        log_id TEXT PRIMARY KEY,
                        project_id TEXT,
                        actor TEXT,
                        action TEXT,
                        target_type TEXT,
                        target_id TEXT,
                        detail JSONB,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_manage_audit_logs_project ON manage_audit_logs(project_id)"
                )

    def save_relation(
        self,
        high_level_requirement: str,
        low_level_requirement: str,
        output: Dict[str, Any],
        title: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> int:
        input_payload = {
            "high_level_requirement": high_level_requirement,
            "low_level_requirement": low_level_requirement,
        }
        if title is None:
            title = output.get("summary") or "关系追溯分析"

        desc = (
            f"顶层需求: {high_level_requirement}\n\n底层需求: {low_level_requirement}"
        )

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO trace_analysis(session_id, analysis_type, title, description, input_json, output_json, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        session_id,
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
        session_id: Optional[str] = None,
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
                    INSERT INTO trace_analysis(session_id, analysis_type, title, description, input_json, output_json, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        session_id,
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
                cur.execute(
                    "DELETE FROM trace_analysis WHERE id = %s", (int(requirement_id),)
                )
                return cur.rowcount > 0

    def statistics(self) -> Dict[str, Any]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT COUNT(1) AS c FROM trace_analysis")
                total = cur.fetchone()["c"]
                cur.execute(
                    "SELECT analysis_type, COUNT(1) AS c FROM trace_analysis GROUP BY analysis_type"
                )
                type_rows = cur.fetchall()

        return {
            "total_requirements": total,
            "analysis_type_stats": {r["analysis_type"]: r["c"] for r in type_rows},
        }

    def save_conflict_batch(
        self,
        session_id: Optional[str],
        conflicts: List[Dict[str, Any]],
        batch_id: Optional[str] = None,
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
        batch_id = batch_id or uuid.uuid4().hex
        with self._connect() as conn:
            with conn.cursor() as cur:
                for conflict in conflicts:
                    result_json = (
                        conflict.get("data") or conflict.get("raw_response") or {}
                    )
                    if isinstance(result_json, str):
                        try:
                            result_json = json.loads(result_json)
                        except Exception:
                            result_json = {"raw": result_json}

                    cur.execute(
                        """
                        INSERT INTO conflict_analysis (
                            batch_id, session_id, requirement_a, requirement_b,
                            is_conflict, raw_response, result_json, created_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (
                            batch_id,
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

    def get_latest_trace_batch(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, output_json
                    FROM trace_analysis
                    WHERE session_id = %s AND analysis_type = 'batch'
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (session_id,),
                )
                row = cur.fetchone()
        if not row:
            return None
        try:
            return {
                "record_id": row["id"],
                "data": json.loads(row["output_json"]),
            }
        except Exception:
            return {"record_id": row["id"], "data": {}}

    def get_latest_conflict_batch(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT batch_id
                    FROM conflict_analysis
                    WHERE session_id = %s AND batch_id IS NOT NULL
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (session_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                batch_id = row["batch_id"]
                cur.execute(
                    """
                    SELECT requirement_a, requirement_b, is_conflict, raw_response, result_json
                    FROM conflict_analysis
                    WHERE session_id = %s AND batch_id = %s
                    ORDER BY created_at ASC
                    """,
                    (session_id, batch_id),
                )
                rows = cur.fetchall()
        return {"batch_id": batch_id, "items": [dict(r) for r in rows]}

    def get_latest_classification(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, requirements, predictions, label_distribution, total, result_json
                    FROM classification_analysis
                    WHERE session_id = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (session_id,),
                )
                row = cur.fetchone()
        if not row:
            return None
        out = dict(row)
        for key in ("requirements", "predictions", "label_distribution", "result_json"):
            try:
                if out.get(key) is not None and isinstance(out.get(key), str):
                    out[key] = json.loads(out[key])
            except Exception:
                pass
        return out

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
                        (
                            json.dumps(label_distribution, ensure_ascii=False)
                            if label_distribution
                            else None
                        ),
                        total,
                        json.dumps(result_json, ensure_ascii=False),
                        _utc_now_iso(),
                    ),
                )
                return int(cur.fetchone()[0])

    # ========================
    # L4 低层需求 (low_level_requirements) 相关方法
    # ========================

    def save_l4_requirements(
        self,
        session_id: str,
        l4_requirements: List[Dict[str, Any]],
    ) -> List[str]:
        """
        保存 L4 需求到数据库

        Args:
            session_id: 会话 ID
            l4_requirements: L4 需求列表，每个包含:
                - l4_id / req_id
                - source_top_id
                - source_top_text (可选)
                - shall_statement / text
                - component
                - acceptance_criteria
                - test_method
                - interfaces
                - data_contracts
                - error_handling
                - nfr
                - open_questions
                - evidence_ids
                - confidence

        Returns:
            插入的 req_id 列表
        """
        if not l4_requirements:
            return []

        inserted_ids = []
        with self._connect() as conn:
            with conn.cursor() as cur:
                for req in l4_requirements:
                    req_id = (
                        req.get("l4_id") or req.get("req_id") or f"L4-{_utc_now_iso()}"
                    )
                    text = req.get("shall_statement") or req.get("text") or ""

                    # 如果 req_id 已存在，则生成新的唯一 ID，避免跨 session 冲突
                    cur.execute(
                        "SELECT 1 FROM low_level_requirements WHERE req_id = %s",
                        (req_id,),
                    )
                    if cur.fetchone():
                        req_id = f"{req_id}-{uuid.uuid4().hex[:6]}"

                    cur.execute(
                        """
                        INSERT INTO low_level_requirements (
                            req_id, session_id, source_top_id, source_top_text,
                            text, component, acceptance_criteria, test_method,
                            interfaces, data_contracts, error_handling, nfr,
                            open_questions, evidence_ids, confidence, source, meta, created_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            req_id,
                            session_id,
                            req.get("source_top_id"),
                            req.get("source_top_text"),
                            text,
                            req.get("component"),
                            json.dumps(
                                req.get("acceptance_criteria", []), ensure_ascii=False
                            ),
                            req.get("test_method"),
                            json.dumps(req.get("interfaces", []), ensure_ascii=False),
                            json.dumps(
                                req.get("data_contracts", []), ensure_ascii=False
                            ),
                            json.dumps(
                                req.get("error_handling", []), ensure_ascii=False
                            ),
                            json.dumps(req.get("nfr", []), ensure_ascii=False),
                            json.dumps(
                                req.get("open_questions", []), ensure_ascii=False
                            ),
                            json.dumps(req.get("evidence_ids", []), ensure_ascii=False),
                            req.get("confidence"),
                            "l4_generation",
                            json.dumps(req, ensure_ascii=False),
                            _utc_now_iso(),
                        ),
                    )
                    inserted_ids.append(req_id)

                    # 维护多对多映射：一个底层需求可关联多个顶层需求
                    top_ids = req.get("source_top_ids") or []
                    if not top_ids and req.get("source_top_id"):
                        top_ids = [req.get("source_top_id")]
                    for top_id in top_ids:
                        if not top_id:
                            continue
                        cur.execute(
                            """
                            INSERT INTO low_level_requirement_links (req_id, session_id, top_req_id, created_at)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT DO NOTHING
                            """,
                            (req_id, session_id, top_id, _utc_now_iso()),
                        )

        return inserted_ids

    def get_l4_requirements_by_session(
        self,
        session_id: str,
        page: int = 1,
        per_page: int = 100,
    ) -> Dict[str, Any]:
        """
        查询指定 session 的 L4 底层需求
        """
        page = max(1, int(page))
        per_page = max(1, min(500, int(per_page)))
        offset = (page - 1) * per_page

        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT COUNT(1) AS c FROM low_level_requirements WHERE session_id = %s",
                    (session_id,),
                )
                total = cur.fetchone()["c"]

                cur.execute(
                    """
                    SELECT 
                        req_id, session_id, source_top_id, source_top_text,
                        text, component, acceptance_criteria, test_method,
                        interfaces, data_contracts, error_handling, nfr,
                        open_questions, evidence_ids, confidence, source,
                        created_at::text AS created_at
                    FROM low_level_requirements
                    WHERE session_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (session_id, per_page, offset),
                )
                rows = cur.fetchall()

                # 批量获取映射关系
                cur.execute(
                    """
                    SELECT req_id, array_agg(top_req_id) AS source_top_ids
                    FROM low_level_requirement_links
                    WHERE session_id = %s
                    GROUP BY req_id
                    """,
                    (session_id,),
                )
                link_rows = cur.fetchall()
                top_map = {r["req_id"]: r["source_top_ids"] for r in link_rows}

        # 解析 JSONB 字段
        requirements = []
        for row in rows:
            req = dict(row)
            for key in (
                "acceptance_criteria",
                "interfaces",
                "data_contracts",
                "error_handling",
                "nfr",
                "open_questions",
                "evidence_ids",
            ):
                if req.get(key) and isinstance(req[key], str):
                    try:
                        req[key] = json.loads(req[key])
                    except Exception:
                        pass
            req["source_top_ids"] = top_map.get(req["req_id"], [])
            requirements.append(req)

        return {
            "requirements": requirements,
            "total": total,
            "pages": (total + per_page - 1) // per_page if total else 0,
            "current_page": page,
        }

    def has_l4_requirements(self, session_id: str) -> bool:
        """检查指定 session 是否有 L4 需求"""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM low_level_requirements WHERE session_id = %s LIMIT 1",
                    (session_id,),
                )
                return cur.fetchone() is not None

    def get_requirement_pairs_for_trace(self, session_id: str) -> List[Dict[str, Any]]:
        """
        获取需要进行追溯分析的顶层-底层需求对

        只返回数据库中有映射关系的对，避免全量笛卡尔积分析

        Returns:
            List[{
                'high_req_id': str,
                'high_req_text': str,
                'low_req_id': str,
                'low_req_text': str,
            }]
        """
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 从映射表关联顶层需求和底层需求
                cur.execute(
                    """
                    SELECT 
                        lnk.top_req_id AS high_req_id,
                        COALESCE(top.text, low.source_top_text, '') AS high_req_text,
                        lnk.req_id AS low_req_id,
                        low.text AS low_req_text
                    FROM low_level_requirement_links lnk
                    JOIN low_level_requirements low ON lnk.req_id = low.req_id
                    LEFT JOIN requirements_l123 top ON lnk.top_req_id = top.req_id
                    WHERE lnk.session_id = %s
                    ORDER BY lnk.created_at
                    """,
                    (session_id,),
                )
                rows = cur.fetchall()

        # 过滤掉空文本的记录
        pairs = []
        for row in rows:
            high_text = (row.get("high_req_text") or "").strip()
            low_text = (row.get("low_req_text") or "").strip()
            if high_text and low_text:
                pairs.append(
                    {
                        "high_req_id": row["high_req_id"],
                        "high_req_text": high_text,
                        "low_req_id": row["low_req_id"],
                        "low_req_text": low_text,
                    }
                )

        return pairs

    def upsert_spans(self, spans: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not spans:
            return {"upserted_count": 0, "inserted": 0, "updated": 0, "conflicts": []}

        span_ids = [span["span_id"] for span in spans]
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT span_id, text FROM spans WHERE span_id = ANY(%s)",
                    (span_ids,),
                )
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
