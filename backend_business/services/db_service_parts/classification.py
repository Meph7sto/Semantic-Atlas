import json
from typing import Any, Dict, List, Optional

from psycopg2.extras import RealDictCursor

from backend_business.services.db_service_parts.utils import _utc_now_iso


class ClassificationAnalysisMixin:
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

