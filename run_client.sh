#!/bin/bash
# Run script for the RPG Client v2.0

echo "🎮 Starting RPG Client v2.0..."
echo "Server: http://localhost:8000"
echo ""
echo "=== SCREEN FLOW ==="
echo "1. Server Select Screen - Click on 'Local Server' or press ENTER"
echo "2. Login Screen - Click 'Go to Register' button to switch modes"
echo "3. Register Screen - Enter username, password, email"
echo "4. Click 'Register' button to submit"
echo ""
echo "Press Ctrl+C to quit"
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
CLIENT_VENV="$SCRIPT_DIR/client_venv"

# Check if client_venv exists
if [ ! -d "$CLIENT_VENV" ]; then
    echo "Error: client_venv not found at $CLIENT_VENV"
    exit 1
fi

# Set PYTHONPATH to include the project root and common
export PYTHONPATH="$SCRIPT_DIR:$SCRIPT_DIR/common/src"

# Run the new client using client_venv
exec "$CLIENT_VENV/bin/python" -m client.src.main "$@"
