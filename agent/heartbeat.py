from __future__ import annotations

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)
HEARTBEAT_INTERVAL = 30


async def heartbeat_loop(server_url: str, agent_name: str, agent_url: str, device_ids: list[str], agent_token: str = "") -> None:
    hb_url = f"{server_url}/agents/heartbeat"
    reg_url = f"{server_url}/agents/register"

    async def _register():
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(reg_url, json={
                    "name": agent_name,
                    "url": agent_url,
                    "device_ids": device_ids,
                    "token": agent_token,
                })
            logger.info("Re-registered with server")
        except Exception:
            logger.debug("Re-registration failed (server unreachable)")

    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL)
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.post(hb_url, json={"name": agent_name})
            if resp.status_code == 404:
                # Agent not known to server - re-register
                await _register()
        except Exception:
            logger.debug("Heartbeat failed (server unreachable)")
