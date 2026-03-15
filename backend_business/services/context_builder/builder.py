import asyncio
from dataclasses import dataclass
from typing import Any, Dict, Generator, List, Optional, Set, Tuple
from uuid import uuid4

from .constants import DEFAULT_OPTIONS, _resolve_llm_model
from .graph import absorb_orphans, compute_components
from .llm_client import LLMClient
from .models import Edge, SSEEvent, Span
from .packing import estimate_tokens, pack_bundles
from .pruning import prune_edges
from .repository import ContextRunRepository
from .windowing import generate_windows, parse_window_edges


@dataclass
class WindowResult:
    """单个窗口的处理结果"""

    window_index: int
    window_spans: List[Span]
    ref_map: Dict[str, str]
    raw_links: List[Dict]
    noise_refs: List[str]
    pruned_edges: List[Edge]


class ContextBuilder:
    def __init__(self, dsn: Optional[str] = None):
        self.repository = ContextRunRepository(dsn=dsn)
        self.llm_client: Optional[LLMClient] = None

    def _get_llm_client(self, mock_mode: bool) -> LLMClient:
        if self.llm_client is None or self.llm_client.mock_mode != mock_mode:
            self.llm_client = LLMClient(mock_mode=mock_mode)
        return self.llm_client

    def load_spans(self, session_id: str) -> List[Span]:
        return self.repository.load_spans(session_id)

    def generate_windows(
        self,
        spans: List[Span],
        window_size: int,
        step_size: int,
    ) -> Generator[Tuple[List[Span], Dict[str, str]], None, None]:
        return generate_windows(spans, window_size, step_size)

    def parse_window_edges(
        self,
        raw_links: List[Dict],
        ref_map: Dict[str, str],
        window_spans: List[Span],
    ) -> List[Edge]:
        return parse_window_edges(raw_links, ref_map, window_spans)

    def prune_edges(
        self,
        edges: List[Edge],
        tau: float,
        top_k: int,
        max_edges: int,
    ) -> List[Edge]:
        return prune_edges(edges, tau, top_k, max_edges)

    def compute_components(
        self,
        spans: List[Span],
        edges: List[Edge],
        noise_span_ids: Set[str],
    ) -> Tuple[Dict[str, List[str]], List[str]]:
        return compute_components(spans, edges, noise_span_ids)

    def absorb_orphans(
        self,
        spans: List[Span],
        components: Dict[str, List[str]],
        orphan_ids: List[str],
    ) -> Dict[str, List[str]]:
        return absorb_orphans(spans, components, orphan_ids)

    def estimate_tokens(self, text: str) -> int:
        return estimate_tokens(text)

    def pack_bundles(
        self,
        spans: List[Span],
        components: Dict[str, List[str]],
        token_limit: int,
        context_run_id: str,
        session_id: str,
    ) -> Tuple[List[Dict], List[Dict]]:
        return pack_bundles(spans, components, token_limit, context_run_id, session_id)

    def create_context_run(self, session_id: str, options: Dict[str, Any]) -> str:
        return self.repository.create_context_run(session_id, options)

    def save_edges(self, context_run_id: str, edges: List[Edge]) -> int:
        return self.repository.save_edges(context_run_id, edges)

    def save_bundles(self, bundles: List[Dict], bundle_items: List[Dict]) -> int:
        return self.repository.save_bundles(bundles, bundle_items)

    async def _process_window_async(
        self,
        window_index: int,
        window_spans: List[Span],
        ref_map: Dict[str, str],
        llm: LLMClient,
        llm_model: Optional[str],
        tau: float,
        top_k: int,
        max_edges_per_window: int,
    ) -> WindowResult:
        """异步处理单个窗口"""
        # 调用异步 LLM
        raw_links, noise_refs = await llm.generate_links_async(
            window_spans, ref_map, llm_model
        )

        # CPU 密集操作（解析和剪枝）
        window_edges = self.parse_window_edges(raw_links, ref_map, window_spans)
        pruned_edges = self.prune_edges(window_edges, tau, top_k, max_edges_per_window)

        return WindowResult(
            window_index=window_index,
            window_spans=window_spans,
            ref_map=ref_map,
            raw_links=raw_links,
            noise_refs=noise_refs,
            pruned_edges=pruned_edges,
        )

    async def _process_windows_parallel(
        self,
        windows: List[Tuple[List[Span], Dict[str, str]]],
        llm: LLMClient,
        llm_model: Optional[str],
        tau: float,
        top_k: int,
        max_edges_per_window: int,
        max_concurrent: int,
        event_queue: asyncio.Queue,
    ) -> List[WindowResult]:
        """并行处理所有窗口，分批控制并发度"""
        results = []

        # 分批处理
        for batch_start in range(0, len(windows), max_concurrent):
            batch_end = min(batch_start + max_concurrent, len(windows))
            batch = windows[batch_start:batch_end]

            # 创建批次任务
            tasks = []
            for i, (window_spans, ref_map) in enumerate(batch):
                window_index = batch_start + i + 1
                task = self._process_window_async(
                    window_index,
                    window_spans,
                    ref_map,
                    llm,
                    llm_model,
                    tau,
                    top_k,
                    max_edges_per_window,
                )
                tasks.append((window_index, task))

            # 并行执行并实时发送事件
            for window_index, task in tasks:
                # 发送开始事件
                await event_queue.put(
                    SSEEvent(
                        "window_start",
                        {"window_index": window_index, "status": "processing"},
                    )
                )

            # 等待所有任务完成
            batch_results = await asyncio.gather(
                *[t[1] for t in tasks], return_exceptions=True
            )

            # 处理结果并发送完成事件
            for (window_index, _), result in zip(tasks, batch_results):
                if isinstance(result, Exception):
                    print(f"[ContextBuilder] Window {window_index} failed: {result}")
                    await event_queue.put(
                        SSEEvent(
                            "window_error",
                            {"window_index": window_index, "error": str(result)},
                        )
                    )
                else:
                    results.append(result)
                    await event_queue.put(
                        SSEEvent(
                            "window_complete",
                            {
                                "window_index": result.window_index,
                                "span_refs": list(result.ref_map.values()),
                                "raw_edge_count": len(result.raw_links),
                                "kept_edge_count": len(result.pruned_edges),
                            },
                        )
                    )

        # 按窗口索引排序
        results.sort(key=lambda r: r.window_index)
        return results

    def update_context_run_status(
        self,
        context_run_id: str,
        status: str,
        stats: Optional[Dict[str, Any]] = None,
    ):
        self.repository.update_context_run_status(context_run_id, status, stats)

    def build_context(
        self, session_id: str, options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        opts = {**DEFAULT_OPTIONS, **(options or {})}
        window_size = max(5, min(10, opts.get("window_size", 8)))
        step_size = max(1, min(window_size - 1, opts.get("step_size", window_size - 1)))
        tau = max(0.0, min(1.0, opts.get("tau", 0.6)))
        top_k = max(2, min(5, opts.get("top_k", 3)))
        max_edges_per_window = max(
            window_size, opts.get("max_edges_per_window", window_size * 3)
        )
        token_limit = max(1000, opts.get("token_limit_per_bundle", 4000))
        mock_llm = opts.get("mock_llm", False)
        llm_model = _resolve_llm_model(opts)

        spans = self.load_spans(session_id)
        if not spans:
            raise ValueError(f"No spans found for session_id: {session_id}")

        context_run_id = self.create_context_run(session_id, opts)

        try:
            llm = self._get_llm_client(mock_llm)

            all_edges: List[Edge] = []
            noise_span_ids: Set[str] = set()

            for window_spans, ref_map in self.generate_windows(
                spans, window_size, step_size
            ):
                raw_links, noise_refs = llm.generate_links(
                    window_spans, ref_map, llm_model
                )
                window_edges = self.parse_window_edges(raw_links, ref_map, window_spans)
                pruned_edges = self.prune_edges(
                    window_edges, tau, top_k, max_edges_per_window
                )

                all_edges.extend(pruned_edges)

                reverse_map = {ref: span_id for span_id, ref in ref_map.items()}
                for ref in noise_refs:
                    if ref in reverse_map:
                        noise_span_ids.add(reverse_map[ref])

            self.save_edges(context_run_id, all_edges)

            components, orphan_ids = self.compute_components(
                spans, all_edges, noise_span_ids
            )
            components = self.absorb_orphans(spans, components, orphan_ids)

            bundles, bundle_items = self.pack_bundles(
                spans, components, token_limit, context_run_id, session_id
            )

            bundled_span_ids = {item["span_id"] for item in bundle_items}
            non_noise_span_ids = {
                span.span_id for span in spans if span.span_id not in noise_span_ids
            }
            uncovered = non_noise_span_ids - bundled_span_ids

            if uncovered:
                misc_spans = [span for span in spans if span.span_id in uncovered]
                if misc_spans:
                    misc_bundle_id = str(uuid4())
                    misc_bundle = {
                        "bundle_id": misc_bundle_id,
                        "context_run_id": context_run_id,
                        "session_id": session_id,
                        "order_index": len(bundles) + 1,
                        "status": "READY",
                        "meta": {"is_misc": True},
                        "spans": misc_spans,
                    }
                    bundles.append(misc_bundle)

                    sorted_misc = sorted(
                        misc_spans,
                        key=lambda span: (span.start_ms or 0, span.order_index),
                    )
                    for i, span in enumerate(sorted_misc):
                        bundle_items.append(
                            {
                                "bundle_id": misc_bundle_id,
                                "span_id": span.span_id,
                                "span_ref": f"S{i + 1}",
                                "order_index": i + 1,
                            }
                        )

            self.save_bundles(bundles, bundle_items)

            stats = {
                "span_total": len(spans),
                "noise_count": len(noise_span_ids),
                "edge_count": len(all_edges),
                "component_count": len(components),
                "bundle_total": len(bundles),
            }
            self.update_context_run_status(context_run_id, "READY", stats)

            bundles_preview = []
            for bundle in bundles:
                bundle_text_lines = []
                for item in bundle_items:
                    if item["bundle_id"] == bundle["bundle_id"]:
                        span = next(
                            (
                                span
                                for span in bundle.get("spans", [])
                                if span.span_id == item["span_id"]
                            ),
                            None,
                        )
                        if span:
                            bundle_text_lines.append(
                                f"[{item['span_ref']}] {span.text[:100]}..."
                            )

                bundles_preview.append(
                    {
                        "bundle_id": bundle["bundle_id"],
                        "order_index": bundle["order_index"],
                        "span_count": len(
                            [
                                it
                                for it in bundle_items
                                if it["bundle_id"] == bundle["bundle_id"]
                            ]
                        ),
                        "meta": bundle.get("meta", {}),
                        "bundle_text_preview": "\n".join(bundle_text_lines[:3]),
                    }
                )

            return {
                "context_run_id": context_run_id,
                **stats,
                "bundles_preview": bundles_preview,
            }

        except Exception as exc:
            self.update_context_run_status(
                context_run_id, "FAILED", {"error": str(exc)}
            )
            raise

    def build_context_stream(
        self,
        session_id: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> Generator[SSEEvent, None, None]:
        opts = {**DEFAULT_OPTIONS, **(options or {})}
        window_size = max(5, min(10, opts.get("window_size", 8)))
        step_size = max(1, min(window_size - 1, opts.get("step_size", window_size - 1)))
        tau = max(0.0, min(1.0, opts.get("tau", 0.6)))
        top_k = max(2, min(5, opts.get("top_k", 3)))
        max_edges_per_window = max(
            window_size, opts.get("max_edges_per_window", window_size * 3)
        )
        token_limit = max(1000, opts.get("token_limit_per_bundle", 4000))
        mock_llm = opts.get("mock_llm", False)
        llm_model = _resolve_llm_model(opts)

        spans = self.load_spans(session_id)
        if not spans:
            yield SSEEvent(
                "error", {"message": f"No spans found for session_id: {session_id}"}
            )
            return

        context_run_id = self.create_context_run(session_id, opts)

        yield SSEEvent(
            "init",
            {
                "session_id": session_id,
                "context_run_id": context_run_id,
                "span_total": len(spans),
            },
        )

        try:
            # 提取并行参数
            enable_parallel = opts.get("enable_parallel_windows", False)
            max_concurrent = max(1, min(10, opts.get("max_concurrent_windows", 5)))

            llm = self._get_llm_client(mock_llm)

            all_edges: List[Edge] = []
            noise_span_ids: Set[str] = set()

            if enable_parallel:
                # 并行模式
                windows = list(self.generate_windows(spans, window_size, step_size))
                total_windows = len(windows)

                yield SSEEvent(
                    "parallel_batch_start",
                    {"total_windows": total_windows, "max_concurrent": max_concurrent},
                )

                async def process_with_events():
                    return await self._process_windows_parallel(
                        windows,
                        llm,
                        llm_model,
                        tau,
                        top_k,
                        max_edges_per_window,
                        max_concurrent,
                        event_queue,
                    )

                # 在新事件循环中运行
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                # 创建事件队列用于实时进度（绑定当前事件循环）
                event_queue = asyncio.Queue()

                # 启动处理任务
                process_task = loop.create_task(process_with_events())

                try:
                    # 实时发送事件
                    while not process_task.done():
                        try:
                            event = event_queue.get_nowait()
                            yield event
                        except asyncio.QueueEmpty:
                            loop.run_until_complete(asyncio.sleep(0.05))

                    while True:
                        try:
                            event = event_queue.get_nowait()
                            yield event
                        except asyncio.QueueEmpty:
                            break

                    # 获取结果
                    window_results = process_task.result()
                finally:
                    try:
                        loop.run_until_complete(llm.close_async())
                    finally:
                        loop.close()
                        asyncio.set_event_loop(None)

                # 收集边和噪声
                for result in window_results:
                    all_edges.extend(result.pruned_edges)

                    reverse_map = {ref: sid for sid, ref in result.ref_map.items()}
                    for ref in result.noise_refs:
                        if ref in reverse_map:
                            noise_span_ids.add(reverse_map[ref])

                    yield SSEEvent(
                        "graph_progress", {"total_edges_so_far": len(all_edges)}
                    )

                yield SSEEvent(
                    "parallel_batch_complete",
                    {"total_windows_processed": len(window_results)},
                )

            else:
                # 串行模式（保持原有逻辑不变）
                window_index = 0

                for window_spans, ref_map in self.generate_windows(
                    spans, window_size, step_size
                ):
                    window_index += 1
                    span_refs = list(ref_map.values())

                    yield SSEEvent(
                        "window_start",
                        {
                            "window_index": window_index,
                            "span_refs": span_refs,
                        },
                    )

                    raw_links, noise_refs = llm.generate_links(
                        window_spans, ref_map, llm_model
                    )

                    yield SSEEvent(
                        "llm_edges",
                        {
                            "window_index": window_index,
                            "raw_edge_count": len(raw_links),
                        },
                    )

                    window_edges = self.parse_window_edges(
                        raw_links, ref_map, window_spans
                    )
                    pruned_edges = self.prune_edges(
                        window_edges, tau, top_k, max_edges_per_window
                    )

                    yield SSEEvent(
                        "pruned_edges",
                        {
                            "window_index": window_index,
                            "kept_edge_count": len(pruned_edges),
                        },
                    )

                    all_edges.extend(pruned_edges)

                    yield SSEEvent(
                        "graph_progress",
                        {"total_edges_so_far": len(all_edges)},
                    )

                    reverse_map = {ref: span_id for span_id, ref in ref_map.items()}
                    for ref in noise_refs:
                        if ref in reverse_map:
                            noise_span_ids.add(reverse_map[ref])

            self.save_edges(context_run_id, all_edges)

            components, orphan_ids = self.compute_components(
                spans, all_edges, noise_span_ids
            )
            components = self.absorb_orphans(spans, components, orphan_ids)

            bundles, bundle_items = self.pack_bundles(
                spans, components, token_limit, context_run_id, session_id
            )

            bundled_span_ids = {item["span_id"] for item in bundle_items}
            non_noise_span_ids = {
                span.span_id for span in spans if span.span_id not in noise_span_ids
            }
            uncovered = non_noise_span_ids - bundled_span_ids

            if uncovered:
                misc_spans = [span for span in spans if span.span_id in uncovered]
                if misc_spans:
                    misc_bundle_id = str(uuid4())
                    misc_bundle = {
                        "bundle_id": misc_bundle_id,
                        "context_run_id": context_run_id,
                        "session_id": session_id,
                        "order_index": len(bundles) + 1,
                        "status": "READY",
                        "meta": {"is_misc": True},
                        "spans": misc_spans,
                    }
                    bundles.append(misc_bundle)

                    sorted_misc = sorted(
                        misc_spans,
                        key=lambda span: (span.start_ms or 0, span.order_index),
                    )
                    for i, span in enumerate(sorted_misc):
                        bundle_items.append(
                            {
                                "bundle_id": misc_bundle_id,
                                "span_id": span.span_id,
                                "span_ref": f"S{i + 1}",
                                "order_index": i + 1,
                            }
                        )

            self.save_bundles(bundles, bundle_items)

            yield SSEEvent("bundling_done", {"bundle_total": len(bundles)})

            stats = {
                "span_total": len(spans),
                "noise_count": len(noise_span_ids),
                "edge_count": len(all_edges),
                "component_count": len(components),
                "bundle_total": len(bundles),
            }
            self.update_context_run_status(context_run_id, "READY", stats)

            yield SSEEvent(
                "final",
                {
                    "context_run_id": context_run_id,
                    "bundle_total": len(bundles),
                    "edge_count": len(all_edges),
                    "component_count": len(components),
                },
            )

        except Exception as exc:
            self.update_context_run_status(
                context_run_id, "FAILED", {"error": str(exc)}
            )
            yield SSEEvent("error", {"message": str(exc)})


context_builder = ContextBuilder()
