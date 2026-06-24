from __future__ import annotations

import asyncio
import logging
import socket
from typing import Any

from zeroconf import IPVersion, ServiceInfo, ServiceStateChange, Zeroconf
from zeroconf.asyncio import AsyncServiceBrowser, AsyncZeroconf

logger = logging.getLogger(__name__)

SERVICE_TYPE = "_boardfarm._tcp.local."

_zeroconf: AsyncZeroconf | None = None
_registered_info: ServiceInfo | None = None
_discovered: dict[str, dict[str, Any]] = {}


async def _fetch_service_info(zc: Zeroconf, service_type: str, name: str) -> None:
    """Resolve service details in a thread pool so we never call the sync
    ServiceInfo.request() from the event loop (which raises RuntimeError in
    modern zeroconf)."""
    info = ServiceInfo(service_type, name)
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, info.request, zc, 3000)
    except Exception:
        logger.debug("mDNS lookup failed for %s", name)
        return
    if not info.addresses:
        return
    address = socket.inet_ntoa(info.addresses[0])
    url = f"http://{address}:{info.port}" if info.port else None
    agent_name = name.replace(f".{SERVICE_TYPE}", "").replace("._boardfarm._tcp.local.", "")
    _discovered[name] = {
        "name": agent_name,
        "url": url,
        "properties": {
            (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
            for k, v in (info.properties or {}).items()
        },
    }
    logger.info("Discovered agent: %s at %s", agent_name, url)


def _on_service_state_change(
    zeroconf: Zeroconf, service_type: str, name: str, state_change: ServiceStateChange
) -> None:
    if state_change is ServiceStateChange.Removed:
        _discovered.pop(name, None)
        logger.info("Agent left: %s", name)
        return
    # Schedule the async lookup — called from the event loop via AsyncServiceBrowser
    asyncio.ensure_future(_fetch_service_info(zeroconf, service_type, name))


async def start(agent_name: str, host_ip: str, port: int, device_count: int) -> None:
    global _zeroconf, _registered_info

    _zeroconf = AsyncZeroconf(ip_version=IPVersion.V4Only)

    _registered_info = ServiceInfo(
        SERVICE_TYPE,
        f"{agent_name}.{SERVICE_TYPE}",
        addresses=[socket.inet_aton(host_ip)],
        port=port,
        properties={
            "version": "0.1.0",
            "devices": str(device_count),
        },
        server=f"{agent_name}.local.",
    )

    await _zeroconf.async_register_service(_registered_info)
    try:
        AsyncServiceBrowser(_zeroconf.zeroconf, SERVICE_TYPE, handlers=[_on_service_state_change])
    except Exception:
        logger.warning("mDNS service discovery unavailable")
    logger.info("mDNS: advertising %s at %s:%d", agent_name, host_ip, port)


async def stop() -> None:
    global _zeroconf, _registered_info
    if _zeroconf and _registered_info:
        try:
            await _zeroconf.async_unregister_service(_registered_info)
        except Exception:
            pass
        await _zeroconf.async_close()
        _zeroconf = None
        _registered_info = None


def get_discovered() -> list[dict[str, Any]]:
    return list(_discovered.values())
