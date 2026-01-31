"""
GameStateManager State Access Helper

Handles username-based queries, batch operations, and map-based state access.
Keeps the main GSM class focused on core CRUD operations.
"""

from typing import Any, Dict, List, Optional, Tuple
import traceback

from glide import GlideClient
from server.src.core.logging_config import get_logger

logger = get_logger(__name__)


class GSMStateAccess:
    """Helper class for advanced state access operations."""
    
    def __init__(self, gsm):
        """Initialize with reference to main GameStateManager."""
        self._gsm = gsm
    
    @property
    def valkey(self) -> Optional[GlideClient]:
        """Get Valkey client from main GSM."""
        return self._gsm.valkey
    
    async def get_player_state_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Get player state by username (transition helper for legacy code).
        
        Args:
            username: Player's username
            
        Returns:
            Player state dict or None if not found
        """
        if not self.valkey:
            return None
            
        from ..connection_service import ConnectionService
        player_id = ConnectionService.get_online_player_id_by_username(username)
        if not player_id:
            return None
            
        return await self._gsm.get_player_full_state(player_id)
    
    async def set_player_hp_by_username(
        self, 
        username: str, 
        current_hp: int, 
        max_hp: Optional[int] = None
    ) -> None:
        """
        Set player HP by username (transition helper for game loop).
        
        Args:
            username: Player's username
            current_hp: New current HP value
            max_hp: New max HP value (optional)
        """
        if not self.valkey:
            logger.warning("No Valkey connection for HP update", extra={"username": username})
            return
            
        from ..connection_service import ConnectionService
        player_id = ConnectionService.get_online_player_id_by_username(username)
        if not player_id:
            logger.warning("Player ID not found for HP update", extra={"username": username})
            return
            
        await self._gsm.set_player_hp(player_id, current_hp, max_hp)
    
    async def batch_update_player_hp(
        self,
        hp_updates: List[tuple[str, int]]  # List of (username, new_hp) tuples
    ) -> None:
        """
        Batch update HP for multiple players using individual operations.
        Optimized for HP regeneration processing in game loop.
        
        Args:
            hp_updates: List of (username, new_current_hp) tuples
        """
        if not self.valkey or not hp_updates:
            return
        
        # Process each HP update individually (since pipeline isn't available)
        # TODO: This should be refactored to use player IDs directly instead of username lookups
        for username, new_hp in hp_updates:
            # Use ConnectionService to get player ID
            from ..connection_service import ConnectionService
            player_id = ConnectionService.get_online_player_id_by_username(username)
            if player_id:
                player_key = f"player:{player_id}"
                await self.valkey.hset(player_key, mapping={"current_hp": str(new_hp)})
                # Mark dirty for database sync
                await self.valkey.sadd("dirty:position", [str(player_id)])
        
        logger.debug(
            "Batch HP regeneration completed",
            extra={"updated_players": len(hp_updates)}
        )
    
    async def get_multiple_players_by_usernames(
        self, 
        usernames: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get full state for multiple players by username using individual operations.
        
        Args:
            usernames: List of player usernames
            
        Returns:
            Dict mapping username to player state
        """
        if not usernames:
            return {}
        
        # Get player IDs from ConnectionService
        from ..connection_service import ConnectionService
        username_to_id = {}
        for username in usernames:
            player_id = ConnectionService.get_online_player_id_by_username(username)
            if player_id:
                username_to_id[username] = player_id
        
        if not username_to_id:
            return {}
        
        # Use individual operations for each player
        result = {}
        for username, player_id in username_to_id.items():
            state = await self._gsm.get_player_full_state(player_id)
            if state:
                result[username] = state
        
        return result
    
    async def get_players_on_map(self, map_id: str) -> List[Dict[str, Any]]:
        """
        Get all online players on a specific map.
        
        Args:
            map_id: Map identifier
            
        Returns:
            List of player state dicts for players on the map
        """
        if not self.valkey:
            return []
            
        players_on_map = []
        
        # Check all online players for map match
        from ..connection_service import ConnectionService
        online_players = ConnectionService.get_online_player_ids()
        for player_id in online_players:
            state = await self._gsm.get_player_full_state(player_id)
            if state and state.get("map_id") == map_id:
                players_on_map.append(state)
        
        return players_on_map
    
    async def get_player_positions_on_map(self, map_id: str) -> Dict[int, Tuple[int, int]]:
        """
        Get player positions for all players on a specific map.
        
        Args:
            map_id: Map identifier
            
        Returns:
            Dict mapping player_id to (x, y) position tuple
        """
        if not self.valkey:
            return {}
            
        positions = {}
        
        # Get positions for all online players on the map
        from ..connection_service import ConnectionService
        online_players = ConnectionService.get_online_player_ids()
        for player_id in online_players:
            position = await self._gsm.get_player_position(player_id)
            if position and position.get("map_id") == map_id:
                x = position.get("x")
                y = position.get("y") 
                if x is not None and y is not None:
                    positions[player_id] = (x, y)
        
        return positions
    
    async def update_player_state(
        self, 
        player_id: int, 
        updates: Dict[str, Any]
    ) -> None:
        """
        Atomically update multiple player state fields.
        
        Args:
            player_id: Player ID
            updates: Dict of field names to new values
        """
        if not self.valkey or not self._gsm.is_online(player_id):
            return
            
        player_key = f"player:{player_id}"
        
        # Convert all values to strings for Valkey storage
        string_updates = {}
        for field, value in updates.items():
            if isinstance(value, (int, float)):
                string_updates[field] = str(value)
            elif isinstance(value, bool):
                string_updates[field] = "true" if value else "false"
            else:
                string_updates[field] = str(value)
        
        try:
            await self.valkey.hset(player_key, string_updates)
            
            # Mark as dirty if position or HP changed
            if any(field in updates for field in ["x", "y", "map_id", "current_hp", "max_hp"]):
                await self.valkey.sadd("dirty:position", str(player_id))
                
            logger.debug(
                "Player state updated",
                extra={
                    "player_id": player_id,
                    "updated_fields": list(updates.keys())
                }
            )
        except Exception as e:
            logger.error(
                "Failed to update player state",
                extra={
                    "player_id": player_id,
                    "updates": updates,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }
            )
            raise
    
    async def exists_player_state(self, player_id: int) -> bool:
        """
        Check if player state exists in Valkey.
        
        Args:
            player_id: Player ID
            
        Returns:
            True if player state exists
        """
        if not self.valkey:
            return False
            
        player_key = f"player:{player_id}"
        try:
            result = await self.valkey.exists([player_key])
            return result > 0
        except Exception as e:
            logger.error(
                "Failed to check player state existence",
                extra={
                    "player_id": player_id,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }
            )
            return False