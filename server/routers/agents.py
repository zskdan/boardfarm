import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import _check_token, require_user
from ..database import get_db
from ..models import Agent, Device
from ..schemas import AgentOut

router = APIRouter(prefix="/agents", tags=["agents"])


def _now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@router.post("/register", response_model=AgentOut)
async def register_agent(
    body: dict,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_check_token),
):
    name = body["name"]
    url = body["url"]
    device_ids: list[str] = body.get("device_ids", [])

    result = await db.execute(select(Agent).where(Agent.name == name))
    agent = result.scalar_one_or_none()

    now = _now_utc()
    if agent is None:
        agent = Agent(id=str(uuid.uuid4()), name=name, url=url, last_seen=now)
        db.add(agent)
    else:
        agent.url = url
        agent.last_seen = now

    agent.agent_token = body.get("token", "")
    agent.agent_version = body.get("agent_version", "")

    await db.flush()

    host_ip = url.split("//")[-1].split(":")[0]

    # Link explicitly configured devices (also updates host_ip to match)
    if device_ids:
        await db.execute(
            update(Device)
            .where(Device.id.in_(device_ids))
            .values(agent_id=agent.id, host_ip=host_ip)
        )

    # Auto-claim any unlinked devices whose host_ip already matches this agent
    await db.execute(
        update(Device)
        .where(Device.host_ip == host_ip, Device.agent_id.is_(None))
        .values(agent_id=agent.id)
    )

    await db.commit()
    await db.refresh(agent)
    return AgentOut.model_validate(agent)


@router.post("/heartbeat")
async def heartbeat(body: dict, db: AsyncSession = Depends(get_db)):
    name = body["name"]
    result = await db.execute(select(Agent).where(Agent.name == name))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not registered")
    agent.last_seen = _now_utc()
    await db.commit()
    return {"ok": True}


@router.get("", response_model=list[AgentOut])
async def list_agents(
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Agent))
    agents = result.scalars().all()
    return [AgentOut.model_validate(a) for a in agents]
