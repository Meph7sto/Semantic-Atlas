"""
分类路由 - FastAPI 版本
对应历史蓝图: classification_bp (url_prefix="/api/v2/classification")
"""

import os
from typing import Optional

from fastapi import APIRouter, File, Query, Request, UploadFile
from fastapi.responses import StreamingResponse, JSONResponse
import httpx

from backend_business.api.http.errors import ErrorResponse
from backend_business.api.routers.schemas.classification_schemas import (
    PredictTextsRequest,
)
from backend_business.config import settings
from backend_business.services.db_service import db_service

router = APIRouter(prefix="/api/v2/classification", tags=["classification"])

# Allow separating classification service URL; fallback to inference URL
CLASSIFICATION_URL = os.getenv("CLASSIFICATION_URL", settings.INFERENCE_BASE_URL)
_fallback_client: Optional[httpx.AsyncClient] = None


def _get_http_client(request: Request) -> httpx.AsyncClient:
    """
    获取复用的 HTTP 客户端（优先使用 app lifespan 初始化的连接池）。
    """
    client = getattr(request.app.state, "classification_http_client", None)
    if isinstance(client, httpx.AsyncClient):
        return client

    global _fallback_client
    if _fallback_client is None:
        _fallback_client = httpx.AsyncClient()
    return _fallback_client


@router.post("/predict-texts")
async def predict_texts(req: PredictTextsRequest, request: Request):
    """
    文本分类。

    转发请求到 inference backend 的 /classification/predict-texts，
    可选保存分类结果到数据库。
    """
    # 构造转发请求体（移除业务层参数）
    payload = req.model_dump(exclude_unset=True, exclude={"save_to_db", "session_id"})

    try:
        client = _get_http_client(request)
        resp = await client.post(
            f"{CLASSIFICATION_URL}/classification/predict-texts",
            json=payload,
            timeout=300.0,
        )

        try:
            resp_data = resp.json()
        except ValueError:
            raise ErrorResponse(f"Upstream Error: {resp.text}", resp.status_code)

        record_id = None
        if req.save_to_db and db_service and resp.status_code == 200:
            predictions = resp_data.get("predictions", [])
            if req.requirements and predictions:
                record_id = db_service.save_classification(
                    session_id=req.session_id,
                    requirements=req.requirements,
                    predictions=predictions,
                    label_distribution=resp_data.get("label_distribution"),
                    total=resp_data.get("total"),
                    result_json=resp_data,
                )

        result = resp_data.copy() if isinstance(resp_data, dict) else {"data": resp_data}
        if record_id is not None:
            result["record_id"] = record_id

        return JSONResponse(content=result, status_code=resp.status_code)
    except httpx.ConnectError:
        raise ErrorResponse(
            f"Cannot connect to Classification Service at {CLASSIFICATION_URL}. Is it running?",
            503,
        )
    except ErrorResponse:
        raise
    except Exception as exc:
        raise ErrorResponse(f"Business Backend Error: {str(exc)}", 500)


@router.post("/predict-csv")
async def predict_csv(request: Request, file: Optional[UploadFile] = File(default=None)):
    """
    CSV 文件分类。

    接收 CSV 文件，转发到 inference backend，
    返回带预测标签的 CSV 文件（StreamingResponse）。
    """
    if file is None:
        raise ErrorResponse("请上传 CSV 文件", 400)

    try:
        content = await file.read()

        client = _get_http_client(request)
        resp = await client.post(
            f"{CLASSIFICATION_URL}/classification/predict-csv",
            files={"file": (file.filename, content, file.content_type or "text/csv")},
            timeout=600.0,
        )

        # Pass through JSON errors
        content_type = resp.headers.get("Content-Type", "")
        if content_type.startswith("application/json"):
            return JSONResponse(content=resp.json(), status_code=resp.status_code)

        # Pass through CSV response
        excluded = {
            "content-encoding",
            "transfer-encoding",
            "connection",
            "content-length",
        }
        headers = {k: v for k, v in resp.headers.items() if k.lower() not in excluded}
        return StreamingResponse(
            iter([resp.content]),
            media_type=resp.headers.get("Content-Type", "text/csv"),
            status_code=resp.status_code,
            headers=headers,
        )
    except httpx.ConnectError:
        raise ErrorResponse(
            f"Cannot connect to Classification Service at {CLASSIFICATION_URL}. Is it running?",
            503,
        )
    except ErrorResponse:
        raise
    except Exception as exc:
        raise ErrorResponse(f"Business Backend Error: {str(exc)}", 500)


@router.get("/latest")
async def get_latest_classification(session_id: Optional[str] = Query(default=None)):
    """
    获取指定 session 的最新分类结果。
    """
    if not session_id:
        raise ErrorResponse("缺少 session_id", 400)

    normalized_session_id = session_id.strip()
    if not normalized_session_id:
        raise ErrorResponse("缺少 session_id", 400)
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)

    try:
        data = db_service.get_latest_classification(normalized_session_id)
        return {"data": data}
    except ErrorResponse:
        raise
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)
