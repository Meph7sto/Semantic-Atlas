from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

from core.model_container import model_engine
from schemas.trace_output import (
    BatchRelationRecord,
    BatchStatistics,
    BatchTraceRelationRequest,
    BatchTraceRelationResponse,
    TraceLink,
    TraceNetwork,
    TraceNode,
    TraceRelationRequest,
    TraceRelationResponse,
)

router = APIRouter(prefix="/traceability", tags=["Traceability"])

# ai-requirement-tracer 追溯逻辑迁入：将“批量逐对调用单对分析”的策略封装为 service
from services.traceability_service import TraceabilityService

traceability_service = TraceabilityService(model_engine=model_engine)


_RELATION_LABELS: Dict[str, str] = {
    "implementation": "实现关系",
    "support": "支持关系",
    "dependency": "依赖关系",
    "decomposition": "分解关系",
    "general": "追溯关系",
    "unknown": "未知关系",
}


SYSTEM_PROMPT_TRACEABILITY = """你是一个专业的系统需求工程专家。
你的任务是判断高层需求与底层需求之间是否存在直接追溯关系，并给出结构化结果。
你必须严格输出有效 JSON，不要输出任何额外文字、解释、Markdown 代码块标记或前后缀。
"""


def _extract_first_json_object(text: str) -> Optional[Dict[str, Any]]:
    """
    从模型输出中提取第一个 JSON 对象（通过大括号配对）。
    兼容模型输出在 JSON 外夹杂少量文本的情况。
    """
    if not text:
        return None

    s = text.strip()

    # 快速路径：整体就是 JSON
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    # 去除常见 ```json ``` 包裹
    s = s.replace("```json", "").replace("```JSON", "").replace("```", "").strip()

    start = s.find("{")
    if start < 0:
        return None

    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue

        if ch == '"':
            in_str = True
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = s[start : i + 1]
                try:
                    obj = json.loads(candidate)
                    return obj if isinstance(obj, dict) else None
                except Exception:
                    return None
    return None


def _build_relation_network(
    high_level_req: str,
    low_level_req: str,
    has_relation: bool,
    relation_type: str,
    confidence: Optional[float],
) -> TraceNetwork:
    nodes = [
        TraceNode(
            id="high_level",
            name="顶层需求",
            text=(high_level_req[:100] + "...") if len(high_level_req) > 100 else high_level_req,
            level=4,
            type="high_level",
        ),
        TraceNode(
            id="low_level",
            name="底层需求",
            text=(low_level_req[:100] + "...") if len(low_level_req) > 100 else low_level_req,
            level=2,
            type="low_level",
        ),
    ]

    links: List[TraceLink] = []
    rel_type = (relation_type or "unknown").strip() or "unknown"
    if has_relation:
        links.append(
            TraceLink(
                source="high_level",
                target="low_level",
                type=rel_type,
                label=_RELATION_LABELS.get(rel_type, "追溯关系"),
                confidence=confidence,
            )
        )
    return TraceNetwork(nodes=nodes, links=links)


@router.post("/relation", response_model=TraceRelationResponse)
async def analyze_relation(request: TraceRelationRequest):
    """
    单对需求关系追溯：判断顶层需求与底层需求之间是否存在直接追溯关系。
    """
    if model_engine.model is None:
        raise HTTPException(status_code=503, detail="Model service not initialized or unavailable.")

    try:
        return traceability_service.analyze_relation(
            high_level_requirement=request.high_level_requirement,
            low_level_requirement=request.low_level_requirement,
            max_new_tokens=request.max_new_tokens,
        )
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Model service not initialized or unavailable.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch-relation", response_model=BatchTraceRelationResponse)
async def batch_analyze_relation(request: BatchTraceRelationRequest):
    """
    批量需求关系追溯：分析多对顶层需求与底层需求之间的追溯关系。
    """
    if model_engine.model is None:
        raise HTTPException(status_code=503, detail="Model service not initialized or unavailable.")

    # 清洗空字符串，避免无意义组合
    highs = [str(s).strip() for s in request.high_level_requirements if str(s).strip()]
    lows = [str(s).strip() for s in request.low_level_requirements if str(s).strip()]
    if not highs or not lows:
        raise HTTPException(status_code=400, detail="high_level_requirements 与 low_level_requirements 不能为空。")

    try:
        return traceability_service.batch_analyze(
            high_level_requirements=highs,
            low_level_requirements=lows,
            max_new_tokens=request.max_new_tokens,
        )
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Model service not initialized or unavailable.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


