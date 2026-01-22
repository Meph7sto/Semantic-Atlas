"""需求管理监控路由"""
from typing import Any, Dict

from flask import Blueprint, jsonify, request

from backend_business.config import settings
from backend_business.services.requirements_manage_service import RequirementsManageService

manage_bp = Blueprint("manage", __name__)
service = RequirementsManageService(dsn=settings.POSTGRES_DSN)


def _json_error(message: str, status: int = 400):
    return jsonify({"error": message}), status


def _get_actor() -> str:
    return request.headers.get("X-Actor", "") or request.args.get("actor", "") or "system"


@manage_bp.post("/projects")
def create_project():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return _json_error("Missing project name")
    description = data.get("description", "")
    actor = _get_actor()
    project = service.create_project(name=name, description=description, created_by=actor)
    service.add_audit_log(project_id=project["project_id"], actor=actor, action="create", target_type="project", target_id=project["project_id"], detail=project)
    return jsonify(project)


@manage_bp.get("/projects")
def list_projects():
    return jsonify({"projects": service.list_projects()})


@manage_bp.get("/projects/<project_id>")
def get_project(project_id: str):
    project = service.get_project(project_id)
    if not project:
        return _json_error("Project not found", 404)
    return jsonify(project)


@manage_bp.post("/projects/<project_id>/requirements")
def create_requirement(project_id: str):
    data = request.get_json(silent=True) or {}
    requirement_type = data.get("requirement_type", "")
    title = (data.get("title") or "").strip()
    if not requirement_type or not title:
        return _json_error("Missing requirement_type or title")

    actor = _get_actor()
    try:
        req = service.create_requirement(
            project_id=project_id,
            requirement_type=requirement_type,
            title=title,
            description=data.get("description", ""),
            status=data.get("status", "draft"),
            parent_id=data.get("parent_id"),
            order_index=data.get("order_index", 0),
            priority=data.get("priority"),
            assignee=data.get("assignee"),
            tags=data.get("tags"),
            due_date=data.get("due_date"),
            created_by=actor,
            source_req_id=data.get("source_req_id"),
            source_level=data.get("source_level"),
            custom_fields=data.get("custom_fields"),
        )
    except Exception as e:
        return _json_error(str(e))

    service.add_audit_log(project_id=project_id, actor=actor, action="create", target_type="requirement", target_id=req["req_id"], detail=req)
    return jsonify(req)


@manage_bp.get("/projects/<project_id>/requirements")
def list_requirements(project_id: str):
    include_deleted = request.args.get("include_deleted") in ("1", "true", "True")
    as_tree = request.args.get("tree") in ("1", "true", "True")
    if as_tree:
        tree, orphans = service.get_requirement_tree(project_id, include_deleted=include_deleted)
        return jsonify({"tree": tree, "orphans": orphans})
    return jsonify({"requirements": service.list_requirements(project_id, include_deleted=include_deleted)})


@manage_bp.post("/projects/<project_id>/requirements/import")
def import_requirements(project_id: str):
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    if not session_id:
        return _json_error("Missing session_id")
    actor = _get_actor()
    result = service.import_from_l123(session_id=session_id, project_id=project_id, created_by=actor, mapping_mode=data.get("mapping_mode", "flat"))
    service.add_audit_log(project_id=project_id, actor=actor, action="import", target_type="requirements", target_id=project_id, detail=result)
    return jsonify(result)


@manage_bp.patch("/requirements/<req_id>")
def update_requirement(req_id: str):
    data = request.get_json(silent=True) or {}
    actor = _get_actor()
    try:
        req = service.update_requirement(req_id, data, updated_by=actor)
    except Exception as e:
        return _json_error(str(e))

    service.add_audit_log(project_id=req["project_id"], actor=actor, action="update", target_type="requirement", target_id=req_id, detail=data)
    return jsonify(req)


@manage_bp.post("/requirements/<req_id>/move")
def move_requirement(req_id: str):
    data = request.get_json(silent=True) or {}
    actor = _get_actor()
    try:
        service.move_requirement(req_id, data.get("parent_id"), data.get("order_index", 0), updated_by=actor)
        req = service.get_requirement(req_id)
        if req:
            service.add_audit_log(project_id=req["project_id"], actor=actor, action="update", target_type="requirement", target_id=req_id, detail={"parent_id": data.get("parent_id"), "order_index": data.get("order_index", 0)})
        return jsonify({"success": True})
    except Exception as e:
        return _json_error(str(e))


@manage_bp.delete("/requirements/<req_id>")
def delete_requirement(req_id: str):
    cascade = request.args.get("cascade") in ("1", "true", "True")
    actor = _get_actor()
    try:
        affected = service.delete_requirement(req_id, cascade=cascade, updated_by=actor)
    except Exception as e:
        return _json_error(str(e))

    req = service.get_requirement(req_id)
    project_id = req["project_id"] if req else None
    service.add_audit_log(project_id=project_id, actor=actor, action="delete", target_type="requirement", target_id=req_id, detail={"cascade": cascade, "affected": affected})
    return jsonify({"deleted": affected})


@manage_bp.post("/projects/<project_id>/test-cases")
def create_test_case(project_id: str):
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return _json_error("Missing test case title")
    actor = _get_actor()
    tc = service.create_test_case(project_id=project_id, title=title, description=data.get("description", ""), status=data.get("status", "draft"), source=data.get("source", ""), created_by=actor)
    service.add_audit_log(project_id=project_id, actor=actor, action="create", target_type="test_case", target_id=tc["test_case_id"], detail=tc)
    return jsonify(tc)


@manage_bp.get("/projects/<project_id>/test-cases")
def list_test_cases(project_id: str):
    return jsonify({"test_cases": service.list_test_cases(project_id)})


@manage_bp.post("/requirements/<req_id>/bind-testcase")
def bind_test_case(req_id: str):
    data = request.get_json(silent=True) or {}
    test_case_id = data.get("test_case_id")
    if not test_case_id:
        return _json_error("Missing test_case_id")
    link_type = data.get("link_type", "verification")
    actor = _get_actor()
    try:
        service.bind_test_case(req_id, test_case_id, link_type)
    except Exception as e:
        return _json_error(str(e))

    req = service.get_requirement(req_id)
    if req:
        service.add_audit_log(project_id=req["project_id"], actor=actor, action="update", target_type="requirement", target_id=req_id, detail={"test_case_id": test_case_id, "link_type": link_type})
    return jsonify({"success": True})


@manage_bp.post("/projects/<project_id>/milestones")
def create_milestone(project_id: str):
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return _json_error("Missing milestone name")
    actor = _get_actor()
    try:
        milestone = service.create_milestone(
            project_id=project_id,
            name=name,
            message=data.get("message", ""),
            created_by=actor,
            milestone_type=data.get("milestone_type", "regular"),
            is_baseline=bool(data.get("is_baseline", False)),
            sprint=data.get("sprint"),
            version=data.get("version"),
            tags=data.get("tags"),
            metadata=data.get("metadata"),
        )
    except Exception as e:
        return _json_error(str(e))

    service.add_audit_log(project_id=project_id, actor=actor, action="snapshot", target_type="milestone", target_id=milestone["milestone_id"], detail=milestone)
    return jsonify(milestone)


@manage_bp.get("/projects/<project_id>/milestones")
def list_milestones(project_id: str):
    return jsonify({"milestones": service.list_milestones(project_id)})


@manage_bp.get("/milestones/<milestone_id>")
def get_milestone(milestone_id: str):
    milestone = service.get_milestone(milestone_id, include_nodes=True)
    if not milestone:
        return _json_error("Milestone not found", 404)
    return jsonify(milestone)


@manage_bp.post("/milestones/<milestone_id>/baseline")
def set_baseline(milestone_id: str):
    actor = _get_actor()
    try:
        service.set_baseline(milestone_id)
        milestone = service.get_milestone(milestone_id, include_nodes=False)
        if milestone:
            service.add_audit_log(project_id=milestone["project_id"], actor=actor, action="baseline", target_type="milestone", target_id=milestone_id, detail=milestone)
        return jsonify({"success": True})
    except Exception as e:
        return _json_error(str(e))


@manage_bp.post("/milestones/compare")
def compare_milestones():
    data = request.get_json(silent=True) or {}
    from_id = data.get("from_milestone_id")
    to_id = data.get("to_milestone_id")
    if not from_id or not to_id:
        return _json_error("Missing from_milestone_id or to_milestone_id")
    try:
        diff = service.compare_milestones(from_id, to_id)
        return jsonify(diff)
    except Exception as e:
        return _json_error(str(e))


@manage_bp.post("/projects/<project_id>/milestones/link")
def add_milestone_edge(project_id: str):
    data = request.get_json(silent=True) or {}
    actor = _get_actor()
    try:
        edge = service.add_milestone_edge(
            project_id=project_id,
            from_milestone_id=data.get("from_milestone_id"),
            to_milestone_id=data.get("to_milestone_id"),
            relation_type=data.get("relation_type", "activity"),
            message=data.get("message", ""),
            created_by=actor,
        )
    except Exception as e:
        return _json_error(str(e))

    service.add_audit_log(project_id=project_id, actor=actor, action="update", target_type="milestone_edge", target_id=str(edge.get("id")), detail=edge)
    return jsonify(edge)


@manage_bp.get("/projects/<project_id>/milestone-graph")
def list_milestone_graph(project_id: str):
    return jsonify({"edges": service.list_milestone_graph(project_id)})


@manage_bp.post("/projects/<project_id>/branches")
def create_branch(project_id: str):
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    base_milestone_id = data.get("base_milestone_id")
    if not name or not base_milestone_id:
        return _json_error("Missing name or base_milestone_id")
    actor = _get_actor()
    branch = service.create_branch(project_id, base_milestone_id, name, actor)
    service.add_audit_log(project_id=project_id, actor=actor, action="branch_create", target_type="branch", target_id=branch["branch_id"], detail=branch)
    return jsonify(branch)


@manage_bp.get("/projects/<project_id>/branches")
def list_branches(project_id: str):
    return jsonify({"branches": service.list_branches(project_id)})


@manage_bp.post("/branches/<branch_id>/changes")
def add_change_set(branch_id: str):
    data = request.get_json(silent=True) or {}
    change_type = data.get("change_type")
    if not change_type:
        return _json_error("Missing change_type")
    actor = _get_actor()
    change = service.add_change_set(
        branch_id=branch_id,
        change_type=change_type,
        requirement_id=data.get("requirement_id"),
        before_data=data.get("before_data"),
        after_data=data.get("after_data"),
        created_by=actor,
    )
    return jsonify(change)


@manage_bp.get("/branches/<branch_id>/changes")
def list_change_sets(branch_id: str):
    return jsonify({"changes": service.list_change_sets(branch_id)})


@manage_bp.post("/branches/<branch_id>/impact")
def create_impact_report(branch_id: str):
    actor = _get_actor()
    report = service.create_impact_report(branch_id, actor)
    return jsonify(report)


@manage_bp.post("/branches/<branch_id>/merge")
def create_merge_request(branch_id: str):
    data = request.get_json(silent=True) or {}
    target_milestone_id = data.get("target_milestone_id")
    if not target_milestone_id:
        return _json_error("Missing target_milestone_id")
    actor = _get_actor()
    merge = service.create_merge_request(branch_id, target_milestone_id, actor)
    return jsonify(merge)


@manage_bp.get("/projects/<project_id>/audits")
def list_audits(project_id: str):
    limit = int(request.args.get("limit", 100))
    return jsonify({"logs": service.list_audit_logs(project_id, limit=limit)})
