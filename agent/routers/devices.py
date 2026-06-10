from fastapi import APIRouter

from ..config import config
from ..services.health import get_health

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("")
async def list_devices():
    return [
        {
            "id": b.id,
            "usb_device": b.usb_device,
            "uart_device": b.uart_device,
            "jtag_port": b.jtag_port,
            "healthy": get_health(b.id),
        }
        for b in config.devices
    ]
