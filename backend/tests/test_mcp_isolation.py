"""Child MCP process isolation (audit finding 12)."""

from __future__ import annotations

from app.core.config import settings
from app.mcp import servers
from app.mcp.isolation import child_launch
from app.mcp.servers import ServerSpec


def test_child_env_drops_application_secrets(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "postgresql://secret")
    monkeypatch.setenv("GEMINI_API_KEY", "gem-secret")
    monkeypatch.setenv("JWT_SECRET_KEY", "jwt-secret")
    monkeypatch.setattr(settings, "mcp_child_workdir", str(tmp_path))
    monkeypatch.setattr(settings, "mcp_child_env_allowlist", "PATH,DATABASE_URL")
    spec = ServerSpec(slug="brave", org_id="org-1", args=servers.brave_args(), env={"BRAVE_API_KEY": "b"})
    command, args, env, cwd = child_launch(spec)
    assert "DATABASE_URL" not in env  # never forwarded, even if allowlisted
    assert "GEMINI_API_KEY" not in env
    assert "JWT_SECRET_KEY" not in env
    assert env["BRAVE_API_KEY"] == "b"
    assert env["HOME"] == cwd
    assert cwd.startswith(str(tmp_path))
    assert command == "npx"


def test_sandbox_wrapper_is_prepended(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "mcp_child_workdir", str(tmp_path))
    monkeypatch.setattr(settings, "mcp_child_sandbox_command", "firejail --quiet --private")
    spec = ServerSpec(slug="playwright", org_id="o", args=servers.playwright_args())
    command, args, _, _ = child_launch(spec)
    assert command == "firejail"
    assert args[:3] == ["--quiet", "--private", "npx"]


def test_packages_are_pinned():
    for args in (servers.brave_args(), servers.playwright_args(), servers.ms365_args()):
        package = args[1]
        assert "@latest" not in package
        assert package.rsplit("@", 1)[1][0].isdigit(), package
