"""
Tests for agent ↔ server communication:
  - Registration (create, upsert, device linking, auto-claim, token storage)
  - Heartbeat
  - Version push (PATCH /devices/{id}/version)
  - Redeploy proxy (GET /redeploy-info, POST /redeploy)
  - Agent token forwarding — FK path and IP-fallback path
  - Agent online/offline status reflected on devices
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

HEADERS = {"X-Token": "test-token", "X-User": "tester"}
AGENT_TOKEN = "agent-secret-123"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _register(client, *, name="agt", url="http://10.0.0.1:8080", device_ids=(), token=AGENT_TOKEN):
    r = await client.post("/agents/register", json={
        "name": name, "url": url, "device_ids": list(device_ids), "token": token,
    }, headers={"X-Token": "test-token"})
    assert r.status_code == 200, r.text
    return r.json()


async def _device(client, *, name="dev", host_ip="10.0.0.1", redeployment_script=""):
    r = await client.post("/devices", json={
        "name": name, "device_id": f"id-{name}", "host_ip": host_ip,
        "redeployment_script": redeployment_script,
    }, headers=HEADERS)
    assert r.status_code == 201, r.text
    return r.json()


def _mock_agent_http(json_body, *, status=200):
    """Fake httpx.AsyncClient context manager returning a canned response."""
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_body
    resp.text = str(json_body)

    mc = AsyncMock()
    mc.__aenter__ = AsyncMock(return_value=mc)
    mc.__aexit__ = AsyncMock(return_value=False)
    mc.get = AsyncMock(return_value=resp)
    mc.post = AsyncMock(return_value=resp)
    return mc


# ─────────────────────────────────────────────────────────────────────────────
# Registration
# ─────────────────────────────────────────────────────────────────────────────

async def test_register_creates_agent(client):
    data = await _register(client, name="agt-1", url="http://10.1.1.1:8080")
    assert data["name"] == "agt-1"
    assert data["url"] == "http://10.1.1.1:8080"


async def test_register_upserts_on_same_name(client):
    """Re-registration with the same name updates the record instead of creating a duplicate."""
    await _register(client, name="agt", url="http://10.0.0.1:8080", token="old")
    await _register(client, name="agt", url="http://10.0.0.2:9090", token="new")

    agents = (await client.get("/agents")).json()
    named = [a for a in agents if a["name"] == "agt"]
    assert len(named) == 1
    assert named[0]["url"] == "http://10.0.0.2:9090"


async def test_register_links_device_by_id(client):
    """Devices listed in device_ids get their agent_id FK set."""
    dev = await _device(client, name="d1", host_ip="10.1.1.10")
    assert dev["agent_id"] is None

    await _register(client, name="agt", url="http://10.1.1.10:8080", device_ids=[dev["id"]])

    r = await client.get(f"/devices/{dev['id']}", headers=HEADERS)
    assert r.json()["agent_id"] is not None


async def test_register_autoclaims_unlinked_device_by_host_ip(client):
    """Existing device whose host_ip matches the registering agent is auto-claimed."""
    dev = await _device(client, name="d2", host_ip="10.2.2.20")
    assert dev["agent_id"] is None

    await _register(client, name="agt", url="http://10.2.2.20:8080", device_ids=[])

    r = await client.get(f"/devices/{dev['id']}", headers=HEADERS)
    assert r.json()["agent_id"] is not None


async def test_register_stores_agent_token(client):
    """The token is persisted and used for subsequent proxy calls (tested via redeploy)."""
    dev = await _device(client, name="d3", host_ip="10.3.3.30", redeployment_script="/s.sh")
    await _register(client, name="agt", url="http://10.3.3.30:8080",
                    device_ids=[dev["id"]], token="stored-tok")

    mc = _mock_agent_http({"exists": True, "script_lines": 5})
    with patch("server.routers.devices.httpx.AsyncClient", return_value=mc):
        r = await client.get(f"/devices/{dev['id']}/redeploy-info", headers=HEADERS)
    assert r.status_code == 200
    sent = mc.get.call_args.kwargs.get("headers", {})
    assert sent.get("X-Agent-Token") == "stored-tok"


# ─────────────────────────────────────────────────────────────────────────────
# Heartbeat
# ─────────────────────────────────────────────────────────────────────────────

async def test_heartbeat_known_agent_returns_ok(client):
    await _register(client, name="agt-hb")
    r = await client.post("/agents/heartbeat", json={"name": "agt-hb"})
    assert r.status_code == 200
    assert r.json()["ok"] is True


async def test_heartbeat_unknown_agent_returns_404(client):
    """Unknown agent gets 404 so it knows to re-register."""
    r = await client.post("/agents/heartbeat", json={"name": "nobody"})
    assert r.status_code == 404


async def test_heartbeat_updates_last_seen(client, db_session):
    """Each heartbeat bumps last_seen, keeping the agent online."""
    from sqlalchemy import select as sa_select
    from server.models import Agent as AgentModel

    await _register(client, name="agt-ts")
    r = await client.post("/agents/heartbeat", json={"name": "agt-ts"})
    assert r.status_code == 200

    res = await db_session.execute(sa_select(AgentModel).where(AgentModel.name == "agt-ts"))
    ag = res.scalar_one()
    age = (datetime.now(timezone.utc).replace(tzinfo=None) - ag.last_seen).total_seconds()
    assert age < 5  # freshly bumped


# ─────────────────────────────────────────────────────────────────────────────
# Agent online/offline status on devices
# ─────────────────────────────────────────────────────────────────────────────

async def test_device_shows_agent_online_after_registration(client):
    dev = await _device(client, name="d-online", host_ip="10.10.10.1")
    await _register(client, name="agt-on", url="http://10.10.10.1:8080", device_ids=[dev["id"]])

    r = await client.get(f"/devices/{dev['id']}", headers=HEADERS)
    assert r.json()["agent_online"] is True


async def test_device_shows_agent_offline_when_last_seen_stale(client, db_session):
    """If an agent's last_seen is > 90 s old, the device reports agent_online=False."""
    from sqlalchemy import update as sa_update
    from server.models import Agent as AgentModel

    dev = await _device(client, name="d-stale", host_ip="10.10.10.2")
    agent_data = await _register(client, name="agt-stale", url="http://10.10.10.2:8080",
                                 device_ids=[dev["id"]])

    stale = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=200)
    await db_session.execute(
        sa_update(AgentModel)
        .where(AgentModel.id == agent_data["id"])
        .values(last_seen=stale)
    )
    await db_session.commit()

    r = await client.get(f"/devices/{dev['id']}", headers=HEADERS)
    assert r.json()["agent_online"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Version push  (PATCH /devices/{id}/version)
# ─────────────────────────────────────────────────────────────────────────────

async def test_version_push_updates_deployed_version(client):
    dev = await _device(client, name="dv1")
    r = await client.patch(
        f"/devices/{dev['id']}/version",
        json={"version": "abc12345:clean:ref99"},
        headers={"X-Token": "test-token"},
    )
    assert r.status_code == 204

    detail = (await client.get(f"/devices/{dev['id']}", headers=HEADERS)).json()
    assert detail["deployed_version"] == "abc12345:clean:ref99"


async def test_version_push_requires_token(client):
    dev = await _device(client, name="dv2")
    r = await client.patch(f"/devices/{dev['id']}/version", json={"version": "v1"})
    assert r.status_code == 401


async def test_version_push_truncates_long_output(client):
    dev = await _device(client, name="dv3")
    await client.patch(
        f"/devices/{dev['id']}/version",
        json={"version": "x" * 20_000},
        headers={"X-Token": "test-token"},
    )
    detail = (await client.get(f"/devices/{dev['id']}", headers=HEADERS)).json()
    assert len(detail["deployed_version"]) == 16384


async def test_version_push_unknown_device_returns_404(client):
    r = await client.patch(
        f"/devices/{uuid.uuid4()}/version",
        json={"version": "v1"},
        headers={"X-Token": "test-token"},
    )
    assert r.status_code == 404


async def test_version_push_strips_surrounding_whitespace(client):
    dev = await _device(client, name="dv4")
    await client.patch(
        f"/devices/{dev['id']}/version",
        json={"version": "  v1.0\n"},
        headers={"X-Token": "test-token"},
    )
    detail = (await client.get(f"/devices/{dev['id']}", headers=HEADERS)).json()
    assert detail["deployed_version"] == "v1.0"


# ─────────────────────────────────────────────────────────────────────────────
# Agent token forwarding in proxy calls
# ─────────────────────────────────────────────────────────────────────────────

async def test_redeploy_info_forwards_token_via_fk_link(client):
    """FK-linked agent: correct token forwarded in X-Agent-Token."""
    dev = await _device(client, name="dp1", host_ip="10.20.1.1",
                        redeployment_script="/opt/redeploy.sh")
    await _register(client, name="agt-fk", url="http://10.20.1.1:8080",
                    device_ids=[dev["id"]], token="fk-tok")

    mc = _mock_agent_http({"exists": True, "script_lines": 5})
    with patch("server.routers.devices.httpx.AsyncClient", return_value=mc):
        r = await client.get(f"/devices/{dev['id']}/redeploy-info", headers=HEADERS)

    assert r.status_code == 200
    sent = mc.get.call_args.kwargs.get("headers", {})
    assert sent.get("X-Agent-Token") == "fk-tok"


async def test_redeploy_info_forwards_token_via_ip_fallback(client):
    """IP-fallback path: discovered agent's token must be forwarded, not empty string."""
    # Register agent FIRST (before device exists, so no auto-claim)
    await _register(client, name="agt-ip", url="http://10.20.2.2:8080", token="ip-tok")

    # Create device with matching host_ip AFTER registration — agent_id stays None
    dev = await _device(client, name="dp2", host_ip="10.20.2.2",
                        redeployment_script="/opt/redeploy.sh")
    # Confirm no FK link (auto-claim only runs during registration, not on device create)
    detail = (await client.get(f"/devices/{dev['id']}", headers=HEADERS)).json()
    assert detail["agent_id"] is None, "Test precondition: device must use IP fallback"

    mc = _mock_agent_http({"exists": True, "script_lines": 8})
    with patch("server.routers.devices.httpx.AsyncClient", return_value=mc):
        r = await client.get(f"/devices/{dev['id']}/redeploy-info", headers=HEADERS)

    assert r.status_code == 200
    sent = mc.get.call_args.kwargs.get("headers", {})
    # BUG: currently returns "" because _resolve_agent reads device.agent.agent_token
    # (None) instead of the IP-matched agent's token.
    assert sent.get("X-Agent-Token") == "ip-tok"


async def test_redeploy_forwards_token_and_proxies_result(client):
    """POST /redeploy proxies to agent and returns the agent's response."""
    dev = await _device(client, name="dp3", host_ip="10.20.3.3",
                        redeployment_script="/opt/redeploy.sh")
    await _register(client, name="agt-rd", url="http://10.20.3.3:8080",
                    device_ids=[dev["id"]], token="rd-tok")

    mc = _mock_agent_http({"ok": True, "stdout": "done", "stderr": "", "returncode": 0})
    with patch("server.routers.devices.httpx.AsyncClient", return_value=mc):
        r = await client.post(f"/devices/{dev['id']}/redeploy", headers=HEADERS)

    assert r.status_code == 200
    assert r.json()["ok"] is True
    sent = mc.post.call_args.kwargs.get("headers", {})
    assert sent.get("X-Agent-Token") == "rd-tok"


# ─────────────────────────────────────────────────────────────────────────────
# Error paths
# ─────────────────────────────────────────────────────────────────────────────

async def test_redeploy_info_returns_503_when_no_agent(client):
    dev = await _device(client, name="dp4", host_ip="", redeployment_script="/s.sh")
    r = await client.get(f"/devices/{dev['id']}/redeploy-info", headers=HEADERS)
    assert r.status_code == 503


async def test_redeploy_info_returns_422_when_no_script(client):
    dev = await _device(client, name="dp5", host_ip="10.20.5.5")
    await _register(client, name="agt5", url="http://10.20.5.5:8080", device_ids=[dev["id"]])
    r = await client.get(f"/devices/{dev['id']}/redeploy-info", headers=HEADERS)
    assert r.status_code == 422


async def test_redeploy_returns_502_when_agent_unreachable(client):
    dev = await _device(client, name="dp6", host_ip="10.20.6.6",
                        redeployment_script="/s.sh")
    await _register(client, name="agt6", url="http://10.20.6.6:8080", device_ids=[dev["id"]])

    mc = AsyncMock()
    mc.__aenter__ = AsyncMock(return_value=mc)
    mc.__aexit__ = AsyncMock(return_value=False)
    mc.post = AsyncMock(side_effect=httpx.ConnectError("refused"))

    with patch("server.routers.devices.httpx.AsyncClient", return_value=mc):
        r = await client.post(f"/devices/{dev['id']}/redeploy", headers=HEADERS)
    assert r.status_code == 502


async def test_redeploy_returns_502_on_agent_error_response(client):
    """If the agent returns a 4xx/5xx, the server surfaces it as 502."""
    dev = await _device(client, name="dp7", host_ip="10.20.7.7",
                        redeployment_script="/s.sh")
    await _register(client, name="agt7", url="http://10.20.7.7:8080", device_ids=[dev["id"]])

    mc = _mock_agent_http({"detail": "script not found"}, status=500)
    with patch("server.routers.devices.httpx.AsyncClient", return_value=mc):
        r = await client.post(f"/devices/{dev['id']}/redeploy", headers=HEADERS)
    assert r.status_code == 502


async def test_list_agents_returns_all_registered(client):
    await _register(client, name="la-1", url="http://10.30.0.1:8080")
    await _register(client, name="la-2", url="http://10.30.0.2:8080")
    r = await client.get("/agents")
    assert r.status_code == 200
    names = {a["name"] for a in r.json()}
    assert {"la-1", "la-2"} <= names
