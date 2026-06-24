from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# check-version lives alongside the package (boardfarm_agent/scripts/check-version in the repo,
# /opt/boardfarm/agent/scripts/check-version when installed).
# In the repo:    __file__ = .../boardfarm_agent/services/version.py  → .parent.parent = .../boardfarm_agent/
# When installed: __file__ = .../agent/boardfarm_agent/services/version.py → .parent.parent = .../agent/boardfarm_agent/
# Try the dev path first; fall back one level for the installed layout.
_pkg_root = Path(__file__).parent.parent
_CHECK_VERSION = (
    _pkg_root / "scripts" / "check-version"
    if (_pkg_root / "scripts" / "check-version").exists()
    else _pkg_root.parent / "scripts" / "check-version"
)

logger.info("check-version path: %s (exists=%s)", _CHECK_VERSION, _CHECK_VERSION.exists())


async def run_script(get_script: str, ref_file: str) -> str | None:
    """Run check-version with the given GET_SCRIPT and REF_FILE and return full stdout.

    Returns None on any failure (script missing, non-zero exit, timeout).
    The first line of stdout is the version badge; remaining lines are content or diff.
    """
    if not get_script:
        return None
    if not _CHECK_VERSION.exists():
        logger.warning("check-version script not found at %s", _CHECK_VERSION)
        return None
    if not Path(get_script).exists():
        logger.warning("version_script not found: %s", get_script)
        return None
    if ref_file and not Path(ref_file).exists():
        logger.warning("version_ref_file not found: %s", ref_file)
        return None
    logger.debug("Running: %s %s %s", _CHECK_VERSION, get_script, ref_file)
    try:
        proc = await asyncio.create_subprocess_exec(
            str(_CHECK_VERSION), get_script, ref_file,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        if proc.returncode != 0:
            logger.warning(
                "check-version failed (rc=%d) for %s: %s",
                proc.returncode, get_script, stderr.decode().strip(),
            )
            return None
        result = stdout.decode().strip()
        logger.debug("check-version output: %s", result[:120])
        return result or None
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
            resp = await client.patch(url, json={"version": version}, headers=headers)
        if resp.status_code >= 300:
            logger.warning("push_version got HTTP %d for device %s: %s", resp.status_code, device_id, resp.text)
        else:
            logger.info("Reported version for device %s: %s", device_id, version[:60])
    except Exception:
        logger.warning("Could not push version for device %s", device_id, exc_info=True)


async def _device_loop(server_url: str, server_token: str, device, interval: int) -> None:
    logger.info(
        "Version polling started for device %s | script=%s ref=%s interval=%ds",
        device.id, device.version_script, device.version_ref_file, interval,
    )
    while True:
        version = await run_script(device.version_script, device.version_ref_file)
        if version is not None:
            await push_version(server_url, server_token, device.id, version)
        await asyncio.sleep(interval)


async def version_loop(server_url: str, server_token: str, fetch_or_list, default_interval: int = 300) -> None:
    """Dynamically manage per-device version polling tasks.

    fetch_or_list may be:
      - a callable (coroutine function) returning a list of DeviceConfig — called every 60s
      - a static list of DeviceConfig (legacy / unit-test path)
    """
    active: dict[str, asyncio.Task] = {}
    active_cfg: dict[str, tuple] = {}  # did → (version_script, version_ref_file, interval)

    while True:
        if callable(fetch_or_list):
            devices = await fetch_or_list()
        else:
            devices = list(fetch_or_list)

        current = {d.id: d for d in devices if d.version_script}

        # Cancel tasks for devices no longer needing polling or whose config changed
        cancelled = []
        for did in list(active):
            device = current.get(did)
            if device is None or active[did].done():
                if device is None:
                    logger.info("Stopping version polling for device %s (removed/unconfigured)", did)
                task = active.pop(did)
                active_cfg.pop(did, None)
                task.cancel()
                cancelled.append(task)
            else:
                interval = device.version_poll_interval if device.version_poll_interval > 0 else default_interval
                cfg = (device.version_script, device.version_ref_file, interval)
                if cfg != active_cfg.get(did):
                    logger.info("Config changed for device %s — restarting version polling", did)
                    task = active.pop(did)
                    active_cfg.pop(did, None)
                    task.cancel()
                    cancelled.append(task)
        for task in cancelled:
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

        # Start tasks for newly discovered devices (or restarted ones)
        for did, device in current.items():
            if did not in active:
                interval = device.version_poll_interval if device.version_poll_interval > 0 else default_interval
                logger.info("Starting version polling for device %s (interval=%ds)", did, interval)
                active[did] = asyncio.create_task(_device_loop(server_url, server_token, device, interval))
                active_cfg[did] = (device.version_script, device.version_ref_file, interval)

        if not current:
            logger.info("No devices with version_script configured — will recheck in 60s")

        await asyncio.sleep(60)
