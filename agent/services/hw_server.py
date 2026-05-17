import asyncio
import logging
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

_processes: dict[str, subprocess.Popen] = {}
_locks: dict[str, asyncio.Lock] = {}


def _get_lock(board_id: str) -> asyncio.Lock:
    if board_id not in _locks:
        _locks[board_id] = asyncio.Lock()
    return _locks[board_id]


async def start(board_id: str, jtag_port: int) -> bool:
    async with _get_lock(board_id):
        if board_id in _processes and _processes[board_id].poll() is None:
            logger.info("hw_server already running for board %s", board_id)
            return True
        try:
            proc = subprocess.Popen(
                ["hw_server", "-s", f"tcp::{jtag_port}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            _processes[board_id] = proc
            logger.info("Started hw_server for board %s on port %d", board_id, jtag_port)
            return True
        except FileNotFoundError:
            logger.warning("hw_server not found; JTAG will not be available for board %s", board_id)
            return False
        except Exception:
            logger.exception("Failed to start hw_server for board %s", board_id)
            return False


async def stop(board_id: str) -> None:
    async with _get_lock(board_id):
        proc = _processes.pop(board_id, None)
        if proc is None:
            return
        try:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            logger.info("Stopped hw_server for board %s", board_id)
        except Exception:
            logger.exception("Error stopping hw_server for board %s", board_id)


async def stop_all() -> None:
    for board_id in list(_processes):
        await stop(board_id)
