"""
KB Service - 静态数据定义

包含:
1. SPEC_ENTRIES: 规范与模板库 (硬约束条目)
2. NFR_ENTRIES: NFR/质量条目库 (非功能需求模板)
"""

from typing import Any, Dict, List


# ========================
# Spec/Template 条目定义 (来自 mission.txt 的硬约束)
# ========================
SPEC_ENTRIES: List[Dict[str, Any]] = [
    {
        "id": "spec-001",
        "text": "L4 需求必须使用 shall 句式表述,格式为:[主体] shall [动作] [对象] [约束条件]",
        "category": "format",
        "source": "mission.txt",
    },
    {
        "id": "spec-002",
        "text": "禁止编造:如果上下文信息不足,必须输出 open_questions 而不是凭空生成内容",
        "category": "integrity",
        "source": "mission.txt",
    },
    {
        "id": "spec-003",
        "text": "字段完备性:每条 L4 必须包含 shall_statement 和 acceptance_criteria",
        "category": "completeness",
        "source": "mission.txt",
    },
    {
        "id": "spec-004",
        "text": "原子性:一条 L4 只表达一个可实现的功能点,不能包含多个独立功能",
        "category": "atomicity",
        "source": "mission.txt",
    },
    {
        "id": "spec-005",
        "text": "可测试性:每条 L4 必须包含可测量或可观测的验收口径",
        "category": "testability",
        "source": "mission.txt",
    },
    {
        "id": "spec-006",
        "text": "可实现性:禁止使用模糊词如'尽量'、'适当'、'友好'、'合理'等",
        "category": "implementability",
        "source": "mission.txt",
    },
    {
        "id": "spec-007",
        "text": "受约束输出:模型只能输出结构化 JSON,不允许段落式自然语言",
        "category": "format",
        "source": "mission.txt",
    },
    {
        "id": "spec-008",
        "text": "去重指纹:相同语义的 L4 需求应当去重,避免重复生成",
        "category": "deduplication",
        "source": "mission.txt",
    },
    {
        "id": "spec-009",
        "text": "要素完整-接口:当需求涉及'接口/对接/调用/返回/请求/响应'时,interfaces 必填",
        "category": "completeness",
        "source": "mission.txt",
    },
    {
        "id": "spec-010",
        "text": "要素完整-数据:当需求涉及'字段/格式/存储/数据库/导出/导入'时,data_contracts 必填",
        "category": "completeness",
        "source": "mission.txt",
    },
    {
        "id": "spec-011",
        "text": "要素完整-错误处理:当需求涉及'失败/异常/超时/重试/降级'时,error_handling 必填",
        "category": "completeness",
        "source": "mission.txt",
    },
    {
        "id": "spec-012",
        "text": "要素完整-NFR:当需求涉及'性能/延迟/并发/吞吐/安全/审计/日志'时,nfr 必填",
        "category": "completeness",
        "source": "mission.txt",
    },
]


# ========================
# NFR 模板条目定义
# ========================
NFR_ENTRIES: List[Dict[str, Any]] = [
    # 性能类
    {
        "id": "nfr-perf-001",
        "text": "系统应在 [X] 并发用户下,保证 API 响应时间 P99 不超过 [Y] 毫秒",
        "nfr_type": "performance",
        "category": "response_time",
    },
    {
        "id": "nfr-perf-002",
        "text": "系统吞吐量应支持每秒处理不少于 [X] 个请求 (TPS)",
        "nfr_type": "performance",
        "category": "throughput",
    },
    {
        "id": "nfr-perf-003",
        "text": "单个接口的资源消耗上限:CPU 不超过 [X]%,内存不超过 [Y] MB",
        "nfr_type": "performance",
        "category": "resource",
    },
    # 安全类
    {
        "id": "nfr-sec-001",
        "text": "所有 API 接口必须进行身份认证,未认证请求返回 401",
        "nfr_type": "security",
        "category": "authentication",
    },
    {
        "id": "nfr-sec-002",
        "text": "敏感操作必须进行权限校验,无权限请求返回 403",
        "nfr_type": "security",
        "category": "authorization",
    },
    {
        "id": "nfr-sec-003",
        "text": "所有敏感数据在日志中必须脱敏处理(手机号、身份证、密码等)",
        "nfr_type": "security",
        "category": "data_masking",
    },
    {
        "id": "nfr-sec-004",
        "text": "关键操作必须记录审计日志,包含操作人、时间、操作类型、结果",
        "nfr_type": "security",
        "category": "audit",
    },
    # 可靠性类
    {
        "id": "nfr-rel-001",
        "text": "外部服务调用失败时,应进行最多 [X] 次重试,重试间隔采用指数退避",
        "nfr_type": "reliability",
        "category": "retry",
    },
    {
        "id": "nfr-rel-002",
        "text": "写操作接口必须保证幂等性,重复请求不产生副作用",
        "nfr_type": "reliability",
        "category": "idempotency",
    },
    {
        "id": "nfr-rel-003",
        "text": "当依赖服务不可用时,系统应提供降级策略,返回缓存数据或默认值",
        "nfr_type": "reliability",
        "category": "degradation",
    },
    {
        "id": "nfr-rel-004",
        "text": "所有外部调用必须设置超时,超时时间不超过 [X] 秒",
        "nfr_type": "reliability",
        "category": "timeout",
    },
    # 可观测性类
    {
        "id": "nfr-obs-001",
        "text": "所有日志必须包含 trace_id 字段,用于请求链路追踪",
        "nfr_type": "observability",
        "category": "tracing",
    },
    {
        "id": "nfr-obs-002",
        "text": "关键业务指标必须暴露 Prometheus 指标,包含 QPS、延迟、错误率",
        "nfr_type": "observability",
        "category": "metrics",
    },
    {
        "id": "nfr-obs-003",
        "text": "当错误率超过 [X]% 或延迟超过 [Y] 毫秒时,必须触发告警",
        "nfr_type": "observability",
        "category": "alerting",
    },
    {
        "id": "nfr-obs-004",
        "text": "日志必须结构化输出 JSON 格式,包含 timestamp、level、message、context",
        "nfr_type": "observability",
        "category": "logging",
    },
]
