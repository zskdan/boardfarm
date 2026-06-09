import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import init_db
from .expiry import expiry_loop
from .routers import agents, boards, bookings, tools
from .ws import ws_handler

logging.basicConfig(level=logging.INFO)


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
app.include_router(boards.router)
app.include_router(tools.router)
app.include_router(bookings.router)


@app.websocket("/ws/status")
async def ws_status(websocket: WebSocket):
    await ws_handler(websocket)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "0.1.0",
        "max_booking_hours": settings.max_booking_hours,
        "default_user": settings.default_user,
    }
