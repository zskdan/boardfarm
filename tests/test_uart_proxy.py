"""
Tests for agent/services/uart_proxy.py

Covers:
  - _start_socat: success, socat missing, generic exception
  - start: empty uart_device, happy path, idempotency
  - stop: active proxy, nothing running
  - stop_all: multiple proxies
  - _monitor: restarts socat on exit, stops when deactivated
"""
import asyncio
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Helpers — reset module-level state between tests
# ---------------------------------------------------------------------------

def _reset_state():
    import agent.services.uart_proxy as m
    m._tasks.clear()
    m._active.clear()
    m._locks.clear()


# ---------------------------------------------------------------------------
# _start_socat
# ---------------------------------------------------------------------------

def test_start_socat_returns_popen_on_success():
    from agent.services.uart_proxy import _start_socat

    mock_proc = MagicMock(spec=subprocess.Popen)
    mock_proc.pid = 1234

    with patch("agent.services.uart_proxy.subprocess.Popen", return_value=mock_proc) as mock_popen:
        result = _start_socat("/dev/ttyUSB0", 115200, 5000)

    assert result is mock_proc
    mock_popen.assert_called_once()
    cmd = mock_popen.call_args[0][0]
    assert "socat" in cmd
    assert "TCP4-LISTEN:5000,fork,reuseaddr" in cmd
    assert "/dev/ttyUSB0,raw,b115200,echo=0" in cmd


def test_start_socat_returns_none_when_socat_missing():
    from agent.services.uart_proxy import _start_socat

    with patch("agent.services.uart_proxy.subprocess.Popen", side_effect=FileNotFoundError):
        result = _start_socat("/dev/ttyUSB0", 115200, 5000)

    assert result is None


def test_start_socat_returns_none_on_generic_exception():
    from agent.services.uart_proxy import _start_socat

    with patch("agent.services.uart_proxy.subprocess.Popen", side_effect=OSError("permission denied")):
        result = _start_socat("/dev/ttyUSB0", 115200, 5000)

    assert result is None


# ---------------------------------------------------------------------------
# start()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_start_returns_false_for_empty_uart_device():
    _reset_state()
    from agent.services.uart_proxy import start

    result = await start("dev-1", "", 115200, 5000)
    assert result is False


@pytest.mark.asyncio
async def test_start_returns_true_and_creates_task():
    _reset_state()
    import agent.services.uart_proxy as m

    mock_proc = MagicMock(spec=subprocess.Popen)
    mock_proc.pid = 42
    mock_proc.wait = MagicMock(return_value=0)

    with patch("agent.services.uart_proxy._start_socat", return_value=mock_proc):
        result = await m.start("dev-2", "/dev/ttyUSB0", 115200, 5001)

    assert result is True
    assert "dev-2" in m._tasks
    assert "dev-2" in m._active
    assert m._active["dev-2"] is True

    # Cleanup
    await m.stop("dev-2")


@pytest.mark.asyncio
async def test_start_is_idempotent():
    """Calling start() twice does not create a second task."""
    _reset_state()
    import agent.services.uart_proxy as m

    mock_proc = MagicMock(spec=subprocess.Popen)
    mock_proc.pid = 99
    mock_proc.wait = MagicMock(return_value=0)

    with patch("agent.services.uart_proxy._start_socat", return_value=mock_proc):
        r1 = await m.start("dev-3", "/dev/ttyUSB0", 115200, 5002)
        task_before = m._tasks.get("dev-3")
        r2 = await m.start("dev-3", "/dev/ttyUSB0", 115200, 5002)
        task_after = m._tasks.get("dev-3")

    assert r1 is True
    assert r2 is True
    assert task_before is task_after  # same task object, not replaced

    await m.stop("dev-3")


# ---------------------------------------------------------------------------
# stop()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stop_cancels_active_task():
    _reset_state()
    import agent.services.uart_proxy as m

    mock_proc = MagicMock(spec=subprocess.Popen)
    mock_proc.pid = 77
    mock_proc.wait = MagicMock(return_value=0)

    with patch("agent.services.uart_proxy._start_socat", return_value=mock_proc):
        await m.start("dev-4", "/dev/ttyUSB0", 115200, 5003)

    assert "dev-4" in m._tasks
    await m.stop("dev-4")

    assert m._active.get("dev-4") is False  # deactivated, not deleted
    assert "dev-4" not in m._tasks


@pytest.mark.asyncio
async def test_stop_is_safe_when_nothing_running():
    """stop() on an unknown device must not raise."""
    _reset_state()
    from agent.services.uart_proxy import stop

    await stop("nonexistent-device")  # must not raise


# ---------------------------------------------------------------------------
# stop_all()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stop_all_clears_all_proxies():
    _reset_state()
    import agent.services.uart_proxy as m

    mock_proc = MagicMock(spec=subprocess.Popen)
    mock_proc.pid = 55
    mock_proc.wait = MagicMock(return_value=0)

    with patch("agent.services.uart_proxy._start_socat", return_value=mock_proc):
        await m.start("dev-a", "/dev/ttyUSB0", 115200, 5010)
        await m.start("dev-b", "/dev/ttyUSB1", 115200, 5011)

    assert len(m._active) == 2
    await m.stop_all()
    assert all(v is False for v in m._active.values())  # all deactivated
    assert len(m._tasks) == 0


# ---------------------------------------------------------------------------
# _monitor()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_monitor_exits_cleanly_when_deactivated():
    """_monitor should exit its loop when _active[device_id] is set to False."""
    _reset_state()
    import agent.services.uart_proxy as m

    m._active["dev-m1"] = True

    mock_proc = MagicMock(spec=subprocess.Popen)
    mock_proc.pid = 11

    call_count = 0

    def fake_wait():
        nonlocal call_count
        call_count += 1
        # After socat "exits", deactivate so the monitor loop stops
        m._active["dev-m1"] = False

    mock_proc.wait = fake_wait

    with patch("agent.services.uart_proxy._start_socat", return_value=mock_proc):
        with patch("agent.services.uart_proxy.asyncio.sleep", new_callable=AsyncMock):
            await m._monitor("dev-m1", "/dev/ttyUSB0", 115200, 5020)

    assert call_count == 1  # socat started once, then deactivated


@pytest.mark.asyncio
async def test_monitor_restarts_socat_on_exit():
    """_monitor restarts socat when it exits while still active."""
    _reset_state()
    import agent.services.uart_proxy as m

    m._active["dev-m2"] = True

    mock_proc = MagicMock(spec=subprocess.Popen)
    mock_proc.pid = 22

    start_calls = []

    def fake_start_socat(uart_device, baud, tcp_port):
        start_calls.append(len(start_calls))
        if len(start_calls) >= 2:
            m._active["dev-m2"] = False  # stop after second start
        return mock_proc

    mock_proc.wait = MagicMock(return_value=0)

    with patch("agent.services.uart_proxy._start_socat", side_effect=fake_start_socat):
        with patch("agent.services.uart_proxy.asyncio.sleep", new_callable=AsyncMock):
            await m._monitor("dev-m2", "/dev/ttyUSB0", 115200, 5021)

    assert len(start_calls) == 2  # socat was restarted once


@pytest.mark.asyncio
async def test_monitor_exits_immediately_when_socat_unavailable():
    """If socat is not found (_start_socat returns None), monitor exits without looping."""
    _reset_state()
    import agent.services.uart_proxy as m

    m._active["dev-m3"] = True

    with patch("agent.services.uart_proxy._start_socat", return_value=None):
        await m._monitor("dev-m3", "/dev/ttyUSB0", 115200, 5022)

    # Monitor must have exited; _active entry may still be set by caller
    # Key invariant: no infinite loop / no task hanging
