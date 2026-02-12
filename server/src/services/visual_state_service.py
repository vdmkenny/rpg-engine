"""
Service for managing visual state (appearance + equipment) for sprite rendering.

Handles building VisualState objects for paperdoll rendering system.
"""

from typing import Optional, Dict, Any
from ..core.logging_config import get_logger
from .player_service import PlayerService
from .equipment_service import EquipmentService
from .visual_registry import get_visual_registry
from .game_state import get_reference_data_manager

from common.src.sprites import AppearanceData, EquippedVisuals, VisualState

logger = get_logger(__name__)


class VisualStateService:
    """Service for managing visual state operations."""
    
    @staticmethod
    def _build_equipped_items_map(equipment, ref_mgr) -> Optional[Dict[str, str]]:
        """
        Build equipment slot map for visual state construction.
        
        Args:
            equipment: List of equipment records
            ref_mgr: ReferenceDataManager instance
            
        Returns:
            Dict mapping slot names to item sprite IDs or None if no equipment
        """
        if not equipment:
            return None
        
        equipped_items = {}
        for equip in equipment:
            slot = equip.get("slot")
            item_id = equip.get("item_id")
            
            # Get item definition from reference data manager cache
            item_def = ref_mgr.get_cached_item_meta(item_id)
            if not item_def:
                continue
            
            # Use equipped_sprite_id from item definition (e.g., "equip_copper_dagger")
            sprite_id = item_def.get("equipped_sprite_id")
            if not sprite_id:
                logger.warning(f"No equipped_sprite_id for item {item_id}, skipping")
                continue
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
        # Updated to use unified slot names: weapon, shield, cape, gloves, boots
        if equipped_items:
            equipped_visuals = EquippedVisuals(
                head=equipped_items.get("head"),
                cape=equipped_items.get("cape") or equipped_items.get("back"),
                weapon=equipped_items.get("weapon") or equipped_items.get("main_hand"),
                body=equipped_items.get("body"),
                shield=equipped_items.get("shield") or equipped_items.get("off_hand"),
                legs=equipped_items.get("legs"),
                gloves=equipped_items.get("gloves") or equipped_items.get("hands"),
                boots=equipped_items.get("boots") or equipped_items.get("feet"),
                ammo=equipped_items.get("ammo"),
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
            ref_mgr = get_reference_data_manager()
            visual_registry = get_visual_registry()
            
            # Get appearance from PlayerService (uses GSM internally)
            appearance = await PlayerService.get_player_appearance(player_id)
            
            # Get equipped items - convert EquipmentData to format expected by _build_equipped_items_map
            equipment_data = await EquipmentService.get_equipment(player_id)
            # Convert EquipmentSlotData list to dict format expected by _build_equipped_items_map
            equipment_list = []
            if equipment_data and equipment_data.slots:
                for slot_data in equipment_data.slots:
                    if slot_data and slot_data.item:
                        equipment_list.append({
                            "slot": slot_data.slot.value,
                            "item_id": slot_data.item.item_id
                        })
            equipped_items = VisualStateService._build_equipped_items_map(equipment_list, ref_mgr)
            
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
