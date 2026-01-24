from typing import Any, Dict, Optional

RELATION_TYPES = frozenset(
    [
        "continuation",
        "elaboration",
        "dependency",
        "same_topic",
        "conflict",
    ]
)

RELATION_PRIORITY = {
    "conflict": 5,
    "continuation": 4,
    "dependency": 4,
    "elaboration": 2,
    "same_topic": 1,
}

DEFAULT_OPTIONS = {
    "window_size": 8,
    "step_size": 7,
    "tau": 0.60,
    "top_k": 3,
    "max_edges_per_window": 24,
    "token_limit_per_bundle": 4000,
    "mock_llm": False,
    "llm_model": None,
    "enable_parallel_windows": False,
    "max_concurrent_windows": 5,
}


def _resolve_llm_model(options: Dict[str, Any]) -> Optional[str]:
    raw_model = options.get("llm_model")
    if isinstance(raw_model, str) and raw_model.strip():
        return raw_model.strip()
    if options.get("use_thinking_mode"):
        return "deepseek-reasoner"
    return None
