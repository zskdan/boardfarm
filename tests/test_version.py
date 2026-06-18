"""Tests for the deployed-version reporting feature.

Covers:
- Server  PATCH /devices/{id}/version endpoint (multi-line payload, auth, truncation)
- Agent   services.version.run_script() returning full stdout
- Script  agent/scripts/get-deployed-version output format (clean / dirty)
"""
from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import textwrap
import uuid
from pathlib import Path

import pytest

from agent.services.version import run_script

AUTH_HEADERS = {"X-Token": "test-token", "X-User": "testuser"}
AGENT_HEADERS = {"X-Token": "test-token"}

SCRIPT_PATH = Path(__file__).parent.parent / "agent" / "scripts" / "get-deployed-version"


# ── helpers ───────────────────────────────────────────────────────────────────

async def _create_device(client) -> dict:
    resp = await client.post(
        "/devices",
        json={
            "name": f"ver-{uuid.uuid4().hex[:6]}",
            "description": "",
            "location": "",
            "features": {},
            "jtag_port": 0,
            "ssh_user": "root",
            "ssh_port": 0,
            "power_script": "",
            "power_args": {},
            "enabled": True,
        },
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 201
    return resp.json()


def _make_script(body: str) -> str:
    """Write body to a temp executable file and return its path."""
    fd, path = tempfile.mkstemp(suffix=".sh")
    os.write(fd, body.encode())
    os.close(fd)
    os.chmod(path, stat.S_IRWXU)
    return path


def _patch_script(dest_dir: Path) -> Path:
    """Copy get-deployed-version to dest_dir with paths substituted for testing."""
    ref = dest_dir / "ref-version.txt"
    get_ver = dest_dir / "get_version.sh"
    current = dest_dir / "current_version.txt"

    text = SCRIPT_PATH.read_text()
    text = text.replace("REF_FILE=/opt/sca/ref-version.txt", f"REF_FILE={ref}")
    text = text.replace("GET_SCRIPT=/opt/sca/get_version.sh", f"GET_SCRIPT={get_ver}")
    text = text.replace("CURRENT_FILE=/tmp/current_version.txt", f"CURRENT_FILE={current}")

    patched = dest_dir / "get-deployed-version"
    patched.write_text(text)
    patched.chmod(0o755)
    return patched


# ── server endpoint tests ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_report_version_single_line(client):
    device = await _create_device(client)
    resp = await client.patch(
        f"/devices/{device['id']}/version",
        json={"version": "a1b2c3d4:clean"},
        headers=AGENT_HEADERS,
    )
    assert resp.status_code == 204

    got = await client.get(f"/devices/{device['id']}", headers=AUTH_HEADERS)
    assert got.json()["deployed_version"] == "a1b2c3d4:clean"


@pytest.mark.asyncio
async def test_report_version_multiline_clean(client):
    device = await _create_device(client)
    payload = "a1b2c3d4:clean\ncomponent1 v1.2.3\ncomponent2 v4.5.6"
    resp = await client.patch(
        f"/devices/{device['id']}/version",
        json={"version": payload},
        headers=AGENT_HEADERS,
    )
    assert resp.status_code == 204

    stored = (await client.get(f"/devices/{device['id']}", headers=AUTH_HEADERS)).json()[
        "deployed_version"
    ]
    assert stored.split("\n")[0] == "a1b2c3d4:clean"
    assert "component1 v1.2.3" in stored
    assert "component2 v4.5.6" in stored


@pytest.mark.asyncio
async def test_report_version_multiline_dirty(client):
    device = await _create_device(client)
    payload = textwrap.dedent("""\
        deadbeef:dirty:cafebabe
        --- /opt/sca/ref-version.txt
        +++ /tmp/current_version.txt
        @@ -1,3 +1,3 @@
         component1 v1.2.3
        -component2 v4.5.6
        +component2 v4.6.0
         component3 v2.1.0""")
    resp = await client.patch(
        f"/devices/{device['id']}/version",
        json={"version": payload},
        headers=AGENT_HEADERS,
    )
    assert resp.status_code == 204

    stored = (await client.get(f"/devices/{device['id']}", headers=AUTH_HEADERS)).json()[
        "deployed_version"
    ]
    assert stored.split("\n")[0] == "deadbeef:dirty:cafebabe"
    assert "-component2 v4.5.6" in stored
    assert "+component2 v4.6.0" in stored


@pytest.mark.asyncio
async def test_report_version_requires_token(client):
    device = await _create_device(client)
    resp = await client.patch(
        f"/devices/{device['id']}/version",
        json={"version": "abc:clean"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_report_version_truncates_at_16384(client):
    device = await _create_device(client)
    resp = await client.patch(
        f"/devices/{device['id']}/version",
        json={"version": "x" * 20_000},
        headers=AGENT_HEADERS,
    )
    assert resp.status_code == 204

    stored = (await client.get(f"/devices/{device['id']}", headers=AUTH_HEADERS)).json()[
        "deployed_version"
    ]
    assert len(stored) == 16_384


# ── agent run_script tests ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_script_returns_full_output():
    script = _make_script("#!/bin/sh\necho 'line1'\necho 'line2'\necho 'line3'\n")
    try:
        result = await run_script(script)
        assert result is not None
        lines = result.split("\n")
        assert lines[0] == "line1"
        assert lines[1] == "line2"
        assert lines[2] == "line3"
    finally:
        os.unlink(script)


@pytest.mark.asyncio
async def test_run_script_multiline_version_format():
    body = textwrap.dedent("""\
        #!/bin/sh
        printf 'a1b2c3d4:clean\\n'
        printf 'component1 v1.2.3\\n'
        printf 'component2 v4.5.6\\n'
    """)
    script = _make_script(body)
    try:
        result = await run_script(script)
        assert result is not None
        assert result.split("\n")[0] == "a1b2c3d4:clean"
        assert "component1 v1.2.3" in result
        assert "component2 v4.5.6" in result
    finally:
        os.unlink(script)


@pytest.mark.asyncio
async def test_run_script_returns_none_on_failure():
    script = _make_script("#!/bin/sh\nexit 1\n")
    try:
        result = await run_script(script)
        assert result is None
    finally:
        os.unlink(script)


@pytest.mark.asyncio
async def test_run_script_returns_none_for_missing_script():
    result = await run_script("/nonexistent/path/version.sh")
    assert result is None


# ── bash script format tests ──────────────────────────────────────────────────

@pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="Script not installed")
def test_script_clean_output():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        content = "component1 v1.2.3\ncomponent2 v4.5.6\n"
        (d / "ref-version.txt").write_text(content)
        get_ver = d / "get_version.sh"
        get_ver.write_text(f"#!/bin/sh\ncat '{d}/ref-version.txt'\n")
        get_ver.chmod(0o755)

        script = _patch_script(d)
        proc = subprocess.run([str(script)], capture_output=True, text=True)
        assert proc.returncode == 0, f"stderr: {proc.stderr}"

        lines = proc.stdout.split("\n")
        first = lines[0]
        parts = first.split(":")
        assert len(parts) == 2, f"Expected '<sha>:clean', got: {first}"
        assert parts[1] == "clean", f"Expected ':clean', got: {first}"
        assert len(parts[0]) == 8, f"Expected 8-char sha, got: {parts[0]}"
        assert "component1 v1.2.3" in proc.stdout
        assert "component2 v4.5.6" in proc.stdout


@pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="Script not installed")
def test_script_dirty_output():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "ref-version.txt").write_text("component1 v1.2.3\ncomponent2 v4.5.6\n")
        get_ver = d / "get_version.sh"
        get_ver.write_text(
            "#!/bin/sh\nprintf 'component1 v1.2.3\\ncomponent2 v4.6.0\\n'\n"
        )
        get_ver.chmod(0o755)

        script = _patch_script(d)
        proc = subprocess.run([str(script)], capture_output=True, text=True)
        assert proc.returncode == 0, f"stderr: {proc.stderr}"

        first = proc.stdout.split("\n")[0]
        parts = first.split(":")
        assert len(parts) == 3, f"Expected '<sha>:dirty:<sha>', got: {first}"
        assert parts[1] == "dirty", f"Expected ':dirty:', got: {first}"
        assert len(parts[0]) == 8
        assert len(parts[2]) == 8
        # Unified diff markers must be present
        assert "-component2 v4.5.6" in proc.stdout
        assert "+component2 v4.6.0" in proc.stdout


@pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="Script not installed")
def test_script_dirty_sha_differs_from_clean():
    """SHA in clean and dirty cases must differ when content differs."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "ref-version.txt").write_text("version 1.0\n")

        # Clean run
        get_ver = d / "get_version.sh"
        get_ver.write_text("#!/bin/sh\nprintf 'version 1.0\\n'\n")
        get_ver.chmod(0o755)
        clean_proc = subprocess.run([str(_patch_script(d))], capture_output=True, text=True)
        clean_sha = clean_proc.stdout.split("\n")[0].split(":")[0]

        # Dirty run
        get_ver.write_text("#!/bin/sh\nprintf 'version 1.1\\n'\n")
        dirty_proc = subprocess.run([str(_patch_script(d))], capture_output=True, text=True)
        parts = dirty_proc.stdout.split("\n")[0].split(":")
        cur_sha, _, ref_sha = parts[0], parts[1], parts[2]

        assert cur_sha != clean_sha, "Current SHA should differ from clean SHA"
        assert ref_sha == clean_sha, "Reference SHA should match the clean SHA"
