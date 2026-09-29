"""The Mac app pieces and the Claude (MCP) connection."""
import asyncio
import json
import os
import plistlib
import subprocess
import zipfile
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def config_file(tmp_path, monkeypatch):
    """A throwaway config so these tests never touch real data."""
    cfg = yaml.safe_load((REPO / "trader" / "config.yaml").read_text())
    cfg["data_dir"] = str(tmp_path / "data")
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(cfg))
    monkeypatch.setenv("AITRADER_CONFIG", str(path))
    for key in ("SCHWAB_APP_KEY", "SCHWAB_APP_SECRET", "ALPACA_PAPER_API_KEY", "ALPACA_PAPER_SECRET_KEY",
                "ALPACA_LIVE_API_KEY", "ALPACA_LIVE_SECRET_KEY"):
        monkeypatch.setenv(key, "")
    return path


def test_claude_can_look_and_pause_but_never_trade(config_file):
    pytest.importorskip("mcp")
    import mcp_server
    names = {t.name for t in asyncio.run(mcp_server.server.list_tools())}
    assert names == {"bot_status", "journal", "trading_plan", "positions", "performance", "broker_account",
                     "pause_trading"}
    assert "=== AI TRADER ===" in mcp_server.bot_status()
    assert "All desks paused" in mcp_server.pause_trading("test")
    assert "PAUSED by Claude" in mcp_server.journal(5)


def test_connect_claude_desktop_keeps_your_other_servers(config_file, tmp_path):
    from aitrader.claude_setup import connect_claude_desktop
    claude = tmp_path / "claude_desktop_config.json"
    claude.write_text(json.dumps({"mcpServers": {"yours": {"command": "x"}}, "other": 1}))
    message = connect_claude_desktop(Path("/Users/me/AITrader"), claude, install=lambda: None)
    settings = json.loads(claude.read_text())
    assert set(settings["mcpServers"]) == {"yours", "ai-trader"} and settings["other"] == 1
    assert settings["mcpServers"]["ai-trader"]["args"] == ["/Users/me/AITrader/mcp_server.py"]
    assert "schwab: skipped" in message and list(tmp_path.glob("claude_desktop_config.backup-*.json"))


def test_schwab_mcp_is_set_up_read_only(config_file, tmp_path, monkeypatch):
    from aitrader.claude_setup import connect_claude_desktop
    monkeypatch.setenv("SCHWAB_APP_KEY", "key")
    monkeypatch.setenv("SCHWAB_APP_SECRET", "secret")
    installed = []
    claude = tmp_path / "claude_desktop_config.json"
    connect_claude_desktop(Path("/Users/me/AITrader"), claude, install=lambda: installed.append(True))
    schwab = json.loads(claude.read_text())["mcpServers"]["schwab"]
    assert schwab["args"] == ["server", "--token-path", "/Users/me/AITrader/data/schwab_token.json"]
    assert "--jesus-take-the-wheel" not in schwab["args"]              # its trading tools stay OFF
    assert schwab["env"]["SCHWAB_CLIENT_ID"] == "key" and installed == [True]


def test_background_autopilot_service(tmp_path, monkeypatch):
    from aitrader import mac_service
    calls = []
    monkeypatch.setattr(mac_service, "PLIST", tmp_path / "com.aitrader.autopilot.plist")
    monkeypatch.setattr(mac_service.subprocess, "run", lambda args, **kw: calls.append(args))
    monkeypatch.setattr(mac_service.os, "getuid", lambda: 501, raising=False)
    mac_service.install(tmp_path)
    plist = plistlib.loads(mac_service.PLIST.read_bytes())
    assert plist["ProgramArguments"][:2] == ["/usr/bin/caffeinate", "-i"]         # no idle sleep while running
    assert plist["ProgramArguments"][-1] == "autopilot" and plist["KeepAlive"] and plist["RunAtLoad"]
    assert ["launchctl", "bootstrap", "gui/501", str(mac_service.PLIST)] in calls


def test_the_mac_app_builds(tmp_path):
    out = subprocess.run(["bash", str(REPO / "mac" / "build_app.sh"), "9.9.9"], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    archive = REPO / "dist" / "AITrader-mac.zip"
    try:
        with zipfile.ZipFile(archive) as z:
            names = set(z.namelist())
            launcher = z.getinfo("AI Trader.app/Contents/MacOS/AITrader")
            assert (launcher.external_attr >> 16) & 0o111, "launcher must stay executable"
            plist = plistlib.loads(z.read("AI Trader.app/Contents/Info.plist"))
        assert plist["CFBundleExecutable"] == "AITrader" and plist["CFBundleShortVersionString"] == "9.9.9"
        assert plist["LSRequiresNativeExecution"] is True                    # no Rosetta prompt
        for f in ("run.py", "mcp_server.py", "config.yaml", "requirements.txt", ".env.example"):
            assert f"AI Trader.app/Contents/Resources/trader/{f}" in names
        assert not any("/.env" == n[-5:] for n in names), "never ship anyone's keys"
    finally:
        subprocess.run(["rm", "-rf", str(REPO / "dist")])
