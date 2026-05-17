import asyncio
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .database import async_session
from .models import Board, Booking
from .ws import broadcast

logger = logging.getLogger(__name__)
AGENT_TIMEOUT = 5.0


async def _stop_agent_services(board: Board, board_id: str) -> None:
    if board and board.agent and board.agent.url:
        try:
            agent_token = board.agent.agent_token if board.agent else ""
            headers = {}
            if agent_token:
                headers["X-Agent-Token"] = agent_token
            async with httpx.AsyncClient(timeout=AGENT_TIMEOUT) as client:
                await client.post(
                    f"{board.agent.url}/boards/{board_id}/services/stop",
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
                    .options(selectinload(Booking.board).selectinload(Board.agent))
                )
                expired = result.scalars().all()
                for booking in expired:
                    booking.active = False
                    booking.release_reason = "expired"
                    logger.info(
                        "Expired booking %s for board %s (user: %s)",
                        booking.id,
                        booking.board_id,
                        booking.username,
                    )
                    await _stop_agent_services(booking.board, booking.board_id)
                if expired:
                    await db.commit()
                    for booking in expired:
                        asyncio.create_task(
                            broadcast(
                                {"type": "booking_expired", "board_id": booking.board_id}
                            )
                        )
        except Exception:
            logger.exception("Error in expiry loop")
