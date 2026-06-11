from __future__ import annotations

import asyncio
import logging
import socket
from typing import Any

from zeroconf import IPVersion, ServiceInfo, Zeroconf
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf

logger = logging.getLogger(__name__)

SERVICE_TYPE = "_boardfarm._tcp.local."

_zeroconf: AsyncZeroconf | None = None
_service_info: ServiceInfo | None = None
_discovered: dict[str, dict[str, Any]] = {}


async def _fetch_service_info(zc: Zeroconf, service_type: str, name: str) -> None:
    """Async lookup for a discovered service — safe to call from the event loop."""
    info = AsyncServiceInfo(service_type, name)
    await info.async_request(zc, 3000)
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


class _Listener:
    """ServiceListener that schedules async info lookups instead of blocking."""

    def add_service(self, zc: Zeroconf, service_type: str, name: str) -> None:
        asyncio.ensure_future(_fetch_service_info(zc, service_type, name))

    def remove_service(self, zc: Zeroconf, service_type: str, name: str) -> None:
        _discovered.pop(name, None)
        logger.info("Agent left: %s", name)

    def update_service(self, zc: Zeroconf, service_type: str, name: str) -> None:
        asyncio.ensure_future(_fetch_service_info(zc, service_type, name))


async def start(agent_name: str, host_ip: str, port: int, device_count: int) -> None:
    global _zeroconf, _service_info

    _zeroconf = AsyncZeroconf(ip_version=IPVersion.V4Only)

    _service_info = ServiceInfo(
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

    await _zeroconf.async_register_service(_service_info)
    AsyncServiceBrowser(_zeroconf.zeroconf, SERVICE_TYPE, listener=_Listener())
    logger.info("mDNS: advertising %s at %s:%d", agent_name, host_ip, port)


async def stop() -> None:
    global _zeroconf, _service_info
    if _zeroconf and _service_info:
        await _zeroconf.async_unregister_service(_service_info)
        await _zeroconf.async_close()
        _zeroconf = None
        _service_info = None


def get_discovered() -> list[dict[str, Any]]:
    return list(_discovered.values())
