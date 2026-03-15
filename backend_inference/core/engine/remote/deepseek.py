from dataclasses import dataclass, field
from typing import Any, Dict, Generator, List, Optional, Union

import requests

from .sse import extract_stream_content

DEFAULT_DEEPSEEK_ENDPOINT = "https://api.deepseek.com/v1/chat/completions"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"


@dataclass
class ToolCallResult:
    """Represents the result of a chat completion that may include tool calls."""

    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    reasoning_content: Optional[str] = None
    finish_reason: Optional[str] = None


class DeepSeekClient:
    """Minimal DeepSeek API client using the official Chat Completions endpoint."""

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

    def _resolve_endpoint(self) -> str:
        """Normalize user-provided URL to the expected /v1/chat/completions endpoint."""
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
        return f"{cleaned}/v1/chat/completions"

    def generate(
        self,
        prompt: str,
        system_prompt: str,
        max_new_tokens: int,
        model_override: Optional[str] = None,
    ) -> str:
        """Call DeepSeek chat completions and return concatenated content."""
        if not self.api_key:
            raise RuntimeError("DeepSeek API key is missing. Set DEEPSEEK_API_KEY.")

        endpoint = self._resolve_endpoint()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        target_model = model_override or self.model
        body = {
            "model": target_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_new_tokens,
            "stream": True,
        }
        # Remove unsupported parameters for reasoner model
        if "reasoner" not in target_model:
            body["temperature"] = 0.3

        chunks: List[str] = []
        try:
            response = requests.post(
                endpoint,
                headers=headers,
                json=body,
                stream=True,
                timeout=self.timeout,
            )
        except (
            requests.exceptions.RequestException
        ) as exc:  # pragma: no cover - network errors
            raise RuntimeError(f"DeepSeek API request failed: {exc}") from exc

        if response.status_code != 200:
            try:
                err_payload = response.json()
            except Exception:
                err_payload = response.text
            raise RuntimeError(
                f"DeepSeek API error {response.status_code}: {err_payload}"
            )

        for line in response.iter_lines():
            if not line:
                continue
            line_str = line.decode("utf-8").strip()
            data = line_str[5:] if line_str.startswith("data:") else line_str
            data = (
                data[1:].strip() if data.startswith(" ") else data
            )  # trim optional leading space
            if not data:
                continue
            if data == "[DONE]":
                break
            extract_stream_content(data, chunks)

        # 如果服务端未按流式返回，尝试读取一次性 JSON
        if not chunks:
            try:
                payload = response.json()
                choices = payload.get("choices") or []
                if choices:
                    message = choices[0].get("message") or {}
                    content = message.get("content") or ""
                    if content:
                        return str(content).strip()
            except Exception:
                pass

        return "".join(chunks).strip()

    def generate_stream(
        self,
        prompt: str,
        system_prompt: str,
        max_new_tokens: int,
        model_override: Optional[str] = None,
    ):
        """Yield content chunks from DeepSeek chat completions."""
        if not self.api_key:
            raise RuntimeError("DeepSeek API key is missing. Set DEEPSEEK_API_KEY.")

        endpoint = self._resolve_endpoint()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        target_model = model_override or self.model

        # Build body
        body = {
            "model": target_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_new_tokens,
            "stream": True,
        }

        # Remove unsupported parameters for reasoner model
        if "reasoner" not in target_model:
            body["temperature"] = 0.3

        try:
            response = requests.post(
                endpoint,
                headers=headers,
                json=body,
                stream=True,
                timeout=self.timeout,
            )
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(f"DeepSeek API request failed: {exc}") from exc

        if response.status_code != 200:
            try:
                err_payload = response.json()
            except Exception:
                err_payload = response.text
            raise RuntimeError(
                f"DeepSeek API error {response.status_code}: {err_payload}"
            )

        import json

        for line in response.iter_lines():
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
                if choices:
                    delta = choices[0].get("delta", {})

                    # 1. Check for reasoning content (Thinking Process)
                    # Note: API might return reasoning_content in delta
                    reasoning = delta.get("reasoning_content", "")
                    if reasoning:
                        yield {"type": "thinking", "delta": reasoning}

                    # 2. Check for final content
                    content = delta.get("content", "")
                    if content:
                        yield {"type": "content", "delta": content}

            except json.JSONDecodeError:
                pass

    def generate_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        max_new_tokens: int = 4096,
        tool_choice: Optional[str] = None,
        model_override: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> ToolCallResult:
        """
        Call DeepSeek chat completions with tool definitions.

        Args:
            messages: List of message dicts with role/content keys.
                      Supports roles: system, user, assistant, tool
            tools: List of tool definitions, each with type="function" and function spec
            max_new_tokens: Maximum tokens to generate
            tool_choice: "none" | "auto" | "required" | None (defaults to "auto" when tools present)
            model_override: Override the default model
            temperature: Optional temperature (not supported for reasoner models)

        Returns:
            ToolCallResult with content, tool_calls, reasoning_content, and finish_reason
        """
        if not self.api_key:
            raise RuntimeError("DeepSeek API key is missing. Set DEEPSEEK_API_KEY.")

        endpoint = self._resolve_endpoint()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        target_model = model_override or self.model

        body: Dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "max_tokens": max_new_tokens,
            "stream": False,
        }

        # Add tools if provided
        if tools:
            body["tools"] = tools
            if tool_choice:
                body["tool_choice"] = tool_choice

        # Temperature not supported for reasoner models
        if "reasoner" not in target_model:
            if temperature is not None:
                body["temperature"] = temperature
            else:
                body["temperature"] = 0.3

        try:
            response = requests.post(
                endpoint,
                headers=headers,
                json=body,
                timeout=self.timeout,
            )
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(f"DeepSeek API request failed: {exc}") from exc

        if response.status_code != 200:
            try:
                err_payload = response.json()
            except Exception:
                err_payload = response.text
            raise RuntimeError(
                f"DeepSeek API error {response.status_code}: {err_payload}"
            )

        import json

        payload = response.json()
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

    def generate_with_tools_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        max_new_tokens: int = 4096,
        tool_choice: Optional[str] = None,
        model_override: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Stream chat completions with tool definitions.

        Args:
            messages: List of message dicts with role/content keys
            tools: List of tool definitions
            max_new_tokens: Maximum tokens to generate
            tool_choice: "none" | "auto" | "required" | None
            model_override: Override the default model
            temperature: Optional temperature

        Yields:
            Dicts with type and delta keys:
            - {"type": "thinking", "delta": str} for reasoning content
            - {"type": "content", "delta": str} for final content
            - {"type": "tool_call", "index": int, "id": str, "function": {"name": str, "arguments": str}}
            - {"type": "finish", "finish_reason": str}
        """
        if not self.api_key:
            raise RuntimeError("DeepSeek API key is missing. Set DEEPSEEK_API_KEY.")

        endpoint = self._resolve_endpoint()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        target_model = model_override or self.model

        body: Dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "max_tokens": max_new_tokens,
            "stream": True,
        }

        # Add tools if provided
        if tools:
            body["tools"] = tools
            if tool_choice:
                body["tool_choice"] = tool_choice

        # Temperature not supported for reasoner models
        if "reasoner" not in target_model:
            if temperature is not None:
                body["temperature"] = temperature
            else:
                body["temperature"] = 0.3

        try:
            response = requests.post(
                endpoint,
                headers=headers,
                json=body,
                stream=True,
                timeout=self.timeout,
            )
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(f"DeepSeek API request failed: {exc}") from exc

        if response.status_code != 200:
            try:
                err_payload = response.json()
            except Exception:
                err_payload = response.text
            raise RuntimeError(
                f"DeepSeek API error {response.status_code}: {err_payload}"
            )

        import json

        # Track tool calls being built incrementally
        tool_calls_buffer: Dict[int, Dict[str, Any]] = {}

        for line in response.iter_lines():
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
                            tool_calls_buffer[index]["function"]["name"] = func["name"]
                        if func.get("arguments"):
                            tool_calls_buffer[index]["function"]["arguments"] += func[
                                "arguments"
                            ]

                        # Yield incremental tool call update
                        yield {
                            "type": "tool_call",
                            "index": index,
                            "id": tool_calls_buffer[index]["id"],
                            "function": {
                                "name": tool_calls_buffer[index]["function"]["name"],
                                "arguments": func.get("arguments", ""),  # incremental
                            },
                        }

                # 4. Check for finish reason
                if finish_reason:
                    yield {"type": "finish", "finish_reason": finish_reason}

            except json.JSONDecodeError:
                pass
