"""
RequirementActor - 单条需求的生命周期管理

遵循虚拟 Actor 模式：
- 透明唤醒/休眠
- 信箱串行处理命令
- 基于事件的状态重建
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Any

from backend_business.services.event_store.event_store import EventStore
from backend_business.services.actor.actors.state_machine import (
    RequirementStatus, RequirementStateMachine
)
from backend_business.services.actor.dev_trace import emit_actor_trace

logger = logging.getLogger(__name__)


@dataclass
class RequirementState:
    """需求内部状态"""
    requirement_id: str
    version: int = 0
    content: Dict = field(default_factory=dict)
    status: RequirementStatus = RequirementStatus.DRAFT
    quality_markers: Dict = field(default_factory=dict)
    evidence_links: list = field(default_factory=list)
    priority: str = "medium"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    is_deleted: bool = False


class DomainException(Exception):
    """业务逻辑异常 - 不应重试"""
    pass


class InfrastructureException(Exception):
    """基础设施异常 - 可重试"""
    pass


class RequirementActor:
    """单条需求的 Actor 实例"""

    PASSIVATION_TIMEOUT = 600  # 10分钟无活动后休眠
    SNAPSHOT_INTERVAL = 100      # 每100事件快照一次
    MAX_RETRIES = 3

    def __init__(self, requirement_id: str, event_store: EventStore):
        self.requirement_id = requirement_id
        self.event_store = event_store
        self.state = RequirementState(requirement_id=requirement_id)
        self.state_machine = RequirementStateMachine()

        # 信箱 - 串行处理命令
        self.mailbox: asyncio.Queue = asyncio.Queue()

        # 生命周期管理
        self.last_accessed = time.time()
        self.is_faulted = False
        self._consumer_task: Optional[asyncio.Task] = None

    async def start(self):
        """启动 Actor 消费协程"""
        if self._consumer_task is None or self._consumer_task.done():
            self._consumer_task = asyncio.create_task(self._process_mailbox())

        logger.debug(f"Actor started: {self.requirement_id}")
        emit_actor_trace(self.requirement_id, "actor_started")

    async def stop(self):
        """停止 Actor，清理资源"""
        # 先确保快照可持久化，失败时保持 Actor 存活
        await self._take_snapshot("manual")

        if self._consumer_task and not self._consumer_task.done():
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass

        logger.debug(f"Actor stopped: {self.requirement_id}")
        emit_actor_trace(self.requirement_id, "actor_stopped")

    async def activate(self):
        """激活 Actor - 从事件存储加载状态"""
        # 尝试从快照加载
        latest_snapshot = self.event_store.get_latest_snapshot(self.requirement_id)
        from_version = 0

        if latest_snapshot:
            snapshot_data = latest_snapshot["snapshot_data"]
            # 从快照重建状态
            self.state = RequirementState(
                requirement_id=snapshot_data.get("requirement_id", self.requirement_id),
                version=snapshot_data.get("version", 0),
                content=snapshot_data.get("content", {}),
                status=RequirementStatus(snapshot_data.get("status", "Draft")),
                quality_markers=snapshot_data.get("quality_markers", {}),
                evidence_links=snapshot_data.get("evidence_links", []),
                priority=snapshot_data.get("priority", "medium"),
                created_at=snapshot_data.get("created_at"),
                updated_at=snapshot_data.get("updated_at"),
            )
            from_version = self.state.version
            logger.debug(f"Loaded from snapshot: {self.requirement_id}, version={from_version}")
        else:
            logger.debug(f"No snapshot found for: {self.requirement_id}, replaying all events")

        # 重放快照之后的事件
        events = self.event_store.replay_events(self.requirement_id, from_version)
        for event in events:
            self._apply_event(event)

        self.last_accessed = time.time()

    async def send_command(self, command: Dict) -> Dict:
        """
        发送命令到 Actor

        Args:
            command: 命令字典，必须包含 type 字段

        Returns:
            命令执行结果

        Raises:
            InfrastructureException: Actor 已熔断
        """
        self.last_accessed = time.time()

        if self.is_faulted:
            raise InfrastructureException(f"Actor {self.requirement_id} 已熔断")

        future = asyncio.get_running_loop().create_future()
        await self.mailbox.put((command, future))
        return await future

    def _apply_event(self, event: Dict):
        """应用事件到状态"""
        event_type = event["event_type"]
        event_data = event["event_data"]

        if event_type == "RequirementCreated":
            self.state.content = event_data.get("content", {})
            self.state.status = RequirementStatus(event_data.get("status", "Draft"))
            self.state.priority = event_data.get("priority", "medium")
            self.state.created_at = event.get("occurred_at")

        elif event_type == "RequirementContentUpdated":
            updates = event_data.get("updates", {})
            self.state.content.update(updates)
            if "priority" in updates:
                self.state.priority = updates["priority"]
            self.state.updated_at = event.get("occurred_at")

        elif event_type == "RequirementStatusChanged":
            old_status = self.state.status
            new_status = RequirementStatus(event_data["new_status"])
            self.state.status = self.state_machine.transition(old_status, new_status)
            self.state.updated_at = event.get("occurred_at")

        elif event_type == "RequirementQualityMarkerAdded":
            marker_type = event_data["marker_type"]
            marker_value = event_data["marker_value"]
            self.state.quality_markers[marker_type] = marker_value

        elif event_type == "RequirementEvidenceLinkAdded":
            link = event_data["link"]
            if link not in self.state.evidence_links:
                self.state.evidence_links.append(link)

        elif event_type == "RequirementPriorityChanged":
            self.state.priority = event_data["priority"]

        elif event_type == "RequirementDeleted":
            self.state.is_deleted = True

        self.state.version = event["event_sequence"]

    async def _process_mailbox(self):
        """处理信箱中的命令"""
        while True:
            if self.is_faulted:
                self._fail_queued_commands()
                await asyncio.sleep(1)
                continue

            try:
                command, future = await asyncio.wait_for(
                    self.mailbox.get(),
                    timeout=5.0
                )
                self.last_accessed = time.time()
                emit_actor_trace(
                    self.requirement_id,
                    "command_dequeued",
                    command_type=command.get("type", "unknown"),
                    mailbox_size=self.mailbox.qsize(),
                )

                retry_count = 0
                is_resolved = False

                while not is_resolved and not self.is_faulted:
                    try:
                        result = await self._handle_command(command)
                        if not future.done():
                            future.set_result(result)
                        is_resolved = True
                        emit_actor_trace(
                            self.requirement_id,
                            "command_succeeded",
                            command_type=command.get("type", "unknown"),
                            version=self.state.version,
                        )

                        # 定期快照
                        if self.state.version > 0 and self.state.version % self.SNAPSHOT_INTERVAL == 0:
                            await self._take_snapshot("scheduled")

                    except DomainException as e:
                        # 业务逻辑错误 - 不重试
                        if not future.done():
                            future.set_exception(e)
                        is_resolved = True
                        emit_actor_trace(
                            self.requirement_id,
                            "command_rejected",
                            level="warning",
                            command_type=command.get("type", "unknown"),
                            error=str(e),
                        )

                    except InfrastructureException as e:
                        # 基础设施错误 - 重试
                        retry_count += 1
                        if retry_count >= self.MAX_RETRIES:
                            self.is_faulted = True
                            if not future.done():
                                future.set_exception(e)
                            is_resolved = True
                            logger.error(f"Actor {self.requirement_id} faulted: {e}")
                            emit_actor_trace(
                                self.requirement_id,
                                "actor_faulted",
                                level="error",
                                command_type=command.get("type", "unknown"),
                                error=str(e),
                            )
                        else:
                            backoff = 2 ** retry_count
                            logger.warning(f"Retry {retry_count}/{self.MAX_RETRIES}: {e}, backoff={backoff}s")
                            emit_actor_trace(
                                self.requirement_id,
                                "infrastructure_retry",
                                level="warning",
                                command_type=command.get("type", "unknown"),
                                retry=retry_count,
                                max_retries=self.MAX_RETRIES,
                                backoff_seconds=backoff,
                                error=str(e),
                            )
                            await asyncio.sleep(backoff)

                    except Exception as e:
                        # 未知错误
                        if not future.done():
                            future.set_exception(e)
                        is_resolved = True
                        logger.error(f"Unknown error handling command: {e}")
                        emit_actor_trace(
                            self.requirement_id,
                            "command_failed_unknown",
                            level="error",
                            command_type=command.get("type", "unknown"),
                            error=str(e),
                        )

                self.mailbox.task_done()

            except asyncio.TimeoutError:
                # 超时，继续循环
                continue
            except asyncio.CancelledError:
                # 协程被取消，退出循环
                break
            except Exception as e:
                # 捕获所有异常，防止崩溃
                logger.error(f"Error in mailbox loop: {e}")
                emit_actor_trace(
                    self.requirement_id,
                    "mailbox_loop_error",
                    level="error",
                    error=str(e),
                )

    def _fail_queued_commands(self):
        """
        Actor 熔断后，主动失败化所有已积压请求，避免调用方无限挂起。
        """
        while True:
            try:
                _command, queued_future = self.mailbox.get_nowait()
            except asyncio.QueueEmpty:
                break

            if not queued_future.done():
                queued_future.set_exception(
                    InfrastructureException(
                        f"Actor {self.requirement_id} 已熔断，积压命令已取消"
                    )
                )
            self.mailbox.task_done()

    async def _handle_command(self, command: Dict) -> Dict:
        """处理单个命令"""
        command_type = command.get("type")

        if command_type == "UpdateRequirementContent":
            return await self._handle_update_content(command)

        elif command_type == "ChangeStatus":
            return await self._handle_change_status(command)

        elif command_type == "AddQualityMarker":
            return await self._handle_add_quality_marker(command)

        elif command_type == "QueryState":
            return self._handle_query_state(command)

        elif command_type == "CreateRequirement":
            return await self._handle_create_requirement(command)

        else:
            raise DomainException(f"未知命令类型: {command_type}")

    async def _handle_create_requirement(self, command: Dict) -> Dict:
        """处理创建需求命令"""
        if self.state.version > 0:
            raise DomainException(f"需求已存在: {self.requirement_id}")

        event = {
            "requirement_id": self.requirement_id,
            "event_type": "RequirementCreated",
            "event_data": {
                "content": command.get("content", {}),
                "status": command.get("status", "Draft"),
                "priority": command.get("priority", "medium")
            },
            "source": command.get("source", "system"),
            "metadata": command.get("metadata", {})
        }

        event_id, sequence = self.event_store.append_event(event)
        event["event_id"] = event_id
        event["event_sequence"] = sequence

        self._apply_event(event)

        return {
            "status": "success",
            "version": self.state.version,
            "event_id": event_id
        }

    async def _handle_update_content(self, command: Dict) -> Dict:
        """处理更新内容命令"""
        # 业务校验
        if self.state.status == RequirementStatus.BASELINED:
            raise DomainException("禁止修改已基线需求")

        if self.state.is_deleted:
            raise DomainException("需求已被删除")

        # 生成事件
        event = {
            "requirement_id": self.requirement_id,
            "event_type": "RequirementContentUpdated",
            "event_data": {
                "updates": command.get("updates", {})
            },
            "source": command.get("source", "system"),
            "metadata": command.get("metadata", {})
        }

        # 追加事件
        event_id, sequence = self.event_store.append_event(event)
        event["event_id"] = event_id
        event["event_sequence"] = sequence

        # 更新内存状态
        self._apply_event(event)

        return {
            "status": "success",
            "version": self.state.version,
            "event_id": event_id
        }

    async def _handle_change_status(self, command: Dict) -> Dict:
        """处理状态变更命令"""
        if self.state.is_deleted:
            raise DomainException("需求已被删除")

        new_status = RequirementStatus(command["new_status"])

        # 状态转换校验
        if not self.state_machine.can_transition(self.state.status, new_status):
            allowed = [s.value for s in self.state_machine.get_allowed_transitions(self.state.status)]
            raise DomainException(
                f"非法状态转换: {self.state.status.value} -> {new_status.value}. "
                f"允许的转换: {allowed}"
            )

        # 生成事件
        event = {
            "requirement_id": self.requirement_id,
            "event_type": "RequirementStatusChanged",
            "event_data": {
                "old_status": self.state.status.value,
                "new_status": new_status.value
            },
            "source": command.get("source", "system"),
            "metadata": command.get("metadata", {})
        }

        event_id, sequence = self.event_store.append_event(event)
        event["event_id"] = event_id
        event["event_sequence"] = sequence

        self._apply_event(event)

        return {
            "status": "success",
            "version": self.state.version,
            "event_id": event_id
        }

    async def _handle_add_quality_marker(self, command: Dict) -> Dict:
        """处理添加质量标记命令"""
        if self.state.is_deleted:
            raise DomainException("需求已被删除")

        event = {
            "requirement_id": self.requirement_id,
            "event_type": "RequirementQualityMarkerAdded",
            "event_data": {
                "marker_type": command["marker_type"],
                "marker_value": command["marker_value"]
            },
            "source": command.get("source", "system"),
            "metadata": command.get("metadata", {})
        }

        event_id, sequence = self.event_store.append_event(event)
        event["event_id"] = event_id
        event["event_sequence"] = sequence

        self._apply_event(event)

        return {
            "status": "success",
            "version": self.state.version,
            "event_id": event_id
        }

    def _handle_query_state(self, command: Dict) -> Dict:
        """Actor Ask - 直接返回内存状态"""
        if self.state.is_deleted:
            return {
                "status": "deleted",
                "requirement_id": self.state.requirement_id
            }

        return {
            "status": "success",
            "state": {
                "requirement_id": self.state.requirement_id,
                "version": self.state.version,
                "content": self.state.content,
                "status": self.state.status.value,
                "quality_markers": self.state.quality_markers,
                "evidence_links": self.state.evidence_links,
                "priority": self.state.priority,
                "created_at": self.state.created_at,
                "updated_at": self.state.updated_at
            }
        }

    async def _take_snapshot(self, reason: str):
        """保存快照"""
        state_data = {
            "requirement_id": self.state.requirement_id,
            "version": self.state.version,
            "content": self.state.content,
            "status": self.state.status.value,
            "quality_markers": self.state.quality_markers,
            "evidence_links": self.state.evidence_links,
            "priority": self.state.priority,
            "created_at": self.state.created_at,
            "updated_at": self.state.updated_at
        }

        try:
            snapshot_id = self.event_store.save_snapshot(
                self.requirement_id,
                self.state.version,
                state_data,
                reason
            )
            logger.debug(f"Snapshot saved: {snapshot_id}, reason={reason}")
            emit_actor_trace(
                self.requirement_id,
                "snapshot_saved",
                reason=reason,
                version=self.state.version,
                snapshot_id=snapshot_id,
            )
        except Exception as e:
            logger.error(f"Failed to save snapshot: {e}")
            emit_actor_trace(
                self.requirement_id,
                "snapshot_failed",
                level="error",
                reason=reason,
                version=self.state.version,
                error=str(e),
            )
            raise InfrastructureException(
                f"Actor {self.requirement_id} 快照落库失败: {e}"
            ) from e
