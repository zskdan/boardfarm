import asyncio
import logging
import subprocess
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import init_db
from .expiry import expiry_loop
from .routers import activity, agents, bookings, devices, setups, tools
from .ws import ws_handler

logging.basicConfig(level=logging.INFO)


def _git_version() -> str:
    try:
        sha = subprocess.check_output(
            ['git', 'rev-parse', '--short=8', 'HEAD'],
            stderr=subprocess.DEVNULL, text=True,
        ).strip()
        try:
            tag = subprocess.check_output(
                ['git', 'describe', '--tags', '--abbrev=0'],
                stderr=subprocess.DEVNULL, text=True,
            ).strip()
        except subprocess.CalledProcessError:
            tag = ''
        dirty = bool(subprocess.check_output(
            ['git', 'status', '--porcelain'], text=True,
        ).strip())
        base = f"{tag}-{sha}" if tag else sha
        return f"{base}-dirty" if dirty else base
    except Exception:
        return 'unknown'


_VERSION = _git_version()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    task = asyncio.create_task(expiry_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Boardfarm Server", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agents.router)
app.include_router(devices.router)
app.include_router(tools.router)
app.include_router(bookings.router)
app.include_router(activity.router)
app.include_router(setups.router)


@app.websocket("/ws/status")
async def ws_status(websocket: WebSocket):
    await ws_handler(websocket)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": _VERSION,
        "max_booking_hours": settings.max_booking_hours,
        "default_user": settings.default_user,
    }
