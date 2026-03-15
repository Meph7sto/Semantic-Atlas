"""
Parallel extraction behavior tests for Phase 3 requirements.
"""

import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend_business.services.ego_bundle_generator import EgoBundleGenerator
from backend_business.services.requirements_extraction import (
    AnchorResult,
    RequirementsExtractionService,
)


class TestRequirementsExtractionParallel(unittest.TestCase):
    def test_parallel_errors_counted(self):
        service = RequirementsExtractionService(
            dsn="postgresql://test:test@localhost:5432/test"
        )

        spans = [
            {"span_id": "s1", "text": "a"},
            {"span_id": "s2", "text": "b"},
        ]
        service.data_access.get_spans_by_session = MagicMock(return_value=spans)

        async def fake_process(anchor_idx, **_kwargs):
            if anchor_idx == 1:
                raise RuntimeError("boom")
            return AnchorResult(
                anchor_idx=anchor_idx,
                anchor_span_id=spans[anchor_idx]["span_id"],
                bundle_r=1,
                exec_result={"inserted": 1, "duplicates": 0},
            )

        # Patch the module-level async function used by the service.
        with patch(
            "backend_business.services.requirements_extraction.service.process_anchors_parallel",
            new=AsyncMock(
                return_value=[
                    AnchorResult(
                        anchor_idx=0,
                        anchor_span_id=spans[0]["span_id"],
                        bundle_r=1,
                        exec_result={
                            "inserted": 1,
                            "duplicates": 0,
                            "status": "success",
                        },
                    ),
                    AnchorResult(
                        anchor_idx=1,
                        anchor_span_id=spans[1]["span_id"],
                        bundle_r=1,
                        exec_result={},
                        error="boom",
                    ),
                ]
            ),
        ):
            result = service.extract_requirements_for_session(
                session_id="test-session",
                bundle_strategy="sequence",
                anchor_strategy="all",
                enable_parallel=True,
                max_concurrent=2,
                adaptive_retry_r2=False,
            )

        self.assertEqual(result["total_anchors"], 2)
        self.assertEqual(result["bundles_processed"], 2)
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["anchor_idx"], 1)

    def test_parallel_forces_history_aware_off(self):
        service = RequirementsExtractionService(
            dsn="postgresql://test:test@localhost:5432/test"
        )
        service.data_access.get_spans_by_session = MagicMock(
            return_value=[{"span_id": "s1", "text": "a"}]
        )

        with patch.object(service, "_run_parallel", return_value=[]):
            result = service.extract_requirements_for_session(
                session_id="test-session",
                bundle_strategy="sequence",
                anchor_strategy="all",
                enable_parallel=True,
                max_concurrent=2,
                history_aware=True,
            )

        self.assertFalse(result["history_aware"])


class TestRequirementsExtractionAsync(unittest.IsolatedAsyncioTestCase):
    async def test_execute_bundle_runs_in_thread(self):
        service = RequirementsExtractionService(
            dsn="postgresql://test:test@localhost:5432/test"
        )

        spans = [{"span_id": "s1", "text": "need feature"}]
        bundle_generator = EgoBundleGenerator(max_spans_per_bundle=5)

        exec_result = {
            "status": "success",
            "parsed_count": 1,
            "inserted": 1,
            "duplicates": 0,
        }
        service.executor.execute_bundle = MagicMock(return_value=exec_result)

        planner_result = {"output": [{"level": "L1", "text": "test requirement text"}]}

        with patch(
            "backend_business.services.requirements_extraction.anchor_processor.call_planner_async",
            new=AsyncMock(return_value=planner_result),
        ):
            with patch(
                "backend_business.services.requirements_extraction.anchor_processor.asyncio.to_thread",
                new=AsyncMock(return_value=exec_result),
            ) as to_thread_mock:
                from backend_business.services.requirements_extraction.anchor_processor import (
                    process_anchor_async,
                )

                result = await process_anchor_async(
                    anchor_idx=0,
                    spans=spans,
                    bundle_generator=bundle_generator,
                    executor=service.executor,
                    bundle_strategy="sequence",
                    adjacency=None,
                    max_r=1,
                    adaptive_retry_r2=False,
                    effective_top_m_2hop=5,
                    session_id="test-session",
                    model_name="deepseek-chat",
                    use_toolcall=True,
                    context_run_id=None,
                    http_session=MagicMock(),
                )

        self.assertEqual(result.exec_result, exec_result)
        self.assertTrue(to_thread_mock.called)
        called_func = to_thread_mock.call_args[0][0]
        self.assertIs(called_func, service.executor.execute_bundle)


if __name__ == "__main__":
    unittest.main(verbosity=2)
