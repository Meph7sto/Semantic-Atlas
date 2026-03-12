from __future__ import annotations

import importlib
from pathlib import Path
import shutil
import uuid


def test_build_targets_sets_requirement_graph_destination_to_data_model(monkeypatch):
    download_models = importlib.import_module("deploy.download_models")
    monkeypatch.delenv("MODEL_DATA_DIR", raising=False)
    monkeypatch.delenv("REQUIREMENT_GRAPH_EMBEDDING_DIR", raising=False)

    targets = {target.key: target for target in download_models._build_targets()}

    requirement_graph_target = targets["requirement-graph"]
    assert requirement_graph_target.destination_dir == (
        download_models.ROOT_DIR / "data" / "model" / "requirement_graph_embedding"
    ).resolve()


def test_resolve_model_source_downloads_requirement_graph_into_destination(monkeypatch):
    download_models = importlib.import_module("deploy.download_models")
    destination_dir = (
        download_models.ROOT_DIR
        / "data"
        / "model"
        / f"test_download_models_{uuid.uuid4().hex}"
    )
    shutil.rmtree(destination_dir, ignore_errors=True)

    captured = {}

    def fake_snapshot_download(*, repo_id, local_dir, **kwargs):
        captured["repo_id"] = repo_id
        captured["local_dir"] = local_dir
        local_path = Path(local_dir)
        local_path.mkdir(parents=True, exist_ok=True)
        (local_path / "modules.json").write_text("{}", encoding="utf-8")
        return str(local_path)

    huggingface_hub = importlib.import_module("huggingface_hub")
    monkeypatch.setattr(huggingface_hub, "snapshot_download", fake_snapshot_download)

    resolved = download_models._resolve_model_source(
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        destination_dir=destination_dir,
    )

    assert captured["repo_id"] == "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    assert Path(captured["local_dir"]) == destination_dir
    assert Path(resolved) == destination_dir

    shutil.rmtree(destination_dir, ignore_errors=True)
