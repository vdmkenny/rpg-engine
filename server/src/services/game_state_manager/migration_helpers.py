"""
GameStateManager Migration Helpers

Handles transition from username-based keys to player_id-based keys.
Provides utilities for migration and legacy key cleanup.
"""

from typing import Any, Dict, List, Optional
from glide import GlideClient
from server.src.core.logging_config import get_logger

logger = get_logger(__name__)


class GSMMigrationHelpers:
    """Helper class for migration-related operations."""
    
    def __init__(self, gsm):
        """Initialize with reference to main GameStateManager."""
        self._gsm = gsm
    
    @property
    def valkey(self) -> Optional[GlideClient]:
        """Get Valkey client from main GSM."""
        return self._gsm.valkey
    
    async def migrate_username_key_to_player_id(
        self, 
        username: str, 
        player_id: int
    ) -> bool:
        """
        Migrate old username-based keys to player_id-based keys.
        
        Args:
            username: Player's username  
            player_id: Player's ID
            
        Returns:
            True if migration was performed
        """
        if not self.valkey:
            return False
            
        try:
            old_key = f"player:{username}"
            new_key = f"player:{player_id}"
            
            # Check if old key exists
            old_data = await self.valkey.hgetall(old_key)
            if not old_data:
                return False  # Nothing to migrate
            
            # Copy data to new key format
            new_data = {}
            for field, value in old_data.items():
                field_str = field.decode() if isinstance(field, bytes) else field
                value_str = value.decode() if isinstance(value, bytes) else value
                new_data[field_str] = value_str
            
            # Ensure player_id is stored in the new format
            new_data["player_id"] = str(player_id)
            
            # Set the new key
            await self.valkey.hset(new_key, new_data)
            
            # Delete the old key
            await self.valkey.delete([old_key])
            
            logger.info(
                "Migrated player key format",
                extra={
                    "username": username,
                    "player_id": player_id,
                    "old_key": old_key,
                    "new_key": new_key
                }
            )
            
            return True
            
        except Exception as e:
            logger.error(
                "Failed to migrate player key",
                extra={
                    "username": username,
                    "player_id": player_id,
                    "error": str(e)
                }
            )
            return False
    
    async def cleanup_legacy_username_keys(self, username: str) -> None:
        """
        Remove old username-based keys after migration.
        
        Args:
            username: Player's username
        """
        if not self.valkey:
            return
            
        try:
            legacy_keys = [
                f"player:{username}",
                f"inventory:{username}",  # In case any exist
                f"equipment:{username}",  # In case any exist  
                f"skills:{username}",     # In case any exist
            ]
            
            # Check which keys exist before deletion
            existing_keys = []
            for key in legacy_keys:
                exists = await self.valkey.exists([key])
                if exists > 0:
                    existing_keys.append(key)
            
            if existing_keys:
                await self.valkey.delete(existing_keys)
                logger.info(
                    "Cleaned up legacy username keys",
                    extra={"username": username, "deleted_keys": existing_keys}
                )
            
        except Exception as e:
            logger.error(
                "Failed to cleanup legacy keys",
                extra={"username": username, "error": str(e)}
            )
    
    async def validate_migration_consistency(self) -> Dict[str, Any]:
        """
        Validate that migration is consistent - no mixed key formats.
        
        Returns:
            Dict with validation results
        """
        if not self.valkey:
            return {"status": "error", "message": "No Valkey connection"}
        
        try:
            # Look for any remaining username-based player keys
            username_keys = await self.valkey.keys("player:*")
            
            legacy_keys = []
            modern_keys = []
            
            for key in username_keys:
                key_str = key.decode() if isinstance(key, bytes) else key
                
                # Check if the key is in old format (contains non-numeric characters after "player:")
                key_suffix = key_str.split(":", 1)[1]
                
                try:
                    # If this succeeds, it's a player_id (modern format)
                    int(key_suffix)
                    modern_keys.append(key_str)
                except ValueError:
                    # If this fails, it's a username (legacy format)
                    legacy_keys.append(key_str)
            
            validation_result = {
                "status": "success",
                "total_player_keys": len(username_keys),
                "modern_keys": len(modern_keys),
                "legacy_keys": len(legacy_keys),
                "legacy_key_list": legacy_keys,
                "migration_complete": len(legacy_keys) == 0
            }
            
            if legacy_keys:
                logger.warning(
                    "Found legacy username-based keys",
                    extra={"legacy_keys": legacy_keys}
                )
            else:
                logger.info("Migration validation passed - no legacy keys found")
            
            return validation_result
            
        except Exception as e:
            logger.error("Migration validation failed", extra={"error": str(e)})
            return {"status": "error", "message": str(e)}
    
    async def get_migration_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about the current state of migration.
        
        Returns:
            Dict with migration statistics
        """
        if not self.valkey:
            return {"status": "error", "message": "No Valkey connection"}
        
        try:
            stats = {
                "online_players": len(self._gsm.get_online_player_ids()),
                "total_inventories": 0,
                "total_equipment": 0, 
                "total_skills": 0,
                "total_ground_items": 0
            }
            
            # Count inventory keys
            inventory_keys = await self.valkey.keys("inventory:*")
            stats["total_inventories"] = len(inventory_keys)
            
            # Count equipment keys
            equipment_keys = await self.valkey.keys("equipment:*")
            stats["total_equipment"] = len(equipment_keys)
            
            # Count skill keys
            skill_keys = await self.valkey.keys("skills:*")
            stats["total_skills"] = len(skill_keys)
            
            # Count ground item keys
            ground_item_keys = await self.valkey.keys("ground_item:*")
            stats["total_ground_items"] = len(ground_item_keys)
            
            # Get dirty tracking counts
            dirty_position = await self.valkey.scard("dirty:position")
            dirty_inventory = await self.valkey.scard("dirty:inventory")
            dirty_equipment = await self.valkey.scard("dirty:equipment")
            dirty_skills = await self.valkey.scard("dirty:skills")
            dirty_ground_items = await self.valkey.scard("dirty:ground_items")
            
            stats["dirty_counts"] = {
                "position": dirty_position,
                "inventory": dirty_inventory,
                "equipment": dirty_equipment,
                "skills": dirty_skills,
                "ground_items": dirty_ground_items
            }
            
            return {"status": "success", "stats": stats}
            
        except Exception as e:
            logger.error("Failed to get migration statistics", extra={"error": str(e)})
            return {"status": "error", "message": str(e)}