"""
L4 Generation System Tests

验证：
1. KB 可持久化复用（第一次 build，第二次 load）
2. 检索返回带 evidence_id + score + metadata
3. 生成结果必须引用 evidence_ids
"""

import os
import sys
import shutil
import tempfile
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend_inference"))

import pytest


class TestKBService:
    """KB Service 测试"""

    @pytest.fixture
    def temp_persist_dir(self):
        """创建临时持久化目录"""
        temp_dir = tempfile.mkdtemp(prefix="kb_test_")
        yield temp_dir
        # 清理
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_kb_build_and_persist(self, temp_persist_dir):
        """测试 KB 构建和持久化"""
        from backend_inference.services.kb_service import KBService

        # 第一次：构建索引
        kb1 = KBService(persist_dir=temp_persist_dir)
        version1 = kb1.build_indexes()

        assert version1, "KB version should not be empty"
        assert kb1._is_loaded, "KB should be loaded after build"
        assert kb1._pattern_count > 0 or kb1._spec_count > 0, "KB should have some entries"

        # 检查持久化文件存在
        version_file = Path(temp_persist_dir) / "version.json"
        assert version_file.exists(), "version.json should exist"

    def test_kb_load_from_persist(self, temp_persist_dir):
        """测试从持久化加载 KB"""
        from backend_inference.services.kb_service import KBService

        # 第一次：构建索引
        kb1 = KBService(persist_dir=temp_persist_dir)
        version1 = kb1.build_indexes()

        # 第二次：从持久化加载
        kb2 = KBService(persist_dir=temp_persist_dir)
        loaded = kb2.load_indexes()

        assert loaded, "Should load from persist successfully"
        assert kb2._kb_version == version1, "Version should match"
        assert kb2._is_loaded, "KB should be loaded"

    def test_kb_search_returns_evidence_with_metadata(self, temp_persist_dir):
        """测试检索返回带 evidence_id + score + metadata"""
        from backend_inference.services.kb_service import KBService

        kb = KBService(persist_dir=temp_persist_dir)
        kb.build_indexes()

        # 搜索
        response = kb.search(query="系统登录", kb_type="spec", top_k=3)

        assert response.kb_version, "Response should have kb_version"
        assert len(response.items) > 0, "Should return some items"

        for item in response.items:
            assert item.evidence_id, "Item should have evidence_id"
            assert item.evidence_id.startswith(("pattern-", "spec-", "nfr-")), \
                f"evidence_id format incorrect: {item.evidence_id}"
            assert isinstance(item.score, float), "Score should be float"
            assert item.kb_type in ("pattern", "spec", "nfr"), "kb_type should be valid"
            assert isinstance(item.metadata, dict), "metadata should be dict"

    def test_evidence_id_stable_across_restart(self, temp_persist_dir):
        """测试 evidence_id 在不同启动中保持稳定"""
        from backend_inference.services.kb_service import KBService

        # 第一次启动
        kb1 = KBService(persist_dir=temp_persist_dir)
        kb1.build_indexes()
        response1 = kb1.search(query="验收", kb_type="spec", top_k=5)
        ids1 = {item.evidence_id for item in response1.items}

        # 第二次启动（模拟重启）
        kb2 = KBService(persist_dir=temp_persist_dir)
        kb2.load_indexes()
        response2 = kb2.search(query="验收", kb_type="spec", top_k=5)
        ids2 = {item.evidence_id for item in response2.items}

        # 应该有相同的 evidence_ids
        assert ids1 == ids2, "evidence_ids should be stable across restart"


class TestL4Validator:
    """L4 Validator 测试"""

    def test_validator_check_evidence_ids(self):
        """测试校验器检查 evidence_ids"""
        from backend_inference.schemas.l4_schemas import L4Requirement
        from backend_inference.services.l4_validator_service import L4ValidatorService

        validator = L4ValidatorService()

        # 没有 evidence_ids 的 L4 应该失败
        l4_no_evidence = L4Requirement(
            source_top_id="REQ-001",
            shall_statement="系统 shall 支持用户登录",
            acceptance_criteria=["用户能成功登录"],
            evidence_ids=[],  # 空的 evidence_ids
        )

        status = validator.validate_single(l4_no_evidence)
        assert not status.passed, "L4 without evidence_ids should fail"

        # 检查是否有 evidence_reference 规则的 issue
        has_evidence_issue = any(
            issue.rule == "evidence_reference" for issue in status.issues
        )
        assert has_evidence_issue, "Should have evidence_reference issue"

    def test_validator_check_fuzzy_words(self):
        """测试校验器检查模糊词"""
        from backend_inference.schemas.l4_schemas import L4Requirement
        from backend_inference.services.l4_validator_service import L4ValidatorService

        validator = L4ValidatorService()

        # 包含模糊词的 L4 应该失败
        l4_fuzzy = L4Requirement(
            source_top_id="REQ-001",
            shall_statement="系统 shall 尽量快速响应用户请求",  # 包含 "尽量"
            acceptance_criteria=["响应时间适当"],  # 包含 "适当"
            evidence_ids=["spec-001"],
        )

        status = validator.validate_single(l4_fuzzy)
        assert not status.passed, "L4 with fuzzy words should fail"

        # 检查是否有 implementability 规则的 issue
        has_impl_issue = any(
            issue.rule == "implementability" for issue in status.issues
        )
        assert has_impl_issue, "Should have implementability issue"

    def test_validator_check_testability(self):
        """测试校验器检查可测试性"""
        from backend_inference.schemas.l4_schemas import L4Requirement
        from backend_inference.services.l4_validator_service import L4ValidatorService

        validator = L4ValidatorService()

        # 没有 acceptance_criteria 的 L4 应该失败
        l4_no_criteria = L4Requirement(
            source_top_id="REQ-001",
            shall_statement="系统 shall 支持用户登录",
            acceptance_criteria=[],  # 空的验收条件
            evidence_ids=["spec-001"],
        )

        status = validator.validate_single(l4_no_criteria)
        assert not status.passed, "L4 without acceptance_criteria should fail"

        # 检查是否有 testability 规则的 issue
        has_test_issue = any(
            issue.rule == "testability" for issue in status.issues
        )
        assert has_test_issue, "Should have testability issue"

    def test_validator_pass_valid_l4(self):
        """测试校验器通过有效的 L4"""
        from backend_inference.schemas.l4_schemas import L4Requirement
        from backend_inference.services.l4_validator_service import L4ValidatorService

        validator = L4ValidatorService()

        # 有效的 L4
        l4_valid = L4Requirement(
            source_top_id="REQ-001",
            shall_statement="登录模块 shall 在用户输入正确的手机号和验证码后完成身份验证",
            acceptance_criteria=[
                "输入正确手机号和验证码后，系统返回登录成功状态码 200",
                "登录成功后，返回有效的 JWT token",
            ],
            evidence_ids=["pattern-0001", "spec-003"],
            confidence=0.8,
        )

        status = validator.validate_single(l4_valid)
        # 只检查是否有 error 级别的 issue
        errors = [i for i in status.issues if i.severity == "error"]
        assert len(errors) == 0, f"Valid L4 should have no errors: {errors}"


class TestL4GenerationService:
    """L4 Generation Service 测试"""

    def test_preprocess_level_detection(self):
        """测试需求层级识别"""
        from backend_inference.schemas.l4_schemas import TopRequirement
        from backend_inference.services.l4_generation_service import L4GenerationService

        service = L4GenerationService()

        # L1 测试
        req_l1 = TopRequirement(id="1", text="提升用户体验是我们的核心目标和价值")
        result = service.preprocess(req_l1)
        assert result["level"] in ("L1", "unknown")

        # L2 测试
        req_l2 = TopRequirement(id="2", text="用户希望能够快速完成登录流程")
        result = service.preprocess(req_l2)
        assert result["level"] in ("L2", "L3", "unknown")

        # L3 测试
        req_l3 = TopRequirement(id="3", text="系统应支持手机号短信验证码登录功能")
        result = service.preprocess(req_l3)
        assert result["level"] in ("L3", "unknown")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
