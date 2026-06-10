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
from ..models import Agent, Board, Booking
from ..schemas import BookingOut, DeviceIn, DeviceOut, DeviceUpdate

router = APIRouter(prefix="/devices", tags=["devices"])


def _raise_uniqueness_error(exc_str: str) -> None:
    if "boards.device_id" in exc_str or "uq_device_id" in exc_str:
        raise HTTPException(status_code=422, detail="Device ID is already in use by another device")
    raise HTTPException(status_code=422, detail="Device name is already in use")


def _now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _build_device_out(board: Board, db: AsyncSession) -> DeviceOut:
    agent_online = False
    if board.agent:
        delta = (_now_utc() - board.agent.last_seen).total_seconds()
        agent_online = delta < 90

    active_booking = None
    for bk in board.bookings:
        if bk.active:
            active_booking = BookingOut(
                id=bk.id,
                board_id=bk.board_id,
                board_name=board.name,
                username=bk.username,
                start_time=bk.start_time,
                end_time=bk.end_time,
                extended=bk.extended,
                active=bk.active,
                release_reason=bk.release_reason,
            )
            break

    return DeviceOut(
        id=board.id,
        device_id=board.device_id,
        serial_number=board.serial_number,
        revision=board.revision,
        name=board.name,
        description=board.description,
        location=board.location,
        current_notes=board.current_notes,
        device_ip=board.device_ip,
        agent_id=board.agent_id,
        host_ip=board.host_ip,
        features=json.loads(board.features) if board.features else {},
        jtag_port=board.jtag_port,
        ssh_user=board.ssh_user,
        ssh_port=board.ssh_port,
        power_script=board.power_script,
        power_args=json.loads(board.power_args) if board.power_args else {},
        usb_device=board.usb_device or "",
        uart_device=board.uart_device or "",
        sdmux_control=board.sdmux_control or "",
        sdmux_sdcard=board.sdmux_sdcard or "",
        enabled=board.enabled,
        agent_online=agent_online,
        active_booking=active_booking,
    )


async def _load_device(device_id: str, db: AsyncSession) -> Board:
    result = await db.execute(
        select(Board)
        .where(Board.id == device_id)
        .options(
            selectinload(Board.agent),
            selectinload(Board.bookings),
        )
    )
    board = result.scalar_one_or_none()
    if board is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return board


@router.get("", response_model=list[DeviceOut])
async def list_devices(
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Board).options(
            selectinload(Board.agent),
            selectinload(Board.bookings),
        )
    )
    boards = result.scalars().all()
    return [await _build_device_out(b, db) for b in boards]


@router.get("/{device_id}", response_model=DeviceOut)
async def get_device(
    device_id: str,
    db: AsyncSession = Depends(get_db),
):
    board = await _load_device(device_id, db)
    return await _build_device_out(board, db)


@router.post("", response_model=DeviceOut, status_code=201)
async def create_device(
    body: DeviceIn,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(require_user),
):
    board = Board(
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
        usb_device=body.usb_device,
        uart_device=body.uart_device,
        sdmux_control=body.sdmux_control,
        sdmux_sdcard=body.sdmux_sdcard,
        enabled=body.enabled,
    )
    db.add(board)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        _raise_uniqueness_error(str(exc))
    board = await _load_device(board.id, db)
    await log_action(db, "board_created", user, board.id, board.name, f"location='{body.location}'", device_id=board.device_id)
    await db.commit()
    return await _build_device_out(board, db)


@router.patch("/{device_id}", response_model=DeviceOut)
async def update_device(
    device_id: str,
    body: DeviceUpdate,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(require_user),
):
    board = await _load_device(device_id, db)
    for field, value in body.model_dump(exclude_none=True).items():
        if field in ("features", "power_args"):
            setattr(board, field, json.dumps(value))
        else:
            setattr(board, field, value)
    detail = ", ".join(f"{k}='{v}'" for k, v in body.model_dump(exclude_none=True).items())
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        _raise_uniqueness_error(str(exc))
    board = await _load_device(device_id, db)
    await log_action(db, "board_updated", user, device_id, board.name, detail, device_id=board.device_id)
    await db.commit()
    return await _build_device_out(board, db)


@router.delete("/{device_id}", status_code=204)
async def delete_device(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(require_user),
):
    board = await _load_device(device_id, db)
    for bk in board.bookings:
        if bk.active:
            raise HTTPException(
                status_code=409, detail="Device has an active booking; release it first"
            )
    await log_action(db, "board_deleted", user, board.id, board.name, "", device_id=board.device_id)
    await db.delete(board)
    await db.commit()
