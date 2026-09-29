#!/bin/bash
# Builds dist/AITrader-mac.zip containing "AI Trader.app": a real Mac app (a Swift program showing
# the dashboard with Apple's WebKit) plus the bot's code. Compiling needs a Mac with Xcode's tools;
# GitHub builds it on a Mac for every update.
# Usage: bash mac/build_app.sh 1.0.7
#        AITRADER_NO_COMPILE=1 bash mac/build_app.sh test   (no compiling: the Linux tests check the rest)
set -euo pipefail
VERSION="${1:-dev}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/dist/AI Trader.app"
rm -rf "$ROOT/dist"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/trader"

cd "$ROOT/trader"
cp -R aitrader run.py mcp_server.py config.yaml requirements.txt README.md .env.example "$APP/Contents/Resources/trader/"
find "$APP" -name "__pycache__" -type d -prune -exec rm -rf {} +

cp "$ROOT/mac/install.sh" "$ROOT/mac/AI Trader Menu.command" "$ROOT/mac/AppIcon.icns" "$APP/Contents/Resources/"
sed "s/__VERSION__/$VERSION/g" "$ROOT/mac/Info.plist" > "$APP/Contents/Info.plist"
echo "$VERSION" > "$APP/Contents/Resources/VERSION"

if [ "${AITRADER_NO_COMPILE:-}" = "1" ]; then
  printf '#!/bin/sh\necho "Test build: the real app is compiled on a Mac."\n' > "$APP/Contents/MacOS/AITrader"
else
  # One program for both kinds of Mac: Apple Silicon (arm64) and Intel (x86_64).
  for arch in arm64 x86_64; do
    xcrun swiftc -O -target "$arch-apple-macos12.0" -o "$ROOT/dist/AITrader-$arch" "$ROOT/mac/app/main.swift"
  done
  lipo -create -output "$APP/Contents/MacOS/AITrader" "$ROOT/dist/AITrader-arm64" "$ROOT/dist/AITrader-x86_64"
  rm "$ROOT/dist/AITrader-arm64" "$ROOT/dist/AITrader-x86_64"
fi
chmod +x "$APP/Contents/MacOS/AITrader" "$APP/Contents/Resources/install.sh" "$APP/Contents/Resources/AI Trader Menu.command"

cd "$ROOT/dist"
if command -v codesign >/dev/null; then
  # A basic ("ad-hoc") signature: Apple Silicon Macs only run signed programs. (A paid Apple
  # developer ID would also skip the "Open Anyway" step.)
  codesign --force --sign - "AI Trader.app"
  ditto -c -k --keepParent "AI Trader.app" AITrader-mac.zip
else
  zip -qry AITrader-mac.zip "AI Trader.app"
fi
echo "Built $ROOT/dist/AITrader-mac.zip (version $VERSION)"
