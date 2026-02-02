"""
Appearance definitions for humanoid entities (players and NPCs).

Defines the visual appearance attributes for paperdoll sprite rendering.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class AppearanceData:
    """
    Visual appearance attributes for humanoid entities.
    
    Used by both players and humanoid NPCs to determine which
    sprite layers to render for the paperdoll system.
    
    Attributes:
        skin_tone: Index into the skin tone palette (0-based)
        hair_style: Identifier for hair sprite (e.g., "short", "long", "bald")
        hair_color: Hex color string for hair tinting (e.g., "#8B4513")
        body_type: Body sprite variant (e.g., "default", "muscular", "slim")
    """
    skin_tone: int = 0
    hair_style: str = "short"
    hair_color: str = "#4A3728"  # Default brown
    body_type: str = "default"
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "skin_tone": self.skin_tone,
            "hair_style": self.hair_style,
            "hair_color": self.hair_color,
            "body_type": self.body_type,
        }
    
    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "AppearanceData":
        """
        Create AppearanceData from dictionary.
        
        Args:
            data: Dictionary with appearance fields, or None for defaults
            
        Returns:
            AppearanceData instance with provided or default values
        """
        if data is None:
            return cls()
        return cls(
            skin_tone=data.get("skin_tone", 0),
            hair_style=data.get("hair_style", "short"),
            hair_color=data.get("hair_color", "#4A3728"),
            body_type=data.get("body_type", "default"),
        )


# Predefined appearance presets for NPCs
class AppearancePresets:
    """Common appearance presets for NPC definitions."""
    
    GUARD = AppearanceData(
        skin_tone=1,
        hair_style="short",
        hair_color="#2C1810",
        body_type="muscular",
    )
    
    ELDER = AppearanceData(
        skin_tone=0,
        hair_style="bald",
        hair_color="#CCCCCC",  # Gray
        body_type="slim",
    )
    
    SHOPKEEPER = AppearanceData(
        skin_tone=2,
        hair_style="short",
        hair_color="#8B4513",  # Brown
        body_type="default",
    )
