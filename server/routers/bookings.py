import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..audit import log_action
from ..auth import require_user, require_user_or_admin
from ..config import settings
from ..database import get_db
from ..models import Device, Booking
from ..schemas import BookingOut, CommandsOut
from ..ws import broadcast

router = APIRouter(tags=["bookings"])

AGENT_TIMEOUT = 5.0
# Sentinel used when max_booking_hours == 0 (never expires)
_PERMANENT_HOURS = 24 * 365 * 10  # 10 years

# Per-device asyncio locks to prevent double-booking race conditions
_device_locks: dict[str, asyncio.Lock] = {}


def _get_lock(device_id: str) -> asyncio.Lock:
    return _device_locks.setdefault(device_id, asyncio.Lock())


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


async def _load_device(device_id: str, db: AsyncSession) -> Device:
    result = await db.execute(
        select(Device)
        .where(Device.id == device_id)
        .options(selectinload(Device.bookings), selectinload(Device.agent))
    )
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


async def _load_booking(booking_id: str, db: AsyncSession) -> Booking:
    result = await db.execute(
        select(Booking)
        .where(Booking.id == booking_id)
        .options(selectinload(Booking.device).selectinload(Device.agent))
    )
    booking = result.scalar_one_or_none()
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking


def _booking_out(bk: Booking) -> BookingOut:
    return BookingOut(
        id=bk.id,
        device_id=bk.device_id,
        device_name=bk.device.name if bk.device else "",
        username=bk.username,
        start_time=bk.start_time,
        end_time=bk.end_time,
        extended=bk.extended,
        active=bk.active,
        release_reason=bk.release_reason,
        comment=bk.comment or "",
    )


@router.post("/devices/{device_id}/book", response_model=BookingOut, status_code=201)
async def book_device(
    device_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(require_user),
):
    comment: str = str(body.get("comment", ""))[:500]
    max_h = settings.max_booking_hours

    if max_h == 0:
        # Never-expires mode: ignore duration_hours, use far-future end_time
        effective_hours = _PERMANENT_HOURS
    else:
        duration_hours = int(body.get("duration_hours", 1))
        if duration_hours < 1:
            raise HTTPException(status_code=422, detail="duration_hours must be >= 1")
        if max_h is not None and duration_hours > max_h:
            raise HTTPException(
                status_code=422, detail=f"duration_hours must be <= {max_h}"
            )
        effective_hours = duration_hours

    async with _get_lock(device_id):
        device = await _load_device(device_id, db)

        if not device.enabled:
            raise HTTPException(status_code=409, detail="Device is disabled")

        for bk in device.bookings:
            if bk.active:
                raise HTTPException(
                    status_code=409,
                    detail=f"Device already booked by {bk.username} until {bk.end_time.isoformat()}",
                )

        now = _now_utc()
        booking = Booking(
            id=str(uuid.uuid4()),
            device_id=device_id,
            username=user,
            start_time=now,
            end_time=now + timedelta(hours=effective_hours),
            comment=comment,
        )
        db.add(booking)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(
                status_code=409, detail="Device already has an active booking"
            )
        await db.refresh(booking)

        agent_token = device.agent.agent_token if device.agent else ""
        if device.agent and device.agent.url:
            await _call_agent(
                device.agent.url,
                f"/devices/{device_id}/services/start",
                agent_token=agent_token,
            )

        result = await db.execute(
            select(Booking)
            .where(Booking.id == booking.id)
            .options(selectinload(Booking.device).selectinload(Device.agent))
        )
        booking = result.scalar_one()
        await log_action(db, "booked", user, device_id, booking.device.name if booking.device else "", f"{effective_hours}h — {comment}", device_id=booking.device.device_id if booking.device else "")
        await db.commit()

    asyncio.create_task(broadcast({"type": "booking_changed", "device_id": device_id}))
    return _booking_out(booking)


@router.delete("/bookings/{booking_id}", response_model=BookingOut)
async def release_booking(
    booking_id: str,
    db: AsyncSession = Depends(get_db),
    auth: tuple[str, bool] = Depends(require_user_or_admin),
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
    await log_action(db, "released", user, booking.device_id, booking.device.name if booking.device else "", f"reason: {booking.release_reason}", device_id=booking.device.device_id if booking.device else "")
    await db.commit()

    device = booking.device
    agent_token = device.agent.agent_token if device and device.agent else ""
    if device and device.agent and device.agent.url:
        await _call_agent(
            device.agent.url,
            f"/devices/{device.id}/services/stop",
            agent_token=agent_token,
        )

    device_id = booking.device_id
    asyncio.create_task(broadcast({"type": "booking_changed", "device_id": device_id}))
    return _booking_out(booking)


@router.patch("/bookings/{booking_id}/extend", response_model=BookingOut)
async def extend_booking(
    booking_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(require_user),
):
    hours = int(body.get("hours", 1))
    booking = await _load_booking(booking_id, db)

    if not booking.active:
        raise HTTPException(status_code=409, detail="Booking is not active")
    if booking.username != user:
        raise HTTPException(status_code=403, detail="Not your booking")
    if booking.extended:
        raise HTTPException(status_code=409, detail="Booking already extended once")

    max_h = settings.max_booking_hours
    new_end = booking.end_time + timedelta(hours=hours)
    if max_h and max_h > 0:
        max_end = booking.start_time + timedelta(hours=max_h)
        if new_end > max_end:
            new_end = max_end

    if new_end == booking.end_time:
        raise HTTPException(status_code=409, detail="Booking is already at maximum duration")

    booking.end_time = new_end
    booking.extended = True
    await log_action(db, "extended", user, booking.device_id, booking.device.name if booking.device else "", f"+{hours}h", device_id=booking.device.device_id if booking.device else "")
    await db.commit()
    await db.refresh(booking)
    return _booking_out(booking)


@router.get("/bookings/{booking_id}/commands", response_model=CommandsOut)
async def get_commands(
    booking_id: str,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(require_user),
):
    booking = await _load_booking(booking_id, db)

    if not booking.active:
        raise HTTPException(status_code=409, detail="Booking is not active")

    device = booking.device
    agent_ip = device.host_ip or "AGENT_IP"
    ssh_ip = device.device_ip or device.host_ip or "DEVICE_IP"

    return CommandsOut(
        jtag_connect=f"connect_hw_server -url tcp:{agent_ip}:{device.jtag_port}" if device.jtag_port else "",
        vivado_tcl=f"connect_hw_server -url tcp:{agent_ip}:{device.jtag_port}\nopen_hw_target" if device.jtag_port else "",
        uart=(
            f"sudo socat pty,link=/dev/tty{device.device_id},rawer "
            f"EXEC:\"ssh vivado@{agent_ip} socat - {device.uart_device},rawer\""
        ) if (device.uart_device and device.host_ip) else "",
        ssh=f"ssh {device.ssh_user}@{ssh_ip} -p {device.ssh_port}" if device.ssh_port else "",
        power_on=f"# Use the boardfarm UI or API: POST /devices/{device.id}/power {{\"action\":\"on\"}}",
    )


@router.get("/bookings", response_model=list[BookingOut])
async def list_bookings(
    device_id: str | None = Query(default=None),
    username: str | None = Query(default=None),
    active: bool | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
):
    query = select(Booking).options(
        selectinload(Booking.device).selectinload(Device.agent)
    )
    if device_id:
        query = query.where(Booking.device_id == device_id)
    if username:
        query = query.where(Booking.username == username)
    if active is not None:
        query = query.where(Booking.active == active)
    query = query.order_by(Booking.start_time.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return [_booking_out(bk) for bk in result.scalars().all()]
