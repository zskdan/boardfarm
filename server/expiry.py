import asyncio
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .database import async_session
from .models import Device, Booking
from .ws import broadcast

logger = logging.getLogger(__name__)
AGENT_TIMEOUT = 5.0


async def _stop_agent_services(device: Device, device_id: str) -> None:
    if device and device.agent and device.agent.url:
        try:
            agent_token = device.agent.agent_token if device.agent else ""
            headers = {}
            if agent_token:
                headers["X-Agent-Token"] = agent_token
            async with httpx.AsyncClient(timeout=AGENT_TIMEOUT) as client:
                await client.post(
                    f"{device.agent.url}/devices/{device_id}/services/stop",
                    headers=headers,
                )
        except Exception:
            pass


async def expiry_loop(interval_seconds: int = 60) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            async with async_session() as db:
                result = await db.execute(
                    select(Booking)
                    .where(Booking.active == True, Booking.end_time < now)
                    .options(selectinload(Booking.device).selectinload(Device.agent))
                )
                expired = result.scalars().all()
                for booking in expired:
                    booking.active = False
                    booking.release_reason = "expired"
                    logger.info(
                        "Expired booking %s for device %s (user: %s)",
                        booking.id,
                        booking.device_id,
                        booking.username,
                    )
                    await _stop_agent_services(booking.device, booking.device_id)
                if expired:
                    await db.commit()
                    for booking in expired:
                        asyncio.create_task(
                            broadcast(
                                {"type": "booking_expired", "device_id": booking.device_id}
                            )
                        )
        except Exception:
            logger.exception("Error in expiry loop")
