"""
Minimal WebSocket test client using httpx-ws - runs in container.
"""

import asyncio
import sys
import uuid
import msgpack
import httpx
from httpx_ws import aconnect_ws

async def test_websocket_connection():
    """Test WebSocket connection from auth to welcome message."""
    
    print("=" * 60)
    print("WebSocket Connection Test - Error Trigger")
    print("=" * 60)
    
    # Step 1: HTTP Login
    print("\n1. HTTP Login...")
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        login_data = {"username": "testuser_1770319678", "password": "testpass123"}
        resp = await client.post("/auth/login", data=login_data)
        
        if resp.status_code != 200:
            print(f"   ❌ Login failed: {resp.status_code}")
            print(f"   Error: {resp.text}")
            return
        
        data = resp.json()
        token = data.get("access_token")
        print(f"   ✅ Login successful, got token")
    
    # Step 2: WebSocket Connection
    print("\n2. WebSocket Connection...")
    try:
        async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
            async with aconnect_ws("/ws", client) as ws:
                print("   ✅ Connected to WebSocket")
                
                # Step 3: Send Auth Message
                print("\n3. Sending Authentication...")
                auth_msg = {
                    "id": str(uuid.uuid4()),
                    "type": "cmd_authenticate",
                    "payload": {"token": token}
                }
                await ws.send_bytes(msgpack.packb(auth_msg))
                print("   ✅ Auth message sent")
                
                # Step 4: Wait for Response
                print("\n4. Waiting for response...")
                try:
                    response_data = await asyncio.wait_for(ws.receive_bytes(), timeout=5.0)
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
                        event_data = await asyncio.wait_for(ws.receive_bytes(), timeout=10.0)
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
                    print("   ⚠️ No welcome event received within 10 seconds")
                
                # Keep connection open for more messages
                print("\n6. Keeping connection open for 10 seconds to trigger errors...")
                await asyncio.sleep(10)
                print("   ✅ Waited 10 seconds")
                
    except Exception as e:
        print(f"   ❌ WebSocket error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("Test Complete - Check server logs for errors!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_websocket_connection())
