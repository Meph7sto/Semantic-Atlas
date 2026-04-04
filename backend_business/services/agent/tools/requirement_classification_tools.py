"""Requirement classification agent tool definitions and execution helpers."""

from __future__ import annotations

import json
from typing import Any, Callable

import requests

from backend_business.config import settings
from backend_business.services.requirements_manage_service import RequirementsManageService


_LIST_ITEM_EXCERPT_LENGTH = 180
_VALID_LEVELS = {"L1", "L2", "L3", "L4"}
_VALID_NATURES = {"functional", "non_functional"}
_VALID_PRIORITIES = {"P0", "P1", "P2", "P3"}
_NON_FUNCTIONAL_LABELS = {
    "性能需求",
    "安全需求",
    "可靠性需求",
    "可用性需求",
    "兼容性需求",
    "可维护性需求",
    "其他",
}


def _normalize_requirement_id(requirement_id: Any) -> str:
    normalized = str(requirement_id or "").strip()
    if not normalized:
        raise ValueError("requirement_id 不能为空")
    return normalized


def _normalize_window_arg(value: Any, *, default: int, field_name: str) -> int:
    if value is None:
        normalized = default
    else:
        normalized = int(value)
    if normalized < 1:
        raise ValueError(f"{field_name} 必须大于等于 1")
    if field_name == "count" and normalized > 20:
        raise ValueError("count 不能大于 20")
    return normalized


def _collapse_excerpt(text: Any) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    single_line = " ".join(raw.split())
    if len(single_line) <= _LIST_ITEM_EXCERPT_LENGTH:
        return single_line
    return f"{single_line[:_LIST_ITEM_EXCERPT_LENGTH - 3]}..."


def _summarize_list_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "requirement_id": item.get("req_id"),
        "title": item.get("title"),
        "status": item.get("status"),
        "priority": item.get("priority"),
        "parent_id": item.get("parent_id"),
        "order_index": item.get("order_index"),
        "source_level": item.get("source_level"),
        "requirement_type": item.get("requirement_type"),
        "description_excerpt": _collapse_excerpt(item.get("description")),
    }


def _requirement_detail(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "requirement_id": item.get("req_id"),
        "title": item.get("title"),
        "status": item.get("status"),
        "priority": item.get("priority"),
        "parent_id": item.get("parent_id"),
        "order_index": item.get("order_index"),
        "requirement_type": item.get("requirement_type"),
        "source_level": item.get("source_level"),
        "description": item.get("description") or "",
        "acceptance_criteria": item.get("acceptance_criteria") or "",
        "notes": item.get("notes") or "",
        "tags": item.get("tags") or [],
    }


def _extract_first_json_object(text: str) -> dict[str, Any] | None:
    stripped = str(text or "").strip()
    if not stripped:
        return None
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _default_classify_texts(texts: list[str]) -> dict[str, Any]:
    response = requests.post(
        f"{settings.INFERENCE_BASE_URL}/classification/predict-texts",
        json={"requirements": texts},
        timeout=120,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("分类服务返回格式无效")
    return payload


class RequirementClassificationTools:
    """Requirement classification tool definitions and execution."""

    def __init__(
        self,
        *,
        requirements_service: RequirementsManageService,
        classify_texts_fn: Callable[[list[str]], dict[str, Any]] | None = None,
        chat_completion_fn: Callable[..., dict[str, Any]] | None = None,
    ) -> None:
        self.requirements_service = requirements_service
        self._classify_texts_fn = classify_texts_fn or _default_classify_texts
        self._chat_completion_fn = chat_completion_fn

    @staticmethod
    def get_tools_list() -> list[dict[str, Any]]:
        window_properties = {
            "start_index": {
                "type": "integer",
                "minimum": 1,
                "default": 1,
                "description": "1-based 起始位置",
            },
            "count": {
                "type": "integer",
                "minimum": 1,
                "maximum": 20,
                "default": 10,
                "description": "窗口大小，默认 10，最大 20",
            },
        }
        return [
            {
                "type": "function",
                "function": {
                    "name": "list_requirements",
                    "description": "列出当前项目的需求（分页窗口），返回摘要信息。",
                    "parameters": {
                        "type": "object",
                        "properties": window_properties,
                        "required": [],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_requirements",
                    "description": "在当前项目内按关键词搜索需求，用于定位目标需求。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "keyword": {
                                "type": "string",
                                "description": "非空搜索关键词，匹配需求 ID、标题、描述",
                            },
                            **window_properties,
                        },
                        "required": ["keyword"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_requirement_detail",
                    "description": "获取单条需求的完整内容，用于后续分类判断。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "requirement_id": {
                                "type": "string",
                                "description": "需求 ID",
                            }
                        },
                        "required": ["requirement_id"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "classify_requirement",
                    "description": (
                        "对指定需求执行四维分类，返回 level、功能/非功能、领域标签、优先级初判。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "requirement_id": {
                                "type": "string",
                                "description": "待分类的需求 ID",
                            }
                        },
                        "required": ["requirement_id"],
                        "additionalProperties": False,
                    },
                },
            },
        ]

    def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any] | str | None,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        parsed_arguments = self._parse_arguments(arguments)
        if tool_name == "list_requirements":
            return self._execute_list_requirements(parsed_arguments, context)
        if tool_name == "search_requirements":
            return self._execute_search_requirements(parsed_arguments, context)
        if tool_name == "get_requirement_detail":
            return self._execute_get_requirement_detail(parsed_arguments, context)
        if tool_name == "classify_requirement":
            return self._execute_classify_requirement(parsed_arguments, context)
        raise ValueError(f"未知工具: {tool_name}")

    @staticmethod
    def _parse_arguments(arguments: dict[str, Any] | str | None) -> dict[str, Any]:
        if arguments is None:
            return {}
        if isinstance(arguments, dict):
            return dict(arguments)
        if isinstance(arguments, str):
            text = arguments.strip()
            if not text:
                return {}
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                raise ValueError("tool arguments 必须是对象")
            return parsed
        raise ValueError("tool arguments 格式无效")

    def _resolve_project_requirement(
        self,
        *,
        project_id: str,
        requirement_id: str,
    ) -> dict[str, Any]:
        requirement = self.requirements_service.get_requirement(requirement_id)
        if not requirement or requirement.get("deleted"):
            raise ValueError(f"需求 {requirement_id} 不存在或已删除")
        if requirement.get("project_id") != project_id:
            raise ValueError(f"需求 {requirement_id} 不属于当前项目")
        return requirement

    def _execute_list_requirements(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        start_index = _normalize_window_arg(
            arguments.get("start_index"), default=1, field_name="start_index"
        )
        count = _normalize_window_arg(arguments.get("count"), default=10, field_name="count")
        window = self.requirements_service.list_requirements_window(
            project_id=context["project_id"],
            start_index=start_index,
            count=count,
            include_deleted=False,
        )
        items = [_summarize_list_item(item) for item in window.get("items") or []]
        return {
            "total": window["total"],
            "start_index": window["start_index"],
            "count": window["count"],
            "has_more": window["has_more"],
            "items": items,
        }

    def _execute_search_requirements(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        keyword = str(arguments.get("keyword") or "").strip()
        if not keyword:
            raise ValueError("keyword 不能为空")
        start_index = _normalize_window_arg(
            arguments.get("start_index"), default=1, field_name="start_index"
        )
        count = _normalize_window_arg(arguments.get("count"), default=10, field_name="count")
        window = self.requirements_service.search_requirements(
            project_id=context["project_id"],
            keyword=keyword,
            start_index=start_index,
            count=count,
            include_deleted=False,
        )
        items = [_summarize_list_item(item) for item in window.get("items") or []]
        return {
            "total": window.get("total", 0),
            "start_index": window.get("start_index", start_index),
            "count": window.get("count", count),
            "has_more": window.get("has_more", False),
            "keyword": keyword,
            "items": items,
        }

    def _execute_get_requirement_detail(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        requirement_id = _normalize_requirement_id(arguments.get("requirement_id"))
        requirement = self._resolve_project_requirement(
            project_id=context["project_id"],
            requirement_id=requirement_id,
        )
        return _requirement_detail(requirement)

    def _execute_classify_requirement(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        requirement_id = _normalize_requirement_id(arguments.get("requirement_id"))
        requirement = self._resolve_project_requirement(
            project_id=context["project_id"],
            requirement_id=requirement_id,
        )
        base_level = self._infer_level_from_fields(requirement)
        requirement_text = self._build_requirement_text(requirement)
        raw_classifier_label = self._classify_requirement_nature(requirement_text)
        llm_result = self._complete_dimensions_with_llm(
            requirement=requirement,
            requirement_text=requirement_text,
            base_level=base_level,
            raw_classifier_label=raw_classifier_label,
        )
        return self._normalize_classification_result(
            requirement=requirement,
            llm_result=llm_result,
            raw_classifier_label=raw_classifier_label,
            base_level=base_level,
        )

    @staticmethod
    def _infer_level_from_fields(requirement: dict[str, Any]) -> str | None:
        source_level = str(requirement.get("source_level") or "").strip().upper()
        if source_level in _VALID_LEVELS:
            return source_level
        if requirement.get("requirement_type") == "low_level":
            return "L4"
        return None

    def _classify_requirement_nature(self, requirement_text: str) -> str | None:
        payload = self._classify_texts_fn([requirement_text]) or {}
        predictions = payload.get("predictions") or []
        if not predictions:
            return None
        predicted = predictions[0].get("predicted_label")
        if predicted is None:
            return None
        return str(predicted).strip() or None

    def _complete_dimensions_with_llm(
        self,
        *,
        requirement: dict[str, Any],
        requirement_text: str,
        base_level: str | None,
        raw_classifier_label: str | None,
    ) -> dict[str, Any]:
        if not callable(self._chat_completion_fn):
            raise ValueError("chat_completion_fn 未配置")

        prompt_payload = {
            "requirement_id": requirement.get("req_id"),
            "title": requirement.get("title"),
            "description": requirement.get("description") or "",
            "acceptance_criteria": requirement.get("acceptance_criteria") or "",
            "notes": requirement.get("notes") or "",
            "requirement_type": requirement.get("requirement_type"),
            "source_level": requirement.get("source_level"),
            "current_priority": requirement.get("priority"),
            "base_level": base_level,
            "raw_classifier_label": raw_classifier_label,
            "task": "输出 level、requirement_nature、domain_tags、priority_suggestion、reasoning、evidence 的 JSON。",
        }
        response = self._chat_completion_fn(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是需求分类专家。"
                        "必须严格输出 JSON 对象。"
                        "level 只能是 L1/L2/L3/L4。"
                        "requirement_nature 只能是 functional 或 non_functional。"
                        "priority_suggestion 只能是 P0/P1/P2/P3。"
                        "domain_tags 必须是 1 到 3 个字符串。"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "context": prompt_payload,
                            "requirement_text": requirement_text,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            temperature=0.0,
            max_tokens=600,
        )
        content = ""
        if isinstance(response, dict):
            content = str(response.get("content") or "")
        payload = _extract_first_json_object(content)
        if payload is None:
            raise ValueError("LLM 分类结果不是有效 JSON")
        return payload

    def _normalize_classification_result(
        self,
        *,
        requirement: dict[str, Any],
        llm_result: dict[str, Any],
        raw_classifier_label: str | None,
        base_level: str | None,
    ) -> dict[str, Any]:
        level = base_level or str(llm_result.get("level") or "").strip().upper()
        if level not in _VALID_LEVELS:
            raise ValueError("level 必须是 L1/L2/L3/L4 之一")

        inferred_nature = self._nature_from_classifier_label(raw_classifier_label)
        requirement_nature = str(
            llm_result.get("requirement_nature") or inferred_nature or ""
        ).strip().lower()
        if requirement_nature not in _VALID_NATURES:
            raise ValueError("requirement_nature 必须是 functional 或 non_functional")

        priority_suggestion = str(llm_result.get("priority_suggestion") or "").strip().upper()
        if priority_suggestion not in _VALID_PRIORITIES:
            raise ValueError("priority_suggestion 必须是 P0/P1/P2/P3 之一")

        domain_tags = llm_result.get("domain_tags")
        if not isinstance(domain_tags, list):
            raise ValueError("domain_tags 必须是字符串数组")
        normalized_domain_tags = []
        for item in domain_tags:
            text = str(item or "").strip()
            if text:
                normalized_domain_tags.append(text)
        if not 1 <= len(normalized_domain_tags) <= 3:
            raise ValueError("domain_tags 必须包含 1 到 3 个标签")

        reasoning = str(llm_result.get("reasoning") or "").strip()
        if not reasoning:
            raise ValueError("reasoning 不能为空")

        evidence = llm_result.get("evidence") or []
        if isinstance(evidence, str):
            evidence_list = [evidence]
        elif isinstance(evidence, list):
            evidence_list = [str(item).strip() for item in evidence if str(item).strip()]
        else:
            raise ValueError("evidence 必须是字符串或字符串数组")

        return {
            "requirement_id": requirement.get("req_id"),
            "title": requirement.get("title"),
            "level": level,
            "requirement_nature": requirement_nature,
            "domain_tags": normalized_domain_tags,
            "priority_suggestion": priority_suggestion,
            "reasoning": reasoning,
            "evidence": evidence_list,
            "raw_classifier_label": raw_classifier_label,
        }

    @staticmethod
    def _nature_from_classifier_label(label: str | None) -> str | None:
        normalized = str(label or "").strip()
        if not normalized:
            return None
        if normalized == "功能性需求":
            return "functional"
        if normalized in _NON_FUNCTIONAL_LABELS:
            return "non_functional"
        return None

    @staticmethod
    def _build_requirement_text(requirement: dict[str, Any]) -> str:
        parts = []
        title = str(requirement.get("title") or "").strip()
        if title:
            parts.append(f"标题: {title}")
        description = str(requirement.get("description") or "").strip()
        if description:
            parts.append(f"描述: {description}")
        acceptance = str(requirement.get("acceptance_criteria") or "").strip()
        if acceptance:
            parts.append(f"验收标准: {acceptance}")
        notes = str(requirement.get("notes") or "").strip()
        if notes:
            parts.append(f"备注: {notes}")
        return "\n".join(parts)
