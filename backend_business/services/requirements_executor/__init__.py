"""
需求抽取执行器包
拆分自原 requirements_executor.py，保持对外接口不变
"""

from .executor import RequirementsExecutor
from .tool_def import RequirementToolDef

__all__ = ["RequirementToolDef", "RequirementsExecutor"]
