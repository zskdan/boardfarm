import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import log_action
from ..auth import require_user
from ..database import get_db
from ..models import Device, Tool
from ..schemas import ToolIn, ToolOut

router = APIRouter(tags=["tools"])


@router.get("/devices/{device_id}/tools", response_model=list[ToolOut])
async def list_tools(
    device_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Tool).where(Tool.board_id == device_id))
    return result.scalars().all()


@router.post("/devices/{device_id}/tools", response_model=ToolOut, status_code=201)
async def add_tool(
    device_id: str,
    body: ToolIn,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(require_user),
):
    device_result = await db.execute(select(Device).where(Device.id == device_id))
    device = device_result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")

    tool = Tool(id=str(uuid.uuid4()), board_id=device_id, **body.model_dump())
    db.add(tool)
    await log_action(db, "tool_added", user, device_id, device.name, f"{body.type} · {body.model}", device_id=device.device_id)
    await db.commit()
    await db.refresh(tool)
    return ToolOut.model_validate(tool)


@router.patch("/tools/{tool_id}", response_model=ToolOut)
async def update_tool(
    tool_id: str,
    body: ToolIn,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(require_user),
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
    user: str = Depends(require_user),
):
    result = await db.execute(select(Tool).where(Tool.id == tool_id))
    tool = result.scalar_one_or_none()
    if tool is None:
        raise HTTPException(status_code=404, detail="Tool not found")
    device_result = await db.execute(select(Device).where(Device.id == tool.board_id))
    device = device_result.scalar_one_or_none()
    device_name = device.name if device else ""
    device_id_val = device.device_id if device else ""
    await log_action(db, "tool_deleted", user, tool.board_id, device_name, f"{tool.type} · {tool.model}", device_id=device_id_val)

    await db.delete(tool)
    await db.commit()
