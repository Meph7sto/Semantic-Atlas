"""
Parameter normalization and result initialization for requirements extraction
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from backend_business.services.ego_bundle_generator import EgoBundleGenerator

from .utils import normalize_keywords, normalize_max_r, safe_int


@dataclass
class ExtractionParams:
    """标准化后的抽取参数"""

    max_r: int
    adaptive_retry_r2: bool
    effective_max_spans: int
    effective_token_limit: Optional[int]
    effective_top_m_2hop: int
    effective_max_concurrent: int
    effective_keywords: Optional[List[str]]
    enable_parallel: bool
    bundle_generator: EgoBundleGenerator


def normalize_extraction_params(
    r: int = 2,
    adaptive_retry_r2: Optional[bool] = None,
    max_spans_per_bundle: Optional[int] = None,
    token_limit: Optional[int] = None,
    top_m_2hop: Optional[int] = None,
    keywords: Optional[Sequence[str]] = None,
    enable_parallel: bool = False,
    max_concurrent: int = 5,
) -> ExtractionParams:
    """
    将原始参数标准化为 ExtractionParams
    """
    max_r = normalize_max_r(r)
    if adaptive_retry_r2 is None:
        adaptive_retry_r2 = True

    effective_max_spans = safe_int(max_spans_per_bundle, 12)
    effective_top_m_2hop = safe_int(top_m_2hop, 5)
    effective_max_concurrent = max(1, min(10, safe_int(max_concurrent, 5)))
    enable_parallel = bool(enable_parallel)

    try:
        token_limit_int = (
            None if token_limit in (None, "", 0, "0") else int(token_limit)
        )  # type: ignore[arg-type]
    except (TypeError, ValueError):
        token_limit_int = 1500

    effective_keywords = normalize_keywords(keywords)

    bundle_generator = EgoBundleGenerator(
        max_spans_per_bundle=effective_max_spans,
        token_limit=token_limit_int,
    )

    return ExtractionParams(
        max_r=max_r,
        adaptive_retry_r2=adaptive_retry_r2,
        effective_max_spans=effective_max_spans,
        effective_token_limit=token_limit_int,
        effective_top_m_2hop=effective_top_m_2hop,
        effective_max_concurrent=effective_max_concurrent,
        effective_keywords=effective_keywords,
        enable_parallel=enable_parallel,
        bundle_generator=bundle_generator,
    )


def build_initial_result(
    session_id: str,
    bundle_strategy: str,
    anchor_strategy: str,
    params: ExtractionParams,
    use_toolcall: bool,
    history_aware: bool,
    **extra: Any,
) -> Dict[str, Any]:
    """
    构建初始统计结果字典
    """
    result: Dict[str, Any] = {
        "session_id": session_id,
        "bundle_strategy": bundle_strategy,
        "anchor_strategy": anchor_strategy,
        "r": params.max_r,
        "use_toolcall": use_toolcall,
        "adaptive_retry_r2": params.adaptive_retry_r2,
        "max_spans_per_bundle": params.effective_max_spans,
        "token_limit": params.effective_token_limit,
        "top_m_2hop": params.effective_top_m_2hop,
        "keywords": params.effective_keywords,
        "history_aware": history_aware,
        "total_spans": 0,
        "total_anchors": 0,
        "bundles_processed": 0,
        "total_inserted": 0,
        "total_duplicates": 0,
        "total_updated": 0,
        "update_log": [],
        "errors": [],
    }
    result.update(extra)
    return result
