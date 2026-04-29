"""
FastAPI chat inference route contract tests.
"""

import json

import pytest

chat = pytest.importorskip("backend_inference.routers.chat")


class _StubModelEngine:
    def __init__(self):
        self.generate_called = False
        self.generate_async_calls = []
        self.generate_stream_async_calls = []

    def generate(self, *args, **kwargs):
        self.generate_called = True
        raise AssertionError("sync generate() should not be used by async routes")

    async def generate_async(
        self,
        prompt: str,
        system_prompt: str,
        max_new_tokens: int = 128,
        model: str | None = None,
        thinking_enabled: bool = True,
    ) -> str:
        self.generate_async_calls.append(
            {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "max_new_tokens": max_new_tokens,
                "model": model,
                "thinking_enabled": thinking_enabled,
            }
        )
        return '{"links":[],"noise":[]}'

    async def generate_stream_async(
        self,
        prompt: str,
        system_prompt: str,
        max_new_tokens: int = 128,
        model: str | None = None,
        thinking_enabled: bool = True,
    ):
        self.generate_stream_async_calls.append(
            {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "max_new_tokens": max_new_tokens,
                "model": model,
                "thinking_enabled": thinking_enabled,
            }
        )
        yield {"type": "thinking", "delta": "reasoning"}
        yield {"type": "content", "delta": '{"links":[],"noise":[]}'}


@pytest.fixture
async def fastapi_client(monkeypatch):
    stub_engine = _StubModelEngine()
    monkeypatch.setattr(chat, "model_engine", stub_engine)

    app = build_test_app(chat.router, include_error_handlers=False)
    async with async_client(app) as client:
        yield client, stub_engine


async def test_context_completion_uses_async_generation(fastapi_client):
    client, stub_engine = fastapi_client

    response = await client.post(
        "/chat/context-completion",
        json={
            "prompt": "Analyze these spans",
            "system_prompt": "Return JSON only",
            "model": "deepseek-v4-pro",
            "thinking_enabled": False,
            "max_tokens": 512,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"content": '{"links":[],"noise":[]}'}
    assert stub_engine.generate_called is False
    assert stub_engine.generate_async_calls == [
        {
            "prompt": "Analyze these spans",
            "system_prompt": "Return JSON only",
            "max_new_tokens": 512,
            "model": "deepseek-v4-pro",
            "thinking_enabled": False,
        }
    ]


async def test_context_completion_stream_uses_async_stream_generation(fastapi_client):
    client, stub_engine = fastapi_client

    response = await client.post(
        "/chat/context-completion/stream",
        json={
            "prompt": "Analyze these spans",
            "system_prompt": "Return JSON only",
            "model": "deepseek-v4-pro",
            "thinking_enabled": False,
            "max_tokens": 512,
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    lines = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    assert lines[0] == {"type": "thinking", "content": "reasoning"}
    assert lines[1] == {"type": "token", "content": '{"links":[],"noise":[]}'}
    assert lines[2] == {"type": "result", "data": {"answer": '{"links":[],"noise":[]}'}}
    assert stub_engine.generate_stream_async_calls == [
        {
            "prompt": "Analyze these spans",
            "system_prompt": "Return JSON only",
            "max_new_tokens": 512,
            "model": "deepseek-v4-pro",
            "thinking_enabled": False,
        }
    ]
