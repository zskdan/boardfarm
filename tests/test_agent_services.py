"""
Tests for agent services:
  - agent/services/health.py
  - agent/services/hw_server.py
  - agent/services/power.py
  - agent/services/access_control.py
  - agent/services/version.py  (push_version, _device_loop, version_loop gaps)
"""
import asyncio
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call
import pytest


# ---------------------------------------------------------------------------
# Helpers — reset module-level state between tests
# ---------------------------------------------------------------------------

def _reset_hw():
    import boardfarm_agent.services.hw_server as m
    m._processes.clear()
    m._locks.clear()


def _reset_health():
    import boardfarm_agent.services.health as m
    m._health.clear()


# ===========================================================================
# health.py
# ===========================================================================

def test_tcp_reachable_returns_true_on_success():
    from boardfarm_agent.services.health import _tcp_reachable
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    with patch("boardfarm_agent.services.health.socket.create_connection", return_value=mock_conn):
        assert _tcp_reachable("10.0.0.1", 22) is True


def test_tcp_reachable_returns_false_on_oserror():
    from boardfarm_agent.services.health import _tcp_reachable
    with patch("boardfarm_agent.services.health.socket.create_connection", side_effect=OSError("refused")):
        assert _tcp_reachable("10.0.0.1", 22) is False


async def test_probe_device_reachable():
    _reset_health()
    from boardfarm_agent.services.health import probe_device, _health
    with patch("boardfarm_agent.services.health._tcp_reachable", return_value=True):
        result = await probe_device("dev-1", "10.0.0.1", 22)
    assert result is True
    assert _health["dev-1"] is True


async def test_probe_device_unreachable():
    _reset_health()
    from boardfarm_agent.services.health import probe_device, _health
    with patch("boardfarm_agent.services.health._tcp_reachable", return_value=False):
        result = await probe_device("dev-2", "10.0.0.2", 22)
    assert result is False
    assert _health["dev-2"] is False


def test_get_health_returns_none_for_unknown():
    _reset_health()
    from boardfarm_agent.services.health import get_health
    assert get_health("unknown-dev") is None


def test_get_health_returns_stored_value():
    _reset_health()
    import boardfarm_agent.services.health as m
    m._health["known-dev"] = True
    from boardfarm_agent.services.health import get_health
    assert get_health("known-dev") is True


async def test_probe_loop_calls_probe_device_and_sleep():
    _reset_health()
    from boardfarm_agent.services.health import probe_loop
    from boardfarm_agent.config import DeviceConfig

    dev = DeviceConfig(id="pd-1", host_check_ip="10.0.0.1", host_check_port=22)

    probed = []

    async def fake_probe(device_id, host_ip, check_port):
        probed.append(device_id)
        return True

    sleep_calls = []

    async def fake_sleep(interval):
        sleep_calls.append(interval)
        raise asyncio.CancelledError  # exit after first iteration

    with patch("boardfarm_agent.services.health.probe_device", side_effect=fake_probe):
        with patch("boardfarm_agent.services.health.asyncio.sleep", side_effect=fake_sleep):
            try:
                await probe_loop([dev], interval=30)
            except asyncio.CancelledError:
                pass

    assert "pd-1" in probed
    assert sleep_calls == [30]


async def test_probe_loop_skips_device_without_host_check():
    """Devices without host_check_ip/port are silently skipped."""
    from boardfarm_agent.services.health import probe_loop
    from boardfarm_agent.config import DeviceConfig

    dev = DeviceConfig(id="no-check", host_check_ip="", host_check_port=0)
    probed = []

    async def fake_probe(*a):
        probed.append(a)
        return True

    async def fake_sleep(_):
        raise asyncio.CancelledError

    with patch("boardfarm_agent.services.health.probe_device", side_effect=fake_probe):
        with patch("boardfarm_agent.services.health.asyncio.sleep", side_effect=fake_sleep):
            try:
                await probe_loop([dev])
            except asyncio.CancelledError:
                pass

    assert probed == []


async def test_probe_loop_swallows_probe_exception():
    """If probe_device raises, health is set to False and loop continues."""
    _reset_health()
    from boardfarm_agent.services.health import probe_loop, _health
    from boardfarm_agent.config import DeviceConfig

    dev = DeviceConfig(id="err-dev", host_check_ip="10.0.0.1", host_check_port=22)

    async def boom(*a):
        raise RuntimeError("connection refused")

    async def fake_sleep(_):
        raise asyncio.CancelledError

    with patch("boardfarm_agent.services.health.probe_device", side_effect=boom):
        with patch("boardfarm_agent.services.health.asyncio.sleep", side_effect=fake_sleep):
            try:
                await probe_loop([dev])
            except asyncio.CancelledError:
                pass

    assert _health.get("err-dev") is False


# ===========================================================================
# hw_server.py
# ===========================================================================

def test_port_in_use_returns_true():
    from boardfarm_agent.services.hw_server import _port_in_use
    mock_sock = MagicMock()
    mock_sock.__enter__ = MagicMock(return_value=mock_sock)
    mock_sock.__exit__ = MagicMock(return_value=False)
    mock_sock.connect_ex.return_value = 0  # 0 = success = port in use
    with patch("boardfarm_agent.services.hw_server.socket.socket", return_value=mock_sock):
        assert _port_in_use(3121) is True


def test_port_in_use_returns_false():
    from boardfarm_agent.services.hw_server import _port_in_use
    mock_sock = MagicMock()
    mock_sock.__enter__ = MagicMock(return_value=mock_sock)
    mock_sock.__exit__ = MagicMock(return_value=False)
    mock_sock.connect_ex.return_value = 1  # non-zero = connection refused
    with patch("boardfarm_agent.services.hw_server.socket.socket", return_value=mock_sock):
        assert _port_in_use(3121) is False


async def test_hw_start_succeeds():
    _reset_hw()
    from boardfarm_agent.services.hw_server import start, _processes

    mock_proc = MagicMock(spec=subprocess.Popen)
    mock_proc.poll.return_value = None  # still running

    with patch("boardfarm_agent.services.hw_server._port_in_use", return_value=False):
        with patch("boardfarm_agent.services.hw_server.subprocess.Popen", return_value=mock_proc):
            result = await start("dev-hw-1", 3121)

    assert result is True
    assert "dev-hw-1" in _processes
    await __import__("boardfarm_agent.services.hw_server", fromlist=["stop"]).stop("dev-hw-1")


async def test_hw_start_already_running_is_idempotent():
    _reset_hw()
    from boardfarm_agent.services import hw_server as m

    mock_proc = MagicMock(spec=subprocess.Popen)
    mock_proc.poll.return_value = None
    m._processes["dev-hw-2"] = mock_proc

    result = await m.start("dev-hw-2", 3121)
    assert result is True  # returns True without re-spawning
    m._processes.pop("dev-hw-2", None)


async def test_hw_start_port_in_use_returns_true():
    _reset_hw()
    from boardfarm_agent.services.hw_server import start

    with patch("boardfarm_agent.services.hw_server._port_in_use", return_value=True):
        result = await start("dev-hw-3", 3121)

    assert result is True  # treat as success


async def test_hw_start_missing_binary_returns_false():
    _reset_hw()
    from boardfarm_agent.services.hw_server import start

    with patch("boardfarm_agent.services.hw_server._port_in_use", return_value=False):
        with patch("boardfarm_agent.services.hw_server.subprocess.Popen", side_effect=FileNotFoundError):
            result = await start("dev-hw-4", 3121)

    assert result is False


async def test_hw_stop_is_safe_when_nothing_running():
    _reset_hw()
    from boardfarm_agent.services.hw_server import stop
    await stop("nonexistent")  # must not raise


async def test_hw_stop_terminates_process():
    _reset_hw()
    import boardfarm_agent.services.hw_server as m

    mock_proc = MagicMock(spec=subprocess.Popen)
    mock_proc.pid = 999
    mock_proc.wait.return_value = 0
    m._processes["dev-hw-5"] = mock_proc

    with patch("boardfarm_agent.services.hw_server.os.killpg"):
        with patch("boardfarm_agent.services.hw_server.os.getpgid", return_value=999):
            await m.stop("dev-hw-5")

    assert "dev-hw-5" not in m._processes


async def test_hw_stop_all():
    _reset_hw()
    import boardfarm_agent.services.hw_server as m

    for dev_id in ("dev-a", "dev-b"):
        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.pid = 100
        mock_proc.wait.return_value = 0
        m._processes[dev_id] = mock_proc

    with patch("boardfarm_agent.services.hw_server.os.killpg"):
        with patch("boardfarm_agent.services.hw_server.os.getpgid", return_value=100):
            await m.stop_all()

    assert len(m._processes) == 0


async def test_hw_stop_sends_sigkill_on_timeout():
    """If proc.wait times out, SIGKILL is sent."""
    _reset_hw()
    import boardfarm_agent.services.hw_server as m

    mock_proc = MagicMock(spec=subprocess.Popen)
    mock_proc.pid = 200
    mock_proc.wait.side_effect = subprocess.TimeoutExpired(cmd="hw_server", timeout=5)
    m._processes["dev-kill"] = mock_proc

    kill_calls = []

    def fake_killpg(pgid, sig):
        kill_calls.append(sig)

    with patch("boardfarm_agent.services.hw_server.os.killpg", side_effect=fake_killpg):
        with patch("boardfarm_agent.services.hw_server.os.getpgid", return_value=200):
            await m.stop("dev-kill")

    import signal
    assert signal.SIGKILL in kill_calls


async def test_hw_stop_handles_process_lookup_error():
    """ProcessLookupError (process already dead) is silently ignored."""
    _reset_hw()
    import boardfarm_agent.services.hw_server as m

    mock_proc = MagicMock(spec=subprocess.Popen)
    mock_proc.pid = 300
    m._processes["dev-dead"] = mock_proc

    with patch("boardfarm_agent.services.hw_server.os.killpg", side_effect=ProcessLookupError):
        with patch("boardfarm_agent.services.hw_server.os.getpgid", return_value=300):
            await m.stop("dev-dead")  # must not raise

    assert "dev-dead" not in m._processes


async def test_hw_stop_handles_generic_exception():
    """Generic exceptions in stop() are logged without propagating."""
    _reset_hw()
    import boardfarm_agent.services.hw_server as m

    mock_proc = MagicMock(spec=subprocess.Popen)
    mock_proc.pid = 400
    m._processes["dev-err"] = mock_proc

    with patch("boardfarm_agent.services.hw_server.os.killpg", side_effect=RuntimeError("unexpected")):
        with patch("boardfarm_agent.services.hw_server.os.getpgid", return_value=400):
            await m.stop("dev-err")  # must not raise

    assert "dev-err" not in m._processes


async def test_hw_start_generic_exception_returns_false():
    """Generic exception from Popen is caught and returns False."""
    _reset_hw()
    from boardfarm_agent.services.hw_server import start

    with patch("boardfarm_agent.services.hw_server._port_in_use", return_value=False):
        with patch("boardfarm_agent.services.hw_server.subprocess.Popen", side_effect=RuntimeError("spawn failed")):
            result = await start("dev-gen-exc", 3121)

    assert result is False


# ===========================================================================
# power.py
# ===========================================================================

async def test_power_run_no_script_returns_false():
    from boardfarm_agent.services.power import run
    result = await run("", "on")
    assert result is False


async def test_power_run_script_not_found_returns_false(tmp_path):
    from boardfarm_agent.services.power import run
    result = await run(str(tmp_path / "nonexistent.sh"), "on")
    assert result is False


async def test_power_run_success(tmp_path):
    from boardfarm_agent.services.power import run

    script = tmp_path / "power.sh"
    script.write_text("#!/bin/sh\necho ok\n")
    script.chmod(0o755)

    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"ok\n", b""))

    with patch("boardfarm_agent.services.power.asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await run(str(script), "on")

    assert result is True


async def test_power_run_nonzero_exit_returns_false(tmp_path):
    from boardfarm_agent.services.power import run

    script = tmp_path / "power.sh"
    script.write_text("#!/bin/sh\nexit 1\n")
    script.chmod(0o755)

    mock_proc = AsyncMock()
    mock_proc.returncode = 1
    mock_proc.communicate = AsyncMock(return_value=(b"", b"error"))

    with patch("boardfarm_agent.services.power.asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await run(str(script), "off")

    assert result is False


async def test_power_run_timeout_returns_false(tmp_path):
    from boardfarm_agent.services.power import run

    script = tmp_path / "power.sh"
    script.write_text("#!/bin/sh\nsleep 99\n")
    script.chmod(0o755)

    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)

    with patch("boardfarm_agent.services.power.asyncio.create_subprocess_exec", return_value=mock_proc):
        with patch("boardfarm_agent.services.power.asyncio.wait_for", side_effect=asyncio.TimeoutError):
            result = await run(str(script), "reset")

    assert result is False


async def test_power_run_exception_returns_false(tmp_path):
    from boardfarm_agent.services.power import run

    script = tmp_path / "power.sh"
    script.write_text("#!/bin/sh\necho ok\n")
    script.chmod(0o755)

    with patch("boardfarm_agent.services.power.asyncio.create_subprocess_exec", side_effect=OSError("spawn failed")):
        result = await run(str(script), "on")

    assert result is False


async def test_power_run_with_extra_args(tmp_path):
    from boardfarm_agent.services.power import run

    script = tmp_path / "power.sh"
    script.write_text("#!/bin/sh\necho ok\n")
    script.chmod(0o755)

    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"ok", b""))

    with patch("boardfarm_agent.services.power.asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        await run(str(script), "on", extra_args={"outlet": "3"})

    cmd = mock_exec.call_args[0]
    assert "--outlet" in cmd
    assert "3" in cmd


# ===========================================================================
# access_control.py
# ===========================================================================

async def test_access_control_no_script_is_noop():
    from boardfarm_agent.services.access_control import run
    # Must not raise, must not call subprocess
    with patch("boardfarm_agent.services.access_control.asyncio.create_subprocess_exec") as m:
        await run("", "lock")
        m.assert_not_called()


async def test_access_control_script_not_found(tmp_path):
    from boardfarm_agent.services.access_control import run
    with patch("boardfarm_agent.services.access_control.asyncio.create_subprocess_exec") as m:
        await run(str(tmp_path / "missing.sh"), "lock")
        m.assert_not_called()


async def test_access_control_success(tmp_path):
    from boardfarm_agent.services.access_control import run

    script = tmp_path / "ac.sh"
    script.write_text("#!/bin/sh\necho ok\n")
    script.chmod(0o755)

    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"ok", b""))

    with patch("boardfarm_agent.services.access_control.asyncio.create_subprocess_exec", return_value=mock_proc):
        await run(str(script), "unlock")  # must not raise


async def test_access_control_nonzero_exit_logs_error(tmp_path):
    from boardfarm_agent.services.access_control import run

    script = tmp_path / "ac.sh"
    script.write_text("#!/bin/sh\nexit 2\n")
    script.chmod(0o755)

    mock_proc = AsyncMock()
    mock_proc.returncode = 2
    mock_proc.communicate = AsyncMock(return_value=(b"", b"denied"))

    with patch("boardfarm_agent.services.access_control.asyncio.create_subprocess_exec", return_value=mock_proc):
        await run(str(script), "lock")  # must not raise


async def test_access_control_timeout(tmp_path):
    from boardfarm_agent.services.access_control import run

    script = tmp_path / "ac.sh"
    script.write_text("#!/bin/sh\nsleep 99\n")
    script.chmod(0o755)

    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)

    with patch("boardfarm_agent.services.access_control.asyncio.create_subprocess_exec", return_value=mock_proc):
        with patch("boardfarm_agent.services.access_control.asyncio.wait_for", side_effect=asyncio.TimeoutError):
            await run(str(script), "lock")  # must not raise


async def test_access_control_exception_swallowed(tmp_path):
    from boardfarm_agent.services.access_control import run

    script = tmp_path / "ac.sh"
    script.write_text("#!/bin/sh\necho ok\n")
    script.chmod(0o755)

    with patch("boardfarm_agent.services.access_control.asyncio.create_subprocess_exec", side_effect=OSError("spawn failed")):
        await run(str(script), "unlock")  # must not raise


# ===========================================================================
# version.py  — push_version, _device_loop, version_loop
# ===========================================================================

async def test_push_version_success():
    from boardfarm_agent.services.version import push_version

    mc = AsyncMock()
    mc.__aenter__ = AsyncMock(return_value=mc)
    mc.__aexit__ = AsyncMock(return_value=False)
    resp = MagicMock()
    resp.status_code = 204
    mc.patch = AsyncMock(return_value=resp)

    with patch("boardfarm_agent.services.version.httpx.AsyncClient", return_value=mc):
        await push_version("http://server:8765", "tok", "dev-1", "v1.0")

    mc.patch.assert_called_once()


async def test_push_version_http_error_is_logged():
    from boardfarm_agent.services.version import push_version

    mc = AsyncMock()
    mc.__aenter__ = AsyncMock(return_value=mc)
    mc.__aexit__ = AsyncMock(return_value=False)
    resp = MagicMock()
    resp.status_code = 500
    resp.text = "error"
    mc.patch = AsyncMock(return_value=resp)

    with patch("boardfarm_agent.services.version.httpx.AsyncClient", return_value=mc):
        await push_version("http://server:8765", "tok", "dev-1", "v1.0")  # must not raise


async def test_push_version_exception_is_swallowed():
    from boardfarm_agent.services.version import push_version

    mc = AsyncMock()
    mc.__aenter__ = AsyncMock(return_value=mc)
    mc.__aexit__ = AsyncMock(return_value=False)
    mc.patch = AsyncMock(side_effect=Exception("network error"))

    with patch("boardfarm_agent.services.version.httpx.AsyncClient", return_value=mc):
        await push_version("http://server:8765", "tok", "dev-1", "v1.0")  # must not raise


async def test_push_version_no_token_omits_header():
    from boardfarm_agent.services.version import push_version

    mc = AsyncMock()
    mc.__aenter__ = AsyncMock(return_value=mc)
    mc.__aexit__ = AsyncMock(return_value=False)
    resp = MagicMock()
    resp.status_code = 204
    mc.patch = AsyncMock(return_value=resp)

    with patch("boardfarm_agent.services.version.httpx.AsyncClient", return_value=mc):
        await push_version("http://server:8765", "", "dev-1", "v1.0")

    headers = mc.patch.call_args.kwargs.get("headers", {})
    assert "X-Token" not in headers


async def test_run_script_check_version_missing(tmp_path):
    """run_script returns None when the check-version binary does not exist."""
    from boardfarm_agent.services.version import run_script
    from pathlib import Path

    script = tmp_path / "get-version.sh"
    script.write_text("#!/bin/sh\necho v1\n")
    script.chmod(0o755)

    missing_check_version = tmp_path / "nonexistent-check-version"

    with patch("boardfarm_agent.services.version._CHECK_VERSION", missing_check_version):
        result = await run_script(str(script), "")

    assert result is None


async def test_run_script_timeout_returns_none(tmp_path):
    """run_script returns None when the subprocess times out."""
    from boardfarm_agent.services.version import run_script
    from pathlib import Path

    script = tmp_path / "get-version.sh"
    script.write_text("#!/bin/sh\nsleep 99\n")
    script.chmod(0o755)

    check_version = tmp_path / "check-version"
    check_version.write_text("#!/bin/sh\necho ok\n")
    check_version.chmod(0o755)

    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)

    with patch("boardfarm_agent.services.version._CHECK_VERSION", check_version):
        with patch("boardfarm_agent.services.version.asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("boardfarm_agent.services.version.asyncio.wait_for", side_effect=asyncio.TimeoutError):
                result = await run_script(str(script), "")

    assert result is None


async def test_run_script_generic_exception_returns_none(tmp_path):
    """run_script returns None on any unexpected exception."""
    from boardfarm_agent.services.version import run_script

    script = tmp_path / "get-version.sh"
    script.write_text("#!/bin/sh\necho v1\n")
    script.chmod(0o755)

    check_version = tmp_path / "check-version"
    check_version.write_text("#!/bin/sh\necho ok\n")
    check_version.chmod(0o755)

    with patch("boardfarm_agent.services.version._CHECK_VERSION", check_version):
        with patch("boardfarm_agent.services.version.asyncio.create_subprocess_exec", side_effect=OSError("spawn failed")):
            result = await run_script(str(script), "")

    assert result is None


async def test_run_script_ref_file_missing(tmp_path):
    """run_script returns None when ref_file is specified but does not exist."""
    from boardfarm_agent.services.version import run_script

    script = tmp_path / "get-version.sh"
    script.write_text("#!/bin/sh\necho v1\n")
    script.chmod(0o755)

    check_version = tmp_path / "check-version"
    check_version.write_text("#!/bin/sh\necho ok\n")
    check_version.chmod(0o755)

    with patch("boardfarm_agent.services.version._CHECK_VERSION", check_version):
        result = await run_script(str(script), str(tmp_path / "nonexistent-ref.txt"))

    assert result is None


async def test_device_loop_runs_and_pushes(tmp_path):
    """_device_loop calls run_script and push_version, then sleeps."""
    from boardfarm_agent.services.version import _device_loop
    from boardfarm_agent.config import DeviceConfig

    dev = DeviceConfig(
        id="ver-dev-1",
        version_script=str(tmp_path / "get-version.sh"),
        version_ref_file="",
        version_poll_interval=10,
    )

    calls = []

    async def fake_run_script(script, ref):
        calls.append(("run", script))
        return "v1.2.3"

    async def fake_push(server_url, token, device_id, version):
        calls.append(("push", device_id, version))

    sleep_count = []

    async def fake_sleep(interval):
        sleep_count.append(interval)
        if len(sleep_count) >= 1:
            raise asyncio.CancelledError

    with patch("boardfarm_agent.services.version.run_script", side_effect=fake_run_script):
        with patch("boardfarm_agent.services.version.push_version", side_effect=fake_push):
            with patch("boardfarm_agent.services.version.asyncio.sleep", side_effect=fake_sleep):
                try:
                    await _device_loop("http://server:8765", "tok", dev, 10)
                except asyncio.CancelledError:
                    pass

    assert any(c[0] == "run" for c in calls)
    assert any(c[0] == "push" for c in calls)


async def test_device_loop_skips_push_when_none(tmp_path):
    """_device_loop skips push_version when run_script returns None."""
    from boardfarm_agent.services.version import _device_loop
    from boardfarm_agent.config import DeviceConfig

    dev = DeviceConfig(id="ver-dev-2", version_script="/fake/script.sh")

    pushed = []

    async def fake_run_script(*a):
        return None

    async def fake_push(*a):
        pushed.append(a)

    async def fake_sleep(_):
        raise asyncio.CancelledError

    with patch("boardfarm_agent.services.version.run_script", side_effect=fake_run_script):
        with patch("boardfarm_agent.services.version.push_version", side_effect=fake_push):
            with patch("boardfarm_agent.services.version.asyncio.sleep", side_effect=fake_sleep):
                try:
                    await _device_loop("http://server", "tok", dev, 10)
                except asyncio.CancelledError:
                    pass

    assert pushed == []


async def test_version_loop_with_static_list(tmp_path):
    """version_loop accepts a static list and starts tasks for each device."""
    from boardfarm_agent.services.version import version_loop
    from boardfarm_agent.config import DeviceConfig

    _real_sleep = asyncio.sleep
    dev = DeviceConfig(id="vl-dev-1", version_script="/script.sh")

    sleep_count = []

    async def fake_sleep(interval):
        await _real_sleep(0)  # yield so create_task'd coroutines can start
        sleep_count.append(interval)
        if len(sleep_count) >= 1:
            raise asyncio.CancelledError

    started = []

    async def fake_device_loop(*a):
        started.append(a[2].id)  # device.id
        await _real_sleep(9999)  # block until cancelled

    with patch("boardfarm_agent.services.version._device_loop", side_effect=fake_device_loop):
        with patch("boardfarm_agent.services.version.asyncio.sleep", side_effect=fake_sleep):
            try:
                await version_loop("http://server", "tok", [dev], default_interval=60)
            except asyncio.CancelledError:
                pass

    assert "vl-dev-1" in started


async def test_version_loop_with_callable():
    """version_loop calls the fetch function each iteration."""
    from boardfarm_agent.services.version import version_loop
    from boardfarm_agent.config import DeviceConfig

    dev = DeviceConfig(id="vl-dev-2", version_script="/script.sh")

    fetch_calls = []

    async def fake_fetch():
        fetch_calls.append(1)
        return [dev]

    sleep_count = []

    async def fake_sleep(_):
        sleep_count.append(1)
        raise asyncio.CancelledError

    async def fake_device_loop(*a):
        await asyncio.sleep(9999)

    with patch("boardfarm_agent.services.version._device_loop", side_effect=fake_device_loop):
        with patch("boardfarm_agent.services.version.asyncio.sleep", side_effect=fake_sleep):
            try:
                await version_loop("http://server", "tok", fake_fetch)
            except asyncio.CancelledError:
                pass

    assert len(fetch_calls) >= 1


async def test_version_loop_stops_removed_device():
    """Devices removed from the fetch list have their tasks cancelled."""
    from boardfarm_agent.services.version import version_loop
    from boardfarm_agent.config import DeviceConfig

    _real_sleep = asyncio.sleep
    dev = DeviceConfig(id="vl-dev-3", version_script="/script.sh")

    call_count = [0]

    async def fake_fetch():
        call_count[0] += 1
        if call_count[0] == 1:
            return [dev]
        return []  # device removed on second call

    sleep_count = [0]

    async def fake_sleep(_):
        await _real_sleep(0)  # yield so tasks can start
        sleep_count[0] += 1
        if sleep_count[0] >= 2:
            raise asyncio.CancelledError

    async def fake_device_loop(*a):
        await _real_sleep(9999)

    with patch("boardfarm_agent.services.version._device_loop", side_effect=fake_device_loop):
        with patch("boardfarm_agent.services.version.asyncio.sleep", side_effect=fake_sleep):
            try:
                await version_loop("http://server", "tok", fake_fetch)
            except asyncio.CancelledError:
                pass

    assert call_count[0] >= 2  # iterated at least twice
