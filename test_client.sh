#!/bin/bash
# Test script for client registration flow with logging

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
CLIENT_VENV="$SCRIPT_DIR/client_venv"
LOG_FILE="/tmp/rpg_client_test.log"

# Clear previous log
> "$LOG_FILE"

echo "Starting RPG Client with logging to $LOG_FILE"
echo "Press Ctrl+C when done testing"
echo ""

export PYTHONPATH="$SCRIPT_DIR:$SCRIPT_DIR/common/src"

# Run client with logging to file
"$CLIENT_VENV/bin/python" -m client.src.main 2>&1 | tee -a "$LOG_FILE"
