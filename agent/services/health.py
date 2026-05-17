import asyncio
import logging
import socket

logger = logging.getLogger(__name__)

# board_id -> bool
_health: dict[str, bool] = {}


def _tcp_reachable(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


async def probe_board(board_id: str, host_ip: str, check_port: int = 22) -> bool:
    """Check if board responds on TCP (default: SSH port)."""
    loop = asyncio.get_event_loop()
    reachable = await loop.run_in_executor(
        None, _tcp_reachable, host_ip, check_port
    )
    _health[board_id] = reachable
    return reachable


async def probe_loop(boards_cfg: list, interval: int = 60) -> None:
    """Periodically probe all boards. boards_cfg is list of BoardConfig."""
    while True:
        for b in boards_cfg:
            if b.host_check_ip and b.host_check_port:
                try:
                    await probe_board(b.id, b.host_check_ip, b.host_check_port)
                except Exception:
                    _health[b.id] = False
        await asyncio.sleep(interval)


def get_health(board_id: str) -> bool | None:
    return _health.get(board_id)
