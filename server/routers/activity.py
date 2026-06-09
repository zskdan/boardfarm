from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import AuditLog
from ..schemas import AuditLogOut

router = APIRouter(tags=["activity"])


@router.get("/activity", response_model=list[AuditLogOut])
async def list_activity(
    board_id: str | None = Query(default=None),
    username: str | None = Query(default=None),
    action: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, le=500),
    db: AsyncSession = Depends(get_db),
):
    query = select(AuditLog)
    if board_id:
        query = query.where(AuditLog.board_id == board_id)
    if username:
        query = query.where(AuditLog.username == username)
    if action:
        query = query.where(AuditLog.action == action)
    query = query.order_by(AuditLog.timestamp.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return [AuditLogOut.model_validate(e) for e in result.scalars().all()]
