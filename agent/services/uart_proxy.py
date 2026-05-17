import asyncio
import logging
import subprocess

logger = logging.getLogger(__name__)

_processes: dict[str, subprocess.Popen] = {}
_locks: dict[str, asyncio.Lock] = {}


def _get_lock(board_id: str) -> asyncio.Lock:
    if board_id not in _locks:
        _locks[board_id] = asyncio.Lock()
    return _locks[board_id]


async def start(board_id: str, uart_device: str, baud: int, tcp_port: int) -> bool:
    if not uart_device:
        logger.info("No UART device configured for board %s; skipping proxy", board_id)
        return False

    async with _get_lock(board_id):
        if board_id in _processes and _processes[board_id].poll() is None:
            logger.info("UART proxy already running for board %s", board_id)
            return True
        try:
            cmd = [
                "socat",
                f"TCP4-LISTEN:{tcp_port},fork,reuseaddr",
                f"{uart_device},raw,b{baud},echo=0",
            ]
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            _processes[board_id] = proc
            logger.info(
                "Started UART proxy for board %s: %s -> TCP:%d",
                board_id,
                uart_device,
                tcp_port,
            )
            return True
        except FileNotFoundError:
            logger.warning("socat not found; UART proxy unavailable for board %s", board_id)
            return False
        except Exception:
            logger.exception("Failed to start UART proxy for board %s", board_id)
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
            logger.info("Stopped UART proxy for board %s", board_id)
        except Exception:
            logger.exception("Error stopping UART proxy for board %s", board_id)


async def stop_all() -> None:
    for board_id in list(_processes):
        await stop(board_id)
