from typing import Optional


class DeepSeekClient:
    """
    DeepSeek 官方 API 客户端占位符
    """

    def __init__(self, api_url: str, api_key: Optional[str]):
        self.api_url = api_url
        self.api_key = api_key

    def generate(self, prompt: str, system_prompt: str, max_new_tokens: int) -> str:
        """
        在接入真实 DeepSeek API 时，按需实现与 Chutes 类似的流式解析逻辑。
        """
        raise NotImplementedError("DeepSeek API client is not implemented yet.")
