from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..auth import require_user
from ..database import get_db
from ..models import Agent, Device, Booking, Setup, SetupDevice
from ..schemas import BookSetupIn, BookingOut, SetupDeviceOut, SetupBookingOut, SetupIn, SetupOut, SetupUpdate

router = APIRouter(prefix="/setups", tags=["setups"])


def _now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _load_setup(setup_id: str, db: AsyncSession) -> Setup:
    result = await db.execute(
        select(Setup)
        .where(Setup.id == setup_id)
        .options(
            selectinload(Setup.setup_devices).selectinload(SetupDevice.device).selectinload(Device.agent),
            selectinload(Setup.setup_devices).selectinload(SetupDevice.device).selectinload(Device.bookings),
        )
    )
    setup = result.scalar_one_or_none()
    if setup is None:
        raise HTTPException(status_code=404, detail="Setup not found")
    return setup


def _device_agent_online(device: Device, agents_by_ip: dict[str, Agent] | None = None) -> bool:
    if not device.host_ip:
        return True  # No agent configured — treat as always accessible
    if device.agent:
        return (_now_utc() - device.agent.last_seen).total_seconds() < 90
    # No FK link — check by IP
    if agents_by_ip:
        ag = agents_by_ip.get(device.host_ip)
        if ag:
            return (_now_utc() - ag.last_seen).total_seconds() < 90
    return False


async def _build_setup_out(setup: Setup, db: AsyncSession, agents_by_ip: dict[str, Agent] | None = None) -> SetupOut:
    device_outs = []
    for sb in setup.setup_devices:
        b = sb.device
        active_bk = next((bk for bk in b.bookings if bk.active), None)
        device_outs.append(SetupDeviceOut(
            id=b.id,
            name=b.name,
            device_id=b.device_id,
            location=b.location,
            agent_online=_device_agent_online(b, agents_by_ip),
            active_booking_username=active_bk.username if active_bk else None,
            active_booking_setup_name=active_bk.setup_name if active_bk else None,
        ))

    all_available = all(
        bof.active_booking_username is None and bof.agent_online
        for bof in device_outs
    )

    result = await db.execute(
        select(Booking).where(
            Booking.setup_id == setup.id,
            Booking.active == True,
        )
    )
    active_setup_bookings = result.scalars().all()
    active_booking_out = None
    if len(active_setup_bookings) == len(setup.setup_devices) and active_setup_bookings:
        bk = active_setup_bookings[0]
        active_booking_out = SetupBookingOut(
            username=bk.username,
            start_time=bk.start_time,
            end_time=bk.end_time,
        )

    return SetupOut(
        id=setup.id,
        name=setup.name,
        description=setup.description,
        created_at=setup.created_at,
        devices=device_outs,
        all_available=all_available,
        active_booking=active_booking_out,
    )


async def _load_agents_by_ip(db: AsyncSession) -> dict[str, Agent]:
    result = await db.execute(select(Agent))
    return {a.url.split("//")[-1].split(":")[0]: a for a in result.scalars().all()}


@router.get("", response_model=list[SetupOut])
async def list_setups(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Setup).options(
            selectinload(Setup.setup_devices).selectinload(SetupDevice.device).selectinload(Device.agent),
            selectinload(Setup.setup_devices).selectinload(SetupDevice.device).selectinload(Device.bookings),
        )
    )
    setups = result.scalars().all()
    agents_by_ip = await _load_agents_by_ip(db)
    return [await _build_setup_out(s, db, agents_by_ip) for s in setups]


@router.post("", response_model=SetupOut, status_code=201)
async def create_setup(
    body: SetupIn,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(require_user),
):
    setup = Setup(
        id=str(uuid.uuid4()),
        name=body.name,
        description=body.description,
        created_at=_now_utc(),
    )
    db.add(setup)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=422, detail="Setup name is already in use")

    for device_id in body.device_ids:
        device_result = await db.execute(select(Device).where(Device.id == device_id))
        if device_result.scalar_one_or_none() is None:
            await db.rollback()
            raise HTTPException(status_code=404, detail=f"Device {device_id} not found")
        db.add(SetupDevice(setup_id=setup.id, device_id=device_id))

    await db.commit()
    setup = await _load_setup(setup.id, db)
    return await _build_setup_out(setup, db, await _load_agents_by_ip(db))


@router.patch("/{setup_id}", response_model=SetupOut)
async def update_setup(
    setup_id: str,
    body: SetupUpdate,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(require_user),
):
    setup = await _load_setup(setup_id, db)
    if body.name is not None:
        setup.name = body.name
    if body.description is not None:
        setup.description = body.description
    if body.device_ids is not None:
        for sb in list(setup.setup_devices):
            await db.delete(sb)
        await db.flush()
        for device_id in body.device_ids:
            device_result = await db.execute(select(Device).where(Device.id == device_id))
            if device_result.scalar_one_or_none() is None:
                await db.rollback()
                raise HTTPException(status_code=404, detail=f"Device {device_id} not found")
            db.add(SetupDevice(setup_id=setup.id, device_id=device_id))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=422, detail="Setup name is already in use")
    setup = await _load_setup(setup_id, db)
    return await _build_setup_out(setup, db, await _load_agents_by_ip(db))


@router.delete("/{setup_id}", status_code=204)
async def delete_setup(
    setup_id: str,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(require_user),
):
    setup = await _load_setup(setup_id, db)
    result = await db.execute(
        select(Booking).where(Booking.setup_id == setup_id, Booking.active == True)
    )
    if result.scalars().first():
        raise HTTPException(status_code=409, detail="Setup has an active booking; release it first")
    await db.delete(setup)
    await db.commit()


@router.post("/{setup_id}/book", response_model=list[BookingOut])
async def book_setup(
    setup_id: str,
    body: BookSetupIn,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(require_user),
):
    setup = await _load_setup(setup_id, db)

    if not setup.setup_devices:
        raise HTTPException(status_code=400, detail="Setup has no devices")

    blocked = []
    for sb in setup.setup_devices:
        b = sb.device
        active_bk = next((bk for bk in b.bookings if bk.active), None)
        if active_bk:
            blocked.append(f"{b.name} (booked by {active_bk.username})")
    if blocked:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot book setup — devices unavailable: {', '.join(blocked)}",
        )

    now = _now_utc()
    end = now + timedelta(hours=body.duration_hours)
    bookings = []
    for sb in setup.setup_devices:
        bk = Booking(
            id=str(uuid.uuid4()),
            device_id=sb.device_id,
            username=user,
            start_time=now,
            end_time=end,
            extended=False,
            active=True,
            release_reason="",
            comment=body.comment,
            setup_id=setup.id,
            setup_name=setup.name,
        )
        db.add(bk)
        bookings.append(bk)

    await db.commit()
    for bk in bookings:
        await db.refresh(bk)

    return [
        BookingOut(
            id=bk.id,
            device_id=bk.device_id,
            device_name=next(sb.device.name for sb in setup.setup_devices if sb.device_id == bk.device_id),
            username=bk.username,
            start_time=bk.start_time,
            end_time=bk.end_time,
            extended=bk.extended,
            active=bk.active,
            release_reason=bk.release_reason,
            setup_id=bk.setup_id,
            setup_name=bk.setup_name,
        )
        for bk in bookings
    ]


@router.delete("/{setup_id}/booking", status_code=204)
async def release_setup_booking(
    setup_id: str,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(require_user),
):
    result = await db.execute(
        select(Booking).where(
            Booking.setup_id == setup_id,
            Booking.active == True,
        )
    )
    active_bookings = result.scalars().all()
    if not active_bookings:
        raise HTTPException(status_code=404, detail="No active booking found for this setup")

    for bk in active_bookings:
        if bk.username != user:
            raise HTTPException(status_code=403, detail="You can only release your own setup bookings")

    for bk in active_bookings:
        bk.active = False
        bk.release_reason = "manual"

    await db.commit()
