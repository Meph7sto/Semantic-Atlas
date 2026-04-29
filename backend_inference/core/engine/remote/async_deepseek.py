"""异步DeepSeek API客户端 - 使用aiohttp实现高性能异步请求"""

from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, List, Optional

import asyncio
import json
import aiohttp

from .deepseek import (
    DEFAULT_DEEPSEEK_ENDPOINT,
    DEFAULT_DEEPSEEK_MODEL,
    ToolCallResult,
    _apply_generation_controls,
    build_deepseek_tool_body,
    normalize_deepseek_model,
)


class AsyncDeepSeekClient:
    """异步DeepSeek API客户端，使用aiohttp实现高并发性能。

    与同步版本DeepSeekClient保持完全相同的接口，但所有方法都是异步的。
    """

    def __init__(
        self,
        api_url: str,
        api_key: Optional[str],
        model: str = DEFAULT_DEEPSEEK_MODEL,
        timeout: int = 600,
    ) -> None:
        self.api_url = api_url or DEFAULT_DEEPSEEK_ENDPOINT
        self.api_key = api_key
        self.model = model or DEFAULT_DEEPSEEK_MODEL
        self.timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        """支持 async with 语法"""
        await self.ensure_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """自动关闭session"""
        await self.close()

    async def ensure_session(self):
        """确保session已创建（复用连接池提升性能）"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )

    async def close(self):
        """关闭session并释放资源"""
        if self._session and not self._session.closed:
            await self._session.close()
            # 等待底层连接完全关闭
            await asyncio.sleep(0.25)

    def _resolve_endpoint(self) -> str:
        """规范化用户提供的URL为标准的 /chat/completions 端点。

        此方法与同步版本完全相同，保持兼容性。
        """
        url = (self.api_url or "").strip()
        if not url:
            return DEFAULT_DEEPSEEK_ENDPOINT

        cleaned = url.rstrip("/")
        if "chat/completions" in cleaned:
            return cleaned
        if cleaned.endswith("/v1"):
            return f"{cleaned}/chat/completions"
        if cleaned.endswith("/v1/chat"):
            return f"{cleaned}/completions"
        return f"{cleaned}/chat/completions"

    async def generate(
        self,
        prompt: str,
        system_prompt: str,
        max_new_tokens: int,
        model_override: Optional[str] = None,
        thinking_enabled: bool = True,
    ) -> str:
        """异步调用DeepSeek chat completions并返回内容。

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词
            max_new_tokens: 最大生成token数
            model_override: 可选的模型覆盖

        Returns:
            生成的完整文本内容

        Raises:
            RuntimeError: API key缺失或API请求失败
        """
        if not self.api_key:
            raise RuntimeError("DeepSeek API key is missing. Set DEEPSEEK_API_KEY.")

        await self.ensure_session()
        endpoint = self._resolve_endpoint()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        target_model = model_override or self.model
        body = {
            "model": normalize_deepseek_model(target_model),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_new_tokens,
            "stream": False,
        }
        _apply_generation_controls(
            body,
            target_model=target_model,
            temperature=0.3,
            thinking_enabled=thinking_enabled,
        )

        try:
            async with self._session.post(
                endpoint, headers=headers, json=body
            ) as response:
                if response.status != 200:
                    try:
                        err_payload = await response.json()
                    except Exception:
                        err_payload = await response.text()
                    raise RuntimeError(
                        f"DeepSeek API error {response.status}: {err_payload}"
                    )

                payload = await response.json()
                choices = payload.get("choices") or []
                if choices:
                    message = choices[0].get("message") or {}
                    content = message.get("content") or ""
                    if content:
                        return str(content).strip()

        except aiohttp.ClientError as exc:
            raise RuntimeError(f"DeepSeek API request failed: {exc}") from exc

        return ""

    def _extract_stream_content(self, data: str, chunks: List[str]) -> None:
        """从SSE数据中提取内容（与同步版本逻辑一致）"""
        try:
            payload = json.loads(data)
            choices = payload.get("choices") or []
            if choices:
                delta = choices[0].get("delta", {})
                content = delta.get("content", "")
                if content:
                    chunks.append(content)
        except json.JSONDecodeError:
            pass

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str,
        max_new_tokens: int,
        model_override: Optional[str] = None,
        thinking_enabled: bool = True,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """异步流式生成，逐块yield内容。

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词
            max_new_tokens: 最大生成token数
            model_override: 可选的模型覆盖

        Yields:
            字典，包含：
            - {"type": "thinking", "delta": str} 推理内容
            - {"type": "content", "delta": str} 最终内容

        Raises:
            RuntimeError: API key缺失或API请求失败
        """
        if not self.api_key:
            raise RuntimeError("DeepSeek API key is missing. Set DEEPSEEK_API_KEY.")

        await self.ensure_session()
        endpoint = self._resolve_endpoint()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        target_model = model_override or self.model

        # Build body
        body = {
            "model": normalize_deepseek_model(target_model),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_new_tokens,
            "stream": True,
        }
        _apply_generation_controls(
            body,
            target_model=target_model,
            temperature=0.3,
            thinking_enabled=thinking_enabled,
        )

        try:
            async with self._session.post(
                endpoint, headers=headers, json=body
            ) as response:
                if response.status != 200:
                    try:
                        err_payload = await response.json()
                    except Exception:
                        err_payload = await response.text()
                    raise RuntimeError(
                        f"DeepSeek API error {response.status}: {err_payload}"
                    )

                buffer = b""
                async for chunk in response.content.iter_chunked(1024):
                    if not chunk:
                        continue
                    buffer += chunk
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        line_str = line.decode("utf-8", errors="ignore").strip()
                        # Remove "data: " prefix
                        data = (
                            line_str[5:] if line_str.startswith("data:") else line_str
                        )
                        data = data.strip()

                        if not data:
                            continue
                        if data == "[DONE]":
                            buffer = b""
                            break

                        try:
                            payload = json.loads(data)
                            choices = payload.get("choices") or []
                            if choices:
                                delta = choices[0].get("delta", {})

                                # 1. Check for reasoning content (Thinking Process)
                                reasoning = delta.get("reasoning_content", "")
                                if reasoning:
                                    yield {"type": "thinking", "delta": reasoning}

                                # 2. Check for final content
                                content = delta.get("content", "")
                                if content:
                                    yield {"type": "content", "delta": content}

                        except json.JSONDecodeError:
                            pass

                if buffer.strip():
                    line_str = buffer.decode("utf-8", errors="ignore").strip()
                    data = line_str[5:] if line_str.startswith("data:") else line_str
                    data = data.strip()
                    if data and data != "[DONE]":
                        try:
                            payload = json.loads(data)
                            choices = payload.get("choices") or []
                            if choices:
                                delta = choices[0].get("delta", {})
                                reasoning = delta.get("reasoning_content", "")
                                if reasoning:
                                    yield {"type": "thinking", "delta": reasoning}
                                content = delta.get("content", "")
                                if content:
                                    yield {"type": "content", "delta": content}
                        except json.JSONDecodeError:
                            pass

        except aiohttp.ClientError as exc:
            raise RuntimeError(f"DeepSeek API request failed: {exc}") from exc

    async def generate_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        max_new_tokens: int = 4096,
        tool_choice: Optional[str] = None,
        model_override: Optional[str] = None,
        temperature: Optional[float] = None,
        thinking_enabled: bool = True,
    ) -> ToolCallResult:
        """异步调用DeepSeek chat completions并支持工具调用。

        Args:
            messages: 消息列表，每个消息包含role和content键。
                     支持的角色：system, user, assistant, tool
            tools: 工具定义列表，每个工具包含type="function"和function规范
            max_new_tokens: 最大生成token数
            tool_choice: "none" | "auto" | "required" | None（存在工具时默认为"auto"）
            model_override: 覆盖默认模型
            temperature: 可选的温度参数（thinking 模式不支持）

        Returns:
            ToolCallResult，包含content、tool_calls、reasoning_content和finish_reason

        Raises:
            RuntimeError: API key缺失或API请求失败
        """
        if not self.api_key:
            raise RuntimeError("DeepSeek API key is missing. Set DEEPSEEK_API_KEY.")

        await self.ensure_session()
        endpoint = self._resolve_endpoint()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        target_model = model_override or self.model

        body = build_deepseek_tool_body(
            messages=messages,
            tools=tools,
            max_new_tokens=max_new_tokens,
            tool_choice=tool_choice,
            target_model=target_model,
            temperature=temperature,
            thinking_enabled=thinking_enabled,
            stream=False,
        )

        try:
            async with self._session.post(
                endpoint, headers=headers, json=body
            ) as response:
                if response.status != 200:
                    try:
                        err_payload = await response.json()
                    except Exception:
                        err_payload = await response.text()
                    raise RuntimeError(
                        f"DeepSeek API error {response.status}: {err_payload}"
                    )

                payload = await response.json()
                choices = payload.get("choices") or []

                if not choices:
                    return ToolCallResult()

                choice = choices[0]
                message = choice.get("message", {})
                finish_reason = choice.get("finish_reason")

                return ToolCallResult(
                    content=message.get("content"),
                    tool_calls=message.get("tool_calls"),
                    reasoning_content=message.get("reasoning_content"),
                    finish_reason=finish_reason,
                )

        except aiohttp.ClientError as exc:
            raise RuntimeError(f"DeepSeek API request failed: {exc}") from exc

    async def generate_with_tools_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        max_new_tokens: int = 4096,
        tool_choice: Optional[str] = None,
        model_override: Optional[str] = None,
        temperature: Optional[float] = None,
        thinking_enabled: bool = True,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """异步流式调用，支持工具定义。

        Args:
            messages: 消息列表，包含role和content键
            tools: 工具定义列表
            max_new_tokens: 最大生成token数
            tool_choice: "none" | "auto" | "required" | None
            model_override: 覆盖默认模型
            temperature: 可选的温度参数

        Yields:
            字典，包含type和delta键：
            - {"type": "thinking", "delta": str} 推理内容
            - {"type": "content", "delta": str} 最终内容
            - {"type": "tool_call", "index": int, "id": str, "function": {"name": str, "arguments": str}}
            - {"type": "finish", "finish_reason": str}

        Raises:
            RuntimeError: API key缺失或API请求失败
        """
        if not self.api_key:
            raise RuntimeError("DeepSeek API key is missing. Set DEEPSEEK_API_KEY.")

        await self.ensure_session()
        endpoint = self._resolve_endpoint()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        target_model = model_override or self.model

        body = build_deepseek_tool_body(
            messages=messages,
            tools=tools,
            max_new_tokens=max_new_tokens,
            tool_choice=tool_choice,
            target_model=target_model,
            temperature=temperature,
            thinking_enabled=thinking_enabled,
            stream=True,
        )

        try:
            async with self._session.post(
                endpoint, headers=headers, json=body
            ) as response:
                if response.status != 200:
                    try:
                        err_payload = await response.json()
                    except Exception:
                        err_payload = await response.text()
                    raise RuntimeError(
                        f"DeepSeek API error {response.status}: {err_payload}"
                    )

                # Track tool calls being built incrementally
                tool_calls_buffer: Dict[int, Dict[str, Any]] = {}

                async for line in response.content:
                    if not line:
                        continue
                    line_str = line.decode("utf-8").strip()
                    # Remove "data: " prefix
                    data = line_str[5:] if line_str.startswith("data:") else line_str
                    data = data.strip()

                    if not data:
                        continue
                    if data == "[DONE]":
                        break

                    try:
                        payload = json.loads(data)
                        choices = payload.get("choices") or []
                        if not choices:
                            continue

                        choice = choices[0]
                        delta = choice.get("delta", {})
                        finish_reason = choice.get("finish_reason")

                        # 1. Check for reasoning content (Thinking Process)
                        reasoning = delta.get("reasoning_content", "")
                        if reasoning:
                            yield {"type": "thinking", "delta": reasoning}

                        # 2. Check for final content
                        content = delta.get("content", "")
                        if content:
                            yield {"type": "content", "delta": content}

                        # 3. Check for tool calls
                        tool_calls = delta.get("tool_calls")
                        if tool_calls:
                            for tc in tool_calls:
                                index = tc.get("index", 0)

                                # Initialize buffer for this tool call if needed
                                if index not in tool_calls_buffer:
                                    tool_calls_buffer[index] = {
                                        "id": tc.get("id", ""),
                                        "type": tc.get("type", "function"),
                                        "function": {"name": "", "arguments": ""},
                                    }

                                # Update with new data
                                if tc.get("id"):
                                    tool_calls_buffer[index]["id"] = tc["id"]
                                if tc.get("type"):
                                    tool_calls_buffer[index]["type"] = tc["type"]

                                func = tc.get("function", {})
                                if func.get("name"):
                                    tool_calls_buffer[index]["function"]["name"] = func[
                                        "name"
                                    ]
                                if func.get("arguments"):
                                    tool_calls_buffer[index]["function"][
                                        "arguments"
                                    ] += func["arguments"]

                                # Yield incremental tool call update
                                yield {
                                    "type": "tool_call",
                                    "index": index,
                                    "id": tool_calls_buffer[index]["id"],
                                    "function": {
                                        "name": tool_calls_buffer[index]["function"][
                                            "name"
                                        ],
                                        "arguments": func.get(
                                            "arguments", ""
                                        ),  # incremental
                                    },
                                }

                        # 4. Check for finish reason
                        if finish_reason:
                            yield {"type": "finish", "finish_reason": finish_reason}

                    except json.JSONDecodeError:
                        pass

        except aiohttp.ClientError as exc:
            raise RuntimeError(f"DeepSeek API request failed: {exc}") from exc
