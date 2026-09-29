"""
claude_setup.py: connects Claude (Claude Code and/or Claude Desktop) to the bot and to Schwab.

Two connections ("MCP servers"):

  ai-trader  this bot's own MCP server (mcp_server.py). Claude can see status, plans, trades
             and your Alpaca account, and can PAUSE trading. It can't buy, sell or go live.

  schwab     the community "schwab-mcp" server (github.com/jkoelker/schwab-mcp, MIT license).
             There is no official Schwab MCP server. It's set up READ-ONLY: quotes, accounts,
             positions, orders. Its trading tools stay OFF (we never pass --jesus-take-the-wheel).
             Added only once your Schwab keys are in .env. It reuses the bot's Schwab login,
             and refuses logins older than 5 days, so log in to Schwab about every 5 days.

Claude Code: added with `claude mcp add --scope user`, so they work in every project.
Claude Desktop: added to its settings file (your old file is backed up first).
"""
import json
import shutil
import subprocess
import time
from pathlib import Path

from .config import load_config

CLAUDE_DESKTOP_CONFIG = Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
SCHWAB_MCP = "git+https://github.com/jkoelker/schwab-mcp.git"
LOCAL_BIN = Path.home() / ".local" / "bin"
CLAUDE_CLI_PLACES = [Path.home() / ".claude" / "local" / "claude", LOCAL_BIN / "claude",
                     Path("/opt/homebrew/bin/claude"), Path("/usr/local/bin/claude")]


def schwab_mcp_command() -> Path:
    return LOCAL_BIN / "schwab-mcp"


def install_schwab_mcp():
    uv = shutil.which("uv") or str(LOCAL_BIN / "uv")
    subprocess.run([uv, "tool", "install", "--python", "3.12", SCHWAB_MCP], check=True)


def servers(root: Path, install=install_schwab_mcp) -> tuple:
    """The MCP servers to connect, as {name: {command, args, env}}, plus notes for the user."""
    cfg = load_config()
    found = {"ai-trader": {"command": str(root / ".venv" / "bin" / "python"), "args": [str(root / "mcp_server.py")]}}
    notes = ["ai-trader: Claude can see the bot and your Alpaca account, and can pause trading."]
    s = cfg["secrets"]
    if s["app_key"] and s["app_secret"]:
        if not schwab_mcp_command().exists():
            install()
        found["schwab"] = {
            "command": str(schwab_mcp_command()),
            "args": ["server", "--token-path", str(root / "data" / "schwab_token.json")],   # READ-ONLY
            "env": {"SCHWAB_CLIENT_ID": s["app_key"], "SCHWAB_CLIENT_SECRET": s["app_secret"],
                    "SCHWAB_CALLBACK_URL": s["callback_url"]},
        }
        notes.append("schwab: READ-ONLY (quotes, accounts, positions, orders; it can't trade). "
                     "Log in to Schwab from the menu about every 5 days.")
    else:
        notes.append("schwab: skipped for now. Add SCHWAB_APP_KEY and SCHWAB_APP_SECRET to .env, "
                     "log in to Schwab, then connect Claude again.")
    return found, notes


def find_claude_cli(which=shutil.which):
    found = which("claude")
    if found:
        return found
    return next((str(p) for p in CLAUDE_CLI_PLACES if p.exists()), None)


def add_command(claude: str, name: str, spec: dict) -> list:
    env = [part for k, v in spec.get("env", {}).items() for part in ("--env", f"{k}={v}")]
    return [claude, "mcp", "add", *env, "--scope", "user", name, "--", spec["command"], *spec["args"]]


def connect_claude_code(root: Path, run=subprocess.run, which=shutil.which, install=install_schwab_mcp) -> str:
    found, notes = servers(root, install)
    claude = find_claude_cli(which)
    if not claude:
        manual = "\n".join("  " + " ".join(add_command("claude", n, spec)) for n, spec in found.items())
        return ("Couldn't find the `claude` command on this Mac. Paste these into Terminal instead:\n" + manual)
    for name, spec in found.items():
        run([claude, "mcp", "remove", name, "--scope", "user"], capture_output=True)   # re-adding would fail
        run(add_command(claude, name, spec), check=True, capture_output=True)
    return "\n".join(["Claude Code connected (in every project):"] + notes +
                     ["Start a NEW Claude Code session, then type /mcp to see them."])


def connect_claude_desktop(root: Path, config_path: Path = CLAUDE_DESKTOP_CONFIG, install=install_schwab_mcp) -> str:
    found, notes = servers(root, install)
    settings = json.loads(config_path.read_text()) if config_path.exists() else {}
    if config_path.exists():
        shutil.copy(config_path, config_path.with_name(f"claude_desktop_config.backup-{int(time.time())}.json"))
    settings.setdefault("mcpServers", {}).update(found)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(settings, indent=2))
    return "\n".join(["Claude Desktop connected:"] + notes +
                     ["Now QUIT Claude Desktop completely (Cmd+Q) and open it again."])
