"""
FastAPI manage extended route contract tests.
"""

from typing import Any

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError


from backend_business.api.http.errors import error_response_handler, validation_error_handler
from backend_business.api.routers import manage


class _StubManageDB:
    def get_user_by_id(self, user_id: str):
        return {"user_id": user_id, "role": "admin"}

    def can_access_project(self, project_id: str, user_id: str, user: dict):
        _ = project_id, user_id, user
        return True

    def can_edit_project(self, project_id: str, user_id: str, user: dict):
        _ = project_id, user_id, user
        return True


class _StubManageService:
    def __init__(self):
        self.requirements = {"r-1": {"req_id": "r-1", "project_id": "p-1", "title": "Req1"}}
        self.test_cases = [{"test_case_id": "tc-1", "project_id": "p-1", "title": "TC1"}]
        self.milestones = {
            "m-1": {"milestone_id": "m-1", "project_id": "p-1", "name": "M1"},
            "m-2": {"milestone_id": "m-2", "project_id": "p-1", "name": "M2"},
        }
        self.branches = [{"ref_id": "b-1", "project_id": "p-1", "ref_name": "main"}]
        self.audit_logs: list[dict[str, Any]] = []

    def add_audit_log(self, **kwargs):
        self.audit_logs.append(kwargs)

    def import_from_session(self, session_id: str, project_id: str, created_by: str, mapping_mode: str):
        _ = created_by
        return {
            "inserted": 2,
            "inserted_l123": 1,
            "inserted_l4": 1,
            "total": 2,
            "mapping_mode": mapping_mode,
            "session_id": session_id,
            "project_id": project_id,
        }

    def get_requirement(self, req_id: str):
        req = self.requirements.get(req_id)
        return dict(req) if req else None

    def create_test_case(self, project_id: str, title: str, description: str, status: str, source: str, created_by: str):
        _ = description, status, source, created_by
        tc = {"test_case_id": f"tc-{len(self.test_cases)+1}", "project_id": project_id, "title": title}
        self.test_cases.append(tc)
        return tc

    def list_test_cases(self, project_id: str):
        return [tc for tc in self.test_cases if tc["project_id"] == project_id]

    def bind_test_case(self, req_id: str, test_case_id: str, link_type: str):
        if req_id not in self.requirements:
            raise ValueError("需求不存在")
        _ = test_case_id, link_type

    def create_milestone(self, project_id: str, name: str, message: str, created_by: str, **kwargs):
        _ = message, created_by, kwargs
        milestone_id = f"m-{len(self.milestones)+1}"
        milestone = {"milestone_id": milestone_id, "project_id": project_id, "name": name}
        self.milestones[milestone_id] = milestone
        return milestone

    def list_milestones(self, project_id: str):
        return [m for m in self.milestones.values() if m["project_id"] == project_id]

    def get_milestone(self, milestone_id: str, include_nodes: bool = False):
        m = self.milestones.get(milestone_id)
        if not m:
            return None
        out = dict(m)
        if include_nodes:
            out["nodes"] = []
            out["relations"] = []
        return out

    def set_baseline(self, milestone_id: str):
        if milestone_id not in self.milestones:
            raise ValueError("Milestone not found")
        self.milestones[milestone_id]["is_baseline"] = True

    def compare_milestones(self, from_milestone_id: str, to_milestone_id: str):
        return {
            "from_milestone_id": from_milestone_id,
            "to_milestone_id": to_milestone_id,
            "summary": {"added": 0, "deleted": 0, "modified": 0},
        }

    def add_milestone_edge(self, project_id: str, from_milestone_id: str, to_milestone_id: str, relation_type: str, message: str, created_by: str):
        _ = message, created_by
        return {
            "id": 1,
            "project_id": project_id,
            "from_milestone_id": from_milestone_id,
            "to_milestone_id": to_milestone_id,
            "relation_type": relation_type,
        }

    def list_milestone_graph(self, project_id: str):
        return {"nodes": [{"id": "m-1"}], "edges": [{"from": "m-1", "to": "m-2"}], "project_id": project_id}

    def create_branch(self, project_id: str, base_milestone_id: str, name: str, created_by: str):
        _ = created_by
        branch = {"ref_id": f"b-{len(self.branches)+1}", "project_id": project_id, "ref_name": name, "base_milestone_id": base_milestone_id}
        self.branches.append(branch)
        return branch

    def list_branches(self, project_id: str):
        return [b for b in self.branches if b["project_id"] == project_id]

    def add_change_set(self, branch_id: str, change_type: str, requirement_id: str | None, before_data: dict | None, after_data: dict | None, created_by: str):
        _ = created_by
        return {"change_id": "chg-1", "branch_id": branch_id, "change_type": change_type, "requirement_id": requirement_id, "before_data": before_data, "after_data": after_data}

    def list_change_sets(self, branch_id: str):
        return [{"change_id": "chg-1", "branch_id": branch_id}]

    def create_impact_report(self, branch_id: str, actor: str):
        return {"report_id": "impact-1", "branch_id": branch_id, "created_by": actor, "status": "pending"}

    def create_merge_request(self, branch_id: str, target_milestone_id: str, actor: str):
        return {"merge_id": "mr-1", "branch_id": branch_id, "target_milestone_id": target_milestone_id, "created_by": actor}

    def merge_branches(self, project_id: str, source_branch: str, target_branch: str, created_by: str, message: str):
        _ = created_by
        return {"project_id": project_id, "source_branch": source_branch, "target_branch": target_branch, "message": message, "conflict_count": 0, "conflicts": []}

    def list_audit_logs(self, project_id: str, limit: int = 100):
        return [{"id": 1, "project_id": project_id, "action": "create"}][:limit]


@pytest.fixture
async def fastapi_client(monkeypatch):
    stub_db = _StubManageDB()
    stub_service = _StubManageService()
    monkeypatch.setattr(manage, "db_service", stub_db)
    monkeypatch.setattr(manage, "_service", stub_service)
    monkeypatch.setattr(manage, "_get_project_id_by_branch", lambda branch_id: "p-1" if branch_id.startswith("b-") else None)

    app = build_test_app(manage.router)
    app.dependency_overrides[manage.get_current_user] = lambda: {"user_id": "admin-1", "role": "admin"}

    async with async_client(app) as client:
        yield client, stub_service


async def test_import_and_test_case_and_bind_contract(fastapi_client):
    client, _ = fastapi_client

    imported = await client.post(
        "/api/v2/manage/projects/p-1/requirements/import",
        json={"session_id": "s-1", "mapping_mode": "tree"},
    )
    assert imported.status_code == 200
    assert imported.json()["inserted"] == 2

    create_tc = await client.post(
        "/api/v2/manage/projects/p-1/test-cases",
        json={"title": "TC new", "description": "d", "status": "draft", "source": "manual"},
    )
    assert create_tc.status_code == 200
    tc_id = create_tc.json()["test_case_id"]

    list_tc = await client.get("/api/v2/manage/projects/p-1/test-cases")
    assert list_tc.status_code == 200
    assert any(tc["test_case_id"] == tc_id for tc in list_tc.json()["test_cases"])

    bind = await client.post(
        "/api/v2/manage/requirements/r-1/bind-testcase",
        json={"test_case_id": tc_id, "link_type": "verification"},
    )
    assert bind.status_code == 200
    assert bind.json()["success"] is True


async def test_milestone_endpoints_contract(fastapi_client):
    client, _ = fastapi_client

    created = await client.post(
        "/api/v2/manage/projects/p-1/milestones",
        json={"name": "M3", "message": "snapshot"},
    )
    assert created.status_code == 200
    milestone_id = created.json()["milestone_id"]

    listed = await client.get("/api/v2/manage/projects/p-1/milestones")
    assert listed.status_code == 200
    assert any(m["milestone_id"] == milestone_id for m in listed.json()["milestones"])

    detail = await client.get(f"/api/v2/manage/milestones/{milestone_id}")
    assert detail.status_code == 200
    assert detail.json()["milestone_id"] == milestone_id

    baseline = await client.post(f"/api/v2/manage/milestones/{milestone_id}/baseline")
    assert baseline.status_code == 200
    assert baseline.json()["success"] is True

    compare = await client.post(
        "/api/v2/manage/milestones/compare",
        json={"from_milestone_id": "m-1", "to_milestone_id": "m-2"},
    )
    assert compare.status_code == 200
    assert compare.json()["summary"]["added"] == 0

    link = await client.post(
        "/api/v2/manage/projects/p-1/milestones/link",
        json={
            "from_milestone_id": "m-1",
            "to_milestone_id": "m-2",
            "relation_type": "activity",
            "message": "link",
        },
    )
    assert link.status_code == 200
    assert link.json()["project_id"] == "p-1"

    graph = await client.get("/api/v2/manage/projects/p-1/milestone-graph")
    assert graph.status_code == 200
    assert graph.json()["nodes"][0]["id"] == "m-1"


async def test_branch_and_audit_endpoints_contract(fastapi_client):
    client, _ = fastapi_client

    create_branch = await client.post(
        "/api/v2/manage/projects/p-1/branches",
        json={"name": "feature-x", "base_milestone_id": "m-1"},
    )
    assert create_branch.status_code == 200
    branch_id = create_branch.json()["ref_id"]

    list_branch = await client.get("/api/v2/manage/projects/p-1/branches")
    assert list_branch.status_code == 200
    assert any(b["ref_id"] == branch_id for b in list_branch.json()["branches"])

    add_change = await client.post(
        f"/api/v2/manage/branches/{branch_id}/changes",
        json={
            "change_type": "update",
            "requirement_id": "r-1",
            "before_data": {"title": "old"},
            "after_data": {"title": "new"},
        },
    )
    assert add_change.status_code == 200
    assert add_change.json()["change_id"] == "chg-1"

    list_change = await client.get(f"/api/v2/manage/branches/{branch_id}/changes")
    assert list_change.status_code == 200
    assert list_change.json()["changes"][0]["change_id"] == "chg-1"

    impact = await client.post(f"/api/v2/manage/branches/{branch_id}/impact")
    assert impact.status_code == 200
    assert impact.json()["report_id"] == "impact-1"

    merge_req = await client.post(
        f"/api/v2/manage/branches/{branch_id}/merge",
        json={"target_milestone_id": "m-2"},
    )
    assert merge_req.status_code == 200
    assert merge_req.json()["merge_id"] == "mr-1"

    merged = await client.post(
        "/api/v2/manage/projects/p-1/branches/merge",
        json={"source_branch": "feature-x", "target_branch": "main", "message": "merge"},
    )
    assert merged.status_code == 200
    assert merged.json()["conflict_count"] == 0

    audits = await client.get("/api/v2/manage/projects/p-1/audits?limit=10")
    assert audits.status_code == 200
    assert audits.json()["logs"][0]["project_id"] == "p-1"

