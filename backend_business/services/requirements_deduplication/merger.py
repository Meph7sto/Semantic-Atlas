"""
LLM-based merger for requirements deduplication.

Uses Tool Call to let LLM decide whether to merge duplicate requirements
and generate the merged text.

Supports both synchronous and asynchronous (parallel) processing.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

import aiohttp

from backend_business.services.ai_proxy import ai_proxy

from .models import MergeDecision

logger = logging.getLogger(__name__)


class MergerToolDef:
    """合并操作的 Tool Call 定义"""

    @classmethod
    def get_merge_tool_schema(cls) -> Dict[str, Any]:
        """返回 merge_requirements 工具的 JSON Schema"""
        return {
            "type": "function",
            "function": {
                "name": "merge_requirements",
                "description": "判断多个语义相似的需求是否应该合并，并生成合并后的文本。合并后的文本应整合所有原需求的核心信息，不丢失关键细节。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "should_merge": {
                            "type": "boolean",
                            "description": "是否应该合并这些需求。如果语义差异明显（描述不同方面），应返回false",
                        },
                        "merged_text": {
                            "type": "string",
                            "description": "合并后的完整需求文本，应涵盖所有原需求的要点。仅当 should_merge=true 时需要提供",
                        },
                        "merged_level": {
                            "type": "string",
                            "enum": ["L1", "L2", "L3"],
                            "description": "合并后的需求层级（通常保持原层级不变）",
                        },
                        "primary_req_id": {
                            "type": "string",
                            "description": "保留哪个需求ID作为主需求（通常选择最完整的那个）",
                        },
                        "reason": {
                            "type": "string",
                            "description": "合并理由或不合并的原因说明",
                        },
                    },
                    "required": ["should_merge", "reason"],
                    "additionalProperties": False,
                },
            },
        }

    @classmethod
    def get_system_prompt(cls) -> str:
        """返回系统提示词"""
        return """你是一个专业的需求分析助手，负责判断多个需求是否应该合并。

**判断标准：**
1. **应该合并**：语义高度重复，只是表述不同
   - 例如："提升审批效率" 与 "加快审批速度" → 应合并
   - 例如："系统响应时间<2秒" 与 "系统必须在2秒内响应" → 应合并

2. **不应合并**：虽然相似，但描述不同的需求侧面
   - 例如："提升效率" 与 "降低成本" → 不应合并（是两个独立目标）
   - 例如："支持批量导入" 与 "支持批量导出" → 不应合并（是不同功能）

**合并原则：**
- 保留所有关键信息（数值、约束、边界条件）
- 使用更准确、更完整的表述
- 避免信息丢失
- 合并文本长度应合理（10-500字）

**输出要求：**
- 必须调用 merge_requirements 工具
- 如果应该合并，提供合并后的完整文本
- 如果不应合并，在 reason 中说明原因"""


class RequirementMerger:
    """
    基于 LLM 的需求合并决策器

    使用 Tool Call 让 LLM 判断是否合并，并生成合并文本
    """

    def __init__(self, model_name: str = "deepseek-reasoner"):
        self.model_name = model_name

    def decide_merge(
        self,
        duplicate_group: Dict[str, Any],
        model_name: Optional[str] = None,
    ) -> MergeDecision:
        """
        让 LLM 判断是否合并，并生成合并文本

        Args:
            duplicate_group: 重复组，包含:
                - level: 需求层级
                - requirements: 需求列表 [{"req_id": ..., "text": ...}]
                - similarity: 相似度
            model_name: 使用的模型（可选，覆盖默认值）

        Returns:
            MergeDecision 决策结果
        """
        model = model_name or self.model_name

        # 构建提示词
        prompt = self._build_merge_prompt(duplicate_group)
        system_prompt = MergerToolDef.get_system_prompt()

        try:
            response = ai_proxy.chat_completion_with_tools(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                tools=[MergerToolDef.get_merge_tool_schema()],
                model=model,
                temperature=0.3,
                tool_choice="auto",
            )

            # 解析响应
            tool_calls = response.get("tool_calls")
            if tool_calls and len(tool_calls) > 0:
                call = tool_calls[0]
                if call.get("type") == "function":
                    func = call["function"]
                    if func.get("name") == "merge_requirements":
                        args = func.get("arguments", {})
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except json.JSONDecodeError:
                                return MergeDecision(
                                    should_merge=False,
                                    reason="LLM返回的参数解析失败",
                                    error="JSON decode error",
                                )

                        # 获取第一个需求作为默认主需求
                        default_primary = ""
                        if duplicate_group.get("requirements"):
                            default_primary = duplicate_group["requirements"][0].get(
                                "req_id", ""
                            )

                        return MergeDecision(
                            should_merge=args.get("should_merge", False),
                            merged_text=args.get("merged_text", ""),
                            merged_level=args.get(
                                "merged_level", duplicate_group.get("level", "L2")
                            ),
                            primary_req_id=args.get("primary_req_id", default_primary),
                            reason=args.get("reason", ""),
                        )

            # 如果没有调用工具，检查是否有文本内容
            content = response.get("content", "")
            if content:
                logger.warning(f"LLM未调用工具，返回文本: {content[:200]}")

            return MergeDecision(
                should_merge=False,
                reason="LLM未调用合并工具，可能认为需求差异明显",
            )

        except Exception as e:
            logger.exception("Error calling LLM for merge decision")
            return MergeDecision(
                should_merge=False,
                reason=f"LLM调用失败: {str(e)}",
                error=str(e),
            )

    async def decide_merge_async(
        self,
        duplicate_group: Dict[str, Any],
        model_name: Optional[str] = None,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> MergeDecision:
        """
        异步版本：让 LLM 判断是否合并，并生成合并文本

        Args:
            duplicate_group: 重复组，包含:
                - level: 需求层级
                - requirements: 需求列表 [{"req_id": ..., "text": ...}]
                - similarity: 相似度
            model_name: 使用的模型（可选，覆盖默认值）
            session: aiohttp ClientSession（用于连接复用）

        Returns:
            MergeDecision 决策结果
        """
        model = model_name or self.model_name

        # 构建提示词
        prompt = self._build_merge_prompt(duplicate_group)
        system_prompt = MergerToolDef.get_system_prompt()

        try:
            response = await ai_proxy.chat_completion_with_tools_async(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                tools=[MergerToolDef.get_merge_tool_schema()],
                model=model,
                temperature=0.3,
                tool_choice="auto",
                session=session,
            )

            # 解析响应（与同步版本相同）
            tool_calls = response.get("tool_calls")
            if tool_calls and len(tool_calls) > 0:
                call = tool_calls[0]
                if call.get("type") == "function":
                    func = call["function"]
                    if func.get("name") == "merge_requirements":
                        args = func.get("arguments", {})
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except json.JSONDecodeError:
                                return MergeDecision(
                                    should_merge=False,
                                    reason="LLM返回的参数解析失败",
                                    error="JSON decode error",
                                )

                        # 获取第一个需求作为默认主需求
                        default_primary = ""
                        if duplicate_group.get("requirements"):
                            default_primary = duplicate_group["requirements"][0].get(
                                "req_id", ""
                            )

                        return MergeDecision(
                            should_merge=args.get("should_merge", False),
                            merged_text=args.get("merged_text", ""),
                            merged_level=args.get(
                                "merged_level", duplicate_group.get("level", "L2")
                            ),
                            primary_req_id=args.get("primary_req_id", default_primary),
                            reason=args.get("reason", ""),
                        )

            # 如果没有调用工具，检查是否有文本内容
            content = response.get("content", "")
            if content:
                logger.warning(f"LLM未调用工具，返回文本: {content[:200]}")

            return MergeDecision(
                should_merge=False,
                reason="LLM未调用合并工具，可能认为需求差异明显",
            )

        except Exception as e:
            logger.exception("Error calling LLM for merge decision (async)")
            return MergeDecision(
                should_merge=False,
                reason=f"LLM调用失败: {str(e)}",
                error=str(e),
            )

    def _build_merge_prompt(self, duplicate_group: Dict[str, Any]) -> str:
        """构建合并判断提示词"""
        lines = ["# 疑似重复的需求", ""]

        level = duplicate_group.get("level", "未知")
        similarity = duplicate_group.get("similarity", 0)

        lines.append(f"**层级**: {level}")
        lines.append(f"**文本相似度**: {similarity:.1%}")
        lines.append("")

        lines.append("**候选需求列表:**")
        requirements = duplicate_group.get("requirements", [])
        for i, req in enumerate(requirements, 1):
            req_id = req.get("req_id", "unknown")
            short_id = req_id[:8] if len(req_id) > 8 else req_id
            text = req.get("text", "")
            lines.append(f"{i}. [{short_id}] {text}")

        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append(
            "**任务**: 请判断这些需求是否应该合并。"
            "使用 `merge_requirements` 工具提供你的决策。"
        )

        return "\n".join(lines)

    def batch_decide_merge(
        self,
        duplicate_groups: List[Dict[str, Any]],
        model_name: Optional[str] = None,
        max_concurrent: int = 5,
    ) -> List[MergeDecision]:
        """
        批量处理多个重复组的合并决策（并行版本）

        Args:
            duplicate_groups: 重复组列表
            model_name: 使用的模型
            max_concurrent: 最大并发数（默认 5）

        Returns:
            决策结果列表（与输入顺序对应）
        """
        if not duplicate_groups:
            return []

        # 使用新的事件循环运行异步批处理
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            decisions = loop.run_until_complete(
                self.batch_decide_merge_async(
                    duplicate_groups,
                    model_name=model_name,
                    max_concurrent=max_concurrent,
                )
            )
        finally:
            loop.close()
            asyncio.set_event_loop(None)

        return decisions

    async def batch_decide_merge_async(
        self,
        duplicate_groups: List[Dict[str, Any]],
        model_name: Optional[str] = None,
        max_concurrent: int = 5,
    ) -> List[MergeDecision]:
        """
        异步批量处理多个重复组的合并决策（真正的并行执行）

        Args:
            duplicate_groups: 重复组列表
            model_name: 使用的模型
            max_concurrent: 最大并发数（默认 5）

        Returns:
            决策结果列表（与输入顺序对应）
        """
        if not duplicate_groups:
            return []

        model = model_name or self.model_name

        # 使用信号量限制并发数
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_one(
            index: int,
            group: Dict[str, Any],
            session: aiohttp.ClientSession,
        ) -> tuple[int, MergeDecision]:
            """处理单个重复组，返回 (索引, 决策结果)"""
            async with semaphore:
                logger.debug(
                    f"Processing duplicate group {index + 1}/{len(duplicate_groups)}"
                )
                decision = await self.decide_merge_async(
                    group, model_name=model, session=session
                )
                return (index, decision)

        # 使用单个 session 复用连接
        async with aiohttp.ClientSession() as session:
            tasks = [
                process_one(i, group, session)
                for i, group in enumerate(duplicate_groups)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        # 按原始顺序整理结果
        decisions: List[MergeDecision] = [None] * len(duplicate_groups)  # type: ignore
        for result in results:
            if isinstance(result, Exception):
                logger.exception(f"Error in parallel merge decision: {result}")
                # 对于异常，创建一个错误决策
                # 但我们不知道索引，所以需要换种方式处理
                continue
            idx, decision = result
            decisions[idx] = decision

        # 填充可能因异常而缺失的决策
        for i, decision in enumerate(decisions):
            if decision is None:
                decisions[i] = MergeDecision(
                    should_merge=False,
                    reason="并行处理时发生异常",
                    error="Processing exception",
                )

        return decisions
