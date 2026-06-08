#!/usr/bin/env python3
"""
Seed script — populates a running boardfarm server with realistic test data.

Usage:
  python scripts/seed.py [--url http://localhost:8765] [--token changeme] [--user admin]
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx

# ---------------------------------------------------------------------------
# Sample dataset
# ---------------------------------------------------------------------------

BOARDS = [
    {
        "name": "zynq-dev-1",
        "description": "Xilinx Zynq-7000 SoC dev board, primary FPGA dev target",
        "location": "Lab A / Rack 2 / Slot 1",
        "features": {"jtag": True, "uart": True, "network": "eth0", "fpga": True},
        "jtag_port": 3121,
        "uart_tcp_port": 5555,
        "ssh_user": "root",
        "ssh_port": 22,
        "power_script": "power/usb_relay.py",
        "power_args": {"relay_id": 1},
        "enabled": True,
        "current_notes": "",
    },
    {
        "name": "zynq-dev-2",
        "description": "Xilinx Zynq-7000 SoC dev board, secondary / stress testing",
        "location": "Lab A / Rack 2 / Slot 2",
        "features": {"jtag": True, "uart": True, "network": "eth0", "fpga": True},
        "jtag_port": 3122,
        "uart_tcp_port": 5556,
        "ssh_user": "root",
        "ssh_port": 22,
        "power_script": "power/usb_relay.py",
        "power_args": {"relay_id": 2},
        "enabled": True,
        "current_notes": "Needs power cycle after JTAG disconnect",
    },
    {
        "name": "stm32-nucleo-1",
        "description": "STM32 Nucleo-H743ZI2, ARM Cortex-M7 evaluation board",
        "location": "Lab A / Rack 3 / Slot 1",
        "features": {"jtag": True, "uart": True, "network": False},
        "jtag_port": 3123,
        "uart_tcp_port": 5557,
        "ssh_user": "root",
        "ssh_port": 22,
        "power_script": "power/gpio.py",
        "power_args": {"gpio_pin": 17},
        "enabled": True,
        "current_notes": "",
    },
    {
        "name": "rpi4-test",
        "description": "Raspberry Pi 4 Model B 8GB, general-purpose test node",
        "location": "Lab B / Bench 1",
        "features": {"jtag": False, "uart": True, "network": "eth0", "gpio": True},
        "jtag_port": 0,
        "uart_tcp_port": 5558,
        "ssh_user": "pi",
        "ssh_port": 22,
        "power_script": "power/dummy.py",
        "power_args": {},
        "enabled": True,
        "current_notes": "",
    },
    {
        "name": "ultra96-v2",
        "description": "Avnet Ultra96-V2, Zynq UltraScale+ MPSoC",
        "location": "Lab A / Rack 1 / Slot 3",
        "features": {"jtag": True, "uart": True, "network": "eth0", "fpga": True, "wifi": True},
        "jtag_port": 3124,
        "uart_tcp_port": 5559,
        "ssh_user": "root",
        "ssh_port": 22,
        "power_script": "power/usb_relay.py",
        "power_args": {"relay_id": 4},
        "enabled": True,
        "current_notes": "",
    },
    {
        "name": "arty-a7",
        "description": "Digilent Arty A7-100T, Artix-7 FPGA board",
        "location": "Lab B / Bench 2",
        "features": {"jtag": True, "uart": True, "network": False, "fpga": True},
        "jtag_port": 3125,
        "uart_tcp_port": 5560,
        "ssh_user": "root",
        "ssh_port": 22,
        "power_script": "power/usb_relay.py",
        "power_args": {"relay_id": 5},
        "enabled": False,  # offline board
        "current_notes": "USB JTAG cable broken — awaiting replacement",
    },
]

# (board_name, tool_type, model, connection, connection_detail, notes)
TOOLS = [
    ("zynq-dev-1",   "logic_analyzer", "Saleae Logic 8",        "usb",     "/dev/ttyUSB1",          ""),
    ("zynq-dev-1",   "power_supply",   "Rigol DP832",           "network", "192.168.1.30:5000",     "Ch1=3.3V, Ch2=5V"),
    ("zynq-dev-2",   "logic_analyzer", "Saleae Logic Pro 16",   "usb",     "/dev/ttyUSB2",          ""),
    ("zynq-dev-2",   "oscilloscope",   "Rigol DS1054Z",         "network", "192.168.1.31:5025",     ""),
    ("stm32-nucleo-1","debugger",      "ST-LINK V3",            "usb",     "/dev/ttyACM0",          "On-board debugger"),
    ("rpi4-test",    "power_supply",   "Bench PSU 30V/5A",      "usb",     "/dev/ttyUSB3",          ""),
    ("ultra96-v2",   "logic_analyzer", "Saleae Logic 8",        "usb",     "/dev/ttyUSB4",          ""),
    ("ultra96-v2",   "power_supply",   "Rigol DP711",           "network", "192.168.1.32:5000",     "1-channel 30V/5A"),
    ("arty-a7",      "debugger",       "Digilent JTAG-HS3",     "usb",     "/dev/ttyUSB5",          "Cable broken"),
]

# Past bookings: (board_name, username, hours_ago_start, duration_h, extended, release_reason)
PAST_BOOKINGS = [
    ("zynq-dev-1",    "alice",   48, 4,  False, "manual"),
    ("zynq-dev-1",    "bob",     36, 8,  True,  "manual"),
    ("zynq-dev-1",    "charlie", 20, 2,  False, "expired"),
    ("zynq-dev-2",    "alice",   72, 6,  False, "manual"),
    ("zynq-dev-2",    "dave",    30, 3,  False, "manual"),
    ("stm32-nucleo-1","bob",     96, 12, True,  "manual"),
    ("stm32-nucleo-1","charlie", 50, 5,  False, "expired"),
    ("rpi4-test",     "dave",    24, 2,  False, "manual"),
    ("ultra96-v2",    "alice",   60, 24, True,  "expired"),
    ("arty-a7",       "bob",    120, 4,  False, "admin"),
]

# Active bookings: (board_name, username, started_hours_ago, duration_hours)
ACTIVE_BOOKINGS = [
    ("zynq-dev-1", "alice", 1, 4),
    ("rpi4-test",  "bob",   0.5, 2),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _headers(token: str, user: str) -> dict:
    return {"X-Token": token, "X-User": user}


def _ok(resp: httpx.Response, label: str) -> dict:
    if resp.status_code not in (200, 201):
        print(f"  ERROR {label}: {resp.status_code} {resp.text[:200]}")
        return {}
    return resp.json()


def _dt(hours_ago: float) -> str:
    t = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return t.isoformat()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Seed boardfarm test data")
    parser.add_argument("--url",   default="http://localhost:8765", help="Server base URL")
    parser.add_argument("--token", default="changeme",              help="Server token")
    parser.add_argument("--user",  default="admin",                 help="Username for seed requests")
    parser.add_argument("--clear", action="store_true",             help="Delete existing boards before seeding")
    args = parser.parse_args()

    h = _headers(args.token, args.user)

    with httpx.Client(base_url=args.url, timeout=10) as c:
        # --- health check ---
        try:
            r = c.get("/health")
            r.raise_for_status()
            print(f"Connected to {args.url}  ({r.json()})")
        except Exception as e:
            print(f"Cannot reach server at {args.url}: {e}")
            sys.exit(1)

        # --- optionally clear existing boards ---
        if args.clear:
            existing = _ok(c.get("/boards", headers=h), "list boards")
            for b in existing:
                c.delete(f"/boards/{b['id']}", headers=h)
            print(f"Cleared {len(existing)} existing board(s)")

        # --- create boards ---
        print("\n--- Boards ---")
        board_ids: dict[str, str] = {}   # name → id
        for bd in BOARDS:
            r = c.post("/boards", json=bd, headers=h)
            if r.status_code == 201:
                board_ids[bd["name"]] = r.json()["id"]
                print(f"  + {bd['name']}  ({board_ids[bd['name']]})")
            elif r.status_code == 409:
                # already exists — look it up
                existing = _ok(c.get("/boards", headers=h), "list")
                for b in existing:
                    if b["name"] == bd["name"]:
                        board_ids[bd["name"]] = b["id"]
                print(f"  = {bd['name']} already exists, skipping")
            else:
                print(f"  ERROR creating {bd['name']}: {r.status_code} {r.text[:200]}")

        # --- create tools ---
        print("\n--- Tools ---")
        for (bname, ttype, model, conn, detail, notes) in TOOLS:
            bid = board_ids.get(bname)
            if not bid:
                print(f"  SKIP tool for {bname} (board not created)")
                continue
            r = c.post(f"/boards/{bid}/tools", headers=h, json={
                "type": ttype,
                "model": model,
                "connection": conn,
                "connection_detail": detail,
                "notes": notes,
            })
            if r.status_code == 201:
                print(f"  + {bname}: {ttype} {model}")
            else:
                print(f"  ERROR adding tool to {bname}: {r.status_code}")

        # --- inject past bookings directly into DB via API workaround ---
        # The public API only creates future/current bookings; for historical
        # records we create then immediately release them. We adjust end_time
        # via PATCH if the API supports it, otherwise just release.
        print("\n--- Past bookings ---")
        for (bname, uname, hours_ago, dur, extended, reason) in PAST_BOOKINGS:
            bid = board_ids.get(bname)
            if not bid:
                print(f"  SKIP booking for {bname}")
                continue
            # Book for a short time so it doesn't conflict with active bookings
            bh = _headers(args.token, uname)
            r = c.post(f"/boards/{bid}/book", headers=bh, json={"duration_hours": min(dur, 24)})
            if r.status_code != 201:
                print(f"  SKIP past booking {bname}/{uname}: {r.status_code} {r.text[:100]}")
                continue
            bk = r.json()
            # extend once if needed
            if extended:
                c.patch(f"/bookings/{bk['id']}/extend", headers=bh, json={"hours": 1})
            # release immediately (simulating a past booking)
            rel_h = _headers(args.token, uname if reason != "admin" else args.user)
            c.delete(f"/bookings/{bk['id']}", headers=rel_h)
            print(f"  + {bname}/{uname}  [{reason}]")

        # --- active bookings ---
        print("\n--- Active bookings ---")
        for (bname, uname, _, dur) in ACTIVE_BOOKINGS:
            bid = board_ids.get(bname)
            if not bid:
                print(f"  SKIP active booking for {bname}")
                continue
            bh = _headers(args.token, uname)
            r = c.post(f"/boards/{bid}/book", headers=bh, json={"duration_hours": dur})
            if r.status_code == 201:
                bk = r.json()
                print(f"  + {bname}/{uname}  expires in {dur}h  ({bk['id']})")
            elif r.status_code == 409:
                print(f"  = {bname} already has an active booking, skipping")
            else:
                print(f"  ERROR booking {bname}: {r.status_code} {r.text[:100]}")

        # --- summary ---
        print("\n--- Summary ---")
        boards_out = _ok(c.get("/boards", headers=h), "list") or []
        active = sum(1 for b in boards_out if b.get("active_booking"))
        print(f"  Boards   : {len(boards_out)}")
        print(f"  Active   : {active}")
        bookings_out = _ok(c.get("/bookings", headers=h), "history") or []
        print(f"  Bookings : {len(bookings_out)} total")
        print("\nDone. Start the frontend and point it at", args.url)


if __name__ == "__main__":
    main()
