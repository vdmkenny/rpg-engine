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


