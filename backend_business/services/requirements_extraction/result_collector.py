"""
Result aggregation logic for requirements extraction
"""

from typing import Any, Dict, List

from .models import AnchorResult


def _summarize_exec_error(exec_result: Dict[str, Any]) -> str | None:
    """提取执行结果中的高价值错误摘要，便于前端流式展示。"""
    planner_error = exec_result.get("planner_error")
    if planner_error:
        return str(planner_error)

    quota_error = exec_result.get("quota_error")
    if quota_error:
        return str(quota_error)

    db_errors = exec_result.get("db_errors") or []
    if db_errors:
        first = db_errors[0]
        return str(first)

    validation_errors = exec_result.get("validation_errors") or []
    if validation_errors:
        first = validation_errors[0]
        return str(first)

    return None


def accumulate_serial_result(
    result: Dict[str, Any],
    anchor_result: AnchorResult,
) -> None:
    """
    将单个串行锚点结果累加到总统计字典中

    Args:
        result: 总统计字典（会被原地修改）
        anchor_result: 单个锚点处理结果
    """
    exec_result = anchor_result.exec_result
    result["bundles_processed"] += 1
    result["total_inserted"] += exec_result.get("inserted", 0)
    result["total_duplicates"] += exec_result.get("duplicates", 0)
    result["total_updated"] += exec_result.get("updated", 0)

    # 收集更新日志
    if exec_result.get("update_log"):
        result["update_log"].extend(exec_result["update_log"])

    # 收集错误
    if anchor_result.error:
        result["errors"].append(
            {
                "anchor_idx": anchor_result.anchor_idx,
                "error": anchor_result.error,
            }
        )
    elif exec_result.get("status") not in ["success", "empty", None]:
        entry: Dict[str, Any] = {
            "anchor_idx": anchor_result.anchor_idx,
            "status": exec_result.get("status"),
            "details": exec_result,
        }
        if anchor_result.bundle_r:
            entry["r"] = anchor_result.bundle_r
        result["errors"].append(entry)


def accumulate_parallel_results(
    result: Dict[str, Any],
    anchor_results: List[AnchorResult],
) -> None:
    """
    将并行处理的所有锚点结果累加到总统计字典中

    Args:
        result: 总统计字典（会被原地修改）
        anchor_results: 并行处理得到的锚点结果列表
    """
    for anchor_result in anchor_results:
        result["bundles_processed"] += 1
        result["total_inserted"] += anchor_result.exec_result.get("inserted", 0)
        result["total_duplicates"] += anchor_result.exec_result.get("duplicates", 0)

        if anchor_result.error:
            result["errors"].append(
                {
                    "anchor_idx": anchor_result.anchor_idx,
                    "error": anchor_result.error,
                }
            )
        elif anchor_result.exec_result.get("status") not in ["success", "empty"]:
            result["errors"].append(
                {
                    "anchor_idx": anchor_result.anchor_idx,
                    "status": anchor_result.exec_result.get("status"),
                    "details": anchor_result.exec_result,
                    "r": anchor_result.bundle_r,
                }
            )


def build_anchor_complete_event(anchor_result: AnchorResult) -> Dict[str, Any]:
    """
    从 AnchorResult 构建 anchor_complete SSE 事件数据
    """
    exec_result = anchor_result.exec_result
    error_message = _summarize_exec_error(exec_result)
    return {
        "anchor_idx": anchor_result.anchor_idx,
        "anchor_span_id": anchor_result.anchor_span_id,
        "r": anchor_result.bundle_r,
        "inserted": exec_result.get("inserted", 0),
        "duplicates": exec_result.get("duplicates", 0),
        "updated": exec_result.get("updated", 0),
        "status": exec_result.get("status", "unknown"),
        "error": error_message,
    }
