import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import require_auth
from ..database import get_db
from ..models import Agent, Board
from ..schemas import AgentOut

router = APIRouter(prefix="/agents", tags=["agents"])


def _now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@router.post("/register", response_model=AgentOut)
async def register_agent(
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    name = body["name"]
    url = body["url"]
    board_ids: list[str] = body.get("board_ids", [])

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

    await db.flush()

    # Claim boards: link them to this agent
    if board_ids:
        host_ip = url.split("//")[-1].split(":")[0]
        await db.execute(
            update(Board)
            .where(Board.id.in_(board_ids))
            .values(agent_id=agent.id, host_ip=host_ip)
        )

    await db.commit()
    await db.refresh(agent)
    return AgentOut.model_validate(agent)


@router.post("/heartbeat")
async def heartbeat(body: dict, db: AsyncSession = Depends(get_db)):
    name = body["name"]
    result = await db.execute(select(Agent).where(Agent.name == name))
    agent = result.scalar_one_or_none()
    if agent:
        agent.last_seen = _now_utc()
        await db.commit()
    return {"ok": True}


@router.get("", response_model=list[AgentOut])
async def list_agents(
    db: AsyncSession = Depends(get_db),
    user: str = Depends(require_auth),
):
    result = await db.execute(select(Agent))
    agents = result.scalars().all()
    return [AgentOut.model_validate(a) for a in agents]
