import json
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..audit import log_action
from ..auth import require_user
from ..database import get_db
from ..models import Agent, Device, Booking
from ..schemas import BookingOut, DeviceIn, DeviceOut, DeviceUpdate

router = APIRouter(prefix="/boards", tags=["boards"])


def _raise_uniqueness_error(exc_str: str) -> None:
    if "boards.device_id" in exc_str or "uq_device_id" in exc_str:
        raise HTTPException(status_code=422, detail="Device ID is already in use by another device")
    raise HTTPException(status_code=422, detail="Device name is already in use")


def _now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _build_device_out(device: Device, db: AsyncSession) -> DeviceOut:
    agent_online = False
    if device.agent:
        delta = (_now_utc() - device.agent.last_seen).total_seconds()
        agent_online = delta < 90

    active_booking = None
    for bk in device.bookings:
        if bk.active:
            active_booking = BookingOut(
                id=bk.id,
                device_id=bk.board_id,
                device_name=device.name,
                username=bk.username,
                start_time=bk.start_time,
                end_time=bk.end_time,
                extended=bk.extended,
                active=bk.active,
                release_reason=bk.release_reason,
            )
            break

    return DeviceOut(
        id=device.id,
        device_id=device.device_id,
        serial_number=device.serial_number,
        revision=device.revision,
        name=device.name,
        description=device.description,
        location=device.location,
        current_notes=device.current_notes,
        device_ip=device.device_ip,
        agent_id=device.agent_id,
        host_ip=device.host_ip,
        features=json.loads(device.features) if device.features else {},
        jtag_port=device.jtag_port,
        ssh_user=device.ssh_user,
        ssh_port=device.ssh_port,
        power_script=device.power_script,
        power_args=json.loads(device.power_args) if device.power_args else {},
        sdmux_control=device.sdmux_control or "",
        sdmux_sdcard=device.sdmux_sdcard or "",
        access_control=device.access_control or "",
        enabled=device.enabled,
        agent_online=agent_online,
        active_booking=active_booking,
    )


async def _load_device(device_id: str, db: AsyncSession) -> Device:
    result = await db.execute(
        select(Device)
        .where(Device.id == device_id)
        .options(
            selectinload(Device.agent),
            selectinload(Device.bookings),
        )
    )
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@router.get("", response_model=list[DeviceOut])
async def list_boards(
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Device).options(
            selectinload(Device.agent),
            selectinload(Device.bookings),
        )
    )
    devices = result.scalars().all()
    return [await _build_device_out(d, db) for d in devices]


@router.get("/{board_id}", response_model=DeviceOut)
async def get_board(
    board_id: str,
    db: AsyncSession = Depends(get_db),
):
    device = await _load_device(board_id, db)
    return await _build_device_out(device, db)


@router.post("", response_model=DeviceOut, status_code=201)
async def create_board(
    body: DeviceIn,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(require_user),
):
    device = Device(
        id=str(uuid.uuid4()),
        device_id="DEV-" + secrets.token_hex(3).upper(),
        serial_number=body.serial_number,
        revision=body.revision,
        name=body.name,
        description=body.description,
        location=body.location,
        current_notes=body.current_notes,
        device_ip=body.device_ip,
        host_ip=body.host_ip,
        features=json.dumps(body.features),
        jtag_port=body.jtag_port,
        ssh_user=body.ssh_user,
        ssh_port=body.ssh_port,
        power_script=body.power_script,
        power_args=json.dumps(body.power_args),
        sdmux_control=body.sdmux_control,
        sdmux_sdcard=body.sdmux_sdcard,
        access_control=body.access_control,
        enabled=body.enabled,
    )
    db.add(device)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        _raise_uniqueness_error(str(exc))
    device = await _load_device(device.id, db)
    await log_action(db, "device_created", user, device.id, device.name, f"location='{body.location}'", device_id=device.device_id)
    await db.commit()
    return await _build_device_out(device, db)


@router.patch("/{board_id}", response_model=DeviceOut)
async def update_board(
    board_id: str,
    body: DeviceUpdate,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(require_user),
):
    device = await _load_device(board_id, db)
    for field, value in body.model_dump(exclude_none=True).items():
        if field in ("features", "power_args"):
            setattr(device, field, json.dumps(value))
        else:
            setattr(device, field, value)
    detail = ", ".join(f"{k}='{v}'" for k, v in body.model_dump(exclude_none=True).items())
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        _raise_uniqueness_error(str(exc))
    device = await _load_device(board_id, db)
    await log_action(db, "device_updated", user, board_id, device.name, detail, device_id=device.device_id)
    await db.commit()
    return await _build_device_out(device, db)


@router.delete("/{board_id}", status_code=204)
async def delete_board(
    board_id: str,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(require_user),
):
    device = await _load_device(board_id, db)
    for bk in device.bookings:
        if bk.active:
            raise HTTPException(
                status_code=409, detail="Device has an active booking; release it first"
            )
    await log_action(db, "device_deleted", user, device.id, device.name, "", device_id=device.device_id)
    await db.delete(device)
    await db.commit()
