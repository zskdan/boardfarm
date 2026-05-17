import asyncio
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import config
from .heartbeat import heartbeat_loop
from .routers import boards, hardware
from .services import hw_server, mdns, uart_proxy

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def _register_with_server() -> None:
    url = f"{config.server_url}/agents/register"
    board_ids = [b.id for b in config.boards]
    agent_url = f"http://{config.host_ip}:{config.port}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                url,
                json={"name": config.name, "url": agent_url, "board_ids": board_ids},
            )
        logger.info("Registered with server at %s", config.server_url)
    except Exception:
        logger.warning("Could not register with server at %s (will retry via heartbeat)", config.server_url)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await mdns.start(config.name, config.host_ip, config.port, len(config.boards))
    await _register_with_server()
    hb_task = asyncio.create_task(heartbeat_loop(config.server_url, config.name))

    yield

    hb_task.cancel()
    try:
        await hb_task
    except asyncio.CancelledError:
        pass
    await hw_server.stop_all()
    await uart_proxy.stop_all()
    await mdns.stop()


app = FastAPI(title="Boardfarm Agent", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(boards.router)
app.include_router(hardware.router)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "0.1.0",
        "agent": config.name,
        "boards": [b.id for b in config.boards],
    }


@app.get("/agents")
async def list_local_agents():
    """Returns self + mDNS-discovered peers (no auth — used by frontend for discovery)."""
    self_entry = {
        "name": config.name,
        "url": f"http://{config.host_ip}:{config.port}",
        "board_count": len(config.boards),
        "self": True,
    }
    peers = [
        {**p, "self": False, "board_count": int(p.get("properties", {}).get("boards", 0))}
        for p in mdns.get_discovered()
    ]
    return [self_entry] + peers
