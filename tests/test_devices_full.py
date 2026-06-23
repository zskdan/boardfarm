"""
Full coverage tests for server/routers/devices.py.

Targets uncovered lines:
  28-30  – _raise_uniqueness_error (device_id conflict vs name conflict)
  49, 54-57 – _build_device_out: active booking loop + IP-fallback (db path, no agents_by_ip)
  120-123 – _load_device: 404 path
  137, 139 – list_devices: agents_by_ip dict build (IP-fallback via list endpoint)
  154 – get_device scalar path
  194-200 – create_device: IntegrityError / uniqueness branch + commit
  211-225 – update_device: field update, IntegrityError branch
  234-242 – delete_device: 404, active-booking guard, cascade
  260-264 – report_device_version: 404 path (device not found)
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

HEADERS = {"X-Token": "test-token", "X-User": "tester"}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _make_device(client, **kwargs) -> dict:
    """Create a device via POST and return the JSON response."""
    payload = {
        "name": f"dev-{uuid.uuid4().hex[:8]}",
        "description": "Test device",
        "location": "Lab X",
        "features": {},
        "jtag_port": 3121,
        "ssh_user": "root",
        "ssh_port": 22,
        "power_script": "",
        "power_args": {},
        "enabled": True,
    }
    payload.update(kwargs)
    r = await client.post("/devices", json=payload, headers=HEADERS)
    assert r.status_code == 201, r.text
    return r.json()


async def _register_agent(client, *, name, url, device_ids=(), token="tok") -> dict:
    r = await client.post("/agents/register", json={
        "name": name, "url": url,
        "device_ids": list(device_ids),
        "token": token,
    })
    assert r.status_code == 200, r.text
    return r.json()


async def _book_device(client, device_id: str, duration_hours: int = 1) -> dict:
    r = await client.post(
        f"/devices/{device_id}/book",
        json={"duration_hours": duration_hours},
        headers=HEADERS,
    )
    assert r.status_code == 201, r.text
    return r.json()


# ─────────────────────────────────────────────────────────────────────────────
# GET /devices  (list_devices — lines 137, 139 and agents_by_ip IP-fallback)
# ─────────────────────────────────────────────────────────────────────────────

async def test_list_devices_empty(client):
    """GET /devices returns a list (possibly empty)."""
    r = await client.get("/devices")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


async def test_list_devices_includes_created_device(client):
    """Newly created device appears in the list."""
    dev = await _make_device(client)
    r = await client.get("/devices")
    assert r.status_code == 200
    ids = [d["id"] for d in r.json()]
    assert dev["id"] in ids


async def test_list_devices_agent_online_via_ip_fallback(client):
    """
    When a device has no FK agent_id but its host_ip matches an online agent's URL,
    list_devices must report agent_online=True (covers lines 28-30 inside the agents_by_ip
    dict built by list_devices at lines 137, 139, and the agents_by_ip lookup at line 49).
    """
    # Register an agent first so it exists (no device_ids so auto-claim may not fire)
    ip = f"10.99.{uuid.uuid4().int & 0xff}.{uuid.uuid4().int & 0xff}"
    agent_name = f"ip-agent-{uuid.uuid4().hex[:6]}"
    await _register_agent(client, name=agent_name, url=f"http://{ip}:8080", device_ids=())

    # Create a device with the same host_ip AFTER registration so agent_id stays None
    dev = await _make_device(client, host_ip=ip)

    # Confirm no FK link
    r = await client.get(f"/devices/{dev['id']}", headers=HEADERS)
    assert r.json()["agent_id"] is None, "Precondition: must be IP-fallback path"

    # GET /devices should resolve via agents_by_ip and report agent_online=True
    r = await client.get("/devices")
    assert r.status_code == 200
    listing = {d["id"]: d for d in r.json()}
    assert listing[dev["id"]]["agent_online"] is True


async def test_list_devices_with_active_booking_shown(client):
    """
    list_devices must populate active_booking for a device that has one
    (covers lines 49, 54-57 active booking loop in _build_device_out).
    """
    dev = await _make_device(client)
    bk = await _book_device(client, dev["id"])

    r = await client.get("/devices")
    assert r.status_code == 200
    listing = {d["id"]: d for d in r.json()}
    assert listing[dev["id"]]["active_booking"] is not None
    assert listing[dev["id"]]["active_booking"]["id"] == bk["id"]


# ─────────────────────────────────────────────────────────────────────────────
# GET /devices/{id}  (get_device — line 154)
# ─────────────────────────────────────────────────────────────────────────────

async def test_get_device_returns_correct_device(client):
    dev = await _make_device(client)
    r = await client.get(f"/devices/{dev['id']}", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["id"] == dev["id"]


async def test_get_device_404_for_unknown(client):
    """_load_device raises 404 when the device is not found (lines 120-123)."""
    r = await client.get(f"/devices/{uuid.uuid4()}", headers=HEADERS)
    assert r.status_code == 404
    assert "not found" in r.json()["detail"].lower()


async def test_get_device_ip_fallback_agent_online(client):
    """
    GET /devices/{id} (single) uses _build_device_out with agents_by_ip=None,
    so it falls through to the db SELECT path for IP resolution (lines 51-57).
    """
    ip = f"10.88.{uuid.uuid4().int & 0xff}.{uuid.uuid4().int & 0xff}"
    agent_name = f"single-ip-{uuid.uuid4().hex[:6]}"
    await _register_agent(client, name=agent_name, url=f"http://{ip}:8080", device_ids=())

    dev = await _make_device(client, host_ip=ip)

    # Ensure no FK link
    r = await client.get(f"/devices/{dev['id']}", headers=HEADERS)
    assert r.json()["agent_id"] is None, "Precondition: IP-fallback only"
    assert r.json()["agent_online"] is True


async def test_get_device_active_booking_reflected(client):
    """Single GET should also show active booking."""
    dev = await _make_device(client)
    bk = await _book_device(client, dev["id"])
    r = await client.get(f"/devices/{dev['id']}", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["active_booking"]["id"] == bk["id"]


async def test_get_device_features_as_json_string(client):
    """
    DeviceOut.parse_json_str validator (schemas.py line 167) is exercised when
    features is stored as a JSON string and returned parsed as a dict.
    """
    features = {"jtag": True, "uart": False, "custom": "value"}
    dev = await _make_device(client, features=features)
    r = await client.get(f"/devices/{dev['id']}", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["features"] == features


# ─────────────────────────────────────────────────────────────────────────────
# POST /devices  (create_device — IntegrityError lines 194-200)
# ─────────────────────────────────────────────────────────────────────────────

async def test_create_device_duplicate_name_returns_422(client):
    """Creating two devices with identical names triggers the name uniqueness error (line 30)."""
    name = f"dup-name-{uuid.uuid4().hex[:6]}"
    await _make_device(client, name=name)

    r = await client.post("/devices", json={"name": name}, headers=HEADERS)
    assert r.status_code == 422
    assert "name" in r.json()["detail"].lower()


async def test_create_device_with_features_and_power_args(client):
    """Verify that features dict and power_args dict are persisted correctly."""
    features = {"jtag": True, "usb": False}
    power_args = {"relay_id": 3, "board": "a7"}
    dev = await _make_device(client, features=features, power_args=power_args)
    assert dev["features"] == features
    assert dev["power_args"] == power_args


# ─────────────────────────────────────────────────────────────────────────────
# PATCH /devices/{id}  (update_device — lines 211-225)
# ─────────────────────────────────────────────────────────────────────────────

async def test_update_device_description(client):
    """update_device writes scalar fields correctly (line 215)."""
    dev = await _make_device(client)
    r = await client.patch(
        f"/devices/{dev['id']}",
        json={"description": "Updated description"},
        headers=HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["description"] == "Updated description"


async def test_update_device_features_dict(client):
    """update_device serialises features dict to JSON before storing (line 213)."""
    dev = await _make_device(client, features={"old": True})
    new_features = {"new": True, "extra": 42}
    r = await client.patch(
        f"/devices/{dev['id']}",
        json={"features": new_features},
        headers=HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["features"] == new_features


async def test_update_device_power_args_dict(client):
    """update_device serialises power_args dict (line 213 branch for power_args)."""
    dev = await _make_device(client)
    new_args = {"relay_id": 7, "timeout": 10}
    r = await client.patch(
        f"/devices/{dev['id']}",
        json={"power_args": new_args},
        headers=HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["power_args"] == new_args


async def test_update_device_enabled_false(client):
    """Disabling a device via PATCH returns enabled=False."""
    dev = await _make_device(client, enabled=True)
    r = await client.patch(
        f"/devices/{dev['id']}",
        json={"enabled": False},
        headers=HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["enabled"] is False


async def test_update_device_404_for_unknown(client):
    """update_device returns 404 when device_id doesn't exist (via _load_device 120-123)."""
    r = await client.patch(
        f"/devices/{uuid.uuid4()}",
        json={"description": "x"},
        headers=HEADERS,
    )
    assert r.status_code == 404


async def test_update_device_duplicate_name_returns_422(client):
    """Renaming a device to an existing name triggers uniqueness error (lines 219-221)."""
    name_a = f"ua-{uuid.uuid4().hex[:6]}"
    name_b = f"ub-{uuid.uuid4().hex[:6]}"
    await _make_device(client, name=name_a)
    dev_b = await _make_device(client, name=name_b)

    r = await client.patch(
        f"/devices/{dev_b['id']}",
        json={"name": name_a},
        headers=HEADERS,
    )
    assert r.status_code == 422
    assert "name" in r.json()["detail"].lower()


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /devices/{id}  (delete_device — lines 234-242)
# ─────────────────────────────────────────────────────────────────────────────

async def test_delete_device_returns_204(client):
    """Normal delete returns 204 and device is gone (lines 234-242)."""
    dev = await _make_device(client)
    r = await client.delete(f"/devices/{dev['id']}", headers=HEADERS)
    assert r.status_code == 204

    r = await client.get(f"/devices/{dev['id']}", headers=HEADERS)
    assert r.status_code == 404


async def test_delete_device_404_for_unknown(client):
    """Delete of nonexistent device returns 404."""
    r = await client.delete(f"/devices/{uuid.uuid4()}", headers=HEADERS)
    assert r.status_code == 404


async def test_delete_device_with_active_booking_returns_409(client):
    """
    delete_device blocks if the device has an active booking (lines 236-239).
    """
    dev = await _make_device(client)
    await _book_device(client, dev["id"])

    r = await client.delete(f"/devices/{dev['id']}", headers=HEADERS)
    assert r.status_code == 409
    assert "active booking" in r.json()["detail"].lower()


async def test_delete_device_with_released_booking_cascade(client):
    """
    After releasing a booking, delete succeeds and the booking is cascade-deleted
    (bookings relationship has cascade='all, delete-orphan').
    """
    dev = await _make_device(client)
    bk = await _book_device(client, dev["id"])

    # Release the booking first
    r = await client.delete(f"/bookings/{bk['id']}", headers=HEADERS)
    assert r.status_code == 200

    # Now delete the device — should succeed
    r = await client.delete(f"/devices/{dev['id']}", headers=HEADERS)
    assert r.status_code == 204

    # Booking should be gone too (cascade)
    r = await client.get("/bookings", params={"device_id": dev["id"]})
    assert r.status_code == 200
    assert r.json() == []


# ─────────────────────────────────────────────────────────────────────────────
# PATCH /devices/{id}/version  (report_device_version — lines 260-264)
# ─────────────────────────────────────────────────────────────────────────────

async def test_version_push_unknown_device_returns_404(client):
    """
    report_device_version returns 404 when the device does not exist
    (lines 260-262, the scalar_one_or_none → 404 branch).
    """
    r = await client.patch(
        f"/devices/{uuid.uuid4()}/version",
        json={"version": "abc123"},
        headers={"X-Token": "test-token"},
    )
    assert r.status_code == 404
    assert "not found" in r.json()["detail"].lower()


async def test_version_push_updates_version(client):
    """Sanity-check: version push succeeds and stores the value."""
    dev = await _make_device(client)
    r = await client.patch(
        f"/devices/{dev['id']}/version",
        json={"version": "abc1234"},
        headers={"X-Token": "test-token"},
    )
    assert r.status_code == 204

    r = await client.get(f"/devices/{dev['id']}", headers=HEADERS)
    assert r.json()["deployed_version"] == "abc1234"


# ─────────────────────────────────────────────────────────────────────────────
# _raise_uniqueness_error  (lines 28-30 — device_id vs name conflict messages)
# ─────────────────────────────────────────────────────────────────────────────

async def test_uniqueness_error_name_message(client):
    """
    When the IntegrityError string does NOT contain 'device_id', the handler
    raises "Device name is already in use" (line 30).
    """
    name = f"uniq-name-{uuid.uuid4().hex[:6]}"
    await _make_device(client, name=name)

    r = await client.post("/devices", json={"name": name}, headers=HEADERS)
    assert r.status_code == 422
    assert "name" in r.json()["detail"].lower()


async def test_uniqueness_error_device_id_message(client):
    """
    Trigger the 'device_id in use' branch (line 28-29) by directly patching
    _raise_uniqueness_error to receive a string containing 'uq_device_id'.
    """
    from server.routers import devices as dev_module

    original = dev_module._raise_uniqueness_error

    def patched(exc_str):
        # Force the device_id branch by embedding the key substring
        return original("devices.device_id: UNIQUE constraint failed")

    with patch.object(dev_module, "_raise_uniqueness_error", side_effect=patched):
        # Call original with a device_id-containing string
        import pytest
        with pytest.raises(Exception) as exc_info:
            dev_module._raise_uniqueness_error("devices.device_id: UNIQUE constraint failed")

    from fastapi import HTTPException
    # Must raise HTTPException with 422 and the device_id message
    exc = exc_info.value
    assert exc.status_code == 422
    assert "Device ID" in exc.detail


async def test_raise_uniqueness_error_name_branch():
    """
    _raise_uniqueness_error with a generic error string (no 'device_id')
    raises 422 with 'Device name' message (line 30).
    """
    import pytest
    from fastapi import HTTPException
    from server.routers.devices import _raise_uniqueness_error

    with pytest.raises(HTTPException) as exc_info:
        _raise_uniqueness_error("UNIQUE constraint failed: devices.name")

    assert exc_info.value.status_code == 422
    assert "name" in exc_info.value.detail.lower()


async def test_raise_uniqueness_error_device_id_branch():
    """
    _raise_uniqueness_error with 'devices.device_id' in the string
    raises 422 with 'Device ID' message (lines 28-29).
    """
    import pytest
    from fastapi import HTTPException
    from server.routers.devices import _raise_uniqueness_error

    with pytest.raises(HTTPException) as exc_info:
        _raise_uniqueness_error("UNIQUE constraint failed: devices.device_id")

    assert exc_info.value.status_code == 422
    assert "Device ID" in exc_info.value.detail


async def test_raise_uniqueness_error_uq_device_id_branch():
    """
    _raise_uniqueness_error with 'uq_device_id' in the string
    also raises the Device ID message (line 28 second condition).
    """
    import pytest
    from fastapi import HTTPException
    from server.routers.devices import _raise_uniqueness_error

    with pytest.raises(HTTPException) as exc_info:
        _raise_uniqueness_error("UNIQUE constraint failed: uq_device_id")

    assert exc_info.value.status_code == 422
    assert "Device ID" in exc_info.value.detail
