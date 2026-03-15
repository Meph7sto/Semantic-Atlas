import difflib
import json
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from psycopg2.extras import RealDictCursor

from backend_business.services.db_service_parts.utils import _utc_now_iso


class L4RequirementsMixin:
    # L4 去重阈值常量
    _L4_EXACT_DUP_RATIO = 0.95  # 高于此阈值直接跳过（明显重复）
    _L4_FUZZY_DUP_RATIO = 0.7   # 高于此阈值需要大模型判断

    def _normalize_l4_text(self, text: str) -> str:
        """归一化 L4 需求文本用于相似度比较"""
        normalized = text.strip().lower()
        # 移除所有空白字符
        normalized = re.sub(r"\s+", "", normalized)
        # 移除标点符号
        normalized = re.sub(r"[，,。.!！？?；;:：\-—（）()\[\]【】""\"'`]", "", normalized)
        return normalized

    def _check_l4_duplicate(
        self,
        new_text: str,
        existing_texts: List[str],
        use_llm: bool = True,
    ) -> Tuple[bool, Optional[str]]:
        """
        检查 L4 需求是否重复

        Args:
            new_text: 新需求文本
            existing_texts: 已存在的需求文本列表
            use_llm: 是否使用大模型判断模糊重复

        Returns:
            (is_duplicate, matched_text)
        """
        normalized_new = self._normalize_l4_text(new_text)
        if not normalized_new:
            return False, None

        for existing in existing_texts:
            normalized_existing = self._normalize_l4_text(existing)
            if not normalized_existing:
                continue

            ratio = difflib.SequenceMatcher(
                None, normalized_new, normalized_existing
            ).ratio()

            if ratio >= self._L4_EXACT_DUP_RATIO:
                # 明显重复，直接跳过
                return True, existing

            if ratio >= self._L4_FUZZY_DUP_RATIO and use_llm:
                # 疑似重复，调用大模型判断
                is_dup = self._llm_judge_duplicate(new_text, existing)
                if is_dup:
                    return True, existing

        return False, None

    def _llm_judge_duplicate(self, text_a: str, text_b: str) -> bool:
        """调用大模型判断两个需求是否语义重复"""
        # 延迟导入，避免循环依赖
        from backend_business.services.ai_proxy import ai_proxy

        prompt = f"""判断以下两个软件需求是否表达相同的含义（语义重复）。

需求 A: {text_a}

需求 B: {text_b}

如果它们描述的是同一个功能/约束，只是措辞不同，则回答 "是"。
如果它们描述的是不同的功能/约束，则回答 "否"。

只回答"是"或"否"，不要解释。"""

        try:
            response = ai_proxy.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model="deepseek-chat",
                temperature=0,
                max_tokens=10,
            )
            answer = response.get("content", "").strip().lower()
            return answer in ("是", "yes", "true", "1")
        except Exception as e:
            # 大模型调用失败时，保守处理：不认为是重复
            print(f"[L4去重] 大模型判断失败: {e}")
            return False

    def _load_existing_l4_texts(self, session_id: str) -> List[str]:
        """加载指定 session 已有的 L4 需求文本"""
        texts = []
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT text FROM low_level_requirements WHERE session_id = %s",
                    (session_id,),
                )
                for row in cur.fetchall():
                    if row[0]:
                        texts.append(row[0])
        return texts

    def save_l4_requirements(
        self,
        session_id: str,
        l4_requirements: List[Dict[str, Any]],
        use_dedup: bool = True,
    ) -> Dict[str, Any]:
        """
        保存 L4 需求到数据库，带去重机制

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
            use_dedup: 是否启用去重（默认 True）

        Returns:
            {
                "inserted": 插入数量,
                "duplicates": 去重跳过数量,
                "inserted_ids": 插入的 req_id 列表,
            }
        """
        if not l4_requirements:
            return {"inserted": 0, "duplicates": 0, "inserted_ids": []}

        # 加载现有需求文本用于去重
        existing_texts = self._load_existing_l4_texts(session_id) if use_dedup else []

        inserted_ids = []
        duplicates = 0

        with self._connect() as conn:
            with conn.cursor() as cur:
                for req in l4_requirements:
                    req_id = (
                        req.get("l4_id") or req.get("req_id") or f"L4-{_utc_now_iso()}"
                    )
                    text = req.get("shall_statement") or req.get("text") or ""

                    # 去重检查
                    if use_dedup and text:
                        is_dup, matched = self._check_l4_duplicate(text, existing_texts)
                        if is_dup:
                            duplicates += 1
                            print(f"[L4去重] 跳过重复需求: '{text[:50]}...' 匹配: '{matched[:50] if matched else ''}...'")
                            continue

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

                    # 将新插入的文本加入已存在列表，用于后续去重
                    if use_dedup and text:
                        existing_texts.append(text)

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

        if duplicates > 0:
            print(f"[L4去重] 本次保存: 插入 {len(inserted_ids)} 条，跳过重复 {duplicates} 条")

        return {
            "inserted": len(inserted_ids),
            "duplicates": duplicates,
            "inserted_ids": inserted_ids,
        }

    def get_l4_requirements_by_session(
        self,
        session_id: str,
        page: int = 1,
        per_page: int = 100,
        top_req_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        查询指定 session 的 L4 底层需求
        """
        page = max(1, int(page))
        per_page = max(1, min(500, int(per_page)))
        offset = (page - 1) * per_page

        if top_req_ids:
            with self._connect() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT COUNT(DISTINCT l.req_id) AS c
                        FROM low_level_requirements l
                        JOIN low_level_requirement_links lk
                          ON lk.req_id = l.req_id AND lk.session_id = l.session_id
                        WHERE l.session_id = %s AND lk.top_req_id = ANY(%s::text[])
                        """,
                        (session_id, top_req_ids),
                    )
                    total = cur.fetchone()["c"]

                    cur.execute(
                        """
                        SELECT DISTINCT ON (l.req_id)
                            l.req_id, l.session_id, l.source_top_id, l.source_top_text,
                            l.text, l.component, l.acceptance_criteria, l.test_method,
                            l.interfaces, l.data_contracts, l.error_handling, l.nfr,
                            l.open_questions, l.evidence_ids, l.confidence, l.source,
                            l.created_at::text AS created_at
                        FROM low_level_requirements l
                        JOIN low_level_requirement_links lk
                          ON lk.req_id = l.req_id AND lk.session_id = l.session_id
                        WHERE l.session_id = %s AND lk.top_req_id = ANY(%s::text[])
                        ORDER BY l.req_id, l.created_at DESC
                        LIMIT %s OFFSET %s
                        """,
                        (session_id, top_req_ids, per_page, offset),
                    )
                    rows = cur.fetchall()

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

            requirements = []
            for row in rows:
                req = dict(row)
                for key in ("acceptance_criteria", "interfaces", "data_contracts",
                            "error_handling", "nfr", "open_questions", "evidence_ids"):
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

    def get_existing_top_req_ids(self, session_id: str, top_req_ids: List[str]) -> List[str]:
        if not top_req_ids:
            return []
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT top_req_id
                    FROM low_level_requirement_links
                    WHERE session_id = %s AND top_req_id = ANY(%s::text[])
                    """,
                    (session_id, top_req_ids),
                )
                return [row[0] for row in cur.fetchall()]

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
