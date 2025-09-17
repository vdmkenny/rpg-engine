#!/bin/bash
echo "🎮 Starting RPG Client..."
echo "Make sure the server is running on localhost:8000"
echo "Use WASD or arrow keys to move"
echo "Press Ctrl+C to quit"
echo ""
"client_venv/bin/python" client/src/client.py
