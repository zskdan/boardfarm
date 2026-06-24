from __future__ import annotations

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


def _get_lock(device_id: str) -> asyncio.Lock:
    if device_id not in _locks:
        _locks[device_id] = asyncio.Lock()
    return _locks[device_id]


async def start(device_id: str, jtag_port: int) -> bool:
    async with _get_lock(device_id):
        if device_id in _processes and _processes[device_id].poll() is None:
            logger.info("hw_server already running for device %s", device_id)
            return True
        if _port_in_use(jtag_port):
            logger.warning("Port %d already in use for device %s; hw_server may already be running", jtag_port, device_id)
            # Treat as success (another hw_server is already serving)
            return True
        try:
            proc = subprocess.Popen(
                ["hw_server", "-s", f"tcp::{jtag_port}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid,  # new process group
            )
            _processes[device_id] = proc
            logger.info("Started hw_server for device %s on port %d", device_id, jtag_port)
            return True
        except FileNotFoundError:
            logger.warning("hw_server not found; JTAG will not be available for device %s", device_id)
            return False
        except Exception:
            logger.exception("Failed to start hw_server for device %s", device_id)
            return False


async def stop(device_id: str) -> None:
    async with _get_lock(device_id):
        proc = _processes.pop(device_id, None)
        if proc is None:
            return
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            logger.info("Stopped hw_server for device %s", device_id)
        except ProcessLookupError:
            pass  # Already dead
        except Exception:
            logger.exception("Error stopping hw_server for device %s", device_id)


async def stop_all() -> None:
    for device_id in list(_processes):
        await stop(device_id)
