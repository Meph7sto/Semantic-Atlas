import json

from backend_business.services.ai_proxy import AIProxy


class _FakeStreamResponse:
    def __init__(self, status_code=200, lines=None):
        self.status_code = status_code
        self._lines = lines or []

    def raise_for_status(self):
        return None

    def iter_lines(self, decode_unicode=False):
        for line in self._lines:
            yield line if decode_unicode else line.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeAsyncContent:
    def __init__(self, chunks):
        self._chunks = chunks

    async def iter_chunked(self, _size):
        for chunk in self._chunks:
            yield chunk


class _FakeAsyncStreamResponse:
    def __init__(self, status=200, chunks=None):
        self.status = status
        self.content = _FakeAsyncContent(chunks or [])

    def raise_for_status(self):
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeAsyncSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        return self.response


def test_context_builder_completion_stream_returns_final_answer(monkeypatch):
    proxy = AIProxy("http://localhost:8000")
    lines = [
        json.dumps({"type": "thinking", "content": "..."}) + "\n",
        json.dumps({"type": "token", "content": "{\"links\":"}) + "\n",
        json.dumps({"type": "token", "content": "[],\"noise\":[]}"}) + "\n",
        json.dumps(
            {"type": "result", "data": {"answer": "{\"links\":[],\"noise\":[]}"}}
        )
        + "\n",
    ]

    def _fake_post(url, json=None, timeout=None, stream=False):
        return _FakeStreamResponse(lines=lines)

    monkeypatch.setattr("backend_business.services.ai_proxy.requests.post", _fake_post)

    result = proxy.context_builder_completion_stream(
        prompt="test",
        system_prompt="json only",
    )

    assert result == "{\"links\":[],\"noise\":[]}"


async def test_context_builder_completion_stream_async_returns_final_answer():
    proxy = AIProxy("http://localhost:8000")
    payload = "\n".join(
        [
            json.dumps({"type": "token", "content": "{\"links\":["}),
            json.dumps({"type": "token", "content": "],\"noise\":[]}"}),
            json.dumps(
                {"type": "result", "data": {"answer": "{\"links\":[],\"noise\":[]}"}}
            ),
            "",
        ]
    ).encode("utf-8")
    session = _FakeAsyncSession(_FakeAsyncStreamResponse(chunks=[payload]))

    result = await proxy.context_builder_completion_stream_async(
        prompt="test",
        system_prompt="json only",
        session=session,
    )

    assert result == "{\"links\":[],\"noise\":[]}"
