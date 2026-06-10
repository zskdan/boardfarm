from __future__ import annotations

import logging
import socket
from typing import Any

from zeroconf import IPVersion, ServiceInfo, Zeroconf
from zeroconf.asyncio import AsyncServiceBrowser, AsyncZeroconf

logger = logging.getLogger(__name__)

SERVICE_TYPE = "_boardfarm._tcp.local."

_zeroconf: AsyncZeroconf | None = None
_service_info: ServiceInfo | None = None
_discovered: dict[str, dict[str, Any]] = {}


class _Listener:
    def add_service(self, zc: Zeroconf, service_type: str, name: str) -> None:
        info = zc.get_service_info(service_type, name)
        if info:
            addresses = [socket.inet_ntoa(a) for a in info.addresses]
            url = f"http://{addresses[0]}:{info.port}" if addresses else None
            agent_name = name.replace(f".{SERVICE_TYPE}", "").replace(
                f"._boardfarm._tcp.local.", ""
            )
            _discovered[name] = {
                "name": agent_name,
                "url": url,
                "properties": {
                    k.decode(): v.decode() for k, v in (info.properties or {}).items()
                },
            }
            logger.info("Discovered agent: %s at %s", agent_name, url)

    def remove_service(self, zc: Zeroconf, service_type: str, name: str) -> None:
        _discovered.pop(name, None)
        logger.info("Agent left: %s", name)

    def update_service(self, zc: Zeroconf, service_type: str, name: str) -> None:
        self.add_service(zc, service_type, name)


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
    AsyncServiceBrowser(_zeroconf.zeroconf, SERVICE_TYPE, handlers=[_Listener()])
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
