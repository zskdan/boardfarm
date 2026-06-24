"""
Tests for agent/config.py (load_config), agent/auth.py (require_agent_auth),
and agent/heartbeat.py (heartbeat_loop).
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from fastapi import HTTPException


# ===========================================================================
# agent/config.py — load_config
# ===========================================================================


def test_load_config_no_yaml_returns_defaults(monkeypatch, tmp_path):
    """When no config.yaml exists, load_config returns AgentConfig defaults."""
    monkeypatch.chdir(tmp_path)  # tmp_path has no config.yaml

    from boardfarm_agent.config import load_config

    cfg = load_config()
    assert cfg.name == "boardfarm-agent"
    assert cfg.port == 8766
    assert cfg.server_url == "http://localhost:8765"
    assert cfg.server_token == "changeme"
    assert cfg.agent_token == "agent-secret"
    assert cfg.host_ip == "127.0.0.1"
    assert cfg.version_poll_interval == 300
    assert cfg.devices == []


def test_load_config_all_agent_fields_overridden(monkeypatch, tmp_path):
    """config.yaml with all agent fields must override every default."""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        yaml.dump(
            {
                "agent": {
                    "name": "my-agent",
                    "port": 9000,
                    "server_url": "http://server:8765",
                    "server_token": "srv-tok",
                    "agent_token": "agt-tok",
                    "host_ip": "192.168.1.1",
                    "version_poll_interval": 60,
                }
            }
        )
    )
    monkeypatch.chdir(tmp_path)

    from boardfarm_agent.config import load_config

    cfg = load_config()
    assert cfg.name == "my-agent"
    assert cfg.port == 9000
    assert cfg.server_url == "http://server:8765"
    assert cfg.server_token == "srv-tok"
    assert cfg.agent_token == "agt-tok"
    assert cfg.host_ip == "192.168.1.1"
    assert cfg.version_poll_interval == 60


def test_load_config_devices_section(monkeypatch, tmp_path):
    """Devices listed in config.yaml are parsed into DeviceConfig objects."""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        yaml.dump(
            {
                "devices": [
                    {
                        "id": "dev-001",
                        "usb_device": "/dev/ttyUSB0",
                        "uart_device": "/dev/ttyAMA0",
                        "jtag_port": 3333,
                        "power_script": "/scripts/power.sh",
                        "power_args": {"outlet": 1},
                        "host_check_ip": "10.0.0.1",
                        "host_check_port": 80,
                        "version_script": "/scripts/version.sh",
                        "version_ref_file": "/refs/dev001.txt",
                        "version_poll_interval": 120,
                        "access_control_script": "/scripts/acl.sh",
                        "redeployment_script": "/scripts/redeploy.sh",
                    },
                    {
                        "id": "dev-002",
                        "usb_device": "/dev/ttyUSB1",
                    },
                ]
            }
        )
    )
    monkeypatch.chdir(tmp_path)

    from boardfarm_agent.config import load_config

    cfg = load_config()
    assert len(cfg.devices) == 2

    d1 = cfg.devices[0]
    assert d1.id == "dev-001"
    assert d1.usb_device == "/dev/ttyUSB0"
    assert d1.uart_device == "/dev/ttyAMA0"
    assert d1.jtag_port == 3333
    assert d1.power_script == "/scripts/power.sh"
    assert d1.power_args == {"outlet": 1}
    assert d1.host_check_ip == "10.0.0.1"
    assert d1.host_check_port == 80
    assert d1.version_script == "/scripts/version.sh"
    assert d1.version_ref_file == "/refs/dev001.txt"
    assert d1.version_poll_interval == 120
    assert d1.access_control_script == "/scripts/acl.sh"
    assert d1.redeployment_script == "/scripts/redeploy.sh"

    d2 = cfg.devices[1]
    assert d2.id == "dev-002"
    assert d2.usb_device == "/dev/ttyUSB1"
    # Fields not specified → defaults
    assert d2.uart_device == ""
    assert d2.jtag_port == 3121
    assert d2.version_poll_interval == 0


def test_load_config_empty_yaml_returns_defaults(monkeypatch, tmp_path):
    """An empty config.yaml (null YAML content) must return AgentConfig defaults."""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("")
    monkeypatch.chdir(tmp_path)

    from boardfarm_agent.config import load_config

    cfg = load_config()
    assert cfg.name == "boardfarm-agent"
    assert cfg.port == 8766
    assert cfg.devices == []


def test_load_config_agent_token_server_token_version_poll_interval(monkeypatch, tmp_path):
    """agent_token, server_token, and version_poll_interval are loaded from YAML."""
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        yaml.dump(
            {
                "agent": {
                    "agent_token": "secret-agt",
                    "server_token": "secret-srv",
                    "version_poll_interval": 42,
                }
            }
        )
    )
    monkeypatch.chdir(tmp_path)

    from boardfarm_agent.config import load_config

    cfg = load_config()
    assert cfg.agent_token == "secret-agt"
    assert cfg.server_token == "secret-srv"
    assert cfg.version_poll_interval == 42


# ===========================================================================
# agent/auth.py — require_agent_auth
# ===========================================================================


async def test_require_agent_auth_valid_token(monkeypatch):
    """Supplying the correct token must not raise any exception."""
    import boardfarm_agent.auth

    monkeypatch.setattr(boardfarm_agent.auth.config, "agent_token", "correct-token")

    # Should complete without raising
    await boardfarm_agent.auth.require_agent_auth(x_agent_token="correct-token")


async def test_require_agent_auth_wrong_token_raises_401(monkeypatch):
    """Supplying a wrong token must raise HTTPException with status 401."""
    import boardfarm_agent.auth

    monkeypatch.setattr(boardfarm_agent.auth.config, "agent_token", "correct-token")

    with pytest.raises(HTTPException) as exc_info:
        await boardfarm_agent.auth.require_agent_auth(x_agent_token="wrong-token")

    assert exc_info.value.status_code == 401


async def test_require_agent_auth_empty_header_raises_401(monkeypatch):
    """Empty x_agent_token header with a non-empty config.agent_token → 401."""
    import boardfarm_agent.auth

    monkeypatch.setattr(boardfarm_agent.auth.config, "agent_token", "non-empty-token")

    with pytest.raises(HTTPException) as exc_info:
        await boardfarm_agent.auth.require_agent_auth(x_agent_token="")

    assert exc_info.value.status_code == 401


async def test_require_agent_auth_empty_config_token_always_passes(monkeypatch):
    """When config.agent_token is empty, auth must always pass (no validation)."""
    import boardfarm_agent.auth

    monkeypatch.setattr(boardfarm_agent.auth.config, "agent_token", "")

    # Any token (or no token) should be accepted when configured token is empty
    await boardfarm_agent.auth.require_agent_auth(x_agent_token="")
    await boardfarm_agent.auth.require_agent_auth(x_agent_token="anything")


# ===========================================================================
# agent/heartbeat.py — heartbeat_loop
# ===========================================================================


async def test_heartbeat_loop_200_no_reregistration():
    """Server returns 200 → _register is NOT called, loop continues normally."""
    call_count = 0

    async def fake_sleep(seconds):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            raise asyncio.CancelledError()

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)

    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cm.__aexit__ = AsyncMock(return_value=False)

    mock_async_client_cls = MagicMock(return_value=mock_client_cm)

    with patch("boardfarm_agent.heartbeat.asyncio.sleep", side_effect=fake_sleep), \
         patch("boardfarm_agent.heartbeat.httpx.AsyncClient", mock_async_client_cls):
        with pytest.raises(asyncio.CancelledError):
            await asyncio.shield(
                asyncio.ensure_future(
                    _heartbeat_loop_wrapper()
                )
            )


async def _heartbeat_loop_wrapper():
    """Helper — imported here so patch targets are established before use."""
    from boardfarm_agent.heartbeat import heartbeat_loop
    await heartbeat_loop(
        server_url="http://server:8765",
        agent_name="test-agent",
        agent_url="http://agent:8766",
        device_ids=["dev-001"],
        agent_token="tok",
    )


async def test_heartbeat_loop_200_no_reregistration_direct():
    """Server returns 200 → registration endpoint is never called."""
    call_count = 0

    async def fake_sleep(seconds):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            raise asyncio.CancelledError()

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)

    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cm.__aexit__ = AsyncMock(return_value=False)

    from boardfarm_agent.heartbeat import heartbeat_loop

    with patch("boardfarm_agent.heartbeat.asyncio.sleep", side_effect=fake_sleep), \
         patch("boardfarm_agent.heartbeat.httpx.AsyncClient", return_value=mock_client_cm):
        try:
            await heartbeat_loop(
                server_url="http://server:8765",
                agent_name="test-agent",
                agent_url="http://agent:8766",
                device_ids=["dev-001"],
                agent_token="tok",
            )
        except asyncio.CancelledError:
            pass

    # post was called for heartbeat; let's check the URL used
    calls = mock_client.post.call_args_list
    # At least one heartbeat call (on iteration 1 before CancelledError on sleep(2))
    assert len(calls) >= 1
    # All calls should be to the heartbeat URL (no register call)
    for call in calls:
        url = call.args[0] if call.args else call.kwargs.get("url", "")
        assert "/agents/heartbeat" in url, f"Unexpected call to: {url}"


async def test_heartbeat_loop_404_triggers_reregistration():
    """Server returns 404 → the agent re-registers (POST to /agents/register)."""
    call_count = 0

    async def fake_sleep(seconds):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            raise asyncio.CancelledError()

    mock_resp = MagicMock()
    mock_resp.status_code = 404

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)

    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cm.__aexit__ = AsyncMock(return_value=False)

    from boardfarm_agent.heartbeat import heartbeat_loop

    with patch("boardfarm_agent.heartbeat.asyncio.sleep", side_effect=fake_sleep), \
         patch("boardfarm_agent.heartbeat.httpx.AsyncClient", return_value=mock_client_cm):
        try:
            await heartbeat_loop(
                server_url="http://server:8765",
                agent_name="test-agent",
                agent_url="http://agent:8766",
                device_ids=["dev-001"],
                agent_token="tok",
            )
        except asyncio.CancelledError:
            pass

    all_urls = [
        (call.args[0] if call.args else call.kwargs.get("url", ""))
        for call in mock_client.post.call_args_list
    ]
    register_calls = [u for u in all_urls if "/agents/register" in u]
    assert len(register_calls) >= 1, f"Expected register call, got: {all_urls}"


async def test_heartbeat_loop_exception_swallowed():
    """httpx raises an Exception (server unreachable) → swallowed, loop continues."""
    call_count = 0

    async def fake_sleep(seconds):
        nonlocal call_count
        call_count += 1
        if call_count >= 3:
            raise asyncio.CancelledError()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=Exception("connection refused"))

    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cm.__aexit__ = AsyncMock(return_value=False)

    from boardfarm_agent.heartbeat import heartbeat_loop

    with patch("boardfarm_agent.heartbeat.asyncio.sleep", side_effect=fake_sleep), \
         patch("boardfarm_agent.heartbeat.httpx.AsyncClient", return_value=mock_client_cm):
        # Must NOT raise any exception other than CancelledError
        try:
            await heartbeat_loop(
                server_url="http://server:8765",
                agent_name="test-agent",
                agent_url="http://agent:8766",
                device_ids=["dev-001"],
                agent_token="tok",
            )
        except asyncio.CancelledError:
            pass

    # Loop ran more than once (exception was swallowed each iteration)
    assert call_count >= 2


async def test_heartbeat_loop_cancelled_error_exits_cleanly():
    """asyncio.CancelledError propagates out of the loop cleanly."""
    async def fake_sleep(seconds):
        raise asyncio.CancelledError()

    mock_client = AsyncMock()
    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cm.__aexit__ = AsyncMock(return_value=False)

    from boardfarm_agent.heartbeat import heartbeat_loop

    with patch("boardfarm_agent.heartbeat.asyncio.sleep", side_effect=fake_sleep), \
         patch("boardfarm_agent.heartbeat.httpx.AsyncClient", return_value=mock_client_cm):
        with pytest.raises(asyncio.CancelledError):
            await heartbeat_loop(
                server_url="http://server:8765",
                agent_name="test-agent",
                agent_url="http://agent:8766",
                device_ids=["dev-001"],
                agent_token="tok",
            )


async def test_heartbeat_loop_reregister_failure_is_swallowed():
    """If _register() itself raises (server unreachable during re-register), it is swallowed."""
    call_count = 0

    async def fake_sleep(seconds):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            raise asyncio.CancelledError()

    async def post_side_effect(url, **kwargs):
        if "/agents/heartbeat" in url:
            resp = MagicMock()
            resp.status_code = 404
            return resp
        # Register URL → raise to trigger except Exception in _register()
        raise Exception("server down during re-register")

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=post_side_effect)

    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cm.__aexit__ = AsyncMock(return_value=False)

    from boardfarm_agent.heartbeat import heartbeat_loop

    with patch("boardfarm_agent.heartbeat.asyncio.sleep", side_effect=fake_sleep), \
         patch("boardfarm_agent.heartbeat.httpx.AsyncClient", return_value=mock_client_cm):
        try:
            await heartbeat_loop(
                server_url="http://server:8765",
                agent_name="test-agent",
                agent_url="http://agent:8766",
                device_ids=["dev-001"],
                agent_token="tok",
            )
        except asyncio.CancelledError:
            pass  # expected exit

    assert call_count >= 1  # loop did run
