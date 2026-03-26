from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.analysis import router as analysis_router
from app.api.v1.auth import router as auth_router
from app.api.v1.reports import router as reports_router


api_router = APIRouter()
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(analysis_router, prefix="/analysis", tags=["analysis"])
api_router.include_router(reports_router, prefix="/reports", tags=["reports"])


__all__ = ["api_router"]
