from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class DeviceConfig:
    id: str
    usb_device: str = ""
    uart_device: str = ""
    jtag_port: int = 3121
    power_script: str = ""
    power_args: dict = field(default_factory=dict)
    host_check_ip: str = ""
    host_check_port: int = 22
    version_script: str = ""
    version_poll_interval: int = 0  # 0 = use agent-level default; >0 = per-device override
    access_control_script: str = ""
    redeployment_script: str = ""


@dataclass
class AgentConfig:
    name: str = "boardfarm-agent"
    port: int = 8766
    server_url: str = "http://localhost:8765"
    server_token: str = "changeme"
    agent_token: str = "agent-secret"  # Token the agent requires for incoming calls from server
    host_ip: str = "127.0.0.1"
    version_poll_interval: int = 300  # seconds between version checks
    devices: list[DeviceConfig] = field(default_factory=list)


def load_config(path: str = "config.yaml") -> AgentConfig:
    cfg_file = Path(path)
    if not cfg_file.exists():
        return AgentConfig()

    data = yaml.safe_load(cfg_file.read_text()) or {}
    agent_data = data.get("agent", {})

    devices = []
    for b in data.get("devices", []):
        devices.append(
            DeviceConfig(
                id=b["id"],
                usb_device=b.get("usb_device", ""),
                uart_device=b.get("uart_device", ""),
                jtag_port=b.get("jtag_port", 3121),
                power_script=b.get("power_script", ""),
                power_args=b.get("power_args", {}),
                host_check_ip=b.get("host_check_ip", ""),
                host_check_port=b.get("host_check_port", 22),
                version_script=b.get("version_script", ""),
                version_poll_interval=b.get("version_poll_interval", 0),
                access_control_script=b.get("access_control_script", ""),
                redeployment_script=b.get("redeployment_script", ""),
            )
        )

    return AgentConfig(
        name=agent_data.get("name", "boardfarm-agent"),
        port=agent_data.get("port", 8766),
        server_url=agent_data.get("server_url", "http://localhost:8765"),
        server_token=agent_data.get("server_token", "changeme"),
        agent_token=agent_data.get("agent_token", "agent-secret"),
        host_ip=agent_data.get("host_ip", "127.0.0.1"),
        version_poll_interval=agent_data.get("version_poll_interval", 300),
        devices=devices,
    )


config = load_config()
