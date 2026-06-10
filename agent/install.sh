#!/usr/bin/env bash
# Boardfarm agent installer.
# Run as root from the repo root (or from a release tarball root).
#
#   sudo ./agent/install.sh
#
# Installs to /opt/boardfarm/agent/.
# Safe to re-run: existing config.yaml is never overwritten.

set -euo pipefail

INSTALL_DIR="/opt/boardfarm/agent"
SERVICE_USER="boardfarm"
SERVICE_FILE="/etc/systemd/system/boardfarm-agent.service"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── helpers ──────────────────────────────────────────────────────────────────

info()  { echo "  [+] $*"; }
fatal() { echo "  [!] $*" >&2; exit 1; }

require_root() {
    [ "$(id -u)" -eq 0 ] || fatal "Run as root: sudo $0"
}

require_python() {
    python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" 2>/dev/null \
        || fatal "Python 3.11+ required (found: $(python3 --version 2>&1))"
}

# ── main ─────────────────────────────────────────────────────────────────────

require_root
require_python

info "Installing boardfarm agent to $INSTALL_DIR"

# System user
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
    info "Created system user '$SERVICE_USER'"
fi
usermod -a -G dialout "$SERVICE_USER" 2>/dev/null || true   # serial port access
usermod -a -G plugdev "$SERVICE_USER" 2>/dev/null || true   # USB device access

# Install directory
mkdir -p "$INSTALL_DIR"

# Python package
info "Copying agent package..."
rm -rf "$INSTALL_DIR/agent"
cp -r "$SCRIPT_DIR/agent" "$INSTALL_DIR/agent"
find "$INSTALL_DIR/agent" -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true

# Helper scripts (sdcard-acquire / sdcard-release go in INSTALL_DIR so
# sudoers rules and the user-facing sdcard script can reference a stable path)
info "Installing helper scripts..."
install -m 0755 "$SCRIPT_DIR/agent/scripts/sdcard-acquire" "$INSTALL_DIR/sdcard-acquire"
install -m 0755 "$SCRIPT_DIR/agent/scripts/sdcard-release" "$INSTALL_DIR/sdcard-release"

# Config (never overwrite an existing one)
if [ ! -f "$INSTALL_DIR/config.yaml" ]; then
    cp "$SCRIPT_DIR/agent/config.example.yaml" "$INSTALL_DIR/config.yaml"
    info "Created $INSTALL_DIR/config.yaml from example — edit before starting the service"
else
    info "Keeping existing $INSTALL_DIR/config.yaml"
fi

# Virtualenv
info "Setting up Python virtualenv..."
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install --quiet -r "$SCRIPT_DIR/agent/requirements.txt"

# Ownership
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

# Systemd service
info "Installing systemd service..."
cp "$SCRIPT_DIR/agent/boardfarm-agent.service" "$SERVICE_FILE"
systemctl daemon-reload
systemctl enable boardfarm-agent

echo ""
echo "Installation complete."
echo ""
echo "  1. Edit $INSTALL_DIR/config.yaml"
echo "  2. Start the agent:"
echo "       sudo systemctl start boardfarm-agent"
echo "       sudo systemctl status boardfarm-agent"
echo "  3. Follow logs:"
echo "       sudo journalctl -u boardfarm-agent -f"
