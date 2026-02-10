#!/usr/bin/env python3
"""
Quick test script to verify map chunks query works.
"""

import asyncio
import aiohttp
import msgpack
from common.src.protocol import MessageType

async def test_map_chunks():
    # Login first
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "http://localhost:8000/auth/login",
            data={"username": "testuser_1770319678", "password": "testpass123"}
        ) as resp:
            if resp.status != 200:
                print(f"✗ Login failed: {await resp.text()}")
                return False
            data = await resp.json()
            token = data.get("access_token")
            if not token:
                print(f"✗ No access token in response: {data}")
                return False
            print(f"✓ Logged in, got token: {token[:20]}...")
        
        # Connect WebSocket
        async with session.ws_connect(
            f"http://localhost:8000/ws",
            headers={"Authorization": f"Bearer {token}"}
        ) as ws:
            print("✓ WebSocket connected")
            
            # Receive welcome message
            msg = await ws.receive()
            welcome = msgpack.unpackb(msg.data)
            print(f"✓ Received welcome: {welcome['type']}")
            
            # Send map chunks query
            query_msg = {
                "id": "test123",
                "type": MessageType.QUERY_MAP_CHUNKS,
                "payload": {
                    "center_x": 25,
                    "center_y": 25,
                    "radius": 2
                }
            }
            await ws.send_bytes(msgpack.packb(query_msg))
            print("✓ Sent map chunks query")
            
            # Wait for response
            for _ in range(10):  # Wait for up to 10 messages
                msg = await asyncio.wait_for(ws.receive(), timeout=2.0)
                response = msgpack.unpackb(msg.data)
                print(f"  Received: {response.get('type', 'unknown')}")
                
                if response.get("type") == MessageType.RESP_DATA:
                    print(f"✓ Got data response!")
                    chunks = response.get("payload", {}).get("data", {}).get("chunks", [])
                    print(f"  Chunks count: {len(chunks)}")
                    if chunks:
                        print(f"  First chunk keys: {list(chunks[0].keys())}")
                    return True
                elif response.get("type") == MessageType.RESP_ERROR:
                    error = response.get("payload", {})
                    print(f"✗ Error response: {error}")
                    return False
            
            print("✗ No response received")
            return False

if __name__ == "__main__":
    try:
        success = asyncio.run(test_map_chunks())
        exit(0 if success else 1)
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
