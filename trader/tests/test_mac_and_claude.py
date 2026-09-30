"""The Mac app pieces and the Claude (MCP) connection."""
import asyncio
import hashlib
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
                     "pause_trading", "knowledge"}
    assert "10-safety-rules" in mcp_server.knowledge() and "good faith" in mcp_server.knowledge("10-safety-rules")
    assert "=== KESTREL ===" in mcp_server.bot_status()
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
    # Compiling the app itself needs a Mac (GitHub does it there); this checks everything around it.
    out = subprocess.run(["bash", str(REPO / "mac" / "build_app.sh"), "9.9.9"], capture_output=True, text=True,
                         env={**os.environ, "AITRADER_NO_COMPILE": "1"})
    assert out.returncode == 0, out.stderr
    archive = REPO / "dist" / "Kestrel-mac.zip"
    try:
        with zipfile.ZipFile(archive) as z:
            names = set(z.namelist())
            launcher = z.getinfo("Kestrel.app/Contents/MacOS/AITrader")
            assert (launcher.external_attr >> 16) & 0o111, "launcher must stay executable"
            plist = plistlib.loads(z.read("Kestrel.app/Contents/Info.plist"))
        assert plist["CFBundleExecutable"] == "AITrader" and plist["CFBundleShortVersionString"] == "9.9.9"
        assert plist["LSRequiresNativeExecution"] is True                    # no Rosetta prompt
        assert plist["CFBundleIconFile"] == "AppIcon" and plist["CFBundleIdentifier"] == "com.aitrader.app"
        for f in ("install.sh", "Kestrel Menu.command", "AppIcon.icns", "VERSION"):
            assert f"Kestrel.app/Contents/Resources/{f}" in names
        for f in ("run.py", "mcp_server.py", "config.yaml", "requirements.txt", ".env.example",
                  "aitrader/web/dashboard.html", "aitrader/app_api.py"):
            assert f"Kestrel.app/Contents/Resources/trader/{f}" in names
        assert not any("/.env" == n[-5:] for n in names), "never ship anyone's keys"
        # What installed apps read to update themselves: this version and the zip's exact fingerprint.
        manifest = json.loads((REPO / "dist" / "latest.json").read_text())
        assert manifest == {"version": "9.9.9", "zip": "Kestrel-mac.zip",
                            "sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}
    finally:
        subprocess.run(["rm", "-rf", str(REPO / "dist")])


def test_connect_claude_code_adds_both_servers_in_user_scope(config_file, monkeypatch):
    from aitrader.claude_setup import connect_claude_code
    monkeypatch.setenv("SCHWAB_APP_KEY", "key")
    monkeypatch.setenv("SCHWAB_APP_SECRET", "secret")
    calls = []
    message = connect_claude_code(Path("/Users/me/AITrader"), run=lambda args, **kw: calls.append(args),
                                  which=lambda name: "/usr/local/bin/claude", install=lambda: None)
    adds = [c for c in calls if c[2] == "add"]
    assert [c for c in calls if c[2] == "remove"] and len(adds) == 2         # removed first, then added
    trader = next(c for c in adds if "ai-trader" in c)
    assert trader == ["/usr/local/bin/claude", "mcp", "add", "--scope", "user", "ai-trader", "--",
                      "/Users/me/AITrader/.venv/bin/python", "/Users/me/AITrader/mcp_server.py"]
    schwab = next(c for c in adds if "schwab" in c)
    assert "--env" in schwab and schwab.index("--env") < schwab.index("schwab")   # options before the name
    assert "--jesus-take-the-wheel" not in schwab and "/mcp" in message


def test_connect_claude_code_without_the_cli_prints_commands(config_file, monkeypatch):
    from aitrader import claude_setup
    monkeypatch.setattr(claude_setup, "CLAUDE_CLI_PLACES", [])
    message = claude_setup.connect_claude_code(Path("/Users/me/AITrader"), run=None, which=lambda name: None)
    assert "claude mcp add --scope user ai-trader --" in message


def test_updates_never_touch_your_keys_settings_or_logins(tmp_path):
    """Your keys (.env), app settings (my_settings.json) and Schwab login (data/) live in ~/AITrader,
    outside the app. An update replaces the app and the bot's code, never those files, and an older
    copy of the app never rolls the bot back."""
    import shutil
    apps = {}
    for version in ("1.0.1", "1.0.2"):
        out = subprocess.run(["bash", str(REPO / "mac" / "build_app.sh"), version], capture_output=True, text=True,
                             env={**os.environ, "AITRADER_NO_COMPILE": "1"})
        assert out.returncode == 0, out.stderr
        apps[version] = tmp_path / version
        shutil.copytree(REPO / "dist" / "Kestrel.app", apps[version] / "Kestrel.app")
    subprocess.run(["rm", "-rf", str(REPO / "dist")])
    home = tmp_path / "home"
    home.mkdir()

    def open_app(version):                              # what the app does each time it opens
        script = apps[version] / "Kestrel.app" / "Contents" / "Resources" / "install.sh"
        subprocess.run(["bash", str(script)], env={**os.environ, "HOME": str(home)}, check=True, capture_output=True)

    bot = home / "AITrader"
    open_app("1.0.1")
    (bot / ".env").write_text("ALPACA_PAPER_API_KEY=PKMYKEY123456789\nALPACA_PAPER_SECRET_KEY=" + "s" * 40 + "\n")
    (bot / "my_settings.json").write_text('{"real_money_cap": 50}')
    (bot / "data").mkdir(exist_ok=True)
    (bot / "data" / "schwab_token.json").write_text('{"creation_timestamp": 1, "token": {}}')
    mine = {p: (bot / p).read_text() for p in (".env", "my_settings.json", "data/schwab_token.json")}

    open_app("1.0.2")                                    # an update
    assert (bot / "VERSION").read_text().strip() == "1.0.2"
    assert {p: (bot / p).read_text() for p in mine} == mine
    open_app("1.0.1")                                    # an older copy of the app opens: no rollback
    assert (bot / "VERSION").read_text().strip() == "1.0.2"
    assert {p: (bot / p).read_text() for p in mine} == mine
