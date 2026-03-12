import pytest

import backend_inference.main as inference_main


class _StubModelEngine:
    def __init__(self):
        self.load_model_calls = 0

    def load_model(self):
        self.load_model_calls += 1


class _StubClassificationEngine:
    def __init__(self):
        self.load_calls = 0

    def load(self):
        self.load_calls += 1


class _StubLoop:
    def __init__(self, previous_handler=None):
        self.previous_handler = previous_handler
        self.installed_handler = None
        self.default_calls = []

    def get_exception_handler(self):
        return self.previous_handler

    def set_exception_handler(self, handler):
        self.installed_handler = handler

    def default_exception_handler(self, context):
        self.default_calls.append(context)


@pytest.mark.asyncio
async def test_lifespan_initializes_remote_providers_even_when_skip_model_load_enabled(
    monkeypatch,
):
    generation_engine = _StubModelEngine()
    classification_engine = _StubClassificationEngine()

    monkeypatch.setattr(inference_main, "model_engine", generation_engine)
    monkeypatch.setattr(inference_main, "classification_engine", classification_engine)
    monkeypatch.setattr(inference_main.settings, "SKIP_MODEL_LOAD", True)
    monkeypatch.setattr(inference_main.settings, "SKIP_KB_LOAD", True)
    monkeypatch.setattr(inference_main.settings, "MODEL_PROVIDER", "deepseek")
    monkeypatch.setattr(inference_main.settings, "CLASSIFICATION_PROVIDER", "deepseek")

    async with inference_main.lifespan(inference_main.app):
        pass

    assert generation_engine.load_model_calls == 1
    assert classification_engine.load_calls == 1


@pytest.mark.asyncio
async def test_lifespan_skips_local_provider_when_skip_model_load_enabled(monkeypatch):
    generation_engine = _StubModelEngine()
    classification_engine = _StubClassificationEngine()

    monkeypatch.setattr(inference_main, "model_engine", generation_engine)
    monkeypatch.setattr(inference_main, "classification_engine", classification_engine)
    monkeypatch.setattr(inference_main.settings, "SKIP_MODEL_LOAD", True)
    monkeypatch.setattr(inference_main.settings, "SKIP_KB_LOAD", True)
    monkeypatch.setattr(inference_main.settings, "MODEL_PROVIDER", "local")
    monkeypatch.setattr(inference_main.settings, "CLASSIFICATION_PROVIDER", "local")

    async with inference_main.lifespan(inference_main.app):
        pass

    assert generation_engine.load_model_calls == 0
    assert classification_engine.load_calls == 0


def test_install_windows_asyncio_noise_filter_suppresses_known_10054_noise(monkeypatch):
    previous_calls = []

    def _previous_handler(loop, context):
        previous_calls.append((loop, context))

    loop = _StubLoop(previous_handler=_previous_handler)
    monkeypatch.setattr(inference_main.sys, "platform", "win32")
    monkeypatch.setattr(inference_main.asyncio, "get_running_loop", lambda: loop)

    restore = inference_main._install_windows_asyncio_noise_filter()

    assert restore is not None
    assert loop.installed_handler is not None

    noise_context = {
        "message": "Exception in callback _ProactorBasePipeTransport._call_connection_lost(None)",
        "handle": "<Handle _ProactorBasePipeTransport._call_connection_lost(None)>",
        "exception": ConnectionResetError(10054, "connection reset"),
    }
    noise_context["exception"].winerror = 10054

    loop.installed_handler(loop, noise_context)

    assert previous_calls == []


def test_install_windows_asyncio_noise_filter_preserves_other_asyncio_errors(monkeypatch):
    previous_calls = []

    def _previous_handler(loop, context):
        previous_calls.append((loop, context))

    loop = _StubLoop(previous_handler=_previous_handler)
    monkeypatch.setattr(inference_main.sys, "platform", "win32")
    monkeypatch.setattr(inference_main.asyncio, "get_running_loop", lambda: loop)

    restore = inference_main._install_windows_asyncio_noise_filter()

    assert restore is not None
    assert loop.installed_handler is not None

    normal_context = {
        "message": "Exception in callback some_other_callback()",
        "handle": "<Handle some_other_callback()>",
        "exception": ConnectionResetError(10054, "connection reset"),
    }
    normal_context["exception"].winerror = 10054

    loop.installed_handler(loop, normal_context)

    assert previous_calls == [(loop, normal_context)]
