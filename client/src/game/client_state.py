"""
Client-side game state management.

Handles all game data including player state, inventory, equipment, entities, and combat.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple, Union
from enum import Enum
import time

import sys
from pathlib import Path
common_path = Path(__file__).parent.parent.parent.parent / "common" / "src"
if str(common_path) not in sys.path:
    sys.path.insert(0, str(common_path))

from protocol import Direction, ChatChannel
from sprites.enums import EquipmentSlot


class EntityType(Enum):
    """Types of entities in the game world."""
    PLAYER = "player"
    NPC = "npc"
    MONSTER = "monster"


@dataclass
class InventoryItem:
    """Represents an item in inventory or equipment."""
    slot: int
    item_id: str
    name: str
    quantity: int = 1
    category: str = ""
    rarity: str = "common"
    is_stackable: bool = False
    is_equippable: bool = False
    equipped_sprite: Optional[str] = None
    description: str = ""


@dataclass
class Skill:
    """Represents a player skill."""
    name: str
    level: int = 1
    xp: int = 0
    xp_to_next: int = 0


@dataclass
class Entity:
    """Represents a visible entity in the game world."""
    entity_id: Union[int, str]
    entity_type: EntityType
    name: str
    x: int
    y: int
    current_hp: int = 100
    max_hp: int = 100
    level: int = 1
    visual_hash: Optional[str] = None
    facing_direction: str = "DOWN"
    is_moving: bool = False
    move_progress: float = 0.0
    start_x: int = 0
    start_y: int = 0
    target_x: int = 0
    target_y: int = 0


@dataclass
class HitSplat:
    """Combat damage indicator."""
    damage: int
    is_miss: bool
    target_id: Union[int, str]
    timestamp: float
    is_heal: bool = False
    
    def is_expired(self, current_time: float = None) -> bool:
        if current_time is None:
            current_time = time.time()
        return current_time - self.timestamp > 1.5


class ClientGameState:
    """
    Central game state manager for the client.
    
    Stores all game data and provides methods for updating from server events.
    """
    
    def __init__(self):
        # Player identity
        self.player_id: Optional[int] = None
        self.username: str = ""
        
        # Position
        self.position: Dict[str, Any] = {"x": 0, "y": 0, "map_id": "default"}
        self.map_id: str = "default"
        self.facing_direction: str = "DOWN"
        
        # Combat stats
        self.current_hp: int = 100
        self.max_hp: int = 100
        self.combat_level: int = 1
        self.is_dead: bool = False
        
        # Visual state
        self.visual_state: Optional[Dict[str, Any]] = None
        self.visual_hash: Optional[str] = None
        self.appearance: Optional[Dict[str, Any]] = None
        
        # Inventory (28 slots)
        self.inventory: Dict[int, InventoryItem] = {}
        self.inventory_capacity: int = 28
        self.gold: int = 0
        
        # Equipment
        self.equipment: Dict[str, InventoryItem] = {}
        
        # Skills
        self.skills: Dict[str, Skill] = {}
        self.total_level: int = 0
        self.total_xp: int = 0
        
        # Entities
        self.entities: Dict[Union[int, str], Entity] = {}
        self.other_players: Dict[int, Dict[str, Any]] = {}
        
        # Ground items
        self.ground_items: Dict[str, Dict[str, Any]] = {}
        
        # Map chunks
        self.chunks: Dict[Tuple[int, int], List[List[int]]] = {}
        
        # Combat state
        self.in_combat: bool = False
        self.combat_target: Optional[Dict[str, Any]] = None
        self.auto_retaliate: bool = True
        self.last_attack_time: float = 0.0
        
        # UI state
        self.chat_history: List[Dict[str, Any]] = []
        self.hit_splats: List[HitSplat] = []
        self.floating_messages: List[Dict[str, Any]] = []
        
        # Server state
        self.server_shutdown_warning: Optional[Dict[str, Any]] = None
        self.is_connected: bool = False
        self.is_authenticated: bool = False
    
    def update_entity(self, entity_id: Union[int, str], data: Dict[str, Any]) -> None:
        """Update or create an entity."""
        if entity_id not in self.entities:
            # Create new entity
            entity_type = EntityType(data.get("type", "npc").lower())
            self.entities[entity_id] = Entity(
                entity_id=entity_id,
                entity_type=entity_type,
                name=data.get("name", "Unknown"),
                x=data.get("x", 0),
                y=data.get("y", 0)
            )
        
        entity = self.entities[entity_id]
        
        # Update position
        if "x" in data:
            entity.x = data["x"]
        if "y" in data:
            entity.y = data["y"]
        
        # Update HP
        if "current_hp" in data:
            entity.current_hp = data["current_hp"]
        if "max_hp" in data:
            entity.max_hp = data["max_hp"]
        
        # Update visual
        if "visual_hash" in data:
            entity.visual_hash = data["visual_hash"]
        
        # Update facing direction
        if "direction" in data:
            entity.facing_direction = data["direction"]
    
    def update_inventory(self, data: Dict[str, Any]) -> None:
        """Update inventory from server data."""
        self.inventory.clear()
        
        items = data.get("items", [])
        for item_data in items:
            slot = item_data.get("slot", 0)
            item = InventoryItem(
                slot=slot,
                item_id=item_data.get("item_id", ""),
                name=item_data.get("name", "Unknown"),
                quantity=item_data.get("quantity", 1),
                category=item_data.get("category", ""),
                rarity=item_data.get("rarity", "common"),
                is_stackable=item_data.get("is_stackable", False),
                is_equippable=item_data.get("is_equippable", False),
                equipped_sprite=item_data.get("equipped_sprite"),
                description=item_data.get("description", "")
            )
            self.inventory[slot] = item
        
        self.gold = data.get("gold", 0)
        self.inventory_capacity = data.get("capacity", 28)
    
    def update_equipment(self, data: Dict[str, Any]) -> None:
        """Update equipment from server data."""
        self.equipment.clear()
        
        slots = data.get("slots", [])
        for slot_data in slots:
            slot_name = slot_data.get("slot")
            item_data = slot_data.get("item")
            
            if slot_name and item_data:
                item = InventoryItem(
                    slot=-1,  # Equipment doesn't have inventory slot
                    item_id=item_data.get("item_id", ""),
                    name=item_data.get("name", "Unknown"),
                    quantity=item_data.get("quantity", 1),
                    category=item_data.get("category", ""),
                    rarity=item_data.get("rarity", "common"),
                    is_equippable=True,
                    equipped_sprite=item_data.get("equipped_sprite")
                )
                self.equipment[slot_name] = item
    
    def update_stats(self, data: Dict[str, Any]) -> None:
        """Update player stats and skills from server data."""
        self.combat_level = data.get("combat_level", 1)
        self.total_level = data.get("total_level", 1)
        self.total_xp = data.get("total_xp", 0)
        self.max_hp = data.get("max_hp", 100)
        
        # Update skills
        skills_data = data.get("skills", [])
        for skill_data in skills_data:
            name = skill_data.get("name", "")
            if name:
                self.skills[name] = Skill(
                    name=name,
                    level=skill_data.get("level", 1),
                    xp=skill_data.get("xp", 0),
                    xp_to_next=skill_data.get("xp_to_next", 0)
                )
    
    def update_map_chunks(self, data: Dict[str, Any]) -> None:
        """Update map chunks from server data."""
        chunks = data.get("chunks", [])
        for chunk_data in chunks:
            chunk_x = chunk_data.get("chunk_x")
            chunk_y = chunk_data.get("chunk_y")
            tiles = chunk_data.get("tiles", [])
            
            if chunk_x is not None and chunk_y is not None:
                self.chunks[(chunk_x, chunk_y)] = tiles
        
        # Update player chunk position if provided
        player_chunk_x = data.get("player_chunk_x")
        player_chunk_y = data.get("player_chunk_y")
        if player_chunk_x is not None and player_chunk_y is not None:
            # Could store this separately if needed
            pass
    
    def add_skill_xp(self, skill_name: str, xp: int) -> None:
        """Add XP to a skill."""
        if skill_name not in self.skills:
            self.skills[skill_name] = Skill(name=skill_name)
        
        self.skills[skill_name].xp += xp
    
    def get_entity_at(self, x: int, y: int) -> Optional[Entity]:
        """Get entity at a specific tile position."""
        for entity in self.entities.values():
            if entity.x == x and entity.y == y:
                return entity
        return None
    
    def get_ground_items_at(self, x: int, y: int) -> List[Dict[str, Any]]:
        """Get all ground items at a specific tile position."""
        items = []
        for item_id, item in self.ground_items.items():
            if item.get("x") == x and item.get("y") == y:
                items.append(item)
        return items
    
    def cleanup_hit_splats(self) -> None:
        """Remove expired hit splats."""
        current_time = time.time()
        self.hit_splats = [s for s in self.hit_splats if not s.is_expired(current_time)]
    
    def clear(self) -> None:
        """Clear all game state (for logout/reset)."""
        self.__init__()


# Singleton instance
_game_state: Optional[ClientGameState] = None


def get_game_state() -> ClientGameState:
    """Get the singleton game state instance."""
    global _game_state
    if _game_state is None:
        _game_state = ClientGameState()
    return _game_state


def reset_game_state() -> None:
    """Reset the game state."""
    global _game_state
    _game_state = None
