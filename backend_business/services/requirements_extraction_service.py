"""
需求抽取服务
整合 EgoBundle 生成、Planner 调用和 Executor 执行的完整流程
"""
import json
import logging
from typing import Any, Dict, List, Optional

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
            r: 邻域半径（sequence 策略）或跳数（graph 策略）
            model_name: 使用的模型名称

        Returns:
            抽取结果统计
        """
        result = {
            "session_id": session_id,
            "bundle_strategy": bundle_strategy,
            "anchor_strategy": anchor_strategy,
            "r": r,
            "total_spans": 0,
            "total_anchors": 0,
            "bundles_processed": 0,
            "total_inserted": 0,
            "total_duplicates": 0,
            "errors": [],
        }

        # 1. 获取 session 的所有 spans
        spans = self._get_spans_by_session(session_id)
        result["total_spans"] = len(spans)

        if not spans:
            result["errors"].append("No spans found for this session")
            return result

        # 2. 选择锚点
        anchor_indices = self.bundle_generator.select_anchors(
            spans, strategy=anchor_strategy
        )
        result["total_anchors"] = len(anchor_indices)

        if not anchor_indices:
            result["errors"].append("No anchors selected")
            return result

        # 3. 对每个锚点生成 EgoBundle 并抽取
        for anchor_idx in anchor_indices:
            try:
                # 3.1 生成 EgoBundle
                if bundle_strategy == "sequence":
                    bundle = self.bundle_generator.generate_sequence_bundle(
                        spans, anchor_idx, r
                    )
                elif bundle_strategy == "graph":
                    if not context_run_id:
                        result["errors"].append(
                            "context_run_id is required for graph strategy"
                        )
                        break
                    # 获取关联边
                    edges = self._get_edges_by_run(context_run_id)
                    adjacency = self.bundle_generator.build_adjacency_from_edges(edges)
                    bundle = self.bundle_generator.generate_graph_bundle(
                        spans, anchor_idx, adjacency, hop=r
                    )
                else:
                    result["errors"].append(f"Unknown bundle strategy: {bundle_strategy}")
                    break

                # 3.2 调用 Planner（大模型）
                planner_result = self._call_planner(bundle, model_name)

                # 3.3 执行器校验并落库
                exec_result = self.executor.execute_bundle(
                    session_id=session_id,
                    anchor_span_id=bundle["anchor_span_id"],
                    r=bundle["r"],
                    model_output=planner_result["output"],
                )

                result["bundles_processed"] += 1
                result["total_inserted"] += exec_result["inserted"]
                result["total_duplicates"] += exec_result["duplicates"]

                if exec_result["status"] not in ["success", "empty"]:
                    result["errors"].append(
                        {
                            "anchor_idx": anchor_idx,
                            "status": exec_result["status"],
                            "details": exec_result,
                        }
                    )

            except Exception as e:
                logger.exception(f"Error processing anchor {anchor_idx}")
                result["errors"].append(
                    {
                        "anchor_idx": anchor_idx,
                        "error": str(e),
                    }
                )

        return result

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
        self, bundle: Dict[str, Any], model_name: str
    ) -> Dict[str, Any]:
        """
        调用 Planner（大模型）进行需求抽取

        Args:
            bundle: EgoBundle
            model_name: 模型名称

        Returns:
            Planner 输出
        """
        # 构建 Prompt
        prompt = self._build_extraction_prompt(bundle)
        system_prompt = RequirementToolDef.get_system_prompt()

        # 调用模型
        # 注意：这里使用简单的文本生成，未来可以扩展为支持工具调用的接口
        try:
            response = ai_proxy.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                model=model_name,
                temperature=0.3,  # 降低温度以获得更稳定的输出
            )
            output = response.get("content", "")
        except Exception as e:
            logger.exception("Error calling planner")
            output = ""

        return {
            "prompt": prompt,
            "system_prompt": system_prompt,
            "output": output,
            "model": model_name,
        }

    def _build_extraction_prompt(self, bundle: Dict[str, Any]) -> str:
        """
        构建需求抽取 Prompt

        Args:
            bundle: EgoBundle

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
