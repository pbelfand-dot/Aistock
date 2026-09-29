"""
claude_setup.py: connects Claude Desktop (on this Mac) to the bot and to your Schwab account.

It adds two entries to Claude Desktop's settings file (your old file is backed up first):

  ai-trader  this bot's own MCP server (mcp_server.py). Claude can see status, plans, trades
             and your Alpaca account, and can PAUSE trading. It can't buy, sell or go live.

  schwab     the community "schwab-mcp" server (github.com/jkoelker/schwab-mcp, MIT license).
             There is no official Schwab MCP server. It's set up READ-ONLY: quotes, accounts,
             positions, orders. Its trading tools stay OFF (we never pass --jesus-take-the-wheel).
             Added only once your Schwab keys are in .env. It reuses the bot's Schwab login,
             and refuses logins older than 5 days, so log in to Schwab about every 5 days.
"""
import json
import shutil
import subprocess
import time
from pathlib import Path

from .config import load_config

CLAUDE_CONFIG = Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
SCHWAB_MCP = "git+https://github.com/jkoelker/schwab-mcp.git"
LOCAL_BIN = Path.home() / ".local" / "bin"


def schwab_mcp_command() -> Path:
    return LOCAL_BIN / "schwab-mcp"


def install_schwab_mcp():
    uv = shutil.which("uv") or str(LOCAL_BIN / "uv")
    subprocess.run([uv, "tool", "install", "--python", "3.12", SCHWAB_MCP], check=True)


def connect_claude_desktop(root: Path, config_path: Path = CLAUDE_CONFIG, install=install_schwab_mcp) -> str:
    cfg = load_config()
    settings = json.loads(config_path.read_text()) if config_path.exists() else {}
    if config_path.exists():
        shutil.copy(config_path, config_path.with_name(f"claude_desktop_config.backup-{int(time.time())}.json"))
    servers = settings.setdefault("mcpServers", {})

    servers["ai-trader"] = {"command": str(root / ".venv" / "bin" / "python"), "args": [str(root / "mcp_server.py")]}
    notes = ["ai-trader: connected. Claude can see the bot and your Alpaca account, and can pause trading."]

    s = cfg["secrets"]
    if s["app_key"] and s["app_secret"]:
        if not schwab_mcp_command().exists():
            install()
        servers["schwab"] = {
            "command": str(schwab_mcp_command()),
            "args": ["server", "--token-path", str(root / "data" / "schwab_token.json")],   # READ-ONLY
            "env": {"SCHWAB_CLIENT_ID": s["app_key"], "SCHWAB_CLIENT_SECRET": s["app_secret"],
                    "SCHWAB_CALLBACK_URL": s["callback_url"]},
        }
        notes.append("schwab: connected READ-ONLY (quotes, accounts, positions, orders; it can't trade). "
                     "Log in to Schwab from the menu about every 5 days.")
    else:
        notes.append("schwab: skipped for now. Add SCHWAB_APP_KEY and SCHWAB_APP_SECRET to .env, "
                     "log in to Schwab, then pick 'Connect Claude' again.")

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(settings, indent=2))
    notes.append("Now QUIT Claude Desktop completely (Cmd+Q) and open it again.")
    return "\n".join(notes)
