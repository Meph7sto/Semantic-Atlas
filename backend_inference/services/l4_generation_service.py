"""
L4 Generation Service - L4 需求生成服务

职责：
1. TopReq 预处理：识别 L1/L2/L3 层级，提取关键词
2. RAG 检索：从三类 KB 检索相关证据
3. LLM 结构化生成：调用 DeepSeekEngine 生成结构化 L4
"""

import json
import re
from typing import Any, Dict, List, Literal, Optional, Tuple
from uuid import uuid4

from core.model_container import model_engine
from schemas.kb_schemas import EvidenceItem
from schemas.l4_schemas import (
    GenerateConfig,
    GenerateL4Response,
    GenerateL4Result,
    L4Requirement,
    TopRequirement,
    ValidatorStatus,
)
from services.kb_service import get_kb_service
from core.engine.remote.deepseek import DEFAULT_DEEPSEEK_MODEL
from services.l4_validator_service import get_l4_validator_service


# ========================
# 层级识别关键词
# ========================
L1_KEYWORDS = ["目标", "愿景", "价值", "目的", "意义", "why", "战略"]
L2_KEYWORDS = ["场景", "用户", "痛点", "需要", "希望", "体验", "流程", "角色"]
L3_KEYWORDS = ["功能", "能力", "系统应", "支持", "提供", "实现", "接口", "模块"]


# ========================
# 要素关键词 (用于校验器)
# ========================
INTERFACE_KEYWORDS = ["接口", "对接", "调用", "返回", "请求", "响应", "API", "HTTP"]
DATA_KEYWORDS = ["字段", "格式", "存储", "数据库", "导出", "导入", "表", "列", "JSON"]
ERROR_KEYWORDS = ["失败", "异常", "超时", "重试", "降级", "错误", "异常处理"]
NFR_KEYWORDS = ["性能", "延迟", "并发", "吞吐", "安全", "审计", "日志", "监控"]


# ========================
# Prompt 模板
# ========================
SYSTEM_PROMPT = """你是一个专业的软件需求分析师，负责将顶层需求分解为 L4 软件需求。

L4 需求的特征：
- 分配给软件实现的系统要素
- 关注模块/接口/数据/算法/UI/错误处理
- 必须可实现、可测试、可验收

输出要求：
1. 严格输出 JSON 格式，不要输出任何额外文字
2. 每条 L4 使用 shall 句式："[主体] shall [动作] [对象] [约束条件]"
3. 必须包含 acceptance_criteria（验收口径）
4. 禁止使用模糊词如"尽量"、"适当"、"友好"、"合理"
5. 如果缺少细节信息（如具体参数、部署方式等），请基于通用软件工程经验进行合理假设（Make Assumptions）以生成完整需求，而不是直接拒绝。
6. 仅当需求完全无法理解或根本无法推导时，才在 open_questions 中列出问题。

输出 JSON Schema：
{
  "l4_requirements": [
    {
      "shall_statement": "系统 shall ...",
      "component": "模块名（不确定填 TBD）",
      "acceptance_criteria": ["验收条件1", "验收条件2"],
      "test_method": "unit|integration|system|analysis|manual|TBD",
      "interfaces": ["涉及的接口（可空）"],
      "data_contracts": ["数据约束（可空）"],
      "error_handling": ["错误处理（可空）"],
      "nfr": ["非功能需求（可空）"],
      "confidence": 0.8,
      "evidence_ids": ["使用的证据 ID，如果没有则留空"]
    }
  ],
  "open_questions": ["仅在完全无法生成时才填写"]
}
"""

MAX_JSON_RETRIES = 1


def _identify_level(text: str) -> Literal["L1", "L2", "L3", "unknown"]:
    """识别需求层级"""
    text_lower = text.lower()

    l1_score = sum(1 for kw in L1_KEYWORDS if kw in text_lower)
    l2_score = sum(1 for kw in L2_KEYWORDS if kw in text_lower)
    l3_score = sum(1 for kw in L3_KEYWORDS if kw in text_lower)

    if l1_score >= l2_score and l1_score >= l3_score and l1_score > 0:
        return "L1"
    elif l2_score >= l3_score and l2_score > 0:
        return "L2"
    elif l3_score > 0:
        return "L3"
    else:
        return "unknown"


def _extract_keywords(text: str) -> List[str]:
    """提取关键词"""
    keywords = []

    # 提取名词短语（简化版）
    # 按标点分割，取长度 >= 2 的词
    parts = re.split(r"[，。、；：！？,.:;!?\s]+", text)
    for part in parts:
        if 2 <= len(part) <= 20:
            keywords.append(part)

    return keywords[:10]  # 最多返回 10 个


def _build_generation_prompt(
    top_req: TopRequirement,
    pattern_evidences: List[EvidenceItem],
    spec_evidences: List[EvidenceItem],
    nfr_evidences: List[EvidenceItem],
    level: str,
) -> str:
    """构建生成 Prompt"""

    prompt_parts = []

    # 输入需求
    prompt_parts.append(f"## 输入顶层需求 (ID: {top_req.id}, 层级: {level})")
    prompt_parts.append(top_req.text)
    prompt_parts.append("")

    # Pattern 证据
    if pattern_evidences:
        prompt_parts.append("## 参考分解范式 (高层→低层)")
        for ev in pattern_evidences:
            prompt_parts.append(f"[{ev.evidence_id}] {ev.text}")
        prompt_parts.append("")

    # Spec 证据
    if spec_evidences:
        prompt_parts.append("## 必须遵守的规范")
        for ev in spec_evidences:
            prompt_parts.append(f"[{ev.evidence_id}] {ev.text}")
        prompt_parts.append("")

    # NFR 证据
    if nfr_evidences:
        prompt_parts.append("## 可参考的 NFR 模板")
        for ev in nfr_evidences:
            prompt_parts.append(f"[{ev.evidence_id}] {ev.text}")
        prompt_parts.append("")

    # 任务指令
    prompt_parts.append("## 任务")
    prompt_parts.append("请将上述顶层需求分解为可实现的 L4 软件需求。")
    prompt_parts.append("必须在 evidence_ids 中引用你使用的证据 ID。")
    prompt_parts.append("只输出 JSON，不要输出其他内容。")

    return "\n".join(prompt_parts)


def _parse_llm_response(response: str) -> Tuple[List[Dict], List[str]]:
    """解析 LLM 响应"""
    # 尝试提取 JSON
    try:
        # 尝试直接解析
        data = json.loads(response)
    except json.JSONDecodeError:
        # 尝试从 markdown 代码块提取
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", response)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
            except json.JSONDecodeError:
                return [], ["无法解析 LLM 输出的 JSON"]
        else:
            # 尝试提取 {...}
            brace_match = re.search(r"\{[\s\S]*\}", response)
            if brace_match:
                try:
                    data = json.loads(brace_match.group(0))
                except json.JSONDecodeError:
                    return [], ["无法解析 LLM 输出的 JSON"]
            else:
                return [], ["LLM 输出不包含有效 JSON"]

    l4_list = data.get("l4_requirements", [])
    open_questions = data.get("open_questions", [])

    return l4_list, open_questions


def _needs_json_retry(open_questions: List[str]) -> bool:
    return any(
        question in ("无法解析 LLM 输出的 JSON", "LLM 输出不包含有效 JSON")
        for question in open_questions
    )


class L4GenerationService:
    """L4 生成服务"""

    def __init__(self):
        self._kb_service = None
        self._model_id = DEFAULT_DEEPSEEK_MODEL

    def _get_kb_service(self):
        """获取 KB Service"""
        if self._kb_service is None:
            self._kb_service = get_kb_service()
        return self._kb_service

    def _call_generation_model(
        self,
        prompt: str,
        system_prompt: str,
        model_id: Optional[str],
        use_thinking_mode: bool = True,
    ) -> str:
        return model_engine.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            max_new_tokens=4096,
            model=model_id,
            thinking_enabled=use_thinking_mode,
        )

    def preprocess(self, top_req: TopRequirement) -> Dict[str, Any]:
        """
        TopReq 预处理

        Returns:
            {
                "level": "L1"|"L2"|"L3"|"unknown",
                "keywords": [...],
                "search_query": "..."
            }
        """
        level = _identify_level(top_req.text)
        keywords = _extract_keywords(top_req.text)

        # 构建检索查询（结合关键词）
        search_query = top_req.text
        if keywords:
            search_query = " ".join(keywords[:5]) + " " + top_req.text[:100]

        return {
            "level": level,
            "keywords": keywords,
            "search_query": search_query,
        }

    def retrieve_evidences(
        self,
        query: str,
        config: GenerateConfig,
    ) -> Tuple[List[EvidenceItem], List[EvidenceItem], List[EvidenceItem]]:
        """
        RAG 检索

        Returns:
            (pattern_evidences, spec_evidences, nfr_evidences)
        """
        kb = self._get_kb_service()

        # 检索三类 KB
        pattern_resp = kb.search(query, kb_type="pattern", top_k=config.top_k_pattern)
        spec_resp = kb.search(query, kb_type="spec", top_k=config.top_k_spec)
        nfr_resp = kb.search(query, kb_type="nfr", top_k=config.top_k_nfr)

        return pattern_resp.items, spec_resp.items, nfr_resp.items

    def generate_l4_for_single(
        self,
        top_req: TopRequirement,
        config: GenerateConfig,
        model_id: Optional[str] = None,
        use_thinking_mode: bool = True,
    ) -> GenerateL4Result:
        """为单条顶层需求生成 L4"""

        # 1. 预处理
        preprocess_result = self.preprocess(top_req)
        level = preprocess_result["level"]
        search_query = preprocess_result["search_query"]

        # 2. RAG 检索
        pattern_evs, spec_evs, nfr_evs = self.retrieve_evidences(search_query, config)
        allowed_evidence_ids = {
            evidence.evidence_id for evidence in (pattern_evs + spec_evs + nfr_evs)
        }

        # 3. 构建 Prompt
        prompt = _build_generation_prompt(
            top_req=top_req,
            pattern_evidences=pattern_evs,
            spec_evidences=spec_evs,
            nfr_evidences=nfr_evs,
            level=level,
        )

        # 4. 调用 LLM
        try:
            response = self._call_generation_model(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT,
                model_id=model_id,
                use_thinking_mode=use_thinking_mode,
            )
        except Exception as e:
            return GenerateL4Result(
                source_top_id=top_req.id,
                l4_requirements=[],
                open_questions=[f"LLM 调用失败: {str(e)}"],
            )

        # 5. 解析响应
        l4_dicts, open_questions = _parse_llm_response(response)

        # 6. 转换为 L4Requirement 对象
        l4_requirements = []
        for l4_dict in l4_dicts:
            try:
                l4 = L4Requirement(
                    source_top_id=top_req.id,
                    source_top_text=top_req.text,
                    l4_id=f"L4-{uuid4().hex[:8]}",
                    component=l4_dict.get("component", "TBD"),
                    shall_statement=l4_dict.get("shall_statement", ""),
                    acceptance_criteria=l4_dict.get("acceptance_criteria", []),
                    test_method=l4_dict.get("test_method", "TBD"),
                    interfaces=l4_dict.get("interfaces", []),
                    data_contracts=l4_dict.get("data_contracts", []),
                    error_handling=l4_dict.get("error_handling", []),
                    nfr=l4_dict.get("nfr", []),
                    open_questions=l4_dict.get("open_questions", []),
                    evidence_ids=l4_dict.get("evidence_ids", []),
                    confidence=l4_dict.get("confidence", 0.5),
                    issues=l4_dict.get("issues", []),
                )
                l4_requirements.append(l4)
            except Exception as e:
                open_questions.append(f"L4 解析失败: {str(e)}")

        # 7. 限制数量
        if len(l4_requirements) > config.max_l4_per_top_req:
            l4_requirements = l4_requirements[: config.max_l4_per_top_req]

        # 8. 规则校验 + 覆盖率门禁
        validator = get_l4_validator_service()
        validation_result = validator.validate_batch(
            l4_requirements,
            expected_top_ids=[top_req.id],
            allowed_evidence_ids=list(allowed_evidence_ids),
            confidence_threshold=config.confidence_threshold,
        )
        passed_requirements = [
            l4 for l4 in l4_requirements if l4.validator_status.passed
        ]

        if passed_requirements:
            l4_requirements = passed_requirements
            if len(l4_requirements) < config.min_l4_per_top_req and not open_questions:
                open_questions.append(
                    f"生成的 L4 数量 ({len(l4_requirements)}) 少于最小要求 ({config.min_l4_per_top_req})"
                )
        else:
            issue_messages = []
            for issues in validation_result.per_item_issues.values():
                for issue in issues:
                    if issue.severity == "error":
                        issue_messages.append(f"{issue.rule}: {issue.message}")
            issue_messages = list(dict.fromkeys(issue_messages))

            if not open_questions:
                if issue_messages:
                    summary = "；".join(issue_messages[:3])
                    open_questions.append(
                        f"未产出通过校验的 L4，需要补充信息以满足约束：{summary}"
                    )
                else:
                    open_questions.append("未产出通过校验的 L4，请补充约束信息后再生成")

            l4_requirements = []

        return GenerateL4Result(
            source_top_id=top_req.id,
            l4_requirements=l4_requirements,
            open_questions=open_questions,
        )

    def generate_l4(
        self,
        requirements: List[TopRequirement],
        config: Optional[GenerateConfig] = None,
        model_id: Optional[str] = None,
        use_thinking_mode: bool = True,
    ) -> GenerateL4Response:
        """批量生成 L4"""

        if config is None:
            config = GenerateConfig()

        resolved_model_id = (
            model_id or getattr(model_engine, "deepseek_model", None) or self._model_id
        )

        # 确保 KB 已加载
        kb = self._get_kb_service()
        kb_version = kb.ensure_loaded()

        # 逐条生成；仅在 JSON 解析失败时延后重试
        results: List[Optional[GenerateL4Result]] = [None] * len(requirements)
        retry_queue: List[Tuple[int, TopRequirement]] = []

        for idx, req in enumerate(requirements):
            result = self.generate_l4_for_single(
                req,
                config,
                model_id=resolved_model_id,
                use_thinking_mode=use_thinking_mode,
            )
            results[idx] = result
            if not result.l4_requirements and _needs_json_retry(result.open_questions):
                retry_queue.append((idx, req))

        for retry_round in range(MAX_JSON_RETRIES):
            if not retry_queue:
                break

            current_queue = retry_queue
            retry_queue = []

            for idx, req in current_queue:
                result = self.generate_l4_for_single(
                    req,
                    config,
                    model_id=resolved_model_id,
                    use_thinking_mode=use_thinking_mode,
                )
                if result.l4_requirements:
                    for l4 in result.l4_requirements:
                        l4.issues.append(f"json_retried:{retry_round + 1}")
                results[idx] = result
                if not result.l4_requirements and _needs_json_retry(result.open_questions):
                    retry_queue.append((idx, req))

        return GenerateL4Response(
            results=[result for result in results if result is not None],
            kb_version=kb_version,
            prompt_version="v1.0",
            model_id=resolved_model_id,
        )


# ========================
# 全局单例
# ========================
_l4_generation_service: Optional[L4GenerationService] = None


def get_l4_generation_service() -> L4GenerationService:
    """获取 L4 生成服务单例"""
    global _l4_generation_service
    if _l4_generation_service is None:
        _l4_generation_service = L4GenerationService()
    return _l4_generation_service
