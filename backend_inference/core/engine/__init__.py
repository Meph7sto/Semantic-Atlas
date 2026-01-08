from typing import Optional

import torch

from core.config import settings
from .local import LocalHFEngine
from .remote import ChutesClient, DeepSeekClient


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
        self.deepseek_model = deepseek_model or getattr(settings, "DEEPSEEK_MODEL", "deepseek-chat")
        # 如果 CUDA 可用，自动配置 device_map，否则为 None
        self.device_map = "auto" if torch.cuda.is_available() else None
        self._local_engine = None
        self._remote_client = None

    def _get_local_engine(self) -> LocalHFEngine:
        if self._local_engine is None:
            self._local_engine = LocalHFEngine(self.model_path)
        return self._local_engine

    def _get_remote_client(self):
        if self.provider == "chutes":
            if not isinstance(self._remote_client, ChutesClient):
                self._remote_client = ChutesClient(self.chutes_api_url, self.chutes_api_token)
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

    def generate(self, prompt: str, system_prompt: str, max_new_tokens: int = 128) -> str:
        """
        根据给定的 prompt 和 system_prompt 生成响应
        """
        if self.provider == "chutes":
            client = self._get_remote_client()
            return client.generate(prompt, system_prompt, max_new_tokens)
        if self.provider == "deepseek":
            client = self._get_remote_client()
            return client.generate(prompt, system_prompt, max_new_tokens)

        local_engine = self._get_local_engine()
        return local_engine.generate(prompt, system_prompt, max_new_tokens)


__all__ = ["DeepSeekEngine"]
