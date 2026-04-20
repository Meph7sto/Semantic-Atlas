# 转发请求到 FastAPI :8000 的客户端占位符
# 此模块将来用于封装与推理后端 (FastAPI) 通信的逻辑
import asyncio
import json
import logging
import os
import aiohttp
import requests
from typing import Any, Dict, Generator, List, Optional

from backend_business.config import settings

logger = logging.getLogger(__name__)


def _is_reasoning_model(model: Optional[str]) -> bool:
    return "reasoner" in str(model or "").strip().lower()


def _normalize_tool_choice_for_model(
    model: Optional[str], tool_choice: Optional[str]
) -> Optional[str]:
    if not tool_choice:
        return None
    # DeepSeek thinking mode rejects tool_choice even when tool use is enabled.
    if _is_reasoning_model(model):
        return None
    return tool_choice


def _truncate_log_text(value: Any, limit: int = 160) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def _summarize_tool_completion_response(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {"response_type": type(data).__name__}

    raw_tool_calls = data.get("tool_calls")
    tool_calls = raw_tool_calls if isinstance(raw_tool_calls, list) else []
    tool_call_names = []
    for item in tool_calls[:5]:
        if not isinstance(item, dict):
            continue
        function_payload = item.get("function") or {}
        tool_name = str(function_payload.get("name") or "").strip()
        if tool_name:
            tool_call_names.append(tool_name)

    content_text = str(data.get("content") or "").strip()
    reasoning_text = str(data.get("reasoning_content") or "").strip()
    return {
        "finish_reason": data.get("finish_reason"),
        "content_present": bool(content_text),
        "content_preview": _truncate_log_text(content_text),
        "reasoning_content_present": bool(reasoning_text),
        "reasoning_preview": _truncate_log_text(reasoning_text),
        "tool_call_count": len(tool_calls),
        "tool_call_names": tool_call_names,
        "response_keys": sorted(str(key) for key in data.keys()),
    }


class AIProxy:
    """
    业务后端调用推理后端（backend_inference）的客户端封装。
    注意：不修改推理后端（尤其是冲突检测）内部结构，仅通过 HTTP 调用。
    """

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    @staticmethod
    def _optional_timeout_env(name: str, default: Optional[float]) -> Optional[float]:
        raw = os.environ.get(name)
        if raw is None:
            return default

        value = raw.strip().lower()
        if value in ("", "none", "null", "off", "false", "disabled", "disable"):
            return None

        return float(raw)

    def _context_builder_connect_timeout(self) -> float:
        return self._optional_timeout_env(
            "CONTEXT_BUILDER_CONNECT_TIMEOUT_SECONDS", 30.0
        ) or 30.0

    def _context_builder_read_timeout(self) -> Optional[float]:
        return self._optional_timeout_env(
            "CONTEXT_BUILDER_READ_TIMEOUT_SECONDS", None
        )

    def _context_builder_requests_timeout(self) -> tuple[float, Optional[float]]:
        # context-builder 是长耗时接口，默认不设读超时，避免慢模型被固定总时长截断。
        return (
            self._context_builder_connect_timeout(),
            self._context_builder_read_timeout(),
        )

    def _context_builder_aiohttp_timeout(self) -> aiohttp.ClientTimeout:
        connect_timeout = self._context_builder_connect_timeout()
        read_timeout = self._context_builder_read_timeout()
        return aiohttp.ClientTimeout(
            total=None,
            connect=connect_timeout,
            sock_connect=connect_timeout,
            sock_read=read_timeout,
        )

    def _tools_connect_timeout(self) -> float:
        return self._optional_timeout_env("TOOLS_CONNECT_TIMEOUT_SECONDS", 30.0) or 30.0

    def _tools_read_timeout(self) -> Optional[float]:
        return self._optional_timeout_env("TOOLS_READ_TIMEOUT_SECONDS", 600.0)

    def _tools_requests_timeout(self) -> tuple[float, Optional[float]]:
        return (
            self._tools_connect_timeout(),
            self._tools_read_timeout(),
        )

    def _tools_aiohttp_timeout(self) -> aiohttp.ClientTimeout:
        connect_timeout = self._tools_connect_timeout()
        read_timeout = self._tools_read_timeout()
        return aiohttp.ClientTimeout(
            total=None,
            connect=connect_timeout,
            sock_connect=connect_timeout,
            sock_read=read_timeout,
        )

    def _tools_max_retries(self) -> int:
        raw = os.environ.get("TOOLS_MAX_RETRIES", "2").strip()
        try:
            return max(0, min(5, int(raw)))
        except ValueError:
            return 2

    def _resolve_tools_timeouts(
        self,
        connect_timeout: Optional[float] = None,
        read_timeout: Optional[float] = None,
    ) -> tuple[float, Optional[float]]:
        resolved_connect = (
            self._tools_connect_timeout()
            if connect_timeout is None
            else max(0.1, float(connect_timeout))
        )
        resolved_read = (
            self._tools_read_timeout() if read_timeout is None else float(read_timeout)
        )
        return resolved_connect, resolved_read

    def _resolve_tools_aiohttp_timeout(
        self,
        connect_timeout: Optional[float] = None,
        read_timeout: Optional[float] = None,
    ) -> aiohttp.ClientTimeout:
        resolved_connect, resolved_read = self._resolve_tools_timeouts(
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
        )
        return aiohttp.ClientTimeout(
            total=None,
            connect=resolved_connect,
            sock_connect=resolved_connect,
            sock_read=resolved_read,
        )

    def _resolve_tools_max_retries(self, max_retries: Optional[int] = None) -> int:
        if max_retries is None:
            return self._tools_max_retries()
        return max(0, min(5, int(max_retries)))

    @staticmethod
    def _tools_retryable(exc: Exception) -> bool:
        if isinstance(exc, asyncio.TimeoutError):
            return True
        if isinstance(
            exc,
            (
                aiohttp.ClientConnectionError,
                aiohttp.ServerDisconnectedError,
                aiohttp.ClientOSError,
                aiohttp.ClientPayloadError,
            ),
        ):
            return True
        if isinstance(exc, aiohttp.ClientResponseError):
            return exc.status in {408, 409, 425, 429, 500, 502, 503, 504}
        return False

    @staticmethod
    def _parse_ndjson_buffer(buffer: str, handler) -> str:
        lines = buffer.split("\n")
        remainder = lines.pop() if lines else ""
        for line in lines:
            line = line.strip()
            if not line:
                continue
            handler(json.loads(line))
        return remainder

    def health(self) -> Dict[str, Any]:
        resp = requests.get(f"{self.base_url}/health", timeout=10)
        resp.raise_for_status()
        return resp.json()

    def trace_relation(
        self, high: str, low: str, max_new_tokens: int = 800
    ) -> Dict[str, Any]:
        resp = requests.post(
            f"{self.base_url}/traceability/relation",
            json={
                "high_level_requirement": high,
                "low_level_requirement": low,
                "max_new_tokens": max_new_tokens,
            },
            timeout=300,  # 5分钟
        )
        resp.raise_for_status()
        return resp.json()

    def trace_batch(
        self,
        highs: List[str],
        lows: List[str],
        max_new_tokens: int = 1600,
    ) -> Dict[str, Any]:
        # 批量分析可能需要更长时间，根据组合数量动态调整超时
        total_combinations = len(highs) * len(lows)
        timeout = max(300, total_combinations * 30)  # 每个组合至少30秒
        timeout = min(timeout, 1800)  # 最多30分钟

        resp = requests.post(
            f"{self.base_url}/traceability/batch-relation",
            json={
                "high_level_requirements": highs,
                "low_level_requirements": lows,
                "max_new_tokens": max_new_tokens,
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def trace_batch_selective(
        self,
        highs: List[str],
        lows: List[str],
        pair_indices: List[tuple],
        max_new_tokens: int = 800,
    ) -> Dict[str, Any]:
        """
        选择性批量追溯分析：只分析指定的 (high_index, low_index) 对
        而不是全量笛卡尔积。

        Args:
            highs: 顶层需求列表
            lows: 底层需求列表
            pair_indices: 需要分析的 (high_index, low_index) 列表
            max_new_tokens: 每次调用的 token 上限

        Returns:
            与 trace_batch 相同格式的结果
        """
        import time

        # 构建节点
        nodes = []
        high_node_ids = {}
        low_node_ids = {}

        for i, r in enumerate(highs):
            nid = f"high_{i}"
            high_node_ids[i] = nid
            nodes.append(
                {
                    "id": nid,
                    "name": f"顶层需求{i + 1}",
                    "text": (r[:100] + "...") if len(r) > 100 else r,
                    "level": 4,
                    "type": "high_level",
                }
            )

        for j, r in enumerate(lows):
            nid = f"low_{j}"
            low_node_ids[j] = nid
            nodes.append(
                {
                    "id": nid,
                    "name": f"底层需求{j + 1}",
                    "text": (r[:100] + "...") if len(r) > 100 else r,
                    "level": 2,
                    "type": "low_level",
                }
            )

        relations = []
        links = []
        relation_type_count = {}

        total_pairs = len(pair_indices)
        completed = 0
        failed_count = 0

        print(
            f"[选择性追溯] 开始分析 {total_pairs} 个映射对（而非全量 {len(highs)}×{len(lows)}={len(highs) * len(lows)} 个）"
        )

        for hi, li in pair_indices:
            completed += 1
            high_text = highs[hi]
            low_text = lows[li]

            # 带重试的单对分析
            single = None
            for attempt in range(3):
                try:
                    single = self.trace_relation(
                        high_text, low_text, max_new_tokens=max_new_tokens
                    )
                    break
                except (
                    requests.exceptions.Timeout,
                    requests.exceptions.ReadTimeout,
                ) as e:
                    if attempt < 2:
                        wait_time = 2 ** (attempt + 1)
                        print(
                            f"[重试 {attempt + 1}/3] 组合 (high[{hi}], low[{li}]) 超时，等待 {wait_time}s..."
                        )
                        time.sleep(wait_time)
                    else:
                        print(f"[选择性追溯] 组合 (high[{hi}], low[{li}]) 最终超时")
                except Exception as e:
                    if attempt < 2:
                        print(
                            f"[重试 {attempt + 1}/3] 组合 (high[{hi}], low[{li}]) 失败: {e}"
                        )
                        time.sleep(2)
                    else:
                        print(
                            f"[选择性追溯] 组合 (high[{hi}], low[{li}]) 最终失败: {e}"
                        )

            if single:
                rec = {
                    "high_level_index": hi,
                    "low_level_index": li,
                    "high_level_requirement": high_text,
                    "low_level_requirement": low_text,
                    "has_relation": single.get("has_relation", False),
                    "relation_type": single.get("relation_type", "unknown"),
                    "confidence": single.get("confidence", 0.0),
                    "analysis_details": single.get("analysis_details", ""),
                    "summary": single.get("summary", ""),
                    "keywords": single.get("keywords", []),
                }
                relations.append(rec)

                if single.get("has_relation"):
                    rel_type = (
                        single.get("relation_type") or "unknown"
                    ).strip() or "unknown"
                    relation_type_count[rel_type] = (
                        relation_type_count.get(rel_type, 0) + 1
                    )
                    links.append(
                        {
                            "source": high_node_ids[hi],
                            "target": low_node_ids[li],
                            "type": rel_type,
                            "label": rel_type,
                            "confidence": single.get("confidence", 0.0),
                        }
                    )
            else:
                failed_count += 1
                relations.append(
                    {
                        "high_level_index": hi,
                        "low_level_index": li,
                        "high_level_requirement": high_text,
                        "low_level_requirement": low_text,
                        "has_relation": False,
                        "relation_type": "unknown",
                        "confidence": 0.0,
                        "analysis_details": "分析失败(已重试)",
                        "summary": "分析失败",
                        "keywords": [],
                    }
                )

            if completed % 3 == 0 or completed == total_pairs:
                print(
                    f"[选择性追溯] 进度: {completed}/{total_pairs} ({100 * completed // total_pairs}%)"
                )

        relations_found = len([r for r in relations if r.get("has_relation")])

        print(
            f"[选择性追溯] 完成! 成功: {total_pairs - failed_count}/{total_pairs}, 发现关系: {relations_found}"
        )

        return {
            "summary": f"基于映射关系分析 {len(highs)} 个顶层需求与 {len(lows)} 个底层需求，共 {total_pairs} 个映射对，发现 {relations_found} 个追溯关系",
            "statistics": {
                "total_combinations": total_pairs,
                "relations_found": relations_found,
                "relation_rate": (relations_found / total_pairs)
                if total_pairs
                else 0.0,
            },
            "high_level_requirements": highs,
            "low_level_requirements": lows,
            "relations": relations,
            "trace_network": {
                "nodes": nodes,
                "links": links,
            },
            "relation_types_count": relation_type_count
            if relation_type_count
            else None,
        }

    def conflict_check(
        self,
        requirement_a: str,
        requirement_b: str,
        use_thinking_mode: bool = True,
    ) -> Dict[str, Any]:
        """
        可选：业务层也可代理冲突检测（不改变原冲突代码）。
        """
        resp = requests.post(
            f"{self.base_url}/conflict/check",
            json={
                "requirement_a": requirement_a,
                "requirement_b": requirement_b,
                "use_thinking_mode": use_thinking_mode,
            },
            timeout=300,  # 5分钟
        )
        resp.raise_for_status()
        return resp.json()

    def conflict_stream_check(
        self,
        requirement_a: str,
        requirement_b: str,
        use_thinking_mode: bool = True,
    ) -> Generator[bytes, None, None]:
        """
        冲突检测流式代理。
        透传推理后端 NDJSON 数据，供业务后端再转发给前端。
        """
        with requests.post(
            f"{self.base_url}/conflict/stream_check",
            json={
                "requirement_a": requirement_a,
                "requirement_b": requirement_b,
                "use_thinking_mode": use_thinking_mode,
            },
            stream=True,
            timeout=300,
        ) as resp:
            resp.raise_for_status()
            for chunk in resp.iter_content(chunk_size=1024):
                if chunk:
                    yield chunk

    def extract_requirements(
        self,
        text: str,
        chunk_size: int = 3600,
        overlap: int = 500,
        clean_model: str = "deepseek-reasoner",
        extract_model: str = "deepseek-reasoner",
    ) -> Dict[str, Any]:
        """
        调用推理后端进行需求抽取 (L1/L2/L3)
        """
        resp = requests.post(
            f"{self.base_url}/acquisition/extract",
            json={
                "text": text,
                "chunk_size": chunk_size,
                "overlap": overlap,
                "clean_model": clean_model,
                "extract_model": extract_model,
            },
            timeout=900,  # 抽取过程可能较慢，给足超时
        )
        resp.raise_for_status()
        return resp.json()

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = "deepseek-reasoner",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        调用推理后端的聊天补全接口
        用于需求抽取等任务

        Args:
            messages: 消息列表 [{"role": "system|user|assistant", "content": "..."}]
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大生成 token 数

        Returns:
            响应内容 {"content": "...", "usage": {...}}
        """
        resp = requests.post(
            f"{self.base_url}/chat/completions",
            json={
                "messages": messages,
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens or 2000,
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()

    def chat_completion_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        model: str = "deepseek-reasoner",
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        tool_choice: Optional[str] = None,
        connect_timeout: Optional[float] = None,
        read_timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        调用推理后端的带工具定义的聊天补全接口
        支持 DeepSeek API tool call 格式

        Args:
            messages: 消息列表 [{"role": "system|user|assistant|tool", "content": "...", ...}]
            tools: 工具定义列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大生成 token 数
            tool_choice: 工具选择策略 "none" | "auto" | "required"

        Returns:
            响应内容 {
                "content": "..." (可能为 None),
                "tool_calls": [...] (工具调用列表),
                "reasoning_content": "..." (可能为 None),
                "finish_reason": "stop" | "tool_calls" | "length"
            }
        """
        payload = {
            "messages": messages,
            "tools": tools,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens or 4096,
        }
        normalized_tool_choice = _normalize_tool_choice_for_model(model, tool_choice)
        if normalized_tool_choice:
            payload["tool_choice"] = normalized_tool_choice

        resolved_max_retries = self._resolve_tools_max_retries(max_retries)
        timeout = self._resolve_tools_timeouts(
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
        )
        url = f"{self.base_url}/chat/completions/tools"

        retryable_statuses = {408, 409, 425, 429, 500, 502, 503, 504}
        for attempt in range(resolved_max_retries + 1):
            try:
                resp = requests.post(
                    url,
                    json=payload,
                    timeout=timeout,
                )
                resp.raise_for_status()
                data = resp.json()
                summary = _summarize_tool_completion_response(data)
                logger.debug(
                    "Tool completion response summary: %s",
                    json.dumps(summary, ensure_ascii=False),
                )
                if (
                    summary.get("content_present") is False
                    and summary.get("tool_call_count") == 0
                ):
                    logger.warning(
                        "Tool completion response contained neither content nor tool calls: %s",
                        json.dumps(summary, ensure_ascii=False),
                    )
                return data
            except (requests.Timeout, requests.ConnectionError) as exc:
                if attempt >= resolved_max_retries:
                    raise
                backoff = min(8.0, float(2 ** attempt))
                logger.warning(
                    "Retrying sync tool-call request after transient error: attempt=%s/%s error=%s backoff=%.1fs",
                    attempt + 1,
                    resolved_max_retries + 1,
                    repr(exc),
                    backoff,
                )
                import time

                time.sleep(backoff)
            except requests.HTTPError as exc:
                status_code = exc.response.status_code if exc.response is not None else None
                if status_code not in retryable_statuses or attempt >= resolved_max_retries:
                    raise
                backoff = min(8.0, float(2 ** attempt))
                logger.warning(
                    "Retrying sync tool-call request after HTTP error: attempt=%s/%s status=%s backoff=%.1fs",
                    attempt + 1,
                    resolved_max_retries + 1,
                    status_code,
                    backoff,
                )
                import time

                time.sleep(backoff)

        raise RuntimeError("sync tool-call retries exhausted")

    async def chat_completion_with_tools_async(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        model: str = "deepseek-reasoner",
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        tool_choice: Optional[str] = None,
        session: Optional[aiohttp.ClientSession] = None,
        connect_timeout: Optional[float] = None,
        read_timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        异步版本的 chat_completion_with_tools，用于并发处理

        Args:
            messages: 消息列表
            tools: 工具定义列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大生成 token 数
            tool_choice: 工具选择策略
            session: 可选的 aiohttp ClientSession（用于连接复用）

        Returns:
            响应内容（与同步版本相同）
        """
        payload = {
            "messages": messages,
            "tools": tools,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens or 4096,
        }
        normalized_tool_choice = _normalize_tool_choice_for_model(model, tool_choice)
        if normalized_tool_choice:
            payload["tool_choice"] = normalized_tool_choice

        url = f"{self.base_url}/chat/completions/tools"

        # 如果提供了 session，使用它；否则创建临时 session
        should_close_session = False
        if session is None:
            session = aiohttp.ClientSession()
            should_close_session = True

        try:
            resolved_max_retries = self._resolve_tools_max_retries(max_retries)
            for attempt in range(resolved_max_retries + 1):
                try:
                    async with session.post(
                        url,
                        json=payload,
                        timeout=self._resolve_tools_aiohttp_timeout(
                            connect_timeout=connect_timeout,
                            read_timeout=read_timeout,
                        ),
                    ) as resp:
                        resp.raise_for_status()
                        return await resp.json()
                except Exception as exc:
                    if not self._tools_retryable(exc):
                        raise
                    if attempt >= resolved_max_retries:
                        raise
                    backoff = min(8.0, float(2 ** attempt))
                    logger.warning(
                        "Retrying tool-call request after transient error: attempt=%s/%s error=%s backoff=%.1fs",
                        attempt + 1,
                        resolved_max_retries + 1,
                        repr(exc),
                        backoff,
                    )
                    await asyncio.sleep(backoff)
        finally:
            if should_close_session:
                await session.close()

    def context_builder_completion(
        self,
        prompt: str,
        system_prompt: str,
        max_new_tokens: int = 8000,
        model: Optional[str] = None,
    ) -> str:
        """
        调用推理后端 context-builder 专用补全接口。
        """
        payload: Dict[str, Any] = {
            "prompt": prompt,
            "system_prompt": system_prompt,
            "max_tokens": max_new_tokens,
        }
        if model:
            payload["model"] = model

        resp = requests.post(
            f"{self.base_url}/chat/context-completion",
            json=payload,
            timeout=self._context_builder_requests_timeout(),
        )
        if resp.status_code in (404, 405):
            return self._context_builder_completion_fallback(
                prompt=prompt,
                system_prompt=system_prompt,
                max_new_tokens=max_new_tokens,
                model=model,
            )
        resp.raise_for_status()
        data = resp.json()
        return str(data.get("content", "")).strip()

    async def context_builder_completion_async(
        self,
        prompt: str,
        system_prompt: str,
        max_new_tokens: int = 8000,
        model: Optional[str] = None,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> str:
        """
        context-builder 专用补全接口的异步版本。
        """
        payload: Dict[str, Any] = {
            "prompt": prompt,
            "system_prompt": system_prompt,
            "max_tokens": max_new_tokens,
        }
        if model:
            payload["model"] = model

        url = f"{self.base_url}/chat/context-completion"

        should_close_session = False
        if session is None:
            session = aiohttp.ClientSession()
            should_close_session = True

        try:
            async with session.post(
                url,
                json=payload,
                timeout=self._context_builder_aiohttp_timeout(),
            ) as resp:
                if resp.status in (404, 405):
                    return await self._context_builder_completion_fallback_async(
                        prompt=prompt,
                        system_prompt=system_prompt,
                        max_new_tokens=max_new_tokens,
                        model=model,
                        session=session,
                    )
                resp.raise_for_status()
                data = await resp.json()
                return str(data.get("content", "")).strip()
        finally:
            if should_close_session:
                await session.close()

    def _context_builder_completion_fallback(
        self,
        prompt: str,
        system_prompt: str,
        max_new_tokens: int,
        model: Optional[str],
    ) -> str:
        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: Dict[str, Any] = {
            "messages": messages,
            "max_tokens": max_new_tokens,
            "temperature": 0.7,
        }
        if model:
            payload["model"] = model

        resp = requests.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            timeout=self._context_builder_requests_timeout(),
        )
        resp.raise_for_status()
        data = resp.json()
        return str(data.get("content", "")).strip()

    def context_builder_completion_stream(
        self,
        prompt: str,
        system_prompt: str,
        max_new_tokens: int = 8000,
        model: Optional[str] = None,
    ) -> str:
        payload: Dict[str, Any] = {
            "prompt": prompt,
            "system_prompt": system_prompt,
            "max_tokens": max_new_tokens,
        }
        if model:
            payload["model"] = model

        chunks: List[str] = []
        final_answer: Optional[str] = None

        def _handle_payload(item: Dict[str, Any]) -> None:
            nonlocal final_answer
            item_type = str(item.get("type", ""))
            if item_type == "result":
                data = item.get("data") or {}
                final_answer = str(data.get("answer", "")).strip()
            elif item_type == "token":
                chunks.append(str(item.get("content", "")))
            elif item_type == "error":
                raise RuntimeError(str(item.get("error", "streaming completion failed")))

        with requests.post(
            f"{self.base_url}/chat/context-completion/stream",
            json=payload,
            timeout=self._context_builder_requests_timeout(),
            stream=True,
        ) as resp:
            if resp.status_code in (404, 405):
                return self.context_builder_completion(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    max_new_tokens=max_new_tokens,
                    model=model,
                )

            resp.raise_for_status()
            buffer = ""
            for line in resp.iter_lines(decode_unicode=True):
                if line is None:
                    continue
                buffer += line + "\n"
                buffer = self._parse_ndjson_buffer(buffer, _handle_payload)

        if buffer.strip():
            _handle_payload(json.loads(buffer.strip()))

        if final_answer is not None:
            return final_answer
        return "".join(chunks).strip()

    async def _context_builder_completion_fallback_async(
        self,
        prompt: str,
        system_prompt: str,
        max_new_tokens: int,
        model: Optional[str],
        session: aiohttp.ClientSession,
    ) -> str:
        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: Dict[str, Any] = {
            "messages": messages,
            "max_tokens": max_new_tokens,
            "temperature": 0.7,
        }
        if model:
            payload["model"] = model

        async with session.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            timeout=self._context_builder_aiohttp_timeout(),
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return str(data.get("content", "")).strip()

    async def context_builder_completion_stream_async(
        self,
        prompt: str,
        system_prompt: str,
        max_new_tokens: int = 8000,
        model: Optional[str] = None,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> str:
        payload: Dict[str, Any] = {
            "prompt": prompt,
            "system_prompt": system_prompt,
            "max_tokens": max_new_tokens,
        }
        if model:
            payload["model"] = model

        chunks: List[str] = []
        final_answer: Optional[str] = None

        def _handle_payload(item: Dict[str, Any]) -> None:
            nonlocal final_answer
            item_type = str(item.get("type", ""))
            if item_type == "result":
                data = item.get("data") or {}
                final_answer = str(data.get("answer", "")).strip()
            elif item_type == "token":
                chunks.append(str(item.get("content", "")))
            elif item_type == "error":
                raise RuntimeError(str(item.get("error", "streaming completion failed")))

        should_close_session = False
        if session is None:
            session = aiohttp.ClientSession()
            should_close_session = True

        try:
            async with session.post(
                f"{self.base_url}/chat/context-completion/stream",
                json=payload,
                timeout=self._context_builder_aiohttp_timeout(),
            ) as resp:
                if resp.status in (404, 405):
                    return await self.context_builder_completion_async(
                        prompt=prompt,
                        system_prompt=system_prompt,
                        max_new_tokens=max_new_tokens,
                        model=model,
                        session=session,
                    )

                resp.raise_for_status()
                buffer = ""
                async for chunk in resp.content.iter_chunked(1024):
                    if not chunk:
                        continue
                    buffer += chunk.decode("utf-8", errors="ignore")
                    buffer = self._parse_ndjson_buffer(buffer, _handle_payload)

                if buffer.strip():
                    _handle_payload(json.loads(buffer.strip()))
        finally:
            if should_close_session:
                await session.close()

        if final_answer is not None:
            return final_answer
        return "".join(chunks).strip()


ai_proxy = AIProxy(settings.INFERENCE_BASE_URL)

# 转发请求到 FastAPI :8000 的客户端占位符
# 此模块将来用于封装与推理后端 (FastAPI) 通信的逻辑
