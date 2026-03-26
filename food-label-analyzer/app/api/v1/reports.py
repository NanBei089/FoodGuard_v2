from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.common import ApiResponse, success_response
from app.schemas.report import ReportDetailResponseSchema, ReportListResponseSchema
from app.services.report_service import get_report_detail, get_report_list


router = APIRouter()


@router.get(
    "",
    response_model=ApiResponse[ReportListResponseSchema],
    summary="分页查询报告列表",
    description="返回当前用户的报告列表，支持分页并在页码越界时自动夹到最后一页。",
    responses={
        200: {"description": "查询成功"},
        401: {"description": "未认证"},
    },
)
async def list_reports(
    page: int = Query(default=1, ge=1, description="页码，从 1 开始", examples=[1]),
    page_size: int = Query(default=10, ge=1, le=50, description="每页条数，最大 50", examples=[10]),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ReportListResponseSchema]:
    payload = await get_report_list(current_user.id, page, page_size, db)
    return success_response(payload)


@router.get(
    "/{report_id}",
    response_model=ApiResponse[ReportDetailResponseSchema],
    summary="查询报告详情",
    description="返回报告详情，包括营养数据、结构化分析结果、RAG 汇总和产物链接。",
    responses={
        200: {"description": "查询成功"},
        401: {"description": "未认证"},
        404: {"description": "报告不存在"},
    },
)
async def report_detail(
    report_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ReportDetailResponseSchema]:
    payload = await get_report_detail(report_id, current_user.id, db)
    return success_response(payload)


__all__ = ["router"]
