"""Deterministic skill document compiler used by Phase 2 writeback."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any

from .collector import ExperienceMaterial
from .targets import ExperienceTarget

try:
    import yaml
except ImportError:  # pragma: no cover - fallback kept for minimal envs
    yaml = None


_SECTION_ORDER = (
    "适用场景",
    "推荐步骤",
    "常见陷阱",
    "结果呈现建议",
    "成功案例模式摘要",
)


@dataclass(frozen=True, slots=True)
class CompiledSkillDraft:
    """Compiled skill markdown plus parsed metadata."""

    content: str
    metadata: dict[str, Any]


class SkillCompiler:
    """Compile a new or updated markdown skill document."""

    def compile_full(
        self,
        *,
        target: ExperienceTarget,
        material: ExperienceMaterial,
        existing_skill: str | None,
        now: datetime | None = None,
    ) -> CompiledSkillDraft:
        timestamp = _normalize_datetime(now)
        existing_metadata, existing_sections = parse_skill_document(existing_skill)
        iteration = int(existing_metadata.get("iteration") or 0) + 1
        created_at = str(existing_metadata.get("created_at") or _isoformat_utc(timestamp))

        steps = self._merge_numbered_items(
            existing_sections.get("推荐步骤", []),
            self._build_recommended_steps(target=target, material=material),
        )
        pitfalls = self._merge_bullets(
            existing_sections.get("常见陷阱", []),
            self._build_pitfalls(target=target, material=material),
        )
        sections = {
            "适用场景": self._merge_bullets(
                existing_sections.get("适用场景", []),
                self._build_scenarios(target=target, material=material),
            ),
            "推荐步骤": steps,
            "常见陷阱": pitfalls,
            "结果呈现建议": self._merge_bullets(
                existing_sections.get("结果呈现建议", []),
                self._build_result_suggestions(target=target, material=material),
            ),
            "成功案例模式摘要": self._merge_bullets(
                existing_sections.get("成功案例模式摘要", []),
                self._build_success_patterns(target=target, material=material),
            ),
        }

        metadata = self._build_metadata(
            target=target,
            material=material,
            existing_metadata=existing_metadata,
            iteration=iteration,
            created_at=created_at,
            timestamp=timestamp,
        )
        return CompiledSkillDraft(
            content=render_skill_document(metadata=metadata, sections=sections),
            metadata=metadata,
        )

    def compile_shared_patterns(
        self,
        *,
        current_skills: dict[str, str],
        existing_skill: str | None,
        now: datetime | None = None,
    ) -> CompiledSkillDraft | None:
        documents = {
            str(target_id): content
            for target_id, content in current_skills.items()
            if str(target_id).strip() and str(target_id).strip() != "shared_patterns" and str(content or "").strip()
        }
        if len(documents) < 2:
            return None

        timestamp = _normalize_datetime(now)
        existing_metadata, existing_sections = parse_skill_document(existing_skill)
        shared_sections = self._extract_shared_sections(documents)
        if not any(shared_sections.get(section) for section in _SECTION_ORDER):
            return None

        iteration = int(existing_metadata.get("iteration") or 0) + 1
        metadata = {
            "skill_id": self._shared_skill_id(existing_metadata, iteration, timestamp),
            "experience_target": "shared_patterns",
            "container_key": "shared_patterns",
            "prompt_builder_kind": "shared_patterns",
            "node_type": "shared",
            "task_pattern_summary": "跨 target 复用的稳定执行模式。",
            "iteration": iteration,
            "invocation_count": int(existing_metadata.get("invocation_count") or 0),
            "injection_miss_count": int(existing_metadata.get("injection_miss_count") or 0),
            "created_at": str(
                existing_metadata.get("created_at") or _isoformat_utc(timestamp)
            ),
            "last_updated_at": _isoformat_utc(timestamp),
            "last_used_at": existing_metadata.get("last_used_at"),
            "derived_from": {
                "targets": sorted(documents.keys()),
            },
        }
        merged_sections: dict[str, list[str]] = {}
        for section in _SECTION_ORDER:
            merged_sections[section] = self._merge_bullets(
                existing_sections.get(section, []),
                shared_sections.get(section, []),
            )
        return CompiledSkillDraft(
            content=render_skill_document(metadata=metadata, sections=merged_sections),
            metadata=metadata,
        )

    def compile_pitfall_only(
        self,
        *,
        material: ExperienceMaterial,
    ) -> str:
        error_summary = _single_line(material.final_error or "执行链路失败")
        tool_names = [
            entry.get("tool_name")
            for entry in material.tool_call_trace
            if str(entry.get("tool_name") or "").strip()
        ]
        tool_hint = " -> ".join(dict.fromkeys(str(name) for name in tool_names[:3]))
        if tool_hint:
            return (
                f"在 `{tool_hint}` 链路出现 `{error_summary}` 类失败时，"
                "应先停止继续推断并回到已确认的工具结果，避免把未完成步骤写成确定性结论。"
            )
        return (
            f"当执行链路出现 `{error_summary}` 类失败时，"
            "应先收束为可解释失败原因并停止继续推断，避免输出未被证据支撑的确定性结论。"
        )

    def apply_pitfall_update(
        self,
        *,
        target: ExperienceTarget,
        material: ExperienceMaterial,
        existing_skill: str | None,
        now: datetime | None = None,
    ) -> CompiledSkillDraft:
        timestamp = _normalize_datetime(now)
        existing_metadata, existing_sections = parse_skill_document(existing_skill)
        pitfall = self.compile_pitfall_only(material=material)
        sections = dict(existing_sections)
        sections["常见陷阱"] = self._merge_bullets(
            existing_sections.get("常见陷阱", []),
            [pitfall],
        )
        for section in _SECTION_ORDER:
            sections.setdefault(section, [])

        iteration = int(existing_metadata.get("iteration") or 0) + 1
        metadata = self._build_metadata(
            target=target,
            material=material,
            existing_metadata=existing_metadata,
            iteration=iteration,
            created_at=str(
                existing_metadata.get("created_at") or _isoformat_utc(timestamp)
            ),
            timestamp=timestamp,
        )
        return CompiledSkillDraft(
            content=render_skill_document(metadata=metadata, sections=sections),
            metadata=metadata,
        )

    def _build_metadata(
        self,
        *,
        target: ExperienceTarget,
        material: ExperienceMaterial,
        existing_metadata: dict[str, Any],
        iteration: int,
        created_at: str,
        timestamp: datetime,
    ) -> dict[str, Any]:
        previous_skill_id = str(existing_metadata.get("skill_id") or "").strip()
        skill_suffix = _timestamp_for_id(timestamp)
        revision = f"{iteration:03d}"
        skill_id = (
            previous_skill_id
            if previous_skill_id.endswith(f"_{revision}")
            else f"exp_{target.target_id}_{skill_suffix}_{revision}"
        )
        return {
            "skill_id": skill_id,
            "experience_target": target.target_id,
            "container_key": target.container_key,
            "prompt_builder_kind": target.prompt_builder_kind,
            "node_type": target.node_type,
            "task_pattern_summary": self._build_pattern_summary(material),
            "iteration": iteration,
            "invocation_count": int(existing_metadata.get("invocation_count") or 0),
            "injection_miss_count": int(
                existing_metadata.get("injection_miss_count") or 0
            ),
            "created_at": created_at,
            "last_updated_at": _isoformat_utc(timestamp),
            "last_used_at": existing_metadata.get("last_used_at"),
            "derived_from": {
                "graph_id": material.graph_id,
                "subgraph_key": material.subgraph_key or None,
                "node_keys": list(material.source_node_keys),
            },
        }

    @staticmethod
    def _merge_bullets(existing: list[str], incoming: list[str]) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for raw_item in [*existing, *incoming]:
            item = _single_line(raw_item)
            if not item:
                continue
            normalized = _normalize_text(item)
            if normalized in seen:
                continue
            seen.add(normalized)
            merged.append(item)
        return merged

    @staticmethod
    def _merge_numbered_items(existing: list[str], incoming: list[str]) -> list[str]:
        merged = SkillCompiler._merge_bullets(existing, incoming)
        return merged[:6]

    @staticmethod
    def _build_pattern_summary(material: ExperienceMaterial) -> str:
        parts = [
            _single_line(material.task_description),
            _single_line(material.user_message),
        ]
        for part in parts:
            if part:
                return _truncate(part, 120)
        return f"{material.experience_target.target_id} 阶段的可复用执行经验。"

    @staticmethod
    def _build_scenarios(
        target: ExperienceTarget,
        material: ExperienceMaterial,
    ) -> list[str]:
        if target.target_id == "session_controller_decision":
            return ["适用于总控需要先判断任务路由、是否委托以及是否直接回复的决策阶段。"]
        if target.target_id.endswith("_delegate"):
            return ["适用于总控已决定委托，并需要把任务收束为单一子阶段执行目标的阶段。"]
        if target.target_id == "requirement_agent_classic":
            return ["适用于需求管理 Agent 直接通过 classic tool-loop 处理需求读写、澄清或审批的场景。"]
        if target.target_id == "conflict_detection_classic":
            return ["适用于冲突检测 Agent 在 classic tool-loop 中完成需求定位、详情读取和冲突结论输出。"]
        if target.target_id == "requirement_classification_classic":
            return ["适用于需求分类 Agent 在 classic tool-loop 中完成目标需求定位与分类结果输出。"]
        if material.task_description:
            return [
                _truncate(
                    f"当前阶段目标是：{_single_line(material.task_description)}",
                    140,
                )
            ]
        if material.user_message:
            return [
                _truncate(
                    f"用户提出的任务需要在该 target 中完成处理：{_single_line(material.user_message)}",
                    140,
                )
            ]
        return [f"适用于 {material.experience_target.target_id} 这一执行阶段。"]

    @staticmethod
    def _build_recommended_steps(
        target: ExperienceTarget,
        material: ExperienceMaterial,
    ) -> list[str]:
        if target.target_id == "session_controller_decision":
            return [
                "先判断当前任务是否需要展开拓扑、委托专项 Agent，还是可以直接回复，不要同时保留多个互相竞争的执行路径。",
                "若决定委托，先明确 delegate_agent、目标 requirement 和阶段目标，再进入 invoke 或后续阶段。",
                "若信息不足以安全决策，优先输出最小澄清问题，而不是直接假设用户意图。",
                "把最终决策收束为可执行的单一路径，并确保后续节点能直接消费该决策结果。",
            ]
        if target.target_id.endswith("_delegate"):
            return [
                "先把当前委托阶段限定为单一目标，明确要交给子 Agent 的任务范围、输入对象和期望产出。",
                "优先补齐委托前的关键上下文，例如 requirement 选择、冲突对象或分类目标，不要把缺失信息直接下沉给子 Agent。",
                "委托结果返回后先校验是否回答了当前阶段目标，再决定是继续总控流程、澄清还是挂起。",
                "最终输出保持为可供后续节点消费的结构化结论，不把中间推理铺陈成无约束长文本。",
            ]
        if target.target_id == "requirement_agent_classic":
            return [
                "先确认目标 requirement 是否已锁定；若未锁定，优先通过检索或澄清定位唯一对象。",
                "执行写操作前先读取当前详情、审批状态和相关上下文，避免在旧状态上直接修改。",
                "当出现澄清或审批分支时，立即把模式切换为 clarification 或 approval_pending，不继续假设用户已授权。",
                "最终回复同时给出处理结果、受影响 requirement 和下一步动作，便于主流程继续消费。",
            ]
        if target.target_id == "conflict_detection_classic":
            return [
                "先定位参与比较的需求集合，再读取每条需求详情，不要只凭标题或摘要判断冲突。",
                "比较时优先基于目标、约束、状态变化和互斥条件逐项对照，避免泛化为抽象风险。",
                "若证据不足以确认冲突，应明确指出缺失信息，而不是输出强结论。",
                "最终先给出是否冲突，再列出支撑证据和需要补充确认的点。",
            ]
        if target.target_id == "requirement_classification_classic":
            return [
                "先锁定目标 requirement；若上下文存在多个候选，先澄清或检索，不要默认选择其中之一。",
                "分类前先读取最新需求内容和上下文，避免依据旧版本或局部片段做判断。",
                "输出分类结果时同时说明分类依据和置信边界，便于后续流程校验。",
                "若工具结果不完整，优先收束为待确认状态，而不是伪造确定分类。",
            ]
        steps = [
            "先确认当前阶段的目标、输入对象和期望产出，再决定最小执行路径。",
        ]
        tool_names = [
            str(entry.get("tool_name") or "").strip()
            for entry in material.tool_call_trace
            if str(entry.get("tool_name") or "").strip()
        ]
        unique_tool_names = list(dict.fromkeys(tool_names))
        if unique_tool_names:
            tool_chain = " -> ".join(f"`{name}`" for name in unique_tool_names[:3])
            steps.append(
                f"优先沿 `{tool_chain}` 这一已验证链路补齐关键上下文，不要跳过前置读取步骤。"
            )
        else:
            steps.append("若缺少关键上下文，先补充读取和确认步骤，再进入结论输出。")
        steps.append("最终结论只基于已记录的工具结果、阶段结论和 scratchpad 证据，不补写未经验证的信息。")
        if material.final_conclusion:
            steps.append(
                "输出前检查结论是否覆盖关键结果、限制条件和必要的下一步动作。"
            )
        return steps[:4]

    @staticmethod
    def _build_pitfalls(
        target: ExperienceTarget,
        material: ExperienceMaterial,
    ) -> list[str]:
        pitfalls: list[str] = []
        if target.target_id == "session_controller_decision":
            pitfalls.append("不要在还未完成路由判断时同时输出直接回复和委托决策，避免把总控状态推入冲突分支。")
        elif target.target_id.endswith("_delegate"):
            pitfalls.append("不要把未确认的 requirement、冲突对象或分类目标直接下传给委托 Agent，避免下游在错误对象上执行。")
        error_results = [
            entry
            for entry in material.tool_call_trace
            if isinstance(entry.get("result"), dict)
            and entry["result"].get("is_error")
        ]
        if error_results:
            tool_name = str(error_results[0].get("tool_name") or "").strip() or "工具调用"
            pitfalls.append(
                f"当 `{tool_name}` 返回错误时，不要继续推断未验证结论，应先收束失败原因或改走补充读取路径。"
            )
        if material.final_error:
            pitfalls.append(
                f"执行出现 `{_single_line(material.final_error)}` 类失败时，不要把未完成步骤包装成已完成结果。"
            )
        if not pitfalls:
            pitfalls.append(
                "不要跳过前置读取或定位步骤，也不要把工具未返回的信息写进最终结论。"
            )
        return pitfalls

    @staticmethod
    def _build_result_suggestions(
        target: ExperienceTarget,
        material: ExperienceMaterial,
    ) -> list[str]:
        suggestions = [
            "先给出结论，再补充支撑证据或限制条件，保持表达紧凑可执行。"
        ]
        if target.target_id == "session_controller_decision":
            suggestions.append("决策结果应显式体现后续动作，例如直接回复、委托、澄清或挂起。")
        if material.runtime_status == "failed":
            suggestions.append("若阶段失败，应明确说明失败原因和阻塞点，而不是输出模糊总结。")
        return suggestions

    @staticmethod
    def _build_success_patterns(
        target: ExperienceTarget,
        material: ExperienceMaterial,
    ) -> list[str]:
        if target.target_id == "session_controller_decision":
            return ["常见成功路径是先完成任务路由，再将决策收束为单一路径并把必要上下文一并传递给后续节点。"]
        tool_names = [
            str(entry.get("tool_name") or "").strip()
            for entry in material.tool_call_trace
            if str(entry.get("tool_name") or "").strip()
        ]
        if tool_names:
            tool_chain = " -> ".join(dict.fromkeys(tool_names[:4]))
            return [f"常见成功路径是先完成 `{tool_chain}`，再基于已确认结果收束输出。"]
        if material.phase_conclusions:
            return [
                "常见成功路径是先明确阶段目标，再逐步收束为单一结论，不在中途扩散任务边界。"
            ]
        return ["常见成功路径是先补齐上下文，再给出基于证据的简洁结论。"]

    @staticmethod
    def _shared_skill_id(
        existing_metadata: dict[str, Any],
        iteration: int,
        timestamp: datetime,
    ) -> str:
        previous_skill_id = str(existing_metadata.get("skill_id") or "").strip()
        revision = f"{iteration:03d}"
        if previous_skill_id.endswith(f"_{revision}"):
            return previous_skill_id
        return f"exp_shared_patterns_{_timestamp_for_id(timestamp)}_{revision}"

    @staticmethod
    def _extract_shared_sections(
        documents: dict[str, str],
    ) -> dict[str, list[str]]:
        parsed_documents = {
            target_id: parse_skill_document(content)[1]
            for target_id, content in documents.items()
        }
        shared_sections: dict[str, list[str]] = {section: [] for section in _SECTION_ORDER}
        for section in _SECTION_ORDER:
            counts: dict[str, int] = {}
            originals: dict[str, str] = {}
            for target_sections in parsed_documents.values():
                seen_in_document: set[str] = set()
                for item in target_sections.get(section, []):
                    normalized = _normalize_text(_single_line(item))
                    if not normalized or normalized in seen_in_document:
                        continue
                    seen_in_document.add(normalized)
                    counts[normalized] = counts.get(normalized, 0) + 1
                    originals.setdefault(normalized, _single_line(item))
            shared_items = [
                originals[key]
                for key, count in counts.items()
                if count >= 2
            ]
            shared_sections[section] = shared_items[:6]
        if not shared_sections.get("适用场景"):
            shared_sections["适用场景"] = ["适用于多个 target 中反复出现的稳定执行模式。"]
        if not shared_sections.get("推荐步骤"):
            shared_sections["推荐步骤"] = [
                "先确认当前阶段目标和输入对象，再决定最小执行路径。",
                "优先复用已经被多个 target 验证过的读取、校验和收束顺序。",
                "最终只输出能被证据支撑、且能直接供后续阶段消费的结论。",
            ]
        if not shared_sections.get("常见陷阱"):
            shared_sections["常见陷阱"] = [
                "不要跳过前置读取或目标确认步骤，也不要把未验证信息写成确定结论。"
            ]
        if not shared_sections.get("结果呈现建议"):
            shared_sections["结果呈现建议"] = [
                "共享模式的输出应保持短、稳、可执行，避免夹带 target 特有细节。"
            ]
        if not shared_sections.get("成功案例模式摘要"):
            shared_sections["成功案例模式摘要"] = [
                "常见成功路径是先补齐上下文，再沿稳定的读取-校验-收束顺序输出结论。"
            ]
        return shared_sections


def parse_skill_document(content: str | None) -> tuple[dict[str, Any], dict[str, list[str]]]:
    """Parse skill front matter plus markdown list sections."""
    if not content:
        return {}, {section: [] for section in _SECTION_ORDER}

    raw_text = str(content)
    metadata: dict[str, Any] = {}
    body_text = raw_text
    if raw_text.startswith("---"):
        match = re.match(r"^---\n(.*?)\n---\n?(.*)$", raw_text, re.S)
        if match:
            raw_header = match.group(1)
            body_text = match.group(2)
            metadata = _parse_yaml_like(raw_header)

    sections: dict[str, list[str]] = {section: [] for section in _SECTION_ORDER}
    current_section = None
    for raw_line in body_text.splitlines():
        line = raw_line.rstrip()
        if line.startswith("## "):
            current_section = line[3:].strip()
            sections.setdefault(current_section, [])
            continue
        if current_section is None:
            continue
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"^\d+\.\s+", stripped):
            sections[current_section].append(re.sub(r"^\d+\.\s+", "", stripped))
            continue
        if stripped.startswith("- "):
            sections[current_section].append(stripped[2:].strip())
            continue
        sections[current_section].append(stripped)
    for section in _SECTION_ORDER:
        sections.setdefault(section, [])
    return metadata, sections


def render_skill_document(
    *,
    metadata: dict[str, Any],
    sections: dict[str, list[str]],
) -> str:
    """Render a complete skill markdown document."""
    header = _dump_yaml_like(metadata).rstrip()
    body_parts: list[str] = [f"---\n{header}\n---"]
    for section in _SECTION_ORDER:
        body_parts.append(f"\n## {section}\n")
        items = sections.get(section) or []
        if section == "推荐步骤":
            for index, item in enumerate(items, start=1):
                body_parts.append(f"{index}. {_single_line(item)}")
        else:
            for item in items:
                body_parts.append(f"- {_single_line(item)}")
    return "\n".join(body_parts).rstrip() + "\n"


def _parse_yaml_like(raw_text: str) -> dict[str, Any]:
    if yaml is not None:
        parsed = yaml.safe_load(raw_text) or {}
        return parsed if isinstance(parsed, dict) else {}

    metadata: dict[str, Any] = {}
    for line in raw_text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"').strip("'")
    return metadata


def _dump_yaml_like(payload: dict[str, Any]) -> str:
    if yaml is not None:
        return yaml.safe_dump(
            payload,
            allow_unicode=True,
            sort_keys=False,
        ).rstrip()
    lines: list[str] = []
    for key, value in payload.items():
        lines.append(f"{key}: {value}")
    return "\n".join(lines)


def _normalize_datetime(value: datetime | None) -> datetime:
    timestamp = value or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def _isoformat_utc(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _timestamp_for_id(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%SZ")


def _single_line(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "…"
