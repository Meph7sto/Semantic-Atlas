"""评审应用服务"""
from __future__ import annotations

from .base_service import AppService
from ..domain.review import Review


class ReviewService(AppService):
    """评审用例服务"""

    def request_review(self, project_id: str, branch_id: str, created_by: str, reviewers: list[str]) -> Review:
        review = Review(
            project_id=project_id,
            branch_id=branch_id,
            reviewers=reviewers,
            created_by=created_by,
        )
        repo = self.repos.get("review")
        if repo:
            repo.add(review)
        if self.uow:
            self.uow.commit()
        return review

    def approve(self, review: Review, decided_by: str) -> Review:
        review.approve(decided_by)
        repo = self.repos.get("review")
        if repo:
            repo.update(review)
        if self.uow:
            self.uow.commit()
        return review

    def reject(self, review: Review, decided_by: str) -> Review:
        review.reject(decided_by)
        repo = self.repos.get("review")
        if repo:
            repo.update(review)
        if self.uow:
            self.uow.commit()
        return review

    def request_changes(self, review: Review, decided_by: str) -> Review:
        review.request_changes(decided_by)
        repo = self.repos.get("review")
        if repo:
            repo.update(review)
        if self.uow:
            self.uow.commit()
        return review
