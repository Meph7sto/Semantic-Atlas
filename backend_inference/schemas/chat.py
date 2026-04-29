from pydantic import BaseModel

from core.engine.remote.deepseek import DEFAULT_DEEPSEEK_MODEL


class ChatRequest(BaseModel):
    """
    General chat request model.
    """

    prompt: str
    system_prompt: str = ""
    max_new_tokens: int = 512
    model: str = DEFAULT_DEEPSEEK_MODEL
    use_thinking_mode: bool = True
    use_async_client: bool = False


class ChatResponse(BaseModel):
    """
    General chat response model.
    """

    answer: str
