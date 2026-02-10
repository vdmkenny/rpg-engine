"""
Minimal WebSocket test client - no UI, just connection testing.
"""

import asyncio
import sys
from pathlib import Path

import aiohttp
import msgpack
import websockets

async def test_websocket_connection():
    """Test WebSocket connection from auth to welcome message."""
    
    print("=" * 60)
    print("WebSocket Connection Test")
    print("=" * 60)
    
    # Step 1: HTTP Login
    print("\n1. HTTP Login...")
    async with aiohttp.ClientSession() as session:
        login_data = {"username": "testuser_1770319678", "password": "testpass123"}
        async with session.post("http://localhost:8000/auth/login", data=login_data) as resp:
            if resp.status != 200:
                print(f"   ❌ Login failed: {resp.status}")
                text = await resp.text()
                print(f"   Error: {text}")
                return
            
            data = await resp.json()
            token = data.get("access_token")
            print(f"   ✅ Login successful, got token")
    
    # Step 2: WebSocket Connection
    print("\n2. WebSocket Connection...")
    try:
        async with websockets.connect("ws://localhost:8000/ws") as ws:
            print("   ✅ Connected to WebSocket")
            
            # Step 3: Send Auth Message
            print("\n3. Sending Authentication...")
            import uuid
            auth_msg = {
                "id": str(uuid.uuid4()),
                "type": "cmd_authenticate",
                "payload": {"token": token}
            }
            await ws.send(msgpack.packb(auth_msg))
            print("   ✅ Auth message sent")
            
            # Step 4: Wait for Response
            print("\n4. Waiting for response...")
            try:
                response_data = await asyncio.wait_for(ws.recv(), timeout=5.0)
                response = msgpack.unpackb(response_data, raw=False)
                print(f"   📨 Received: {response}")
                
                msg_type = response.get("type")
                if msg_type == "resp_success":
                    print("   ✅ Authentication successful!")
                elif msg_type == "resp_error":
                    error = response.get("payload", {}).get("error", "Unknown")
                    print(f"   ❌ Auth error: {error}")
                    return
                else:
                    print(f"   ⚠️ Unexpected response type: {msg_type}")
                    
            except asyncio.TimeoutError:
                print("   ❌ Timeout waiting for response")
                return
            
            # Step 5: Listen for Welcome Event
            print("\n5. Listening for events...")
            try:
                while True:
                    event_data = await asyncio.wait_for(ws.recv(), timeout=10.0)
                    event = msgpack.unpackb(event_data, raw=False)
                    msg_type = event.get("type")
                    print(f"   📨 Event: {msg_type}")
                    
                    if msg_type == "event_welcome":
                        payload = event.get("payload", {})
                        username = payload.get("username")
                        print(f"   ✅ Welcome received! User: {username}")
                        print(f"   📊 Full payload keys: {list(payload.keys())}")
                        break
                        
            except asyncio.TimeoutError:
                print("   ⚠️ No more events within 10 seconds")
            
            # Keep connection open for more messages
            print("\n6. Keeping connection open for 10 seconds...")
            await asyncio.sleep(10)
            print("   ✅ Waited 10 seconds")
            
    except Exception as e:
        print(f"   ❌ WebSocket error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("Test Complete")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_websocket_connection())
