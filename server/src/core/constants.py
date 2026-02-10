"""
Shared constants and enums used across multiple layers.

This module contains enums and constants that are needed by both:
- Models (database layer)
- Schemas (API/serialization layer)  
- Services (business logic layer)

Placing them here avoids circular imports and cross-layer dependencies.
"""

from enum import Enum


class PlayerRole(str, Enum):
    """Player access roles."""
    PLAYER = "player"
    MODERATOR = "moderator"
    ADMIN = "admin"
