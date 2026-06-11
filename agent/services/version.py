from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


async def run_script(script_path: str) -> str | None:
    """Run a version script and return its first line of stdout, or None on failure."""
    path = Path(script_path)
    if not path.exists():
        logger.warning("Version script not found: %s", script_path)
        return None
    try:
        proc = await asyncio.create_subprocess_exec(
            str(path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        if proc.returncode != 0:
            logger.warning("Version script failed (rc=%d): %s", proc.returncode, stderr.decode().strip())
            return None
        version = stdout.decode().strip().split("\n")[0]
        return version or None
    except asyncio.TimeoutError:
        logger.warning("Version script timed out: %s", script_path)
        return None
    except Exception:
        logger.exception("Error running version script: %s", script_path)
        return None


async def push_version(server_url: str, server_token: str, device_id: str, version: str) -> None:
    url = f"{server_url}/devices/{device_id}/version"
    headers = {"X-Token": server_token} if server_token else {}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.patch(url, json={"version": version}, headers=headers)
        logger.info("Reported version '%s' for device %s", version, device_id)
    except Exception:
        logger.debug("Could not push version for device %s", device_id)


async def _device_loop(server_url: str, server_token: str, device, interval: int) -> None:
    while True:
        await asyncio.sleep(interval)
        version = await run_script(device.version_script)
        if version is not None:
            await push_version(server_url, server_token, device.id, version)


async def version_loop(server_url: str, server_token: str, devices: list, default_interval: int = 300) -> None:
    """Spawn one polling loop per device that has a version_script configured."""
    tasks = []
    for device in devices:
        if not device.version_script:
            continue
        interval = device.version_poll_interval if device.version_poll_interval > 0 else default_interval
        tasks.append(_device_loop(server_url, server_token, device, interval))
    if tasks:
        await asyncio.gather(*tasks)
