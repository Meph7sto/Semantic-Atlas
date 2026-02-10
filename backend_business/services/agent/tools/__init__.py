"""Agent tools package.
Agent 工具包。

Tools are functions exposed to agents (via OpenAI schemas) that can:
工具是暴露给 Agent 的函数（通过 OpenAI schema），可以：
- Read data (e.g. search requirements)
  读取数据（例如搜索需求）
- Write data (e.g. update requirement -> creates pending task)
  写入数据（例如更新需求 -> 创建待处理任务）
- Perform actions (e.g. delegate to another agent)
  执行动作（例如委派给另一个 Agent）
"""

from backend_business.services.agent.tools.base import ToolDefinition, tool_registry

__all__ = ["ToolDefinition", "tool_registry"]
