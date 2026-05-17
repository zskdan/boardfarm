from fastapi import APIRouter

from ..config import config

router = APIRouter(prefix="/boards", tags=["boards"])


@router.get("")
async def list_boards():
    return [
        {
            "id": b.id,
            "uart_device": b.uart_device,
            "jtag_port": b.jtag_port,
            "uart_tcp_port": b.uart_tcp_port,
        }
        for b in config.boards
    ]
