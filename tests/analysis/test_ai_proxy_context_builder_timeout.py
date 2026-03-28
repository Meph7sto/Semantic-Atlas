import aiohttp
import asyncio
import pytest

from backend_business.services.ai_proxy import AIProxy


class _FakeSyncResponse:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {"content": '{"links":[],"noise":[]}'}


class _FakeAsyncResponse:
    status = 200

    def raise_for_status(self):
        return None

    async def json(self):
        return {"content": '{"links":[],"noise":[]}'}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        return _FakeAsyncResponse()


class _RetryAsyncResponse:
    status = 200

    def raise_for_status(self):
        return None

    async def json(self):
        return {"content": "ok"}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _TimeoutThenSuccessResponse:
    def __init__(self):
        self.enter_count = 0

    async def __aenter__(self):
        self.enter_count += 1
        if self.enter_count == 1:
            raise asyncio.TimeoutError()
        return _RetryAsyncResponse()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _StatusErrorResponse:
    def __init__(self, status):
        self.status = status
        self.request_info = None
        self.history = ()

    async def __aenter__(self):
        raise aiohttp.ClientResponseError(
            request_info=self.request_info,
            history=self.history,
            status=self.status,
            message=f"http {self.status}",
        )

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _SequencedAsyncSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        return self._responses.pop(0)


def test_context_builder_requests_timeout_defaults_to_connect_only(monkeypatch):
    proxy = AIProxy("http://localhost:8000")
    calls = []

    def _fake_post(url, json=None, timeout=None):
        calls.append({"url": url, "json": json, "timeout": timeout})
        return _FakeSyncResponse()

    monkeypatch.delenv("CONTEXT_BUILDER_READ_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setattr("backend_business.services.ai_proxy.requests.post", _fake_post)

    result = proxy.context_builder_completion(
        prompt="test",
        system_prompt="json only",
    )

    assert result == '{"links":[],"noise":[]}'
    assert calls[0]["timeout"] == (30.0, None)


async def test_context_builder_async_timeout_has_no_total_and_no_read(monkeypatch):
    proxy = AIProxy("http://localhost:8000")
    session = _FakeSession()

    monkeypatch.delenv("CONTEXT_BUILDER_READ_TIMEOUT_SECONDS", raising=False)

    result = await proxy.context_builder_completion_async(
        prompt="test",
        system_prompt="json only",
        session=session,
    )

    timeout = session.calls[0]["timeout"]
    assert result == '{"links":[],"noise":[]}'
    assert isinstance(timeout, aiohttp.ClientTimeout)
    assert timeout.total is None
    assert timeout.connect == 30.0
    assert timeout.sock_connect == 30.0
    assert timeout.sock_read is None


@pytest.mark.asyncio
async def test_tools_async_timeout_retries_then_succeeds(monkeypatch):
    proxy = AIProxy("http://localhost:8000")
    session = _SequencedAsyncSession(
        [
            _TimeoutThenSuccessResponse(),
            _RetryAsyncResponse(),
        ]
    )

    monkeypatch.setenv("TOOLS_MAX_RETRIES", "2")
    monkeypatch.setenv("TOOLS_READ_TIMEOUT_SECONDS", "600")

    async def _fake_sleep(*_args, **_kwargs):
        return None

    monkeypatch.setattr("backend_business.services.ai_proxy.asyncio.sleep", _fake_sleep)

    result = await proxy.chat_completion_with_tools_async(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        session=session,
    )

    assert result == {"content": "ok"}
    assert len(session.calls) == 2
    timeout = session.calls[0]["timeout"]
    assert isinstance(timeout, aiohttp.ClientTimeout)
    assert timeout.total is None
    assert timeout.sock_read == 600.0


@pytest.mark.asyncio
async def test_tools_async_non_retryable_status_fails_fast(monkeypatch):
    proxy = AIProxy("http://localhost:8000")
    session = _SequencedAsyncSession([_StatusErrorResponse(400)])

    monkeypatch.setenv("TOOLS_MAX_RETRIES", "2")

    with pytest.raises(aiohttp.ClientResponseError) as exc_info:
        await proxy.chat_completion_with_tools_async(
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            session=session,
        )

    assert exc_info.value.status == 400
    assert len(session.calls) == 1
