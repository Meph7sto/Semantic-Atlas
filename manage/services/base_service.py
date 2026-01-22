"""应用层基础服务（抽象接口）"""
from __future__ import annotations
from typing import Protocol, Optional, Dict, Any, List


class Repository(Protocol):
    """仓储接口占位（基础CRUD）"""

    def add(self, entity: Any) -> None:
        ...

    def get(self, entity_id: str) -> Optional[Any]:
        ...

    def list(self, **filters: Any) -> List[Any]:
        ...

    def update(self, entity: Any) -> None:
        ...

    def delete(self, entity_id: str) -> None:
        ...


class UnitOfWork(Protocol):
    """工作单元接口占位（事务控制）"""

    def commit(self) -> None:
        ...

    def rollback(self) -> None:
        ...


class AppService:
    """应用层服务基类"""

    def __init__(
        self,
        repos: Dict[str, Repository] | None = None,
        uow: UnitOfWork | None = None,
    ) -> None:
        self.repos = repos or {}
        self.uow = uow
