"""
Serial single-anchor processing pipeline for requirements extraction
"""

import logging
from typing import Any, Dict, List, Optional

from backend_business.services.ego_bundle_generator import EgoBundleGenerator
from backend_business.services.requirements_executor import RequirementsExecutor

from .data_access import RequirementsDataAccess
from .models import AnchorResult
from .planner import call_planner
from .utils import build_attempt_r_values, is_insufficient_output

logger = logging.getLogger(__name__)


def _generate_bundle(
    bundle_generator: EgoBundleGenerator,
    spans: List[Dict[str, Any]],
    anchor_idx: int,
    bundle_strategy: str,
    attempt_r: int,
    adjacency: Optional[Dict],
    effective_top_m_2hop: int,
) -> Dict[str, Any]:
    """根据策略生成 bundle"""
    if bundle_strategy == "sequence":
        return bundle_generator.generate_sequence_bundle(spans, anchor_idx, attempt_r)
    elif bundle_strategy == "graph":
        return bundle_generator.generate_graph_bundle(
            spans,
            anchor_idx,
            adjacency or {},
            hop=attempt_r,
            top_m_2hop=effective_top_m_2hop,
        )
    else:
        raise ValueError(f"Unknown bundle strategy: {bundle_strategy}")


def _make_planner_error_result(error_msg: str) -> Dict[str, Any]:
    """构建 planner 错误结果"""
    return {
        "status": "planner_error",
        "parsed_count": 0,
        "validation_errors": [],
        "quota_error": None,
        "inserted": 0,
        "duplicates": 0,
        "updated": 0,
        "db_errors": [],
        "planner_error": error_msg,
    }


def process_single_anchor_serial(
    anchor_idx: int,
    spans: List[Dict[str, Any]],
    bundle_generator: EgoBundleGenerator,
    executor: RequirementsExecutor,
    data_access: RequirementsDataAccess,
    bundle_strategy: str,
    adjacency: Optional[Dict],
    max_r: int,
    adaptive_retry_r2: bool,
    effective_top_m_2hop: int,
    session_id: str,
    model_name: str,
    use_toolcall: bool,
    history_aware: bool,
    existing_requirements: Optional[List[Dict[str, Any]]] = None,
) -> AnchorResult:
    """
    串行处理单个锚点的完整管线:
    尝试不同 r 值 → 生成 bundle → 调用 planner → 调用 executor → 判断是否重试

    Returns:
        AnchorResult 包含处理结果
    """
    exec_result: Optional[Dict[str, Any]] = None
    bundle_r: Optional[int] = None
    anchor_span_id: str = ""
    attempt_rs = [max_r] if not adaptive_retry_r2 else build_attempt_r_values(max_r)

    # 历史感知模式：获取当前已知需求
    if history_aware and existing_requirements is None:
        existing_requirements = data_access.get_all_requirements_for_session(session_id)

    for attempt_r in attempt_rs:
        bundle = _generate_bundle(
            bundle_generator,
            spans,
            anchor_idx,
            bundle_strategy,
            attempt_r,
            adjacency,
            effective_top_m_2hop,
        )
        anchor_span_id = bundle.get("anchor_span_id", "")

        # 调用 Planner（支持历史感知）
        planner_result = call_planner(
            bundle,
            model_name,
            use_toolcall=use_toolcall,
            existing_requirements=existing_requirements,
            history_aware=history_aware,
        )
        if planner_result.get("error"):
            exec_result = _make_planner_error_result(planner_result["error"])
            bundle_r = bundle["r"]
            break

        # 根据模式选择执行器
        if history_aware:
            exec_result = executor.execute_bundle_with_history(
                session_id=session_id,
                anchor_span_id=bundle["anchor_span_id"],
                r=bundle["r"],
                model_output=planner_result["output"],
            )
        else:
            exec_result = executor.execute_bundle(
                session_id=session_id,
                anchor_span_id=bundle["anchor_span_id"],
                r=bundle["r"],
                model_output=planner_result["output"],
                use_toolcall_format=use_toolcall,
            )
        bundle_r = bundle["r"]

        if not is_insufficient_output(exec_result):
            break

    return AnchorResult(
        anchor_idx=anchor_idx,
        anchor_span_id=anchor_span_id,
        bundle_r=bundle_r or 0,
        exec_result=exec_result or {},
    )
