#!/bin/bash
# Copyright (c) 2026 Denis Dowling (dpd@opsol.com.au)
#
# Deploy firmware/*.py files to the connected RP2350 board.
# Always runs from the repo root regardless of current directory.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIRMWARE_DIR="$SCRIPT_DIR/firmware"

echo "Deploying firmware from $FIRMWARE_DIR"
mpremote fs cp "$FIRMWARE_DIR"/*.py :

echo "Resetting board..."
mpremote reset

echo "Done."
