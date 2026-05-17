import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class BoardConfig:
    id: str
    uart_device: str = ""
    uart_baud: int = 115200
    jtag_port: int = 3121
    uart_tcp_port: int = 5555
    power_script: str = ""
    power_args: dict = field(default_factory=dict)


@dataclass
class AgentConfig:
    name: str = "boardfarm-agent"
    port: int = 8766
    server_url: str = "http://localhost:8765"
    server_token: str = "changeme"
    host_ip: str = "127.0.0.1"
    boards: list[BoardConfig] = field(default_factory=list)


def load_config(path: str = "config.yaml") -> AgentConfig:
    cfg_file = Path(path)
    if not cfg_file.exists():
        return AgentConfig()

    data = yaml.safe_load(cfg_file.read_text()) or {}
    agent_data = data.get("agent", {})

    boards = []
    for b in data.get("boards", []):
        boards.append(
            BoardConfig(
                id=b["id"],
                uart_device=b.get("uart_device", ""),
                uart_baud=b.get("uart_baud", 115200),
                jtag_port=b.get("jtag_port", 3121),
                uart_tcp_port=b.get("uart_tcp_port", 5555),
                power_script=b.get("power_script", ""),
                power_args=b.get("power_args", {}),
            )
        )

    return AgentConfig(
        name=agent_data.get("name", "boardfarm-agent"),
        port=agent_data.get("port", 8766),
        server_url=agent_data.get("server_url", "http://localhost:8765"),
        server_token=agent_data.get("server_token", "changeme"),
        host_ip=agent_data.get("host_ip", "127.0.0.1"),
        boards=boards,
    )


config = load_config()
