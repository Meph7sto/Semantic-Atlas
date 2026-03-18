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
    CreateContainerRequest,
    UpdateContainerRequest,
    CreateSubgraphRequest,
    UpdateSubgraphRequest,
    CreateNodeRequest,
    UpdateNodeRequest,
    CreateEdgeRequest,
    UpdateEdgeRequest,
    ExecuteTopologyRequest,
)
from backend_business.services.agent.execution_graph_service import (
    ExecutionGraphService,
)
from backend_business.services.db_service import db_service
from backend_business.services.agent.execution.topology_execution_service import (
    TopologyExecutionService,
)
from backend_business.services.agent.topology import (
    GraphStructureBuilder,
    StructureValidator,
    TopologyStructureSerializer,
)

router = APIRouter(prefix="/api/v2/execution-topology", tags=["execution-topology"])

# 初始化服务
_service = ExecutionGraphService(dsn=settings.POSTGRES_DSN)
_topology_execution_service = TopologyExecutionService(execution_graph_service=_service)


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
# Container Endpoints
# ========================


@router.post("/{graph_id}/containers")
async def create_container(
    graph_id: str,
    req: CreateContainerRequest,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """在图中创建容器"""
    actor = _get_actor(request, current_user)
    try:
        container = _service.create_container(
            graph_id=graph_id,
            container_key=req.container_key,
            label=req.label,
            role_type=req.role_type,
            config_json=req.config_json,
            order_index=req.order_index,
            created_by=actor,
        )
        return container
    except ValueError as e:
        raise ErrorResponse(str(e), 400)


@router.patch("/containers/{container_id}")
async def update_container(
    container_id: str,
    req: UpdateContainerRequest,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """更新容器"""
    actor = _get_actor(request, current_user)
    try:
        container = _service.update_container(
            container_id=container_id,
            label=req.label,
            role_type=req.role_type,
            config_json=req.config_json,
            order_index=req.order_index,
            updated_by=actor,
        )
        if not container:
            raise ErrorResponse("容器不存在或已删除", 404)
        return container
    except ValueError as e:
        raise ErrorResponse(str(e), 400)


@router.delete("/containers/{container_id}")
async def delete_container(
    container_id: str,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """删除容器"""
    actor = _get_actor(request, current_user)
    try:
        deleted = _service.delete_container(container_id=container_id, updated_by=actor)
        if not deleted:
            raise ErrorResponse("容器不存在或已删除", 404)
        return {"message": "删除成功"}
    except ValueError as e:
        raise ErrorResponse(str(e), 400)


# ========================
# Subgraph Endpoints
# ========================


@router.post("/{graph_id}/subgraphs")
async def create_subgraph(
    graph_id: str,
    req: CreateSubgraphRequest,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """在图中创建子图"""
    actor = _get_actor(request, current_user)
    try:
        subgraph = _service.create_subgraph(
            graph_id=graph_id,
            container_id=req.container_id,
            subgraph_key=req.subgraph_key,
            label=req.label,
            task_description=req.task_description,
            order_index=req.order_index,
            config_json=req.config_json,
            created_by=actor,
        )
        return subgraph
    except ValueError as e:
        raise ErrorResponse(str(e), 400)


@router.get("/{graph_id}/subgraphs")
async def list_subgraphs(
    graph_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """列出图中的子图"""
    try:
        subgraphs = _service.list_subgraphs(graph_id=graph_id)
        return {"subgraphs": subgraphs}
    except ValueError as e:
        raise ErrorResponse(str(e), 400)


@router.patch("/subgraphs/{subgraph_id}")
async def update_subgraph(
    subgraph_id: str,
    req: UpdateSubgraphRequest,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """更新子图"""
    actor = _get_actor(request, current_user)
    try:
        subgraph = _service.update_subgraph(
            subgraph_id=subgraph_id,
            label=req.label,
            task_description=req.task_description,
            order_index=req.order_index,
            config_json=req.config_json,
            updated_by=actor,
        )
        if not subgraph:
            raise ErrorResponse("子图不存在或已删除", 404)
        return subgraph
    except ValueError as e:
        raise ErrorResponse(str(e), 400)


@router.delete("/subgraphs/{subgraph_id}")
async def delete_subgraph(
    subgraph_id: str,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """删除子图"""
    actor = _get_actor(request, current_user)
    try:
        deleted = _service.delete_subgraph(subgraph_id=subgraph_id, updated_by=actor)
        if not deleted:
            raise ErrorResponse("子图不存在或已删除", 404)
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
            container_id=req.container_id,
            subgraph_id=req.subgraph_id,
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
            container_id=req.container_id,
            subgraph_id=req.subgraph_id,
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


@router.post("/{graph_id}/execute")
async def execute_topology_template(
    graph_id: str,
    req: ExecuteTopologyRequest,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """从拓扑模板创建运行时图并执行。"""
    actor = _get_actor(request, current_user)
    try:
        return _topology_execution_service.execute_template(
            template_graph_id=graph_id,
            input_payload=req.input_payload,
            actor=actor,
            max_steps=req.max_steps,
            runtime_graph_name=req.runtime_graph_name,
            runtime_graph_description=req.runtime_graph_description,
        )
    except ValueError as e:
        raise ErrorResponse(str(e), 400)


# ========================
# Topology Structure Endpoints
# ========================


@router.get("/{graph_id}/structure")
async def get_topology_structure(
    graph_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """获取编译的拓扑结构

    This endpoint loads topology from database and returns
    compiled runtime structure with containers and edges.
    """
    try:
        # Load graph from database
        graph = _service.get_execution_graph(graph_id)
        if not graph:
            raise ErrorResponse("Graph not found", 404)

        # Load nodes and edges from database
        nodes = _service.list_execution_nodes(graph_id)
        containers = _service.list_execution_containers(graph_id)
        edges = _service.list_execution_edges(graph_id)

        # Build topology structure
        builder = GraphStructureBuilder(db_service)
        structure = builder.load_topology(
            graph_id, graph, nodes, edges, containers
        )

        # Validate structure
        validator = StructureValidator()
        validation = validator.validate(structure)
        structure.validation_status = "valid" if validation.is_valid else "invalid"
        structure.validation_errors = validation.errors

        return {
            "success": True,
            "structure": {
                "graph_id": structure.graph_id,
                "graph_name": structure.graph_name,
                "containers": [c.to_dict() for c in structure.containers],
                "edges": [e.to_dict() for e in structure.edges],
                "start_containers": [c.container_id for c in structure.start_containers],
                "end_containers": [c.container_id for c in structure.end_containers],
                "validation_status": structure.validation_status,
                "validation_errors": structure.validation_errors,
            },
        }
    except ErrorResponse:
        raise
    except Exception as e:
        raise ErrorResponse(f"Error getting topology structure: {e}", 500)


@router.post("/{graph_id}/validate")
async def validate_topology_structure(
    graph_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """验证拓扑结构

    This endpoint loads and validates topology structure.
    """
    try:
        # Load topology structure
        graph = _service.get_execution_graph(graph_id)
        if not graph:
            raise ErrorResponse("Graph not found", 404)

        nodes = _service.list_execution_nodes(graph_id)
        containers = _service.list_execution_containers(graph_id)
        edges = _service.list_execution_edges(graph_id)

        builder = GraphStructureBuilder(db_service)
        structure = builder.load_topology(
            graph_id, graph, nodes, edges, containers
        )

        # Validate structure
        validator = StructureValidator()
        validation = validator.validate(structure)

        return {
            "success": True,
            "result": {
                "is_valid": validation.is_valid,
                "errors": validation.errors,
                "warnings": validation.warnings,
            },
        }
    except ErrorResponse:
        raise
    except Exception as e:
        raise ErrorResponse(f"Error validating topology structure: {e}", 500)


@router.get("/{graph_id}/containers")
async def get_containers(
    graph_id: str,
    node_type: Optional[str] = None,
    role_type: Optional[str] = None,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """获取所有容器定义

    This endpoint returns list of AgentContainer objects
    for specified graph, optionally filtered by type or role.

    Query Parameters:
        node_type: Filter by node type (optional)
        role_type: Filter by role type (optional)
    """
    try:
        containers = _service.list_execution_containers(graph_id)
        nodes = _service.list_execution_nodes(graph_id)

        # Apply filters from query parameters
        if role_type:
            containers = [c for c in containers if c.get("role_type") == role_type]
        if node_type:
            node_types_by_container = {}
            for node in nodes:
                cid = node.get("container_id")
                if not cid:
                    continue
                if cid not in node_types_by_container:
                    node_types_by_container[cid] = set()
                node_types_by_container[cid].add(node.get("node_type"))
            containers = [
                c for c in containers if node_type in node_types_by_container.get(c.get("container_id"), set())
            ]

        return {
            "success": True,
            "containers": containers,
        }
    except Exception as e:
        raise ErrorResponse(f"Error getting containers: {e}", 500)


@router.get("/{graph_id}/export")
async def export_topology(
    graph_id: str,
    format: str = "json",
    current_user: Optional[dict] = Depends(get_current_user),
):
    """导出拓扑供代理使用

    This endpoint exports topology structure in a format
    that can be understood and taken over by intelligent agents.

    Query Parameters:
        format: Export format (only 'json' supported)
    """
    try:
        if format != "json":
            raise ErrorResponse("Only 'json' format is supported", 400)

        # Load topology structure
        graph = _service.get_execution_graph(graph_id)
        if not graph:
            raise ErrorResponse("Graph not found", 404)

        nodes = _service.list_execution_nodes(graph_id)
        containers = _service.list_execution_containers(graph_id)
        edges = _service.list_execution_edges(graph_id)

        builder = GraphStructureBuilder(db_service)
        structure = builder.load_topology(
            graph_id, graph, nodes, edges, containers
        )

        # Serialize for agent consumption
        serializer = TopologyStructureSerializer()
        exported_data = serializer.export_for_agent(structure)

        return {
            "success": True,
            "exported": exported_data,
        }
    except ErrorResponse:
        raise
    except Exception as e:
        raise ErrorResponse(f"Error exporting topology: {e}", 500)
