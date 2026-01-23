from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from schemas.trace_output import (
    BatchRelationRecord,
    BatchStatistics,
    BatchTraceRelationResponse,
    TraceLink,
    TraceNetwork,
    TraceNode,
    TraceRelationResponse,
)


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


def _extract_json_like_ai_tracer(text: str) -> Optional[Dict[str, Any]]:
    """
    与 ai-requirement-tracer 对齐的兜底策略：
    先用正则提取第一个 {...} 段，再 json.loads。
    """
    if not text:
        return None
    s = text.strip()
    s = s.replace("```json", "").replace("```JSON", "").replace("```", "").strip()
    m = re.search(r"\{.*?\}", s, re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _safe_float(x: Any, default: float = 0.5) -> float:
    try:
        v = float(x)
    except Exception:
        v = default
    return max(0.0, min(1.0, v))


def _build_pair_network(
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


class TraceabilityService:
    """
    将 ai-requirement-tracer 的“单对调用 + 批量逐对循环”思想迁入本项目：
    - /relation：单对判断（模型输出 JSON -> 解析 -> network/summary）
    - /batch-relation：逐对调用单对逻辑，保证覆盖所有组合（避免一次性让模型输出大 JSON 丢组合）
    """

    def __init__(self, model_engine):
        self.model_engine = model_engine

    def analyze_relation(
        self,
        high_level_requirement: str,
        low_level_requirement: str,
        max_new_tokens: int = 800,
    ) -> TraceRelationResponse:
        # 对齐 ai-requirement-tracer 的提示词风格（更容易让模型输出 JSON）
        prompt = f"""请判断以下高层需求和底层需求之间是否存在直接的追溯关系。请从以下几个方面进行分析：

高层需求：{high_level_requirement}

底层需求：{low_level_requirement}

请按照以下格式返回JSON分析结果（必须是有效JSON）：
{{
  "has_relation": true/false,
  "relation_type": "implementation/support/dependency/decomposition/general/unknown",
  "confidence": 0.0-1.0,
  "analysis_details": "详细分析说明为什么有/没有关系",
  "keywords": ["关键词1", "关键词2"],
  "summary": "一句话总结关系判断结果",
  "suggestions": ["建议1", "建议2"]
}}

分析要求：
1. 仔细分析两个需求的内容和语义
2. 判断是否存在实现、支持、依赖或分解关系
3. 给出置信度评分
4. 提取关键技术术语
5. 严格输出JSON格式，不要添加其他文字
"""

        try:
            raw = self.model_engine.generate(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT_TRACEABILITY,
                max_new_tokens=max_new_tokens,
                temperature=0.1,
                top_p=0.8,
                do_sample=True,
                min_new_tokens=16,
            )
        except TypeError:
            raw = self.model_engine.generate(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT_TRACEABILITY,
                max_new_tokens=max_new_tokens,
            )

        parsed = _extract_first_json_object(raw) or _extract_json_like_ai_tracer(raw)
        if not parsed:
            network = _build_pair_network(high_level_requirement, low_level_requirement, False, "unknown", 0.5)
            return TraceRelationResponse(
                high_level_requirement=high_level_requirement,
                low_level_requirement=low_level_requirement,
                has_relation=False,
                relation_type="unknown",
                confidence=0.5,
                summary="未检测到直接的追溯关系",
                analysis_details=(raw or "")[:800],
                keywords=[],
                suggestions=["建议检查需求描述的完整性", "考虑重新表述需求后重试"],
                trace_network=network,
                raw_response=raw,
                extra=None,
            )

        has_relation = bool(parsed.get("has_relation", False))
        relation_type = str(parsed.get("relation_type", "unknown") or "unknown").replace("/", "_").strip()
        # 兼容 ai-tracer 风格 relation_type="implementation/support/..."，只取第一段
        if "/" in str(parsed.get("relation_type", "")):
            relation_type = str(parsed.get("relation_type", "")).split("/", 1)[0].strip() or "unknown"
        relation_type = relation_type if relation_type in _RELATION_LABELS else ("general" if has_relation else "unknown")
        confidence_f = _safe_float(parsed.get("confidence", 0.5), default=0.5)

        # ai-requirement-tracer 风格：如果没给 summary，则用关系类型 + 置信度生成
        if has_relation:
            summary = f"检测到{_RELATION_LABELS.get(relation_type, '追溯关系')}，置信度: {confidence_f:.1%}"
        else:
            summary = "未检测到直接的追溯关系"
        summary = str(parsed.get("summary") or summary)

        network = _build_pair_network(high_level_requirement, low_level_requirement, has_relation, relation_type, confidence_f)

        known = {"has_relation", "relation_type", "confidence", "analysis_details", "keywords", "summary", "suggestions"}
        extra = {k: v for k, v in parsed.items() if k not in known} or None

        return TraceRelationResponse(
            high_level_requirement=high_level_requirement,
            low_level_requirement=low_level_requirement,
            has_relation=has_relation,
            relation_type=relation_type,
            confidence=confidence_f,
            summary=summary,
            analysis_details=str(parsed.get("analysis_details", "")),
            keywords=list(parsed.get("keywords", []) or []),
            suggestions=list(parsed.get("suggestions", []) or []),
            trace_network=network,
            raw_response=raw,
            extra=extra,
        )

    def _analyze_with_retry(
        self,
        high: str,
        low: str,
        high_idx: int,
        low_idx: int,
        max_new_tokens: int,
        max_retries: int = 3,
    ) -> TraceRelationResponse:
        """
        带重试机制的单对追溯分析
        - 最多重试 max_retries 次
        - 使用指数退避策略
        - 超时/网络错误才重试，其他错误直接抛出
        """
        import time
        import requests

        last_error = None
        # 指数退避：2s, 4s, 8s
        for attempt in range(max_retries):
            try:
                return self.analyze_relation(high, low, max_new_tokens=max_new_tokens)
            except (
                requests.exceptions.Timeout,
                requests.exceptions.ReadTimeout,
                requests.exceptions.ConnectionError,
                TimeoutError,
            ) as e:
                last_error = e
                wait_time = 2 ** (attempt + 1)  # 2, 4, 8 秒
                print(f"[重试 {attempt + 1}/{max_retries}] 组合 (high[{high_idx}], low[{low_idx}]) 超时，等待 {wait_time}s 后重试...")
                time.sleep(wait_time)
            except Exception as e:
                # 非超时错误（如解析错误），尝试一次重试
                if attempt == 0:
                    last_error = e
                    print(f"[重试 1/{max_retries}] 组合 (high[{high_idx}], low[{low_idx}]) 失败: {e}，尝试重试...")
                    time.sleep(2)
                else:
                    raise e

        # 所有重试都失败
        raise last_error or Exception("未知错误")

    def batch_analyze(
        self,
        high_level_requirements: List[str],
        low_level_requirements: List[str],
        max_new_tokens: int = 800,  # 降低默认值，减少推理时间
    ) -> BatchTraceRelationResponse:
        """
        批量追溯分析（带重试和优化）
        
        算法改进：
        1. 重试机制：超时/网络错误自动重试最多3次
        2. 指数退避：重试间隔逐次增加（2s, 4s, 8s）
        3. 降低 max_new_tokens：从 1600 降到 800，减少推理时间
        4. 进度打印：输出当前处理进度
        5. 错误隔离：单对失败不影响其他组合
        """
        highs = [str(s).strip() for s in high_level_requirements if str(s).strip()]
        lows = [str(s).strip() for s in low_level_requirements if str(s).strip()]

        nodes: List[TraceNode] = []
        links: List[TraceLink] = []

        high_node_ids: Dict[int, str] = {}
        low_node_ids: Dict[int, str] = {}

        for i, r in enumerate(highs):
            nid = f"high_{i}"
            high_node_ids[i] = nid
            nodes.append(
                TraceNode(
                    id=nid,
                    name=f"顶层需求{i+1}",
                    text=(r[:100] + "...") if len(r) > 100 else r,
                    level=4,
                    type="high_level",
                )
            )
        for j, r in enumerate(lows):
            nid = f"low_{j}"
            low_node_ids[j] = nid
            nodes.append(
                TraceNode(
                    id=nid,
                    name=f"底层需求{j+1}",
                    text=(r[:100] + "...") if len(r) > 100 else r,
                    level=2,
                    type="low_level",
                )
            )

        relations: List[BatchRelationRecord] = []
        relation_type_count: Dict[str, int] = {}

        total_combinations = len(highs) * len(lows)
        completed = 0
        failed_count = 0

        print(f"[批量追溯] 开始分析 {len(highs)} 个顶层需求 × {len(lows)} 个底层需求 = {total_combinations} 个组合")

        for i, high in enumerate(highs):
            for j, low in enumerate(lows):
                completed += 1
                single = None
                try:
                    # 使用带重试的分析方法
                    single = self._analyze_with_retry(
                        high, low, i, j,
                        max_new_tokens=max_new_tokens,
                        max_retries=3
                    )
                    rec = BatchRelationRecord(
                        high_level_index=i,
                        low_level_index=j,
                        high_level_requirement=high,
                        low_level_requirement=low,
                        has_relation=single.has_relation,
                        relation_type=single.relation_type,
                        confidence=single.confidence,
                        analysis_details=single.analysis_details,
                        summary=single.summary,
                        keywords=single.keywords,
                    )
                    relations.append(rec)
                    
                    # 输出进度
                    if completed % 5 == 0 or completed == total_combinations:
                        print(f"[批量追溯] 进度: {completed}/{total_combinations} ({100*completed//total_combinations}%)")
                        
                except Exception as e:
                    # 所有重试都失败后，记录错误但继续处理其他组合
                    failed_count += 1
                    print(f"[批量追溯] 组合 (high[{i}], low[{j}]) 最终失败: {e}")
                    rec = BatchRelationRecord(
                        high_level_index=i,
                        low_level_index=j,
                        high_level_requirement=high,
                        low_level_requirement=low,
                        has_relation=False,
                        relation_type="unknown",
                        confidence=0.0,
                        analysis_details=f"分析失败(已重试): {str(e)}",
                        summary="分析失败",
                        keywords=[],
                    )
                    relations.append(rec)

                if single and single.has_relation:
                    rel_type = (single.relation_type or "unknown").strip() or "unknown"
                    relation_type_count[rel_type] = relation_type_count.get(rel_type, 0) + 1
                    links.append(
                        TraceLink(
                            source=high_node_ids[i],
                            target=low_node_ids[j],
                            type=rel_type,
                            label=_RELATION_LABELS.get(rel_type, "追溯关系"),
                            confidence=single.confidence,
                        )
                    )

        print(f"[批量追溯] 完成! 成功: {total_combinations - failed_count}/{total_combinations}, 失败: {failed_count}")

        expected = len(highs) * len(lows)
        relations_found = len([r for r in relations if r.has_relation])
        stats = BatchStatistics(
            total_combinations=expected,
            relations_found=relations_found,
            relation_rate=(relations_found / expected) if expected else 0.0,
        )

        summary = (
            f"批量分析了 {len(highs)} 个顶层需求和 {len(lows)} 个底层需求，共 {expected} 个组合，发现 {relations_found} 个追溯关系"
        )

        extra = {"relation_types_count": relation_type_count} if relation_type_count else None

        return BatchTraceRelationResponse(
            summary=summary,
            statistics=stats,
            high_level_requirements=highs,
            low_level_requirements=lows,
            relations=relations,
            trace_network=TraceNetwork(nodes=nodes, links=links),
            relation_types_count=relation_type_count if relation_type_count else None,
            raw_response=None,
            extra=extra,
        )


