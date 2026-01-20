"""
需求抽取服务
整合 EgoBundle 生成、Planner 调用和 Executor 执行的完整流程
"""
import json
import logging
import re
from typing import Any, Dict, List, Optional, Sequence

import psycopg2
from psycopg2.extras import RealDictCursor

from backend_business.services.ai_proxy import ai_proxy
from backend_business.services.ego_bundle_generator import EgoBundleGenerator
from backend_business.services.requirements_executor import (
    RequirementsExecutor,
    RequirementToolDef,
)

logger = logging.getLogger(__name__)


class RequirementsExtractionService:
    """
    L1-L3 需求抽取服务
    """

    def __init__(self, dsn: str):
        self.dsn = dsn
        self.bundle_generator = EgoBundleGenerator(
            max_spans_per_bundle=12,
            token_limit=1500,
        )
        self.executor = RequirementsExecutor(dsn)

    def _connect(self) -> psycopg2.extensions.connection:
        return psycopg2.connect(self.dsn)

    def extract_requirements_for_session(
        self,
        session_id: str,
        context_run_id: Optional[str] = None,
        bundle_strategy: str = "sequence",
        anchor_strategy: str = "informative",
        r: int = 2,
        model_name: str = "deepseek-chat",
        use_toolcall: bool = True,
        adaptive_retry_r2: Optional[bool] = None,
        max_spans_per_bundle: Optional[int] = None,
        token_limit: Optional[int] = None,
        top_m_2hop: Optional[int] = None,
        keywords: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        """
        对指定 session 进行 L1-L3 需求抽取

        Args:
            session_id: 会话 ID
            context_run_id: 上下文运行 ID（可选，用于基于图邻域的策略）
            bundle_strategy: bundle 生成策略
                - "sequence": 基于序列窗口
                - "graph": 基于图邻域（需要 context_run_id）
            anchor_strategy: 锚点选择策略
                - "all": 所有 span 都作为锚点
                - "keyword": 包含关键词的 span
                - "informative": 信息量大的 span（推荐）
            r: 最大邻域半径（sequence 策略）或跳数（graph 策略），优先用 r=1，不足时自动重试到 r=2
            model_name: 使用的模型名称
            use_toolcall: 是否使用 DeepSeek API tool call 格式（默认为 True）
            adaptive_retry_r2: r>=2 时是否自动尝试 r=2（默认 True）
            max_spans_per_bundle: 每个 EgoBundle 最多 spans 数（默认 12）
            token_limit: 每个 EgoBundle 大概字数上限（默认 1500，None 表示不限制）
            top_m_2hop: 2-hop 邻居 Top-M（默认 5）
            keywords: 锚点关键词（用于 keyword/informative 策略）

        Returns:
            抽取结果统计
        """
        result = {
            "session_id": session_id,
            "bundle_strategy": bundle_strategy,
            "anchor_strategy": anchor_strategy,
            "r": r,
            "use_toolcall": use_toolcall,
            "adaptive_retry_r2": adaptive_retry_r2,
            "max_spans_per_bundle": max_spans_per_bundle,
            "token_limit": token_limit,
            "top_m_2hop": top_m_2hop,
            "keywords": keywords,
            "total_spans": 0,
            "total_anchors": 0,
            "bundles_processed": 0,
            "total_inserted": 0,
            "total_duplicates": 0,
            "errors": [],
        }

        max_r = self._normalize_max_r(r)
        result["r"] = max_r
        if adaptive_retry_r2 is None:
            adaptive_retry_r2 = True
        result["adaptive_retry_r2"] = adaptive_retry_r2

        def _safe_int(value: Any, default: int) -> int:
            try:
                if value in (None, ""):
                    return default
                return int(value)
            except (TypeError, ValueError):
                return default

        effective_max_spans = _safe_int(max_spans_per_bundle, 12)
        effective_top_m_2hop = _safe_int(top_m_2hop, 5)

        try:
            token_limit_int = None if token_limit in (None, "", 0, "0") else int(token_limit)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            token_limit_int = 1500
        effective_token_limit = token_limit_int

        def _normalize_keywords(value: Optional[Sequence[str]]) -> Optional[List[str]]:
            if not value:
                return None
            if isinstance(value, str):
                parts = re.split(r"[,，;\n|]+", value)
                normalized = [p.strip() for p in parts if p.strip()]
                return normalized or None
            normalized = [str(v).strip() for v in value if str(v).strip()]
            return normalized or None

        effective_keywords = _normalize_keywords(keywords)
        result["max_spans_per_bundle"] = effective_max_spans
        result["token_limit"] = effective_token_limit
        result["top_m_2hop"] = effective_top_m_2hop
        result["keywords"] = effective_keywords

        bundle_generator = EgoBundleGenerator(
            max_spans_per_bundle=effective_max_spans,
            token_limit=effective_token_limit,
        )

        # 1. 获取 session 的所有 spans
        spans = self._get_spans_by_session(session_id)
        result["total_spans"] = len(spans)

        if not spans:
            result["errors"].append("No spans found for this session")
            return result

        # 2. 选择锚点
        anchor_indices = bundle_generator.select_anchors(
            spans, strategy=anchor_strategy, keywords=effective_keywords
        )
        result["total_anchors"] = len(anchor_indices)

        if not anchor_indices:
            result["errors"].append("No anchors selected")
            return result

        adjacency = None
        if bundle_strategy == "graph":
            if not context_run_id:
                result["errors"].append("context_run_id is required for graph strategy")
                return result
            edges = self._get_edges_by_run(context_run_id)
            adjacency = bundle_generator.build_adjacency_from_edges(edges)

        # 3. 对每个锚点生成 EgoBundle 并抽取
        for anchor_idx in anchor_indices:
            try:
                if bundle_strategy == "graph" and not context_run_id:
                    result["errors"].append("context_run_id is required for graph strategy")
                    break
                if bundle_strategy not in {"sequence", "graph"}:
                    result["errors"].append(f"Unknown bundle strategy: {bundle_strategy}")
                    break

                exec_result = None
                bundle_r = None
                attempt_rs = [max_r] if not adaptive_retry_r2 else self._build_attempt_r_values(max_r)
                for attempt_r in attempt_rs:
                    # 3.1 生成 EgoBundle
                    if bundle_strategy == "sequence":
                        bundle = bundle_generator.generate_sequence_bundle(
                            spans, anchor_idx, attempt_r
                        )
                    elif bundle_strategy == "graph":
                        bundle = bundle_generator.generate_graph_bundle(
                            spans,
                            anchor_idx,
                            adjacency or {},
                            hop=attempt_r,
                            top_m_2hop=effective_top_m_2hop,
                        )

                    # 3.2 调用 Planner（大模型）- 使用 tool call 格式
                    planner_result = self._call_planner(bundle, model_name, use_toolcall=use_toolcall)
                    if planner_result.get("error"):
                        exec_result = {
                            "status": "planner_error",
                            "parsed_count": 0,
                            "validation_errors": [],
                            "quota_error": None,
                            "inserted": 0,
                            "duplicates": 0,
                            "db_errors": [],
                            "planner_error": planner_result.get("error"),
                        }
                        bundle_r = bundle["r"]
                        break

                    # 3.3 执行器校验并落库
                    exec_result = self.executor.execute_bundle(
                        session_id=session_id,
                        anchor_span_id=bundle["anchor_span_id"],
                        r=bundle["r"],
                        model_output=planner_result["output"],
                        use_toolcall_format=use_toolcall,
                    )
                    bundle_r = bundle["r"]

                    result["total_inserted"] += exec_result["inserted"]
                    result["total_duplicates"] += exec_result["duplicates"]

                    if not self._is_insufficient_output(exec_result):
                        break

                if not exec_result:
                    continue

                result["bundles_processed"] += 1

                if exec_result and exec_result["status"] not in ["success", "empty"]:
                    error_entry = {
                        "anchor_idx": anchor_idx,
                        "status": exec_result["status"],
                        "details": exec_result,
                    }
                    if bundle_r is not None:
                        error_entry["r"] = bundle_r
                    result["errors"].append(error_entry)

            except Exception as e:
                logger.exception(f"Error processing anchor {anchor_idx}")
                result["errors"].append(
                    {
                        "anchor_idx": anchor_idx,
                        "error": str(e),
                    }
                )

        return result

    @staticmethod
    def _normalize_max_r(r_value: Any) -> int:
        try:
            value = int(r_value)
        except (TypeError, ValueError):
            value = 2
        return 1 if value <= 1 else 2

    @staticmethod
    def _build_attempt_r_values(max_r: int) -> List[int]:
        return [1, 2] if max_r >= 2 else [1]

    @staticmethod
    def _is_insufficient_output(exec_result: Optional[Dict[str, Any]]) -> bool:
        if not exec_result:
            return True
        status = exec_result.get("status")
        if status in {"empty", "invalid_format", "validation_failed"}:
            return True
        parsed_count = exec_result.get("parsed_count", 0)
        inserted = exec_result.get("inserted", 0)
        duplicates = exec_result.get("duplicates", 0)
        if parsed_count == 0:
            return True
        if inserted == 0 and duplicates == 0:
            return True
        return False

    def _get_spans_by_session(self, session_id: str) -> List[Dict[str, Any]]:
        """
        获取指定 session 的所有 spans，按 start_ms 排序
        """
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT span_id, session_id, start_ms, end_ms, speaker, text, asr_confidence, meta_json
                    FROM spans
                    WHERE session_id = %s
                    ORDER BY start_ms ASC, span_id ASC
                    """,
                    (session_id,),
                )
                return [dict(row) for row in cur.fetchall()]

    def _get_edges_by_run(self, context_run_id: str) -> List[Dict[str, Any]]:
        """
        获取指定 context_run 的所有关联边
        """
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT source_span_id, target_span_id, relation_type, strength
                    FROM span_links
                    WHERE context_run_id = %s
                    """,
                    (context_run_id,),
                )
                return [dict(row) for row in cur.fetchall()]

    def _call_planner(
        self, bundle: Dict[str, Any], model_name: str, use_toolcall: bool = True
    ) -> Dict[str, Any]:
        """
        调用 Planner（大模型）进行需求抽取

        Args:
            bundle: EgoBundle
            model_name: 模型名称
            use_toolcall: 是否使用 DeepSeek API tool call 格式（默认为 True）

        Returns:
            Planner 输出
        """
        # 构建 Prompt
        prompt = self._build_extraction_prompt(bundle, use_toolcall=use_toolcall)
        system_prompt = RequirementToolDef.get_system_prompt()

        if use_toolcall:
            # 使用 DeepSeek API tool call 格式
            try:
                tools = RequirementToolDef.get_tools_list()
                response = ai_proxy.chat_completion_with_tools(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    tools=tools,
                    model=model_name,
                    temperature=0.3,
                    tool_choice="auto",  # 让模型自动决定是否调用工具
                )
                # tool_calls 格式返回
                tool_calls = response.get("tool_calls")
                content = response.get("content", "")
                finish_reason = response.get("finish_reason")
                
                return {
                    "prompt": prompt,
                    "system_prompt": system_prompt,
                    "output": tool_calls,  # 返回 tool_calls 列表
                    "content": content,  # 可能有的文本内容
                    "finish_reason": finish_reason,
                    "model": model_name,
                    "use_toolcall": True,
                }
            except Exception as e:
                logger.exception("Error calling planner with tool call")
                return {
                    "prompt": prompt,
                    "system_prompt": system_prompt,
                    "output": None,
                    "content": "",
                    "finish_reason": "error",
                    "model": model_name,
                    "use_toolcall": True,
                    "status": "error",
                    "error": str(e),
                }
        else:
            # 旧的文本生成方式
            try:
                response = ai_proxy.chat_completion(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    model=model_name,
                    temperature=0.3,
                )
                output = response.get("content", "")
            except Exception as e:
                logger.exception("Error calling planner")
                return {
                    "prompt": prompt,
                    "system_prompt": system_prompt,
                    "output": None,
                    "model": model_name,
                    "use_toolcall": False,
                    "status": "error",
                    "error": str(e),
                }

            return {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "output": output,
                "model": model_name,
                "use_toolcall": False,
            }

    def _build_extraction_prompt(self, bundle: Dict[str, Any], use_toolcall: bool = True) -> str:
        """
        构建需求抽取 Prompt

        Args:
            bundle: EgoBundle
            use_toolcall: 是否使用 tool call 格式

        Returns:
            Prompt 字符串
        """
        lines = []
        lines.append("# 上下文片段")
        lines.append("")

        for i, span in enumerate(bundle["spans"]):
            ref = bundle["span_refs"][i]
            speaker = span.get("speaker", "未知")
            text = span.get("text", "")
            start_ms = span.get("start_ms")
            end_ms = span.get("end_ms")

            time_info = ""
            if start_ms is not None and end_ms is not None:
                time_info = f" [{start_ms}ms - {end_ms}ms]"

            lines.append(f"**{ref}**{time_info} {speaker}: {text}")
            lines.append("")

        lines.append("---")
        lines.append("")
        lines.append("# 任务")
        lines.append("")
        
        if use_toolcall:
            lines.append("基于上述上下文片段，请使用 create_req 工具抽取 L1/L2/L3 需求。")
            lines.append("对于每个识别到的需求，调用一次 create_req 工具。")
        else:
            lines.append("基于上述上下文片段，使用 create_req 工具抽取 L1/L2/L3 需求。")
            lines.append("")
            lines.append("**输出格式示例：**")
            lines.append('CALL create_req level="L1" text="提升借用审批效率并降低人工核验成本"')
            lines.append('CALL create_req level="L2" text="系统应支持在线提交借用申请"')
            lines.append('CALL create_req level="L3" text="系统必须在 2 秒内完成审批流程验证"')

        return "\n".join(lines)

    def get_requirements_by_session(
        self,
        session_id: str,
        level: Optional[str] = None,
        page: int = 1,
        per_page: int = 50,
    ) -> Dict[str, Any]:
        """
        查询指定 session 的需求

        Args:
            session_id: 会话 ID
            level: 需求层级过滤（可选）
            page: 页码
            per_page: 每页数量

        Returns:
            需求列表和分页信息
        """
        page = max(1, page)
        per_page = max(1, min(200, per_page))
        offset = (page - 1) * per_page

        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 计数
                if level:
                    cur.execute(
                        "SELECT COUNT(1) AS c FROM requirements_l123 WHERE session_id = %s AND level = %s",
                        (session_id, level),
                    )
                else:
                    cur.execute(
                        "SELECT COUNT(1) AS c FROM requirements_l123 WHERE session_id = %s",
                        (session_id,),
                    )
                total = cur.fetchone()["c"]

                # 查询
                if level:
                    cur.execute(
                        """
                        SELECT req_id, session_id, level, text, fingerprint, anchor_span_id, r, created_at::text AS created_at
                        FROM requirements_l123
                        WHERE session_id = %s AND level = %s
                        ORDER BY created_at DESC
                        LIMIT %s OFFSET %s
                        """,
                        (session_id, level, per_page, offset),
                    )
                else:
                    cur.execute(
                        """
                        SELECT req_id, session_id, level, text, fingerprint, anchor_span_id, r, created_at::text AS created_at
                        FROM requirements_l123
                        WHERE session_id = %s
                        ORDER BY level ASC, created_at DESC
                        LIMIT %s OFFSET %s
                        """,
                        (session_id, per_page, offset),
                    )

                requirements = [dict(row) for row in cur.fetchall()]

        return {
            "requirements": requirements,
            "total": total,
            "pages": (total + per_page - 1) // per_page,
            "current_page": page,
            "per_page": per_page,
        }

    def get_requirement_detail(self, req_id: str) -> Optional[Dict[str, Any]]:
        """
        获取需求详情
        """
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT req_id, session_id, level, text, fingerprint, anchor_span_id, r, created_at::text AS created_at
                    FROM requirements_l123
                    WHERE req_id = %s
                    """,
                    (req_id,),
                )
                row = cur.fetchone()
                return dict(row) if row else None

    def delete_requirement(self, req_id: str) -> bool:
        """
        删除需求
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM requirements_l123 WHERE req_id = %s", (req_id,))
                return cur.rowcount > 0

    def get_statistics(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        获取需求统计信息
        """
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if session_id:
                    cur.execute(
                        "SELECT COUNT(1) AS c FROM requirements_l123 WHERE session_id = %s",
                        (session_id,),
                    )
                    total = cur.fetchone()["c"]
                    cur.execute(
                        """
                        SELECT level, COUNT(1) AS c
                        FROM requirements_l123
                        WHERE session_id = %s
                        GROUP BY level
                        ORDER BY level
                        """,
                        (session_id,),
                    )
                else:
                    cur.execute("SELECT COUNT(1) AS c FROM requirements_l123")
                    total = cur.fetchone()["c"]
                    cur.execute(
                        """
                        SELECT level, COUNT(1) AS c
                        FROM requirements_l123
                        GROUP BY level
                        ORDER BY level
                        """
                    )

                level_stats = {row["level"]: row["c"] for row in cur.fetchall()}

        return {
            "total": total,
            "by_level": level_stats,
        }
