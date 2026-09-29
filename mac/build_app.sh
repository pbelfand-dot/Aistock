#!/bin/bash
# Builds dist/AITrader-mac.zip containing "AI Trader.app": a small launcher plus the bot's code.
# Usage: bash mac/build_app.sh 1.0.7      (GitHub Actions runs this for every update)
set -euo pipefail
VERSION="${1:-dev}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/dist/AI Trader.app"
rm -rf "$ROOT/dist"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/trader"

cd "$ROOT/trader"
cp -R aitrader run.py mcp_server.py config.yaml requirements.txt README.md .env.example "$APP/Contents/Resources/trader/"
find "$APP" -name "__pycache__" -type d -prune -exec rm -rf {} +

cp "$ROOT/mac/launcher.sh" "$APP/Contents/MacOS/AITrader"
cp "$ROOT/mac/AI Trader Menu.command" "$APP/Contents/Resources/"
sed "s/__VERSION__/$VERSION/g" "$ROOT/mac/Info.plist" > "$APP/Contents/Info.plist"
echo "$VERSION" > "$APP/Contents/Resources/VERSION"
chmod +x "$APP/Contents/MacOS/AITrader" "$APP/Contents/Resources/AI Trader Menu.command"

cd "$ROOT/dist"
zip -qry AITrader-mac.zip "AI Trader.app"
echo "Built $ROOT/dist/AITrader-mac.zip (version $VERSION)"
