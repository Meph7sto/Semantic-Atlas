from typing import List, Optional

import requests

from .sse import extract_stream_content

DEFAULT_DEEPSEEK_ENDPOINT = "https://api.deepseek.com/v1/chat/completions"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"


class DeepSeekClient:
    """Minimal DeepSeek API client using the official Chat Completions endpoint."""

    def __init__(
        self,
        api_url: str,
        api_key: Optional[str],
        model: str = DEFAULT_DEEPSEEK_MODEL,
        timeout: int = 120,
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

    def generate(self, prompt: str, system_prompt: str, max_new_tokens: int) -> str:
        """Call DeepSeek chat completions and return concatenated content."""
        if not self.api_key:
            raise RuntimeError("DeepSeek API key is missing. Set DEEPSEEK_API_KEY.")

        endpoint = self._resolve_endpoint()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_new_tokens,
            "stream": True,
            "temperature": 0.3,
        }

        chunks: List[str] = []
        try:
            response = requests.post(
                endpoint,
                headers=headers,
                json=body,
                stream=True,
                timeout=self.timeout,
            )
        except requests.exceptions.RequestException as exc:  # pragma: no cover - network errors
            raise RuntimeError(f"DeepSeek API request failed: {exc}") from exc

        if response.status_code != 200:
            try:
                err_payload = response.json()
            except Exception:
                err_payload = response.text
            raise RuntimeError(f"DeepSeek API error {response.status_code}: {err_payload}")

        for line in response.iter_lines():
            if not line:
                continue
            line_str = line.decode("utf-8").strip()
            data = line_str[5:] if line_str.startswith("data:") else line_str
            data = data[1:].strip() if data.startswith(" ") else data  # trim optional leading space
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

    def generate_stream(self, prompt: str, system_prompt: str, max_new_tokens: int):
        """Yield content chunks from DeepSeek chat completions."""
        if not self.api_key:
            raise RuntimeError("DeepSeek API key is missing. Set DEEPSEEK_API_KEY.")

        endpoint = self._resolve_endpoint()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_new_tokens,
            "stream": True,
            "temperature": 0.3,
        }

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
            raise RuntimeError(f"DeepSeek API error {response.status_code}: {err_payload}")

        for line in response.iter_lines():
            if not line:
                continue
            line_str = line.decode("utf-8").strip()
            data = line_str[5:] if line_str.startswith("data:") else line_str
            data = data[1:].strip() if data.startswith(" ") else data
            if not data:
                continue
            if data == "[DONE]":
                break
            
            # Re-use the logic from sse.extract_stream_content but yield directly
            # Since extract_stream_content appends to a list, we can just reproduce the logic here simply
            # or modify extract_stream_content. 
            # Looking at sse.py (not visible but imported), assuming simple structure:
            try:
                import json
                chunk_json = json.loads(data)
                choices = chunk_json.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
            except Exception:
                pass
