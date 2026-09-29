#!/bin/bash
# AI Trader menu. The first time, it installs Python and the bot's libraries (about 2 minutes).
# You can also double-click this file in your AITrader folder to open the menu.
APP_HOME="$HOME/AITrader"
cd "$APP_HOME" || exit 1
UV="$HOME/.local/bin/uv"

stop() { echo; echo "$1"; echo "Press Return to close."; read -r; exit 1; }

if [ ! -x "$UV" ]; then
  echo "First run: getting 'uv', a small tool that installs Python for the bot..."
  curl -LsSf https://astral.sh/uv/install.sh | sh || stop "Couldn't download uv. Check your internet and open AI Trader again."
fi
if [ ! -x .venv/bin/python ]; then
  echo "Installing Python 3.12 for the bot (one time)..."
  "$UV" venv --python 3.12 .venv || stop "Couldn't install Python."
fi
if ! cmp -s requirements.txt .venv/.installed-requirements; then
  echo "Installing the bot's libraries (about a minute)..."
  "$UV" pip install --python .venv/bin/python -r requirements.txt || stop "Couldn't install the libraries (see above)."
  cp requirements.txt .venv/.installed-requirements
fi
clear
exec .venv/bin/python run.py menu
