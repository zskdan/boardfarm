"""Tests for server/routers/setups.py — targets 100% coverage."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta

import pytest

AUTH_HEADERS = {"X-Token": "test-token", "X-User": "tester"}
OTHER_HEADERS = {"X-Token": "test-token", "X-User": "other-user"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_device(client, *, name: str | None = None, host_ip: str | None = None) -> dict:
    payload = {
        "name": name or f"dev-{uuid.uuid4().hex[:8]}",
        "description": "test",
        "location": "Lab",
        "features": {},
        "jtag_port": 3121,
        "ssh_user": "root",
        "ssh_port": 22,
        "power_script": "",
        "power_args": {},
        "enabled": True,
    }
    if host_ip is not None:
        payload["host_ip"] = host_ip
    resp = await client.post("/devices", json=payload, headers=AUTH_HEADERS)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _create_setup(client, *, name: str | None = None, device_ids: list[str] | None = None) -> dict:
    payload = {
        "name": name or f"setup-{uuid.uuid4().hex[:8]}",
        "description": "a setup",
        "device_ids": device_ids or [],
    }
    resp = await client.post("/setups", json=payload, headers=AUTH_HEADERS)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _create_agent(client, *, name: str | None = None, ip: str = "10.0.0.1") -> dict:
    payload = {
        "name": name or f"agent-{uuid.uuid4().hex[:8]}",
        "url": f"http://{ip}:8080",
        "last_seen": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "agent_token": "tok",
    }
    resp = await client.post("/agents", json=payload, headers=AUTH_HEADERS)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# GET /setups
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_setups_empty(client):
    resp = await client.get("/setups")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_list_setups_with_setup(client):
    device = await _create_device(client)
    setup = await _create_setup(client, device_ids=[device["id"]])
    resp = await client.get("/setups")
    assert resp.status_code == 200
    ids = [s["id"] for s in resp.json()]
    assert setup["id"] in ids


@pytest.mark.asyncio
async def test_list_setups_device_with_active_booking(client):
    """Covers the active_booking_username path in SetupDeviceOut."""
    device = await _create_device(client)
    setup = await _create_setup(client, device_ids=[device["id"]])

    # Book the single device directly so it shows as unavailable in the setup list
    book_resp = await client.post(
        f"/devices/{device['id']}/book",
        json={"duration_hours": 1},
        headers=AUTH_HEADERS,
    )
    assert book_resp.status_code == 201

    resp = await client.get("/setups")
    assert resp.status_code == 200
    matching = [s for s in resp.json() if s["id"] == setup["id"]]
    assert matching
    devices_in_setup = matching[0]["devices"]
    assert devices_in_setup[0]["active_booking_username"] == "tester"
    assert matching[0]["all_available"] is False


@pytest.mark.asyncio
async def test_list_setups_agent_online_via_ip_fallback(client):
    """Covers _device_agent_online IP-fallback path (agent found by IP, not FK)."""
    ip = f"10.{uuid.uuid4().int % 255}.{uuid.uuid4().int % 255}.2"
    # Create agent via /agents/register with a recent last_seen (within 90 s) so online=True
    agent_payload = {
        "name": f"agent-ip-{uuid.uuid4().hex[:6]}",
        "url": f"http://{ip}:8080",
        "token": "tok",
    }
    agent_resp = await client.post("/agents/register", json=agent_payload, headers={"X-Token": "test-token"})
    assert agent_resp.status_code == 200, agent_resp.text

    # Create device with the same host_ip but NO agent FK link (don't pass device_ids
    # to register so the agent doesn't auto-link to this device via FK)
    device = await _create_device(client, host_ip=ip)
    setup = await _create_setup(client, device_ids=[device["id"]])

    resp = await client.get("/setups")
    assert resp.status_code == 200
    matching = [s for s in resp.json() if s["id"] == setup["id"]]
    assert matching
    # agent should be found by IP → agent_online True
    assert matching[0]["devices"][0]["agent_online"] is True


@pytest.mark.asyncio
async def test_list_setups_active_setup_booking_visible(client):
    """active_booking on SetupOut is populated when setup is booked."""
    dev1 = await _create_device(client)
    dev2 = await _create_device(client)
    setup = await _create_setup(client, device_ids=[dev1["id"], dev2["id"]])

    book_resp = await client.post(
        f"/setups/{setup['id']}/book",
        json={"duration_hours": 1},
        headers=AUTH_HEADERS,
    )
    assert book_resp.status_code == 200

    resp = await client.get("/setups")
    assert resp.status_code == 200
    matching = [s for s in resp.json() if s["id"] == setup["id"]]
    assert matching
    ab = matching[0]["active_booking"]
    assert ab is not None
    assert ab["username"] == "tester"
    # Verify the SetupBookingOut datetime serialisers ran (schemas.py lines 199, 203)
    assert ab["start_time"].endswith("Z")
    assert ab["end_time"].endswith("Z")
    # SetupOut.created_at serialiser (schemas.py line 217)
    assert matching[0]["created_at"].endswith("Z")


# ---------------------------------------------------------------------------
# POST /setups
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_setup_with_devices(client):
    device = await _create_device(client)
    resp = await client.post(
        "/setups",
        json={"name": f"s-{uuid.uuid4().hex[:6]}", "description": "desc", "device_ids": [device["id"]]},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"]
    assert len(body["devices"]) == 1


@pytest.mark.asyncio
async def test_create_setup_device_not_found(client):
    resp = await client.post(
        "/setups",
        json={"name": f"s-{uuid.uuid4().hex[:6]}", "device_ids": ["nonexistent-id"]},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_setup_duplicate_name(client):
    name = f"dup-setup-{uuid.uuid4().hex[:6]}"
    await _create_setup(client, name=name)
    resp = await client.post(
        "/setups",
        json={"name": name, "device_ids": []},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /setups/{id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_setup_name(client):
    setup = await _create_setup(client)
    new_name = f"renamed-{uuid.uuid4().hex[:6]}"
    resp = await client.patch(
        f"/setups/{setup['id']}",
        json={"name": new_name},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == new_name


@pytest.mark.asyncio
async def test_update_setup_device_ids(client):
    dev1 = await _create_device(client)
    dev2 = await _create_device(client)
    setup = await _create_setup(client, device_ids=[dev1["id"]])

    # Replace devices
    resp = await client.patch(
        f"/setups/{setup['id']}",
        json={"device_ids": [dev2["id"]]},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200

    # Confirm via GET /setups that dev2 is now the only device
    list_resp = await client.get("/setups")
    matching = [s for s in list_resp.json() if s["id"] == setup["id"]]
    assert matching
    device_ids_in_setup = [d["id"] for d in matching[0]["devices"]]
    assert dev2["id"] in device_ids_in_setup
    assert dev1["id"] not in device_ids_in_setup


@pytest.mark.asyncio
async def test_update_setup_not_found(client):
    resp = await client.patch(
        "/setups/does-not-exist",
        json={"name": "x"},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_setup_duplicate_name(client):
    s1 = await _create_setup(client)
    s2 = await _create_setup(client)
    resp = await client.patch(
        f"/setups/{s2['id']}",
        json={"name": s1["name"]},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_update_setup_device_not_found(client):
    setup = await _create_setup(client)
    resp = await client.patch(
        f"/setups/{setup['id']}",
        json={"device_ids": ["bad-device-id"]},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /setups/{id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_setup_success(client):
    setup = await _create_setup(client)
    resp = await client.delete(f"/setups/{setup['id']}", headers=AUTH_HEADERS)
    assert resp.status_code == 204

    # Confirm gone
    resp2 = await client.get("/setups")
    ids = [s["id"] for s in resp2.json()]
    assert setup["id"] not in ids


@pytest.mark.asyncio
async def test_delete_setup_not_found(client):
    resp = await client.delete("/setups/nonexistent-id", headers=AUTH_HEADERS)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_setup_with_active_booking(client):
    dev1 = await _create_device(client)
    dev2 = await _create_device(client)
    setup = await _create_setup(client, device_ids=[dev1["id"], dev2["id"]])

    # Book the setup first
    book_resp = await client.post(
        f"/setups/{setup['id']}/book",
        json={"duration_hours": 1},
        headers=AUTH_HEADERS,
    )
    assert book_resp.status_code == 200

    # Now try to delete — should be 409
    resp = await client.delete(f"/setups/{setup['id']}", headers=AUTH_HEADERS)
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# POST /setups/{id}/book
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_book_setup_success(client):
    dev1 = await _create_device(client)
    dev2 = await _create_device(client)
    setup = await _create_setup(client, device_ids=[dev1["id"], dev2["id"]])

    resp = await client.post(
        f"/setups/{setup['id']}/book",
        json={"duration_hours": 2, "comment": "CI run"},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200
    bookings = resp.json()
    assert len(bookings) == 2
    assert all(b["active"] for b in bookings)
    assert all(b["username"] == "tester" for b in bookings)
    assert all(b["setup_id"] == setup["id"] for b in bookings)


@pytest.mark.asyncio
async def test_book_setup_device_already_booked(client):
    dev1 = await _create_device(client)
    dev2 = await _create_device(client)
    setup = await _create_setup(client, device_ids=[dev1["id"], dev2["id"]])

    # Directly book one of the devices
    await client.post(
        f"/devices/{dev1['id']}/book",
        json={"duration_hours": 1},
        headers=OTHER_HEADERS,
    )

    resp = await client.post(
        f"/setups/{setup['id']}/book",
        json={"duration_hours": 1},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 409
    assert "unavailable" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_book_setup_no_devices(client):
    setup = await _create_setup(client, device_ids=[])
    resp = await client.post(
        f"/setups/{setup['id']}/book",
        json={"duration_hours": 1},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 400
    assert "no devices" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_book_setup_not_found(client):
    resp = await client.post(
        "/setups/nonexistent-setup/book",
        json={"duration_hours": 1},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /setups/{id}/booking
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_release_setup_booking_success(client):
    dev1 = await _create_device(client)
    dev2 = await _create_device(client)
    setup = await _create_setup(client, device_ids=[dev1["id"], dev2["id"]])

    await client.post(
        f"/setups/{setup['id']}/book",
        json={"duration_hours": 1},
        headers=AUTH_HEADERS,
    )

    resp = await client.delete(f"/setups/{setup['id']}/booking", headers=AUTH_HEADERS)
    assert resp.status_code == 204

    # Verify active_booking is gone
    list_resp = await client.get("/setups")
    matching = [s for s in list_resp.json() if s["id"] == setup["id"]]
    assert matching[0]["active_booking"] is None


@pytest.mark.asyncio
async def test_release_setup_booking_no_active_booking(client):
    setup = await _create_setup(client)
    resp = await client.delete(f"/setups/{setup['id']}/booking", headers=AUTH_HEADERS)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_release_setup_booking_wrong_user(client):
    dev1 = await _create_device(client)
    dev2 = await _create_device(client)
    setup = await _create_setup(client, device_ids=[dev1["id"], dev2["id"]])

    # tester books it
    await client.post(
        f"/setups/{setup['id']}/book",
        json={"duration_hours": 1},
        headers=AUTH_HEADERS,
    )

    # other-user tries to release
    resp = await client.delete(f"/setups/{setup['id']}/booking", headers=OTHER_HEADERS)
    assert resp.status_code == 403
