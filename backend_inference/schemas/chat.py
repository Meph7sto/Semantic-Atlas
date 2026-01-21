from pydantic import BaseModel


class ChatRequest(BaseModel):
    """
    General chat request model.
    """
    prompt: str
    system_prompt: str = ""
    max_new_tokens: int = 512
    use_thinking_mode: bool = False


class ChatResponse(BaseModel):
    """
    General chat response model.
    """
    answer: str
