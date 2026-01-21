"""
Manages active WebSocket connections for the game server, organized by map.

This module provides a ConnectionManager class that allows the server to keep
track of all connected clients, grouped by the map they are currently on. This
is essential for scoping game state updates and other messages to relevant
players, improving efficiency and scalability.

The manager uses a dictionary to store active connections, where keys are
map_ids and values are dictionaries of client_ids to WebSocket objects. A
reverse mapping is also kept to quickly find a client's map.

Notes for the next agent:
- The current implementation uses simple dictionaries to store connections.
  For a larger-scale application, consider using a more robust solution that
  can be shared across multiple server instances, such as a Redis-based
  pub/sub system.
- The data structures are not thread-safe. While FastAPI's async nature
  minimizes risks, be mindful of potential race conditions if the logic
  becomes more complex or if threading is introduced.
"""

from collections import defaultdict
from typing import Dict, List
from fastapi import WebSocket


class ConnectionManager:
    """
    Manages WebSocket connections, organized by map, for real-time communication.
    """

    def __init__(self):
        """
        Initializes the ConnectionManager.
        - `connections_by_map`: Stores connections per map.
        - `client_to_map`: Maps a client_id to their current map_id for quick lookups.
        """
        self.connections_by_map: Dict[str, Dict[str, WebSocket]] = defaultdict(dict)
        self.client_to_map: Dict[str, str] = {}

    async def connect(self, websocket: WebSocket, client_id: str, map_id: str):
        """
        Assigns an already-accepted WebSocket connection to a map.

        Args:
            websocket: The WebSocket connection object (already accepted).
            client_id: A unique identifier for the client.
            map_id: The identifier of the map the client is on.
        """
        self.connections_by_map[map_id][client_id] = websocket
        self.client_to_map[client_id] = map_id

    def disconnect(self, client_id: str):
        """
        Removes a WebSocket connection regardless of its map.

        Args:
            client_id: The identifier of the client to disconnect.
        """
        map_id = self.client_to_map.pop(client_id, None)
        if map_id and client_id in self.connections_by_map[map_id]:
            del self.connections_by_map[map_id][client_id]
            # Clean up empty map entries
            if not self.connections_by_map[map_id]:
                del self.connections_by_map[map_id]

    async def broadcast_to_map(self, map_id: str, message: bytes):
        """
        Broadcasts a message to all clients on a specific map.

        Args:
            map_id: The identifier of the map to broadcast to.
            message: The message to be sent, as bytes.
        """
        # Get a snapshot of connections to avoid modification during iteration
        connections_dict = self.connections_by_map.get(map_id, {})
        connections_list = list(connections_dict.items())  # Get (client_id, connection) pairs
        
        failed_connections = []
        
        for client_id, connection in connections_list:
            try:
                # Validate connection state before sending
                if hasattr(connection, 'client_state') and connection.client_state == 3:  # WebSocket CLOSED
                    failed_connections.append(client_id)
                    continue
                    
                await connection.send_bytes(message)
                
            except Exception as e:
                # Log the error for debugging and mark connection for removal
                print(f"Failed to send message to client {client_id}: {e}")
                failed_connections.append(client_id)
        
        # Clean up failed connections immediately
        for client_id in failed_connections:
            self.disconnect(client_id)

    async def broadcast_to_all(self, message: bytes):
        """
        Broadcasts a message to all connected clients across all maps.

        Args:
            message: The message to be sent, as bytes.
        """
        for map_id in list(self.connections_by_map.keys()):
            await self.broadcast_to_map(map_id, message)

    def get_all_connections(self) -> List[Dict[str, str]]:
        """
        Get a list of all connections with their metadata.
        
        Returns:
            List of dictionaries with connection info: [{'username': str, 'map_id': str}]
        """
        connections = []
        for map_id, map_connections in self.connections_by_map.items():
            for client_id in map_connections.keys():
                connections.append({
                    'username': client_id,  # client_id is username in our setup
                    'map_id': map_id
                })
        return connections

    async def broadcast_to_users(self, usernames: List[str], message: bytes):
        """
        Broadcasts a message to specific users by username.

        Args:
            usernames: List of usernames to send the message to.
            message: The message to be sent, as bytes.
        """
        username_set = set(usernames)
        failed_connections = []
        
        for map_id in list(self.connections_by_map.keys()):
            connections = self.connections_by_map.get(map_id, {})
            for client_id, connection in connections.items():
                if client_id in username_set:
                    try:
                        # Validate connection state before sending
                        if hasattr(connection, 'client_state') and connection.client_state == 3:  # WebSocket CLOSED
                            failed_connections.append(client_id)
                            continue
                            
                        await connection.send_bytes(message)
                    except Exception as e:
                        print(f"Failed to send message to user {client_id}: {e}")
                        failed_connections.append(client_id)
        
        # Clean up failed connections
        for client_id in failed_connections:
            self.disconnect(client_id)

    async def send_personal_message(self, username: str, message: bytes):
        """
        Sends a message to a specific user.

        Args:
            username: The username to send the message to.
            message: The message to be sent, as bytes.
        """
        map_id = self.client_to_map.get(username)
        if map_id and username in self.connections_by_map[map_id]:
            connection = self.connections_by_map[map_id][username]
            try:
                # Validate connection state before sending
                if hasattr(connection, 'client_state') and connection.client_state == 3:  # WebSocket CLOSED
                    self.disconnect(username)
                    return
                    
                await connection.send_bytes(message)
            except Exception as e:
                print(f"Failed to send personal message to {username}: {e}")
                self.disconnect(username)

    def clear(self):
        """
        Clear all connections. Used for test isolation.
        """
        self.connections_by_map.clear()
        self.client_to_map.clear()
