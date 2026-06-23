"""
Tests for server/config.py, server/auth.py, server/main.py (_git_version),
and server/database.py (init_db / get_db).
"""
import subprocess
from unittest.mock import patch

import pytest
import yaml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

AUTH = {"X-Token": "test-token", "X-User": "testuser"}


# ===========================================================================
# Settings / config — server/config.py lines 24-39
# ===========================================================================


def test_settings_loads_from_yaml(monkeypatch, tmp_path):
    """Settings.model_post_init reads values from a config.yaml in cwd."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        yaml.dump(
            {
                "server": {
                    "token": "yaml-tok",
                    "port": 9999,
                    "admin_users": ["admin"],
                    "max_booking_hours": 48,
                    "default_user": "alice",
                    "app_name": "TestFarm",
                    "db_path": "/tmp/test.db",
                }
            }
        )
    )
    monkeypatch.chdir(tmp_path)
    # Remove any env-var overrides so YAML values win
    for key in (
        "BOARDFARM_TOKEN",
        "BOARDFARM_PORT",
        "BOARDFARM_ADMIN_USERS",
        "BOARDFARM_MAX_BOOKING_HOURS",
        "BOARDFARM_DEFAULT_USER",
        "BOARDFARM_APP_NAME",
        "BOARDFARM_DB_PATH",
    ):
        monkeypatch.delenv(key, raising=False)

    from server.config import Settings

    s = Settings()
    assert s.token == "yaml-tok"
    assert s.port == 9999
    assert s.admin_users == ["admin"]
    assert s.max_booking_hours == 48
    assert s.default_user == "alice"
    assert s.app_name == "TestFarm"
    assert s.db_path == "/tmp/test.db"


def test_settings_env_var_overrides_yaml(monkeypatch, tmp_path):
    """An env-var must take precedence over the value in config.yaml."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text(yaml.dump({"server": {"token": "yaml-tok", "port": 9999}}))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BOARDFARM_TOKEN", "env-tok")
    monkeypatch.delenv("BOARDFARM_PORT", raising=False)

    from server.config import Settings

    s = Settings()
    # env var must win for token
    assert s.token == "env-tok"
    # port comes from YAML because BOARDFARM_PORT is not set
    assert s.port == 9999


def test_settings_env_var_port_overrides_yaml(monkeypatch, tmp_path):
    """BOARDFARM_PORT env var takes precedence over yaml port."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text(yaml.dump({"server": {"port": 9999}}))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BOARDFARM_PORT", "1234")

    from server.config import Settings

    s = Settings()
    assert s.port == 1234


def test_settings_defaults_without_yaml(monkeypatch, tmp_path):
    """Without a config.yaml, Settings uses hard-coded defaults."""
    monkeypatch.chdir(tmp_path)  # no config.yaml in tmp_path
    for key in (
        "BOARDFARM_TOKEN",
        "BOARDFARM_PORT",
        "BOARDFARM_ADMIN_USERS",
        "BOARDFARM_MAX_BOOKING_HOURS",
        "BOARDFARM_DEFAULT_USER",
        "BOARDFARM_APP_NAME",
        "BOARDFARM_DB_PATH",
    ):
        monkeypatch.delenv(key, raising=False)

    from server.config import Settings

    s = Settings()
    assert s.port == 8765
    assert s.token == ""
    assert s.admin_users == []
    assert s.max_booking_hours == 24
    assert s.default_user is None
    assert "BOARDFARM" in s.app_name


def test_settings_yaml_empty_server_block(monkeypatch, tmp_path):
    """A config.yaml with no 'server' key must not crash Settings."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text(yaml.dump({"other_section": {"foo": "bar"}}))
    monkeypatch.chdir(tmp_path)
    for key in ("BOARDFARM_TOKEN", "BOARDFARM_PORT"):
        monkeypatch.delenv(key, raising=False)

    from server.config import Settings

    s = Settings()  # must not raise
    assert s.port == 8765


def test_settings_yaml_null_content(monkeypatch, tmp_path):
    """An empty config.yaml (null YAML) must not crash Settings."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text("")
    monkeypatch.chdir(tmp_path)
    for key in ("BOARDFARM_TOKEN", "BOARDFARM_PORT"):
        monkeypatch.delenv(key, raising=False)

    from server.config import Settings

    s = Settings()  # must not raise
    assert s.port == 8765


# ===========================================================================
# Auth — server/auth.py line 11 (no-token path)
# ===========================================================================


@pytest.mark.asyncio
async def test_no_token_configured_allows_requests(client):
    """When settings.token is empty, mutating requests succeed without X-Token."""
    from server.config import settings

    orig = settings.token
    settings.token = ""
    try:
        r = await client.post(
            "/devices",
            json={"name": "no-token-device", "device_id": "no-tok-dev"},
            headers={"X-User": "u"},  # no X-Token header
        )
        assert r.status_code == 201
    finally:
        settings.token = orig


@pytest.mark.asyncio
async def test_wrong_token_is_rejected(client):
    """A wrong token returns HTTP 401."""
    r = await client.post(
        "/devices",
        json={"name": "rejected-device", "device_id": "rej-dev"},
        headers={"X-Token": "wrong-token", "X-User": "u"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_missing_token_is_rejected(client):
    """Missing X-Token header returns HTTP 401 when a token is configured."""
    r = await client.post(
        "/devices",
        json={"name": "no-token-hdr", "device_id": "no-tok-hdr"},
        headers={"X-User": "u"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_correct_token_is_accepted(client):
    """The correct token allows the request through."""
    r = await client.post(
        "/devices",
        json={"name": "auth-ok-device", "device_id": "auth-ok-dev"},
        headers=AUTH,
    )
    assert r.status_code == 201


# ===========================================================================
# _git_version() — server/main.py lines 18-43
# ===========================================================================


def test_git_version_uses_env_var(monkeypatch):
    """BOARDFARM_VERSION env var is returned directly, no git calls made."""
    monkeypatch.setenv("BOARDFARM_VERSION", "v1.2.3-abc")
    monkeypatch.delenv("BOARDFARM_VERSION", raising=False)  # ensure clean state first
    monkeypatch.setenv("BOARDFARM_VERSION", "v1.2.3-abc")

    from server.main import _git_version

    with patch("server.main.subprocess.check_output") as mock_co:
        result = _git_version()
    assert result == "v1.2.3-abc"
    mock_co.assert_not_called()


def test_git_version_with_tag_clean():
    """When a tag exists and tree is clean, returns '<tag>-<sha>'."""
    def fake_check_output(cmd, **kw):
        if "rev-parse" in cmd:
            return "abc12345\n"
        if "describe" in cmd:
            return "v1.0\n"
        if "status" in cmd:
            return ""  # clean working tree
        raise subprocess.CalledProcessError(1, cmd)

    import os

    with patch.dict(os.environ, {}, clear=False):
        # Make sure BOARDFARM_VERSION is absent
        os.environ.pop("BOARDFARM_VERSION", None)
        with patch("server.main.subprocess.check_output", side_effect=fake_check_output):
            from server.main import _git_version

            result = _git_version()

    assert result == "v1.0-abc12345"


def test_git_version_dirty_no_tag():
    """When working tree is dirty and there is no tag, returns '<sha>-dirty'."""
    def fake_check_output(cmd, **kw):
        if "rev-parse" in cmd:
            return "abc12345\n"
        if "describe" in cmd:
            raise subprocess.CalledProcessError(1, cmd)
        if "status" in cmd:
            return "M file.py\n"  # dirty
        raise subprocess.CalledProcessError(1, cmd)

    import os

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("BOARDFARM_VERSION", None)
        with patch("server.main.subprocess.check_output", side_effect=fake_check_output):
            from server.main import _git_version

            result = _git_version()

    assert result == "abc12345-dirty"


def test_git_version_clean_no_tag():
    """When working tree is clean and no tag, returns just '<sha>'."""
    def fake_check_output(cmd, **kw):
        if "rev-parse" in cmd:
            return "deadbeef\n"
        if "describe" in cmd:
            raise subprocess.CalledProcessError(1, cmd)
        if "status" in cmd:
            return ""  # clean
        raise subprocess.CalledProcessError(1, cmd)

    import os

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("BOARDFARM_VERSION", None)
        with patch("server.main.subprocess.check_output", side_effect=fake_check_output):
            from server.main import _git_version

            result = _git_version()

    assert result == "deadbeef"


def test_git_version_dirty_with_tag():
    """When tag exists and tree is dirty, returns '<tag>-<sha>-dirty'."""
    def fake_check_output(cmd, **kw):
        if "rev-parse" in cmd:
            return "cafebabe\n"
        if "describe" in cmd:
            return "v2.3\n"
        if "status" in cmd:
            return "M dirty.py\n"
        raise subprocess.CalledProcessError(1, cmd)

    import os

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("BOARDFARM_VERSION", None)
        with patch("server.main.subprocess.check_output", side_effect=fake_check_output):
            from server.main import _git_version

            result = _git_version()

    assert result == "v2.3-cafebabe-dirty"


def test_git_version_fallback_on_file_not_found():
    """When git is not available (FileNotFoundError), returns 'unknown'."""
    import os

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("BOARDFARM_VERSION", None)
        with patch(
            "server.main.subprocess.check_output", side_effect=FileNotFoundError
        ):
            from server.main import _git_version

            result = _git_version()

    assert result == "unknown"


def test_git_version_fallback_on_generic_exception():
    """Any unexpected exception during git falls back to 'unknown'."""
    import os

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("BOARDFARM_VERSION", None)
        with patch(
            "server.main.subprocess.check_output",
            side_effect=RuntimeError("unexpected"),
        ):
            from server.main import _git_version

            result = _git_version()

    assert result == "unknown"


# ===========================================================================
# database — server/database.py lines 28-40
# ===========================================================================


@pytest.mark.asyncio
async def test_init_db_is_idempotent():
    """Calling init_db() twice must not raise (migrations skip existing columns)."""
    from server.database import init_db

    await init_db()
    await init_db()  # second call must be a no-op


@pytest.mark.asyncio
async def test_get_db_yields_session():
    """get_db() yields a live AsyncSession and closes it cleanly."""
    from server.database import get_db
    from sqlalchemy.ext.asyncio import AsyncSession

    gen = get_db()
    session = await gen.__anext__()
    assert session is not None
    assert isinstance(session, AsyncSession)
    # Close the generator gracefully
    try:
        await gen.aclose()
    except Exception:
        pass


@pytest.mark.asyncio
async def test_get_db_session_can_execute_query():
    """Session from get_db() can run a trivial SQL query."""
    from server.database import get_db
    from sqlalchemy import text

    gen = get_db()
    session = await gen.__anext__()
    try:
        result = await session.execute(text("SELECT 1"))
        row = result.scalar()
        assert row == 1
    finally:
        try:
            await gen.aclose()
        except Exception:
            pass
