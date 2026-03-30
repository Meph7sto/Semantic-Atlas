"""
Main requirements extraction service - orchestration layer
"""

import asyncio
import logging
from typing import Any, Dict, Generator, Optional, Sequence

from backend_business.services.requirements_executor import RequirementsExecutor

from .anchor_processor import process_anchors_parallel
from .data_access import RequirementsDataAccess
from .params import build_initial_result, normalize_extraction_params
from .result_collector import (
    accumulate_parallel_results,
    accumulate_serial_result,
    build_anchor_complete_event,
)
from .serial_processor import process_single_anchor_serial

logger = logging.getLogger(__name__)


class RequirementsExtractionService:
    """
    L1-L3 需求抽取服务
    """

    def __init__(self, dsn: str):
        self.dsn = dsn
        self.executor = RequirementsExecutor(dsn)
        self.data_access = RequirementsDataAccess(dsn)

    # ------------------------------------------------------------------
    # 公共准备阶段: spans → anchors → adjacency
    # ------------------------------------------------------------------
    def _prepare_extraction(
        self,
        session_id: str,
        bundle_strategy: str,
        anchor_strategy: str,
        context_run_id: Optional[str],
        params,
        result: Dict[str, Any],
    ):
        """
        获取 spans、选择锚点、构建邻接表。
        返回 (spans, anchor_indices, adjacency) 或在异常时返回 None 并把错误写入 result。
        """
        spans = self.data_access.get_spans_by_session(session_id)
        result["total_spans"] = len(spans)

        if not spans:
            result["errors"].append("No spans found for this session")
            return None

        anchor_indices = params.bundle_generator.select_anchors(
            spans,
            strategy=anchor_strategy,
            keywords=params.effective_keywords,
        )
        result["total_anchors"] = len(anchor_indices)

        if not anchor_indices:
            result["errors"].append("No anchors selected")
            return None

        adjacency = None
        if bundle_strategy == "graph":
            if not context_run_id:
                result["errors"].append("context_run_id is required for graph strategy")
                return None
            edges = self.data_access.get_edges_by_run(context_run_id)
            adjacency = params.bundle_generator.build_adjacency_from_edges(edges)

        if bundle_strategy not in {"sequence", "graph"}:
            result["errors"].append(f"Unknown bundle strategy: {bundle_strategy}")
            return None

        return spans, anchor_indices, adjacency

    # ------------------------------------------------------------------
    # 并行执行（同步包装）
    # ------------------------------------------------------------------
    def _run_parallel(
        self,
        anchor_indices,
        spans,
        params,
        bundle_strategy,
        adjacency,
        session_id,
        model_name,
        use_toolcall,
        context_run_id,
        planner_connect_timeout_seconds=None,
        planner_read_timeout_seconds=None,
        planner_max_retries=None,
        event_queue=None,
    ):
        """在新事件循环中运行并行处理，返回 anchor_results 列表"""

        if event_queue is None:

            class _NullQueue:
                async def put(self, _item: Any) -> None:
                    return None

            event_queue = _NullQueue()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            anchor_results = loop.run_until_complete(
                process_anchors_parallel(
                    anchor_indices=anchor_indices,
                    spans=spans,
                    bundle_generator=params.bundle_generator,
                    executor=self.executor,
                    bundle_strategy=bundle_strategy,
                    adjacency=adjacency,
                    max_r=params.max_r,
                    adaptive_retry_r2=params.adaptive_retry_r2,
                    effective_top_m_2hop=params.effective_top_m_2hop,
                    session_id=session_id,
                    model_name=model_name,
                    use_toolcall=use_toolcall,
                    context_run_id=context_run_id,
                    max_concurrent=params.effective_max_concurrent,
                    event_queue=event_queue,
                    planner_connect_timeout_seconds=planner_connect_timeout_seconds,
                    planner_read_timeout_seconds=planner_read_timeout_seconds,
                    planner_max_retries=planner_max_retries,
                )
            )
        finally:
            try:
                loop.close()
            finally:
                asyncio.set_event_loop(None)

        return anchor_results

    # ------------------------------------------------------------------
    # 同步版本
    # ------------------------------------------------------------------
    def extract_requirements_for_session(
        self,
        session_id: str,
        context_run_id: Optional[str] = None,
        bundle_strategy: str = "sequence",
        anchor_strategy: str = "informative",
        r: int = 2,
        model_name: str = "deepseek-reasoner",
        use_toolcall: bool = True,
        adaptive_retry_r2: Optional[bool] = None,
        max_spans_per_bundle: Optional[int] = None,
        token_limit: Optional[int] = None,
        top_m_2hop: Optional[int] = None,
        keywords: Optional[Sequence[str]] = None,
        enable_parallel: bool = False,
        max_concurrent: int = 5,
        history_aware: bool = False,
        planner_connect_timeout_seconds: Optional[float] = None,
        planner_read_timeout_seconds: Optional[float] = None,
        planner_max_retries: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        对指定 session 进行 L1-L3 需求抽取

        Args:
            session_id: 会话 ID
            context_run_id: 上下文运行 ID（可选,用于基于图邻域的策略）
            bundle_strategy: bundle 生成策略
                - "sequence": 基于序列窗口
                - "graph": 基于图邻域（需要 context_run_id）
            anchor_strategy: 锚点选择策略
                - "all": 所有 span 都作为锚点
                - "keyword": 包含关键词的 span
                - "informative": 信息量大的 span（推荐）
            r: 最大邻域半径（sequence 策略）或跳数（graph 策略）
            model_name: 使用的模型名称
            use_toolcall: 是否使用 DeepSeek API tool call 格式（默认为 True）
            adaptive_retry_r2: r>=2 时是否自动尝试 r=2（默认 True）
            max_spans_per_bundle: 每个 EgoBundle 最多 spans 数（默认 12）
            token_limit: 每个 EgoBundle 大概字数上限（默认 1500）
            top_m_2hop: 2-hop 邻居 Top-M（默认 5）
            keywords: 锚点关键词（用于 keyword/informative 策略）
            history_aware: 是否启用历史感知模式

        Returns:
            抽取结果统计
        """
        if enable_parallel and history_aware:
            logger.warning(
                "history_aware is serial-only; forcing history_aware=False in parallel mode"
            )
            history_aware = False

        params = normalize_extraction_params(
            r=r,
            adaptive_retry_r2=adaptive_retry_r2,
            max_spans_per_bundle=max_spans_per_bundle,
            token_limit=token_limit,
            top_m_2hop=top_m_2hop,
            keywords=keywords,
            enable_parallel=enable_parallel,
            max_concurrent=max_concurrent,
        )
        result = build_initial_result(
            session_id=session_id,
            bundle_strategy=bundle_strategy,
            anchor_strategy=anchor_strategy,
            params=params,
            use_toolcall=use_toolcall,
            history_aware=history_aware,
        )

        prepared = self._prepare_extraction(
            session_id,
            bundle_strategy,
            anchor_strategy,
            context_run_id,
            params,
            result,
        )
        if prepared is None:
            return result
        spans, anchor_indices, adjacency = prepared

        # 并行模式
        if params.enable_parallel:
            anchor_results = self._run_parallel(
                anchor_indices,
                spans,
                params,
                bundle_strategy,
                adjacency,
                session_id,
                model_name,
                use_toolcall,
                context_run_id,
                planner_connect_timeout_seconds,
                planner_read_timeout_seconds,
                planner_max_retries,
            )
            accumulate_parallel_results(result, anchor_results)
            return result

        # 串行模式
        rolling_existing_requirements = None
        if history_aware:
            rolling_existing_requirements = (
                self.data_access.get_all_requirements_for_session(session_id)
            )

        for anchor_idx in anchor_indices:
            try:
                anchor_result = process_single_anchor_serial(
                    anchor_idx=anchor_idx,
                    spans=spans,
                    bundle_generator=params.bundle_generator,
                    executor=self.executor,
                    data_access=self.data_access,
                    bundle_strategy=bundle_strategy,
                    adjacency=adjacency,
                    max_r=params.max_r,
                    adaptive_retry_r2=params.adaptive_retry_r2,
                    effective_top_m_2hop=params.effective_top_m_2hop,
                    session_id=session_id,
                    model_name=model_name,
                    use_toolcall=use_toolcall,
                    history_aware=history_aware,
                    existing_requirements=rolling_existing_requirements,
                    planner_connect_timeout_seconds=planner_connect_timeout_seconds,
                    planner_read_timeout_seconds=planner_read_timeout_seconds,
                    planner_max_retries=planner_max_retries,
                )
                accumulate_serial_result(result, anchor_result)

                if history_aware:
                    rolling_existing_requirements = (
                        self.data_access.get_all_requirements_for_session(session_id)
                    )
            except Exception as e:
                logger.exception(f"Error processing anchor {anchor_idx}")
                result["errors"].append({"anchor_idx": anchor_idx, "error": str(e)})

        return result

    # ------------------------------------------------------------------
    # 流式版本
    # ------------------------------------------------------------------
    def extract_requirements_for_session_stream(
        self,
        session_id: str,
        context_run_id: Optional[str] = None,
        bundle_strategy: str = "sequence",
        anchor_strategy: str = "informative",
        r: int = 2,
        model_name: str = "deepseek-reasoner",
        use_toolcall: bool = True,
        adaptive_retry_r2: Optional[bool] = None,
        max_spans_per_bundle: Optional[int] = None,
        token_limit: Optional[int] = None,
        top_m_2hop: Optional[int] = None,
        keywords: Optional[Sequence[str]] = None,
        enable_parallel: bool = False,
        max_concurrent: int = 5,
        history_aware: bool = False,
        planner_connect_timeout_seconds: Optional[float] = None,
        planner_read_timeout_seconds: Optional[float] = None,
        planner_max_retries: Optional[int] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """
        流式版本的需求抽取,支持并发处理

        Yields:
            SSE 事件 {"event": "...", "data": {...}}
        """
        if enable_parallel and history_aware:
            logger.warning(
                "history_aware is serial-only; forcing history_aware=False in parallel mode"
            )
            history_aware = False

        params = normalize_extraction_params(
            r=r,
            adaptive_retry_r2=adaptive_retry_r2,
            max_spans_per_bundle=max_spans_per_bundle,
            token_limit=token_limit,
            top_m_2hop=top_m_2hop,
            keywords=keywords,
            enable_parallel=enable_parallel,
            max_concurrent=max_concurrent,
        )
        result = build_initial_result(
            session_id=session_id,
            bundle_strategy=bundle_strategy,
            anchor_strategy=anchor_strategy,
            params=params,
            use_toolcall=use_toolcall,
            history_aware=history_aware,
            enable_parallel=params.enable_parallel,
            max_concurrent=params.effective_max_concurrent,
        )

        try:
            # 1. 获取 spans
            spans = self.data_access.get_spans_by_session(session_id)
            result["total_spans"] = len(spans)

            yield {
                "event": "init",
                "data": {
                    "session_id": session_id,
                    "total_spans": len(spans),
                    "enable_parallel": params.enable_parallel,
                    "max_concurrent": params.effective_max_concurrent,
                    "history_aware": history_aware,
                    "planner_connect_timeout_seconds": planner_connect_timeout_seconds,
                    "planner_read_timeout_seconds": planner_read_timeout_seconds,
                    "planner_max_retries": planner_max_retries,
                },
            }

            if not spans:
                yield {
                    "event": "error",
                    "data": {"message": "No spans found for this session"},
                }
                return

            # 2. 选择锚点
            anchor_indices = params.bundle_generator.select_anchors(
                spans,
                strategy=anchor_strategy,
                keywords=params.effective_keywords,
            )
            result["total_anchors"] = len(anchor_indices)

            yield {
                "event": "anchors_selected",
                "data": {"total_anchors": len(anchor_indices)},
            }

            if not anchor_indices:
                yield {"event": "error", "data": {"message": "No anchors selected"}}
                return

            adjacency = None
            if bundle_strategy == "graph":
                if not context_run_id:
                    yield {
                        "event": "error",
                        "data": {
                            "message": "context_run_id is required for graph strategy"
                        },
                    }
                    return
                edges = self.data_access.get_edges_by_run(context_run_id)
                adjacency = params.bundle_generator.build_adjacency_from_edges(edges)

            # 3. 处理锚点
            if params.enable_parallel:
                yield from self._stream_parallel(
                    anchor_indices,
                    spans,
                    params,
                    bundle_strategy,
                    adjacency,
                    session_id,
                    model_name,
                    use_toolcall,
                    context_run_id,
                    planner_connect_timeout_seconds,
                    planner_read_timeout_seconds,
                    planner_max_retries,
                    result,
                )
            else:
                yield from self._stream_serial(
                    anchor_indices,
                    spans,
                    params,
                    bundle_strategy,
                    adjacency,
                    session_id,
                    model_name,
                    use_toolcall,
                    history_aware,
                    planner_connect_timeout_seconds,
                    planner_read_timeout_seconds,
                    planner_max_retries,
                    result,
                )

            # 最终统计
            yield {
                "event": "final",
                "data": {
                    "total_anchors": result["total_anchors"],
                    "bundles_processed": result["bundles_processed"],
                    "total_inserted": result["total_inserted"],
                    "total_duplicates": result["total_duplicates"],
                    "total_updated": result["total_updated"],
                    "error_count": len(result["errors"]),
                },
            }

        except Exception as exc:
            logger.exception("Error in extract_requirements_for_session_stream")
            yield {"event": "error", "data": {"message": str(exc)}}

    # ------------------------------------------------------------------
    # 流式-并行
    # ------------------------------------------------------------------
    def _stream_parallel(
        self,
        anchor_indices,
        spans,
        params,
        bundle_strategy,
        adjacency,
        session_id,
        model_name,
        use_toolcall,
        context_run_id,
        planner_connect_timeout_seconds,
        planner_read_timeout_seconds,
        planner_max_retries,
        result,
    ) -> Generator[Dict[str, Any], None, None]:
        yield {
            "event": "parallel_batch_start",
            "data": {
                "total_anchors": len(anchor_indices),
                "max_concurrent": params.effective_max_concurrent,
            },
        }

        # 在新事件循环中运行并实时转发事件
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        event_queue = asyncio.Queue()

        async def _process():
            return await process_anchors_parallel(
                anchor_indices=anchor_indices,
                spans=spans,
                bundle_generator=params.bundle_generator,
                executor=self.executor,
                bundle_strategy=bundle_strategy,
                adjacency=adjacency,
                max_r=params.max_r,
                adaptive_retry_r2=params.adaptive_retry_r2,
                effective_top_m_2hop=params.effective_top_m_2hop,
                session_id=session_id,
                model_name=model_name,
                use_toolcall=use_toolcall,
                context_run_id=context_run_id,
                max_concurrent=params.effective_max_concurrent,
                event_queue=event_queue,
                planner_connect_timeout_seconds=planner_connect_timeout_seconds,
                planner_read_timeout_seconds=planner_read_timeout_seconds,
                planner_max_retries=planner_max_retries,
            )

        process_task = loop.create_task(_process())

        try:
            # 实时发送事件
            while not process_task.done():
                try:
                    event = event_queue.get_nowait()
                    yield event
                except asyncio.QueueEmpty:
                    loop.run_until_complete(asyncio.sleep(0.05))

            # 清空剩余事件
            while True:
                try:
                    event = event_queue.get_nowait()
                    yield event
                except asyncio.QueueEmpty:
                    break

            anchor_results = process_task.result()
        finally:
            loop.close()
            asyncio.set_event_loop(None)

        accumulate_parallel_results(result, anchor_results)

        yield {
            "event": "parallel_batch_complete",
            "data": {"total_anchors_processed": len(anchor_results)},
        }

    # ------------------------------------------------------------------
    # 流式-串行
    # ------------------------------------------------------------------
    def _stream_serial(
        self,
        anchor_indices,
        spans,
        params,
        bundle_strategy,
        adjacency,
        session_id,
        model_name,
        use_toolcall,
        history_aware,
        planner_connect_timeout_seconds,
        planner_read_timeout_seconds,
        planner_max_retries,
        result,
    ) -> Generator[Dict[str, Any], None, None]:
        rolling_existing_requirements = None
        if history_aware:
            rolling_existing_requirements = (
                self.data_access.get_all_requirements_for_session(session_id)
            )

        for anchor_idx in anchor_indices:
            yield {
                "event": "anchor_start",
                "data": {
                    "anchor_idx": anchor_idx,
                    "history_aware": history_aware,
                },
            }

            try:
                anchor_result = process_single_anchor_serial(
                    anchor_idx=anchor_idx,
                    spans=spans,
                    bundle_generator=params.bundle_generator,
                    executor=self.executor,
                    data_access=self.data_access,
                    bundle_strategy=bundle_strategy,
                    adjacency=adjacency,
                    max_r=params.max_r,
                    adaptive_retry_r2=params.adaptive_retry_r2,
                    effective_top_m_2hop=params.effective_top_m_2hop,
                    session_id=session_id,
                    model_name=model_name,
                    use_toolcall=use_toolcall,
                    history_aware=history_aware,
                    existing_requirements=rolling_existing_requirements,
                    planner_connect_timeout_seconds=planner_connect_timeout_seconds,
                    planner_read_timeout_seconds=planner_read_timeout_seconds,
                    planner_max_retries=planner_max_retries,
                )
                accumulate_serial_result(result, anchor_result)

                if history_aware:
                    rolling_existing_requirements = (
                        self.data_access.get_all_requirements_for_session(session_id)
                    )

                yield {
                    "event": "anchor_complete",
                    "data": build_anchor_complete_event(anchor_result),
                }

            except Exception as e:
                logger.exception(f"Error processing anchor {anchor_idx}")
                result["errors"].append({"anchor_idx": anchor_idx, "error": str(e)})
                yield {
                    "event": "anchor_error",
                    "data": {"anchor_idx": anchor_idx, "error": str(e)},
                }

    # ------------------------------------------------------------------
    # Delegate to data access layer
    # ------------------------------------------------------------------
    def get_requirements_by_session(
        self,
        session_id: str,
        level: Optional[str] = None,
        page: int = 1,
        per_page: int = 50,
    ) -> Dict[str, Any]:
        """查询指定 session 的需求"""
        return self.data_access.get_requirements_by_session(
            session_id, level, page, per_page
        )

    def get_requirement_detail(self, req_id: str) -> Optional[Dict[str, Any]]:
        """获取需求详情"""
        return self.data_access.get_requirement_detail(req_id)

    def delete_requirement(self, req_id: str) -> bool:
        """删除需求"""
        return self.data_access.delete_requirement(req_id)

    def clear_requirements_for_session(self, session_id: str) -> int:
        """清理指定 session 的全部 L1-L3 需求"""
        return self.data_access.clear_requirements_for_session(session_id)

    def get_statistics(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """获取需求统计信息"""
        return self.data_access.get_statistics(session_id)
