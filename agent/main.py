from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import config, DeviceConfig
from .heartbeat import heartbeat_loop
from .routers import devices as boards_router, hardware
from .services import health as health_svc
from .services import hw_server, mdns
from .services import version as version_svc

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def _register_with_server() -> None:
    url = f"{config.server_url}/agents/register"
    device_ids = [b.id for b in config.devices]
    agent_url = f"http://{config.host_ip}:{config.port}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                url,
                json={
                    "name": config.name,
                    "url": agent_url,
                    "device_ids": device_ids,
                    "token": config.agent_token,
                },
            )
        logger.info("Registered with server at %s", config.server_url)
    except Exception:
        logger.warning("Could not register with server at %s (will retry via heartbeat)", config.server_url)


async def _fetch_version_devices() -> list[DeviceConfig]:
    """Fetch ALL server devices that have version_script set, regardless of local config."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{config.server_url}/devices",
                headers={"X-Token": config.server_token, "X-User": "__agent__"},
            )
        if resp.status_code != 200:
            return []
        result = []
        for data in resp.json():
            if not data.get("version_script"):
                continue
            result.append(DeviceConfig(
                id=data["id"],
                version_script=data["version_script"],
                version_ref_file=data.get("version_ref_file", ""),
                version_poll_interval=data.get("version_poll_interval", 0),
            ))
        logger.info("Scheduling version polling for %d device(s)", len(result))
        return result
    except Exception:
        logger.warning("Could not fetch version devices from server")
        return []


async def _recover_active_bookings() -> None:
    """On startup, restart services for any devices that have active bookings."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{config.server_url}/bookings",
                params={"active": "true"},
                headers={"X-Token": config.server_token, "X-User": "__agent__"},
            )
            if resp.status_code != 200:
                return
            bookings = resp.json()
        our_device_ids = {b.id for b in config.devices}
        device_map = {b.id: b for b in config.devices}
        for booking in bookings:
            bid = booking["device_id"]
            if bid in our_device_ids:
                b = device_map[bid]
                logger.info("Recovering services for device %s (active booking: %s)", bid, booking["id"])
                await hw_server.start(bid, b.jtag_port)
    except Exception:
        logger.warning("Could not recover active bookings from server (will retry on next booking event)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await mdns.start(config.name, config.host_ip, config.port, len(config.devices))
    await _register_with_server()
    await _recover_active_bookings()
    version_devices = await _fetch_version_devices()
    agent_url = f"http://{config.host_ip}:{config.port}"
    hb_task = asyncio.create_task(heartbeat_loop(config.server_url, config.name, agent_url, [b.id for b in config.devices], config.agent_token))
    health_task = asyncio.create_task(health_svc.probe_loop(config.devices))
    version_task = asyncio.create_task(
        version_svc.version_loop(config.server_url, config.server_token, version_devices, config.version_poll_interval)
    )

    yield

    for task in (hb_task, health_task, version_task):
        task.cancel()
    for task in (hb_task, health_task, version_task):
        try:
            await task
        except asyncio.CancelledError:
            pass
    await hw_server.stop_all()
    await mdns.stop()


app = FastAPI(title="Boardfarm Agent", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(boards_router.router)
app.include_router(hardware.router)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "0.1.0",
        "agent": config.name,
        "devices": [b.id for b in config.devices],
    }


@app.get("/agents")
async def list_local_agents():
    """Returns self + mDNS-discovered peers (no auth — used by frontend for discovery)."""
    self_entry = {
        "name": config.name,
        "url": f"http://{config.host_ip}:{config.port}",
        "device_count": len(config.devices),
        "self": True,
    }
    peers = [
        {**p, "self": False, "device_count": int(p.get("properties", {}).get("devices", 0))}
        for p in mdns.get_discovered()
    ]
    return [self_entry] + peers
