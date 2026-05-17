import asyncio
import logging
import os
import signal
import socket
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(('127.0.0.1', port)) == 0

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
        if _port_in_use(jtag_port):
            logger.warning("Port %d already in use for board %s; hw_server may already be running", jtag_port, board_id)
            # Treat as success (another hw_server is already serving)
            return True
        try:
            proc = subprocess.Popen(
                ["hw_server", "-s", f"tcp::{jtag_port}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid,  # new process group
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
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            logger.info("Stopped hw_server for board %s", board_id)
        except ProcessLookupError:
            pass  # Already dead
        except Exception:
            logger.exception("Error stopping hw_server for board %s", board_id)


async def stop_all() -> None:
    for board_id in list(_processes):
        await stop(board_id)
