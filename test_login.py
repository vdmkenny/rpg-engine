"""
Simple test client for debugging.
"""

import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "common" / "src"))

import aiohttp
from client.src.config import get_config

async def test_login():
    """Test the login flow."""
    config = get_config()
    
    print(f"Testing login to {config.server.base_url}")
    
    async with aiohttp.ClientSession() as session:
        # Test login
        login_data = {"username": "testuser1738770000", "password": "testpass123"}
        async with session.post(f"{config.server.base_url}/auth/login", data=login_data) as resp:
            print(f"Login status: {resp.status}")
            if resp.status == 200:
                data = await resp.json()
                token = data.get("access_token")
                print(f"Got token: {token[:20]}..." if token else "No token")
            else:
                text = await resp.text()
                print(f"Login error: {text}")

if __name__ == "__main__":
    asyncio.run(test_login())
