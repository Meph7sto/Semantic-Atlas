import asyncio
import json
from logging import Logger
from typing import Any, Callable, Dict, List, Optional

import aiohttp

from .helpers import _extract_json_payload


class _RelationDiscoveryToolDef:
    @classmethod
    def get_tool_schema(cls) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "submit_discovered_requirement_relations",
                "description": "主动发现输入包内需求节点之间除 REFINES 外的需求关系。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "relations": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "source": {"type": "string"},
                                    "target": {"type": "string"},
                                    "type": {
                                        "type": "string",
                                        "enum": [
                                            "DEPENDS_ON",
                                            "CONFLICTS_WITH",
                                            "INCLUDES",
                                            "EXTENDS",
                                            "IMPACTS",
                                            "VALIDATES_WITH",
                                            "SIMILAR_TO",
                                        ],
                                    },
                                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                                    "reason": {"type": "string"},
                                    "evidence": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                },
                                "required": [
                                    "source",
                                    "target",
                                    "type",
                                    "confidence",
                                    "reason",
                                    "evidence",
                                ],
                                "additionalProperties": False,
                            },
                        }
                    },
                    "required": ["relations"],
                    "additionalProperties": False,
                },
            },
        }

    @classmethod
    def get_system_prompt(cls, relation_types: List[str]) -> str:
        return (
            "你是需求关系发现器。"
            "输入包包含一个 L1/L2/L3 顶层需求、它关联的全部 L4 底层需求，以及已知 REFINES 追溯关系。"
            "你必须主动发现包内仍缺失的非追溯需求关系。"
            "只能使用输入包内节点 id，不能创建节点，不能引用包外节点。"
            "不能输出 REFINES，不能修改、删除或覆盖已知追溯/细化关系。"
            "只允许输出这些关系类型："
            f"{relation_types}。"
            "证据不足时不要输出关系。"
            "必须调用 submit_discovered_requirement_relations 工具输出。"
        )


class _RequirementGraphRelationDiscoveryCoordinator:
    def __init__(
        self,
        *,
        ai: Any,
        logger: Logger,
        clean: Callable[[Any], Optional[str]],
        edge_label: Callable[[str], str],
        normalize_edge_key: Callable[[Any, Any, Any], tuple[str, str, str]],
        resolve_node_reference: Callable[[Any, set[str]], Optional[str]],
        as_list: Callable[[Any], List[Any]],
        compact_list: Callable[[List[Any]], List[str]],
        float_or_default: Callable[[Any, float], float],
        allowed_relation_types: set[str],
        symmetric_edge_types: set[str],
    ) -> None:
        self.ai = ai
        self.logger = logger
        self.clean = clean
        self.edge_label = edge_label
        self.normalize_edge_key = normalize_edge_key
        self.resolve_node_reference = resolve_node_reference
        self.as_list = as_list
        self.compact_list = compact_list
        self.float_or_default = float_or_default
        self.allowed_relation_types = allowed_relation_types
        self.symmetric_edge_types = symmetric_edge_types

    def build_package(
        self,
        *,
        package_id: str,
        top_requirement: Dict[str, Any],
        l4_requirements: List[Dict[str, Any]],
        known_refines: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        top_node_id = top_requirement["node_id"]
        l4_items = [
            {
                "id": item["node_id"],
                "req_id": item.get("req_id"),
                "text": item.get("text") or "",
                "component": item.get("component"),
                "acceptance_criteria": self.as_list(item.get("acceptance_criteria")),
                "test_method": item.get("test_method"),
                "interfaces": self.as_list(item.get("interfaces")),
                "data_contracts": self.as_list(item.get("data_contracts")),
                "error_handling": self.as_list(item.get("error_handling")),
                "nfr": self.as_list(item.get("nfr")),
                "open_questions": self.as_list(item.get("open_questions")),
            }
            for item in l4_requirements
        ]
        payload = {
            "package_id": package_id,
            "top_requirement": {
                "id": top_node_id,
                "req_id": top_requirement.get("req_id"),
                "level": top_requirement.get("level"),
                "text": top_requirement.get("text") or "",
            },
            "l4_requirements": l4_items,
            "known_refines": known_refines,
            "allowed_relation_types": sorted(self.allowed_relation_types),
        }
        payload["node_ids"] = [top_node_id, *[item["id"] for item in l4_items]]
        return payload

    def estimate_prompt_chars(self, package: Dict[str, Any]) -> int:
        return len(json.dumps(package, ensure_ascii=False)) + 1200

    async def review_packages_as_completed(
        self,
        packages: List[Dict[str, Any]],
        *,
        model: str,
        review_concurrency: int,
    ):
        if not packages or self.ai is None:
            return
        concurrency = max(1, min(int(review_concurrency or 1), len(packages)))
        semaphore = asyncio.Semaphore(concurrency)
        connector = aiohttp.TCPConnector(limit=max(6, len(packages) * 2))
        async with aiohttp.ClientSession(connector=connector) as session:
            async def _run(package):
                try:
                    result = await self._review_package(
                        package,
                        model=model,
                        session=session,
                        semaphore=semaphore,
                    )
                    return package, result
                except Exception as exc:
                    return package, exc

            tasks = [asyncio.create_task(_run(package)) for package in packages]
            for task in asyncio.as_completed(tasks):
                yield await task

    async def _review_package(
        self,
        package: Dict[str, Any],
        *,
        model: str,
        session: aiohttp.ClientSession,
        semaphore: asyncio.Semaphore,
    ) -> Dict[str, Any]:
        async with semaphore:
            user_prompt = "请发现当前输入包内缺失的非 REFINES 需求关系。\n输入包：\n" + json.dumps(
                package,
                ensure_ascii=False,
            )
            if hasattr(self.ai, "chat_completion_with_tools_async"):
                response = await self.ai.chat_completion_with_tools_async(
                    messages=[
                        {
                            "role": "system",
                            "content": _RelationDiscoveryToolDef.get_system_prompt(
                                sorted(self.allowed_relation_types)
                            ),
                        },
                        {"role": "user", "content": user_prompt},
                    ],
                    tools=[_RelationDiscoveryToolDef.get_tool_schema()],
                    model=model,
                    temperature=0.1,
                    max_tokens=5000,
                    tool_choice="required",
                    session=session,
                )
            elif hasattr(self.ai, "chat_completion"):
                response = self.ai.chat_completion(
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                _RelationDiscoveryToolDef.get_system_prompt(
                                    sorted(self.allowed_relation_types)
                                )
                                + '\n只返回严格 JSON：{"relations":[...]}，不要输出额外说明。'
                            ),
                        },
                        {"role": "user", "content": user_prompt},
                    ],
                    model=model,
                    temperature=0.1,
                    max_tokens=5000,
                )
            else:
                response = {"relations": []}
        return {
            "package_id": package["package_id"],
            "relations": self.parse_response(response, package),
        }

    def parse_response(self, response: Dict[str, Any], package: Dict[str, Any]) -> List[Dict[str, Any]]:
        raw_relations: List[Any] = []
        tool_calls = response.get("tool_calls") if isinstance(response, dict) else []
        if isinstance(tool_calls, list):
            for call in tool_calls:
                if not isinstance(call, dict) or call.get("type") != "function":
                    continue
                function_payload = call.get("function") or {}
                if function_payload.get("name") != "submit_discovered_requirement_relations":
                    continue
                arguments = function_payload.get("arguments") or {}
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        continue
                if isinstance(arguments, dict):
                    raw_relations.extend(arguments.get("relations") or [])

        if not raw_relations and isinstance(response, dict):
            if isinstance(response.get("relations"), list):
                raw_relations = response.get("relations") or []
            else:
                parsed = _extract_json_payload(response.get("content") or "")
                if isinstance(parsed, dict):
                    raw_relations = parsed.get("relations") or []

        deduped: Dict[tuple[str, str, str], Dict[str, Any]] = {}
        valid_node_ids = set(package.get("node_ids") or [])
        for item in raw_relations if isinstance(raw_relations, list) else []:
            normalized = self._normalize_relation(item, valid_node_ids)
            if not normalized:
                continue
            key = self.normalize_edge_key(
                normalized["source"],
                normalized["target"],
                normalized["type"],
            )
            current = deduped.get(key)
            if not current or self._relation_quality(normalized) > self._relation_quality(current):
                deduped[key] = normalized
        return list(deduped.values())

    def _normalize_relation(
        self,
        raw_relation: Any,
        valid_node_ids: set[str],
    ) -> Optional[Dict[str, Any]]:
        if not isinstance(raw_relation, dict):
            return None
        source = self.resolve_node_reference(raw_relation.get("source"), valid_node_ids)
        target = self.resolve_node_reference(raw_relation.get("target"), valid_node_ids)
        edge_type = self.clean(raw_relation.get("type"))
        if (
            not source
            or not target
            or source == target
            or not edge_type
            or edge_type == "REFINES"
            or edge_type not in self.allowed_relation_types
        ):
            return None
        if edge_type in self.symmetric_edge_types and source > target:
            source, target = target, source
        return {
            "source": source,
            "target": target,
            "type": edge_type,
            "confidence": max(
                0.0,
                min(1.0, self.float_or_default(raw_relation.get("confidence"), 0.65)),
            ),
            "reason": self.clean(raw_relation.get("reason")) or "",
            "evidence": self.compact_list(self.as_list(raw_relation.get("evidence")))[:8],
        }

    @staticmethod
    def _relation_quality(relation: Dict[str, Any]) -> tuple[float, int]:
        return (
            float(relation.get("confidence") or 0),
            len(relation.get("evidence") or []),
        )
