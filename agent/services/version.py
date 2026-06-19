from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# check-version lives alongside the agent package (agent/scripts/check-version in the repo,
# /opt/boardfarm/agent/scripts/check-version when installed).
_CHECK_VERSION = Path(__file__).parent.parent / "scripts" / "check-version"


async def run_script(get_script: str, ref_file: str) -> str | None:
    """Run check-version with the given GET_SCRIPT and REF_FILE and return full stdout.

    Returns None on any failure (script missing, non-zero exit, timeout).
    The first line of stdout is the version badge; remaining lines are content or diff.
    """
    if not get_script:
        return None
    if not _CHECK_VERSION.exists():
        logger.warning("check-version script not found: %s", _CHECK_VERSION)
        return None
    try:
        proc = await asyncio.create_subprocess_exec(
            str(_CHECK_VERSION), get_script, ref_file,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        if proc.returncode != 0:
            logger.warning("check-version failed (rc=%d): %s", proc.returncode, stderr.decode().strip())
            return None
        return stdout.decode().strip() or None
    except asyncio.TimeoutError:
        logger.warning("check-version timed out for get_script=%s", get_script)
        return None
    except Exception:
        logger.exception("Error running check-version for get_script=%s", get_script)
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
        version = await run_script(device.version_script, device.version_ref_file)
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
