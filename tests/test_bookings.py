import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
import uuid
import json

AUTH_HEADERS = {"X-Token": "test-token", "X-User": "testuser"}
ADMIN_HEADERS = {"X-Token": "test-token", "X-User": "admin"}


async def create_test_device(client) -> dict:
    resp = await client.post(
        "/boards",
        json={
            "name": f"test-device-{uuid.uuid4().hex[:6]}",
            "description": "Test device",
            "location": "Test Lab",
            "features": {"jtag": True},
            "jtag_port": 3121,
            "ssh_user": "root",
            "ssh_port": 22,
            "power_script": "",
            "power_args": {},
            "enabled": True,
        },
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 201
    return resp.json()


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_create_device(client):
    device = await create_test_device(client)
    assert device["name"].startswith("test-device-")
    assert device["enabled"] is True
    assert device["agent_online"] is False


@pytest.mark.asyncio
async def test_list_devices(client):
    await create_test_device(client)
    resp = await client.get("/boards", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_book_and_release(client):
    device = await create_test_device(client)
    device_id = device["id"]

    # Book it
    resp = await client.post(
        f"/boards/{device_id}/book",
        json={"duration_hours": 2},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 201
    booking = resp.json()
    assert booking["active"] is True
    assert booking["username"] == "testuser"

    # Device should now show as booked
    resp = await client.get(f"/boards/{device_id}", headers=AUTH_HEADERS)
    assert resp.json()["active_booking"]["id"] == booking["id"]

    # Release it
    resp = await client.delete(f"/bookings/{booking['id']}", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["active"] is False
    assert resp.json()["release_reason"] == "manual"


@pytest.mark.asyncio
async def test_double_booking_rejected(client):
    device = await create_test_device(client)
    device_id = device["id"]

    # First booking
    resp1 = await client.post(
        f"/boards/{device_id}/book",
        json={"duration_hours": 1},
        headers=AUTH_HEADERS,
    )
    assert resp1.status_code == 201

    # Second booking on same device should fail
    resp2 = await client.post(
        f"/boards/{device_id}/book",
        json={"duration_hours": 1},
        headers={"X-Token": "test-token", "X-User": "otheruser"},
    )
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_extend_booking(client):
    device = await create_test_device(client)
    device_id = device["id"]

    resp = await client.post(
        f"/boards/{device_id}/book",
        json={"duration_hours": 2},
        headers=AUTH_HEADERS,
    )
    booking = resp.json()

    # Extend once
    resp = await client.patch(
        f"/bookings/{booking['id']}/extend",
        json={"hours": 1},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["extended"] is True

    # Extend again should fail
    resp = await client.patch(
        f"/bookings/{booking['id']}/extend",
        json={"hours": 1},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_booking_duration_limit(client):
    device = await create_test_device(client)
    resp = await client.post(
        f"/boards/{device['id']}/book",
        json={"duration_hours": 25},  # over 24h limit
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_release_other_user_booking_rejected(client):
    device = await create_test_device(client)
    device_id = device["id"]

    resp = await client.post(
        f"/boards/{device_id}/book",
        json={"duration_hours": 1},
        headers=AUTH_HEADERS,
    )
    booking = resp.json()

    # Other user tries to release
    resp = await client.delete(
        f"/bookings/{booking['id']}",
        headers={"X-Token": "test-token", "X-User": "intruder"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_booking_history(client):
    device = await create_test_device(client)
    device_id = device["id"]

    # Create and release a booking
    resp = await client.post(
        f"/boards/{device_id}/book",
        json={"duration_hours": 1},
        headers=AUTH_HEADERS,
    )
    booking = resp.json()
    await client.delete(f"/bookings/{booking['id']}", headers=AUTH_HEADERS)

    # History should include it
    resp = await client.get(
        "/bookings",
        params={"board_id": device_id},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200
    history = resp.json()
    assert any(b["id"] == booking["id"] for b in history)


@pytest.mark.asyncio
async def test_add_and_remove_tool(client):
    device = await create_test_device(client)
    device_id = device["id"]

    # Add tool
    resp = await client.post(
        f"/boards/{device_id}/tools",
        json={
            "type": "logic_analyzer",
            "model": "Saleae Logic 8",
            "connection": "usb",
            "connection_detail": "/dev/ttyUSB1",
            "notes": "",
        },
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 201
    tool = resp.json()

    # Device should show tool
    resp = await client.get(f"/boards/{device_id}", headers=AUTH_HEADERS)
    assert any(t["id"] == tool["id"] for t in resp.json()["tools"])

    # Remove tool
    resp = await client.delete(f"/tools/{tool['id']}", headers=AUTH_HEADERS)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_device_notes(client):
    device = await create_test_device(client)
    device_id = device["id"]

    resp = await client.patch(
        f"/boards/{device_id}",
        json={"current_notes": "Device needs power cycle after JTAG"},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["current_notes"] == "Device needs power cycle after JTAG"


@pytest.mark.asyncio
async def test_auth_required(client):
    resp = await client.get("/boards")
    assert resp.status_code == 422  # Missing header

    resp = await client.get("/boards", headers={"X-Token": "wrong", "X-User": "u"})
    assert resp.status_code == 401
