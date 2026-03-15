"""异步Chutes API客户端 - 使用aiohttp实现高性能异步请求"""

from typing import List, Optional

import aiohttp
import asyncio
import json


class AsyncChutesClient:
    """异步Chutes API客户端，使用aiohttp实现高并发性能。

    与同步版本ChutesClient保持完全相同的接口，但所有方法都是异步的。
    """

    def __init__(self, api_url: str, api_token: Optional[str]):
        self.api_url = api_url
        self.api_token = api_token
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
                timeout=aiohttp.ClientTimeout(total=600)
            )

    async def close(self):
        """关闭session并释放资源"""
        if self._session and not self._session.closed:
            await self._session.close()
            # 等待底层连接完全关闭
            await asyncio.sleep(0.25)

    async def generate(
        self, prompt: str, system_prompt: str, max_new_tokens: int
    ) -> str:
        """异步使用 Chutes API 进行推理，采用流式解析。

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词
            max_new_tokens: 最大生成token数

        Returns:
            生成的完整文本内容

        Raises:
            RuntimeError: API token缺失或API请求失败
        """
        if not self.api_token:
            raise RuntimeError(
                "Chutes API token is missing. Set CHUTES_API_TOKEN/CHUTES_API_KEY."
            )

        await self.ensure_session()

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
            async with self._session.post(
                self.api_url, headers=headers, json=body
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(
                        f"Chutes API error {response.status}: {error_text}"
                    )

                buffer = b""
                async for chunk in response.content.iter_chunked(1024):
                    if not chunk:
                        continue
                    buffer += chunk
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        line_str = line.decode("utf-8", errors="ignore").strip()
                        data = (
                            line_str[6:] if line_str.startswith("data: ") else line_str
                        )
                        if not data:
                            continue
                        if data == "[DONE]":
                            buffer = b""
                            break
                        self._extract_stream_content(data, chunks)

                if buffer.strip():
                    line_str = buffer.decode("utf-8", errors="ignore").strip()
                    data = line_str[6:] if line_str.startswith("data: ") else line_str
                    if data and data != "[DONE]":
                        self._extract_stream_content(data, chunks)

        except aiohttp.ClientError as e:
            raise RuntimeError(f"Chutes API request failed: {e}")

        return "".join(chunks).strip()

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
