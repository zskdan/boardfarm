import asyncio
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import config
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
                json={"name": config.name, "url": agent_url, "device_ids": device_ids},
            )
        logger.info("Registered with server at %s", config.server_url)
    except Exception:
        logger.warning("Could not register with server at %s (will retry via heartbeat)", config.server_url)


async def _fetch_device_version_configs() -> None:
    """Pull version fields from the server for each device."""
    for device in config.devices:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    f"{config.server_url}/devices/{device.id}",
                    headers={"X-Token": config.server_token, "X-User": "__agent__"},
                )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("version_script"):
                    device.version_script = data["version_script"]
                if data.get("version_ref_file"):
                    device.version_ref_file = data["version_ref_file"]
                if data.get("version_poll_interval", 0) > 0:
                    device.version_poll_interval = data["version_poll_interval"]
        except Exception:
            logger.debug("Could not fetch version config for device %s", device.id)


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
    await _fetch_device_version_configs()
    await _recover_active_bookings()
    agent_url = f"http://{config.host_ip}:{config.port}"
    hb_task = asyncio.create_task(heartbeat_loop(config.server_url, config.name, agent_url, [b.id for b in config.devices]))
    health_task = asyncio.create_task(health_svc.probe_loop(config.devices))
    version_task = asyncio.create_task(
        version_svc.version_loop(config.server_url, config.server_token, config.devices, config.version_poll_interval)
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
