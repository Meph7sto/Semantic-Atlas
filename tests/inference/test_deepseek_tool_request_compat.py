import asyncio
import sys
import types

import pytest


class _UnusedTransformerLoader:
    @classmethod
    def from_pretrained(cls, *args, **kwargs):  # pragma: no cover - defensive stub
        raise AssertionError("Local transformer loading should not happen in this test.")


sys.modules.setdefault(
    "transformers",
    types.SimpleNamespace(
        AutoTokenizer=_UnusedTransformerLoader,
        AutoModelForCausalLM=_UnusedTransformerLoader,
        AutoModelForSeq2SeqLM=_UnusedTransformerLoader,
    ),
)


from backend_inference.core.engine.remote.async_deepseek import AsyncDeepSeekClient
from backend_inference.core.engine.remote.deepseek import (
    DEEPSEEK_MODELS,
    DEFAULT_DEEPSEEK_MODEL,
    DeepSeekClient,
    build_deepseek_tool_body,
)


def test_deepseek_catalog_contains_only_current_models():
    assert DEEPSEEK_MODELS == ("deepseek-v4-pro", "deepseek-flash")
    assert DEFAULT_DEEPSEEK_MODEL == "deepseek-v4-pro"


def _sample_tools():
    return [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get weather information.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string"},
                    },
                    "required": ["location"],
                },
            },
        }
    ]


def test_deepseek_endpoint_defaults_to_current_chat_completions_path():
    client = DeepSeekClient(
        api_url="https://api.deepseek.com",
        api_key="test-key",
        model="deepseek-v4-pro",
    )

    assert client._resolve_endpoint() == "https://api.deepseek.com/chat/completions"


def test_deepseek_endpoint_preserves_legacy_v1_base_url():
    client = DeepSeekClient(
        api_url="https://api.deepseek.com/v1",
        api_key="test-key",
        model="deepseek-v4-pro",
    )

    assert client._resolve_endpoint() == "https://api.deepseek.com/v1/chat/completions"


def test_build_deepseek_tool_body_uses_v4_pro_thinking_mode():
    body = build_deepseek_tool_body(
        messages=[
            {
                "role": "assistant",
                "content": "Let me think.",
                "reasoning_content": "internal chain of thought",
            },
            {"role": "user", "content": "What's the weather?"},
        ],
        tools=_sample_tools(),
        max_new_tokens=2048,
        tool_choice="required",
        target_model="deepseek-v4-pro",
        temperature=0.2,
        stream=False,
    )

    assert body["model"] == "deepseek-v4-pro"
    assert body["thinking"] == {"type": "enabled"}
    assert body["reasoning_effort"] == "high"
    assert "tool_choice" not in body
    assert "temperature" not in body
    assert body["messages"][0]["reasoning_content"] == "internal chain of thought"


def test_build_deepseek_tool_body_defaults_to_v4_pro_thinking_mode():
    body = build_deepseek_tool_body(
        messages=[{"role": "user", "content": "Hi"}],
        tools=_sample_tools(),
        max_new_tokens=1024,
        tool_choice="auto",
        target_model="",
        temperature=0.6,
        stream=True,
    )

    assert body["model"] == "deepseek-v4-pro"
    assert body["thinking"] == {"type": "enabled"}
    assert body["reasoning_effort"] == "high"
    assert "temperature" not in body
    assert "tool_choice" not in body
    assert body["stream"] is True


def test_build_deepseek_tool_body_allows_flash_with_default_thinking():
    body = build_deepseek_tool_body(
        messages=[{"role": "user", "content": "Hi"}],
        tools=_sample_tools(),
        max_new_tokens=1024,
        tool_choice="auto",
        target_model="deepseek-flash",
        temperature=0.6,
        stream=True,
    )

    assert body["model"] == "deepseek-flash"
    assert body["thinking"] == {"type": "enabled"}
    assert body["reasoning_effort"] == "high"
    assert "temperature" not in body
    assert "tool_choice" not in body
    assert body["stream"] is True


@pytest.mark.parametrize("model", ["deepseek-v4-pro", "deepseek-flash"])
def test_build_deepseek_tool_body_can_disable_thinking(model):
    body = build_deepseek_tool_body(
        messages=[{"role": "user", "content": "Hi"}],
        tools=_sample_tools(),
        max_new_tokens=1024,
        tool_choice="auto",
        target_model=model,
        temperature=0.6,
        thinking_enabled=False,
        stream=True,
    )

    assert body["model"] == model
    assert body["thinking"] == {"type": "disabled"}
    assert body["temperature"] == 0.6
    assert body["tool_choice"] == "auto"
    assert "reasoning_effort" not in body


@pytest.mark.parametrize("model", ["deepseek-v4-pro", "deepseek-flash"])
def test_generate_with_tools_posts_current_model_requests(monkeypatch, model):
    captured = {}

    class _Response:
        status_code = 200
        text = ""

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "get_weather",
                                        "arguments": '{"location":"Hangzhou"}',
                                    },
                                }
                            ],
                            "reasoning_content": "thinking",
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            }

    def _fake_post(url, headers=None, json=None, timeout=None, **kwargs):
        captured["url"] = url
        captured["json"] = json
        return _Response()

    monkeypatch.setattr(
        "backend_inference.core.engine.remote.deepseek.requests.post",
        _fake_post,
    )

    client = DeepSeekClient(
        api_url="https://api.deepseek.com",
        api_key="test-key",
        model=model,
    )

    result = client.generate_with_tools(
        messages=[
            {
                "role": "assistant",
                "content": "Prior reply",
                "reasoning_content": "should not be sent back",
            },
            {"role": "user", "content": "杭州天气怎么样？"},
        ],
        tools=_sample_tools(),
        tool_choice="required",
    )

    assert captured["json"]["model"] == model
    assert captured["json"]["thinking"] == {"type": "enabled"}
    assert captured["json"]["reasoning_effort"] == "high"
    assert captured["json"]["messages"][0]["reasoning_content"] == "should not be sent back"
    assert "tool_choice" not in captured["json"]
    assert result.finish_reason == "tool_calls"
    assert result.tool_calls[0]["function"]["name"] == "get_weather"


@pytest.mark.parametrize("model", ["deepseek-v4-pro", "deepseek-flash"])
def test_async_generate_with_tools_posts_current_model_requests(model):
    captured = {}

    class _AsyncResponse:
        def __init__(self, payload):
            self.status = 200
            self._payload = payload

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

        async def json(self):
            return self._payload

        async def text(self):
            return ""

    class _AsyncSession:
        closed = False

        def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["json"] = json
            return _AsyncResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "done",
                                "tool_calls": None,
                                "reasoning_content": "thinking",
                            },
                            "finish_reason": "stop",
                        }
                    ]
                }
            )

    async def _run():
        client = AsyncDeepSeekClient(
            api_url="https://api.deepseek.com",
            api_key="test-key",
            model=model,
        )
        client._session = _AsyncSession()
        return await client.generate_with_tools(
            messages=[
                {
                    "role": "assistant",
                    "content": "Previous reply",
                    "reasoning_content": "should not be sent back",
                },
                {"role": "user", "content": "继续"},
            ],
            tools=_sample_tools(),
            tool_choice="auto",
        )

    result = asyncio.run(_run())

    assert captured["json"]["model"] == model
    assert captured["json"]["thinking"] == {"type": "enabled"}
    assert captured["json"]["reasoning_effort"] == "high"
    assert "tool_choice" not in captured["json"]
    assert captured["json"]["messages"][0]["reasoning_content"] == "should not be sent back"
    assert result.content == "done"
