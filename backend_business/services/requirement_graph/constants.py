import os
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _env_path(name: str, default: Path) -> Path:
    raw_value = os.environ.get(name)
    if not raw_value:
        return default.resolve()
    candidate = Path(raw_value)
    if not candidate.is_absolute():
        candidate = (_PROJECT_ROOT / candidate).resolve()
    return candidate


_REQ_REQ_INFERRED_TYPES = {
    "DEPENDS_ON",
    "CONFLICTS_WITH",
    "INCLUDES",
    "EXTENDS",
    "IMPACTS",
    "VALIDATES_WITH",
}
_REQ_REQ_EXTRA_RELATION_TYPES = {
    "INCLUDES",
    "EXTENDS",
    "IMPACTS",
    "VALIDATES_WITH",
}
_RULE_RELATION_TYPES = {
    "DEPENDS_ON",
    "CONFLICTS_WITH",
    "VALIDATES_WITH",
    "SIMILAR_TO",
}
_STAKEHOLDER_REQ_INFERRED_TYPES = {
    "RAISES",
    "OWNS",
    "AFFECTED_BY",
    "APPROVES",
    "BENEFITS_FROM",
    "OPPOSES",
}
_STAKEHOLDER_STAKEHOLDER_INFERRED_TYPES = {
    "INTEREST_CONFLICTS_WITH",
    "COLLABORATES_WITH",
}
_SYMMETRIC_EDGE_TYPES = {
    "COLLABORATES_WITH",
    "INTEREST_CONFLICTS_WITH",
    "CONFLICTS_WITH",
    "SIMILAR_TO",
    "VALIDATES_WITH",
}
_UNDIRECTED_EDGE_TYPES = _SYMMETRIC_EDGE_TYPES
_RELATION_PRIORITY = {
    "REFINES": 6,
    "DEPENDS_ON": 5,
    "CONFLICTS_WITH": 5,
    "INCLUDES": 4,
    "EXTENDS": 4,
    "IMPACTS": 4,
    "VALIDATES_WITH": 3,
    "SIMILAR_TO": 1,
}
_SOURCE_KIND_PRIORITY = {
    "structural": 6,
    "trace_analysis": 5,
    "conflict_analysis": 5,
    "classification_analysis": 5,
    "local_vector": 4,
    "llm": 3,
    "rule_extra": 2,
    "rule": 1,
}
_LEVEL_ORDER = ["L1", "L2", "L3", "L4", "UNKNOWN_LEVEL"]
_DEPENDENCY_MARKERS = (
    "依赖",
    "前置",
    "调用",
    "使用",
    "基于",
    "接入",
    "读取",
    "写入",
    "消费",
    "订阅",
    "发布",
    "输入",
    "输出",
    "接口",
    "api",
    "module",
)
_VALIDATION_MARKERS = (
    "验收",
    "验证",
    "测试",
    "校验",
    "检查",
    "断言",
    "用例",
    "回归",
    "审计",
    "成功标准",
)
_CONFLICT_MARKERS = ("冲突", "互斥", "相反", "矛盾", "不能同时", "资源竞争")
_RESOURCE_TERMS = (
    "数据库",
    "缓存",
    "队列",
    "消息",
    "线程",
    "带宽",
    "显存",
    "gpu",
    "cpu",
    "内存",
    "锁",
    "连接池",
)
_GENERIC_TERMS = {
    "系统",
    "需求",
    "功能",
    "模块",
    "接口",
    "服务",
    "页面",
    "用户",
    "数据",
    "支持",
    "实现",
    "提供",
    "相关",
    "处理",
    "校验",
    "测试",
    "验证",
    "requirement",
    "service",
    "module",
    "system",
}
_NON_INFORMATIVE_TERMS = _GENERIC_TERMS | {
    "shall",
    "should",
    "must",
    "will",
    "would",
    "could",
    "may",
    "might",
    "need",
    "needs",
    "require",
    "required",
    "requires",
    "allow",
    "allows",
    "ensure",
    "ensures",
    "support",
    "supports",
    "provide",
    "provides",
    "能够",
    "可以",
    "需要",
    "应当",
    "应该",
    "必须",
    "用于",
}
_TRANSIENT_TOOL_ERROR_STATUSES = {408, 409, 425, 429, 500, 502, 503, 504}


def _env_int(name: str, default: int, *, minimum: int = 1, maximum: int = 64) -> int:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


_DEPENDENCY_AUDIT_BATCH_SIZE = _env_int(
    "REQUIREMENT_GRAPH_DEPENDENCY_AUDIT_BATCH_SIZE",
    4,
    maximum=16,
)
_DEPENDENCY_AUDIT_MAX_CONCURRENCY = _env_int(
    "REQUIREMENT_GRAPH_DEPENDENCY_AUDIT_MAX_CONCURRENCY",
    2,
    maximum=8,
)
_DEPENDENCY_AUDIT_CONFIDENCE_THRESHOLD = 0.72
_DEPENDENCY_PER_SOURCE_LIMIT = 4
_MODEL_DATA_DIR = _env_path("MODEL_DATA_DIR", _PROJECT_ROOT / "data" / "model")
_REQUIREMENT_GRAPH_EMBEDDING_DIR = _env_path(
    "REQUIREMENT_GRAPH_EMBEDDING_DIR",
    _MODEL_DATA_DIR / "requirement_graph_embedding",
)
_SEMANTIC_EMBEDDING_MODEL = (
    os.environ.get("REQUIREMENT_GRAPH_EMBEDDING_MODEL")
    or "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
_SEMANTIC_PAIR_MAX_REQUIREMENTS = 256
_SEMANTIC_PAIR_THRESHOLD = 0.62
_SEMANTIC_SIMILARITY_THRESHOLD = 0.74
