"""单需求变更分析路由。"""

from fastapi import APIRouter

from backend_business.api.http.errors import ErrorResponse
from backend_business.api.routers.schemas.requirement_change_schemas import (
    AnalyzeRequirementChangeRequest,
)
from backend_business.config import settings
from backend_business.services.ai_proxy import ai_proxy
from backend_business.services.db_service import db_service
from backend_business.services.requirement_change_analysis_service import (
    RequirementChangeAnalysisNotFoundError,
    RequirementChangeAnalysisService,
)
from backend_business.services.requirement_graph_service import RequirementGraphService
from backend_business.services.requirements_manage_service import RequirementsManageService


router = APIRouter(prefix="/api/v2/requirement-change", tags=["requirement-change"])

_manage_service = RequirementsManageService(dsn=settings.POSTGRES_DSN)


def _require_change_analysis_service() -> RequirementChangeAnalysisService:
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)
    graph_service = RequirementGraphService(db_service, ai_client=ai_proxy)
    return RequirementChangeAnalysisService(_manage_service, graph_service)


@router.post("/analyze")
def analyze_requirement_change(req: AnalyzeRequirementChangeRequest):
    try:
        return _require_change_analysis_service().analyze_requirement_change(
            project_id=req.project_id,
            requirement_id=req.requirement_id,
            changes=req.changes.model_dump(exclude_unset=True),
        )
    except RequirementChangeAnalysisNotFoundError as exc:
        raise ErrorResponse(str(exc), 404)
    except ValueError as exc:
        raise ErrorResponse(str(exc), 400)
    except ErrorResponse:
        raise
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)
