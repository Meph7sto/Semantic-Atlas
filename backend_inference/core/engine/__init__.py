from typing import Any, AsyncGenerator, Dict, Generator, List, Optional

import torch
import asyncio

from ..config import settings
from .local import LocalHFEngine
from .remote import ChutesClient, DeepSeekClient, ToolCallResult
from .remote.async_deepseek import AsyncDeepSeekClient
from .remote.async_chutes import AsyncChutesClient


class DeepSeekEngine:
    """
    DeepSeek 模型引擎类
    负责加载模型、Tokenizer 以及执行文本生成任务
    """

    def __init__(
        self,
        model_path: str,
        provider: str = "local",
        chutes_api_url: Optional[str] = None,
        chutes_api_token: Optional[str] = None,
        deepseek_api_url: Optional[str] = None,
        deepseek_api_key: Optional[str] = None,
        deepseek_model: Optional[str] = None,
    ):
        self.model_path = model_path
        self.model = None
        self.tokenizer = None
        self.provider = (provider or settings.MODEL_PROVIDER).lower()
        self.chutes_api_url = chutes_api_url or settings.CHUTES_API_URL
        self.chutes_api_token = chutes_api_token or settings.CHUTES_API_TOKEN
        self.deepseek_api_url = deepseek_api_url or settings.DEEPSEEK_API_URL
        self.deepseek_api_key = deepseek_api_key or settings.DEEPSEEK_API_KEY
        self.deepseek_model = deepseek_model or getattr(
            settings, "DEEPSEEK_MODEL", "deepseek-chat"
        )
        # 如果 CUDA 可用，自动配置 device_map，否则为 None
        self.device_map = "auto" if torch.cuda.is_available() else None
        self._local_engine = None
        self._remote_client = None
        self._async_remote_client = None

    def _get_local_engine(self) -> LocalHFEngine:
        if self._local_engine is None:
            self._local_engine = LocalHFEngine(self.model_path)
        return self._local_engine

    def _get_remote_client(self):
        if self.provider == "chutes":
            if not isinstance(self._remote_client, ChutesClient):
                self._remote_client = ChutesClient(
                    self.chutes_api_url, self.chutes_api_token
                )
            return self._remote_client
        if self.provider == "deepseek":
            if not isinstance(self._remote_client, DeepSeekClient):
                self._remote_client = DeepSeekClient(
                    self.deepseek_api_url,
                    self.deepseek_api_key,
                    model=self.deepseek_model,
                )
            return self._remote_client
        return None

    async def _get_async_remote_client(self):
        """获取异步远程客户端（复用session以提升性能）"""
        if self.provider == "chutes":
            if not isinstance(self._async_remote_client, AsyncChutesClient):
                self._async_remote_client = AsyncChutesClient(
                    self.chutes_api_url, self.chutes_api_token
                )
                await self._async_remote_client.ensure_session()
            return self._async_remote_client
        if self.provider == "deepseek":
            if not isinstance(self._async_remote_client, AsyncDeepSeekClient):
                self._async_remote_client = AsyncDeepSeekClient(
                    self.deepseek_api_url,
                    self.deepseek_api_key,
                    model=self.deepseek_model,
                )
                await self._async_remote_client.ensure_session()
            return self._async_remote_client
        return None

    # ---------------------
    # 本地模型加载逻辑
    # ---------------------
    def load_model(self):
        """
        加载 Tokenizer 和模型
        """
        if self.provider != "local":
            # API 模式下无需加载本地模型
            self.model = "api"  # 简单标记可用
            self.tokenizer = None
            print(f"Using remote provider '{self.provider}', skip local model loading.")
            return

        local_engine = self._get_local_engine()
        local_engine.load_model()
        self.model = local_engine.model
        self.tokenizer = local_engine.tokenizer
        self.device_map = local_engine.device_map

    def generate(
        self,
        prompt: str,
        system_prompt: str,
        max_new_tokens: int = 128,
        model: Optional[str] = None,
    ) -> str:
        """
        根据给定的 prompt 和 system_prompt 生成响应
        """
        if self.provider == "chutes":
            client = self._get_remote_client()
            return client.generate(prompt, system_prompt, max_new_tokens)
        if self.provider == "deepseek":
            client = self._get_remote_client()
            return client.generate(
                prompt, system_prompt, max_new_tokens, model_override=model
            )

        local_engine = self._get_local_engine()
        return local_engine.generate(prompt, system_prompt, max_new_tokens)

    def generate_stream(
        self,
        prompt: str,
        system_prompt: str,
        max_new_tokens: int = 128,
        model: Optional[str] = None,
    ):
        """
        流式生成响应
        """
        if self.provider == "deepseek":
            client = self._get_remote_client()
            return client.generate_stream(
                prompt, system_prompt, max_new_tokens, model_override=model
            )

        # Fallback for other providers if not implemented (e.g. local/chutes)
        # return a simulated stream from the full generation
        full_text = self.generate(prompt, system_prompt, max_new_tokens)

        # Generator for fallback
        def _simulated_stream():
            # simulate chunks
            chunk_size = 4
            for i in range(0, len(full_text), chunk_size):
                yield {"type": "content", "delta": full_text[i : i + chunk_size]}

        return _simulated_stream()

    def generate_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        max_new_tokens: int = 4096,
        tool_choice: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> ToolCallResult:
        """
        使用工具定义生成响应（仅支持 deepseek provider）

        Args:
            messages: 消息列表，支持 system/user/assistant/tool 角色
            tools: 工具定义列表
            max_new_tokens: 最大生成 token 数
            tool_choice: "none" | "auto" | "required"
            model: 模型覆盖
            temperature: 温度参数

        Returns:
            ToolCallResult 包含 content, tool_calls, reasoning_content, finish_reason
        """
        if self.provider != "deepseek":
            raise NotImplementedError(
                f"Tool calls not supported for provider: {self.provider}"
            )

        client = self._get_remote_client()
        return client.generate_with_tools(
            messages=messages,
            tools=tools,
            max_new_tokens=max_new_tokens,
            tool_choice=tool_choice,
            model_override=model,
            temperature=temperature,
        )

    def generate_with_tools_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        max_new_tokens: int = 4096,
        tool_choice: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """
        流式生成带工具调用的响应（仅支持 deepseek provider）

        Args:
            messages: 消息列表
            tools: 工具定义列表
            max_new_tokens: 最大生成 token 数
            tool_choice: "none" | "auto" | "required"
            model: 模型覆盖
            temperature: 温度参数

        Yields:
            包含 type 和相关数据的字典:
            - {"type": "thinking", "delta": str}
            - {"type": "content", "delta": str}
            - {"type": "tool_call", "index": int, "id": str, "function": {...}}
            - {"type": "finish", "finish_reason": str}
        """
        if self.provider != "deepseek":
            raise NotImplementedError(
                f"Tool calls not supported for provider: {self.provider}"
            )

        client = self._get_remote_client()
        return client.generate_with_tools_stream(
            messages=messages,
            tools=tools,
            max_new_tokens=max_new_tokens,
            tool_choice=tool_choice,
            model_override=model,
            temperature=temperature,
        )

    # =====================================================
    # 异步接口（新增）- 使用aiohttp实现高并发性能
    # =====================================================

    async def generate_async(
        self,
        prompt: str,
        system_prompt: str,
        max_new_tokens: int = 128,
        model: Optional[str] = None,
    ) -> str:
        """异步生成响应（使用aiohttp，性能更高）

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词
            max_new_tokens: 最大生成token数
            model: 可选的模型覆盖

        Returns:
            生成的完整文本内容
        """
        if self.provider == "chutes":
            client = await self._get_async_remote_client()
            return await client.generate(prompt, system_prompt, max_new_tokens)
        if self.provider == "deepseek":
            client = await self._get_async_remote_client()
            return await client.generate(
                prompt, system_prompt, max_new_tokens, model_override=model
            )

        # 本地引擎在线程池中运行（避免阻塞事件循环）
        local_engine = self._get_local_engine()
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: local_engine.generate(prompt, system_prompt, max_new_tokens)
        )

    async def generate_stream_async(
        self,
        prompt: str,
        system_prompt: str,
        max_new_tokens: int = 128,
        model: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """异步流式生成响应

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词
            max_new_tokens: 最大生成token数
            model: 可选的模型覆盖

        Yields:
            字典，包含：
            - {"type": "thinking", "delta": str} 推理内容
            - {"type": "content", "delta": str} 最终内容
        """
        if self.provider == "deepseek":
            client = await self._get_async_remote_client()
            async for chunk in client.generate_stream(
                prompt, system_prompt, max_new_tokens, model_override=model
            ):
                yield chunk
        else:
            # Fallback for other providers (chutes, local)
            # 在线程池中运行同步generate，然后模拟流式输出
            full_text = await self.generate_async(prompt, system_prompt, max_new_tokens)

            # 模拟分块输出
            chunk_size = 4
            for i in range(0, len(full_text), chunk_size):
                yield {"type": "content", "delta": full_text[i : i + chunk_size]}
                await asyncio.sleep(0)  # 让出控制权

    async def generate_with_tools_async(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        max_new_tokens: int = 4096,
        tool_choice: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> ToolCallResult:
        """异步生成带工具调用的响应（仅支持 deepseek provider）

        Args:
            messages: 消息列表，支持 system/user/assistant/tool 角色
            tools: 工具定义列表
            max_new_tokens: 最大生成 token 数
            tool_choice: "none" | "auto" | "required"
            model: 模型覆盖
            temperature: 温度参数

        Returns:
            ToolCallResult 包含 content, tool_calls, reasoning_content, finish_reason
        """
        if self.provider != "deepseek":
            raise NotImplementedError(
                f"Tool calls not supported for provider: {self.provider}"
            )

        client = await self._get_async_remote_client()
        return await client.generate_with_tools(
            messages=messages,
            tools=tools,
            max_new_tokens=max_new_tokens,
            tool_choice=tool_choice,
            model_override=model,
            temperature=temperature,
        )

    async def generate_with_tools_stream_async(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        max_new_tokens: int = 4096,
        tool_choice: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """异步流式生成带工具调用的响应（仅支持 deepseek provider）

        Args:
            messages: 消息列表
            tools: 工具定义列表
            max_new_tokens: 最大生成 token 数
            tool_choice: "none" | "auto" | "required"
            model: 模型覆盖
            temperature: 温度参数

        Yields:
            包含 type 和相关数据的字典:
            - {"type": "thinking", "delta": str}
            - {"type": "content", "delta": str}
            - {"type": "tool_call", "index": int, "id": str, "function": {...}}
            - {"type": "finish", "finish_reason": str}
        """
        if self.provider != "deepseek":
            raise NotImplementedError(
                f"Tool calls not supported for provider: {self.provider}"
            )

        client = await self._get_async_remote_client()
        async for chunk in client.generate_with_tools_stream(
            messages=messages,
            tools=tools,
            max_new_tokens=max_new_tokens,
            tool_choice=tool_choice,
            model_override=model,
            temperature=temperature,
        ):
            yield chunk

    async def close_async(self):
        """关闭异步资源（session等）"""
        if self._async_remote_client:
            await self._async_remote_client.close()


__all__ = ["DeepSeekEngine", "ToolCallResult"]
