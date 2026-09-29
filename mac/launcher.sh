#!/bin/bash
# "AI Trader.app" itself. Double-clicking the app runs this.
#  1. Copies the bot into ~/AITrader (keeping your keys, data, and a backup of your settings).
#  2. Opens the AI Trader menu in a Terminal window (first time: installs Python there).
RES="$(cd "$(dirname "$0")/../Resources" && pwd)"
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
fi

cp "$RES/AI Trader Menu.command" "$APP_HOME/AI Trader Menu.command"
chmod +x "$APP_HOME/AI Trader Menu.command"
# These are the bot's own files: clear the "downloaded from the internet" flag so they can run.
xattr -dr com.apple.quarantine "$APP_HOME" 2>/dev/null
open -a Terminal "$APP_HOME/AI Trader Menu.command"
