# Boardfarm

A development device booking and inventory system for shared hardware labs. Teams register physical devices (FPGAs, microcontrollers, SoCs, instruments) in a central server, book them by username, and get ready-to-run shell commands for SSH, UART, JTAG, and power control.

## Architecture

```
┌─────────────┐     REST/HTTP      ┌───────────────────────────┐
│  Frontend   │ ─────────────────> │  Server (central)         │
│ (React SPA) │                    │  - Device inventory       │
└─────────────┘                    │  - Booking history        │
                                   │  - Setup groups           │
                                   │  - Agent registry         │
                                   └───────────┬───────────────┘
                                               │ REST/HTTP
                                    ┌──────────┴──────────┐
                                    │  Agent(s)           │
                                    │  (per device-host)  │
                                    │  - hw_server JTAG   │
                                    │  - socat UART proxy │
                                    │  - Power control    │
                                    └─────────────────────┘
```

## Repository layout

| Path | Description |
|------|-------------|
| `server/` | Central inventory & booking API (FastAPI, SQLite) |
| `agent/` | Hardware agent per device-host PC (FastAPI + mDNS) |
| `agent/scripts/` | Server-side helper scripts installed to `/opt/boardfarm/agent/` |
| `power/` | Power control scripts (USB relay, GPIO, dummy) |
| `frontend/` | React + Vite SPA |
| `user-scripts/` | Client-side helper scripts (`uart-connect`, `sdcard`) |
| `build-installer.sh` | Builds a self-contained offline agent installer tarball |

---

## Quick Start

### Docker Compose (recommended)

```bash
cp server/config.example.yaml server/config.yaml
docker compose up --build
```

| Container  | Port | Description |
|------------|------|-------------|
| `server`   | 8765 | FastAPI booking API |
| `frontend` | 80   | Nginx serving the React SPA |

Open `http://localhost` and enter `http://localhost:8765` as the server URL.

The SQLite database is stored in a named volume (`boardfarm_data`) and persists across restarts.

```bash
docker compose up -d --build      # background
docker compose logs -f server     # follow server logs
docker compose down               # stop
docker compose down -v            # stop + delete DB
```

---

### Manual setup

#### Server

```bash
cd server
pip install -r requirements.txt
cp config.example.yaml config.yaml
uvicorn server.main:app --port 8765
```

Key `config.yaml` options:

```yaml
server:
  token: ""              # empty = no token required (fine for internal labs)
  max_booking_hours: 24  # N = cap in hours, null = unlimited, 0 = never expires
  default_user: null     # username pre-filled in every form (null = none)
  admin_users:           # can release any booking and delete any device
    - "admin"
```

#### Agent (on the host PC wired to devices)

The agent needs direct access to USB/serial devices — run it natively, not in Docker.

**Production install (offline, recommended)**

Build the installer on any machine that has Python and internet access:

```bash
./build-installer.sh
# → boardfarm-agent-YYYYMMDD.tar.gz

# Cross-architecture (e.g. building for an ARM host from an x86 machine):
./build-installer.sh --platform manylinux2014_aarch64
```

Transfer the tarball to the target host (USB, SCP, etc.), then:

```bash
tar xzf boardfarm-agent-YYYYMMDD.tar.gz
sudo boardfarm-agent/install.sh
# Edit /opt/boardfarm/agent/config.yaml
sudo systemctl start boardfarm-agent
sudo journalctl -u boardfarm-agent -f
```

The installer creates a `boardfarm` system user, installs a Python virtualenv with all dependencies from the bundled wheels (no internet needed on the target), copies `sdcard-acquire` / `sdcard-release` to `/opt/boardfarm/agent/`, and registers a systemd service.

**Development (requires internet)**

```bash
cd agent
pip install -r requirements.txt
cp config.example.yaml config.yaml
# Edit: server_url, server_token, host_ip, device IDs
uvicorn agent.main:app --port 8766
```

#### Frontend (dev server)

```bash
cd frontend
npm install
npm run dev
# Open http://localhost:5173 and enter the server URL
```

---

## Agent config (`/opt/boardfarm/agent/config.yaml`)

Edit this file before starting the service. A template is created automatically by the installer at `/opt/boardfarm/agent/config.yaml`.

```yaml
agent:
  name: "lab-host-1"
  port: 8766
  server_url: "http://192.168.1.100:8765"
  server_token: ""           # match server/config.yaml token
  agent_token: ""            # token agents use to authenticate with server
  host_ip: "192.168.1.5"    # this machine's LAN IP (used by clients to reach JTAG/UART)

devices:
  - id: "paste-device-uuid-here"   # copy from the server's device detail page
    usb_device: "/dev/bus/usb/001/002"  # raw USB device (optional)
    uart_device: "/dev/ttyUSB0"         # UART serial device (optional)
    jtag_port: 3121                     # hw_server listen port (optional)
    power_script: "/opt/boardfarm/agent/power/usb_relay.py"
    power_args:
      relay_id: 1
```

After editing, apply with:

```bash
sudo systemctl restart boardfarm-agent
```

---

## User scripts (`user-scripts/`)

Client-side helpers for developers. Copy or symlink them into your `PATH`.

### `uart-connect`

Bridges a device's UART (on the agent host) to a local PTY via SSH.

```bash
uart-connect vivado@<agent_ip> <uart_device> <device_id>

# Example (values shown on the device detail page):
uart-connect vivado@192.168.1.5 /dev/ttyUSB0 DEV-A3F9C1
screen /dev/ttyDEV-A3F9C1
```

### `sdcard`

Mounts or unmounts a device's SD card locally via `sshfs`. Requires `sshfs` on the client.

```bash
sdcard vivado@<agent_ip> <device_id> open|close

# Example:
sdcard vivado@192.168.1.5 DEV-A3F9C1 open
# → SD card available at ~/sdcard-DEV-A3F9C1

sdcard vivado@192.168.1.5 DEV-A3F9C1 close
```

The device detail page also offers a **Script** download button for both commands, pre-filled with the correct agent IP and device ID.

---

## Power control scripts

Scripts in `power/` share a CLI: `python3 script.py --action on|off|reset`.

| Script | Hardware |
|--------|----------|
| `dummy.py` | No-op (for testing) |
| `usb_relay.py` | USB HID relay board (`--relay-id N`) |
| `gpio.py` | Raspberry Pi GPIO (`--gpio-pin N`) |

Custom controllers: subclass `power.base.PowerController`.

---

## Screenshots

| Inventory | Setups |
|-----------|--------|
| ![Inventory page showing device list with status badges](screenshots/inventory.png) | ![Setups page with atomic booking cards](screenshots/setups.png) |

| Device detail (shell commands) | Booking history |
|-------------------------------|----------------|
| ![Device detail with SSH/UART/JTAG shell commands](screenshots/device-detail.png) | ![History page with audit log](screenshots/history.png) |

| Settings | Add Setup (device picker) |
|----------|--------------------------|
| ![Settings modal for server URL and username](screenshots/settings-modal.png) | ![Add setup modal with searchable device picker](screenshots/add-setup-modal.png) |

| Book Setup modal | Add device (agent section expanded) |
|-----------------|-------------------------------------|
| ![Book setup modal with duration and comment](screenshots/book-setup-modal.png) | ![Add device modal with agent section expanded showing USB, UART, JTAG and Power Control](screenshots/add-device-modal-agent.png) |

---

## Using the UI

> **No login required.** You supply your username when performing an action (book, release, add). A default username is stored locally in the browser and pre-filled in every form.

### Inventory (`/devices`)

Lists every registered device with live status:

- **Status badge** — Free (green), Booked (blue), Offline (amber), Disabled (grey)
- **Device ID** — server-assigned unique identifier (e.g. `DEV-A3F9C1`), shown as a monospace badge next to the device name
- **Booked by** — current holder's username and booking comment
- **Location** — physical rack/bench location
- **Features** — colour-coded badges for device capabilities (e.g. `jtag: true`, `fpga: zynq-7020`)
- **Actions** — Book · Release · Modify

The **Filter** box searches by device name, device ID, location, username, or feature key.

**Add Device** form sections, all collapsed by default:

- **Ethernet** — reveals Device IP, then SSH sub-checkbox (on by default):
  - **SSH** — reveals SSH User (default `root`), SSH Port (default `22`)
- **Hardware agent** — reveals Agent Host IP and capability sub-checkboxes (all off by default). Enabling any sub-checkbox automatically adds the matching key to the device's Features map:
  - **USB** — reveals USB device path (e.g. `/dev/bus/usb/001/002`)
  - **UART** — reveals UART device path (e.g. `/dev/ttyUSB0`)
  - **JTAG** — reveals JTAG Port (default `3121`)
  - **Power Control** — reveals Power Script, Power Script Args
  - **SDMux** — reveals SDMux control device (default `/dev/sg0`) and SD card path
  - **Access Control** — reveals Access Control device path (e.g. `/dev/ttyACM0`)

### Device detail (`/devices/:id`)

Each device has a detail page with:

- **Hardware info** — device ID, serial number, PCB revision, location, IP addresses, USB device path, agent status
- **Features** — arbitrary key/value capability map (e.g. `jtag: true`)
- **Connectivity** — ready-to-run shell commands, each in its own terminal block with a **Copy** button:

  | Service | Command |
  |---------|---------|
  | SSH | `$ ssh -J vivado@<agent_ip> root@<device_ip> -p <port>` (checkbox toggles the `-J` jump host; on by default when an agent is present) |
  | UART | `$ sudo socat pty,link=/dev/ttyDEV-XXXX,rawer EXEC:"ssh vivado@<agent_ip> socat - /dev/ttyUSB0,rawer"` |
  | JTAG | `$ connect_hw_server -url tcp:<agent_ip>:<jtag_port>` |
  | Power | `$ python3 <power_script> --action on` |

- **Notes** — freeform notes, editable inline
- **Booking** — book / extend / release with a live countdown timer

The **SD Card** entry provides a downloadable helper script that calls `sdcard-acquire` / `sdcard-release` from `/opt/boardfarm/agent/` on the agent host and mounts the card locally via `sshfs`.

### Setups (`/setups`)

Groups of devices that are always used together (e.g. "FPGA + logic analyzer + test host").

- **Book atomically** — all devices in a setup are reserved in a single transaction. If any device is already taken the whole booking fails, with a message listing which devices are blocked and by whom.
- **Release atomically** — releases all devices in the setup at once.
- **Device picker** — searchable by name, device ID, or location. Selected devices appear as removable chips so the list stays short at scale.
- Each setup card shows a per-device availability dot: green = free and online, blue = booked, grey = offline.

### Booking history (`/history`)

Full audit log of all actions: bookings, releases, extensions, device creates/updates/deletes. Each entry records the device name and its auto-assigned device ID, so records stay meaningful after renames.

Filter by user or action category (Bookings / Device changes).

---

## API reference

### Authentication

| Request | `X-User` | `X-Token` |
|---------|----------|-----------|
| `GET` (read) | not required | not required |
| `POST` / `PATCH` / `DELETE` (write) | **required** | required only if `token` is set in config |

### Server endpoints (`http://server:8765`)

**Devices**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/devices` | List all devices with live status |
| GET | `/devices/{id}` | Device detail + active booking |
| POST | `/devices` | Add device (`device_id` is auto-assigned by server) |
| PATCH | `/devices/{id}` | Update device metadata |
| DELETE | `/devices/{id}` | Remove device (fails if actively booked) |

**Bookings**

| Method | Path | Description |
|--------|------|-------------|
| POST | `/devices/{id}/book` | Book a single device `{duration_hours, comment}` |
| DELETE | `/bookings/{id}` | Release booking (admin can release any) |
| PATCH | `/bookings/{id}/extend` | Extend by N hours (once per booking) |
| GET | `/bookings/{id}/commands` | SSH / UART / JTAG / power command strings |
| GET | `/bookings` | Booking history (`device_id`, `username`, `active`, `limit`) |

**Setups**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/setups` | List all setups with device availability |
| POST | `/setups` | Create setup `{name, description, device_ids}` |
| PATCH | `/setups/{id}` | Update name / description / device list |
| DELETE | `/setups/{id}` | Delete setup (fails if actively booked) |
| POST | `/setups/{id}/book` | Book all devices atomically `{duration_hours, comment}` |
| DELETE | `/setups/{id}/booking` | Release all devices in the setup |

**Agents & activity**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/agents` | List registered agents (online / offline) |
| POST | `/agents/register` | Agent startup registration |
| POST | `/agents/heartbeat` | Agent keep-alive (every 30 s) |
| GET | `/activity` | Audit log (`device_ref`, `username`, `action`, `limit`) |
| GET | `/health` | Liveness check + server config |

### Agent endpoints (`http://agent:8766`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness + version |
| GET | `/devices` | Devices managed by this agent |
| POST | `/devices/{id}/services/start` | Start hw_server + UART proxy |
| POST | `/devices/{id}/services/stop` | Stop services |
| POST | `/devices/{id}/power` | Power action `{action: on\|off\|reset}` |

---

## Device fields

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | Stable across agent changes |
| `device_id` | string | Auto-assigned by server on creation (e.g. `DEV-A3F9C1`) |
| `name` | string | Human-readable name, unique |
| `serial_number` | string | Hardware serial (optional) |
| `revision` | string | PCB revision (optional) |
| `description` | string | Free text |
| `location` | string | Physical location (e.g. `Lab A / Rack 3 / Slot 1`) |
| `device_ip` | string | Device's own IP address (SSH target) |
| `host_ip` | string | IP of the agent's host PC (JTAG / UART / power) |
| `ssh_user` / `ssh_port` | string / int | SSH access (default `root` / `22`) |
| `usb_device` | string | Raw USB device path on agent host (e.g. `/dev/bus/usb/001/002`) |
| `uart_device` | string | UART serial device path on agent host (e.g. `/dev/ttyUSB0`) |
| `jtag_port` | int | hw_server port (default `3121`) |
| `power_script` | string | Path to power control script |
| `sdmux_control` | string | SDMux control device path on agent host (e.g. `/dev/sg0`) |
| `sdmux_sdcard` | string | SD card block device path (e.g. `/dev/disk/by-path/...`) |
| `access_control` | string | Access control device path on agent host (e.g. `/dev/ttyACM0`) |
| `features` | JSON | Arbitrary key/value capability map; auto-populated from enabled hardware options |
| `enabled` | bool | Disabled devices cannot be booked |
