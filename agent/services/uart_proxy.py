import asyncio
import logging
import os
import signal
import subprocess

logger = logging.getLogger(__name__)

# device_id -> asyncio.Task (the monitor task)
_tasks: dict[str, asyncio.Task] = {}
# device_id -> bool (True = should keep running)
_active: dict[str, bool] = {}
_locks: dict[str, asyncio.Lock] = {}


def _get_lock(device_id: str) -> asyncio.Lock:
    if device_id not in _locks:
        _locks[device_id] = asyncio.Lock()
    return _locks[device_id]


def _start_socat(uart_device: str, baud: int, tcp_port: int) -> subprocess.Popen | None:
    try:
        cmd = [
            "socat",
            f"TCP4-LISTEN:{tcp_port},fork,reuseaddr",
            f"{uart_device},raw,b{baud},echo=0",
        ]
        return subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid,
        )
    except FileNotFoundError:
        logger.warning("socat not found")
        return None
    except Exception:
        logger.exception("Failed to start socat")
        return None


async def _monitor(device_id: str, uart_device: str, baud: int, tcp_port: int) -> None:
    """Keep socat running as long as device_id is in _active."""
    loop = asyncio.get_event_loop()
    while _active.get(device_id):
        proc = _start_socat(uart_device, baud, tcp_port)
        if proc is None:
            return  # socat not available, give up
        logger.info("UART proxy started for device %s (pid %d)", device_id, proc.pid)
        # Wait for process to exit (non-blocking via executor)
        await loop.run_in_executor(None, proc.wait)
        if _active.get(device_id):
            logger.warning("UART proxy exited for device %s; restarting in 2s", device_id)
            await asyncio.sleep(2)
    logger.info("UART proxy stopped for device %s", device_id)


async def start(device_id: str, uart_device: str, baud: int, tcp_port: int) -> bool:
    if not uart_device:
        return False
    async with _get_lock(device_id):
        if _active.get(device_id):
            logger.info("UART proxy already active for device %s", device_id)
            return True
        _active[device_id] = True
        task = asyncio.create_task(_monitor(device_id, uart_device, baud, tcp_port))
        _tasks[device_id] = task
        return True


async def stop(device_id: str) -> None:
    async with _get_lock(device_id):
        if not _active.get(device_id):
            return
        _active[device_id] = False
        task = _tasks.pop(device_id, None)
        if task:
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=3)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass


async def stop_all() -> None:
    for device_id in list(_active):
        await stop(device_id)
