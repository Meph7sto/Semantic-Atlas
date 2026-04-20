import os

import pytest

from backend_inference.core.config import settings
from backend_inference.core.engine import DeepSeekEngine


_RUN_DEEPSEEK_INTEGRATION = (
    os.getenv("RUN_DEEPSEEK_INTEGRATION", "").strip().lower() in {"1", "true", "yes"}
)

pytestmark = pytest.mark.skipif(
    not _RUN_DEEPSEEK_INTEGRATION,
    reason="Online DeepSeek tests are opt-in. Set RUN_DEEPSEEK_INTEGRATION=1 to run.",
)


def _build_engine() -> DeepSeekEngine:
    return DeepSeekEngine(
        model_path="",
        provider="deepseek",
        deepseek_api_url=settings.DEEPSEEK_API_URL,
        deepseek_api_key=settings.DEEPSEEK_API_KEY,
        deepseek_model=settings.DEEPSEEK_MODEL,
    )


def _build_ping_tool():
    return [
        {
            "type": "function",
            "function": {
                "name": "ping",
                "description": "Echo back the provided text exactly once.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Text to echo back verbatim.",
                        }
                    },
                    "required": ["text"],
                },
            },
        }
    ]


def test_online_deepseek_toolcall_roundtrip_uses_env_api():
    if not settings.DEEPSEEK_API_KEY.strip():
        pytest.skip("DEEPSEEK_API_KEY is not configured in env/.env.")

    engine = _build_engine()
    tools = _build_ping_tool()

    first_turn = engine.generate_with_tools(
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a careful assistant. When the user asks you to use ping, "
                    "you must call the ping tool before answering."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Call the ping tool with text exactly 'env-online-toolcall-ok'. "
                    "Do not answer directly before calling the tool."
                ),
            },
        ],
        tools=tools,
        max_new_tokens=1024,
        tool_choice="required",
        model=settings.DEEPSEEK_MODEL,
    )

    assert first_turn.tool_calls, "Model did not return any tool call."
    first_call = first_turn.tool_calls[0]
    assert first_call["function"]["name"] == "ping"
    assert "env-online-toolcall-ok" in first_call["function"]["arguments"]

    second_turn = engine.generate_with_tools(
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a careful assistant. Summarize the tool result in one short sentence."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Call the ping tool with text exactly 'env-online-toolcall-ok'. "
                    "Do not answer directly before calling the tool."
                ),
            },
            {
                "role": "assistant",
                "content": first_turn.content,
                "reasoning_content": first_turn.reasoning_content,
                "tool_calls": first_turn.tool_calls,
            },
            {
                "role": "tool",
                "tool_call_id": first_call["id"],
                "content": "env-online-toolcall-ok",
            },
        ],
        tools=tools,
        max_new_tokens=1024,
        model=settings.DEEPSEEK_MODEL,
    )

    assert isinstance(second_turn.content, str)
    assert second_turn.content.strip(), "Model did not return final content after tool result."
    assert "env-online-toolcall-ok" in second_turn.content
