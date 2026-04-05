#!/bin/bash
# Jarvis 1.0 — Mac Setup Script
# Run from the repo root or agent/ directory on your MacBook.

set -e

PYTHON=/opt/homebrew/bin/python3.13
VENV=~/jarvis-venv
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Checking for Homebrew Python 3.13..."
if [ ! -f "$PYTHON" ]; then
    echo "ERROR: $PYTHON not found. Install it with: brew install python@3.13"
    exit 1
fi

echo "==> Creating virtual environment at $VENV..."
$PYTHON -m venv "$VENV"

echo "==> Installing dependencies..."
source "$VENV/bin/activate"
pip install --quiet --upgrade pip
pip install -r "$SCRIPT_DIR/requirements.txt"

echo "==> Adding 'jarvis' alias to ~/.zshrc..."
ALIAS_LINE="alias jarvis=\"source $VENV/bin/activate && cd $SCRIPT_DIR\""
if ! grep -qF "alias jarvis=" ~/.zshrc 2>/dev/null; then
    echo "" >> ~/.zshrc
    echo "# Jarvis 1.0" >> ~/.zshrc
    echo "$ALIAS_LINE" >> ~/.zshrc
    echo "    Added alias."
else
    echo "    Alias already exists, skipping."
fi

echo ""
echo "✓ Python environment ready."
echo ""
echo "Next steps:"
echo "  1. Copy your .env file to: $SCRIPT_DIR/.env"
echo "     (or run: cp $SCRIPT_DIR/.env.example $SCRIPT_DIR/.env  and fill in secrets)"
echo "  2. Copy credentials.json to: $SCRIPT_DIR/credentials.json"
echo "     (AirDrop or USB from your PC)"
echo "  3. Open a new terminal tab (to load the alias), then type:"
echo "       jarvis"
echo "       python3 personalhq/morning_briefing.py"
