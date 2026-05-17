import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import require_auth
from ..database import get_db
from ..models import Board, Tool
from ..schemas import ToolIn, ToolOut

router = APIRouter(tags=["tools"])


@router.get("/boards/{board_id}/tools", response_model=list[ToolOut])
async def list_tools(
    board_id: str,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(require_auth),
):
    result = await db.execute(select(Tool).where(Tool.board_id == board_id))
    return result.scalars().all()


@router.post("/boards/{board_id}/tools", response_model=ToolOut, status_code=201)
async def add_tool(
    board_id: str,
    body: ToolIn,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(require_auth),
):
    result = await db.execute(select(Board).where(Board.id == board_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Board not found")

    tool = Tool(id=str(uuid.uuid4()), board_id=board_id, **body.model_dump())
    db.add(tool)
    await db.commit()
    await db.refresh(tool)
    return ToolOut.model_validate(tool)


@router.patch("/tools/{tool_id}", response_model=ToolOut)
async def update_tool(
    tool_id: str,
    body: ToolIn,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(require_auth),
):
    result = await db.execute(select(Tool).where(Tool.id == tool_id))
    tool = result.scalar_one_or_none()
    if tool is None:
        raise HTTPException(status_code=404, detail="Tool not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(tool, field, value)
    await db.commit()
    await db.refresh(tool)
    return ToolOut.model_validate(tool)


@router.delete("/tools/{tool_id}", status_code=204)
async def delete_tool(
    tool_id: str,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(require_auth),
):
    result = await db.execute(select(Tool).where(Tool.id == tool_id))
    tool = result.scalar_one_or_none()
    if tool is None:
        raise HTTPException(status_code=404, detail="Tool not found")
    await db.delete(tool)
    await db.commit()
