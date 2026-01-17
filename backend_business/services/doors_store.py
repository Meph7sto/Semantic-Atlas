from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import pymysql
from pymysql.cursors import DictCursor


def _uuid() -> str:
    return str(uuid.uuid4())


def _utc_now() -> datetime:
    return datetime.utcnow()


def _normalize_text(s: str) -> str:
    return " ".join((s or "").strip().split())


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


@dataclass
class ImportedRequirement:
    object_id: str
    revision_id: str
    object_type: str
    text: str


class DoorsStore:
    """
    DOORS 风格对象库（MySQL）最小实现：
    - requirement_object / requirement_revision（对象 + 修订）
    - module / module_object（模块视图）
    - artifact / transcript_segment / evidence_link（证据一等化，先以 quote 为证据）
    - requirement_link / link_revision（追溯链接 + 验收/驳回）

    注意：这里使用 pymysql 直连 MySQL，兼容 Python 3.14。
    """

    def __init__(self, db_url: str):
        if not db_url:
            raise ValueError("DOORS_DB_URL is empty")
        self._conn_kwargs = self._parse_db_url(db_url)

    def _parse_db_url(self, db_url: str) -> Dict[str, Any]:
        # mysql+pymysql://user:pass@host:port/db?charset=utf8mb4
        parsed = urlparse(db_url)
        if parsed.scheme not in ("mysql+pymysql", "mysql"):
            raise ValueError("DOORS_DB_URL must start with mysql+pymysql://")
        user = parsed.username or ""
        password = parsed.password or ""
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 3306
        db = (parsed.path or "").lstrip("/")
        if not db:
            raise ValueError("DOORS_DB_URL missing database name")
        query = parse_qs(parsed.query or "")
        charset = (query.get("charset") or ["utf8mb4"])[0]
        return {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "database": db,
            "charset": charset,
            "autocommit": True,
            "cursorclass": DictCursor,
        }

    def _get_conn(self):
        return pymysql.connect(**self._conn_kwargs)

    def _fetchone(self, sql: str, params: Tuple[Any, ...]) -> Optional[Dict[str, Any]]:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchone()

    def _fetchall(self, sql: str, params: Tuple[Any, ...]) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return list(cur.fetchall() or [])

    def _execute(self, sql: str, params: Tuple[Any, ...]) -> None:
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)

    # -------------------------
    # Workspace / Analysis run
    # -------------------------
    def create_workspace(
        self,
        project_id: str,
        scope_query: Optional[Dict[str, Any]] = None,
        created_by: Optional[str] = None,
    ) -> str:
        ws_id = _uuid()
        self._execute(
            "INSERT INTO workspace(id,project_id,scope_query,created_by,created_at) "
            "VALUES (%s,%s,CAST(%s AS JSON),%s,%s)",
            (ws_id, project_id, json.dumps(scope_query or {}, ensure_ascii=False), created_by, _utc_now()),
        )
        return ws_id

    def create_analysis_run(
        self,
        workspace_id: str,
        stage: str,
        config: Optional[Dict[str, Any]] = None,
        status: str = "success",
    ) -> str:
        run_id = _uuid()
        self._execute(
            "INSERT INTO analysis_run(id,workspace_id,stage,config,status,created_at) "
            "VALUES (%s,%s,%s,CAST(%s AS JSON),%s,%s)",
            (run_id, workspace_id, stage, json.dumps(config or {}, ensure_ascii=False), status, _utc_now()),
        )
        return run_id

    def insert_conflict_finding(
        self,
        run_id: str,
        object_a_id: str,
        object_b_id: str,
        explanation: Optional[str],
        conflict_type: Optional[str] = None,
        severity: Optional[str] = None,
        status: str = "open",
    ) -> str:
        fid = _uuid()
        self._execute(
            "INSERT INTO conflict_finding("
            "id,run_id,object_a_id,object_b_id,conflict_type,severity,explanation,status,created_at"
            ") VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (fid, run_id, object_a_id, object_b_id, conflict_type, severity, explanation, status, _utc_now()),
        )
        return fid

    def insert_classification_result(
        self,
        run_id: str,
        object_id: str,
        label: str,
        score: Optional[float] = None,
        rationale: Optional[str] = None,
        status: str = "proposed",
    ) -> str:
        cid = _uuid()
        self._execute(
            "INSERT INTO classification_result("
            "id,run_id,object_id,label,score,rationale,status,created_at"
            ") VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (cid, run_id, object_id, label, score, rationale, status, _utc_now()),
        )
        return cid

    # -------------------------
    # Acquisition run + candidate artifacts
    # -------------------------
    def create_extraction_run(
        self,
        artifact_id: str,
        model: str,
        prompt_version: Optional[str] = None,
        status: str = "success",
        config: Optional[Dict[str, Any]] = None,
    ) -> str:
        rid = _uuid()
        self._execute(
            "INSERT INTO extraction_run(id,artifact_id,model,prompt_version,status,config,created_at) "
            "VALUES (%s,%s,%s,%s,%s,CAST(%s AS JSON),%s)",
            (rid, artifact_id, model, prompt_version, status, json.dumps(config or {}, ensure_ascii=False), _utc_now()),
        )
        return rid

    def create_candidate_requirement(
        self,
        extraction_run_id: str,
        text_body: str,
        confidence: Optional[float] = None,
        suggested_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        cid = _uuid()
        self._execute(
            "INSERT INTO candidate_requirement("
            "id,extraction_run_id,text,confidence,suggested_type,metadata,created_at"
            ") VALUES (%s,%s,%s,%s,%s,CAST(%s AS JSON),%s)",
            (cid, extraction_run_id, _normalize_text(text_body), confidence, suggested_type, json.dumps(metadata or {}, ensure_ascii=False), _utc_now()),
        )
        return cid

    def link_candidate_evidence(
        self,
        candidate_id: str,
        transcript_segment_id: str,
        score: Optional[float] = None,
        span_offsets: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._execute(
            "INSERT INTO candidate_evidence(candidate_id,transcript_segment_id,score,span_offsets,created_at) "
            "VALUES (%s,%s,%s,CAST(%s AS JSON),%s) "
            "ON DUPLICATE KEY UPDATE score=VALUES(score), span_offsets=VALUES(span_offsets)",
            (candidate_id, transcript_segment_id, score, json.dumps(span_offsets or {}, ensure_ascii=False), _utc_now()),
        )

    # -------------------------
    # Project / Module
    # -------------------------
    def ensure_project(self, name: str, description: Optional[str] = None) -> str:
        name = (name or "default").strip() or "default"
        row = self._fetchone("SELECT id FROM project WHERE name=%s", (name,))
        if row:
            return str(row["id"])
        pid = _uuid()
        self._execute(
            "INSERT INTO project(id,name,description,created_at) VALUES (%s,%s,%s,%s)",
            (pid, name, description, _utc_now()),
        )
        return pid

    def ensure_module(self, project_id: str, name: str, description: Optional[str] = None) -> str:
        name = (name or "").strip()
        if not name:
            raise ValueError("module name is empty")
        row = self._fetchone("SELECT id FROM module WHERE project_id=%s AND name=%s", (project_id, name))
        if row:
            return str(row["id"])
        mid = _uuid()
        self._execute(
            "INSERT INTO module(id,project_id,name,description,created_at) VALUES (%s,%s,%s,%s,%s)",
            (mid, project_id, name, description, _utc_now()),
        )
        return mid

    # -------------------------
    # Artifact / Evidence
    # -------------------------
    def create_artifact(
        self,
        project_id: str,
        artifact_type: str = "text",
        uri: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        aid = _uuid()
        self._execute(
            "INSERT INTO artifact(id,project_id,type,uri,metadata,created_at) "
            "VALUES (%s,%s,%s,%s,CAST(%s AS JSON),%s)",
            (aid, project_id, artifact_type, uri, json.dumps(metadata or {}, ensure_ascii=False), _utc_now()),
        )
        return aid

    def _ensure_transcript_segment_by_quote(self, artifact_id: str, quote_text: str) -> str:
        quote_text = (quote_text or "").strip()
        if not quote_text:
            return ""
        row = self._fetchone(
            "SELECT id FROM transcript_segment WHERE artifact_id=%s AND text=%s AND start_ms IS NULL AND end_ms IS NULL LIMIT 1",
            (artifact_id, quote_text),
        )
        if row:
            return str(row["id"])
        sid = _uuid()
        self._execute(
            "INSERT INTO transcript_segment(id,artifact_id,start_ms,end_ms,speaker,text,metadata,created_at) "
            "VALUES (%s,%s,NULL,NULL,NULL,%s,CAST(%s AS JSON),%s)",
            (sid, artifact_id, quote_text, json.dumps({}, ensure_ascii=False), _utc_now()),
        )
        return sid

    # -------------------------
    # Requirement Object / Revision
    # -------------------------
    def upsert_requirement(
        self,
        project_id: str,
        object_type: str,
        text_body: str,
        title: Optional[str] = None,
        rationale: Optional[str] = None,
        status: str = "Proposed",
        source_kind: str = "extracted",
        created_by: Optional[str] = None,
        quality_metrics: Optional[Dict[str, Any]] = None,
        artifact_id_for_evidence: Optional[str] = None,
        evidence_quotes: Optional[List[Tuple[str, Optional[float]]]] = None,
    ) -> ImportedRequirement:
        object_type = (object_type or "system").strip() or "system"
        norm = _normalize_text(text_body)
        if not norm:
            raise ValueError("requirement text is empty")
        object_key = _sha256_hex(norm)

        row = self._fetchone(
            "SELECT id, current_rev_id FROM requirement_object WHERE project_id=%s AND object_key=%s AND deleted_at IS NULL",
            (project_id, object_key),
        )
        if row:
            object_id = str(row["id"])
        else:
            object_id = _uuid()
            self._execute(
                "INSERT INTO requirement_object(id,project_id,current_rev_id,object_type,object_key,created_by,created_at,deleted_at) "
                "VALUES (%s,%s,NULL,%s,%s,%s,%s,NULL)",
                (object_id, project_id, object_type, object_key, created_by, _utc_now()),
            )

        rev_row = self._fetchone(
            "SELECT COALESCE(MAX(rev_no),0) AS m FROM requirement_revision WHERE object_id=%s",
            (object_id,),
        )
        next_rev_no = int((rev_row or {}).get("m") or 0) + 1
        rev_id = _uuid()
        self._execute(
            "INSERT INTO requirement_revision("
            "id,object_id,rev_no,title,text,rationale,status,source_kind,quality_metrics,created_by,created_at"
            ") VALUES (%s,%s,%s,%s,%s,%s,%s,%s,CAST(%s AS JSON),%s,%s)",
            (
                rev_id,
                object_id,
                next_rev_no,
                title,
                norm,
                rationale,
                status,
                source_kind,
                json.dumps(quality_metrics or {}, ensure_ascii=False),
                created_by,
                _utc_now(),
            ),
        )
        self._execute("UPDATE requirement_object SET current_rev_id=%s WHERE id=%s", (rev_id, object_id))

        if artifact_id_for_evidence and evidence_quotes:
            for quote, score in evidence_quotes:
                seg_id = self._ensure_transcript_segment_by_quote(artifact_id_for_evidence, quote)
                if not seg_id:
                    continue
                self._execute(
                    "INSERT INTO evidence_link(id,rev_id,transcript_segment_id,start_ms,end_ms,quote_text,score,created_at) "
                    "VALUES (%s,%s,%s,NULL,NULL,%s,%s,%s)",
                    (_uuid(), rev_id, seg_id, (quote or "")[:512], score, _utc_now()),
                )

        return ImportedRequirement(object_id=object_id, revision_id=rev_id, object_type=object_type, text=norm)

    def add_object_to_module(self, module_id: str, object_id: str, position: int, outline_level: int = 1) -> None:
        self._execute(
            "INSERT INTO module_object(module_id,object_id,position,outline_level) "
            "VALUES (%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE position=VALUES(position), outline_level=VALUES(outline_level)",
            (module_id, object_id, int(position), int(outline_level)),
        )

    # -------------------------
    # Links + validation
    # -------------------------
    def create_or_update_link(
        self,
        project_id: str,
        src_object_id: str,
        dst_object_id: str,
        link_type: str,
        confidence: Optional[float],
        evidence: Optional[Dict[str, Any]] = None,
        created_by: Optional[str] = None,
    ) -> Tuple[str, str]:
        link_type = (link_type or "general").strip() or "general"
        row = self._fetchone(
            "SELECT id FROM requirement_link WHERE project_id=%s AND src_object_id=%s AND dst_object_id=%s AND link_type=%s LIMIT 1",
            (project_id, src_object_id, dst_object_id, link_type),
        )
        if row:
            link_id = str(row["id"])
        else:
            link_id = _uuid()
            self._execute(
                "INSERT INTO requirement_link(id,project_id,src_object_id,dst_object_id,link_type,current_rev_id,created_by,created_at) "
                "VALUES (%s,%s,%s,%s,%s,NULL,%s,%s)",
                (link_id, project_id, src_object_id, dst_object_id, link_type, created_by, _utc_now()),
            )

        rev_row = self._fetchone(
            "SELECT COALESCE(MAX(rev_no),0) AS m FROM link_revision WHERE link_id=%s",
            (link_id,),
        )
        next_rev_no = int((rev_row or {}).get("m") or 0) + 1
        link_rev_id = _uuid()
        self._execute(
            "INSERT INTO link_revision("
            "id,link_id,rev_no,confidence,validation_status,validation_by,validation_at,comment,evidence,created_by,created_at"
            ") VALUES (%s,%s,%s,%s,'proposed',NULL,NULL,NULL,CAST(%s AS JSON),%s,%s)",
            (link_rev_id, link_id, next_rev_no, confidence, json.dumps(evidence or {}, ensure_ascii=False), created_by, _utc_now()),
        )
        self._execute("UPDATE requirement_link SET current_rev_id=%s WHERE id=%s", (link_rev_id, link_id))
        return link_id, link_rev_id

    def list_link_revisions(self, project_id: str, status: str = "proposed", limit: int = 50) -> List[Dict[str, Any]]:
        limit = max(1, min(500, int(limit)))
        status = (status or "proposed").strip() or "proposed"
        rows = self._fetchall(
            "SELECT lr.id, lr.link_id, lr.rev_no, lr.confidence, lr.validation_status, lr.created_at, "
            "l.link_type, l.src_object_id, l.dst_object_id "
            "FROM link_revision lr "
            "JOIN requirement_link l ON l.id = lr.link_id "
            "WHERE l.project_id=%s AND lr.validation_status=%s "
            "ORDER BY lr.created_at DESC LIMIT %s",
            (project_id, status, limit),
        )
        return [
            {
                "link_revision_id": str(r["id"]),
                "link_id": str(r["link_id"]),
                "rev_no": int(r["rev_no"]),
                "confidence": float(r["confidence"]) if r["confidence"] is not None else None,
                "validation_status": str(r["validation_status"]),
                "created_at": str(r["created_at"]),
                "link_type": str(r["link_type"]),
                "src_object_id": str(r["src_object_id"]),
                "dst_object_id": str(r["dst_object_id"]),
            }
            for r in rows
        ]

    def validate_link_revision(
        self,
        link_id: str,
        validation_status: str,
        validation_by: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> Dict[str, Any]:
        validation_status = (validation_status or "").strip().lower()
        if validation_status not in ("accepted", "rejected", "needs_review"):
            raise ValueError("validation_status must be one of: accepted/rejected/needs_review")

        row = self._fetchone("SELECT current_rev_id FROM requirement_link WHERE id=%s", (link_id,))
        if not row or not row.get("current_rev_id"):
            raise ValueError("link not found or has no current revision")
        current_rev_id = str(row["current_rev_id"])

        cur = self._fetchone("SELECT confidence, evidence FROM link_revision WHERE id=%s", (current_rev_id,))
        if not cur:
            raise ValueError("current link revision not found")

        rev_row = self._fetchone("SELECT COALESCE(MAX(rev_no),0) AS m FROM link_revision WHERE link_id=%s", (link_id,))
        next_rev_no = int((rev_row or {}).get("m") or 0) + 1

        new_rev_id = _uuid()
        self._execute(
            "INSERT INTO link_revision("
            "id,link_id,rev_no,confidence,validation_status,validation_by,validation_at,comment,evidence,created_by,created_at"
            ") VALUES (%s,%s,%s,%s,%s,%s,%s,%s,CAST(%s AS JSON),%s,%s)",
            (
                new_rev_id,
                link_id,
                next_rev_no,
                cur.get("confidence"),
                validation_status,
                validation_by,
                _utc_now(),
                comment,
                cur.get("evidence") if isinstance(cur.get("evidence"), str) else json.dumps(cur.get("evidence") or {}, ensure_ascii=False),
                validation_by,
                _utc_now(),
            ),
        )
        self._execute("UPDATE requirement_link SET current_rev_id=%s WHERE id=%s", (new_rev_id, link_id))
        return {"link_id": link_id, "link_revision_id": new_rev_id, "validation_status": validation_status}

