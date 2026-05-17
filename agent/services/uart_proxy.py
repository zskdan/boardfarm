import asyncio
import logging
import os
import signal
import subprocess

logger = logging.getLogger(__name__)

# board_id -> asyncio.Task (the monitor task)
_tasks: dict[str, asyncio.Task] = {}
# board_id -> bool (True = should keep running)
_active: dict[str, bool] = {}
_locks: dict[str, asyncio.Lock] = {}


def _get_lock(board_id: str) -> asyncio.Lock:
    if board_id not in _locks:
        _locks[board_id] = asyncio.Lock()
    return _locks[board_id]


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


async def _monitor(board_id: str, uart_device: str, baud: int, tcp_port: int) -> None:
    """Keep socat running as long as board_id is in _active."""
    loop = asyncio.get_event_loop()
    while _active.get(board_id):
        proc = _start_socat(uart_device, baud, tcp_port)
        if proc is None:
            return  # socat not available, give up
        logger.info("UART proxy started for board %s (pid %d)", board_id, proc.pid)
        # Wait for process to exit (non-blocking via executor)
        await loop.run_in_executor(None, proc.wait)
        if _active.get(board_id):
            logger.warning("UART proxy exited for board %s; restarting in 2s", board_id)
            await asyncio.sleep(2)
    logger.info("UART proxy stopped for board %s", board_id)


async def start(board_id: str, uart_device: str, baud: int, tcp_port: int) -> bool:
    if not uart_device:
        return False
    async with _get_lock(board_id):
        if _active.get(board_id):
            logger.info("UART proxy already active for board %s", board_id)
            return True
        _active[board_id] = True
        task = asyncio.create_task(_monitor(board_id, uart_device, baud, tcp_port))
        _tasks[board_id] = task
        return True


async def stop(board_id: str) -> None:
    async with _get_lock(board_id):
        if not _active.get(board_id):
            return
        _active[board_id] = False
        task = _tasks.pop(board_id, None)
        if task:
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=3)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass


async def stop_all() -> None:
    for board_id in list(_active):
        await stop(board_id)
