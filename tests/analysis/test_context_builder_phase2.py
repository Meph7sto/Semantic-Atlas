import os
import sys
import unittest
import asyncio

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
INFERENCE_DIR = os.path.join(ROOT_DIR, "backend_inference")
if INFERENCE_DIR not in sys.path:
    sys.path.insert(0, INFERENCE_DIR)

from backend_business.services.context_builder import ContextBuilder, Edge, Span, RELATION_TYPES


def _llm_available() -> bool:
    provider = os.getenv("MODEL_PROVIDER", "local").lower()
    if provider == "deepseek":
        return bool(os.getenv("DEEPSEEK_API_KEY"))
    if provider == "chutes":
        return bool(os.getenv("CHUTES_API_TOKEN") or os.getenv("CHUTES_API_KEY"))
    return os.getenv("RUN_LLM_CONTEXT_TEST", "").lower() in ("1", "true", "yes")


class TestContextBuilderPhase2(unittest.TestCase):
    def setUp(self):
        self.builder = ContextBuilder(dsn="")

    def _span(self, span_id: str, order_index: int) -> Span:
        return Span(
            span_id=span_id,
            session_id="session-1",
            start_ms=order_index * 1000,
            end_ms=order_index * 1000 + 100,
            speaker=None,
            text=f"text {span_id}",
            order_index=order_index,
        )

    def test_parse_window_edges_keeps_max_strength(self):
        spans = [self._span("A", 0), self._span("B", 1)]
        ref_map = {"A": "S1", "B": "S2"}
        raw_links = [
            {"source": "S1", "target": "S2", "type": "continuation", "strength": 0.2, "note": "weak"},
            {"source": "S1", "target": "S2", "type": "continuation", "strength": 0.8, "note": "strong"},
        ]

        edges = self.builder.parse_window_edges(raw_links, ref_map, spans)

        self.assertEqual(len(edges), 1)
        self.assertAlmostEqual(edges[0].strength, 0.8, places=3)
        self.assertEqual(edges[0].note, "strong")

    def test_prune_edges_top_k_by_strength(self):
        spans = [
            self._span("A", 0),
            self._span("B", 1),
            self._span("C", 2),
            self._span("D", 3),
            self._span("X", 4),
            self._span("Y", 5),
            self._span("Z", 6),
        ]
        order = {s.span_id: s.order_index for s in spans}

        edges = [
            Edge("A", "B", "conflict", 0.6, source_order=order["A"], target_order=order["B"]),
            Edge("A", "C", "same_topic", 0.9, source_order=order["A"], target_order=order["C"]),
            Edge("A", "D", "elaboration", 0.8, source_order=order["A"], target_order=order["D"]),
            Edge("B", "X", "same_topic", 0.95, source_order=order["B"], target_order=order["X"]),
            Edge("B", "Y", "continuation", 0.94, source_order=order["B"], target_order=order["Y"]),
            Edge("B", "Z", "dependency", 0.93, source_order=order["B"], target_order=order["Z"]),
            Edge("C", "X", "elaboration", 0.96, source_order=order["C"], target_order=order["X"]),
            Edge("C", "Y", "same_topic", 0.95, source_order=order["C"], target_order=order["Y"]),
            Edge("D", "X", "elaboration", 0.97, source_order=order["D"], target_order=order["X"]),
            Edge("D", "Y", "same_topic", 0.95, source_order=order["D"], target_order=order["Y"]),
        ]

        pruned = self.builder.prune_edges(edges, tau=0.0, top_k=2, max_edges=100)
        kept = {(e.source_span_id, e.target_span_id) for e in pruned}

        self.assertIn(("A", "C"), kept)
        self.assertIn(("A", "D"), kept)
        self.assertNotIn(("A", "B"), kept)

    def test_process_windows_parallel_emits_refs_and_error_details(self):
        async def _run():
            spans = [self._span("A", 0), self._span("B", 1), self._span("C", 2)]
            windows = [
                ([spans[0], spans[1]], {"A": "S1", "B": "S2"}),
                ([spans[1], spans[2]], {"B": "S1", "C": "S2"}),
            ]
            event_queue = asyncio.Queue()

            async def _fake_process_window_async(
                window_index,
                window_spans,
                ref_map,
                llm,
                llm_model,
                use_streaming_llm,
                tau,
                top_k,
                max_edges_per_window,
            ):
                await asyncio.sleep(0 if window_index == 1 else 0.01)
                if window_index == 2:
                    raise TimeoutError()
                return type(
                    "WindowResultStub",
                    (),
                    {
                        "window_index": window_index,
                        "ref_map": ref_map,
                        "raw_links": [{"source": "S1", "target": "S2", "type": "continuation", "strength": 0.8}],
                        "pruned_edges": [],
                        "noise_refs": [],
                    },
                )()

            self.builder._process_window_async = _fake_process_window_async

            results = await self.builder._process_windows_parallel(
                windows=windows,
                llm=object(),
                llm_model=None,
                use_streaming_llm=False,
                tau=0.6,
                top_k=3,
                max_edges_per_window=8,
                max_concurrent=2,
                event_queue=event_queue,
            )

            events = []
            while not event_queue.empty():
                events.append(await event_queue.get())

            self.assertEqual([result.window_index for result in results], [1])
            self.assertEqual(events[0].event, "window_start")
            self.assertEqual(events[0].data["span_refs"], ["S1", "S2"])
            self.assertEqual(events[1].event, "window_start")
            self.assertEqual(events[1].data["span_refs"], ["S1", "S2"])
            self.assertEqual(events[2].event, "window_complete")
            self.assertEqual(events[2].data["window_index"], 1)
            self.assertEqual(events[3].event, "window_error")
            self.assertEqual(events[3].data["window_index"], 2)
            self.assertEqual(events[3].data["error"], "TimeoutError")

        asyncio.run(_run())

    @unittest.skipUnless(
        _llm_available(),
        "Live LLM test skipped (missing provider config/API key).",
    )
    def test_llm_generate_links_smoke(self):
        spans = [self._span("A", 0), self._span("B", 1), self._span("C", 2)]
        ref_map = {"A": "S1", "B": "S2", "C": "S3"}

        llm = self.builder._get_llm_client(mock_mode=False)
        links, noise = llm.generate_links(spans, ref_map)

        self.assertIsInstance(links, list)
        self.assertIsInstance(noise, list)
        for link in links:
            self.assertIn(link.get("source"), ref_map.values())
            self.assertIn(link.get("target"), ref_map.values())
            self.assertIn(link.get("type"), RELATION_TYPES)

        parsed_edges = self.builder.parse_window_edges(links, ref_map, spans)
        pruned_edges = self.builder.prune_edges(parsed_edges, tau=0.6, top_k=2, max_edges=10)

        for edge in pruned_edges:
            self.assertNotEqual(edge.source_span_id, edge.target_span_id)
            self.assertIn(edge.relation_type, RELATION_TYPES)
            self.assertGreaterEqual(edge.strength, 0.6)


if __name__ == "__main__":
    unittest.main()
