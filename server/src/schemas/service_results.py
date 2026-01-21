"""
Structured service result types for clean error handling and WebSocket integration.

This module defines the foundation for modern service-layer architecture where
all services return structured results with consistent error information.
"""

from dataclasses import dataclass
from typing import Optional, Any, Dict, List, Generic, TypeVar

T = TypeVar('T')


@dataclass
class ServiceResult(Generic[T]):
    """
    Generic service result with structured error information.
    
    This replaces the old pattern of returning raw data or raising exceptions.
    All services should return ServiceResult to enable clean error handling.
    """
    success: bool
    data: Optional[T] = None
    message: str = ""
    error_code: Optional[str] = None
    
    @classmethod
    def success_with_data(cls, data: T, message: str = "Operation successful") -> 'ServiceResult[T]':
        """Create successful result with data."""
        return cls(success=True, data=data, message=message)
    
    @classmethod
    def success_no_data(cls, message: str = "Operation successful") -> 'ServiceResult[None]':
        """Create successful result without data."""
        return cls(success=True, data=None, message=message)
    
    @classmethod
    def failure(cls, message: str, error_code: Optional[str] = None) -> 'ServiceResult[T]':
        """Create failure result with error information."""
        return cls(success=False, data=None, message=message, error_code=error_code)


@dataclass
class PlayerServiceResult(ServiceResult[T]):
    """Player service specific result extensions."""
    player_id: Optional[int] = None
    
    @classmethod
    def success_with_player(
        cls, 
        player: T, 
        player_id: int,
        message: str = "Player operation successful"
    ) -> 'PlayerServiceResult[T]':
        """Create successful result with player data."""
        return cls(
            success=True, 
            data=player, 
            message=message,
            player_id=player_id
        )


@dataclass
class InventoryServiceResult(ServiceResult[T]):
    """Inventory service specific result extensions."""
    inventory_updates: Optional[List[int]] = None  # Updated slot numbers
    items_affected: Optional[Dict[str, int]] = None  # {item_name: quantity_change}
    
    @classmethod
    def success_with_updates(
        cls,
        data: T,
        updated_slots: List[int],
        message: str = "Inventory operation successful"
    ) -> 'InventoryServiceResult[T]':
        """Create successful result with inventory update information."""
        return cls(
            success=True,
            data=data,
            message=message,
            inventory_updates=updated_slots
        )


@dataclass  
class EquipmentServiceResult(ServiceResult[T]):
    """Equipment service specific result extensions."""
    stat_changes: Optional[Dict[str, int]] = None  # {stat_name: delta}
    equipment_updates: Optional[List[str]] = None  # Updated slot names
    
    @classmethod
    def success_with_stats(
        cls,
        data: T,
        stat_changes: Dict[str, int],
        updated_slots: List[str],
        message: str = "Equipment operation successful"
    ) -> 'EquipmentServiceResult[T]':
        """Create successful result with stat change information."""
        return cls(
            success=True,
            data=data,
            message=message,
            stat_changes=stat_changes,
            equipment_updates=updated_slots
        )


@dataclass
class GroundItemServiceResult(ServiceResult[T]):
    """Ground item service specific result extensions."""
    ground_item_id: Optional[int] = None
    inventory_slot: Optional[int] = None  # For pickup operations
    
    @classmethod
    def success_with_ground_item(
        cls,
        ground_item_id: int,
        message: str = "Ground item operation successful"
    ) -> 'GroundItemServiceResult[None]':
        """Create successful result with ground item ID."""
        return cls(
            success=True,
            data=None,
            message=message,
            ground_item_id=ground_item_id
        )
    
    @classmethod
    def success_with_pickup(
        cls,
        inventory_slot: int,
        message: str = "Item picked up successfully"
    ) -> 'GroundItemServiceResult[None]':
        """Create successful result with pickup information."""
        return cls(
            success=True,
            data=None,
            message=message,
            inventory_slot=inventory_slot
        )


@dataclass
class TestDataServiceResult(ServiceResult[T]):
    """Test data service specific result extensions."""
    created_players: Optional[List[int]] = None  # Player IDs created
    synced_items: Optional[int] = None  # Number of items synced
    cleanup_needed: Optional[List[str]] = None  # Resources that need cleanup
    
    @classmethod
    def success_with_players(
        cls,
        data: T,
        player_ids: List[int],
        message: str = "Test scenario created successfully"
    ) -> 'TestDataServiceResult[T]':
        """Create successful result with created player information."""
        return cls(
            success=True,
            data=data,
            message=message,
            created_players=player_ids
        )


# Error codes for consistent client-side error handling
class ServiceErrorCodes:
    """Standardized error codes across all services."""
    
    # Common errors
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    INSUFFICIENT_RESOURCES = "INSUFFICIENT_RESOURCES"
    
    # Player errors
    PLAYER_NOT_FOUND = "PLAYER_NOT_FOUND"
    PLAYER_ALREADY_EXISTS = "PLAYER_ALREADY_EXISTS"
    PLAYER_NOT_ONLINE = "PLAYER_NOT_ONLINE"
    
    # Inventory errors
    INVENTORY_FULL = "INVENTORY_FULL"
    ITEM_NOT_FOUND = "ITEM_NOT_FOUND"
    INSUFFICIENT_QUANTITY = "INSUFFICIENT_QUANTITY"
    INVALID_SLOT = "INVALID_SLOT"
    
    # Equipment errors
    EQUIPMENT_REQUIREMENTS_NOT_MET = "EQUIPMENT_REQUIREMENTS_NOT_MET"
    ITEM_NOT_EQUIPPABLE = "ITEM_NOT_EQUIPPABLE"
    SLOT_OCCUPIED = "SLOT_OCCUPIED"
    
    # Ground item errors
    GROUND_ITEM_NOT_FOUND = "GROUND_ITEM_NOT_FOUND"
    GROUND_ITEM_PROTECTED = "GROUND_ITEM_PROTECTED"
    WRONG_POSITION = "WRONG_POSITION"
    ITEM_DESPAWNED = "ITEM_DESPAWNED"
    
    # Chat errors
    MESSAGE_TOO_LONG = "MESSAGE_TOO_LONG"
    CHAT_COOLDOWN = "CHAT_COOLDOWN"
    PROFANITY_DETECTED = "PROFANITY_DETECTED"
    
    # Authentication errors
    INVALID_TOKEN = "INVALID_TOKEN"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    ACCOUNT_SUSPENDED = "ACCOUNT_SUSPENDED"