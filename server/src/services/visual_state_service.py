"""
Service for managing visual state (appearance + equipment) for sprite rendering.

Handles building VisualState objects for paperdoll rendering system.
"""

from typing import Optional, Dict, Any
from ..core.logging_config import get_logger
from .player_service import PlayerService
from .equipment_service import EquipmentService
from .visual_registry import get_visual_registry
from .game_state_manager import get_game_state_manager

from common.src.sprites import AppearanceData, EquippedVisuals, VisualState

logger = get_logger(__name__)


class VisualStateService:
    """Service for managing visual state operations."""
    
    @staticmethod
    def _build_equipped_items_map(equipment, gsm) -> Optional[Dict[str, str]]:
        """
        Build equipment slot map for visual state construction.
        
        Args:
            equipment: List of equipment records
            gsm: GameStateManager instance
            
        Returns:
            Dict mapping slot names to item sprite IDs or None if no equipment
        """
        if not equipment:
            return None
        
        equipped_items = {}
        for equip in equipment:
            slot = equip.get("slot")
            item_id = equip.get("item_id")
            
            # Get item definition from GSM permanent cache
            item_def = gsm.get_item_def(item_id)
            if not item_def:
                continue
            
            # Use item sprite_id or fallback to item_id
            sprite_id = getattr(item_def, "sprite_id", None) or item_id
            equipped_items[slot] = sprite_id
        
        return equipped_items if equipped_items else None
    
    @staticmethod
    def _build_visual_state(
        appearance: Optional[Dict], 
        equipped_items: Optional[Dict[str, str]],
    ) -> VisualState:
        """
        Build a VisualState from appearance dict and equipped items map.
        
        Args:
            appearance: Appearance dictionary from player state
            equipped_items: Dict mapping slot names to item names/sprite IDs
            
        Returns:
            VisualState instance for hash computation and serialization
        """
        # Build AppearanceData from dict
        appearance_data = AppearanceData.from_dict(appearance)
        
        # Build EquippedVisuals from equipped items
        if equipped_items:
            equipped_visuals = EquippedVisuals(
                head=equipped_items.get("head"),
                body=equipped_items.get("body"),
                legs=equipped_items.get("legs"),
                feet=equipped_items.get("feet"),
                hands=equipped_items.get("hands"),
                main_hand=equipped_items.get("main_hand"),
                off_hand=equipped_items.get("off_hand"),
                back=equipped_items.get("back"),
                belt=equipped_items.get("belt"),
            )
        else:
            equipped_visuals = EquippedVisuals()
        
        return VisualState(appearance=appearance_data, equipment=equipped_visuals)
    
    @staticmethod
    async def get_player_visual_state(player_id: int) -> Optional[Dict[str, Any]]:
        """
        Get player's complete visual state (appearance + equipment + hash).
        
        Used for welcome messages and initial game state broadcasts.
        
        Args:
            player_id: Player ID
            
        Returns:
            Dict with visual_hash and visual_state keys, or None if player not found
        """
        try:
            gsm = get_game_state_manager()
            visual_registry = get_visual_registry()
            
            # Get appearance from PlayerService (uses GSM internally)
            appearance = await PlayerService.get_player_appearance(player_id)
            
            # Get equipped items
            equipment = await EquipmentService.get_equipment_raw(player_id)
            equipped_items = VisualStateService._build_equipped_items_map(equipment, gsm)
            
            # Build visual state
            visual_state = VisualStateService._build_visual_state(appearance, equipped_items)
            visual_hash = await visual_registry.register_visual_state(
                f"player_{player_id}", visual_state
            )
            
            return {
                "visual_hash": visual_hash,
                "visual_state": visual_state.to_dict(),
            }
            
        except Exception as e:
            logger.error(
                "Error getting player visual state",
                extra={
                    "player_id": player_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                }
            )
            return None
