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
