"""
THREAD-SAFE WebSocket Connection Manager for the game server.

This module provides a ConnectionManager class that allows the server to keep
track of all connected clients, grouped by the map they are currently on. This
is essential for scoping game state updates and other messages to relevant
players, improving efficiency and scalability.

KEY DESIGN PRINCIPLE:
- player_id (int) is the ONLY internal identifier for players
- username is for display/authentication only, never for lookups

KEY IMPROVEMENTS:
- Thread-safe operations using asyncio.Lock
- Atomic connection state changes
- Safe concurrent broadcasting
- Race condition prevention for connect/disconnect operations
"""

import asyncio
from collections import defaultdict
from typing import Dict, List, Any
from fastapi import WebSocket
from starlette.websockets import WebSocketState
from server.src.core.logging_config import get_logger

logger = get_logger(__name__)


class ConnectionManager:
    """
    Thread-safe WebSocket connection manager, organized by map, for real-time communication.
    
    All player identification uses player_id (int), never username.
    """

    def __init__(self):
        """
        Initializes the ConnectionManager with thread-safety locks.
        - `connections_by_map`: Stores connections per map: {map_id: {player_id: WebSocket}}
        - `player_to_map`: Maps a player_id to their current map_id for quick lookups
        - `_connection_lock`: Protects connection state changes
        """
        self.connections_by_map: Dict[str, Dict[int, WebSocket]] = defaultdict(dict)
        self.player_to_map: Dict[int, str] = {}
        self._connection_lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, player_id: int, map_id: str):
        """
        Assigns an already-accepted WebSocket connection to a map (thread-safe).

        Args:
            websocket: The WebSocket connection object (already accepted).
            player_id: The player's unique database ID.
            map_id: The identifier of the map the player is on.
        """
        async with self._connection_lock:
            # Check if player is already connected and cleanup old connection
            old_map_id = self.player_to_map.get(player_id)
            if old_map_id:
                logger.warning(
                    "Player reconnecting - cleaning up old connection",
                    extra={
                        "player_id": player_id,
                        "old_map_id": old_map_id,
                        "new_map_id": map_id
                    }
                )
                # Remove old connection without lock (we're already holding it)
                if player_id in self.connections_by_map[old_map_id]:
                    del self.connections_by_map[old_map_id][player_id]
                    if not self.connections_by_map[old_map_id]:
                        del self.connections_by_map[old_map_id]
            
            # Add new connection
            self.connections_by_map[map_id][player_id] = websocket
            self.player_to_map[player_id] = map_id
            
            logger.debug(
                "Player connected to map",
                extra={
                    "player_id": player_id,
                    "map_id": map_id,
                }
            )

    async def disconnect(self, player_id: int):
        """
        Removes a WebSocket connection regardless of its map (thread-safe).

        Args:
            player_id: The player's unique database ID.
        """
        async with self._connection_lock:
            map_id = self.player_to_map.pop(player_id, None)
            if map_id and player_id in self.connections_by_map[map_id]:
                del self.connections_by_map[map_id][player_id]
                
                # Clean up empty map entries
                if not self.connections_by_map[map_id]:
                    del self.connections_by_map[map_id]
                
                logger.debug(
                    "Player disconnected from map",
                    extra={
                        "player_id": player_id,
                        "map_id": map_id,
                    }
                )
            else:
                logger.warning(
                    "Attempted to disconnect unknown player",
                    extra={"player_id": player_id}
                )

    async def broadcast_to_map(self, map_id: str, message: bytes):
        """
        Broadcasts a message to all players on a specific map (thread-safe).

        Args:
            map_id: The identifier of the map to broadcast to.
            message: The message to be sent, as bytes.
        """
        # Create a snapshot of connections to avoid modification during iteration
        connections_snapshot = []
        async with self._connection_lock:
            connections_dict = self.connections_by_map.get(map_id, {})
            connections_snapshot = list(connections_dict.items())  # Get (player_id, connection) pairs
        
        if not connections_snapshot:
            return  # No connections on this map
        
        failed_connections = []
        successful_sends = 0
        
        for player_id, connection in connections_snapshot:
            try:
                # Validate connection state before sending
                if hasattr(connection, 'client_state') and connection.client_state == WebSocketState.DISCONNECTED:
                    failed_connections.append(player_id)
                    continue
                    
                await connection.send_bytes(message)
                successful_sends += 1
                
            except Exception as e:
                # Log the error for debugging and mark connection for removal
                logger.warning(
                    "Failed to send message to player",
                    extra={
                        "player_id": player_id,
                        "map_id": map_id,
                        "error": str(e)
                    }
                )
                failed_connections.append(player_id)
        
        # Clean up failed connections atomically
        if failed_connections:
            async with self._connection_lock:
                for player_id in failed_connections:
                    # Double-check the player is still connected to this map
                    current_map = self.player_to_map.get(player_id)
                    if current_map == map_id:
                        # Remove from both mappings
                        self.player_to_map.pop(player_id, None)
                        if player_id in self.connections_by_map[map_id]:
                            del self.connections_by_map[map_id][player_id]
                        
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
        Broadcasts a message to all connected players across all maps.

        Args:
            message: The message to be sent, as bytes.
        """
        for map_id in list(self.connections_by_map.keys()):
            await self.broadcast_to_map(map_id, message)

    async def get_all_connections(self) -> List[Dict[str, Any]]:
        """
        Get a list of all connections with their metadata (thread-safe).
        
        Returns:
            List of dictionaries with connection info: [{'player_id': int, 'map_id': str}]
        """
        connections = []
        async with self._connection_lock:
            for map_id, map_connections in self.connections_by_map.items():
                for player_id in map_connections.keys():
                    connections.append({
                        'player_id': player_id,
                        'map_id': map_id
                    })
        return connections

    async def broadcast_to_players(self, player_ids: List[int], message: bytes):
        """
        Broadcasts a message to specific players by player_id (thread-safe).

        Args:
            player_ids: List of player IDs to send the message to.
            message: The message to be sent, as bytes.
        """
        player_id_set = set(player_ids)
        failed_connections = []
        
        # Create snapshot of all connections
        connections_snapshot = []
        async with self._connection_lock:
            for map_id in list(self.connections_by_map.keys()):
                connections = self.connections_by_map.get(map_id, {})
                for player_id, connection in connections.items():
                    if player_id in player_id_set:
                        connections_snapshot.append((player_id, connection, map_id))
        
        # Send messages without holding the lock
        for player_id, connection, map_id in connections_snapshot:
            try:
                # Validate connection state before sending
                if hasattr(connection, 'client_state') and connection.client_state == WebSocketState.DISCONNECTED:
                    failed_connections.append(player_id)
                    continue
                    
                await connection.send_bytes(message)
            except Exception as e:
                logger.warning(
                    "Failed to send message to player",
                    extra={
                        "player_id": player_id,
                        "error": str(e)
                    }
                )
                failed_connections.append(player_id)
        
        # Clean up failed connections atomically
        if failed_connections:
            for player_id in failed_connections:
                await self.disconnect(player_id)

    async def send_personal_message(self, player_id: int, message: bytes):
        """
        Sends a message to a specific player (thread-safe).

        Args:
            player_id: The player's unique database ID.
            message: The message to be sent, as bytes.
        """
        # Get connection info under lock
        connection_info = None
        async with self._connection_lock:
            map_id = self.player_to_map.get(player_id)
            if map_id and player_id in self.connections_by_map[map_id]:
                connection_info = (self.connections_by_map[map_id][player_id], map_id)
        
        if not connection_info:
            logger.warning(
                "Attempted to send personal message to unknown player",
                extra={"player_id": player_id}
            )
            return
            
        connection, map_id = connection_info
        try:
            # Validate connection state before sending
            if hasattr(connection, 'client_state') and connection.client_state == WebSocketState.DISCONNECTED:
                await self.disconnect(player_id)
                return
                
            await connection.send_bytes(message)
            logger.debug(
                "Personal message sent successfully",
                extra={"player_id": player_id}
            )
        except Exception as e:
            logger.warning(
                "Failed to send personal message",
                extra={
                    "player_id": player_id,
                    "error": str(e)
                }
            )
            await self.disconnect(player_id)

    def get_player_websocket(self, player_id: int) -> WebSocket | None:
        """
        Get the WebSocket connection for a specific player (not thread-safe, use with caution).
        
        For use in game loop where we already have the player_id and need the websocket.
        
        Args:
            player_id: The player's unique database ID.
            
        Returns:
            WebSocket connection or None if not found.
        """
        map_id = self.player_to_map.get(player_id)
        if map_id:
            return self.connections_by_map.get(map_id, {}).get(player_id)
        return None

    async def clear(self):
        """
        Clear all connections (thread-safe). Used for test isolation.
        """
        async with self._connection_lock:
            self.connections_by_map.clear()
            self.player_to_map.clear()

    async def disconnect_all(self):
        """
        Disconnect all active WebSocket connections and clear data structures (thread-safe).

        This method:
        1. Gets all active player connections
        2. Properly closes each WebSocket connection
        3. Clears the internal data structures

        Used for graceful shutdown or mass disconnection scenarios.
        """
        async with self._connection_lock:
            connections_to_close = []

            for map_id, map_connections in self.connections_by_map.items():
                for player_id, websocket in map_connections.items():
                    connections_to_close.append((player_id, websocket, map_id))

            self.connections_by_map.clear()
            self.player_to_map.clear()

        for player_id, websocket, map_id in connections_to_close:
            try:
                await websocket.close()
                logger.debug(
                    "WebSocket connection closed for player",
                    extra={
                        "player_id": player_id,
                        "map_id": map_id,
                    }
                )
            except Exception as e:
                logger.warning(
                    "Error closing WebSocket connection",
                    extra={
                        "player_id": player_id,
                        "map_id": map_id,
                        "error": str(e),
                    }
                )
