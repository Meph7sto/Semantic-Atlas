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
from types import SimpleNamespace

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

    def test_kb_falls_back_to_lexical_mode_when_embedding_unavailable(
        self, temp_persist_dir, monkeypatch
    ):
        """嵌入模型不可用时，KB 仍应可构建和检索"""
        from backend_inference.services.kb_service import KBService

        monkeypatch.setattr(KBService, "_get_embed_model", lambda self: None)

        kb = KBService(persist_dir=temp_persist_dir)
        version = kb.build_indexes()
        response = kb.search(query="系统登录", kb_type="spec", top_k=3)

        assert version, "KB version should not be empty in lexical mode"
        assert kb._is_loaded, "KB should still be marked loaded in lexical mode"
        assert len(response.items) > 0, "Lexical mode should still return evidence"
        assert all(
            item.metadata.get("retrieval_mode") == "lexical"
            for item in response.items
        ), "Fallback search should mark lexical retrieval mode"

    def test_kb_loads_from_docstore_without_csv_or_embedding(
        self, temp_persist_dir, monkeypatch
    ):
        """CSV 缺失时，仍应能从持久化 docstore 加载 spec/nfr"""
        from backend_inference.services.kb_service import KBService

        monkeypatch.setattr(KBService, "_get_embed_model", lambda self: None)

        kb1 = KBService(
            persist_dir=temp_persist_dir,
            csv_path="missing_patterns.csv",
        )
        kb1.build_indexes()

        kb2 = KBService(
            persist_dir=temp_persist_dir,
            csv_path="missing_patterns.csv",
        )
        loaded = kb2.load_indexes()
        response = kb2.search(query="性能 日志 接口", kb_type="all", top_k=5)

        assert loaded, "KB should load from persisted docstore in lexical mode"
        assert kb2._pattern_count == 0, "Missing CSV should not produce pattern entries"
        assert kb2._spec_count > 0, "Spec entries should still be available"
        assert kb2._nfr_count > 0, "NFR entries should still be available"
        assert len(response.items) > 0, "Search should still return spec/nfr evidence"


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

    def test_generate_l4_retries_json_failures_after_first_pass(self, monkeypatch):
        """JSON 解析失败的条目应在首轮结束后再重试"""
        from backend_inference.schemas.kb_schemas import EvidenceItem
        from backend_inference.schemas.l4_schemas import GenerateConfig, TopRequirement
        from backend_inference.services.l4_generation_service import L4GenerationService

        service = L4GenerationService()
        service._kb_service = SimpleNamespace(ensure_loaded=lambda: "kb-test")

        evidence = EvidenceItem(
            evidence_id="spec-001",
            kb_type="spec",
            text="L4 需求必须使用 shall 句式",
            score=1.0,
            metadata={},
        )
        monkeypatch.setattr(
            service,
            "retrieve_evidences",
            lambda query, config: ([], [evidence], []),
        )

        call_order = []

        def fake_generate(
            prompt: str,
            system_prompt: str,
            model_id: str | None,
            use_thinking_mode: bool = True,
        ) -> str:
            if "REQ-1" in prompt:
                call_order.append("REQ-1")
                if call_order.count("REQ-1") == 1:
                    return "not json"
                return """
                {
                  "l4_requirements": [
                    {
                      "shall_statement": "认证模块 shall 完成用户身份校验",
                      "component": "认证模块",
                      "acceptance_criteria": ["输入合法凭证时系统完成身份校验"],
                      "test_method": "integration",
                      "interfaces": [],
                      "data_contracts": [],
                      "error_handling": [],
                      "nfr": [],
                      "confidence": 0.8,
                      "evidence_ids": ["spec-001"]
                    }
                  ],
                  "open_questions": []
                }
                """
            call_order.append("REQ-2")
            return """
            {
              "l4_requirements": [
                {
                  "shall_statement": "会话模块 shall 记录用户登录态",
                  "component": "会话模块",
                  "acceptance_criteria": ["登录成功后系统保存有效登录态"],
                  "test_method": "integration",
                  "interfaces": [],
                  "data_contracts": [],
                  "error_handling": [],
                  "nfr": [],
                  "confidence": 0.8,
                  "evidence_ids": ["spec-001"]
                }
              ],
              "open_questions": []
            }
            """

        monkeypatch.setattr(service, "_call_generation_model", fake_generate)

        response = service.generate_l4(
            requirements=[
                TopRequirement(id="REQ-1", text="用户应能够登录系统"),
                TopRequirement(id="REQ-2", text="系统应维护用户会话"),
            ],
            config=GenerateConfig(),
            model_id="test-model",
        )

        assert call_order == ["REQ-1", "REQ-2", "REQ-1"]
        assert len(response.results) == 2
        assert response.results[0].source_top_id == "REQ-1"
        assert len(response.results[0].l4_requirements) == 1
        assert "json_retried:1" in response.results[0].l4_requirements[0].issues
        assert response.results[1].source_top_id == "REQ-2"
        assert len(response.results[1].l4_requirements) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
