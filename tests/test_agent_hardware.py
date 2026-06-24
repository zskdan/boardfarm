"""
Tests for agent hardware router (agent/routers/hardware.py) and
agent device router (agent/routers/devices.py).

Uses a minimal FastAPI test app so we don't have to start the full
agent lifespan (mDNS, server registration, etc.).
"""
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from boardfarm_agent.config import DeviceConfig


# ---------------------------------------------------------------------------
# Minimal test app — mounts the routers with auth disabled
# ---------------------------------------------------------------------------

def _make_test_app(devices: list[DeviceConfig], agent_token: str = "") -> FastAPI:
    """Create a minimal FastAPI app with hardware + devices routers, patching config."""
    from boardfarm_agent.routers import hardware, devices as dev_router

    app = FastAPI()

    # Patch config used by both routers and auth
    with patch.multiple(
        "boardfarm_agent.routers.hardware.config",
        devices=devices,
        agent_token=agent_token,
    ):
        pass  # we do patching at request time below

    app.include_router(hardware.router)
    app.include_router(dev_router.router)
    return app


TOKEN = "test-agent-token"
AUTH = {"X-Agent-Token": TOKEN}


@pytest.fixture
def test_device(tmp_path) -> DeviceConfig:
    script = tmp_path / "redeploy.sh"
    script.write_text("#!/bin/sh\necho done\n")
    script.chmod(0o755)
    return DeviceConfig(
        id="test-dev-id",
        jtag_port=3121,
        power_script=str(tmp_path / "power.sh"),
        access_control_script="",
        redeployment_script=str(script),
    )


@pytest.fixture
async def ac(test_device):
    """AsyncClient wired to the agent test app."""
    from boardfarm_agent.routers import hardware as hw_mod, devices as dev_mod
    import boardfarm_agent.auth as auth_mod

    app = FastAPI()
    app.include_router(hw_mod.router)
    app.include_router(dev_mod.router)

    with patch.object(hw_mod, "config") as mock_cfg, \
         patch.object(dev_mod, "config") as mock_dev_cfg, \
         patch.object(auth_mod, "config") as mock_auth_cfg:

        mock_cfg.devices = [test_device]
        mock_dev_cfg.devices = [test_device]
        mock_auth_cfg.agent_token = TOKEN

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


# ===========================================================================
# agent/routers/devices.py — list devices
# ===========================================================================

async def test_list_devices_returns_device_info(ac, test_device):
    with patch("boardfarm_agent.services.health.get_health", return_value=True):
        r = await ac.get("/devices")
    assert r.status_code == 200
    data = r.json()
    assert any(d["id"] == test_device.id for d in data)
    assert data[0]["jtag_port"] == 3121


# ===========================================================================
# agent/routers/hardware.py — _get_device
# ===========================================================================

async def test_start_services_unknown_device_returns_404(ac):
    r = await ac.post("/devices/no-such-device/services/start", headers=AUTH)
    assert r.status_code == 404


async def test_stop_services_unknown_device_returns_404(ac):
    r = await ac.post("/devices/no-such-device/services/stop", headers=AUTH)
    assert r.status_code == 404


# ===========================================================================
# services/start  — POST /devices/{id}/services/start
# ===========================================================================

async def test_start_services_calls_hw_server_and_access_control(ac, test_device):
    with patch("boardfarm_agent.services.hw_server.start", new_callable=AsyncMock, return_value=True) as hw_mock:
        with patch("boardfarm_agent.services.access_control.run", new_callable=AsyncMock) as ac_mock:
            r = await ac.post(f"/devices/{test_device.id}/services/start", headers=AUTH)

    assert r.status_code == 200
    assert r.json()["jtag_started"] is True
    hw_mock.assert_called_once_with(test_device.id, test_device.jtag_port)
    ac_mock.assert_called_once_with(test_device.access_control_script, "unlock")


# ===========================================================================
# services/stop  — POST /devices/{id}/services/stop
# ===========================================================================

async def test_stop_services_calls_hw_server_and_access_control(ac, test_device):
    with patch("boardfarm_agent.services.hw_server.stop", new_callable=AsyncMock) as hw_mock:
        with patch("boardfarm_agent.services.access_control.run", new_callable=AsyncMock) as ac_mock:
            r = await ac.post(f"/devices/{test_device.id}/services/stop", headers=AUTH)

    assert r.status_code == 200
    assert r.json()["stopped"] is True
    hw_mock.assert_called_once_with(test_device.id)
    ac_mock.assert_called_once_with(test_device.access_control_script, "lock")


# ===========================================================================
# Auth — invalid token rejected
# ===========================================================================

async def test_start_services_invalid_token_returns_401(ac, test_device):
    r = await ac.post(f"/devices/{test_device.id}/services/start",
                      headers={"X-Agent-Token": "wrong-token"})
    assert r.status_code == 401


async def test_start_services_missing_token_returns_401(ac, test_device):
    r = await ac.post(f"/devices/{test_device.id}/services/start")
    assert r.status_code == 401


# ===========================================================================
# power  — POST /devices/{id}/power
# ===========================================================================

async def test_power_action_success(ac, test_device, tmp_path):
    with patch("boardfarm_agent.services.power.run", new_callable=AsyncMock, return_value=True):
        r = await ac.post(
            f"/devices/{test_device.id}/power",
            json={"action": "on"},
            headers=AUTH,
        )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["action"] == "on"


async def test_power_action_failure_returns_500(ac, test_device):
    with patch("boardfarm_agent.services.power.run", new_callable=AsyncMock, return_value=False):
        r = await ac.post(
            f"/devices/{test_device.id}/power",
            json={"action": "off"},
            headers=AUTH,
        )
    assert r.status_code == 500


async def test_power_action_invalid_action_returns_422(ac, test_device):
    r = await ac.post(
        f"/devices/{test_device.id}/power",
        json={"action": "explode"},
        headers=AUTH,
    )
    assert r.status_code == 422


# ===========================================================================
# redeploy-info  — GET /devices/{id}/redeploy-info
# ===========================================================================

async def test_redeploy_info_script_exists(ac, test_device):
    r = await ac.get(f"/devices/{test_device.id}/redeploy-info", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["exists"] is True
    assert data["script_lines"] >= 1


async def test_redeploy_info_no_script_returns_422(ac):
    from boardfarm_agent.routers import hardware as hw_mod, devices as dev_mod
    import boardfarm_agent.auth as auth_mod

    dev_no_script = DeviceConfig(id="no-script-dev", redeployment_script="")
    app = FastAPI()
    app.include_router(hw_mod.router)

    with patch.object(hw_mod, "config") as mock_cfg, \
         patch.object(auth_mod, "config") as mock_auth_cfg:
        mock_cfg.devices = [dev_no_script]
        mock_auth_cfg.agent_token = TOKEN

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get(f"/devices/{dev_no_script.id}/redeploy-info", headers=AUTH)

    assert r.status_code == 422


async def test_redeploy_info_script_missing_from_disk(ac):
    from boardfarm_agent.routers import hardware as hw_mod, devices as dev_mod
    import boardfarm_agent.auth as auth_mod

    dev = DeviceConfig(id="missing-script-dev", redeployment_script="/nonexistent/script.sh")
    app = FastAPI()
    app.include_router(hw_mod.router)

    with patch.object(hw_mod, "config") as mock_cfg, \
         patch.object(auth_mod, "config") as mock_auth_cfg:
        mock_cfg.devices = [dev]
        mock_auth_cfg.agent_token = TOKEN

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get(f"/devices/{dev.id}/redeploy-info", headers=AUTH)

    assert r.status_code == 200
    assert r.json()["exists"] is False


# ===========================================================================
# redeploy  — POST /devices/{id}/redeploy
# ===========================================================================

async def test_redeploy_success(ac, test_device):
    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"done\n", b""))

    with patch("boardfarm_agent.routers.hardware.asyncio.create_subprocess_exec", return_value=mock_proc):
        r = await ac.post(f"/devices/{test_device.id}/redeploy", headers=AUTH)

    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert "done" in data["stdout"]


async def test_redeploy_script_failure(ac, test_device):
    mock_proc = AsyncMock()
    mock_proc.returncode = 1
    mock_proc.communicate = AsyncMock(return_value=(b"", b"error!"))

    with patch("boardfarm_agent.routers.hardware.asyncio.create_subprocess_exec", return_value=mock_proc):
        r = await ac.post(f"/devices/{test_device.id}/redeploy", headers=AUTH)

    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert "error!" in r.json()["stderr"]


async def test_redeploy_timeout_returns_504(ac, test_device):
    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)

    with patch("boardfarm_agent.routers.hardware.asyncio.create_subprocess_exec", return_value=mock_proc):
        with patch("boardfarm_agent.routers.hardware.asyncio.wait_for", side_effect=asyncio.TimeoutError):
            r = await ac.post(f"/devices/{test_device.id}/redeploy", headers=AUTH)

    assert r.status_code == 504


async def test_redeploy_no_script_returns_422(ac):
    from boardfarm_agent.routers import hardware as hw_mod
    import boardfarm_agent.auth as auth_mod

    dev = DeviceConfig(id="no-script-dev-2", redeployment_script="")
    app = FastAPI()
    app.include_router(hw_mod.router)

    with patch.object(hw_mod, "config") as mock_cfg, \
         patch.object(auth_mod, "config") as mock_auth_cfg:
        mock_cfg.devices = [dev]
        mock_auth_cfg.agent_token = TOKEN

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post(f"/devices/{dev.id}/redeploy", headers=AUTH)

    assert r.status_code == 422


async def test_redeploy_generic_exception_returns_500(ac, test_device):
    """Unexpected exception from subprocess returns 500."""
    with patch("boardfarm_agent.routers.hardware.asyncio.create_subprocess_exec",
               side_effect=OSError("permission denied")):
        r = await ac.post(f"/devices/{test_device.id}/redeploy", headers=AUTH)
    assert r.status_code == 500


async def test_redeploy_script_missing_from_disk_returns_422(ac):
    from boardfarm_agent.routers import hardware as hw_mod
    import boardfarm_agent.auth as auth_mod

    dev = DeviceConfig(id="missing-script-dev-2", redeployment_script="/nonexistent/deploy.sh")
    app = FastAPI()
    app.include_router(hw_mod.router)

    with patch.object(hw_mod, "config") as mock_cfg, \
         patch.object(auth_mod, "config") as mock_auth_cfg:
        mock_cfg.devices = [dev]
        mock_auth_cfg.agent_token = TOKEN

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post(f"/devices/{dev.id}/redeploy", headers=AUTH)

    assert r.status_code == 422
