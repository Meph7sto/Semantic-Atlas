
import logging
import json
import os
import re
from dataclasses import dataclass, asdict
from typing import Any, Callable, Dict, List, Optional
from openai import OpenAI
from core.config import settings
from core.engine.remote.deepseek import (
    DEFAULT_DEEPSEEK_MODEL,
    normalize_deepseek_model,
)

logger = logging.getLogger(__name__)

# --- Data Structures ---

@dataclass
class ProcessedChunk:
    cleaned_text: str
    summary: str

@dataclass
class RequirementItem:
    statement: str
    rationale: str
    evidence: str
    confidence: float

@dataclass
class RequirementGroup:
    business: List[RequirementItem]
    stakeholder: List[RequirementItem]
    system: List[RequirementItem]

# --- Helper Functions ---

def smart_chunk(text: str, chunk_size: int, overlap: int) -> List[str]:
    """Split text into overlapping chunks, cutting at sentence boundaries when possible."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    if overlap < 0:
        raise ValueError("overlap must be >= 0")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    punctuation = "。！？!?；;！?.\n"
    chunks: List[str] = []
    pos = 0
    n = len(text)

    while pos < n:
        window_end = min(pos + chunk_size, n)
        window = text[pos:window_end]
        cut = len(window)
        for idx in range(len(window) - 1, max(-1, len(window) - chunk_size - 1), -1):
            if window[idx] in punctuation and idx > int(0.5 * chunk_size):
                cut = idx + 1
                break
        chunk = window[:cut].strip()
        if chunk:
            chunks.append(chunk)
        if window_end >= n:
            break
        next_pos = pos + cut - overlap
        if next_pos <= pos:
            next_pos = pos + 1
        pos = next_pos
    return chunks

def _normalize_openai_base_url(base_url: Optional[str]) -> Optional[str]:
    if not base_url:
        return base_url
    cleaned = base_url.strip().rstrip("/")
    if cleaned.endswith("/chat/completions"):
        cleaned = cleaned[: -len("/chat/completions")]
    if cleaned.endswith("/v1/chat"):
        cleaned = cleaned[: -len("/chat")]
    return cleaned

def _extract_first_json_object(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    s = text.strip()
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
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

def _emit_progress(callback: Optional[Callable[[Dict[str, Any]], None]], payload: Dict[str, Any]) -> None:
    if not callback:
        return
    try:
        callback(payload)
    except Exception:
        logger.debug("Progress callback failed", exc_info=True)

def call_openai_json(
    client: OpenAI,
    messages: List[dict],
    model: str,
    temperature: float,
    thinking_enabled: bool = True,
) -> dict:
    def _run(with_response_format: bool) -> str:
        resolved_model = normalize_deepseek_model(model)
        kwargs = {
            "model": resolved_model,
            "messages": messages,
        }
        if thinking_enabled:
            kwargs["reasoning_effort"] = "high"
            kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
        else:
            kwargs["temperature"] = temperature
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        if with_response_format:
            kwargs["response_format"] = {"type": "json_object"}
        resp = client.chat.completions.create(**kwargs)
        content = resp.choices[0].message.content
        if not content:
            raise RuntimeError("Empty response from model")
        return content

    try:
        content = _run(True)
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            parsed = _extract_first_json_object(content)
            if parsed:
                return parsed
        raise RuntimeError("Model returned non-JSON output")
    except Exception as e:
        logger.warning(f"OpenAI call with response_format failed, retrying: {e}")
        try:
            content = _run(False)
            parsed = _extract_first_json_object(content)
            if parsed:
                return parsed
            raise RuntimeError("Model returned non-JSON output")
        except Exception as e2:
            logger.error(f"OpenAI Call Failed: {e2}")
            raise RuntimeError(f"Model interaction failed: {e2}")

def _compact_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()

def _normalize_key(category: str, statement: str) -> str:
    st = _compact_whitespace(statement)
    st = re.sub(r"[，,。.!！？?；;:：\-—（）()\[\]【】]", "", st)
    return f"{category}:{st}"[:300]

def parse_requirement_item(data: dict) -> Optional[RequirementItem]:
    statement = _compact_whitespace(str(data.get("statement", "")))
    if not statement:
        return None
    rationale = _compact_whitespace(str(data.get("rationale", "")))
    evidence = _compact_whitespace(str(data.get("evidence", "")))
    try:
        confidence = float(data.get("confidence", 0.0))
    except Exception:
        confidence = 0.0
    return RequirementItem(
        statement=statement,
        rationale=rationale,
        evidence=evidence[:50], # Increased slightly from 30
        confidence=confidence,
    )

# --- Prompts ---

def build_clean_prompt(chunk: str, previous_summary: Optional[str]) -> List[dict]:
    system = (
        "你是一位极其严谨的会议速记整理专家。任务是从混乱的文本中还原准确内容。"
        "保持原意，不新增或删除需求。清洗去掉口头语、杂讯，补全缺失成分。"
    )
    user_parts = [
        f"处理以下文本[{chunk}]：",
        "1.剔除语气干扰（呃、啊等）。",
        "2.修正转录错误（同音字修正）。",
        "3.合并破碎句。",
        "4.由不改变原意，不增加非原文信息。",
    ]
    if previous_summary:
        user_parts.append("上一段摘要：" + previous_summary)
    user_parts.append("输出JSON: {\"cleaned_text\": \"...\"}")
    return [{"role": "system", "content": system}, {"role": "user", "content": "\n\n".join(user_parts)}]

def build_polish_prompt(cleaned_chunk: str, previous_summary: Optional[str]) -> List[dict]:
    system = "你是一位资深需求分析师。请将文本转化为专业、清晰的业务书面表达。"
    user_parts = [
        f"润色以下文本[{cleaned_chunk}]：",
        "1.消除模糊代词（它->具体名词）。",
        "2.口语转书面。",
        "3.突出痛点和愿景。",
        "4.保持客观。",
    ]
    if previous_summary:
        user_parts.append("上一段摘要：" + previous_summary)
    user_parts.append("输出JSON: {\"cleaned_text\": \"...\", \"short_summary\": \"...\"}")
    return [{"role": "system", "content": system}, {"role": "user", "content": "\n\n".join(user_parts)}]

def build_extract_prompt(chunk: str, previous_summary: Optional[str]) -> List[dict]:
    system = "你是一个高精确度的需求抽取器。任务是抽取三类需求：业务需求(L1)、利益相关者需求(L2)、系统需求(L3)。"
    user_parts = [
        f"从以下文本提取需求:\n{chunk}",
    ]
    if previous_summary:
        user_parts.append("上下文摘要：" + previous_summary)
    
    user_parts.append(
        "定义：\n"
        "1) L1 业务/使命需求 (business_requirements): 为什么做？商业目标、问题定义、ROI、约束方向。输出 Business Case / 目标指标。\n"
        "2) L2 利益相关者需求 (stakeholder_requirements): 利益相关者“想用它做什么”？场景、痛点、期望 (非技术语言)。\n"
        "3) L3 系统需求 (system_requirements): 系统黑盒应具备的能力与属性。边界、接口、质量指标。\n"
    )
    user_parts.append(
        "规则：\n"
        "- 仅抽取与原文直接相关的需求。\n"
        "- 严禁实现细节 (L4/L5)，如具体函数名、技术栈。\n"
        "- evidence 必须是原文摘录 (<= 50 chars)。\n"
    )
    user_parts.append(
        "输出 JSON 对象，包含 business_requirements, stakeholder_requirements, system_requirements 数组。\n"
        "每个元素包含: statement, rationale, evidence, confidence。"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": "\n\n".join(user_parts)}]

def build_summary_prompt(chunk: str) -> List[dict]:
    return [{"role": "user", "content": f"生成10-40字摘要供上下文理解。输出JSON: {{\"short_summary\": \"...\"}}\n\n{chunk}"}]

# --- Main Service Class ---

class RequirementsAcquisitionService:
    def __init__(self):
        # In a real scenario, use settings.OPENAI_API_KEY. Assuming settings or env var.
        api_key = settings.OPENAI_API_KEY
        base_url = _normalize_openai_base_url(settings.OPENAI_BASE_URL)
        if not api_key:
             logging.warning("API Key not found in settings, attempting fallback to env var.")
             api_key = os.getenv("OPENAI_API_KEY") 
        
        try:
            # Check if key is present to avoid immediate crash if strict validation happens
            if not api_key:
                logger.warning("No OpenAI API KEY found. Service will fail on request.")
                self.client = None
            else:
                self.client = OpenAI(api_key=api_key, base_url=base_url)
        except Exception as e:
            logger.error(f"Failed to init OpenAI client: {e}")
            self.client = None

        self.model = DEFAULT_DEEPSEEK_MODEL
        self.temperature = 0.2
        self.chunk_size = 3600
        self.overlap = 500

    def process(
        self,
        raw_text: str,
        clean_model: str = DEFAULT_DEEPSEEK_MODEL,
        extract_model: str = DEFAULT_DEEPSEEK_MODEL,
        use_thinking_mode: bool = True,
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> RequirementGroup:
        if not self.client:
            raise RuntimeError("OpenAI client not initialized. Check server logs for missing API KEY.")

        # Step 1: Clean & Polish
        chunks = smart_chunk(raw_text, self.chunk_size, self.overlap)
        _emit_progress(on_progress, {"stage": "clean_polish", "current": 0, "total": len(chunks)})
        polished_text_parts = []
        previous_summary = None
        
        # Clean/Polish Phase
        for idx, chunk in enumerate(chunks, start=1):
            # Clean
            clean_msgs = build_clean_prompt(chunk, previous_summary)
            clean_res = call_openai_json(
                self.client,
                clean_msgs,
                clean_model,
                self.temperature,
                thinking_enabled=use_thinking_mode,
            )
            cleaned = clean_res.get("cleaned_text", "")
            
            # Polish
            polish_msgs = build_polish_prompt(cleaned, previous_summary)
            polish_res = call_openai_json(
                self.client,
                polish_msgs,
                clean_model,
                self.temperature,
                thinking_enabled=use_thinking_mode,
            )
            polished = polish_res.get("cleaned_text", "")
            summary = polish_res.get("short_summary", "")
            
            polished_text_parts.append(polished)
            previous_summary = summary
            _emit_progress(on_progress, {"stage": "clean_polish", "current": idx, "total": len(chunks)})
        
        full_polished_text = "\n\n".join(polished_text_parts)
        
        # Step 2: Extract
        extract_chunks = smart_chunk(full_polished_text, self.chunk_size, self.overlap)
        _emit_progress(on_progress, {"stage": "extract", "current": 0, "total": len(extract_chunks)})
        merged_business = {}
        merged_stakeholder = {}
        merged_system = {}
        previous_summary = None

        for idx, chunk in enumerate(extract_chunks, start=1):
            msgs = build_extract_prompt(chunk, previous_summary)
            data = call_openai_json(
                self.client,
                msgs,
                extract_model,
                self.temperature,
                thinking_enabled=use_thinking_mode,
            )
            
            for key, target_dict in [
                ("business_requirements", merged_business),
                ("stakeholder_requirements", merged_stakeholder),
                ("system_requirements", merged_system)
            ]:
                items = data.get(key, [])
                if isinstance(items, list):
                    for it in items:
                        if isinstance(it, dict):
                            parsed = parse_requirement_item(it)
                            if parsed:
                                k = _normalize_key(key, parsed.statement)
                                existing = target_dict.get(k)
                                if not existing or parsed.confidence > existing.confidence:
                                    target_dict[k] = parsed
            
            # Context summary for next extraction chunk
            sum_res = call_openai_json(
                self.client,
                build_summary_prompt(chunk),
                DEFAULT_DEEPSEEK_MODEL,
                self.temperature,
                thinking_enabled=use_thinking_mode,
            )
            previous_summary = sum_res.get("short_summary", "")
            _emit_progress(on_progress, {"stage": "extract", "current": idx, "total": len(extract_chunks)})

        business = sorted(list(merged_business.values()), key=lambda x: x.confidence, reverse=True)
        stakeholder = sorted(list(merged_stakeholder.values()), key=lambda x: x.confidence, reverse=True)
        system = sorted(list(merged_system.values()), key=lambda x: x.confidence, reverse=True)

        _emit_progress(on_progress, {"stage": "done", "current": 1, "total": 1})
        return RequirementGroup(business=business, stakeholder=stakeholder, system=system)

acquisition_service = RequirementsAcquisitionService()
