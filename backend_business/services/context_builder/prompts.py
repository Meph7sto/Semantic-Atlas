from typing import Dict, List

from .models import Span

SYSTEM_PROMPT_LINK = """你是一个语义关系分析专家。你需要分析给定的对话片段之间的语义关联关系。

## 关系类型（只能选择以下5种）:
- continuation: 延续 - 后续内容是对前文的自然延续
- elaboration: 补充/细化 - 对之前观点的详细展开或补充说明
- dependency: 依赖 - 后文依赖前文的信息才能理解（有向）
- same_topic: 同主题弱连接 - 讨论相同主题但无强逻辑关联
- conflict: 冲突 - 两个片段之间存在矛盾或冲突

## 输出格式要求:
你必须输出一个JSON对象，包含两个数组：
1. "links": 边列表，每条边包含:
   - "source": 源片段短引用（如"S1"）
   - "target": 目标片段短引用（如"S2"）
   - "type": 关系类型（只能是上述5种之一）
   - "strength": 关联强度（0.0-1.0之间的小数）
   - "note": 简短理由（可选）

2. "noise": 噪音片段列表（无意义的片段引用，如["S3"]），可为空数组

## 重要约束:
- source和target必须使用给定的短引用（S1, S2, ...），不能使用其他标识
- 不要输出自环（source等于target）
- strength必须在0.0到1.0之间
- 只输出JSON，不要有其他文字

## 示例输出:
```json
{
  "links": [
    {"source": "S1", "target": "S2", "type": "continuation", "strength": 0.85, "note": "自然延续讨论"},
    {"source": "S1", "target": "S3", "type": "elaboration", "strength": 0.70, "note": "S3补充说明S1"}
  ],
  "noise": ["S4"]
}
```
"""


def build_window_prompt(spans: List[Span], ref_map: Dict[str, str]) -> str:
    lines = ["请分析以下对话片段之间的语义关联关系：\n"]
    for span in spans:
        ref = ref_map[span.span_id]
        time_info = (
            f"{span.start_ms}-{span.end_ms}" if span.start_ms is not None else "?"
        )
        speaker = span.speaker or "unknown"
        lines.append(f"[{ref}] [{time_info}] [{speaker}]: {span.text}")
    lines.append("\n请输出JSON格式的分析结果。")
    return "\n".join(lines)
