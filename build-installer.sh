#!/usr/bin/env bash
# Build a self-contained offline installer for the boardfarm agent.
#
# Run on any machine that has Python 3.11+ and internet access.
# The resulting tarball can be transferred to the target host and
# installed without any network access.
#
#   ./build-installer.sh [--platform PLATFORM]
#
# Options:
#   --platform  pip platform tag for cross-platform wheel download
#               e.g. manylinux2014_x86_64, manylinux2014_aarch64
#               Defaults to the current machine's platform.
#
# Output:
#   boardfarm-agent-YYYYMMDD.tar.gz
#
# On the target host:
#   tar xzf boardfarm-agent-YYYYMMDD.tar.gz
#   sudo boardfarm-agent/install.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
VERSION="$(date +%Y%m%d)"
PACKAGE_NAME="boardfarm-agent-${VERSION}"
OUTPUT="${REPO_ROOT}/${PACKAGE_NAME}.tar.gz"
PLATFORM=""

# ── args ─────────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --platform) PLATFORM="$2"; shift 2 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

# ── build ─────────────────────────────────────────────────────────────────────
STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT

PKG="$STAGING/$PACKAGE_NAME"
mkdir -p "$PKG"

echo "[1/4] Copying agent files..."
cp -r "$REPO_ROOT/agent"                   "$PKG/agent"
cp    "$REPO_ROOT/agent/boardfarm-agent.service" "$PKG/"
cp    "$REPO_ROOT/agent/config.example.yaml"     "$PKG/"

# install.sh lives at the tarball root
cp    "$REPO_ROOT/agent/install.sh"        "$PKG/install.sh"
chmod +x "$PKG/install.sh"

# helper scripts
mkdir -p "$PKG/scripts"
cp "$REPO_ROOT/agent/scripts/sdcard-manager"       "$PKG/scripts/"
cp "$REPO_ROOT/agent/scripts/get-deployed-version" "$PKG/scripts/"
chmod +x "$PKG/scripts/"*

# strip __pycache__
find "$PKG/agent" -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true

echo "[2/4] Downloading Python wheels..."
mkdir -p "$PKG/wheels"

PIP_ARGS=(
    download
    --quiet
    --dest "$PKG/wheels"
    --python-version "3.8"
    --only-binary ":all:"
    -r "$REPO_ROOT/agent/requirements.txt"
)

if [[ -n "$PLATFORM" ]]; then
    PIP_ARGS+=(--platform "$PLATFORM")
fi

pip "${PIP_ARGS[@]}"

# Also grab pip itself so the target can upgrade if needed
pip download --quiet --dest "$PKG/wheels" "pip>=23" --only-binary :all: 2>/dev/null || true

WHEEL_COUNT=$(find "$PKG/wheels" -name '*.whl' | wc -l)
echo "    Downloaded $WHEEL_COUNT wheel(s)"

echo "[3/4] Creating tarball..."
tar czf "$OUTPUT" -C "$STAGING" "$PACKAGE_NAME"

SIZE=$(du -sh "$OUTPUT" | cut -f1)
echo "[4/4] Done."
echo ""
echo "  Package : $OUTPUT ($SIZE)"
echo "  Wheels  : $WHEEL_COUNT bundled"
echo ""
echo "  Transfer to target host, then:"
echo "    tar xzf ${PACKAGE_NAME}.tar.gz"
echo "    sudo ${PACKAGE_NAME}/install.sh"
