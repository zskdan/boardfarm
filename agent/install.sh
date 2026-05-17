#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="/opt/boardfarm"
SERVICE_USER="boardfarm"

echo "Installing boardfarm agent to $INSTALL_DIR"

# Create user if needed
id "$SERVICE_USER" &>/dev/null || useradd --system --no-create-home "$SERVICE_USER"

# Copy files
mkdir -p "$INSTALL_DIR"
cp -r . "$INSTALL_DIR/"
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

# Create venv and install
sudo -u "$SERVICE_USER" python3 -m venv "$INSTALL_DIR/venv"
sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/agent/requirements.txt"

# Add to dialout group for serial port access
usermod -a -G dialout "$SERVICE_USER"

# Install systemd service
cp "$INSTALL_DIR/agent/boardfarm-agent.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable boardfarm-agent
systemctl start boardfarm-agent

echo "Done. Check status with: systemctl status boardfarm-agent"
