from typing import Any, Dict, List


class SpansMixin:
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
