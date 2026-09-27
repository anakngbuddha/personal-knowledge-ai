"""Process isolation for third-party MCP servers (audit finding 12).

The Python-side sandbox (tool allowlists, URL checks, timeouts, output fencing) only
controls what we *ask* a child server to do. It cannot contain a compromised npm
package. This module narrows what a child process can reach even if it misbehaves:

* **Environment**: only allowlisted variables plus the server's own credential. The
  child never inherits DATABASE_URL, GEMINI_API_KEY, JWT_SECRET_KEY, R2 keys, etc.
  (the old code passed `env=None`, which inherits the full parent environment).
* **Filesystem**: a private HOME / working directory / npm cache per server and
  tenant, created 0700, instead of the application's working directory.
* **OS sandbox (optional)**: `MCP_CHILD_SANDBOX_COMMAND` is prepended to the launch
  command, e.g. `bwrap --unshare-all --share-net --die-with-parent --ro-bind / / --tmpfs /tmp --`
  or `firejail --quiet --private --net=none`. Use it wherever the host supports it;
  without it, network and filesystem reach are those of the app user.

Package versions are pinned in app.mcp.servers.
"""

from __future__ import annotations

import os
import re
import shlex
from pathlib import Path

from app.core.config import settings
from app.mcp.servers import ServerSpec

# Never forwarded, even if someone adds them to the allowlist by mistake.
_NEVER_FORWARD = re.compile(
    r"(DATABASE|POSTGRES|JWT|SECRET|PASSWORD|GEMINI|OPENROUTER|R2_|AWS_|MCP_CREDENTIALS|SSO_|OIDC_|SAML_)",
    re.IGNORECASE,
)


def _allowlist() -> list[str]:
    raw = getattr(settings, "mcp_child_env_allowlist", "PATH") or "PATH"
    return [name.strip() for name in raw.split(",") if name.strip()]


def _safe_segment(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", value)[:80] or "default"


def child_workdir(spec: ServerSpec) -> Path:
    base = Path(getattr(settings, "mcp_child_workdir", "./.mcp-sandbox") or "./.mcp-sandbox").resolve()
    path = base / f"{_safe_segment(spec.slug)}-{_safe_segment(str(spec.org_id))}"
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path


def child_environment(spec: ServerSpec, workdir: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for name in _allowlist():
        if _NEVER_FORWARD.search(name):
            continue
        value = os.environ.get(name)
        if value is not None:
            env[name] = value
    home = str(workdir)
    env.update(
        {
            "HOME": home,
            "USERPROFILE": home,
            "TMPDIR": str(workdir / "tmp"),
            "npm_config_cache": str(workdir / ".npm"),
            "npm_config_update_notifier": "false",
            "NO_UPDATE_NOTIFIER": "1",
        }
    )
    (workdir / "tmp").mkdir(exist_ok=True)
    # The server's own credential(s), set explicitly by the integration store.
    for key, value in (spec.env or {}).items():
        env[str(key)] = str(value)
    return env


def child_launch(spec: ServerSpec) -> tuple[str, list[str], dict[str, str], str]:
    """(command, args, env, cwd) for a sandboxed stdio launch of `spec`."""
    workdir = child_workdir(spec)
    env = child_environment(spec, workdir)
    command = spec.command
    args = list(spec.args)
    wrapper = shlex.split(getattr(settings, "mcp_child_sandbox_command", "") or "")
    if wrapper:
        args = [*wrapper[1:], command, *args]
        command = wrapper[0]
    return command, args, env, str(workdir)
