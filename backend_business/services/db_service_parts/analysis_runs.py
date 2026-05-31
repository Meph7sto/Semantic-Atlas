import json
import uuid
from typing import Any, Dict, List, Optional

from psycopg2.extras import RealDictCursor

from backend_business.services.db_service_parts.utils import _utc_now_iso


def _parse_json_field(value: Any, fallback: Any):
    if value is None:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return fallback
    return fallback


class RequirementsAnalysisRunMixin:
    def save_requirements_analysis_run(
        self,
        session_id: str,
        trace_result: Dict[str, Any],
        conflict_result: Dict[str, Any],
        classification_result: Dict[str, Any],
        *,
        project_id: Optional[str] = None,
        context_run_id: Optional[str] = None,
        high_level_requirements: Optional[List[Dict[str, Any]]] = None,
        low_level_requirements: Optional[List[Dict[str, Any]]] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> str:
        analysis_run_id = uuid.uuid4().hex
        high_level_requirements = high_level_requirements or []
        low_level_requirements = low_level_requirements or []
        conflict_items = list((conflict_result or {}).get("items") or [])
        predictions = list((classification_result or {}).get("predictions") or [])

        summary = {
            "high_level_count": len(high_level_requirements),
            "low_level_count": len(low_level_requirements),
            "trace_relations_count": len((trace_result or {}).get("relations") or []),
            "conflict_total": len(conflict_items),
            "confirmed_conflict_count": sum(
                1 for item in conflict_items if item.get("verdict") == "confirmed"
            ),
            "suspected_conflict_count": sum(
                1 for item in conflict_items if item.get("verdict") == "suspected"
            ),
            "classification_total": (classification_result or {}).get("total")
            or len(predictions),
        }
        merged_meta = {**(meta or {}), "summary": summary}

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO requirements_analysis_runs (
                        analysis_run_id, session_id, project_id, context_run_id,
                        high_level_requirements, low_level_requirements,
                        trace_result, conflict_result, classification_result,
                        meta_json, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        analysis_run_id,
                        session_id,
                        project_id,
                        context_run_id,
                        json.dumps(high_level_requirements, ensure_ascii=False),
                        json.dumps(low_level_requirements, ensure_ascii=False),
                        json.dumps(trace_result or {}, ensure_ascii=False),
                        json.dumps(conflict_result or {}, ensure_ascii=False),
                        json.dumps(classification_result or {}, ensure_ascii=False),
                        json.dumps(merged_meta, ensure_ascii=False),
                        _utc_now_iso(),
                    ),
                )

        return analysis_run_id

    def list_requirements_analysis_runs(
        self,
        session_id: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT analysis_run_id, session_id, project_id, context_run_id, meta_json, created_at::text AS created_at
                    FROM requirements_analysis_runs
                    WHERE session_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (session_id, max(1, min(int(limit), 100))),
                )
                rows = cur.fetchall()

        result = []
        for row in rows:
            item = dict(row)
            item["meta"] = _parse_json_field(item.pop("meta_json", None), {})
            result.append(item)
        return result

    def get_requirements_analysis_run(
        self,
        analysis_run_id: str,
    ) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT analysis_run_id, session_id, project_id, context_run_id,
                           high_level_requirements, low_level_requirements,
                           trace_result, conflict_result, classification_result,
                           meta_json, created_at::text AS created_at
                    FROM requirements_analysis_runs
                    WHERE analysis_run_id = %s
                    LIMIT 1
                    """,
                    (analysis_run_id,),
                )
                row = cur.fetchone()
        if not row:
            return None
        return self._serialize_requirements_analysis_run(dict(row))

    def get_latest_requirements_analysis_run(
        self,
        session_id: str,
    ) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT analysis_run_id, session_id, project_id, context_run_id,
                           high_level_requirements, low_level_requirements,
                           trace_result, conflict_result, classification_result,
                           meta_json, created_at::text AS created_at
                    FROM requirements_analysis_runs
                    WHERE session_id = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (session_id,),
                )
                row = cur.fetchone()
        if not row:
            return None
        return self._serialize_requirements_analysis_run(dict(row))

    def _serialize_requirements_analysis_run(
        self,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        payload["high_level_requirements"] = _parse_json_field(
            payload.get("high_level_requirements"), []
        )
        payload["low_level_requirements"] = _parse_json_field(
            payload.get("low_level_requirements"), []
        )
        payload["trace_result"] = _parse_json_field(payload.get("trace_result"), {})
        payload["conflict_result"] = _parse_json_field(
            payload.get("conflict_result"), {}
        )
        payload["classification_result"] = _parse_json_field(
            payload.get("classification_result"), {}
        )
        payload["meta"] = _parse_json_field(payload.pop("meta_json", None), {})
        return payload
