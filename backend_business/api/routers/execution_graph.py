"""
执行拓扑图路由 - FastAPI 版本
"""

from typing import Optional

from fastapi import APIRouter, Depends, Request

from backend_business.config import settings
from backend_business.api.deps.auth import get_current_user
from backend_business.api.http.errors import ErrorResponse
from backend_business.api.routers.schemas.execution_graph_schemas import (
    CreateGraphRequest,
    UpdateGraphRequest,
    CreateNodeRequest,
    UpdateNodeRequest,
    CreateEdgeRequest,
    UpdateEdgeRequest,
)
from backend_business.services.execution_graph_service import (
    ExecutionGraphService,
)

router = APIRouter(prefix="/api/v2/execution-topology", tags=["execution-topology"])

# 初始化服务
_service = ExecutionGraphService(dsn=settings.POSTGRES_DSN)


# ========================
# 辅助函数
# ========================


def _get_actor(request: Request, current_user: Optional[dict] = None) -> str:
    """
    获取操作者标识
    优先使用认证用户ID，其次使用 X-Actor header，最后使用 "system"
    """
    if current_user:
        return current_user.get("user_id", "system")

    actor = request.headers.get("X-Actor", "")
    if actor:
        return actor

    actor = request.query_params.get("actor", "")
    if actor:
        return actor

    return "system"


# ========================
# Graph Endpoints
# ========================


@router.post("/projects/{project_id}")
async def create_graph(
    project_id: str,
    req: CreateGraphRequest,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """创建新的执行拓扑图"""
    actor = _get_actor(request, current_user)
    try:
        graph = _service.create_execution_graph(
            project_id=project_id,
            name=req.name,
            description=req.description,
            created_by=actor,
        )
        return graph
    except ValueError as e:
        raise ErrorResponse(str(e), 400)


@router.get("/projects/{project_id}")
async def list_graphs(
    project_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """列出项目的所有执行拓扑图"""
    try:
        graphs = _service.list_execution_graphs(project_id=project_id)
        return {"graphs": graphs}
    except ValueError as e:
        raise ErrorResponse(str(e), 400)


@router.get("/{graph_id}")
async def get_graph(
    graph_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """获取指定的执行拓扑图"""
    try:
        graph = _service.get_execution_graph(graph_id=graph_id)
        if not graph:
            raise ErrorResponse("图不存在或已删除", 404)
        return graph
    except ValueError as e:
        raise ErrorResponse(str(e), 400)


@router.patch("/{graph_id}")
async def update_graph(
    graph_id: str,
    req: UpdateGraphRequest,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """更新执行拓扑图"""
    actor = _get_actor(request, current_user)
    try:
        graph = _service.update_execution_graph(
            graph_id=graph_id,
            name=req.name,
            description=req.description,
            status=req.status,
            layout_json=req.layout_json,
            meta_json=req.meta_json,
            updated_by=actor,
        )
        if not graph:
            raise ErrorResponse("图不存在或已删除", 404)
        return graph
    except ValueError as e:
        raise ErrorResponse(str(e), 400)


@router.delete("/{graph_id}")
async def delete_graph(
    graph_id: str,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """删除执行拓扑图（软删除）"""
    actor = _get_actor(request, current_user)
    try:
        deleted = _service.delete_execution_graph(graph_id=graph_id, updated_by=actor)
        if not deleted:
            raise ErrorResponse("图不存在或已删除", 404)
        return {"message": "删除成功"}
    except ValueError as e:
        raise ErrorResponse(str(e), 400)


# ========================
# Node Endpoints
# ========================


@router.post("/{graph_id}/nodes")
async def create_node(
    graph_id: str,
    req: CreateNodeRequest,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """在图中创建节点"""
    actor = _get_actor(request, current_user)
    try:
        node = _service.create_node(
            graph_id=graph_id,
            node_key=req.node_key,
            label=req.label,
            node_type=req.node_type,
            role_type=req.role_type,
            config_json=req.config_json,
            input_schema_json=req.input_schema_json,
            output_schema_json=req.output_schema_json,
            order_index=req.order_index,
            created_by=actor,
        )
        return node
    except ValueError as e:
        raise ErrorResponse(str(e), 400)


@router.patch("/nodes/{node_id}")
async def update_node(
    node_id: str,
    req: UpdateNodeRequest,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """更新节点"""
    actor = _get_actor(request, current_user)
    try:
        node = _service.update_node(
            node_id=node_id,
            label=req.label,
            node_type=req.node_type,
            role_type=req.role_type,
            config_json=req.config_json,
            input_schema_json=req.input_schema_json,
            output_schema_json=req.output_schema_json,
            order_index=req.order_index,
            updated_by=actor,
        )
        if not node:
            raise ErrorResponse("节点不存在或已删除", 404)
        return node
    except ValueError as e:
        raise ErrorResponse(str(e), 400)


@router.delete("/nodes/{node_id}")
async def delete_node(
    node_id: str,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """删除节点"""
    actor = _get_actor(request, current_user)
    try:
        deleted = _service.delete_node(node_id=node_id, updated_by=actor)
        if not deleted:
            raise ErrorResponse("节点不存在或已删除", 404)
        return {"message": "删除成功"}
    except ValueError as e:
        raise ErrorResponse(str(e), 400)


# ========================
# Edge Endpoints
# ========================


@router.post("/{graph_id}/edges")
async def create_edge(
    graph_id: str,
    req: CreateEdgeRequest,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """在图中创建边"""
    actor = _get_actor(request, current_user)
    try:
        edge = _service.create_edge(
            graph_id=graph_id,
            source_node_id=req.source_node_id,
            target_node_id=req.target_node_id,
            edge_type=req.edge_type,
            label=req.label,
            condition_expr=req.condition_expr,
            config_json=req.config_json,
            order_index=req.order_index,
            created_by=actor,
        )
        return edge
    except ValueError as e:
        raise ErrorResponse(str(e), 400)


@router.patch("/edges/{edge_id}")
async def update_edge(
    edge_id: str,
    req: UpdateEdgeRequest,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """更新边"""
    actor = _get_actor(request, current_user)
    try:
        edge = _service.update_edge(
            edge_id=edge_id,
            label=req.label,
            edge_type=req.edge_type,
            condition_expr=req.condition_expr,
            config_json=req.config_json,
            order_index=req.order_index,
            updated_by=actor,
        )
        if not edge:
            raise ErrorResponse("边不存在或已删除", 404)
        return edge
    except ValueError as e:
        raise ErrorResponse(str(e), 400)


@router.delete("/edges/{edge_id}")
async def delete_edge(
    edge_id: str,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """删除边"""
    actor = _get_actor(request, current_user)
    try:
        deleted = _service.delete_edge(edge_id=edge_id, updated_by=actor)
        if not deleted:
            raise ErrorResponse("边不存在或已删除", 404)
        return {"message": "删除成功"}
    except ValueError as e:
        raise ErrorResponse(str(e), 400)


# ========================
# Aggregated Endpoint
# ========================


@router.get("/{graph_id}/detail")
async def get_graph_detail(
    graph_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """获取图的完整信息（包括节点和边）"""
    try:
        detail = _service.get_graph_detail(graph_id=graph_id)
        if not detail["graph"]:
            raise ErrorResponse("图不存在或已删除", 404)
        return detail
    except ValueError as e:
        raise ErrorResponse(str(e), 400)
