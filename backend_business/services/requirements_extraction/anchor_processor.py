"""
Async anchor processing for requirements extraction
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

import aiohttp

from backend_business.services.ego_bundle_generator import EgoBundleGenerator
from backend_business.services.requirements_executor import RequirementsExecutor

from .models import AnchorResult
from .planner import call_planner_async
from .result_collector import build_anchor_complete_event
from .utils import build_attempt_r_values, is_insufficient_output

logger = logging.getLogger(__name__)


async def process_anchor_async(
    anchor_idx: int,
    spans: List[Dict[str, Any]],
    bundle_generator: EgoBundleGenerator,
    executor: RequirementsExecutor,
    bundle_strategy: str,
    adjacency: Optional[Dict[str, List[str]]],
    max_r: int,
    adaptive_retry_r2: bool,
    effective_top_m_2hop: int,
    session_id: str,
    model_name: str,
    use_toolcall: bool,
    use_thinking_mode: bool,
    context_run_id: Optional[str],
    http_session: aiohttp.ClientSession,
    planner_connect_timeout_seconds: Optional[float] = None,
    planner_read_timeout_seconds: Optional[float] = None,
    planner_max_retries: Optional[int] = None,
) -> AnchorResult:
    """异步处理单个锚点"""
    try:
        exec_result = None
        bundle_r = None
        attempt_rs = (
            [max_r]
            if not adaptive_retry_r2
            else build_attempt_r_values(max_r)
        )

        for attempt_r in attempt_rs:
            # 生成 EgoBundle
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
            else:
                raise ValueError(f"Unknown bundle strategy: {bundle_strategy}")

            # 异步调用 Planner
            planner_result = await call_planner_async(
                bundle,
                model_name,
                use_toolcall=use_toolcall,
                use_thinking_mode=use_thinking_mode,
                session=http_session,
                connect_timeout=planner_connect_timeout_seconds,
                read_timeout=planner_read_timeout_seconds,
                max_retries=planner_max_retries,
            )

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

            # 执行器校验并落库
            exec_result = await asyncio.to_thread(
                executor.execute_bundle,
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
            anchor_span_id=bundle["anchor_span_id"] if bundle_r is not None else "",
            bundle_r=bundle_r or max_r,
            exec_result=exec_result or {},
        )

    except Exception as e:
        logger.exception(f"Error processing anchor {anchor_idx}")
        return AnchorResult(
            anchor_idx=anchor_idx,
            anchor_span_id="",
            bundle_r=max_r,
            exec_result={},
            error=str(e),
        )


async def process_anchors_parallel(
    anchor_indices: List[int],
    spans: List[Dict[str, Any]],
    bundle_generator: EgoBundleGenerator,
    executor: RequirementsExecutor,
    bundle_strategy: str,
    adjacency: Optional[Dict[str, List[str]]],
    max_r: int,
    adaptive_retry_r2: bool,
    effective_top_m_2hop: int,
    session_id: str,
    model_name: str,
    use_toolcall: bool,
    context_run_id: Optional[str],
    max_concurrent: int,
    event_queue: asyncio.Queue,
    use_thinking_mode: bool = True,
    planner_connect_timeout_seconds: Optional[float] = None,
    planner_read_timeout_seconds: Optional[float] = None,
    planner_max_retries: Optional[int] = None,
) -> List[AnchorResult]:
    """并行处理所有锚点,分批控制并发度"""
    results = []

    async def _run_one(
        anchor_idx: int,
        http_session: aiohttp.ClientSession,
    ) -> tuple[int, AnchorResult]:
        try:
            result = await process_anchor_async(
                anchor_idx=anchor_idx,
                spans=spans,
                bundle_generator=bundle_generator,
                executor=executor,
                bundle_strategy=bundle_strategy,
                adjacency=adjacency,
                max_r=max_r,
                adaptive_retry_r2=adaptive_retry_r2,
                effective_top_m_2hop=effective_top_m_2hop,
                session_id=session_id,
                model_name=model_name,
                use_toolcall=use_toolcall,
                use_thinking_mode=use_thinking_mode,
                context_run_id=context_run_id,
                http_session=http_session,
                planner_connect_timeout_seconds=planner_connect_timeout_seconds,
                planner_read_timeout_seconds=planner_read_timeout_seconds,
                planner_max_retries=planner_max_retries,
            )
        except Exception as exc:
            logger.exception(f"Anchor {anchor_idx} task failed unexpectedly")
            result = AnchorResult(
                anchor_idx=anchor_idx,
                anchor_span_id="",
                bundle_r=max_r,
                exec_result={},
                error=str(exc),
            )
        return anchor_idx, result

    # 创建共享的 HTTP session
    async with aiohttp.ClientSession() as http_session:
        # 分批处理
        for batch_start in range(0, len(anchor_indices), max_concurrent):
            batch_end = min(batch_start + max_concurrent, len(anchor_indices))
            batch = anchor_indices[batch_start:batch_end]

            # 创建批次任务
            tasks: list[asyncio.Task[tuple[int, AnchorResult]]] = []
            for anchor_idx in batch:
                task = asyncio.create_task(
                    _run_one(
                        anchor_idx=anchor_idx,
                        http_session=http_session,
                    )
                )
                tasks.append(task)

            # 发送开始事件
            for anchor_idx in batch:
                await event_queue.put(
                    {
                        "event": "anchor_start",
                        "data": {"anchor_idx": anchor_idx, "status": "processing"},
                    }
                )

            # 按完成顺序发送事件，而不是整批等待后统一输出
            for completed in asyncio.as_completed(tasks):
                anchor_idx, result = await completed

                results.append(result)

                if result.error:
                    await event_queue.put(
                        {
                            "event": "anchor_error",
                            "data": {
                                "anchor_idx": result.anchor_idx,
                                "error": result.error,
                            },
                        }
                    )
                    continue

                await event_queue.put(
                    {
                        "event": "anchor_complete",
                        "data": build_anchor_complete_event(result),
                    }
                )

    return results
