from typing import List, Optional

from .sse import extract_stream_content


class ChutesClient:
    """
    Chutes API 客户端
    """

    def __init__(self, api_url: str, api_token: Optional[str]):
        self.api_url = api_url
        self.api_token = api_token

    def generate(self, prompt: str, system_prompt: str, max_new_tokens: int) -> str:
        """
        使用 Chutes API 进行推理，采用 requests 进行同步流式解析。
        """
        import requests

        if not self.api_token:
            raise RuntimeError("Chutes API token is missing. Set CHUTES_API_TOKEN/CHUTES_API_KEY.")

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }
        body = {
            "model": "deepseek-ai/DeepSeek-V3.1-Terminus",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "stream": True,
            "max_tokens": max_new_tokens,
            "temperature": 0.7,
        }

        chunks: List[str] = []

        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                json=body,
                stream=True,
                timeout=600,
            )

            if response.status_code != 200:
                raise RuntimeError(f"Chutes API error {response.status_code}: {response.text}")

            for line in response.iter_lines():
                if not line:
                    continue
                line_str = line.decode("utf-8").strip()
                data = line_str[6:] if line_str.startswith("data: ") else line_str
                if not data:
                    continue
                if data == "[DONE]":
                    break
                extract_stream_content(data, chunks)

        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Chutes API request failed: {e}")

        return "".join(chunks).strip()
