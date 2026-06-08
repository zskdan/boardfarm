import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..auth import require_auth, require_auth_or_admin
from ..database import get_db
from ..models import Board, Booking
from ..schemas import BookingOut, CommandsOut
from ..ws import broadcast

router = APIRouter(tags=["bookings"])

MAX_BOOKING_HOURS = 24
AGENT_TIMEOUT = 5.0

# Per-board asyncio locks to prevent double-booking race conditions
_board_locks: dict[str, asyncio.Lock] = {}


def _get_lock(board_id: str) -> asyncio.Lock:
    return _board_locks.setdefault(board_id, asyncio.Lock())


def _now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _call_agent(
    agent_url: str, path: str, agent_token: str = "", method: str = "POST"
) -> None:
    try:
        headers = {}
        if agent_token:
            headers["X-Agent-Token"] = agent_token
        async with httpx.AsyncClient(timeout=AGENT_TIMEOUT) as client:
            await client.request(method, f"{agent_url}{path}", headers=headers)
    except Exception:
        pass  # Agent offline — booking still proceeds


async def _load_board(board_id: str, db: AsyncSession) -> Board:
    result = await db.execute(
        select(Board)
        .where(Board.id == board_id)
        .options(selectinload(Board.bookings), selectinload(Board.agent))
    )
    board = result.scalar_one_or_none()
    if board is None:
        raise HTTPException(status_code=404, detail="Board not found")
    return board


async def _load_booking(booking_id: str, db: AsyncSession) -> Booking:
    result = await db.execute(
        select(Booking)
        .where(Booking.id == booking_id)
        .options(selectinload(Booking.board).selectinload(Board.agent))
    )
    booking = result.scalar_one_or_none()
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking


def _booking_out(bk: Booking) -> BookingOut:
    return BookingOut(
        id=bk.id,
        board_id=bk.board_id,
        board_name=bk.board.name if bk.board else "",
        username=bk.username,
        start_time=bk.start_time,
        end_time=bk.end_time,
        extended=bk.extended,
        active=bk.active,
        release_reason=bk.release_reason,
    )


@router.post("/boards/{board_id}/book", response_model=BookingOut, status_code=201)
async def book_board(
    board_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(require_auth),
):
    duration_hours = int(body.get("duration_hours", 1))
    if duration_hours < 1 or duration_hours > MAX_BOOKING_HOURS:
        raise HTTPException(
            status_code=422, detail=f"duration_hours must be 1-{MAX_BOOKING_HOURS}"
        )
    comment: str = str(body.get("comment", ""))[:500]

    async with _get_lock(board_id):
        board = await _load_board(board_id, db)

        if not board.enabled:
            raise HTTPException(status_code=409, detail="Board is disabled")

        for bk in board.bookings:
            if bk.active:
                raise HTTPException(
                    status_code=409,
                    detail=f"Board already booked by {bk.username} until {bk.end_time.isoformat()}",
                )

        now = _now_utc()
        booking = Booking(
            id=str(uuid.uuid4()),
            board_id=board_id,
            username=user,
            start_time=now,
            end_time=now + timedelta(hours=duration_hours),
            comment=comment,
        )
        db.add(booking)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(
                status_code=409, detail="Board already has an active booking"
            )
        await db.refresh(booking)

        agent_token = board.agent.agent_token if board.agent else ""
        if board.agent and board.agent.url:
            await _call_agent(
                board.agent.url,
                f"/boards/{board_id}/services/start",
                agent_token=agent_token,
            )

        result = await db.execute(
            select(Booking)
            .where(Booking.id == booking.id)
            .options(selectinload(Booking.board).selectinload(Board.agent))
        )
        booking = result.scalar_one()

    asyncio.create_task(broadcast({"type": "booking_changed", "board_id": board_id}))
    return _booking_out(booking)


@router.delete("/bookings/{booking_id}", response_model=BookingOut)
async def release_booking(
    booking_id: str,
    db: AsyncSession = Depends(get_db),
    auth: tuple[str, bool] = Depends(require_auth_or_admin),
):
    user, is_admin = auth
    booking = await _load_booking(booking_id, db)

    if not booking.active:
        raise HTTPException(status_code=409, detail="Booking is already inactive")

    if not is_admin and booking.username != user:
        raise HTTPException(
            status_code=403, detail="You can only release your own bookings"
        )

    booking.active = False
    booking.release_reason = "admin" if is_admin and booking.username != user else "manual"
    await db.commit()

    board = booking.board
    agent_token = board.agent.agent_token if board and board.agent else ""
    if board and board.agent and board.agent.url:
        await _call_agent(
            board.agent.url,
            f"/boards/{board.id}/services/stop",
            agent_token=agent_token,
        )

    board_id = booking.board_id
    await db.refresh(booking)
    asyncio.create_task(broadcast({"type": "booking_changed", "board_id": board_id}))
    return _booking_out(booking)


@router.patch("/bookings/{booking_id}/extend", response_model=BookingOut)
async def extend_booking(
    booking_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(require_auth),
):
    hours = int(body.get("hours", 1))
    booking = await _load_booking(booking_id, db)

    if not booking.active:
        raise HTTPException(status_code=409, detail="Booking is not active")
    if booking.username != user:
        raise HTTPException(status_code=403, detail="Not your booking")
    if booking.extended:
        raise HTTPException(status_code=409, detail="Booking already extended once")

    new_end = booking.end_time + timedelta(hours=hours)
    max_end = booking.start_time + timedelta(hours=MAX_BOOKING_HOURS)
    if new_end > max_end:
        new_end = max_end

    booking.end_time = new_end
    booking.extended = True
    await db.commit()
    await db.refresh(booking)
    return _booking_out(booking)


@router.get("/bookings/{booking_id}/commands", response_model=CommandsOut)
async def get_commands(
    booking_id: str,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(require_auth),
):
    booking = await _load_booking(booking_id, db)

    if not booking.active:
        raise HTTPException(status_code=409, detail="Booking is not active")
    if booking.username != user:
        raise HTTPException(status_code=403, detail="Not your booking")

    board = booking.board
    ip = board.host_ip or "AGENT_IP"

    return CommandsOut(
        jtag_connect=f"connect_hw_server -url tcp:{ip}:{board.jtag_port}",
        vivado_tcl=f"connect_hw_server -url tcp:{ip}:{board.jtag_port}\nopen_hw_target",
        uart=f"telnet {ip} {board.uart_tcp_port}",
        ssh=f"ssh {board.ssh_user}@{ip} -p {board.ssh_port}",
        power_on=f"# Use the boardfarm UI or API: POST /boards/{board.id}/power {{\"action\":\"on\"}}",
    )


@router.get("/bookings", response_model=list[BookingOut])
async def list_bookings(
    board_id: str | None = Query(default=None),
    username: str | None = Query(default=None),
    active: bool | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
    user: str = Depends(require_auth),
):
    query = select(Booking).options(
        selectinload(Booking.board).selectinload(Board.agent)
    )
    if board_id:
        query = query.where(Booking.board_id == board_id)
    if username:
        query = query.where(Booking.username == username)
    if active is not None:
        query = query.where(Booking.active == active)
    query = query.order_by(Booking.start_time.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return [_booking_out(bk) for bk in result.scalars().all()]
