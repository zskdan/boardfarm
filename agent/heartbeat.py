import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)
HEARTBEAT_INTERVAL = 30


async def heartbeat_loop(server_url: str, agent_name: str) -> None:
    url = f"{server_url}/agents/heartbeat"
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL)
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(url, json={"name": agent_name})
        except Exception:
            logger.debug("Heartbeat failed (server unreachable)")
