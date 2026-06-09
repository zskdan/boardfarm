"""
Reusable pytest fixtures providing a pre-seeded dataset.

Import the fixtures you need in your test file:

    from tests.dataset import seeded_client, board_ids, active_booking

Or simply use them as pytest fixtures (conftest auto-collects this module
if you add `pytest_plugins = ["tests.dataset"]` to conftest.py).
"""

from datetime import datetime, timedelta, timezone
import uuid
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from server.database import Base, get_db
from server.main import app
from server.config import settings

AUTH = {"X-Token": "test-token", "X-User": "testuser"}
ALICE = {"X-Token": "test-token", "X-User": "alice"}
BOB   = {"X-Token": "test-token", "X-User": "bob"}
ADMIN = {"X-Token": "test-token", "X-User": "admin"}


# ---------------------------------------------------------------------------
# Board definitions
# ---------------------------------------------------------------------------

BOARD_DEFS = [
    {
        "name": "zynq-dev-1",
        "description": "Xilinx Zynq-7000 SoC dev board",
        "location": "Lab A / Rack 2 / Slot 1",
        "features": {"jtag": True, "uart": True, "network": "eth0"},
        "jtag_port": 3121,
        "ssh_user": "root", "ssh_port": 22,
        "power_script": "power/usb_relay.py", "power_args": {"relay_id": 1},
        "enabled": True, "current_notes": "",
    },
    {
        "name": "stm32-nucleo-1",
        "description": "STM32 Nucleo-H743ZI2 ARM Cortex-M7",
        "location": "Lab A / Rack 3 / Slot 1",
        "features": {"jtag": True, "uart": True},
        "jtag_port": 3123,
        "ssh_user": "root", "ssh_port": 22,
        "power_script": "power/gpio.py", "power_args": {"gpio_pin": 17},
        "enabled": True, "current_notes": "",
    },
    {
        "name": "arty-a7",
        "description": "Digilent Arty A7-100T Artix-7 FPGA",
        "location": "Lab B / Bench 2",
        "features": {"jtag": True, "uart": True},
        "jtag_port": 3125,
        "ssh_user": "root", "ssh_port": 22,
        "power_script": "power/usb_relay.py", "power_args": {"relay_id": 5},
        "enabled": False,  # offline / disabled board
        "current_notes": "USB JTAG cable broken",
    },
]

TOOL_DEFS = [
    # (board_name, type, model, connection, connection_detail)
    ("zynq-dev-1", "logic_analyzer", "Saleae Logic 8",   "usb",     "/dev/ttyUSB1"),
    ("zynq-dev-1", "power_supply",   "Rigol DP832",       "network", "192.168.1.30:5000"),
    ("stm32-nucleo-1", "debugger",   "ST-LINK V3",        "usb",     "/dev/ttyACM0"),
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def seeded_db_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded_client(seeded_db_engine):
    """
    HTTP test client with pre-seeded boards, tools, and booking history.

    Attributes injected on the client object for convenience:
      client.board_ids   — dict[name → id]
      client.tool_ids    — dict[(board_name, model) → id]
      client.booking_ids — list of released booking IDs (history)
    """
    factory = sessionmaker(seeded_db_engine, class_=AsyncSession, expire_on_commit=False)

    async def _get_db():
        async with factory() as s:
            yield s

    app.dependency_overrides[get_db] = _get_db
    original_token = settings.token
    settings.token = "test-token"
    settings.admin_users = ["admin"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        board_ids: dict[str, str] = {}
        tool_ids: dict[tuple, str] = {}
        booking_ids: list[str] = []

        # Create boards
        for bd in BOARD_DEFS:
            r = await ac.post("/boards", json=bd, headers=AUTH)
            assert r.status_code == 201, f"board create failed: {r.text}"
            board_ids[bd["name"]] = r.json()["id"]

        # Create tools
        for (bname, ttype, model, conn, detail) in TOOL_DEFS:
            r = await ac.post(f"/boards/{board_ids[bname]}/tools", headers=AUTH, json={
                "type": ttype, "model": model,
                "connection": conn, "connection_detail": detail, "notes": "",
            })
            assert r.status_code == 201
            tool_ids[(bname, model)] = r.json()["id"]

        # Past booking: alice booked zynq-dev-1, already released
        r = await ac.post(f"/boards/{board_ids['zynq-dev-1']}/book",
                          json={"duration_hours": 3}, headers=ALICE)
        assert r.status_code == 201
        bk = r.json()
        booking_ids.append(bk["id"])
        await ac.delete(f"/bookings/{bk['id']}", headers=ALICE)

        # Past booking: bob booked stm32-nucleo-1, extended, then released
        r = await ac.post(f"/boards/{board_ids['stm32-nucleo-1']}/book",
                          json={"duration_hours": 4}, headers=BOB)
        assert r.status_code == 201
        bk = r.json()
        booking_ids.append(bk["id"])
        await ac.patch(f"/bookings/{bk['id']}/extend", json={"hours": 2}, headers=BOB)
        await ac.delete(f"/bookings/{bk['id']}", headers=BOB)

        # Active booking: alice has zynq-dev-1 right now
        r = await ac.post(f"/boards/{board_ids['zynq-dev-1']}/book",
                          json={"duration_hours": 2}, headers=ALICE)
        assert r.status_code == 201
        active_booking = r.json()

        ac.board_ids = board_ids
        ac.tool_ids = tool_ids
        ac.booking_ids = booking_ids
        ac.active_booking = active_booking

        yield ac

    app.dependency_overrides.clear()
    settings.token = original_token
