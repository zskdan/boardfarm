"""Tests for server/routers/tools.py — targets 100% coverage."""
from __future__ import annotations

import uuid

import pytest

AUTH_HEADERS = {"X-Token": "test-token", "X-User": "tester"}


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


async def _add_tool(client, device_id: str, *, tool_type: str = "jtag", model: str = "J-Link") -> dict:
    payload = {
        "type": tool_type,
        "model": model,
        "connection": "usb",
        "connection_detail": "/dev/ttyUSB0",
        "notes": "test tool",
    }
    resp = await client.post(f"/devices/{device_id}/tools", json=payload, headers=AUTH_HEADERS)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# GET /devices/{id}/tools
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_tools_empty(client):
    device = await _create_device(client)
    resp = await client.get(f"/devices/{device['id']}/tools")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_tools_with_tool(client):
    device = await _create_device(client)
    tool = await _add_tool(client, device["id"])
    resp = await client.get(f"/devices/{device['id']}/tools")
    assert resp.status_code == 200
    tools = resp.json()
    assert any(t["id"] == tool["id"] for t in tools)
    assert tools[0]["type"] == "jtag"
    assert tools[0]["model"] == "J-Link"
    assert tools[0]["connection"] == "usb"


# ---------------------------------------------------------------------------
# POST /devices/{id}/tools
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_tool_success(client):
    device = await _create_device(client)
    resp = await client.post(
        f"/devices/{device['id']}/tools",
        json={
            "type": "logic_analyzer",
            "model": "Saleae Logic 8",
            "connection": "usb",
            "connection_detail": "/dev/ttyUSB1",
            "notes": "8-channel",
        },
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["type"] == "logic_analyzer"
    assert body["model"] == "Saleae Logic 8"
    assert body["device_id"] == device["id"]
    assert "id" in body


@pytest.mark.asyncio
async def test_add_tool_device_not_found(client):
    resp = await client.post(
        "/devices/nonexistent-device/tools",
        json={"type": "jtag", "model": "J-Link"},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 404
    assert "device" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# PATCH /tools/{id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_tool_fields(client):
    device = await _create_device(client)
    tool = await _add_tool(client, device["id"])

    resp = await client.patch(
        f"/tools/{tool['id']}",
        json={
            "type": "power_supply",
            "model": "BK Precision 9130",
            "connection": "ethernet",
            "connection_detail": "192.168.1.50",
            "notes": "updated notes",
        },
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["type"] == "power_supply"
    assert updated["model"] == "BK Precision 9130"
    assert updated["connection"] == "ethernet"
    assert updated["connection_detail"] == "192.168.1.50"
    assert updated["notes"] == "updated notes"
    assert updated["id"] == tool["id"]


@pytest.mark.asyncio
async def test_update_tool_not_found(client):
    resp = await client.patch(
        "/tools/nonexistent-tool-id",
        json={"type": "jtag", "model": "x"},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 404
    assert "tool" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# DELETE /tools/{id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_tool_success(client):
    device = await _create_device(client)
    tool = await _add_tool(client, device["id"])

    resp = await client.delete(f"/tools/{tool['id']}", headers=AUTH_HEADERS)
    assert resp.status_code == 204

    # Verify gone
    list_resp = await client.get(f"/devices/{device['id']}/tools")
    assert not any(t["id"] == tool["id"] for t in list_resp.json())


@pytest.mark.asyncio
async def test_delete_tool_not_found(client):
    resp = await client.delete("/tools/nonexistent-tool-id", headers=AUTH_HEADERS)
    assert resp.status_code == 404
    assert "tool" in resp.json()["detail"].lower()
