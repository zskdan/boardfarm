"""
Tests that run against the pre-seeded dataset (seeded_client fixture).
"""

import pytest
from tests.dataset import ALICE, BOB, ADMIN, AUTH


@pytest.mark.asyncio
async def test_seeded_boards_present(seeded_client):
    r = await seeded_client.get("/boards", headers=AUTH)
    assert r.status_code == 200
    names = {b["name"] for b in r.json()}
    assert {"zynq-dev-1", "stm32-nucleo-1", "arty-a7"} == names


@pytest.mark.asyncio
async def test_disabled_board_in_inventory(seeded_client):
    r = await seeded_client.get("/boards", headers=AUTH)
    arty = next(b for b in r.json() if b["name"] == "arty-a7")
    assert arty["enabled"] is False


@pytest.mark.asyncio
async def test_tools_attached_to_board(seeded_client):
    bid = seeded_client.board_ids["zynq-dev-1"]
    r = await seeded_client.get(f"/boards/{bid}", headers=AUTH)
    tools = r.json()["tools"]
    types = {t["type"] for t in tools}
    assert "logic_analyzer" in types
    assert "power_supply" in types


@pytest.mark.asyncio
async def test_active_booking_visible(seeded_client):
    bid = seeded_client.board_ids["zynq-dev-1"]
    r = await seeded_client.get(f"/boards/{bid}", headers=AUTH)
    booking = r.json()["active_booking"]
    assert booking is not None
    assert booking["username"] == "alice"


@pytest.mark.asyncio
async def test_booking_history_contains_past_entries(seeded_client):
    r = await seeded_client.get("/bookings", headers=AUTH)
    assert r.status_code == 200
    all_ids = {b["id"] for b in r.json()}
    for past_id in seeded_client.booking_ids:
        assert past_id in all_ids


@pytest.mark.asyncio
async def test_free_board_can_be_booked(seeded_client):
    bid = seeded_client.board_ids["stm32-nucleo-1"]
    r = await seeded_client.post(
        f"/boards/{bid}/book", json={"duration_hours": 1}, headers=BOB
    )
    assert r.status_code == 201
    assert r.json()["username"] == "bob"


@pytest.mark.asyncio
async def test_admin_can_release_any_booking(seeded_client):
    booking_id = seeded_client.active_booking["id"]
    r = await seeded_client.delete(f"/bookings/{booking_id}", headers=ADMIN)
    assert r.status_code == 200
    assert r.json()["release_reason"] == "admin"


@pytest.mark.asyncio
async def test_connection_commands_for_active_booking(seeded_client):
    booking_id = seeded_client.active_booking["id"]
    r = await seeded_client.get(f"/bookings/{booking_id}/commands", headers=ALICE)
    assert r.status_code == 200
    cmds = r.json()
    assert "ssh" in cmds
    assert "uart" in cmds
