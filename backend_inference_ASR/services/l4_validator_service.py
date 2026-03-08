"""
L4 Validator Service - L4 需求校验服务

硬规则校验：
1. 原子性：一条只表达一个可实现点
2. 可测试性：必须含验收口径
3. 可实现性：禁止模糊词
4. 要素完整性：按需具备接口/数据约束/错误处理/NFR
5. 禁止编造：缺信息必须有 open_questions
6. 证据引用：必须引用 evidence_ids

覆盖率门禁：
- 每条顶层需求 ≥1 条 validator pass，否则必须给 open_questions
"""

import re
from typing import Dict, List, Optional, Set

from schemas.l4_schemas import (
    CoverageSummary,
    L4Requirement,
    ValidateL4Response,
    ValidatorIssue,
    ValidatorStatus,
)
from services.kb_service import get_kb_service


# ========================
# 模糊词列表 (禁止使用)
# ========================
FUZZY_WORDS = [
    "尽量",
    "适当",
    "友好",
    "合理",
    "尽可能",
    "一般",
    "通常",
    "大约",
    "左右",
    "大概",
    "差不多",
    "基本上",
    "可能",
    "也许",
    "或许",
    "酌情",
    "灵活",
    "弹性",
    "视情况",
    "根据需要",
    "良好",
    "优秀",
    "较好",
    "较高",
    "较低",
    "适度",
]

LOW_CONFIDENCE_THRESHOLD = 0.6

# ========================
# 要素关键词
# ========================
INTERFACE_KEYWORDS = [
    "接口",
    "对接",
    "调用",
    "返回",
    "请求",
    "响应",
    "API",
    "HTTP",
    "RPC",
    "REST",
]
DATA_KEYWORDS = [
    "字段",
    "格式",
    "存储",
    "数据库",
    "导出",
    "导入",
    "表",
    "列",
    "JSON",
    "XML",
    "CSV",
]
ERROR_KEYWORDS = [
    "失败",
    "异常",
    "超时",
    "重试",
    "降级",
    "错误",
    "回滚",
    "补偿",
    "熔断",
]
NFR_KEYWORDS = [
    "性能",
    "延迟",
    "并发",
    "吞吐",
    "安全",
    "审计",
    "日志",
    "监控",
    "可用性",
    "可靠性",
]


class L4ValidatorService:
    """L4 校验服务"""

    def __init__(self):
        self._fuzzy_pattern = re.compile("|".join(re.escape(w) for w in FUZZY_WORDS))
        self._shall_pattern = re.compile(r"\bshall\b", re.IGNORECASE)
        self._kb_service = None

    def _get_kb_service(self):
        if self._kb_service is None:
            self._kb_service = get_kb_service()
        return self._kb_service

    def _check_atomicity(self, l4: L4Requirement) -> List[ValidatorIssue]:
        """检查原子性：一条只表达一个功能点"""
        issues = []
        text = l4.shall_statement

        # 检查是否包含多个"并且"、"同时"、"以及"等连接词
        connectors = ["并且", "同时", "以及", "而且", " and ", " & "]
        connector_count = sum(1 for c in connectors if c in text.lower())

        if connector_count >= 2:
            issues.append(
                ValidatorIssue(
                    rule="atomicity",
                    severity="warning",
                    message=f"需求可能不满足原子性（包含 {connector_count} 个连接词），建议拆分",
                    field="shall_statement",
                )
            )

        # 检查是否有多个动词（简化判断）
        action_verbs = ["应", "须", "必须", "shall", "should", "must", "需要", "要求"]
        verb_count = sum(1 for v in action_verbs if v in text.lower())
        if verb_count >= 3:
            issues.append(
                ValidatorIssue(
                    rule="atomicity",
                    severity="warning",
                    message=f"需求可能包含多个独立动作（{verb_count} 个动词），建议拆分",
                    field="shall_statement",
                )
            )

        return issues

    def _check_shall_format(self, l4: L4Requirement) -> List[ValidatorIssue]:
        """检查 shall 句式"""
        issues = []
        text = l4.shall_statement or ""

        if not (self._shall_pattern.search(text) or "应" in text or "必须" in text):
            issues.append(
                ValidatorIssue(
                    rule="shall_format",
                    severity="error",
                    message="需求正文未使用 shall/应/必须 句式",
                    field="shall_statement",
                )
            )

        return issues

    def _check_testability(self, l4: L4Requirement) -> List[ValidatorIssue]:
        """检查可测试性：必须含验收口径"""
        issues = []

        if not l4.acceptance_criteria or len(l4.acceptance_criteria) == 0:
            issues.append(
                ValidatorIssue(
                    rule="testability",
                    severity="error",
                    message="缺少验收口径 (acceptance_criteria)，L4 需求必须可测试",
                    field="acceptance_criteria",
                )
            )
        else:
            # 检查验收口径是否有效（不能太短或太模糊）
            for i, criterion in enumerate(l4.acceptance_criteria):
                if len(criterion) < 5:
                    issues.append(
                        ValidatorIssue(
                            rule="testability",
                            severity="warning",
                            message=f"验收口径 [{i}] 过短，可能不够具体",
                            field="acceptance_criteria",
                        )
                    )
                # 检查是否包含模糊词
                if self._fuzzy_pattern.search(criterion):
                    issues.append(
                        ValidatorIssue(
                            rule="testability",
                            severity="error",
                            message=f"验收口径 [{i}] 包含模糊词，不满足可测试性",
                            field="acceptance_criteria",
                        )
                    )

        return issues

    def _check_implementability(self, l4: L4Requirement) -> List[ValidatorIssue]:
        """检查可实现性：禁止使用模糊词"""
        issues = []
        text = l4.shall_statement

        matches = self._fuzzy_pattern.findall(text)
        if matches:
            issues.append(
                ValidatorIssue(
                    rule="implementability",
                    severity="error",
                    message=f"需求包含模糊词 [{', '.join(set(matches))}]，不满足可实现性",
                    field="shall_statement",
                )
            )

        # 检查是否有空的 shall_statement
        if not text or len(text.strip()) < 10:
            issues.append(
                ValidatorIssue(
                    rule="implementability",
                    severity="error",
                    message="需求正文为空或过短",
                    field="shall_statement",
                )
            )

        return issues

    def _check_completeness(self, l4: L4Requirement) -> List[ValidatorIssue]:
        """检查要素完整性"""
        issues = []
        text = l4.shall_statement.lower()

        # 检查接口要素
        if any(kw in text for kw in INTERFACE_KEYWORDS) and not l4.interfaces:
            issues.append(
                ValidatorIssue(
                    rule="completeness_interface",
                    severity="error",
                    message="需求涉及接口相关内容，但 interfaces 为空",
                    field="interfaces",
                )
            )

        # 检查数据要素
        if any(kw in text for kw in DATA_KEYWORDS) and not l4.data_contracts:
            issues.append(
                ValidatorIssue(
                    rule="completeness_data",
                    severity="error",
                    message="需求涉及数据相关内容，但 data_contracts 为空",
                    field="data_contracts",
                )
            )

        # 检查错误处理要素
        if any(kw in text for kw in ERROR_KEYWORDS) and not l4.error_handling:
            issues.append(
                ValidatorIssue(
                    rule="completeness_error",
                    severity="error",
                    message="需求涉及错误处理相关内容，但 error_handling 为空",
                    field="error_handling",
                )
            )

        # 检查 NFR 要素
        if any(kw in text for kw in NFR_KEYWORDS) and not l4.nfr:
            issues.append(
                ValidatorIssue(
                    rule="completeness_nfr",
                    severity="error",
                    message="需求涉及非功能性需求相关内容，但 nfr 为空",
                    field="nfr",
                )
            )

        return issues

    def _check_no_fabrication(
        self, l4: L4Requirement, confidence_threshold: float
    ) -> List[ValidatorIssue]:
        """检查禁止编造：信息不足必须有 open_questions"""
        issues = []

        # 如果置信度低但没有 open_questions
        if l4.confidence < confidence_threshold and not l4.open_questions:
            issues.append(
                ValidatorIssue(
                    rule="no_fabrication",
                    severity="error",
                    message=f"置信度较低 ({l4.confidence:.2f}) 但没有 open_questions",
                    field="open_questions",
                )
            )

        return issues

    def _fingerprint(self, l4: L4Requirement) -> str:
        text = (l4.shall_statement or "").lower()
        return re.sub(r"[\W_]+", "", text)

    def _check_evidence_reference(
        self,
        l4: L4Requirement,
        allowed_evidence_ids: Optional[Set[str]] = None,
    ) -> List[ValidatorIssue]:
        """检查证据引用：尽量引用 evidence_ids"""
        issues = []

        if not l4.evidence_ids or len(l4.evidence_ids) == 0:
            issues.append(
                ValidatorIssue(
                    rule="evidence_reference",
                    severity="warning",
                    message="未引用任何 KB 证据 (evidence_ids 为空)，属于推导性生成",
                    field="evidence_ids",
                )
            )
            return issues

        if allowed_evidence_ids is not None:
            invalid_ids = [
                evidence_id
                for evidence_id in l4.evidence_ids
                if evidence_id not in allowed_evidence_ids
            ]
            if invalid_ids:
                issues.append(
                    ValidatorIssue(
                        rule="evidence_reference",
                        severity="warning",
                        message=f"evidence_ids 未在本次检索范围内: {', '.join(invalid_ids)}",
                        field="evidence_ids",
                    )
                )
            return issues

        try:
            kb_service = self._get_kb_service()
            missing_ids = [
                evidence_id
                for evidence_id in l4.evidence_ids
                if not kb_service.evidence_exists(evidence_id)
            ]
            if missing_ids:
                issues.append(
                    ValidatorIssue(
                        rule="evidence_reference",
                        severity="warning",
                        message=f"evidence_ids 未在 KB 中找到: {', '.join(missing_ids)}",
                        field="evidence_ids",
                    )
                )
        except Exception as e:
            issues.append(
                ValidatorIssue(
                    rule="evidence_reference",
                    severity="warning",
                    message=f"证据一致性校验异常: {str(e)}",
                    field="evidence_ids",
                )
            )

        return issues

    def validate_single(
        self,
        l4: L4Requirement,
        allowed_evidence_ids: Optional[Set[str]] = None,
        confidence_threshold: Optional[float] = None,
    ) -> ValidatorStatus:
        """校验单条 L4"""
        all_issues: List[ValidatorIssue] = []
        threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else LOW_CONFIDENCE_THRESHOLD
        )

        # 执行所有校验规则
        all_issues.extend(self._check_atomicity(l4))
        all_issues.extend(self._check_shall_format(l4))
        all_issues.extend(self._check_testability(l4))
        all_issues.extend(self._check_implementability(l4))
        all_issues.extend(self._check_completeness(l4))
        all_issues.extend(self._check_no_fabrication(l4, threshold))
        all_issues.extend(self._check_evidence_reference(l4, allowed_evidence_ids))

        # 判断是否通过（没有 error 级别的问题）
        has_error = any(issue.severity == "error" for issue in all_issues)

        return ValidatorStatus(
            passed=not has_error,
            issues=all_issues,
        )

    def validate_batch(
        self,
        l4_requirements: List[L4Requirement],
        expected_top_ids: Optional[List[str]] = None,
        open_questions_by_top_id: Optional[Dict[str, List[str]]] = None,
        allowed_evidence_ids: Optional[List[str]] = None,
        confidence_threshold: Optional[float] = None,
    ) -> ValidateL4Response:
        """批量校验 L4"""
        per_item_issues: Dict[str, List[ValidatorIssue]] = {}
        status_map: Dict[str, ValidatorStatus] = {}
        allowed_set = (
            set(allowed_evidence_ids) if allowed_evidence_ids is not None else None
        )

        for l4 in l4_requirements:
            status = self.validate_single(
                l4,
                allowed_evidence_ids=allowed_set,
                confidence_threshold=confidence_threshold,
            )

            # 更新 L4 的校验状态
            l4.validator_status = status

            per_item_issues[l4.l4_id] = status.issues
            status_map[l4.l4_id] = status

        # 去重指纹
        fingerprint_map: Dict[str, List[L4Requirement]] = {}
        for l4 in l4_requirements:
            fingerprint = self._fingerprint(l4)
            if not fingerprint:
                continue
            fingerprint_map.setdefault(fingerprint, []).append(l4)

        for fingerprint, items in fingerprint_map.items():
            if len(items) <= 1:
                continue
            duplicate_ids = [item.l4_id for item in items]
            for item in items:
                issue = ValidatorIssue(
                    rule="deduplication",
                    severity="error",
                    message=f"与其他 L4 重复 ({', '.join(duplicate_ids)})",
                    field="shall_statement",
                )
                status = status_map[item.l4_id]
                status.issues.append(issue)
                status.passed = False
                item.validator_status = status
                per_item_issues[item.l4_id] = status.issues

        pass_count = sum(1 for status in status_map.values() if status.passed)
        fail_count = len(status_map) - pass_count
        open_question_count = sum(1 for l4 in l4_requirements if l4.open_questions)

        coverage = CoverageSummary(
            total_count=len(l4_requirements),
            pass_count=pass_count,
            fail_count=fail_count,
            open_question_count=open_question_count,
        )

        top_req_ids = set(expected_top_ids or [])
        top_req_ids.update(
            {l4.source_top_id for l4 in l4_requirements if l4.source_top_id}
        )
        if open_questions_by_top_id:
            top_req_ids.update(open_questions_by_top_id.keys())

        top_req_pass = 0
        top_req_open_question = 0
        top_req_fail = 0

        for top_id in top_req_ids:
            related = [l4 for l4 in l4_requirements if l4.source_top_id == top_id]
            has_pass = any(l4.validator_status.passed for l4 in related)
            has_open_questions = any(l4.open_questions for l4 in related)
            if open_questions_by_top_id and open_questions_by_top_id.get(top_id):
                has_open_questions = True

            if has_pass:
                top_req_pass += 1
            elif has_open_questions:
                top_req_open_question += 1
            else:
                top_req_fail += 1

        coverage.top_requirement_total = len(top_req_ids)
        coverage.top_requirement_passed = top_req_pass
        coverage.top_requirement_open_question = top_req_open_question
        coverage.top_requirement_failed = top_req_fail

        global_pass = top_req_fail == 0

        return ValidateL4Response(
            per_item_issues=per_item_issues,
            coverage_summary=coverage,
            global_pass=global_pass,
        )


# ========================
# 全局单例
# ========================
_validator_service: Optional[L4ValidatorService] = None


def get_l4_validator_service() -> L4ValidatorService:
    """获取 L4 校验服务单例"""
    global _validator_service
    if _validator_service is None:
        _validator_service = L4ValidatorService()
    return _validator_service
