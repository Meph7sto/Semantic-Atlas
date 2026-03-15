import json
from typing import List


def extract_stream_content(data: str, buffer: List[str]) -> None:
    """
    尝试从 SSE 数据块中提取文本内容并写入 buffer。
    如果解析失败，则直接附加原始字符串，保证不丢失信息。
    """
    try:
        payload = json.loads(data)
        choices = payload.get("choices") or []
        if not choices:
            return
        delta = choices[0].get("delta") or choices[0].get("message") or {}
        content_piece = delta.get("content") or delta.get("text") or ""
        if content_piece:
            buffer.append(content_piece)
    except json.JSONDecodeError:
        # 兼容特殊行：无法解析的块直接拼接
        buffer.append(data)
