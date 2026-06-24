"""
Tests for agent/main.py and agent/services/mdns.py.

agent/main.py:
  - _register_with_server: success, server unreachable
  - _fetch_version_devices: parses devices with/without version_script, server error
  - _recover_active_bookings: starts hw_server for matching devices, server error
  - list_local_agents endpoint: returns self + discovered peers

agent/services/mdns.py:
  - _fetch_service_info: success path, no addresses, exception
  - _on_service_state_change: Added (schedules fetch), Removed (drops from _discovered)
  - start: mocked AsyncZeroconf
  - stop: with and without prior start
  - get_discovered: returns list copy
"""
import asyncio
import socket
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport


# ===========================================================================
# agent/main.py — helper functions
# ===========================================================================


async def test_register_with_server_success():
    """_register_with_server posts name/url/device_ids/token to the server."""
    from boardfarm_agent.main import _register_with_server

    mc = AsyncMock()
    mc.__aenter__ = AsyncMock(return_value=mc)
    mc.__aexit__ = AsyncMock(return_value=False)
    mc.post = AsyncMock(return_value=MagicMock(status_code=200))

    with patch("boardfarm_agent.main.httpx.AsyncClient", return_value=mc):
        await _register_with_server()  # must not raise

    mc.post.assert_called_once()
    call_kwargs = mc.post.call_args
    body = call_kwargs[1].get("json", call_kwargs[0][1] if len(call_kwargs[0]) > 1 else {})
    assert "name" in body
    assert "url" in body


async def test_register_with_server_exception_is_swallowed():
    """If the server is unreachable, exception is logged and swallowed."""
    from boardfarm_agent.main import _register_with_server

    mc = AsyncMock()
    mc.__aenter__ = AsyncMock(return_value=mc)
    mc.__aexit__ = AsyncMock(return_value=False)
    mc.post = AsyncMock(side_effect=Exception("connection refused"))

    with patch("boardfarm_agent.main.httpx.AsyncClient", return_value=mc):
        await _register_with_server()  # must not raise


async def test_fetch_version_devices_filters_by_version_script():
    """Only devices with version_script set are returned."""
    from boardfarm_agent.main import _fetch_version_devices

    server_devices = [
        {"id": "d1", "version_script": "/scripts/get-version.sh",
         "version_ref_file": "/ref.txt", "version_poll_interval": 60},
        {"id": "d2", "version_script": ""},  # no script → excluded
        {"id": "d3"},                          # no version_script key → excluded
    ]

    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = server_devices

    mc = AsyncMock()
    mc.__aenter__ = AsyncMock(return_value=mc)
    mc.__aexit__ = AsyncMock(return_value=False)
    mc.get = AsyncMock(return_value=resp)

    with patch("boardfarm_agent.main.httpx.AsyncClient", return_value=mc):
        result = await _fetch_version_devices()

    assert len(result) == 1
    assert result[0].id == "d1"
    assert result[0].version_script == "/scripts/get-version.sh"
    assert result[0].version_ref_file == "/ref.txt"
    assert result[0].version_poll_interval == 60


async def test_fetch_version_devices_server_error_returns_empty():
    """Non-200 response → returns empty list."""
    from boardfarm_agent.main import _fetch_version_devices

    resp = MagicMock()
    resp.status_code = 500

    mc = AsyncMock()
    mc.__aenter__ = AsyncMock(return_value=mc)
    mc.__aexit__ = AsyncMock(return_value=False)
    mc.get = AsyncMock(return_value=resp)

    with patch("boardfarm_agent.main.httpx.AsyncClient", return_value=mc):
        result = await _fetch_version_devices()

    assert result == []


async def test_fetch_version_devices_exception_returns_empty():
    """Exception from httpx → returns empty list."""
    from boardfarm_agent.main import _fetch_version_devices

    mc = AsyncMock()
    mc.__aenter__ = AsyncMock(return_value=mc)
    mc.__aexit__ = AsyncMock(return_value=False)
    mc.get = AsyncMock(side_effect=Exception("network error"))

    with patch("boardfarm_agent.main.httpx.AsyncClient", return_value=mc):
        result = await _fetch_version_devices()

    assert result == []


async def test_recover_active_bookings_starts_hw_server_for_matching_device():
    """Active booking for a device we own → hw_server.start is called."""
    from boardfarm_agent.config import DeviceConfig
    from boardfarm_agent.main import _recover_active_bookings

    our_device = DeviceConfig(id="dev-owned", jtag_port=3121)

    bookings = [
        {"id": "bk-1", "device_id": "dev-owned"},
        {"id": "bk-2", "device_id": "dev-other"},  # not ours
    ]

    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = bookings

    mc = AsyncMock()
    mc.__aenter__ = AsyncMock(return_value=mc)
    mc.__aexit__ = AsyncMock(return_value=False)
    mc.get = AsyncMock(return_value=resp)

    hw_start_calls = []

    async def fake_hw_start(device_id, jtag_port):
        hw_start_calls.append((device_id, jtag_port))
        return True

    with patch("boardfarm_agent.main.httpx.AsyncClient", return_value=mc):
        with patch("boardfarm_agent.main.config") as mock_cfg:
            mock_cfg.devices = [our_device]
            mock_cfg.server_url = "http://server:8765"
            mock_cfg.server_token = "tok"
            with patch("boardfarm_agent.main.hw_server.start", side_effect=fake_hw_start):
                await _recover_active_bookings()

    assert ("dev-owned", 3121) in hw_start_calls
    assert all(d != "dev-other" for d, _ in hw_start_calls)


async def test_recover_active_bookings_server_error_swallowed():
    """Non-200 from server → swallowed, no hw_server calls."""
    from boardfarm_agent.main import _recover_active_bookings

    resp = MagicMock()
    resp.status_code = 500

    mc = AsyncMock()
    mc.__aenter__ = AsyncMock(return_value=mc)
    mc.__aexit__ = AsyncMock(return_value=False)
    mc.get = AsyncMock(return_value=resp)

    with patch("boardfarm_agent.main.httpx.AsyncClient", return_value=mc):
        with patch("boardfarm_agent.main.config") as mock_cfg:
            mock_cfg.server_url = "http://server:8765"
            mock_cfg.server_token = "tok"
            mock_cfg.devices = []
            await _recover_active_bookings()  # must not raise


async def test_recover_active_bookings_exception_swallowed():
    """httpx exception → swallowed."""
    from boardfarm_agent.main import _recover_active_bookings

    mc = AsyncMock()
    mc.__aenter__ = AsyncMock(return_value=mc)
    mc.__aexit__ = AsyncMock(return_value=False)
    mc.get = AsyncMock(side_effect=Exception("connection refused"))

    with patch("boardfarm_agent.main.httpx.AsyncClient", return_value=mc):
        with patch("boardfarm_agent.main.config") as mock_cfg:
            mock_cfg.server_url = "http://server:8765"
            mock_cfg.server_token = "tok"
            mock_cfg.devices = []
            await _recover_active_bookings()  # must not raise


# ===========================================================================
# agent/main.py — GET /agents endpoint
# ===========================================================================


async def test_list_local_agents_includes_self():
    """GET /agents returns the self entry."""
    from boardfarm_agent.main import app as agent_app

    with patch("boardfarm_agent.main.config") as mock_cfg, \
         patch("boardfarm_agent.main.mdns.get_discovered", return_value=[]):
        mock_cfg.name = "my-agent"
        mock_cfg.host_ip = "10.0.0.1"
        mock_cfg.port = 8766
        mock_cfg.devices = []

        transport = ASGITransport(app=agent_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/agents")

    assert r.status_code == 200
    data = r.json()
    self_entries = [e for e in data if e.get("self") is True]
    assert len(self_entries) == 1
    assert self_entries[0]["name"] == "my-agent"


async def test_list_local_agents_includes_peers():
    """GET /agents includes mDNS-discovered peers with self=False."""
    from boardfarm_agent.main import app as agent_app

    peer = {"name": "peer-agent", "url": "http://10.0.0.2:8766",
            "properties": {"devices": "2"}, "self": False}

    with patch("boardfarm_agent.main.config") as mock_cfg, \
         patch("boardfarm_agent.main.mdns.get_discovered", return_value=[peer]):
        mock_cfg.name = "my-agent"
        mock_cfg.host_ip = "10.0.0.1"
        mock_cfg.port = 8766
        mock_cfg.devices = []

        transport = ASGITransport(app=agent_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/agents")

    data = r.json()
    peer_entries = [e for e in data if e.get("self") is False]
    assert len(peer_entries) == 1
    assert peer_entries[0]["name"] == "peer-agent"
    assert peer_entries[0]["device_count"] == 2


async def test_health_endpoint():
    """GET /health returns ok status."""
    from boardfarm_agent.main import app as agent_app

    with patch("boardfarm_agent.main.config") as mock_cfg:
        mock_cfg.name = "my-agent"
        mock_cfg.devices = []

        transport = ASGITransport(app=agent_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/health")

    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ===========================================================================
# agent/services/mdns.py
# ===========================================================================


def _reset_mdns():
    import boardfarm_agent.services.mdns as m
    m._zeroconf = None
    m._registered_info = None
    m._discovered.clear()


async def test_fetch_service_info_populates_discovered():
    """_fetch_service_info stores agent info in _discovered on success."""
    _reset_mdns()
    import boardfarm_agent.services.mdns as m

    mock_info = MagicMock()
    mock_info.addresses = [socket.inet_aton("10.0.0.5")]
    mock_info.port = 8766
    mock_info.properties = {b"version": b"0.1.0", b"devices": b"3"}
    mock_info.request = MagicMock(return_value=True)

    mock_zc = MagicMock()

    with patch("boardfarm_agent.services.mdns.ServiceInfo", return_value=mock_info):
        await m._fetch_service_info(mock_zc, m.SERVICE_TYPE, f"peer-agent.{m.SERVICE_TYPE}")

    assert len(m._discovered) == 1
    entry = list(m._discovered.values())[0]
    assert entry["url"] == "http://10.0.0.5:8766"
    assert entry["properties"]["version"] == "0.1.0"


async def test_fetch_service_info_no_addresses_skips():
    """If ServiceInfo has no addresses, nothing is added to _discovered."""
    _reset_mdns()
    import boardfarm_agent.services.mdns as m

    mock_info = MagicMock()
    mock_info.addresses = []
    mock_info.request = MagicMock(return_value=False)

    mock_zc = MagicMock()

    with patch("boardfarm_agent.services.mdns.ServiceInfo", return_value=mock_info):
        await m._fetch_service_info(mock_zc, m.SERVICE_TYPE, f"peer.{m.SERVICE_TYPE}")

    assert len(m._discovered) == 0


async def test_fetch_service_info_exception_is_swallowed():
    """Exceptions from info.request are swallowed and nothing is added."""
    _reset_mdns()
    import boardfarm_agent.services.mdns as m

    mock_info = MagicMock()
    mock_info.request = MagicMock(side_effect=Exception("lookup failed"))

    mock_zc = MagicMock()

    with patch("boardfarm_agent.services.mdns.ServiceInfo", return_value=mock_info):
        await m._fetch_service_info(mock_zc, m.SERVICE_TYPE, f"peer.{m.SERVICE_TYPE}")

    assert len(m._discovered) == 0


def test_on_service_state_change_removed_clears_discovered():
    """Removed state removes the entry from _discovered."""
    _reset_mdns()
    import boardfarm_agent.services.mdns as m
    from zeroconf import ServiceStateChange

    name = f"old-agent.{m.SERVICE_TYPE}"
    m._discovered[name] = {"name": "old-agent", "url": "http://10.0.0.9:8766"}

    mock_zc = MagicMock()
    m._on_service_state_change(mock_zc, m.SERVICE_TYPE, name, ServiceStateChange.Removed)

    assert name not in m._discovered


def test_on_service_state_change_added_schedules_fetch():
    """Added state schedules _fetch_service_info via ensure_future."""
    _reset_mdns()
    import boardfarm_agent.services.mdns as m
    from zeroconf import ServiceStateChange

    with patch("boardfarm_agent.services.mdns.asyncio.ensure_future") as mock_ef:
        mock_zc = MagicMock()
        m._on_service_state_change(
            mock_zc, m.SERVICE_TYPE, f"new-agent.{m.SERVICE_TYPE}", ServiceStateChange.Added
        )
    mock_ef.assert_called_once()


def test_get_discovered_returns_list():
    """get_discovered returns a list copy of the discovered agents."""
    _reset_mdns()
    import boardfarm_agent.services.mdns as m

    m._discovered["key1"] = {"name": "agent1", "url": "http://10.0.0.1:8766"}
    m._discovered["key2"] = {"name": "agent2", "url": "http://10.0.0.2:8766"}

    result = m.get_discovered()

    assert isinstance(result, list)
    assert len(result) == 2
    names = {e["name"] for e in result}
    assert names == {"agent1", "agent2"}


async def test_mdns_stop_when_not_started_is_noop():
    """stop() when nothing was started must not raise."""
    _reset_mdns()
    import boardfarm_agent.services.mdns as m

    await m.stop()  # must not raise


async def test_mdns_start_and_stop():
    """start() registers with mDNS; stop() unregisters cleanly."""
    _reset_mdns()
    import boardfarm_agent.services.mdns as m

    mock_azc = AsyncMock()
    mock_azc.async_register_service = AsyncMock()
    mock_azc.async_unregister_service = AsyncMock()
    mock_azc.async_close = AsyncMock()
    mock_azc.zeroconf = MagicMock()

    mock_service_info = MagicMock()

    with patch("boardfarm_agent.services.mdns.AsyncZeroconf", return_value=mock_azc), \
         patch("boardfarm_agent.services.mdns.ServiceInfo", return_value=mock_service_info), \
         patch("boardfarm_agent.services.mdns.AsyncServiceBrowser"):
        await m.start("test-agent", "10.0.0.1", 8766, 2)

    assert m._zeroconf is mock_azc

    with patch("boardfarm_agent.services.mdns.AsyncZeroconf", return_value=mock_azc):
        await m.stop()

    assert m._zeroconf is None
    mock_azc.async_unregister_service.assert_called_once()
    mock_azc.async_close.assert_called_once()


async def test_mdns_start_browser_exception_swallowed():
    """If AsyncServiceBrowser raises, it is swallowed and start still returns."""
    _reset_mdns()
    import boardfarm_agent.services.mdns as m

    mock_azc = AsyncMock()
    mock_azc.async_register_service = AsyncMock()
    mock_azc.zeroconf = MagicMock()

    with patch("boardfarm_agent.services.mdns.AsyncZeroconf", return_value=mock_azc), \
         patch("boardfarm_agent.services.mdns.ServiceInfo", return_value=MagicMock()), \
         patch("boardfarm_agent.services.mdns.AsyncServiceBrowser", side_effect=Exception("no network")):
        await m.start("test-agent", "10.0.0.1", 8766, 1)  # must not raise

    assert m._zeroconf is mock_azc
    await m.stop()


async def test_mdns_stop_unregister_exception_swallowed():
    """If async_unregister_service raises, it is swallowed and close is still called."""
    _reset_mdns()
    import boardfarm_agent.services.mdns as m

    mock_azc = AsyncMock()
    mock_azc.async_unregister_service = AsyncMock(side_effect=Exception("unregister failed"))
    mock_azc.async_close = AsyncMock()
    m._zeroconf = mock_azc
    m._registered_info = MagicMock()

    await m.stop()  # must not raise

    mock_azc.async_close.assert_called_once()
    assert m._zeroconf is None


async def test_agent_lifespan_starts_and_stops_tasks():
    """lifespan starts background tasks and cancels them on shutdown."""
    from boardfarm_agent.main import lifespan, app as agent_app

    started_tasks = []

    async def fake_probe_loop(*a):
        started_tasks.append("health")
        await asyncio.sleep(9999)

    async def fake_heartbeat_loop(*a, **kw):
        started_tasks.append("heartbeat")
        await asyncio.sleep(9999)

    async def fake_version_loop(*a, **kw):
        started_tasks.append("version")
        await asyncio.sleep(9999)

    with patch("boardfarm_agent.main.mdns.start", new_callable=AsyncMock), \
         patch("boardfarm_agent.main.mdns.stop", new_callable=AsyncMock), \
         patch("boardfarm_agent.main._register_with_server", new_callable=AsyncMock), \
         patch("boardfarm_agent.main._recover_active_bookings", new_callable=AsyncMock), \
         patch("boardfarm_agent.main.health_svc.probe_loop", side_effect=fake_probe_loop), \
         patch("boardfarm_agent.main.heartbeat_loop", side_effect=fake_heartbeat_loop), \
         patch("boardfarm_agent.main.version_svc.version_loop", side_effect=fake_version_loop), \
         patch("boardfarm_agent.main.hw_server.stop_all", new_callable=AsyncMock), \
         patch("boardfarm_agent.main.config") as mock_cfg:

        mock_cfg.name = "test-agent"
        mock_cfg.host_ip = "10.0.0.1"
        mock_cfg.port = 8766
        mock_cfg.server_url = "http://server:8765"
        mock_cfg.server_token = "tok"
        mock_cfg.agent_token = "agent-tok"
        mock_cfg.version_poll_interval = 300
        mock_cfg.devices = []

        async with lifespan(agent_app):
            await asyncio.sleep(0)  # yield so tasks can start

    assert "health" in started_tasks
    assert "heartbeat" in started_tasks
    assert "version" in started_tasks
