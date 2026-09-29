#!/bin/bash
# Run by "AI Trader.app" each time it opens (quick): copies this version of the bot into ~/AITrader.
# Your keys (.env), data (data/) and a backup of your settings are kept.
# Installing Python and the libraries happens in the Setup menu (AI Trader Menu.command), which the
# app opens in Terminal only when needed.
RES="$(cd "$(dirname "$0")" && pwd)"
APP_HOME="$HOME/AITrader"
NEW="$(cat "$RES/VERSION")"
OLD="$(cat "$APP_HOME/VERSION" 2>/dev/null)"
mkdir -p "$APP_HOME"

if [ "$NEW" != "$OLD" ]; then
  rm -rf "$APP_HOME/aitrader"
  cp -R "$RES/trader/aitrader" "$APP_HOME/aitrader"
  for f in run.py mcp_server.py requirements.txt README.md .env.example; do
    cp "$RES/trader/$f" "$APP_HOME/$f"
  done
  if [ -f "$APP_HOME/config.yaml" ] && ! cmp -s "$RES/trader/config.yaml" "$APP_HOME/config.yaml"; then
    cp "$APP_HOME/config.yaml" "$APP_HOME/config.yaml.before-$NEW"
    echo "AI Trader was updated to $NEW and its settings (config.yaml) were reset to the new defaults. Your previous settings are saved in config.yaml.before-$NEW if you want to copy anything back." > "$APP_HOME/.config_note"
  fi
  cp "$RES/trader/config.yaml" "$APP_HOME/config.yaml"
  [ -f "$APP_HOME/.env" ] || cp "$RES/trader/.env.example" "$APP_HOME/.env"
  echo "$NEW" > "$APP_HOME/VERSION"
  touch "$APP_HOME/.restart_autopilot"      # a running background autopilot must switch to the new code
fi

cp "$RES/AI Trader Menu.command" "$APP_HOME/AI Trader Menu.command"
chmod +x "$APP_HOME/AI Trader Menu.command"
# These are the bot's own files: clear the "downloaded from the internet" flag so they can run.
xattr -dr com.apple.quarantine "$APP_HOME" 2>/dev/null

# Libraries unchanged? Then restart the background autopilot right away. (If they changed, the
# Setup menu installs them first and restarts it afterwards.)
if [ -f "$APP_HOME/.restart_autopilot" ] && cmp -s "$APP_HOME/requirements.txt" "$APP_HOME/.venv/.installed-requirements"; then
  rm -f "$APP_HOME/.restart_autopilot"
  if [ -f "$HOME/Library/LaunchAgents/com.aitrader.autopilot.plist" ]; then
    launchctl kickstart -k "gui/$(id -u)/com.aitrader.autopilot" >/dev/null 2>&1
  fi
fi
exit 0
