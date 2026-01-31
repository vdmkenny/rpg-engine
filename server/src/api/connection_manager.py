"""
THREAD-SAFE WebSocket Connection Manager for the game server.

This module provides a ConnectionManager class that allows the server to keep
track of all connected clients, grouped by the map they are currently on. This
is essential for scoping game state updates and other messages to relevant
players, improving efficiency and scalability.

KEY IMPROVEMENTS:
- Thread-safe operations using asyncio.Lock
- Atomic connection state changes
- Safe concurrent broadcasting
- Race condition prevention for connect/disconnect operations

The manager uses a dictionary to store active connections, where keys are
map_ids and values are dictionaries of client_ids to WebSocket objects. A
reverse mapping is also kept to quickly find a client's map.

Notes for the next agent:
- All connection operations are now thread-safe and atomic
- Broadcasting operations create snapshots to prevent modification during iteration
- Proper cleanup of failed connections without affecting ongoing operations
"""

import asyncio
from collections import defaultdict
from typing import Dict, List
from fastapi import WebSocket
from server.src.core.logging_config import get_logger

logger = get_logger(__name__)


class ConnectionManager:
    """
    Thread-safe WebSocket connection manager, organized by map, for real-time communication.
    """

    def __init__(self):
        """
        Initializes the ConnectionManager with thread-safety locks.
        - `connections_by_map`: Stores connections per map.
        - `client_to_map`: Maps a client_id to their current map_id for quick lookups.
        - `_connection_lock`: Protects connection state changes
        """
        self.connections_by_map: Dict[str, Dict[str, WebSocket]] = defaultdict(dict)
        self.client_to_map: Dict[str, str] = {}
        self._connection_lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, client_id: str, map_id: str):
        """
        Assigns an already-accepted WebSocket connection to a map (thread-safe).

        Args:
            websocket: The WebSocket connection object (already accepted).
            client_id: A unique identifier for the client.
            map_id: The identifier of the map the client is on.
        """
        async with self._connection_lock:
            # Check if client is already connected and cleanup old connection
            old_map_id = self.client_to_map.get(client_id)
            if old_map_id:
                logger.warning(
                    "Client reconnecting - cleaning up old connection",
                    extra={
                        "client_id": client_id,
                        "old_map_id": old_map_id,
                        "new_map_id": map_id
                    }
                )
                # Remove old connection without lock (we're already holding it)
                if client_id in self.connections_by_map[old_map_id]:
                    del self.connections_by_map[old_map_id][client_id]
                    if not self.connections_by_map[old_map_id]:
                        del self.connections_by_map[old_map_id]
            
            # Add new connection
            self.connections_by_map[map_id][client_id] = websocket
            self.client_to_map[client_id] = map_id
            
            logger.debug(
                "Client connected to map",
                extra={
                    "client_id": client_id,
                    "map_id": map_id,
                }
            )

    async def disconnect(self, client_id: str):
        """
        Removes a WebSocket connection regardless of its map (thread-safe).

        Args:
            client_id: The identifier of the client to disconnect.
        """
        async with self._connection_lock:
            map_id = self.client_to_map.pop(client_id, None)
            if map_id and client_id in self.connections_by_map[map_id]:
                del self.connections_by_map[map_id][client_id]
                
                # Clean up empty map entries
                if not self.connections_by_map[map_id]:
                    del self.connections_by_map[map_id]
                
                logger.debug(
                    "Client disconnected from map",
                    extra={
                        "client_id": client_id,
                        "map_id": map_id,
                    }
                )
            else:
                logger.warning(
                    "Attempted to disconnect unknown client",
                    extra={"client_id": client_id}
                )

    async def broadcast_to_map(self, map_id: str, message: bytes):
        """
        Broadcasts a message to all clients on a specific map (thread-safe).

        Args:
            map_id: The identifier of the map to broadcast to.
            message: The message to be sent, as bytes.
        """
        # Create a snapshot of connections to avoid modification during iteration
        connections_snapshot = []
        async with self._connection_lock:
            connections_dict = self.connections_by_map.get(map_id, {})
            connections_snapshot = list(connections_dict.items())  # Get (client_id, connection) pairs
        
        if not connections_snapshot:
            return  # No connections on this map
        
        failed_connections = []
        successful_sends = 0
        
        for client_id, connection in connections_snapshot:
            try:
                # Validate connection state before sending
                if hasattr(connection, 'client_state') and connection.client_state == 3:  # WebSocket CLOSED
                    failed_connections.append(client_id)
                    continue
                    
                await connection.send_bytes(message)
                successful_sends += 1
                
            except Exception as e:
                # Log the error for debugging and mark connection for removal
                logger.warning(
                    "Failed to send message to client",
                    extra={
                        "client_id": client_id,
                        "map_id": map_id,
                        "error": str(e)
                    }
                )
                failed_connections.append(client_id)
        
        # Clean up failed connections atomically
        if failed_connections:
            async with self._connection_lock:
                for client_id in failed_connections:
                    # Double-check the client is still connected to this map
                    current_map = self.client_to_map.get(client_id)
                    if current_map == map_id:
                        # Remove from both mappings
                        self.client_to_map.pop(client_id, None)
                        if client_id in self.connections_by_map[map_id]:
                            del self.connections_by_map[map_id][client_id]
                        
                        # Clean up empty map entries
                        if not self.connections_by_map[map_id]:
                            del self.connections_by_map[map_id]
            
            logger.debug(
                "Broadcast completed with cleanup",
                extra={
                    "map_id": map_id,
                    "failed_connections": len(failed_connections),
                }
            )

    async def broadcast_to_all(self, message: bytes):
        """
        Broadcasts a message to all connected clients across all maps.

        Args:
            message: The message to be sent, as bytes.
        """
        for map_id in list(self.connections_by_map.keys()):
            await self.broadcast_to_map(map_id, message)

    async def get_all_connections(self) -> List[Dict[str, str]]:
        """
        Get a list of all connections with their metadata (thread-safe).
        
        Returns:
            List of dictionaries with connection info: [{'username': str, 'map_id': str}]
        """
        connections = []
        async with self._connection_lock:
            for map_id, map_connections in self.connections_by_map.items():
                for client_id in map_connections.keys():
                    connections.append({
                        'username': client_id,  # client_id is username in our setup
                        'map_id': map_id
                    })
        return connections

    async def broadcast_to_users(self, usernames: List[str], message: bytes):
        """
        Broadcasts a message to specific users by username (thread-safe).

        Args:
            usernames: List of usernames to send the message to.
            message: The message to be sent, as bytes.
        """
        username_set = set(usernames)
        failed_connections = []
        
        # Create snapshot of all connections
        connections_snapshot = []
        async with self._connection_lock:
            for map_id in list(self.connections_by_map.keys()):
                connections = self.connections_by_map.get(map_id, {})
                for client_id, connection in connections.items():
                    if client_id in username_set:
                        connections_snapshot.append((client_id, connection, map_id))
        
        # Send messages without holding the lock
        for client_id, connection, map_id in connections_snapshot:
            try:
                # Validate connection state before sending
                if hasattr(connection, 'client_state') and connection.client_state == 3:  # WebSocket CLOSED
                    failed_connections.append(client_id)
                    continue
                    
                await connection.send_bytes(message)
            except Exception as e:
                logger.warning(
                    "Failed to send message to user",
                    extra={
                        "client_id": client_id,
                        "error": str(e)
                    }
                )
                failed_connections.append(client_id)
        
        # Clean up failed connections atomically
        if failed_connections:
            for client_id in failed_connections:
                await self.disconnect(client_id)

    async def send_personal_message(self, username: str, message: bytes):
        """
        Sends a message to a specific user (thread-safe).

        Args:
            username: The username to send the message to.
            message: The message to be sent, as bytes.
        """
        # Get connection info under lock
        connection_info = None
        async with self._connection_lock:
            map_id = self.client_to_map.get(username)
            if map_id and username in self.connections_by_map[map_id]:
                connection_info = (self.connections_by_map[map_id][username], map_id)
        
        if not connection_info:
            logger.warning(
                "Attempted to send personal message to unknown user",
                extra={"username": username}
            )
            return
            
        connection, map_id = connection_info
        try:
            # Validate connection state before sending
            if hasattr(connection, 'client_state') and connection.client_state == 3:  # WebSocket CLOSED
                await self.disconnect(username)
                return
                
            await connection.send_bytes(message)
            logger.debug(
                "Personal message sent successfully",
                extra={"username": username}
            )
        except Exception as e:
            logger.warning(
                "Failed to send personal message",
                extra={
                    "username": username,
                    "error": str(e)
                }
            )
            await self.disconnect(username)

    async def clear(self):
        """
        Clear all connections (thread-safe). Used for test isolation.
        """
        async with self._connection_lock:
            self.connections_by_map.clear()
            self.client_to_map.clear()
