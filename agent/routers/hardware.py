from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import require_agent_auth
from ..config import config
from ..services import hw_server, power

router = APIRouter(tags=["hardware"])


def _get_device(board_id: str):
    for b in config.boards:
        if b.id == board_id:
            return b
    raise HTTPException(status_code=404, detail="Device not managed by this agent")


@router.post("/boards/{board_id}/services/start")
async def start_services(board_id: str, _: None = Depends(require_agent_auth)):
    device = _get_device(board_id)
    jtag_ok = await hw_server.start(board_id, device.jtag_port)
    return {"jtag_started": jtag_ok}


@router.post("/boards/{board_id}/services/stop")
async def stop_services(board_id: str, _: None = Depends(require_agent_auth)):
    _get_device(board_id)
    await hw_server.stop(board_id)
    return {"stopped": True}


class PowerBody(BaseModel):
    action: Literal["on", "off", "reset"]


@router.post("/boards/{board_id}/power")
async def power_action(board_id: str, body: PowerBody, _: None = Depends(require_agent_auth)):
    device = _get_device(board_id)
    ok = await power.run(device.power_script, body.action, device.power_args)
    if not ok:
        raise HTTPException(status_code=500, detail="Power action failed")
    return {"action": body.action, "ok": True}
