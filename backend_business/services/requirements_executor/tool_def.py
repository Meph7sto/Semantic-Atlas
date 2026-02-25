"""
需求工具定义
create_req / update_req 工具定义与约束规则、系统提示词
"""

from typing import Any, Dict, List


class RequirementToolDef:
    """
    create_req / update_req 工具定义与约束规则
    """

    LEVEL_ENUM = {"L1", "L2", "L3"}
    TEXT_MIN_LENGTH = 10
    TEXT_MAX_LENGTH = 500

    # 每个 EgoBundle 的产出上限
    QUOTA_PER_BUNDLE = {
        "L1": 2,
        "L2": 5,
        "L3": 8,
    }

    # L3 引导关键词（优先使用，但不强制）
    L3_KEYWORDS = ["系统必须", "应当", "shall", "must", "should"]

    @classmethod
    def get_create_tool_schema(cls) -> Dict[str, Any]:
        """
        返回 create_req 工具的 JSON Schema
        用于传递给大模型，符合 DeepSeek API tool call 格式
        参考: https://api-docs.deepseek.com/zh-cn/guides/tool_calls
        """
        return {
            "type": "function",
            "function": {
                "name": "create_req",
                "description": "创建一条全新的 L1/L2/L3 需求条目。仅当发现与已知需求不重复的新需求时使用。L1为业务目标，L2为功能需求，L3为系统需求（建议使用'系统必须/应当/shall/must/should'等可验证措辞）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "level": {
                            "type": "string",
                            "enum": ["L1", "L2", "L3"],
                            "description": "需求层级：L1（业务目标）、L2（功能需求）、L3（系统需求）",
                        },
                        "text": {
                            "type": "string",
                            "description": "需求文本，应当简洁明确地描述需求内容",
                        },
                    },
                    "required": ["level", "text"],
                    "additionalProperties": False,
                },
            },
        }

    @classmethod
    def get_update_tool_schema(cls) -> Dict[str, Any]:
        """
        返回 update_req 工具的 JSON Schema
        用于更新已存在的需求条目
        """
        return {
            "type": "function",
            "function": {
                "name": "update_req",
                "description": "更新已存在的需求条目。当发现当前片段是对已有需求的细化、补充、数值修正或语义增强时使用此工具。需要指定要更新的需求ID和更新后的完整文本。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "req_id": {
                            "type": "string",
                            "description": "要更新的需求条目ID（来自已知需求清单）",
                        },
                        "level": {
                            "type": "string",
                            "enum": ["L1", "L2", "L3"],
                            "description": "需求层级（通常保持不变，但可根据需要调整）",
                        },
                        "text": {
                            "type": "string",
                            "description": "更新后的完整需求文本，应整合原有信息与新发现的细节",
                        },
                        "reason": {
                            "type": "string",
                            "description": "更新原因简述（如：补充了性能指标、细化了边界条件等）",
                        },
                    },
                    "required": ["req_id", "level", "text"],
                    "additionalProperties": False,
                },
            },
        }

    @classmethod
    def get_tool_schema(cls) -> Dict[str, Any]:
        """
        返回 create_req 工具的 JSON Schema（保持向后兼容）
        """
        return cls.get_create_tool_schema()

    @classmethod
    def get_tools_list(cls, include_update: bool = False) -> List[Dict[str, Any]]:
        """
        返回工具列表，用于 DeepSeek API tool call

        Args:
            include_update: 是否包含 update_req 工具（用于串行历史感知模式）

        Returns:
            工具定义列表
        """
        tools = [cls.get_create_tool_schema()]
        if include_update:
            tools.append(cls.get_update_tool_schema())
        return tools

    @classmethod
    def get_system_prompt(cls, history_aware: bool = False) -> str:
        """
        返回系统提示词，用于 tool call 模式下的需求分析

        Args:
            history_aware: 是否启用历史感知模式（串行模式下使用）
        """
        base_prompt = f"""你是一个专业的需求分析助手。请根据提供的上下文片段进行需求抽取。

**需求层级说明：**
- L1：业务目标、宏观愿景（如"提升借用审批效率并降低人工核验成本"）
- L2：功能需求、用户故事（如"系统应支持在线提交借用申请"）
- L3：系统需求、技术约束（如"系统必须在 2 秒内完成审批流程验证"）
  - L3 可优先覆盖性能/稳定性/安全/一致性/容量/接口边界等可验证约束

**约束规则：**
1. level 必须属于 L1、L2、L3 之一。
2. text 非空，长度限制 {cls.TEXT_MIN_LENGTH}-{cls.TEXT_MAX_LENGTH} 字。
3. 产出上限：L1 <= {cls.QUOTA_PER_BUNDLE["L1"]}，L2 <= {cls.QUOTA_PER_BUNDLE["L2"]}，L3 <= {cls.QUOTA_PER_BUNDLE["L3"]}。
4. L3 建议使用"系统必须/应当/shall/must/should"等可验证措辞，但不强制；更鼓励明确的系统能力、质量指标、边界或约束。
5. 若上下文不足以形成某层需求，该层可为空，但不得编造与输入无关的需求。
"""

        if history_aware:
            base_prompt += """
**历史感知模式 - 重要操作指引：**

你有两个可用工具：`create_req` 和 `update_req`。在处理当前片段时，你必须基于【已知需求清单】进行智能判断：

1. **发现全新需求** → 调用 `create_req`
   - 当前片段包含与已知需求完全不同的新业务目标、功能或约束
   - 确保不是已有需求的变体或重复表述

2. **细化/补充已有需求** → 调用 `update_req`
   - 当前片段提供了已有需求的更多细节（如具体数值、边界条件、异常处理）
   - 当前片段修正了已有需求的表述（如更精确的描述、更新的指标）
   - 需要将新信息整合到已有需求中，产出完整的更新文本
   - 必须提供 req_id 指定要更新的需求

3. **语义高度重复且无新信息** → 不进行任何操作
   - 当前片段与已知需求语义重复，没有增量价值
   - 不要为了产出而产出，避免制造噪音

**判断优先级：** 先检查是否与已有需求相关（更新或跳过），再考虑是否为新需求（创建）。
"""

        return base_prompt

    @classmethod
    def format_existing_requirements(cls, requirements: List[Dict[str, Any]]) -> str:
        """
        格式化已存在的需求清单，用于注入到提示词中

        Args:
            requirements: 需求列表，每项包含 req_id, level, text

        Returns:
            格式化的需求清单字符串
        """
        if not requirements:
            return "【已知需求清单】\n（当前暂无已抽取的需求）\n"

        lines = ["【已知需求清单】", ""]

        # 按层级分组
        by_level: Dict[str, List[Dict[str, Any]]] = {"L1": [], "L2": [], "L3": []}
        for req in requirements:
            level = req.get("level", "")
            if level in by_level:
                by_level[level].append(req)

        for level in ["L1", "L2", "L3"]:
            reqs = by_level[level]
            if reqs:
                level_names = {"L1": "业务目标", "L2": "功能需求", "L3": "系统需求"}
                lines.append(
                    f"## {level} - {level_names.get(level, level)} ({len(reqs)}条)"
                )
                for req in reqs:
                    req_id = req.get("req_id", "unknown")
                    text = req.get("text", "")
                    # 使用短ID便于引用
                    short_id = req_id[:8] if len(req_id) > 8 else req_id
                    lines.append(f"- [{short_id}] {text}")
                lines.append("")

        lines.append("---")
        return "\n".join(lines)
