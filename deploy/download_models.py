#!/usr/bin/env python
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional helper
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(ROOT_DIR / ".env", override=False)


@dataclass(frozen=True)
class ModelTarget:
    key: str
    label: str
    model_name: str
    source_hint: str
    destination_dir: Path | None = None


def _resolve_kb_embedding_model() -> str:
    return (
        os.environ.get("KB_EMBEDDING_MODEL")
        or "sentence-transformers/all-MiniLM-L6-v2"
    )


def _resolve_requirement_graph_embedding_model() -> str:
    return (
        os.environ.get("REQUIREMENT_GRAPH_EMBEDDING_MODEL")
        or "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )


def _resolve_model_data_dir() -> Path:
    raw_value = os.environ.get("MODEL_DATA_DIR") or "data/model"
    candidate = Path(raw_value)
    if not candidate.is_absolute():
        candidate = ROOT_DIR / candidate
    return candidate.resolve()


def _resolve_requirement_graph_embedding_dir() -> Path:
    raw_value = (
        os.environ.get("REQUIREMENT_GRAPH_EMBEDDING_DIR")
        or str(_resolve_model_data_dir() / "requirement_graph_embedding")
    )
    candidate = Path(raw_value)
    if not candidate.is_absolute():
        candidate = ROOT_DIR / candidate
    return candidate.resolve()


def _build_targets() -> list[ModelTarget]:
    return [
        ModelTarget(
            key="kb",
            label="知识库检索 embedding",
            model_name=_resolve_kb_embedding_model(),
            source_hint="backend_inference/services/kb_service",
        ),
        ModelTarget(
            key="requirement-graph",
            label="需求图谱相似关系 embedding",
            model_name=_resolve_requirement_graph_embedding_model(),
            source_hint="backend_business/services/requirement_graph",
            destination_dir=_resolve_requirement_graph_embedding_dir(),
        ),
    ]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="预下载 Semantic-Atlas 运行期会用到的 HuggingFace / sentence-transformers 模型。",
    )
    parser.add_argument(
        "--target",
        dest="targets",
        action="append",
        choices=["kb", "requirement-graph", "all"],
        help="只下载指定目标；可重复传入，默认下载全部。",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        help="可选，显式指定 sentence-transformers 缓存目录。",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="仅输出当前会下载的模型，不执行下载。",
    )
    return parser.parse_args()


def _select_targets(all_targets: Iterable[ModelTarget], requested: list[str] | None) -> list[ModelTarget]:
    targets = list(all_targets)
    if not requested or "all" in requested:
        return targets
    requested_set = set(requested)
    return [target for target in targets if target.key in requested_set]


def _configure_cache_dir(cache_dir: Path | None) -> Path | None:
    if cache_dir is None:
        return None
    resolved = cache_dir.resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", str(resolved))
    os.environ.setdefault("HF_HOME", str(resolved))
    return resolved


def _resolve_model_source(
    model_name: str,
    *,
    destination_dir: Path | None,
) -> str:
    candidate = Path(model_name)
    if candidate.exists():
        return str(candidate.resolve())

    if destination_dir is None:
        return model_name

    from huggingface_hub import snapshot_download

    destination_dir.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=model_name,
        local_dir=str(destination_dir),
    )
    return str(destination_dir)


def _download_target(target: ModelTarget, cache_dir: Path | None) -> None:
    from sentence_transformers import SentenceTransformer

    print(f"[download] {target.label}")
    print(f"           model={target.model_name}")
    print(f"           source={target.source_hint}")
    if target.destination_dir:
        print(f"           destination={target.destination_dir}")
    model_source = _resolve_model_source(
        target.model_name,
        destination_dir=target.destination_dir,
    )
    model = SentenceTransformer(
        model_source,
        cache_folder=str(cache_dir) if cache_dir else None,
    )
    # 通过一次最小编码确保模型、tokenizer 与配置都已经落到本地缓存。
    model.encode(["模型预热"], show_progress_bar=False, normalize_embeddings=True)
    print("[download] done\n")


def main() -> int:
    args = _parse_args()
    cache_dir = _configure_cache_dir(args.cache_dir)
    targets = _select_targets(_build_targets(), args.targets)

    if not targets:
        print("未匹配到任何模型目标。", file=sys.stderr)
        return 1

    print("Semantic-Atlas 模型预下载清单:")
    for target in targets:
        print(f"- {target.key}: {target.model_name} ({target.source_hint})")
        if target.destination_dir:
            print(f"  destination: {target.destination_dir}")
    if cache_dir:
        print(f"- cache_dir: {cache_dir}")
    print("")

    if args.list:
        return 0

    failures: list[tuple[ModelTarget, Exception]] = []
    seen_models: set[str] = set()
    for target in targets:
        if target.model_name in seen_models:
            print(f"[skip] {target.model_name} 已在当前批次下载过，跳过重复目标 {target.key}。\n")
            continue
        seen_models.add(target.model_name)
        try:
            _download_target(target, cache_dir)
        except Exception as exc:  # pragma: no cover - depends on local network/runtime
            failures.append((target, exc))
            print(f"[error] {target.key} 下载失败: {exc}\n", file=sys.stderr)

    if failures:
        print("以下模型下载失败:", file=sys.stderr)
        for target, exc in failures:
            print(f"- {target.key}: {target.model_name} -> {exc}", file=sys.stderr)
        return 1

    print("全部目标模型已预热完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
