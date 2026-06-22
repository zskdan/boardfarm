#!/usr/bin/env bash
# Boardfarm agent installer.
#
# Works in two modes:
#
#   Offline tarball (recommended for production):
#     tar xzf boardfarm-agent-YYYYMMDD.tar.gz
#     sudo boardfarm-agent/install.sh
#
#   Repo (development, requires internet):
#     sudo ./agent/install.sh          # from repo root
#
# Installs to /opt/boardfarm/agent/.
# Safe to re-run: existing config.yaml is never overwritten.

set -euo pipefail

INSTALL_DIR="/opt/boardfarm/agent"
SERVICE_USER="boardfarm"
SERVICE_FILE="/etc/systemd/system/boardfarm-agent.service"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Auto-detect layout:
#   tarball: install.sh lives at root, agent/ is a subdirectory
#   repo:    install.sh lives inside agent/, which IS the Python package
if [ -d "$SCRIPT_DIR/agent" ]; then
    AGENT_SRC="$SCRIPT_DIR/agent"
    SCRIPTS_SRC="$SCRIPT_DIR/scripts"
    SERVICE_SRC="$SCRIPT_DIR/boardfarm-agent.service"
    CONFIG_EXAMPLE="$SCRIPT_DIR/config.example.yaml"
    REQUIREMENTS="$SCRIPT_DIR/agent/requirements.txt"
else
    AGENT_SRC="$SCRIPT_DIR"
    SCRIPTS_SRC="$SCRIPT_DIR/scripts"
    SERVICE_SRC="$SCRIPT_DIR/boardfarm-agent.service"
    CONFIG_EXAMPLE="$SCRIPT_DIR/config.example.yaml"
    REQUIREMENTS="$SCRIPT_DIR/requirements.txt"
fi

WHEELS_DIR="$SCRIPT_DIR/wheels"

# ── helpers ───────────────────────────────────────────────────────────────────

info()  { echo "  [+] $*"; }
fatal() { echo "  [!] $*" >&2; exit 1; }

require_root() {
    [ "$(id -u)" -eq 0 ] || fatal "Run as root: sudo $0"
}

require_python() {
    python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,8) else 1)" 2>/dev/null \
        || fatal "Python 3.8+ required (found: $(python3 --version 2>&1))"
}

# ── main ──────────────────────────────────────────────────────────────────────

require_root
require_python

info "Installing boardfarm agent to $INSTALL_DIR"

# System user
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
    info "Created system user '$SERVICE_USER'"
fi
usermod -a -G dialout "$SERVICE_USER" 2>/dev/null || true
usermod -a -G plugdev "$SERVICE_USER" 2>/dev/null || true

# Install directory
mkdir -p "$INSTALL_DIR"

# Python package
info "Copying agent package..."
rm -rf "$INSTALL_DIR/agent"
cp -r "$AGENT_SRC" "$INSTALL_DIR/agent"
find "$INSTALL_DIR/agent" -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true

# Helper scripts
info "Installing helper scripts..."
mkdir -p "$INSTALL_DIR/scripts"
install -m 0755 "$SCRIPTS_SRC/sdcard-manager"  "$INSTALL_DIR/scripts/sdcard-manager"
install -m 0755 "$SCRIPTS_SRC/check-version"   "$INSTALL_DIR/scripts/check-version"
install -m 0755 "$SCRIPTS_SRC/access-control"  "$INSTALL_DIR/scripts/access-control"

# Test scripts
info "Installing test scripts..."
mkdir -p "$INSTALL_DIR/tests"
install -m 0755 "$AGENT_SRC/tests/get-version.sh" "$INSTALL_DIR/tests/get-version.sh"
install -m 0755 "$AGENT_SRC/tests/redeploy.sh"    "$INSTALL_DIR/tests/redeploy.sh"
install -m 0644 "$AGENT_SRC/tests/ref-version.txt" "$INSTALL_DIR/tests/ref-version.txt"

# sudoers — allow the service user to run sdcard-manager as root without a password
info "Installing sudoers rule..."
cat > /etc/sudoers.d/boardfarm-sdcard <<'EOF'
vivado ALL=(root) NOPASSWD: /opt/boardfarm/agent/scripts/sdcard-manager
EOF
chmod 0440 /etc/sudoers.d/boardfarm-sdcard

# Config (never overwrite)
if [ ! -f "$INSTALL_DIR/config.yaml" ]; then
    cp "$CONFIG_EXAMPLE" "$INSTALL_DIR/config.yaml"
    info "Created $INSTALL_DIR/config.yaml — edit before starting the service"
else
    info "Keeping existing $INSTALL_DIR/config.yaml"
fi

# Virtualenv
info "Setting up Python virtualenv..."
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip

if [ -d "$WHEELS_DIR" ]; then
    info "Installing dependencies from bundled wheels (offline)..."
    "$INSTALL_DIR/venv/bin/pip" install --quiet \
        --no-index \
        --find-links "$WHEELS_DIR" \
        -r "$REQUIREMENTS"
else
    info "Installing dependencies from PyPI..."
    "$INSTALL_DIR/venv/bin/pip" install --quiet -r "$REQUIREMENTS"
fi

# Ownership
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

# Systemd service
info "Installing systemd service..."
cp "$SERVICE_SRC" "$SERVICE_FILE"
systemctl daemon-reload
systemctl enable boardfarm-agent

echo ""
echo "Installation complete."
echo ""
echo "  1. Edit $INSTALL_DIR/config.yaml"
echo "  2. Start:   sudo systemctl start boardfarm-agent"
echo "  3. Status:  sudo systemctl status boardfarm-agent"
echo "  4. Logs:    sudo journalctl -u boardfarm-agent -f"
