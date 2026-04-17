import importlib


def _reload_config_module(monkeypatch, **env):
    managed_keys = ["MODEL_PROVIDER", "DEEPSEEK_API_KEY", "CHUTES_API_TOKEN", "CHUTES_API_KEY"]
    for key in managed_keys:
        monkeypatch.setenv(key, "")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    import backend_inference.core.config as config_module

    return importlib.reload(config_module)


def test_prefers_explicit_model_provider(monkeypatch):
    config_module = _reload_config_module(
        monkeypatch,
        MODEL_PROVIDER="local",
        DEEPSEEK_API_KEY="sk-test",
    )

    assert config_module._resolve_model_provider() == "local"
    assert config_module.Settings.MODEL_PROVIDER == "local"


def test_defaults_to_deepseek_when_api_key_exists(monkeypatch):
    config_module = _reload_config_module(
        monkeypatch,
        DEEPSEEK_API_KEY="sk-test",
    )

    assert config_module._resolve_model_provider() == "deepseek"
    assert config_module.Settings.MODEL_PROVIDER == "deepseek"


def test_defaults_to_chutes_when_token_exists(monkeypatch):
    config_module = _reload_config_module(
        monkeypatch,
        CHUTES_API_TOKEN="token-test",
    )

    assert config_module._resolve_model_provider() == "chutes"
    assert config_module.Settings.MODEL_PROVIDER == "chutes"


def test_falls_back_to_local_without_remote_credentials(monkeypatch):
    config_module = _reload_config_module(monkeypatch)

    assert config_module._resolve_model_provider() == "local"
    assert config_module.Settings.MODEL_PROVIDER == "local"
