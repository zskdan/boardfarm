"""Tests for the deployed-version reporting feature.

Covers:
- Server  PATCH /devices/{id}/version endpoint (multi-line payload, auth, truncation)
- Agent   services.version.run_script() returning full stdout via check-version
- Script  agent/scripts/check-version output format (clean / dirty)
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

from boardfarm_agent.services.version import run_script

AUTH_HEADERS = {"X-Token": "test-token", "X-User": "testuser"}
AGENT_HEADERS = {"X-Token": "test-token"}

SCRIPT_PATH = Path(__file__).parent.parent / "agent" / "scripts" / "check-version"


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
    """Copy check-version to dest_dir with CURRENT_FILE substituted for testing.

    GET_SCRIPT and REF_FILE are now positional arguments, so callers must pass
    them on the command line: subprocess.run([str(script), get_ver, ref_file], ...)
    """
    current = dest_dir / "current_version.txt"
    text = SCRIPT_PATH.read_text()
    text = text.replace("CURRENT_FILE=/tmp/current_version.txt", f"CURRENT_FILE={current}")
    patched = dest_dir / "check-version"
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
# run_script(get_script, ref_file) now calls check-version internally.

@pytest.mark.asyncio
@pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="check-version script not found")
async def test_run_script_returns_full_output():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        content = "line1\nline2\nline3\n"
        ref = d / "ref.txt"
        ref.write_text(content)
        get_ver = d / "get_version.sh"
        get_ver.write_text(f"#!/bin/sh\nprintf 'line1\\nline2\\nline3\\n'\n")
        get_ver.chmod(0o755)
        result = await run_script(str(get_ver), str(ref))
        assert result is not None
        assert "line1" in result
        assert "line2" in result
        assert "line3" in result


@pytest.mark.asyncio
@pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="check-version script not found")
async def test_run_script_multiline_version_format():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        content = "component1 v1.2.3\ncomponent2 v4.5.6\n"
        ref = d / "ref.txt"
        ref.write_text(content)
        get_ver = d / "get_version.sh"
        get_ver.write_text(f"#!/bin/sh\nprintf 'component1 v1.2.3\\ncomponent2 v4.5.6\\n'\n")
        get_ver.chmod(0o755)
        result = await run_script(str(get_ver), str(ref))
        assert result is not None
        assert "component1 v1.2.3" in result
        assert "component2 v4.5.6" in result


@pytest.mark.asyncio
@pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="check-version script not found")
async def test_run_script_returns_none_on_failure():
    get_ver = _make_script("#!/bin/sh\nexit 1\n")
    try:
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            ref = f.name
            f.write(b"dummy\n")
        try:
            result = await run_script(get_ver, ref)
            assert result is None
        finally:
            os.unlink(ref)
    finally:
        os.unlink(get_ver)


@pytest.mark.asyncio
async def test_run_script_returns_none_for_missing_script():
    result = await run_script("/nonexistent/get_version.sh", "/nonexistent/ref.txt")
    assert result is None


# ── bash script format tests ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_report_version_added_line(client):
    """A line present in current but absent from reference shows as +line in stored diff."""
    device = await _create_device(client)
    payload = textwrap.dedent("""\
        b3c4d5e6:dirty:a1b2c3d4
        --- /opt/sca/ref-version.txt
        +++ /tmp/current_version.txt
        @@ -1,5 +1,5 @@
         kernel 6.6.30
        -glibc 2.38
         openssl 3.2.1
         busybox 1.36.1
         python3 3.11.8
        +musl-libc 1.2.5""")
    resp = await client.patch(
        f"/devices/{device['id']}/version",
        json={"version": payload},
        headers=AGENT_HEADERS,
    )
    assert resp.status_code == 204

    stored = (await client.get(f"/devices/{device['id']}", headers=AUTH_HEADERS)).json()[
        "deployed_version"
    ]
    # Added line (pure addition — no preceding - line)
    assert "+musl-libc 1.2.5" in stored
    # Removed line (pure deletion — no following + line)
    assert "-glibc 2.38" in stored
    # glibc must not appear as an addition
    assert "+glibc" not in stored
    # musl must not appear as a deletion
    assert "-musl" not in stored


@pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="Script not installed")
def test_script_line_added_to_current():
    """A line in current that has no counterpart in reference emits a bare +line."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        ref = d / "ref-version.txt"
        ref.write_text("kernel 6.6.30\nopenssl 3.2.1\n")
        get_ver = d / "get_version.sh"
        # current has an extra line at the end
        get_ver.write_text(
            "#!/bin/sh\nprintf 'kernel 6.6.30\\nopenssl 3.2.1\\nmusl-libc 1.2.5\\n'\n"
        )
        get_ver.chmod(0o755)

        script = _patch_script(d)
        proc = subprocess.run([str(script), str(get_ver), str(ref)], capture_output=True, text=True)
        assert proc.returncode == 0
        assert proc.stdout.split("\n")[0].endswith(":dirty:" + proc.stdout.split("\n")[0].split(":")[-1])

        output_lines = proc.stdout.split("\n")
        # The added line must appear with + prefix
        assert any(l == "+musl-libc 1.2.5" for l in output_lines), \
            f"Expected '+musl-libc 1.2.5' in output:\n{proc.stdout}"
        # No corresponding deletion of musl
        assert not any(l == "-musl-libc 1.2.5" for l in output_lines)


@pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="Script not installed")
def test_script_line_removed_from_current():
    """A line in reference that has no counterpart in current emits a bare -line."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        ref = d / "ref-version.txt"
        ref.write_text("kernel 6.6.30\nglibc 2.38\nopenssl 3.2.1\n")
        get_ver = d / "get_version.sh"
        # current is missing glibc
        get_ver.write_text(
            "#!/bin/sh\nprintf 'kernel 6.6.30\\nopenssl 3.2.1\\n'\n"
        )
        get_ver.chmod(0o755)

        script = _patch_script(d)
        proc = subprocess.run([str(script), str(get_ver), str(ref)], capture_output=True, text=True)
        assert proc.returncode == 0

        output_lines = proc.stdout.split("\n")
        # Removed line must appear with - prefix
        assert any(l == "-glibc 2.38" for l in output_lines), \
            f"Expected '-glibc 2.38' in output:\n{proc.stdout}"
        # No corresponding addition of glibc
        assert not any(l == "+glibc 2.38" for l in output_lines)


@pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="Script not installed")
def test_script_mixed_add_remove_change():
    """Combined add, remove, and change all produce correct diff markers."""
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        ref = d / "ref-version.txt"
        ref.write_text(
            "kernel 6.6.30\nglibc 2.38\nopenssl 3.2.1\nbusybox 1.36.1\npython3 3.11.8\n"
        )
        get_ver = d / "get_version.sh"
        # glibc removed, openssl version changed, musl-libc added
        get_ver.write_text(
            "#!/bin/sh\nprintf 'kernel 6.6.30\\nopenssl 3.3.0\\nbusybox 1.36.1\\npython3 3.11.8\\nmusl-libc 1.2.5\\n'\n"
        )
        get_ver.chmod(0o755)

        script = _patch_script(d)
        proc = subprocess.run([str(script), str(get_ver), str(ref)], capture_output=True, text=True)
        assert proc.returncode == 0
        lines = proc.stdout.split("\n")

        # removed: glibc
        assert any(l == "-glibc 2.38" for l in lines)
        assert not any(l == "+glibc 2.38" for l in lines)
        # changed: openssl (both - and + must be present)
        assert any(l == "-openssl 3.2.1" for l in lines)
        assert any(l == "+openssl 3.3.0" for l in lines)
        # added: musl-libc
        assert any(l == "+musl-libc 1.2.5" for l in lines)
        assert not any(l == "-musl-libc 1.2.5" for l in lines)


@pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="Script not installed")
def test_script_clean_output():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        content = "component1 v1.2.3\ncomponent2 v4.5.6\n"
        ref = d / "ref-version.txt"
        ref.write_text(content)
        get_ver = d / "get_version.sh"
        get_ver.write_text(f"#!/bin/sh\ncat '{ref}'\n")
        get_ver.chmod(0o755)

        script = _patch_script(d)
        proc = subprocess.run([str(script), str(get_ver), str(ref)], capture_output=True, text=True)
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
        ref = d / "ref-version.txt"
        ref.write_text("component1 v1.2.3\ncomponent2 v4.5.6\n")
        get_ver = d / "get_version.sh"
        get_ver.write_text(
            "#!/bin/sh\nprintf 'component1 v1.2.3\\ncomponent2 v4.6.0\\n'\n"
        )
        get_ver.chmod(0o755)

        script = _patch_script(d)
        proc = subprocess.run([str(script), str(get_ver), str(ref)], capture_output=True, text=True)
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
        ref = d / "ref-version.txt"
        ref.write_text("version 1.0\n")

        # Clean run
        get_ver = d / "get_version.sh"
        get_ver.write_text("#!/bin/sh\nprintf 'version 1.0\\n'\n")
        get_ver.chmod(0o755)
        script = _patch_script(d)
        clean_proc = subprocess.run([str(script), str(get_ver), str(ref)], capture_output=True, text=True)
        clean_sha = clean_proc.stdout.split("\n")[0].split(":")[0]

        # Dirty run
        get_ver.write_text("#!/bin/sh\nprintf 'version 1.1\\n'\n")
        dirty_proc = subprocess.run([str(script), str(get_ver), str(ref)], capture_output=True, text=True)
        parts = dirty_proc.stdout.split("\n")[0].split(":")
        cur_sha, _, ref_sha = parts[0], parts[1], parts[2]

        assert cur_sha != clean_sha, "Current SHA should differ from clean SHA"
        assert ref_sha == clean_sha, "Reference SHA should match the clean SHA"
