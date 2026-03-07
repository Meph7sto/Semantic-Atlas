"""
Actor 模块

提供基于 Actor 模型的需求生命周期管理：
- 状态机控制需求状态转换
- RequirementActor 管理单条需求的生命周期
- ActorManager 全局管理所有 Actor
"""

from .actor_manager import ActorManager

__all__ = ["ActorManager"]
