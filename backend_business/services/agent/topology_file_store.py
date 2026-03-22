"""
拓扑图文件持久化工具

每次创建 / 更新 / 删除 execution_topology_template 图时，
将图的完整 detail 以可移植 JSON 格式写入 data/拓扑图/ 目录。
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from backend_business.config import settings

logger = logging.getLogger(__name__)

_FORMAT_ID = "semantic-atlas-topology-template"
_FORMAT_VERSION = "1.0.0"


def _ensure_dir() -> str:
    """确保 data/拓扑图/ 目录存在，返回目录路径。"""
    folder = settings.TOPOLOGY_FOLDER
    os.makedirs(folder, exist_ok=True)
    return folder


def _build_portable_payload(graph_detail: dict[str, Any]) -> dict[str, Any]:
    """
    将 graph_detail（含 DB UUID）转换为可移植的 key 引用格式，
    与前端 topologyTemplateIO.js 的 buildExportPayload 保持一致。
    """
    graph = graph_detail.get("graph") or {}
    containers: list[dict[str, Any]] = graph_detail.get("containers") or []
    nodes: list[dict[str, Any]] = graph_detail.get("nodes") or []
    edges: list[dict[str, Any]] = graph_detail.get("edges") or []

    container_id_to_key: dict[str, str] = {
        c["container_id"]: c["container_key"] for c in containers if c.get("container_id")
    }
    node_id_to_key: dict[str, str] = {
        n["node_id"]: n["node_key"] for n in nodes if n.get("node_id")
    }

    from datetime import datetime, timezone

    return {
        "format": _FORMAT_ID,
        "version": _FORMAT_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "graph": {
            "name": graph.get("name") or "",
            "description": graph.get("description") or "",
            "status": "draft",
            "layout_json": graph.get("layout_json") or {},
            "meta_json": graph.get("meta_json") or {},
        },
        "containers": [
            {
                "container_key": c.get("container_key") or "",
                "label": c.get("label") or "",
                "role_type": c.get("role_type") or "agent",
                "order_index": c.get("order_index") or 0,
                "config_json": c.get("config_json") or {},
            }
            for c in containers
        ],
        "nodes": [
            {
                "node_key": n.get("node_key") or "",
                "label": n.get("label") or "",
                "node_type": n.get("node_type") or "llm",
                "role_type": n.get("role_type") or "agent",
                "container_key": container_id_to_key.get(n.get("container_id") or "") or None,
                "phase_label": n.get("phase_label") or "",
                "task_prompt": n.get("task_prompt") or "",
                "conditional_edges": n.get("conditional_edges") or [],
                "order_index": n.get("order_index") or 0,
                "config_json": n.get("config_json") or {},
                "input_schema_json": n.get("input_schema_json") or [],
            }
            for n in nodes
        ],
        "edges": [
            {
                "source_node_key": node_id_to_key.get(e.get("source_node_id") or "") or "",
                "target_node_key": node_id_to_key.get(e.get("target_node_id") or "") or "",
                "edge_type": e.get("edge_type") or "call",
                "label": e.get("label") or "",
                "condition_expr": e.get("condition_expr") or "",
                "order_index": e.get("order_index") or 0,
                "config_json": e.get("config_json") or {},
            }
            for e in edges
        ],
    }


def save_graph(graph_detail: dict[str, Any]) -> None:
    """
    将拓扑模板图序列化为 JSON 并写入 data/拓扑图/{graph_id}.json。
    只处理 graph_type == 'execution_topology_template' 的图。
    """
    graph = graph_detail.get("graph") or {}
    graph_id = graph.get("graph_id")
    if not graph_id:
        logger.warning("[topology_file_store] save_graph 收到无 graph_id 的数据，跳过")
        return

    graph_type = graph.get("graph_type") or ""
    if graph_type != "execution_topology_template":
        return

    try:
        folder = _ensure_dir()
        payload = _build_portable_payload(graph_detail)
        file_path = os.path.join(folder, f"{graph_id}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        logger.debug("[topology_file_store] 已写入 %s", file_path)
    except Exception:
        logger.exception("[topology_file_store] 写入拓扑图文件失败 graph_id=%s", graph_id)


def delete_graph_file(graph_id: str) -> None:
    """删除 data/拓扑图/{graph_id}.json（文件不存在时静默忽略）。"""
    if not graph_id:
        return
    try:
        folder = settings.TOPOLOGY_FOLDER
        file_path = os.path.join(folder, f"{graph_id}.json")
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.debug("[topology_file_store] 已删除 %s", file_path)
    except Exception:
        logger.exception("[topology_file_store] 删除拓扑图文件失败 graph_id=%s", graph_id)
