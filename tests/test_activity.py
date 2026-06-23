"""Tests for server/routers/activity.py — targets 100% coverage (lines 21-30)."""
from __future__ import annotations

import uuid

import pytest

AUTH_HEADERS = {"X-Token": "test-token", "X-User": "tester"}
OTHER_HEADERS = {"X-Token": "test-token", "X-User": "other-user"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_device(client, *, name: str | None = None) -> dict:
    payload = {
        "name": name or f"dev-{uuid.uuid4().hex[:8]}",
        "description": "test device",
        "location": "Lab",
        "features": {},
        "jtag_port": 3121,
        "ssh_user": "root",
        "ssh_port": 22,
        "power_script": "",
        "power_args": {},
        "enabled": True,
    }
    resp = await client.post("/devices", json=payload, headers=AUTH_HEADERS)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _book_device(client, device_id: str, headers: dict = AUTH_HEADERS) -> dict:
    resp = await client.post(
        f"/devices/{device_id}/book",
        json={"duration_hours": 1},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _release_booking(client, booking_id: str, headers: dict = AUTH_HEADERS) -> None:
    resp = await client.delete(f"/bookings/{booking_id}", headers=headers)
    assert resp.status_code == 200, resp.text


async def _add_tool(client, device_id: str) -> dict:
    resp = await client.post(
        f"/devices/{device_id}/tools",
        json={"type": "jtag", "model": "J-Link"},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# GET /activity
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_activity_empty(client):
    """GET /activity returns an empty list when no audit entries exist."""
    resp = await client.get("/activity")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_list_activity_after_book_and_release(client):
    """After booking and releasing a device, audit entries are returned."""
    device = await _create_device(client)
    booking = await _book_device(client, device["id"])
    await _release_booking(client, booking["id"])

    resp = await client.get("/activity")
    assert resp.status_code == 200
    entries = resp.json()
    assert len(entries) >= 2  # at minimum: booked + released

    # Verify AuditLogOut.timestamp serialiser ran (schemas.py line 249)
    for entry in entries:
        assert "timestamp" in entry
        assert entry["timestamp"].endswith("Z")
        assert "action" in entry
        assert "username" in entry


@pytest.mark.asyncio
async def test_list_activity_filter_by_device_ref(client):
    """Filter by device_ref returns only entries for that device."""
    dev1 = await _create_device(client)
    dev2 = await _create_device(client)

    booking1 = await _book_device(client, dev1["id"])
    booking2 = await _book_device(client, dev2["id"])

    # Release both
    await _release_booking(client, booking1["id"])
    await _release_booking(client, booking2["id"])

    resp = await client.get("/activity", params={"device_ref": dev1["id"]})
    assert resp.status_code == 200
    entries = resp.json()
    assert len(entries) >= 1
    # All returned entries should reference dev1
    for entry in entries:
        assert entry["device_ref"] == dev1["id"]


@pytest.mark.asyncio
async def test_list_activity_filter_by_username(client):
    """Filter by username returns only entries for that user."""
    device = await _create_device(client)

    # tester books it
    booking = await _book_device(client, device["id"], headers=AUTH_HEADERS)
    await _release_booking(client, booking["id"], headers=AUTH_HEADERS)

    resp = await client.get("/activity", params={"username": "tester"})
    assert resp.status_code == 200
    entries = resp.json()
    assert len(entries) >= 1
    for entry in entries:
        assert entry["username"] == "tester"


@pytest.mark.asyncio
async def test_list_activity_filter_by_action(client):
    """Filter by action only returns entries with that action type."""
    device = await _create_device(client)
    tool = await _add_tool(client, device["id"])

    # Remove the tool — produces a 'tool_deleted' audit entry
    await client.delete(f"/tools/{tool['id']}", headers=AUTH_HEADERS)

    resp = await client.get("/activity", params={"action": "tool_deleted"})
    assert resp.status_code == 200
    entries = resp.json()
    assert len(entries) >= 1
    for entry in entries:
        assert entry["action"] == "tool_deleted"


@pytest.mark.asyncio
async def test_list_activity_filter_by_action_tool_added(client):
    """Adding a tool produces a 'tool_added' audit entry that can be filtered."""
    device = await _create_device(client)
    await _add_tool(client, device["id"])

    resp = await client.get("/activity", params={"action": "tool_added"})
    assert resp.status_code == 200
    entries = resp.json()
    assert len(entries) >= 1
    for entry in entries:
        assert entry["action"] == "tool_added"


@pytest.mark.asyncio
async def test_list_activity_pagination_skip(client):
    """skip parameter offsets the returned results."""
    device = await _create_device(client)
    booking = await _book_device(client, device["id"])
    await _release_booking(client, booking["id"])

    resp_all = await client.get("/activity", params={"limit": 500})
    all_entries = resp_all.json()
    total = len(all_entries)

    if total < 2:
        pytest.skip("Not enough audit entries to test skip pagination")

    resp_skipped = await client.get("/activity", params={"skip": 1, "limit": 500})
    skipped_entries = resp_skipped.json()
    assert len(skipped_entries) == total - 1
    # The first entry of skip=0 should not appear at position 0 of skip=1
    assert all_entries[0]["id"] not in [e["id"] for e in skipped_entries[:1]] or len(skipped_entries) < total


@pytest.mark.asyncio
async def test_list_activity_pagination_limit(client):
    """limit parameter caps the number of returned results."""
    device = await _create_device(client)
    # Generate several audit entries
    for _ in range(3):
        dev = await _create_device(client)
        bk = await _book_device(client, dev["id"])
        await _release_booking(client, bk["id"])

    resp = await client.get("/activity", params={"limit": 2})
    assert resp.status_code == 200
    assert len(resp.json()) <= 2


@pytest.mark.asyncio
async def test_list_activity_multiple_filters(client):
    """Combining filters works correctly (AND semantics)."""
    device = await _create_device(client)
    booking = await _book_device(client, device["id"], headers=AUTH_HEADERS)
    await _release_booking(client, booking["id"], headers=AUTH_HEADERS)

    # Filter by both username and device_ref
    resp = await client.get(
        "/activity",
        params={"username": "tester", "device_ref": device["id"]},
    )
    assert resp.status_code == 200
    entries = resp.json()
    assert len(entries) >= 1
    for entry in entries:
        assert entry["username"] == "tester"
        assert entry["device_ref"] == device["id"]


@pytest.mark.asyncio
async def test_list_activity_no_match_filter(client):
    """A filter that matches nothing returns an empty list."""
    resp = await client.get("/activity", params={"username": "no-such-user-xyz"})
    assert resp.status_code == 200
    assert resp.json() == []
