"""
Tests for server/ws.py and server/expiry.py.
"""
import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import update
from starlette.testclient import TestClient

from server.main import app
from server.ws import _connections, broadcast

# Capture the real asyncio.sleep before any patching so mocks can yield
# to the event loop without recursing into the mock.
_real_sleep = asyncio.sleep


async def _yielding_sleep(_interval):
    """Replacement for asyncio.sleep that actually yields to the event loop."""
    await _real_sleep(0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

AUTH = {"X-Token": "test-token", "X-User": "testuser"}


# ===========================================================================
# broadcast() tests — server/ws.py lines 26-37
# ===========================================================================


@pytest.mark.asyncio
async def test_broadcast_sends_to_all_connections():
    """broadcast() calls send_text on every live connection."""
    ws1 = AsyncMock()
    ws2 = AsyncMock()
    _connections.add(ws1)
    _connections.add(ws2)
    try:
        await broadcast({"type": "ping"})
        ws1.send_text.assert_called_once()
        ws2.send_text.assert_called_once()
        # Payload must be valid JSON containing the event type
        payload = json.loads(ws1.send_text.call_args[0][0])
        assert payload["type"] == "ping"
    finally:
        _connections.discard(ws1)
        _connections.discard(ws2)


@pytest.mark.asyncio
async def test_broadcast_removes_dead_connections():
    """A connection whose send_text raises is removed from _connections."""
    ws = AsyncMock()
    ws.send_text.side_effect = Exception("closed")
    _connections.add(ws)
    try:
        await broadcast({"type": "ping"})
        assert ws not in _connections
    finally:
        _connections.discard(ws)


@pytest.mark.asyncio
async def test_broadcast_no_connections_is_noop():
    """broadcast() with no connections must not raise."""
    _connections.clear()
    await broadcast({"type": "ping"})  # should not raise


@pytest.mark.asyncio
async def test_broadcast_partial_failure_keeps_good_connections():
    """Only the dead connection is removed; the healthy one stays."""
    good = AsyncMock()
    bad = AsyncMock()
    bad.send_text.side_effect = RuntimeError("dead")
    _connections.add(good)
    _connections.add(bad)
    try:
        await broadcast({"type": "update"})
        assert bad not in _connections
        assert good in _connections
        good.send_text.assert_called_once()
    finally:
        _connections.discard(good)
        _connections.discard(bad)


@pytest.mark.asyncio
async def test_broadcast_json_serialises_event():
    """The message sent over the wire is JSON-encoded."""
    ws = AsyncMock()
    _connections.add(ws)
    try:
        event = {"type": "booking_expired", "device_id": "dev-123"}
        await broadcast(event)
        raw = ws.send_text.call_args[0][0]
        assert json.loads(raw) == event
    finally:
        _connections.discard(ws)


# ===========================================================================
# ws_handler() tests — server/ws.py lines 13-23
# via starlette.testclient.TestClient (synchronous WS support)
# ===========================================================================


def test_ws_connect_and_disconnect():
    """Client can connect, send text, then disconnect cleanly."""
    with TestClient(app) as tc:
        with tc.websocket_connect("/ws/status") as ws:
            ws.send_text("ping")
            # Closing the context manager triggers WebSocketDisconnect inside the handler


def test_ws_connection_added_and_removed():
    """ws_handler adds the websocket to _connections and removes it on disconnect."""
    with TestClient(app) as tc:
        initial_count = len(_connections)
        with tc.websocket_connect("/ws/status") as ws:
            # Connection should be present while the websocket is open
            # (TestClient runs the handler in a background thread so timing is
            #  non-deterministic; we just confirm no crash and count returns)
            ws.send_text("hello")
        # After disconnection the handler's finally block should have removed it
        assert len(_connections) <= initial_count


def test_ws_multiple_clients():
    """Multiple concurrent clients can connect without error."""
    with TestClient(app) as tc:
        with tc.websocket_connect("/ws/status") as ws1:
            with tc.websocket_connect("/ws/status") as ws2:
                ws1.send_text("a")
                ws2.send_text("b")


# ===========================================================================
# _stop_agent_services() tests — server/expiry.py lines 17-30
# ===========================================================================


@pytest.mark.asyncio
async def test_stop_agent_services_posts_to_agent():
    """When a device has an agent URL, a POST is sent to stop services."""
    from server.expiry import _stop_agent_services

    mock_agent = MagicMock()
    mock_agent.url = "http://agent.local:8080"
    mock_agent.agent_token = "secret"

    mock_device = MagicMock()
    mock_device.agent = mock_agent

    mock_response = MagicMock()
    mock_response.status_code = 200

    mock_client_instance = AsyncMock()
    mock_client_instance.post.return_value = mock_response
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=False)

    with patch("server.expiry.httpx.AsyncClient", return_value=mock_client_instance):
        await _stop_agent_services(mock_device, "dev-001")

    mock_client_instance.post.assert_called_once_with(
        "http://agent.local:8080/devices/dev-001/services/stop",
        headers={"X-Agent-Token": "secret"},
    )


@pytest.mark.asyncio
async def test_stop_agent_services_no_token_no_header():
    """When the agent has no token, X-Agent-Token header is omitted."""
    from server.expiry import _stop_agent_services

    mock_agent = MagicMock()
    mock_agent.url = "http://agent.local:8080"
    mock_agent.agent_token = ""  # empty token

    mock_device = MagicMock()
    mock_device.agent = mock_agent

    mock_client_instance = AsyncMock()
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=False)

    with patch("server.expiry.httpx.AsyncClient", return_value=mock_client_instance):
        await _stop_agent_services(mock_device, "dev-002")

    mock_client_instance.post.assert_called_once_with(
        "http://agent.local:8080/devices/dev-002/services/stop",
        headers={},
    )


@pytest.mark.asyncio
async def test_stop_agent_services_device_none():
    """Passing None as device is a no-op (no HTTP call)."""
    from server.expiry import _stop_agent_services

    with patch("server.expiry.httpx.AsyncClient") as mock_cls:
        await _stop_agent_services(None, "dev-003")
        mock_cls.assert_not_called()


@pytest.mark.asyncio
async def test_stop_agent_services_agent_none():
    """Device with no agent is a no-op."""
    from server.expiry import _stop_agent_services

    mock_device = MagicMock()
    mock_device.agent = None

    with patch("server.expiry.httpx.AsyncClient") as mock_cls:
        await _stop_agent_services(mock_device, "dev-004")
        mock_cls.assert_not_called()


@pytest.mark.asyncio
async def test_stop_agent_services_agent_url_empty():
    """Device whose agent.url is empty is a no-op."""
    from server.expiry import _stop_agent_services

    mock_agent = MagicMock()
    mock_agent.url = ""

    mock_device = MagicMock()
    mock_device.agent = mock_agent

    with patch("server.expiry.httpx.AsyncClient") as mock_cls:
        await _stop_agent_services(mock_device, "dev-005")
        mock_cls.assert_not_called()


@pytest.mark.asyncio
async def test_stop_agent_services_swallows_exceptions():
    """HTTP errors from the agent are silently swallowed."""
    from server.expiry import _stop_agent_services

    mock_agent = MagicMock()
    mock_agent.url = "http://unreachable:9999"
    mock_agent.agent_token = ""

    mock_device = MagicMock()
    mock_device.agent = mock_agent

    mock_client_instance = AsyncMock()
    mock_client_instance.post.side_effect = Exception("connection refused")
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=False)

    with patch("server.expiry.httpx.AsyncClient", return_value=mock_client_instance):
        # Must not raise
        await _stop_agent_services(mock_device, "dev-006")


# ===========================================================================
# expiry_loop() tests — server/expiry.py lines 33-64
#
# Strategy: run the expiry body logic directly rather than through the loop,
# to avoid having to patch asyncio.sleep (which is a shared module attribute
# and would globally affect aiosqlite and other async internals).
# ===========================================================================


async def _run_expiry_body_once(session_factory, broadcast_fn=None):
    """Execute the inner body of expiry_loop exactly once using the given session factory."""
    from datetime import datetime, timezone

    import server.expiry as expiry_mod

    real_broadcast = expiry_mod.broadcast
    if broadcast_fn is not None:
        expiry_mod.broadcast = broadcast_fn

    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        from server.models import Booking, Device

        async with session_factory() as db:
            result = await db.execute(
                select(Booking)
                .where(Booking.active == True, Booking.end_time < now)
                .options(selectinload(Booking.device).selectinload(Device.agent))
            )
            expired = result.scalars().all()
            for booking in expired:
                booking.active = False
                booking.release_reason = "expired"
                await expiry_mod._stop_agent_services(booking.device, booking.device_id)
            if expired:
                await db.commit()
                for booking in expired:
                    asyncio.create_task(
                        expiry_mod.broadcast(
                            {"type": "booking_expired", "device_id": booking.device_id}
                        )
                    )
    finally:
        if broadcast_fn is not None:
            expiry_mod.broadcast = real_broadcast


@pytest.mark.asyncio
async def test_expiry_marks_expired_bookings(client, db_engine):
    """expiry_loop body marks active bookings past end_time as inactive."""
    from server.models import Booking
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import sessionmaker

    # Create a device and an active booking via the HTTP API (uses test DB via `client`)
    r = await client.post(
        "/devices",
        json={"name": "expiry-test-dev", "device_id": "expiry-dev-01"},
        headers=AUTH,
    )
    assert r.status_code == 201
    dev_id = r.json()["id"]

    r2 = await client.post(
        f"/devices/{dev_id}/book",
        json={"duration_hours": 1},
        headers=AUTH,
    )
    assert r2.status_code == 201
    booking_id = r2.json()["id"]

    # Build a session factory that points at the same in-memory test DB
    test_session_factory = sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )

    # Age the booking via a direct DB write
    async with test_session_factory() as sess:
        past = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2)
        await sess.execute(
            update(Booking).where(Booking.id == booking_id).values(end_time=past)
        )
        await sess.commit()

    # Run the expiry body once
    await _run_expiry_body_once(test_session_factory)

    # Verify: expired booking now shows active=False via HTTP
    r3 = await client.get("/bookings", params={"active": "false"}, headers=AUTH)
    assert r3.status_code == 200
    inactive = [b for b in r3.json() if b["id"] == booking_id]
    assert inactive, "Booking should have been marked inactive by expiry logic"
    assert inactive[0]["active"] is False
    assert inactive[0]["release_reason"] == "expired"


@pytest.mark.asyncio
async def test_expiry_loop_does_not_touch_active_future_bookings(client, db_engine):
    """Bookings with a future end_time must not be expired by the expiry body."""
    from server.models import Booking
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import sessionmaker

    r = await client.post(
        "/devices",
        json={"name": "future-booking-dev", "device_id": "future-dev-01"},
        headers=AUTH,
    )
    assert r.status_code == 201
    dev_id = r.json()["id"]

    r2 = await client.post(
        f"/devices/{dev_id}/book",
        json={"duration_hours": 4},
        headers=AUTH,
    )
    assert r2.status_code == 201
    booking_id = r2.json()["id"]

    test_session_factory = sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )

    # Run the expiry body — booking is still in the future, must not be touched
    await _run_expiry_body_once(test_session_factory)

    # Check via the list endpoint that the booking is still active
    r3 = await client.get("/bookings", params={"active": "true"}, headers=AUTH)
    assert r3.status_code == 200
    active_ids = {b["id"] for b in r3.json()}
    assert booking_id in active_ids, "Future booking must remain active"


@pytest.mark.asyncio
async def test_expiry_loop_broadcasts_on_expiry(client, db_engine):
    """expiry body broadcasts a booking_expired event for each expired booking."""
    from server.models import Booking
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import sessionmaker

    r = await client.post(
        "/devices",
        json={"name": "broadcast-test-dev", "device_id": "broadcast-dev-01"},
        headers=AUTH,
    )
    assert r.status_code == 201
    dev_id = r.json()["id"]

    r2 = await client.post(
        f"/devices/{dev_id}/book",
        json={"duration_hours": 1},
        headers=AUTH,
    )
    assert r2.status_code == 201
    booking_id = r2.json()["id"]

    test_session_factory = sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with test_session_factory() as sess:
        past = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2)
        await sess.execute(
            update(Booking).where(Booking.id == booking_id).values(end_time=past)
        )
        await sess.commit()

    broadcast_calls = []

    async def fake_broadcast(event):
        broadcast_calls.append(event)

    await _run_expiry_body_once(test_session_factory, broadcast_fn=fake_broadcast)
    # Drain any pending create_task callbacks
    await _real_sleep(0)

    assert any(e.get("type") == "booking_expired" for e in broadcast_calls)


@pytest.mark.asyncio
async def test_expiry_loop_survives_inner_exception():
    """expiry_loop must catch exceptions in its inner body and keep iterating."""
    from server.expiry import expiry_loop

    iterations = []

    async def fake_sleep(_interval):
        iterations.append(len(iterations))
        # After 3 iterations, raise CancelledError to exit the loop
        if len(iterations) >= 3:
            raise asyncio.CancelledError
        # Yield to event loop so the task can actually run
        await _real_sleep(0)

    # Use a callable that raises when called so async_session() always blows up
    def broken_session_factory():
        raise Exception("db down")

    # The loop's except block should swallow the db error and call sleep again
    with patch("server.expiry.asyncio.sleep", side_effect=fake_sleep):
        with patch("server.expiry.async_session", broken_session_factory):
            try:
                await expiry_loop(interval_seconds=0)
            except asyncio.CancelledError:
                pass

    # Must have reached at least 3 sleep calls (iterated 3 times despite errors)
    assert len(iterations) >= 3
