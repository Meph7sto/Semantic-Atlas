"""评审模型定义"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional
from uuid import uuid4

from .enums import ReviewStatus


@dataclass
class ReviewComment:
    """评审意见"""
    id: str = field(default_factory=lambda: str(uuid4()))
    reviewer: str = ""
    comment: str = ""
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "reviewer": self.reviewer,
            "comment": self.comment,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class Review:
    """分支评审"""
    id: str = field(default_factory=lambda: str(uuid4()))
    project_id: str = ""
    branch_id: str = ""

    status: ReviewStatus = ReviewStatus.PENDING
    reviewers: List[str] = field(default_factory=list)
    comments: List[ReviewComment] = field(default_factory=list)

    created_by: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    decided_by: Optional[str] = None
    decided_at: Optional[datetime] = None

    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_comment(self, reviewer: str, comment: str) -> ReviewComment:
        new_comment = ReviewComment(reviewer=reviewer, comment=comment)
        self.comments.append(new_comment)
        return new_comment

    def approve(self, decided_by: str) -> None:
        self.status = ReviewStatus.APPROVED
        self.decided_by = decided_by
        self.decided_at = datetime.now()

    def reject(self, decided_by: str) -> None:
        self.status = ReviewStatus.REJECTED
        self.decided_by = decided_by
        self.decided_at = datetime.now()

    def request_changes(self, decided_by: str) -> None:
        self.status = ReviewStatus.CHANGES_REQUESTED
        self.decided_by = decided_by
        self.decided_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "branch_id": self.branch_id,
            "status": self.status.value,
            "reviewers": self.reviewers,
            "comments": [c.to_dict() for c in self.comments],
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "decided_by": self.decided_by,
            "decided_at": self.decided_at.isoformat() if self.decided_at else None,
            "metadata": self.metadata,
        }
