"""
Unit tests for requirements deduplication service.

Tests detection, merging, and the deduplication pipeline.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend_business.services.requirements_deduplication.detector import (
    DuplicateDetector,
)
from backend_business.services.requirements_deduplication.executor import (
    DeduplicationExecutor,
)
from backend_business.services.requirements_deduplication.merger import (
    RequirementMerger,
)
from backend_business.services.requirements_deduplication.models import (
    DuplicateGroup,
    MergeDecision,
    MergeResult,
)
from backend_business.services.requirements_deduplication.service import (
    RequirementsDeduplicationService,
)


class TestDuplicateDetector(unittest.TestCase):
    """Tests for duplicate detection logic."""

    def setUp(self):
        self.detector = DuplicateDetector(similarity_threshold=0.85)

    def test_normalize_text(self):
        """Test text normalization for comparison."""
        text = "  Hello, World!  "
        normalized = self.detector._normalize_text(text)
        self.assertEqual(normalized, "helloworld")

    def test_normalize_text_chinese(self):
        """Test text normalization with Chinese punctuation."""
        text = "用户需要登录系统，验证身份。"
        normalized = self.detector._normalize_text(text)
        self.assertEqual(normalized, "用户需要登录系统验证身份")

    def test_compute_similarity_identical(self):
        """Test similarity of identical texts."""
        similarity = self.detector._compute_similarity(
            "用户需要登录系统", "用户需要登录系统"
        )
        self.assertEqual(similarity, 1.0)

    def test_compute_similarity_similar(self):
        """Test similarity of similar texts."""
        similarity = self.detector._compute_similarity(
            "用户需要登录系统进行身份验证", "用户需要登录系统验证身份"
        )
        # Actual similarity may vary, just check it's reasonable
        self.assertGreater(similarity, 0.7)

    def test_compute_similarity_different(self):
        """Test similarity of different texts."""
        similarity = self.detector._compute_similarity(
            "用户登录系统", "系统需要支持文件上传"
        )
        self.assertLess(similarity, 0.5)

    def test_compute_similarity_empty(self):
        """Test similarity with empty text."""
        similarity = self.detector._compute_similarity("", "some text")
        self.assertEqual(similarity, 0.0)

    def test_detect_duplicates_no_duplicates(self):
        """Test detection when no duplicates exist."""
        requirements = [
            {"req_id": "r1", "level": "L1", "text": "系统需要支持用户登录"},
            {"req_id": "r2", "level": "L1", "text": "系统需要支持文件上传"},
            {"req_id": "r3", "level": "L1", "text": "系统需要支持数据导出"},
        ]
        groups = self.detector.detect_duplicates(requirements, by_level=True)
        self.assertEqual(len(groups), 0)

    def test_detect_duplicates_with_duplicates(self):
        """Test detection when duplicates exist."""
        # Use very similar texts that will definitely exceed 0.85 threshold
        requirements = [
            {"req_id": "r1", "level": "L2", "text": "用户需要登录系统进行身份验证"},
            {
                "req_id": "r2",
                "level": "L2",
                "text": "用户需要登录系统进行身份验证功能",
            },  # Very similar
            {"req_id": "r3", "level": "L2", "text": "系统需要支持文件上传"},
        ]
        groups = self.detector.detect_duplicates(requirements, by_level=True)
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0].requirements), 2)
        self.assertEqual(groups[0].level, "L2")

    def test_detect_duplicates_by_level(self):
        """Test that detection respects level boundaries."""
        requirements = [
            {"req_id": "r1", "level": "L1", "text": "用户需要登录系统"},
            {
                "req_id": "r2",
                "level": "L2",
                "text": "用户需要登录系统",
            },  # Same text, different level
        ]
        groups = self.detector.detect_duplicates(requirements, by_level=True)
        # Should NOT detect as duplicates because they are in different levels
        self.assertEqual(len(groups), 0)

    def test_detect_duplicates_cross_level(self):
        """Test detection across levels when by_level=False."""
        requirements = [
            {"req_id": "r1", "level": "L1", "text": "用户需要登录系统"},
            {"req_id": "r2", "level": "L2", "text": "用户需要登录系统"},
        ]
        groups = self.detector.detect_duplicates(requirements, by_level=False)
        # Should detect as duplicates when by_level=False
        self.assertEqual(len(groups), 1)

    def test_detect_duplicates_empty_list(self):
        """Test detection with empty requirements list."""
        groups = self.detector.detect_duplicates([], by_level=True)
        self.assertEqual(len(groups), 0)

    def test_detect_duplicates_single_requirement(self):
        """Test detection with single requirement."""
        requirements = [{"req_id": "r1", "level": "L1", "text": "用户需要登录"}]
        groups = self.detector.detect_duplicates(requirements, by_level=True)
        self.assertEqual(len(groups), 0)

    def test_find_similar_pairs(self):
        """Test finding similar pairs."""
        # Use very similar texts that will definitely exceed 0.85 threshold
        requirements = [
            {"req_id": "r1", "level": "L2", "text": "用户需要登录系统进行身份验证"},
            {
                "req_id": "r2",
                "level": "L2",
                "text": "用户需要登录系统进行身份验证功能",
            },  # Very similar
            {"req_id": "r3", "level": "L2", "text": "系统需要支持文件上传"},
        ]
        pairs = self.detector.find_similar_pairs(requirements, by_level=True)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["req_1"]["req_id"], "r1")
        self.assertEqual(pairs[0]["req_2"]["req_id"], "r2")
        self.assertGreater(pairs[0]["similarity"], 0.8)

    def test_threshold_sensitivity(self):
        """Test that threshold affects detection."""
        requirements = [
            {"req_id": "r1", "level": "L2", "text": "用户登录系统"},
            {"req_id": "r2", "level": "L2", "text": "用户注册系统"},
        ]

        # High threshold - should not detect
        high_detector = DuplicateDetector(similarity_threshold=0.95)
        groups_high = high_detector.detect_duplicates(requirements, by_level=True)

        # Low threshold - might detect
        low_detector = DuplicateDetector(similarity_threshold=0.5)
        groups_low = low_detector.detect_duplicates(requirements, by_level=True)

        # The exact result depends on similarity, but low threshold should be >= high
        self.assertGreaterEqual(len(groups_low), len(groups_high))


class TestDeduplicationExecutor(unittest.TestCase):
    """Tests for merge and delete execution."""

    def test_compute_fingerprint(self):
        """Test fingerprint computation."""
        fp1 = DeduplicationExecutor._compute_fingerprint(
            "session1", "L2", "用户需要登录系统"
        )
        fp2 = DeduplicationExecutor._compute_fingerprint(
            "session1", "L2", "用户需要登录系统"
        )
        fp3 = DeduplicationExecutor._compute_fingerprint(
            "session1",
            "L2",
            "  用户需要登录系统  ",  # With whitespace
        )

        # Same content should produce same fingerprint
        self.assertEqual(fp1, fp2)
        self.assertEqual(fp1, fp3)

    def test_compute_fingerprint_different(self):
        """Test fingerprints for different content."""
        fp1 = DeduplicationExecutor._compute_fingerprint("session1", "L2", "用户登录")
        fp2 = DeduplicationExecutor._compute_fingerprint("session1", "L2", "用户注册")
        fp3 = DeduplicationExecutor._compute_fingerprint(
            "session1",
            "L1",
            "用户登录",  # Different level
        )
        fp4 = DeduplicationExecutor._compute_fingerprint(
            "session2",
            "L2",
            "用户登录",  # Different session
        )

        self.assertNotEqual(fp1, fp2)
        self.assertNotEqual(fp1, fp3)
        self.assertNotEqual(fp1, fp4)

    @patch.object(DeduplicationExecutor, "_connect")
    def test_merge_requirements_validation(self, mock_connect):
        """Test merge validation."""
        executor = DeduplicationExecutor(dsn="postgresql://test")

        # Missing primary_req_id
        result = executor.merge_requirements(
            session_id="s1",
            primary_req_id="",
            to_delete_req_ids=["r2"],
            merged_text="new text here",
            merged_level="L2",
        )
        self.assertFalse(result.success)
        self.assertIn("primary_req_id", result.error)

        # Short merged_text
        result = executor.merge_requirements(
            session_id="s1",
            primary_req_id="r1",
            to_delete_req_ids=["r2"],
            merged_text="short",
            merged_level="L2",
        )
        self.assertFalse(result.success)
        self.assertIn("merged_text", result.error)

        # Invalid merged_level
        result = executor.merge_requirements(
            session_id="s1",
            primary_req_id="r1",
            to_delete_req_ids=["r2"],
            merged_text="valid text here longer",
            merged_level="L4",
        )
        self.assertFalse(result.success)
        self.assertIn("merged_level", result.error)

    @patch.object(DeduplicationExecutor, "_connect")
    def test_delete_requirements_empty_list(self, mock_connect):
        """Test delete with empty list."""
        executor = DeduplicationExecutor(dsn="postgresql://test")

        result = executor.delete_requirements(
            session_id="s1",
            req_ids=[],
        )
        self.assertFalse(result["success"])
        self.assertIn("req_ids", result["error"])

    @patch.object(DeduplicationExecutor, "_connect")
    def test_get_requirements_by_ids_empty(self, mock_connect):
        """Test get requirements with empty list."""
        executor = DeduplicationExecutor(dsn="postgresql://test")

        result = executor.get_requirements_by_ids(
            session_id="s1",
            req_ids=[],
        )
        self.assertEqual(result, [])


class TestRequirementMerger(unittest.TestCase):
    """Tests for LLM merge decision making."""

    def test_build_merge_prompt(self):
        """Test prompt construction."""
        merger = RequirementMerger(model_name="deepseek-chat")

        group_data = {
            "level": "L2",
            "requirements": [
                {"req_id": "r1", "text": "用户登录系统"},
                {"req_id": "r2", "text": "用户登录平台"},
            ],
            "similarity": 0.92,
        }

        prompt = merger._build_merge_prompt(group_data)

        self.assertIn("L2", prompt)
        self.assertIn("92", prompt)  # Could be "92.0%" or "0.92"
        self.assertIn("r1", prompt)

    @patch("backend_business.services.requirements_deduplication.merger.ai_proxy")
    def test_decide_merge_success(self, mock_ai_proxy):
        """Test successful merge decision."""
        mock_ai_proxy.chat_completion_with_tools.return_value = {
            "tool_calls": [
                {
                    "type": "function",
                    "function": {
                        "name": "merge_requirements",
                        "arguments": '{"should_merge": true, "merged_text": "用户需要登录系统", "merged_level": "L2", "primary_req_id": "r1", "reason": "语义相同"}',
                    },
                }
            ]
        }

        merger = RequirementMerger(model_name="deepseek-chat")

        group_data = {
            "level": "L2",
            "requirements": [
                {"req_id": "r1", "text": "用户登录系统"},
                {"req_id": "r2", "text": "用户登录平台"},
            ],
            "similarity": 0.92,
        }

        decision = merger.decide_merge(group_data)

        self.assertTrue(decision.should_merge)
        self.assertEqual(decision.merged_text, "用户需要登录系统")
        self.assertEqual(decision.primary_req_id, "r1")

    @patch("backend_business.services.requirements_deduplication.merger.ai_proxy")
    def test_decide_merge_no_merge(self, mock_ai_proxy):
        """Test decision when LLM says don't merge."""
        mock_ai_proxy.chat_completion_with_tools.return_value = {
            "tool_calls": [
                {
                    "type": "function",
                    "function": {
                        "name": "merge_requirements",
                        "arguments": '{"should_merge": false, "merged_text": "", "merged_level": "", "primary_req_id": "", "reason": "different functions"}',
                    },
                }
            ]
        }

        merger = RequirementMerger(model_name="deepseek-chat")

        group_data = {
            "level": "L2",
            "requirements": [
                {"req_id": "r1", "text": "用户登录系统"},
                {"req_id": "r2", "text": "用户注册系统"},
            ],
            "similarity": 0.86,
        }

        decision = merger.decide_merge(group_data)

        self.assertFalse(decision.should_merge)
        self.assertIn("different", decision.reason)

    @patch("backend_business.services.requirements_deduplication.merger.ai_proxy")
    def test_decide_merge_api_error(self, mock_ai_proxy):
        """Test handling of API errors."""
        mock_ai_proxy.chat_completion_with_tools.side_effect = Exception("API Error")

        merger = RequirementMerger(model_name="deepseek-chat")

        group_data = {
            "level": "L2",
            "requirements": [
                {"req_id": "r1", "text": "用户登录系统"},
            ],
            "similarity": 0.9,
        }

        decision = merger.decide_merge(group_data)

        self.assertFalse(decision.should_merge)
        self.assertIsNotNone(decision.error)

    @patch("backend_business.services.requirements_deduplication.merger.ai_proxy")
    def test_batch_decide_merge_parallel(self, mock_ai_proxy):
        """Test parallel batch merge decision."""
        # Mock async method
        import asyncio

        async def mock_async_call(*args, **kwargs):
            return {
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": "merge_requirements",
                            "arguments": '{"should_merge": true, "merged_text": "合并后的需求", "merged_level": "L2", "primary_req_id": "r1", "reason": "语义相同"}',
                        },
                    }
                ]
            }

        mock_ai_proxy.chat_completion_with_tools_async = mock_async_call

        merger = RequirementMerger(model_name="deepseek-chat")

        groups = [
            {
                "level": "L2",
                "requirements": [
                    {"req_id": "r1", "text": "用户登录系统"},
                    {"req_id": "r2", "text": "用户登录平台"},
                ],
                "similarity": 0.92,
            },
            {
                "level": "L2",
                "requirements": [
                    {"req_id": "r3", "text": "数据导出功能"},
                    {"req_id": "r4", "text": "数据导出接口"},
                ],
                "similarity": 0.88,
            },
        ]

        decisions = merger.batch_decide_merge(groups, max_concurrent=2)

        self.assertEqual(len(decisions), 2)
        for decision in decisions:
            self.assertTrue(decision.should_merge)
            self.assertEqual(decision.merged_text, "合并后的需求")


class TestRequirementsDeduplicationService(unittest.TestCase):
    """Integration tests for the deduplication service."""

    @patch.object(
        RequirementsDeduplicationService, "__init__", lambda x, **kwargs: None
    )
    def setUp(self):
        self.service = RequirementsDeduplicationService.__new__(
            RequirementsDeduplicationService
        )
        self.service.dsn = "postgresql://test"
        self.service.detector = DuplicateDetector(similarity_threshold=0.85)
        self.service.merger = MagicMock()
        self.service.executor = MagicMock()
        self.service.data_access = MagicMock()
        self.service.default_model = "deepseek-chat"

    def test_detect_duplicates_empty(self):
        """Test detection with no requirements."""
        self.service.data_access.get_all_requirements_for_session.return_value = []

        result = self.service.detect_duplicates(
            session_id="test-session",
            with_llm_decision=False,
        )

        self.assertEqual(result["total_duplicates"], 0)
        self.assertEqual(result["total_requirements_scanned"], 0)

    def test_detect_duplicates_single_requirement(self):
        """Test detection with single requirement."""
        self.service.data_access.get_all_requirements_for_session.return_value = [
            {"req_id": "r1", "level": "L2", "text": "用户登录系统"}
        ]

        result = self.service.detect_duplicates(
            session_id="test-session",
            with_llm_decision=False,
        )

        self.assertEqual(result["total_duplicates"], 0)
        self.assertIn("不足", result["message"])

    def test_detect_duplicates_no_duplicates(self):
        """Test detection when no duplicates found."""
        self.service.data_access.get_all_requirements_for_session.return_value = [
            {"req_id": "r1", "level": "L2", "text": "用户登录系统"},
            {"req_id": "r2", "level": "L2", "text": "文件上传功能"},
            {"req_id": "r3", "level": "L2", "text": "数据导出接口"},
        ]

        result = self.service.detect_duplicates(
            session_id="test-session",
            with_llm_decision=False,
        )

        self.assertEqual(result["total_duplicates"], 0)
        self.assertIn("未检测到", result["message"])

    def test_detect_duplicates_with_duplicates(self):
        """Test detection with actual duplicates."""
        # Use very similar texts that will exceed 0.85 threshold
        self.service.data_access.get_all_requirements_for_session.return_value = [
            {"req_id": "r1", "level": "L2", "text": "用户需要登录系统进行身份验证"},
            {
                "req_id": "r2",
                "level": "L2",
                "text": "用户需要登录系统进行身份验证功能",
            },  # Very similar
            {"req_id": "r3", "level": "L2", "text": "系统需要支持文件上传功能"},
        ]

        result = self.service.detect_duplicates(
            session_id="test-session",
            with_llm_decision=False,
        )

        self.assertEqual(result["total_duplicates"], 1)
        self.assertEqual(result["total_requirements_scanned"], 3)
        self.assertEqual(len(result["duplicate_groups"]), 1)
        self.assertEqual(len(result["duplicate_groups"][0]["requirements"]), 2)

    def test_detect_duplicates_with_llm(self):
        """Test detection with LLM decisions."""
        # Use very similar texts that will exceed 0.85 threshold
        self.service.data_access.get_all_requirements_for_session.return_value = [
            {"req_id": "r1", "level": "L2", "text": "用户需要登录系统进行身份验证"},
            {
                "req_id": "r2",
                "level": "L2",
                "text": "用户需要登录系统进行身份验证功能",
            },  # Very similar
        ]

        mock_decision = MergeDecision(
            should_merge=True,
            merged_text="用户需要通过登录系统进行身份验证",
            merged_level="L2",
            primary_req_id="r1",
            reason="语义相同，合并为更清晰的表述",
        )
        # Updated to use batch_decide_merge (returns list)
        self.service.merger.batch_decide_merge.return_value = [mock_decision]

        result = self.service.detect_duplicates(
            session_id="test-session",
            with_llm_decision=True,
            auto_merge=False,
        )

        self.assertEqual(result["total_duplicates"], 1)
        self.assertTrue(result["duplicate_groups"][0]["llm_decision"]["should_merge"])
        self.assertEqual(
            result["duplicate_groups"][0]["llm_decision"]["primary_req_id"], "r1"
        )

    def test_detect_duplicates_with_auto_merge(self):
        """Test detection with auto-merge enabled."""
        # Use very similar texts that will exceed 0.85 threshold
        self.service.data_access.get_all_requirements_for_session.return_value = [
            {"req_id": "r1", "level": "L2", "text": "用户需要登录系统进行身份验证"},
            {
                "req_id": "r2",
                "level": "L2",
                "text": "用户需要登录系统进行身份验证功能",
            },  # Very similar
        ]

        mock_decision = MergeDecision(
            should_merge=True,
            merged_text="用户需要通过登录系统进行身份验证",
            merged_level="L2",
            primary_req_id="r1",
            reason="语义相同",
        )
        # Updated to use batch_decide_merge (returns list)
        self.service.merger.batch_decide_merge.return_value = [mock_decision]

        mock_merge_result = MergeResult(
            success=True,
            primary_req_id="r1",
            deleted_count=1,
            old_text="用户需要登录系统进行身份验证",
            new_text="用户需要通过登录系统进行身份验证",
            reason="语义相同",
        )
        self.service.executor.merge_requirements.return_value = mock_merge_result

        result = self.service.detect_duplicates(
            session_id="test-session",
            with_llm_decision=True,
            auto_merge=True,
        )

        self.assertEqual(result["total_duplicates"], 1)
        self.assertEqual(result["total_merged"], 1)
        self.assertTrue(result["duplicate_groups"][0]["merge_result"]["success"])

    def test_detect_duplicates_level_filter(self):
        """Test detection with level filter."""
        self.service.data_access.get_all_requirements_for_session.return_value = [
            {"req_id": "r1", "level": "L1", "text": "用户需要登录系统"},
            {"req_id": "r2", "level": "L1", "text": "用户需要登录系统验证身份"},
            {
                "req_id": "r3",
                "level": "L2",
                "text": "用户需要登录系统",
            },  # L2, same text
        ]

        result = self.service.detect_duplicates(
            session_id="test-session",
            level="L1",
            with_llm_decision=False,
        )

        # Only L1 requirements should be scanned
        self.assertEqual(result["total_requirements_scanned"], 2)

    def test_execute_merge(self):
        """Test manual merge execution."""
        mock_result = MergeResult(
            success=True,
            primary_req_id="r1",
            deleted_count=2,
            old_text="old text",
            new_text="merged text here",
            reason="manual merge",
        )
        self.service.executor.merge_requirements.return_value = mock_result

        result = self.service.execute_merge(
            session_id="test-session",
            primary_req_id="r1",
            to_delete_req_ids=["r2", "r3"],
            merged_text="merged text here",
            merged_level="L2",
            reason="manual merge",
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["deleted_count"], 2)

    def test_delete_requirements(self):
        """Test batch delete."""
        self.service.executor.delete_requirements.return_value = {
            "success": True,
            "deleted_count": 3,
            "reason": "duplicate cleanup",
            "error": None,
        }

        result = self.service.delete_requirements(
            session_id="test-session",
            req_ids=["r1", "r2", "r3"],
            reason="duplicate cleanup",
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["deleted_count"], 3)

    def test_get_similar_pairs(self):
        """Test getting similar pairs."""
        # Use very similar texts that will exceed 0.85 threshold
        self.service.data_access.get_all_requirements_for_session.return_value = [
            {"req_id": "r1", "level": "L2", "text": "用户需要登录系统进行身份验证"},
            {
                "req_id": "r2",
                "level": "L2",
                "text": "用户需要登录系统进行身份验证功能",
            },  # Very similar
            {"req_id": "r3", "level": "L2", "text": "系统需要支持文件上传功能"},
        ]

        result = self.service.get_similar_pairs(session_id="test-session")

        self.assertEqual(result["total_pairs"], 1)
        self.assertEqual(result["total_requirements_scanned"], 3)

    def test_regenerate_llm_decision_insufficient_reqs(self):
        """Test regenerate with insufficient requirements."""
        self.service.executor.get_requirements_by_ids.return_value = [
            {"req_id": "r1", "level": "L2", "text": "用户登录"}
        ]

        result = self.service.regenerate_llm_decision(
            session_id="test-session",
            req_ids=["r1", "r2"],
        )

        self.assertIn("error", result)
        self.assertIn("至少2个", result["error"])

if __name__ == "__main__":
    unittest.main(verbosity=2)
