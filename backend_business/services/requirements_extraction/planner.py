"""
LLM planner interaction for requirements extraction
"""

import logging
from typing import Any, Dict, List, Optional

import aiohttp

from backend_business.services.ai_proxy import ai_proxy
from backend_business.services.requirements_executor import RequirementToolDef

logger = logging.getLogger(__name__)


def build_extraction_prompt(
    bundle: Dict[str, Any],
    use_toolcall: bool = True,
    existing_requirements: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    构建需求抽取 Prompt

    Args:
        bundle: EgoBundle
        use_toolcall: 是否使用 tool call 格式
        existing_requirements: 已存在的需求列表（用于历史感知模式）

    Returns:
        Prompt 字符串
    """
    lines = []

    # 如果有已知需求，先注入
    if existing_requirements:
        lines.append(
            RequirementToolDef.format_existing_requirements(existing_requirements)
        )
        lines.append("")

    lines.append("# 上下文片段")
    lines.append("")

    for i, span in enumerate(bundle["spans"]):
        ref = bundle["span_refs"][i]
        speaker = span.get("speaker", "未知")
        text = span.get("text", "")
        start_ms = span.get("start_ms")
        end_ms = span.get("end_ms")

        time_info = ""
        if start_ms is not None and end_ms is not None:
            time_info = f" [{start_ms}ms - {end_ms}ms]"

        lines.append(f"**{ref}**{time_info} {speaker}: {text}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("# 任务")
    lines.append("")
    lines.append("请只提炼明确的需求或约束，忽略背景介绍、论证过程、寒暄、供应方承诺和纯示例性表述。")
    lines.append("每条需求必须原子化，只表达一个核心点；若同一片段包含多个独立要求，请拆成多条。")
    lines.append("会议中的举例或场景应改写为通用需求，不要把示例细节整段照抄进需求文本。")
    lines.append("")

    if use_toolcall:
        if existing_requirements:
            # 历史感知模式的任务说明
            lines.append(
                "基于上述上下文片段和【已知需求清单】，请进行智能需求抽取和更新。"
            )
            lines.append("")
            lines.append("**操作指引：**")
            lines.append(
                "1. 如发现全新需求（与已知需求不重复），调用 `create_req` 创建"
            )
            lines.append(
                "2. 如发现当前片段细化/补充了已有需求，调用 `update_req` 更新对应条目"
            )
            lines.append("3. 如当前片段与已知需求高度重复且无新信息，则不进行任何操作")
            lines.append("4. 不要把多个独立主题揉进同一条 update_req；能拆则拆")
        else:
            lines.append(
                "基于上述上下文片段,请使用 create_req 工具抽取 L1/L2/L3 需求。"
            )
            lines.append("对于每个识别到的需求,调用一次 create_req 工具。")
    else:
        lines.append("基于上述上下文片段,使用 create_req 工具抽取 L1/L2/L3 需求。")
        lines.append("")
        lines.append("**输出格式示例:**")
        lines.append(
            'CALL create_req level="L1" text="提升借用审批效率并降低人工核验成本"'
        )
        lines.append('CALL create_req level="L2" text="系统应支持在线提交借用申请"')
        lines.append(
            'CALL create_req level="L3" text="系统必须在 2 秒内完成审批流程验证"'
        )

    return "\n".join(lines)


def call_planner(
    bundle: Dict[str, Any],
    model_name: str,
    use_toolcall: bool = True,
    existing_requirements: Optional[List[Dict[str, Any]]] = None,
    history_aware: bool = False,
    use_thinking_mode: bool = True,
    connect_timeout: Optional[float] = None,
    read_timeout: Optional[float] = None,
    max_retries: Optional[int] = None,
) -> Dict[str, Any]:
    """
    调用 Planner（大模型）进行需求抽取

    Args:
        bundle: EgoBundle
        model_name: 模型名称
        use_toolcall: 是否使用 DeepSeek API tool call 格式（默认为 True）
        existing_requirements: 已存在的需求列表（用于历史感知模式）
        history_aware: 是否启用历史感知模式

    Returns:
        Planner 输出
    """
    # 构建 Prompt
    prompt = build_extraction_prompt(
        bundle,
        use_toolcall=use_toolcall,
        existing_requirements=existing_requirements if history_aware else None,
    )
    system_prompt = RequirementToolDef.get_system_prompt(history_aware=history_aware)

    if use_toolcall:
        # 使用 DeepSeek API tool call 格式
        try:
            # 根据是否启用历史感知模式决定工具列表
            tools = RequirementToolDef.get_tools_list(include_update=history_aware)
            response = ai_proxy.chat_completion_with_tools(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                tools=tools,
                model=model_name,
                thinking_enabled=use_thinking_mode,
                temperature=0.3,
                tool_choice="auto",  # 让模型自动决定是否调用工具
                connect_timeout=connect_timeout,
                read_timeout=read_timeout,
                max_retries=max_retries,
            )
            # tool_calls 格式返回
            tool_calls = response.get("tool_calls")
            content = response.get("content", "")
            finish_reason = response.get("finish_reason")

            return {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "output": tool_calls,  # 返回 tool_calls 列表
                "content": content,  # 可能有的文本内容
                "finish_reason": finish_reason,
                "model": model_name,
                "use_toolcall": True,
                "history_aware": history_aware,
            }
        except Exception as e:
            logger.exception("Error calling planner with tool call")
            return {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "output": None,
                "content": "",
                "finish_reason": "error",
                "model": model_name,
                "use_toolcall": True,
                "history_aware": history_aware,
                "status": "error",
                "error": str(e),
            }
    else:
        # 旧的文本生成方式
        try:
            response = ai_proxy.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                model=model_name,
                thinking_enabled=use_thinking_mode,
                temperature=0.3,
            )
            output = response.get("content", "")
        except Exception as e:
            logger.exception("Error calling planner")
            return {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "output": None,
                "model": model_name,
                "use_toolcall": False,
                "history_aware": False,
                "status": "error",
                "error": str(e),
            }

        return {
            "prompt": prompt,
            "system_prompt": system_prompt,
            "output": output,
            "model": model_name,
            "use_toolcall": False,
            "history_aware": False,
        }


async def call_planner_async(
    bundle: Dict[str, Any],
    model_name: str,
    use_toolcall: bool = True,
    session: Optional[aiohttp.ClientSession] = None,
    existing_requirements: Optional[List[Dict[str, Any]]] = None,
    history_aware: bool = False,
    use_thinking_mode: bool = True,
    connect_timeout: Optional[float] = None,
    read_timeout: Optional[float] = None,
    max_retries: Optional[int] = None,
) -> Dict[str, Any]:
    """
    异步调用 Planner（大模型）进行需求抽取

    Args:
        bundle: EgoBundle
        model_name: 模型名称
        use_toolcall: 是否使用 DeepSeek API tool call 格式
        session: aiohttp ClientSession（用于连接复用）
        existing_requirements: 已存在的需求列表（用于历史感知模式）
        history_aware: 是否启用历史感知模式

    Returns:
        Planner 输出
    """
    # 构建 Prompt
    prompt = build_extraction_prompt(
        bundle,
        use_toolcall=use_toolcall,
        existing_requirements=existing_requirements if history_aware else None,
    )
    system_prompt = RequirementToolDef.get_system_prompt(history_aware=history_aware)

    if use_toolcall:
        # 使用 DeepSeek API tool call 格式
        try:
            tools = RequirementToolDef.get_tools_list(include_update=history_aware)
            response = await ai_proxy.chat_completion_with_tools_async(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                tools=tools,
                model=model_name,
                thinking_enabled=use_thinking_mode,
                temperature=0.3,
                tool_choice="auto",
                session=session,
                connect_timeout=connect_timeout,
                read_timeout=read_timeout,
                max_retries=max_retries,
            )

            tool_calls = response.get("tool_calls")
            content = response.get("content", "")
            finish_reason = response.get("finish_reason")

            return {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "output": tool_calls,
                "content": content,
                "finish_reason": finish_reason,
                "model": model_name,
                "use_toolcall": True,
                "history_aware": history_aware,
            }
        except Exception as e:
            logger.exception("Error calling planner with tool call (async)")
            return {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "output": None,
                "content": "",
                "finish_reason": "error",
                "model": model_name,
                "use_toolcall": True,
                "history_aware": history_aware,
                "status": "error",
                "error": str(e),
            }
    else:
        # 旧的文本生成方式（异步版本暂不实现,因为不需要）
        raise NotImplementedError("Async non-toolcall mode is not supported")
