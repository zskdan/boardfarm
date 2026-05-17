from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import config
from ..services import hw_server, power, uart_proxy

router = APIRouter(tags=["hardware"])


def _get_board(board_id: str):
    for b in config.boards:
        if b.id == board_id:
            return b
    raise HTTPException(status_code=404, detail="Board not managed by this agent")


@router.post("/boards/{board_id}/services/start")
async def start_services(board_id: str):
    board = _get_board(board_id)
    jtag_ok = await hw_server.start(board_id, board.jtag_port)
    uart_ok = await uart_proxy.start(
        board_id, board.uart_device, board.uart_baud, board.uart_tcp_port
    )
    return {"jtag_started": jtag_ok, "uart_started": uart_ok}


@router.post("/boards/{board_id}/services/stop")
async def stop_services(board_id: str):
    _get_board(board_id)
    await hw_server.stop(board_id)
    await uart_proxy.stop(board_id)
    return {"stopped": True}


class PowerBody(BaseModel):
    action: Literal["on", "off", "reset"]


@router.post("/boards/{board_id}/power")
async def power_action(board_id: str, body: PowerBody):
    board = _get_board(board_id)
    ok = await power.run(board.power_script, body.action, board.power_args)
    if not ok:
        raise HTTPException(status_code=500, detail="Power action failed")
    return {"action": body.action, "ok": True}
