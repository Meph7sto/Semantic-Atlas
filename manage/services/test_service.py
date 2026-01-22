"""测试用例/验收标准应用服务"""
from __future__ import annotations
from typing import Optional

from .base_service import AppService
from ..domain.test_case import TestCase, AcceptanceCriteria, RequirementTestLink
from ..domain.enums import TestCaseStatus


class TestService(AppService):
    """测试与验收标准用例服务"""

    def create_test_case(self, test_case: TestCase) -> TestCase:
        repo = self.repos.get("test_case")
        if repo:
            repo.add(test_case)
        if self.uow:
            self.uow.commit()
        return test_case

    def update_test_case(self, test_case: TestCase, **kwargs) -> TestCase:
        test_case.update(**kwargs)
        repo = self.repos.get("test_case")
        if repo:
            repo.update(test_case)
        if self.uow:
            self.uow.commit()
        return test_case

    def create_acceptance(self, acceptance: AcceptanceCriteria) -> AcceptanceCriteria:
        repo = self.repos.get("acceptance")
        if repo:
            repo.add(acceptance)
        if self.uow:
            self.uow.commit()
        return acceptance

    def update_acceptance(self, acceptance: AcceptanceCriteria, **kwargs) -> AcceptanceCriteria:
        acceptance.update(**kwargs)
        repo = self.repos.get("acceptance")
        if repo:
            repo.update(acceptance)
        if self.uow:
            self.uow.commit()
        return acceptance

    def link_requirement_test(self, link: RequirementTestLink) -> RequirementTestLink:
        repo = self.repos.get("requirement_test_link")
        if repo:
            repo.add(link)
        if self.uow:
            self.uow.commit()
        return link

    def unlink_requirement_test(self, link: RequirementTestLink) -> RequirementTestLink:
        repo = self.repos.get("requirement_test_link")
        if repo:
            repo.delete(link.id)
        if self.uow:
            self.uow.commit()
        return link

    def change_status(self, test_case: TestCase, status: TestCaseStatus, updated_by: str = "") -> TestCase:
        test_case.update(status=status, updated_by=updated_by)
        repo = self.repos.get("test_case")
        if repo:
            repo.update(test_case)
        if self.uow:
            self.uow.commit()
        return test_case
