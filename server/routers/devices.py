from __future__ import annotations

import json
import secrets
import uuid

import httpx
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..audit import log_action
from ..auth import require_user
from ..config import settings
from ..database import get_db
from ..models import Agent, Device, Booking, Tool
from ..schemas import BookingOut, DeviceIn, DeviceOut, DeviceUpdate, ToolOut

router = APIRouter(prefix="/devices", tags=["devices"])


def _raise_uniqueness_error(exc_str: str) -> None:
    if "devices.device_id" in exc_str or "uq_device_id" in exc_str:
        raise HTTPException(status_code=422, detail="Device ID is already in use by another device")
    raise HTTPException(status_code=422, detail="Device name is already in use")


def _now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _build_device_out(
    device: Device,
    db: AsyncSession,
    agents_by_ip: dict[str, Agent] | None = None,
) -> DeviceOut:
    agent_online = False
    if device.agent:
        delta = (_now_utc() - device.agent.last_seen).total_seconds()
        agent_online = delta < 90
    elif device.host_ip:
        # No FK link yet — check if an agent with this IP is currently online
        if agents_by_ip is not None:
            ag = agents_by_ip.get(device.host_ip)
        else:
            res = await db.execute(
                select(Agent).where(Agent.url.like(f"http://{device.host_ip}:%"))
            )
            ag = res.scalar_one_or_none()
        if ag:
            delta = (_now_utc() - ag.last_seen).total_seconds()
            agent_online = delta < 90

    active_booking = None
    for bk in device.bookings:
        if bk.active:
            active_booking = BookingOut(
                id=bk.id,
                device_id=bk.device_id,
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
        usb_device=device.usb_device or "",
        uart_device=device.uart_device or "",
        sdmux_control=device.sdmux_control or "",
        sdmux_sdcard=device.sdmux_sdcard or "",
        access_control_script=device.access_control_script or "",
        enabled=device.enabled,
        agent_online=agent_online,
        deployed_version=device.deployed_version or "",
        version_script=device.version_script or "",
        version_ref_file=device.version_ref_file or "",
        version_poll_interval=device.version_poll_interval or 0,
        redeployment_script=device.redeployment_script or "",
        active_booking=active_booking,
        tools=[ToolOut.model_validate(t) for t in (device.tools or [])],
    )


async def _load_device(device_id: str, db: AsyncSession) -> Device:
    result = await db.execute(
        select(Device)
        .where(Device.id == device_id)
        .options(
            selectinload(Device.agent),
            selectinload(Device.bookings),
            selectinload(Device.tools),
        )
    )
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@router.get("", response_model=list[DeviceOut])
async def list_devices(
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Device).options(
            selectinload(Device.agent),
            selectinload(Device.bookings),
            selectinload(Device.tools),
        )
    )
    devices = result.scalars().all()

    agents_result = await db.execute(select(Agent))
    agents_by_ip: dict[str, Agent] = {
        a.url.split("//")[-1].split(":")[0]: a
        for a in agents_result.scalars().all()
    }

    return [await _build_device_out(d, db, agents_by_ip) for d in devices]


@router.get("/{device_id}", response_model=DeviceOut)
async def get_device(
    device_id: str,
    db: AsyncSession = Depends(get_db),
):
    device = await _load_device(device_id, db)
    return await _build_device_out(device, db)


@router.post("", response_model=DeviceOut, status_code=201)
async def create_device(
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
        usb_device=body.usb_device,
        uart_device=body.uart_device,
        sdmux_control=body.sdmux_control,
        sdmux_sdcard=body.sdmux_sdcard,
        access_control_script=body.access_control_script,
        enabled=body.enabled,
        version_script=body.version_script,
        version_ref_file=body.version_ref_file,
        version_poll_interval=body.version_poll_interval,
        redeployment_script=body.redeployment_script,
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


@router.patch("/{device_id}", response_model=DeviceOut)
async def update_device(
    device_id: str,
    body: DeviceUpdate,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(require_user),
):
    device = await _load_device(device_id, db)
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
    device = await _load_device(device_id, db)
    await log_action(db, "device_updated", user, device_id, device.name, detail, device_id=device.device_id)
    await db.commit()
    return await _build_device_out(device, db)


@router.delete("/{device_id}", status_code=204)
async def delete_device(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(require_user),
):
    device = await _load_device(device_id, db)
    for bk in device.bookings:
        if bk.active:
            raise HTTPException(
                status_code=409, detail="Device has an active booking; release it first"
            )
    await log_action(db, "device_deleted", user, device.id, device.name, "", device_id=device.device_id)
    await db.delete(device)
    await db.commit()


class _VersionReport(BaseModel):
    version: str


@router.patch("/{device_id}/version", status_code=204)
async def report_device_version(
    device_id: str,
    body: _VersionReport,
    db: AsyncSession = Depends(get_db),
    x_token: str | None = Header(default=None, alias="X-Token"),
):
    """Called by agents to report the deployed software version on a device."""
    if settings.token and not secrets.compare_digest(x_token or "", settings.token):
        raise HTTPException(status_code=401, detail="Invalid token")
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    device.deployed_version = body.version.strip()[:16384]
    await db.commit()


@router.post("/{device_id}/redeploy", status_code=200)
async def trigger_redeploy(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    user: str = Depends(require_user),
):
    """Proxy a redeploy request to the agent running the device."""
    device = await _load_device(device_id, db)
    if not device.redeployment_script:
        raise HTTPException(status_code=422, detail="No redeployment script configured for this device")

    agent_url = device.agent.url if device.agent else None
    if not agent_url and device.host_ip:
        res = await db.execute(
            select(Agent).where(Agent.url.like(f"http://{device.host_ip}:%"))
        )
        ag = res.scalar_one_or_none()
        if ag:
            agent_url = ag.url

    if not agent_url:
        raise HTTPException(status_code=503, detail="No agent available for this device")

    agent_token = device.agent.agent_token if device.agent else ""
    headers = {}
    if agent_token:
        headers["X-Agent-Token"] = agent_token
    try:
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(f"{agent_url}/devices/{device_id}/redeploy", headers=headers)
        if resp.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Agent error: {resp.text}")
        return resp.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Redeployment timed out")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Agent unreachable: {exc}")
