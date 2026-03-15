from __future__ import annotations

import io
from typing import Optional

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from core.model_container import classification_engine
from schemas.classification import RequirementClassificationRequest, RequirementClassificationResponse
from services.classification_service import RequirementClassificationService

router = APIRouter(prefix="/classification", tags=["Requirement Classification"])
classification_service = RequirementClassificationService(classification_engine)


def _ensure_classifier_ready() -> None:
    if not classification_engine.is_ready:
        raise HTTPException(status_code=503, detail="Classification model not initialized.")


def _load_csv_bytes(payload: bytes) -> pd.DataFrame:
    if not payload:
        raise ValueError("请上传 CSV 内容")

    first_error: Optional[Exception] = None
    for header in (0, None):
        try:
            return pd.read_csv(io.BytesIO(payload), dtype=str, header=header)
        except Exception as exc:
            first_error = exc
            continue
    raise ValueError(f"无法解析 CSV：{first_error}")


@router.post("/predict-texts", response_model=RequirementClassificationResponse)
async def classify_texts(request: RequirementClassificationRequest):
    _ensure_classifier_ready()
    try:
        return classification_service.classify_texts(
            requirements=request.requirements,
            batch_size=request.batch_size,
            max_length=request.max_length,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/predict-csv")
async def classify_csv(file: UploadFile = File(...)):
    _ensure_classifier_ready()
    filename = file.filename or "uploaded.csv"
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="请上传 CSV 文件（.csv）")

    content = await file.read()
    try:
        dataframe = _load_csv_bytes(content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        result_df = classification_service.classify_dataframe(dataframe)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    buffer = io.BytesIO()
    result_df.to_csv(buffer, index=False, encoding="utf-8-sig")
    buffer.seek(0)
    out_name = f"pred_{filename}" if filename else "predictions.csv"

    headers = {"Content-Disposition": f"attachment; filename={out_name}"}
    return StreamingResponse(buffer, media_type="text/csv", headers=headers)
