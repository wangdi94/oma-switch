#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing oma-switch..."
pip install "$SCRIPT_DIR"
echo ""
echo "✓ oma-switch installed successfully"
echo "Run 'oma-switch help' to get started"
