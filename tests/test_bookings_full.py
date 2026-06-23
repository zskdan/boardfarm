"""
Full coverage tests for server/routers/bookings.py.

Targets uncovered lines:
  41-48   – _call_agent: agent notification on book/release
  57-60   – _load_device: 404 path
  69-72   – _load_booking: 404 path
  101     – max_h == 0 (permanent/never-expires) mode
  105     – duration_hours < 1 → 422
  115-162 – book_device: disabled device 409, already-booked 409, normal booking,
            agent call on booking, IntegrityError path
  174-199 – release_booking: inactive 409, wrong-user 403, admin release,
            agent call on release
  212-231 – extend_booking: inactive 409, wrong-user 403, already-extended 409,
            max_booking_hours cap, normal extend
  241-248 – get_commands: inactive 409, commands output
  275, 277 – list_bookings: device_id filter, username filter, active filter
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.config import settings

HEADERS = {"X-Token": "test-token", "X-User": "tester"}
OTHER_HEADERS = {"X-Token": "test-token", "X-User": "other-user"}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _make_device(client, **kwargs) -> dict:
    payload = {
        "name": f"bk-dev-{uuid.uuid4().hex[:8]}",
        "description": "Booking test device",
        "location": "Lab",
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


async def _register_agent(client, *, name, url, device_ids=(), token="agent-tok") -> dict:
    r = await client.post("/agents/register", json={
        "name": name, "url": url,
        "device_ids": list(device_ids),
        "token": token,
    }, headers={"X-Token": "test-token"})
    assert r.status_code == 200, r.text
    return r.json()


async def _book(client, device_id: str, *, duration_hours: int = 1,
                headers=None) -> dict:
    headers = headers or HEADERS
    r = await client.post(
        f"/devices/{device_id}/book",
        json={"duration_hours": duration_hours},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _release(client, booking_id: str, headers=None) -> dict:
    headers = headers or HEADERS
    r = await client.delete(f"/bookings/{booking_id}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _silent_agent_mock():
    """Return a mock httpx.AsyncClient whose request() silently succeeds."""
    mc = AsyncMock()
    mc.__aenter__ = AsyncMock(return_value=mc)
    mc.__aexit__ = AsyncMock(return_value=False)
    mc.request = AsyncMock(return_value=MagicMock(status_code=200))
    return mc


# ─────────────────────────────────────────────────────────────────────────────
# _load_device 404  (lines 57-60)
# ─────────────────────────────────────────────────────────────────────────────

async def test_book_unknown_device_returns_404(client):
    """POST /devices/{id}/book with an unknown device_id → 404."""
    r = await client.post(
        f"/devices/{uuid.uuid4()}/book",
        json={"duration_hours": 1},
        headers=HEADERS,
    )
    assert r.status_code == 404
    assert "not found" in r.json()["detail"].lower()


# ─────────────────────────────────────────────────────────────────────────────
# _load_booking 404  (lines 69-72)
# ─────────────────────────────────────────────────────────────────────────────

async def test_release_unknown_booking_returns_404(client):
    """DELETE /bookings/{id} with unknown booking_id → 404."""
    r = await client.delete(f"/bookings/{uuid.uuid4()}", headers=HEADERS)
    assert r.status_code == 404


async def test_extend_unknown_booking_returns_404(client):
    """PATCH /bookings/{id}/extend with unknown booking_id → 404."""
    r = await client.patch(
        f"/bookings/{uuid.uuid4()}/extend",
        json={"hours": 1},
        headers=HEADERS,
    )
    assert r.status_code == 404


async def test_get_commands_unknown_booking_returns_404(client):
    """GET /bookings/{id}/commands with unknown booking_id → 404."""
    r = await client.get(f"/bookings/{uuid.uuid4()}/commands", headers=HEADERS)
    assert r.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# book_device — max_booking_hours == 0  (line 101)
# ─────────────────────────────────────────────────────────────────────────────

async def test_book_permanent_mode_ignores_duration(client):
    """
    When settings.max_booking_hours == 0, duration_hours is ignored and the
    booking end_time is set ~10 years in the future (line 101).
    """
    dev = await _make_device(client)

    original = settings.max_booking_hours
    settings.max_booking_hours = 0
    try:
        r = await client.post(
            f"/devices/{dev['id']}/book",
            json={},  # no duration_hours at all
            headers=HEADERS,
        )
        assert r.status_code == 201, r.text
        bk = r.json()
        assert bk["active"] is True

        from datetime import datetime as dt
        end = dt.fromisoformat(bk["end_time"].replace("Z", ""))
        start = dt.fromisoformat(bk["start_time"].replace("Z", ""))
        delta_days = (end - start).days
        # 10-year sentinel: should be well over 365 days
        assert delta_days > 365 * 5
    finally:
        settings.max_booking_hours = original


# ─────────────────────────────────────────────────────────────────────────────
# book_device — duration_hours < 1  (line 105)
# ─────────────────────────────────────────────────────────────────────────────

async def test_book_duration_less_than_1_returns_422(client):
    """duration_hours < 1 must be rejected (line 105)."""
    dev = await _make_device(client)

    original = settings.max_booking_hours
    settings.max_booking_hours = 24
    try:
        r = await client.post(
            f"/devices/{dev['id']}/book",
            json={"duration_hours": 0},
            headers=HEADERS,
        )
        assert r.status_code == 422
        assert "duration_hours" in r.json()["detail"].lower()
    finally:
        settings.max_booking_hours = original


async def test_book_duration_negative_returns_422(client):
    dev = await _make_device(client)

    original = settings.max_booking_hours
    settings.max_booking_hours = 24
    try:
        r = await client.post(
            f"/devices/{dev['id']}/book",
            json={"duration_hours": -5},
            headers=HEADERS,
        )
        assert r.status_code == 422
    finally:
        settings.max_booking_hours = original


# ─────────────────────────────────────────────────────────────────────────────
# book_device — duration_hours > max  (line 107-109)
# ─────────────────────────────────────────────────────────────────────────────

async def test_book_duration_exceeds_max_returns_422(client):
    """duration_hours > max_booking_hours must be rejected."""
    dev = await _make_device(client)

    original = settings.max_booking_hours
    settings.max_booking_hours = 4
    try:
        r = await client.post(
            f"/devices/{dev['id']}/book",
            json={"duration_hours": 8},
            headers=HEADERS,
        )
        assert r.status_code == 422
        assert "4" in r.json()["detail"]
    finally:
        settings.max_booking_hours = original


# ─────────────────────────────────────────────────────────────────────────────
# book_device — disabled device  (line 115-116)
# ─────────────────────────────────────────────────────────────────────────────

async def test_book_disabled_device_returns_409(client):
    """Booking a disabled device returns 409."""
    dev = await _make_device(client, enabled=False)
    r = await client.post(
        f"/devices/{dev['id']}/book",
        json={"duration_hours": 1},
        headers=HEADERS,
    )
    assert r.status_code == 409
    assert "disabled" in r.json()["detail"].lower()


# ─────────────────────────────────────────────────────────────────────────────
# book_device — already booked  (line 119-123)
# ─────────────────────────────────────────────────────────────────────────────

async def test_book_already_booked_device_returns_409(client):
    """Booking a device that already has an active booking returns 409."""
    dev = await _make_device(client)
    await _book(client, dev["id"])

    r = await client.post(
        f"/devices/{dev['id']}/book",
        json={"duration_hours": 1},
        headers=OTHER_HEADERS,
    )
    assert r.status_code == 409


# ─────────────────────────────────────────────────────────────────────────────
# book_device — with agent (_call_agent on book, lines 144-150)
# ─────────────────────────────────────────────────────────────────────────────

async def test_book_calls_agent_on_booking(client):
    """
    When a device has an FK-linked agent, book_device calls the agent
    at /devices/{id}/services/start (lines 144-150).
    """
    ip = f"10.77.{uuid.uuid4().int & 0xff}.{uuid.uuid4().int & 0xff}"
    dev = await _make_device(client, host_ip=ip)
    await _register_agent(
        client,
        name=f"bk-agt-{uuid.uuid4().hex[:6]}",
        url=f"http://{ip}:8080",
        device_ids=[dev["id"]],
        token="bk-tok",
    )

    mc = _silent_agent_mock()
    with patch("server.routers.bookings.httpx.AsyncClient", return_value=mc):
        r = await client.post(
            f"/devices/{dev['id']}/book",
            json={"duration_hours": 1},
            headers=HEADERS,
        )
    assert r.status_code == 201
    # Agent must have been called
    mc.request.assert_called_once()
    call_args = mc.request.call_args
    assert "start" in call_args[0][1]  # URL contains "start"


async def test_book_agent_offline_still_succeeds(client):
    """
    If the agent raises an exception, _call_agent swallows it and the booking
    proceeds anyway (lines 41-48 exception handler).
    """
    ip = f"10.76.{uuid.uuid4().int & 0xff}.{uuid.uuid4().int & 0xff}"
    dev = await _make_device(client, host_ip=ip)
    await _register_agent(
        client,
        name=f"off-agt-{uuid.uuid4().hex[:6]}",
        url=f"http://{ip}:8080",
        device_ids=[dev["id"]],
    )

    mc = AsyncMock()
    mc.__aenter__ = AsyncMock(return_value=mc)
    mc.__aexit__ = AsyncMock(return_value=False)
    mc.request = AsyncMock(side_effect=Exception("Connection refused"))

    with patch("server.routers.bookings.httpx.AsyncClient", return_value=mc):
        r = await client.post(
            f"/devices/{dev['id']}/book",
            json={"duration_hours": 1},
            headers=HEADERS,
        )
    assert r.status_code == 201


# ─────────────────────────────────────────────────────────────────────────────
# release_booking — paths (lines 174-199)
# ─────────────────────────────────────────────────────────────────────────────

async def test_release_inactive_booking_returns_409(client):
    """Releasing an already-inactive booking returns 409 (line 174-175)."""
    dev = await _make_device(client)
    bk = await _book(client, dev["id"])
    await _release(client, bk["id"])

    # Second release attempt
    r = await client.delete(f"/bookings/{bk['id']}", headers=HEADERS)
    assert r.status_code == 409
    assert "inactive" in r.json()["detail"].lower()


async def test_release_other_users_booking_forbidden(client):
    """Releasing another user's booking (non-admin) returns 403 (lines 177-180)."""
    dev = await _make_device(client)
    bk = await _book(client, dev["id"])

    r = await client.delete(f"/bookings/{bk['id']}", headers=OTHER_HEADERS)
    assert r.status_code == 403
    assert "your own" in r.json()["detail"].lower()


async def test_release_booking_reason_manual(client):
    """Normal release by the booker sets release_reason='manual' (line 183)."""
    dev = await _make_device(client)
    bk = await _book(client, dev["id"])

    r = await client.delete(f"/bookings/{bk['id']}", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["release_reason"] == "manual"
    assert r.json()["active"] is False


async def test_admin_release_sets_reason_admin(client):
    """
    Admin user releasing another user's booking sets release_reason='admin' (line 183).
    Also covers the is_admin=True path in require_user_or_admin.
    """
    dev = await _make_device(client)
    bk = await _book(client, dev["id"])  # booked by "tester"

    original_admins = settings.admin_users
    settings.admin_users = ["admin-user"]
    try:
        admin_headers = {"X-Token": "test-token", "X-User": "admin-user"}
        r = await client.delete(f"/bookings/{bk['id']}", headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["release_reason"] == "admin"
        assert r.json()["active"] is False
    finally:
        settings.admin_users = original_admins


async def test_release_calls_agent_on_release(client):
    """
    When a device has an FK-linked agent, release_booking calls the agent
    at /devices/{id}/services/stop (lines 187-194).
    """
    ip = f"10.75.{uuid.uuid4().int & 0xff}.{uuid.uuid4().int & 0xff}"
    dev = await _make_device(client, host_ip=ip)
    await _register_agent(
        client,
        name=f"rel-agt-{uuid.uuid4().hex[:6]}",
        url=f"http://{ip}:8080",
        device_ids=[dev["id"]],
        token="rel-tok",
    )

    # Book (mock agent call for booking)
    book_mc = _silent_agent_mock()
    with patch("server.routers.bookings.httpx.AsyncClient", return_value=book_mc):
        bk = await _book(client, dev["id"])

    # Release — the agent must be notified
    release_mc = _silent_agent_mock()
    with patch("server.routers.bookings.httpx.AsyncClient", return_value=release_mc):
        r = await client.delete(f"/bookings/{bk['id']}", headers=HEADERS)

    assert r.status_code == 200
    release_mc.request.assert_called_once()
    call_args = release_mc.request.call_args
    assert "stop" in call_args[0][1]


async def test_release_agent_offline_still_succeeds(client):
    """
    Agent exception during release is silently swallowed (lines 41-48 path on release).
    """
    ip = f"10.74.{uuid.uuid4().int & 0xff}.{uuid.uuid4().int & 0xff}"
    dev = await _make_device(client, host_ip=ip)
    await _register_agent(
        client,
        name=f"off-rel-{uuid.uuid4().hex[:6]}",
        url=f"http://{ip}:8080",
        device_ids=[dev["id"]],
    )

    book_mc = _silent_agent_mock()
    with patch("server.routers.bookings.httpx.AsyncClient", return_value=book_mc):
        bk = await _book(client, dev["id"])

    fail_mc = AsyncMock()
    fail_mc.__aenter__ = AsyncMock(return_value=fail_mc)
    fail_mc.__aexit__ = AsyncMock(return_value=False)
    fail_mc.request = AsyncMock(side_effect=Exception("unreachable"))

    with patch("server.routers.bookings.httpx.AsyncClient", return_value=fail_mc):
        r = await client.delete(f"/bookings/{bk['id']}", headers=HEADERS)

    assert r.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# extend_booking  (lines 212-231)
# ─────────────────────────────────────────────────────────────────────────────

async def test_extend_inactive_booking_returns_409(client):
    """Extending a released booking returns 409 (line 212-213)."""
    dev = await _make_device(client)
    bk = await _book(client, dev["id"])
    await _release(client, bk["id"])

    r = await client.patch(
        f"/bookings/{bk['id']}/extend",
        json={"hours": 1},
        headers=HEADERS,
    )
    assert r.status_code == 409
    assert "not active" in r.json()["detail"].lower()


async def test_extend_other_users_booking_returns_403(client):
    """Extending another user's booking returns 403 (line 214-215)."""
    dev = await _make_device(client)
    bk = await _book(client, dev["id"])

    r = await client.patch(
        f"/bookings/{bk['id']}/extend",
        json={"hours": 1},
        headers=OTHER_HEADERS,
    )
    assert r.status_code == 403
    assert "your booking" in r.json()["detail"].lower()


async def test_extend_twice_returns_409(client):
    """Extending a booking that is already extended returns 409 (line 216-217)."""
    dev = await _make_device(client)
    bk = await _book(client, dev["id"])

    # First extend — should succeed
    r = await client.patch(
        f"/bookings/{bk['id']}/extend",
        json={"hours": 1},
        headers=HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["extended"] is True

    # Second extend — must fail
    r = await client.patch(
        f"/bookings/{bk['id']}/extend",
        json={"hours": 1},
        headers=HEADERS,
    )
    assert r.status_code == 409
    assert "already extended" in r.json()["detail"].lower()


async def test_extend_normal_adds_hours(client):
    """Normal extend increases end_time (lines 226-231)."""
    dev = await _make_device(client)
    bk = await _book(client, dev["id"], duration_hours=2)

    original_end = bk["end_time"]

    r = await client.patch(
        f"/bookings/{bk['id']}/extend",
        json={"hours": 2},
        headers=HEADERS,
    )
    assert r.status_code == 200
    new_end = r.json()["end_time"]
    assert new_end > original_end
    assert r.json()["extended"] is True


async def test_extend_capped_at_max_booking_hours(client):
    """
    When the new end_time would exceed start_time + max_booking_hours,
    it is capped at max_end (lines 221-224).
    """
    original = settings.max_booking_hours
    settings.max_booking_hours = 3
    try:
        dev = await _make_device(client)
        bk = await _book(client, dev["id"], duration_hours=2)

        # Try to extend by 5 hours — cap at 3h from start
        r = await client.patch(
            f"/bookings/{bk['id']}/extend",
            json={"hours": 5},
            headers=HEADERS,
        )
        assert r.status_code == 200
        from datetime import datetime as dt
        start = dt.fromisoformat(r.json()["start_time"].replace("Z", ""))
        end = dt.fromisoformat(r.json()["end_time"].replace("Z", ""))
        total_hours = (end - start).total_seconds() / 3600
        # Should be at most 3h (plus tiny float tolerance)
        assert total_hours <= 3.01
    finally:
        settings.max_booking_hours = original


# ─────────────────────────────────────────────────────────────────────────────
# get_commands  (lines 241-257)
# ─────────────────────────────────────────────────────────────────────────────

async def test_get_commands_inactive_booking_returns_409(client):
    """GET /bookings/{id}/commands on an inactive booking returns 409 (lines 241-242)."""
    dev = await _make_device(client)
    bk = await _book(client, dev["id"])
    await _release(client, bk["id"])

    r = await client.get(f"/bookings/{bk['id']}/commands", headers=HEADERS)
    assert r.status_code == 409
    assert "not active" in r.json()["detail"].lower()


async def test_get_commands_active_booking_returns_fields(client):
    """GET /bookings/{id}/commands on an active booking returns all command fields."""
    dev = await _make_device(client,
                              host_ip="192.168.1.50",
                              device_ip="192.168.1.51",
                              jtag_port=3121,
                              ssh_user="root",
                              ssh_port=22,
                              uart_device="/dev/ttyUSB0")
    bk = await _book(client, dev["id"])

    r = await client.get(f"/bookings/{bk['id']}/commands", headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert "jtag_connect" in data
    assert "uart" in data
    assert "ssh" in data
    assert "power_on" in data
    assert "vivado_tcl" in data

    # jtag_connect should reference the agent IP and port
    assert "192.168.1.50" in data["jtag_connect"]
    assert "3121" in data["jtag_connect"]

    # uart should include uart_device and host_ip
    assert "/dev/ttyUSB0" in data["uart"]
    assert "192.168.1.50" in data["uart"]

    # ssh should include ssh_user, device_ip, and ssh_port
    assert "root" in data["ssh"]
    assert "22" in data["ssh"]


async def test_get_commands_no_jtag_port_empty_string(client):
    """When jtag_port=0 (falsy), jtag_connect and vivado_tcl must be empty strings."""
    dev = await _make_device(client, jtag_port=0)
    bk = await _book(client, dev["id"])

    r = await client.get(f"/bookings/{bk['id']}/commands", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["jtag_connect"] == ""
    assert r.json()["vivado_tcl"] == ""


async def test_get_commands_no_ssh_port_empty_string(client):
    """When ssh_port=0 (falsy), ssh must be empty string."""
    dev = await _make_device(client, ssh_port=0)
    bk = await _book(client, dev["id"])

    r = await client.get(f"/bookings/{bk['id']}/commands", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["ssh"] == ""


async def test_get_commands_no_uart_device_empty_string(client):
    """When uart_device is empty (or host_ip absent), uart must be empty string."""
    dev = await _make_device(client, uart_device="", host_ip=None)
    bk = await _book(client, dev["id"])

    r = await client.get(f"/bookings/{bk['id']}/commands", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["uart"] == ""


# ─────────────────────────────────────────────────────────────────────────────
# list_bookings  (lines 275, 277 — filters)
# ─────────────────────────────────────────────────────────────────────────────

async def test_list_bookings_no_filter(client):
    """GET /bookings with no filters returns all bookings."""
    dev = await _make_device(client)
    bk = await _book(client, dev["id"])

    r = await client.get("/bookings")
    assert r.status_code == 200
    ids = [b["id"] for b in r.json()]
    assert bk["id"] in ids


async def test_list_bookings_filter_by_device_id(client):
    """GET /bookings?device_id=X returns only bookings for that device (line 273)."""
    dev_a = await _make_device(client)
    dev_b = await _make_device(client)
    bk_a = await _book(client, dev_a["id"])
    bk_b = await _book(client, dev_b["id"])
    await _release(client, bk_b["id"])  # release to allow booking on dev_b if needed

    r = await client.get("/bookings", params={"device_id": dev_a["id"]})
    assert r.status_code == 200
    ids = [b["id"] for b in r.json()]
    assert bk_a["id"] in ids
    assert bk_b["id"] not in ids


async def test_list_bookings_filter_by_username(client):
    """GET /bookings?username=X returns only that user's bookings (line 275)."""
    dev_a = await _make_device(client)
    dev_b = await _make_device(client)

    # "tester" books dev_a
    bk_tester = await _book(client, dev_a["id"], headers=HEADERS)
    # "other-user" books dev_b
    bk_other = await _book(client, dev_b["id"], headers=OTHER_HEADERS)

    r = await client.get("/bookings", params={"username": "tester"})
    assert r.status_code == 200
    ids = [b["id"] for b in r.json()]
    assert bk_tester["id"] in ids
    assert bk_other["id"] not in ids


async def test_list_bookings_filter_active_true(client):
    """GET /bookings?active=true returns only active bookings (line 277)."""
    dev = await _make_device(client)
    bk_active = await _book(client, dev["id"])

    r = await client.get("/bookings", params={"active": "true"})
    assert r.status_code == 200
    assert all(b["active"] for b in r.json())
    ids = [b["id"] for b in r.json()]
    assert bk_active["id"] in ids


async def test_list_bookings_filter_active_false(client):
    """GET /bookings?active=false returns only inactive bookings (line 277)."""
    dev = await _make_device(client)
    bk = await _book(client, dev["id"])
    await _release(client, bk["id"])

    r = await client.get("/bookings", params={"active": "false"})
    assert r.status_code == 200
    assert all(not b["active"] for b in r.json())
    ids = [b["id"] for b in r.json()]
    assert bk["id"] in ids


# ─────────────────────────────────────────────────────────────────────────────
# _call_agent direct test  (lines 41-48)
# ─────────────────────────────────────────────────────────────────────────────

async def test_call_agent_with_token(client):
    """_call_agent sends X-Agent-Token header when a token is provided."""
    from server.routers.bookings import _call_agent

    mc = _silent_agent_mock()
    with patch("server.routers.bookings.httpx.AsyncClient", return_value=mc):
        await _call_agent("http://10.1.1.1:8080", "/ping", agent_token="secret-123")

    mc.request.assert_called_once()
    _, kwargs = mc.request.call_args
    assert kwargs.get("headers", {}).get("X-Agent-Token") == "secret-123"


async def test_call_agent_without_token_no_header(client):
    """_call_agent omits X-Agent-Token header when token is empty."""
    from server.routers.bookings import _call_agent

    mc = _silent_agent_mock()
    with patch("server.routers.bookings.httpx.AsyncClient", return_value=mc):
        await _call_agent("http://10.1.1.1:8080", "/ping", agent_token="")

    mc.request.assert_called_once()
    _, kwargs = mc.request.call_args
    assert "X-Agent-Token" not in kwargs.get("headers", {})


async def test_call_agent_swallows_exception(client):
    """_call_agent silently swallows any exception (lines 47-48)."""
    from server.routers.bookings import _call_agent

    mc = AsyncMock()
    mc.__aenter__ = AsyncMock(return_value=mc)
    mc.__aexit__ = AsyncMock(return_value=False)
    mc.request = AsyncMock(side_effect=ConnectionError("refused"))

    with patch("server.routers.bookings.httpx.AsyncClient", return_value=mc):
        # Must not raise
        await _call_agent("http://10.1.1.1:8080", "/ping")


# ─────────────────────────────────────────────────────────────────────────────
# Additional integration smoke tests
# ─────────────────────────────────────────────────────────────────────────────

async def test_full_booking_lifecycle(client):
    """
    Smoke test covering the full happy path:
    create → book → get_commands → extend → release.
    """
    dev = await _make_device(client,
                              host_ip="10.10.10.10",
                              device_ip="10.10.10.11",
                              jtag_port=3121,
                              ssh_user="root",
                              ssh_port=22)
    # Book
    bk = await _book(client, dev["id"], duration_hours=2)
    assert bk["active"] is True
    assert bk["username"] == "tester"

    # Commands
    r = await client.get(f"/bookings/{bk['id']}/commands", headers=HEADERS)
    assert r.status_code == 200

    # Extend
    r = await client.patch(
        f"/bookings/{bk['id']}/extend",
        json={"hours": 1},
        headers=HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["extended"] is True

    # Release
    r = await client.delete(f"/bookings/{bk['id']}", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["active"] is False

    # Device should now be bookable again
    bk2 = await _book(client, dev["id"], duration_hours=1)
    assert bk2["active"] is True
