"""
FastAPI permission reviews/change/baseline lock contract tests.
"""

import os
import sys
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.api.deps.auth import get_current_user
from backend_business.api.http.errors import error_response_handler, validation_error_handler
from backend_business.api.routers import permission


class _StubPermissionDB:
    def __init__(self):
        self.review_assignments: dict[str, dict[str, Any]] = {}
        self.change_requests: dict[str, dict[str, Any]] = {
            "cr-1": {"request_id": "cr-1", "project_id": "p1", "status": "pending"}
        }
        self.baselines: dict[str, dict[str, Any]] = {
            "11": {"id": 11, "project_id": "p1", "version": "1.0.0", "locked": False}
        }
        self.permissions: dict[tuple[str, str], set[str]] = {
            ("p1", "u-op"): {"req:change_request", "req:change_approve", "req:change_reject", "req:baseline_manage"},
        }

    def get_user_by_id(self, user_id: str):
        if user_id in {"u-op", "reviewer-1"}:
            return {"user_id": user_id, "username": user_id}
        return None

    def check_permission(self, project_id: str, user_id: str, permission_code: str):
        return permission_code in self.permissions.get((project_id, user_id), set())

    def create_review_assignment(self, requirement_id: str, reviewer_id: str, initiated_by: str, seq: int = 1, comment: str | None = None):
        aid = f"rv-{len(self.review_assignments)+1}"
        item = {
            "assignment_id": aid,
            "requirement_id": requirement_id,
            "reviewer_id": reviewer_id,
            "initiated_by": initiated_by,
            "seq": seq,
            "comment": comment,
            "status": "pending",
        }
        self.review_assignments[aid] = item
        return item

    def list_requirement_reviews(self, requirement_id: str, status: str | None = None):
        rows = [r for r in self.review_assignments.values() if r["requirement_id"] == requirement_id]
        if status:
            rows = [r for r in rows if r["status"] == status]
        return rows

    def approve_review(self, assignment_id: str, user_id: str, comment: str | None):
        item = self.review_assignments.get(assignment_id)
        if not item:
            return None
        item = dict(item)
        item["status"] = "approved"
        item["approved_by"] = user_id
        item["comment"] = comment
        self.review_assignments[assignment_id] = item
        return item

    def reject_review(self, assignment_id: str, user_id: str, comment: str | None):
        item = self.review_assignments.get(assignment_id)
        if not item:
            return None
        item = dict(item)
        item["status"] = "rejected"
        item["rejected_by"] = user_id
        item["comment"] = comment
        self.review_assignments[assignment_id] = item
        return item

    def withdraw_review(self, assignment_id: str, user_id: str):
        _ = user_id
        item = self.review_assignments.get(assignment_id)
        if not item:
            return None
        item = dict(item)
        item["status"] = "withdrawn"
        self.review_assignments[assignment_id] = item
        return item

    def get_user_pending_reviews(self, user_id: str, project_id: str | None = None):
        _ = project_id
        return [r for r in self.review_assignments.values() if r["reviewer_id"] == user_id and r["status"] == "pending"]

    def get_baseline(self, baseline_id: int | str):
        return self.baselines.get(str(baseline_id))

    def lock_baseline(self, baseline_id: str, user_id: str):
        _ = user_id
        baseline = self.baselines.get(str(baseline_id))
        if not baseline:
            return None
        baseline["locked"] = True
        return dict(baseline)

    def unlock_baseline(self, baseline_id: str, user_id: str):
        _ = user_id
        baseline = self.baselines.get(str(baseline_id))
        if not baseline:
            return None
        baseline["locked"] = False
        return dict(baseline)

    def get_baseline_by_version(self, project_id: str, version: str):
        for baseline in self.baselines.values():
            if baseline["project_id"] == project_id and baseline["version"] == version:
                return baseline
        return None

    def create_change_request(self, requirement_id: str, baseline_id: int, requested_by: str, reason: str, change_summary: str):
        req_id = f"cr-{len(self.change_requests)+1}"
        baseline = self.get_baseline(baseline_id)
        item = {
            "request_id": req_id,
            "project_id": baseline["project_id"] if baseline else "p1",
            "requirement_id": requirement_id,
            "baseline_id": baseline_id,
            "requested_by": requested_by,
            "reason": reason,
            "change_summary": change_summary,
            "status": "pending",
        }
        self.change_requests[req_id] = item
        return item

    def list_requirement_change_requests(self, requirement_id: str, status: str | None = None):
        rows = [r for r in self.change_requests.values() if r.get("requirement_id") == requirement_id]
        if status:
            rows = [r for r in rows if r["status"] == status]
        return rows

    def get_change_request(self, request_id: str):
        return self.change_requests.get(request_id)

    def reject_change_request(self, request_id: str, user_id: str, review_comment: str | None):
        item = self.change_requests.get(request_id)
        if not item:
            return None
        item = dict(item)
        item["status"] = "rejected"
        item["rejected_by"] = user_id
        item["review_comment"] = review_comment
        self.change_requests[request_id] = item
        return item

    def get_accessible_projects(self, user_id: str):
        if user_id == "u-op":
            return ["p1", "p2"]
        return []

    def get_pending_change_requests(self, project_id: str | None = None):
        rows = [r for r in self.change_requests.values() if r.get("status") == "pending"]
        if project_id is not None:
            rows = [r for r in rows if r.get("project_id") == project_id]
        return rows


@pytest.fixture
def fastapi_client(monkeypatch):
    stub = _StubPermissionDB()
    monkeypatch.setattr(permission, "db_service", stub)

    app = FastAPI()
    app.include_router(permission.router)
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "u-op", "role": "member"}
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(HTTPException, error_response_handler)
    app.add_exception_handler(Exception, error_response_handler)

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, stub


def test_review_endpoints_contract(fastapi_client):
    client, _ = fastapi_client

    create = client.post(
        "/api/v2/permission/requirements/r1/reviews",
        json={"reviewer_id": "reviewer-1", "seq": 1, "comment": "please review"},
    )
    assert create.status_code == 200
    assignment_id = create.json()["assignment_id"]

    listed = client.get("/api/v2/permission/requirements/r1/reviews")
    assert listed.status_code == 200
    assert listed.json()[0]["assignment_id"] == assignment_id

    approved = client.post(
        f"/api/v2/permission/reviews/{assignment_id}/approve",
        json={"comment": "ok"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    rejected = client.post(
        f"/api/v2/permission/reviews/{assignment_id}/reject",
        json={"comment": "no"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    withdrawn = client.post(f"/api/v2/permission/reviews/{assignment_id}/withdraw")
    assert withdrawn.status_code == 200
    assert withdrawn.json()["status"] == "withdrawn"

    pending = client.get("/api/v2/permission/user/pending-reviews")
    assert pending.status_code == 200
    assert isinstance(pending.json(), list)


def test_baseline_lock_unlock_and_change_request_contract(fastapi_client):
    client, stub = fastapi_client

    locked = client.post("/api/v2/permission/baselines/11/lock")
    assert locked.status_code == 200
    assert locked.json()["locked"] is True

    unlocked = client.post("/api/v2/permission/baselines/11/unlock")
    assert unlocked.status_code == 200
    assert unlocked.json()["locked"] is False

    created = client.post(
        "/api/v2/permission/requirements/r1/change-requests",
        json={"baseline_id": 11, "reason": "need update", "change_summary": "summary"},
    )
    assert created.status_code == 200
    created_req_id = created.json()["request_id"]

    listed = client.get("/api/v2/permission/requirements/r1/change-requests")
    assert listed.status_code == 200
    assert listed.json()[0]["request_id"] == created_req_id

    rejected = client.post(
        f"/api/v2/permission/change-requests/{created_req_id}/reject",
        json={"review_comment": "not allowed"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    # keep one pending request and verify list pending aggregation path
    stub.change_requests["cr-pending"] = {"request_id": "cr-pending", "project_id": "p1", "status": "pending"}
    pending = client.get("/api/v2/permission/change-requests/pending")
    assert pending.status_code == 200
    assert any(item["request_id"] == "cr-pending" for item in pending.json())
