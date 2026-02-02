"""
Client-side game state management.
Handles player state, inventory, equipment, skills, entities, and combat.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum
import time

import sys
import os
workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.append(workspace_root)

from common.src.protocol import Direction, ChatChannel


# =============================================================================
# ENUMS
# =============================================================================

class EntityType(str, Enum):
    """Types of entities in the game world."""
    PLAYER = "player"
    NPC = "npc"
    MONSTER = "monster"
    GROUND_ITEM = "ground_item"


class EquipmentSlot(str, Enum):
    """Equipment slot identifiers."""
    HEAD = "head"
    CAPE = "cape"
    NECK = "neck"
    AMMUNITION = "ammunition"
    WEAPON = "weapon"
    BODY = "body"
    SHIELD = "shield"
    LEGS = "legs"
    HANDS = "hands"
    FEET = "feet"
    RING = "ring"


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class InventoryItem:
    """Represents an item in inventory or equipment."""
    item_id: int
    quantity: int
    durability: float = 1.0
    # Cached metadata
    name: str = ""
    display_name: str = ""
    description: str = ""
    category: str = ""
    rarity: str = "common"
    value: int = 0
    equipable: bool = False
    equipment_slot: Optional[str] = None
    stackable: bool = False
    max_stack: int = 1
    # Combat stats
    attack_bonus: int = 0
    strength_bonus: int = 0
    defence_bonus: int = 0


@dataclass
class Entity:
    """Represents a visible entity in the game world."""
    instance_id: int
    entity_type: EntityType
    name: str
    display_name: str
    x: int
    y: int
    # Visual state
    display_x: float = 0.0
    display_y: float = 0.0
    is_moving: bool = False
    facing_direction: Direction = Direction.DOWN
    move_start_time: float = 0.0
    _start_x: float = 0.0
    _start_y: float = 0.0
    # Combat state
    current_hp: int = 10
    max_hp: int = 10
    combat_level: int = 1
    is_attackable: bool = True
    in_combat: bool = False
    # Appearance (legacy)
    appearance: Optional[Dict[str, Any]] = None
    # Paperdoll visual state
    visual_state: Optional[Dict[str, Any]] = None
    visual_hash: Optional[str] = None


@dataclass
class GroundItem:
    """Represents an item on the ground."""
    ground_item_id: str
    item_id: int
    quantity: int
    x: int
    y: int
    name: str = ""
    display_name: str = ""
    despawn_time: Optional[float] = None
    owner: Optional[str] = None  # Username of owner (for loot protection)


@dataclass
class CombatState:
    """Tracks player combat state."""
    in_combat: bool = False
    target_type: Optional[str] = None  # "entity" or "player"
    target_id: Optional[int] = None
    auto_retaliate: bool = True
    last_attack_time: float = 0.0


@dataclass
class PlayerStats:
    """Aggregated player combat stats."""
    # Combat stats
    attack_bonus: int = 0
    strength_bonus: int = 0
    defence_bonus: int = 0
    ranged_attack: int = 0
    ranged_strength: int = 0
    magic_attack: int = 0
    magic_defence: int = 0
    # Other stats
    health_bonus: int = 0
    speed_bonus: int = 0


@dataclass
class Skill:
    """Represents a player skill."""
    name: str
    level: int = 1
    experience: int = 0
    # XP for next level
    next_level_xp: int = 83


@dataclass
class FloatingMessage:
    """Chat message floating above player."""
    message: str
    timestamp: float
    duration: float = 3.0
    
    def is_expired(self, current_time: float) -> bool:
        return current_time - self.timestamp > self.duration
    
    def get_alpha(self, current_time: float) -> int:
        age = current_time - self.timestamp
        if age > self.duration * 0.7:
            fade_progress = (age - self.duration * 0.7) / (self.duration * 0.3)
            return max(0, int(255 * (1 - fade_progress)))
        return 255


@dataclass
class HitSplat:
    """Combat damage indicator."""
    damage: int
    is_miss: bool
    timestamp: float
    duration: float = 1.5
    is_heal: bool = False
    
    def is_expired(self, current_time: float) -> bool:
        return current_time - self.timestamp > self.duration
    
    def get_y_offset(self, current_time: float) -> float:
        """Get vertical offset for floating animation."""
        age = current_time - self.timestamp
        # Float up over time
        return -age * 20


# =============================================================================
# GAME STATE
# =============================================================================

class ClientGameState:
    """
    Central game state manager for the client.
    
    Stores all game data and provides methods for updating from server events.
    """
    
    def __init__(self):
        # Player state
        self.username: str = ""
        self.player_id: int = 0
        self.x: int = 0
        self.y: int = 0
        self.map_id: str = "test_map"
        self.current_hp: int = 10
        self.max_hp: int = 10
        
        # Animation state
        self.display_x: float = 0.0
        self.display_y: float = 0.0
        self.is_moving: bool = False
        self.facing_direction: Direction = Direction.DOWN
        self.move_start_time: float = 0.0
        self._start_x: float = 0.0
        self._start_y: float = 0.0
        self.move_duration: float = 0.2
        
        # Floating messages
        self.floating_messages: List[FloatingMessage] = []
        self.hit_splats: List[HitSplat] = []
        
        # Inventory (slot -> item)
        self.inventory: Dict[int, InventoryItem] = {}
        self.inventory_capacity: int = 28
        
        # Equipment (slot name -> item)
        self.equipment: Dict[str, InventoryItem] = {}
        
        # Skills
        self.skills: Dict[str, Skill] = {}
        
        # Aggregated stats
        self.stats: PlayerStats = PlayerStats()
        
        # Combat state
        self.combat: CombatState = CombatState()
        
        # Other players (keyed by player_id for identification)
        self.other_players: Dict[int, Entity] = {}
        
        # NPCs and monsters
        self.entities: Dict[int, Entity] = {}
        
        # Ground items
        self.ground_items: Dict[str, GroundItem] = {}
        
        # Chunk tracking
        self.last_chunk_request_x: int = 0
        self.last_chunk_request_y: int = 0
        
        # Item metadata cache (item_id -> metadata)
        self._item_cache: Dict[int, Dict[str, Any]] = {}
        
        # Paperdoll visual state (own player)
        self.visual_state: Optional[Dict[str, Any]] = None
        self.visual_hash: Optional[str] = None
    
    def reset(self) -> None:
        """Reset all game state (for logout/disconnect)."""
        self.__init__()
    
    # =========================================================================
    # PLAYER UPDATE METHODS
    # =========================================================================
    
    def update_player_position(self, x: int, y: int, animate: bool = True) -> None:
        """Update player position with optional animation."""
        if x == self.x and y == self.y:
            return
        
        if animate:
            # Start animation from current display position (smooth continuous movement)
            # If already moving, this prevents "stepping" by continuing from where we are
            self._start_x = self.display_x
            self._start_y = self.display_y
            self.is_moving = True
            self.move_start_time = time.time()
            
            # Update facing direction
            if x > self.x:
                self.facing_direction = Direction.RIGHT
            elif x < self.x:
                self.facing_direction = Direction.LEFT
            elif y > self.y:
                self.facing_direction = Direction.DOWN
            elif y < self.y:
                self.facing_direction = Direction.UP
        else:
            self.display_x = float(x)
            self.display_y = float(y)
            self.is_moving = False
        
        self.x = x
        self.y = y
    
    def update_player_hp(self, current_hp: int, max_hp: int) -> None:
        """Update player HP."""
        old_hp = self.current_hp
        self.current_hp = current_hp
        self.max_hp = max_hp
        
        # Create hit splat for damage/heal
        if current_hp < old_hp:
            damage = old_hp - current_hp
            self.hit_splats.append(HitSplat(
                damage=damage,
                is_miss=False,
                timestamp=time.time()
            ))
        elif current_hp > old_hp:
            heal = current_hp - old_hp
            self.hit_splats.append(HitSplat(
                damage=heal,
                is_miss=False,
                timestamp=time.time(),
                is_heal=True
            ))
    
    def add_floating_message(self, message: str) -> None:
        """Add a floating chat message above player."""
        self.floating_messages.append(FloatingMessage(
            message=message,
            timestamp=time.time()
        ))
    
    def update_visual_state(self, visual_state: Dict[str, Any], visual_hash: str) -> None:
        """Update player's paperdoll visual state."""
        self.visual_state = visual_state
        self.visual_hash = visual_hash
    
    # =========================================================================
    # INVENTORY METHODS
    # =========================================================================
    
    def set_inventory(self, inventory_data: Dict[str, Any]) -> None:
        """Set full inventory from server response. Expects list format."""
        self.inventory.clear()
        
        slots = inventory_data.get("slots", [])
        for slot_info in slots:
            slot = slot_info.get("slot", 0)
            self.inventory[slot] = self._parse_inventory_item(slot_info)
    
    def set_inventory_slot(self, slot: int, item_data: Optional[Dict[str, Any]]) -> None:
        """Update a single inventory slot."""
        if item_data is None:
            self.inventory.pop(slot, None)
        else:
            self.inventory[slot] = self._parse_inventory_item(item_data)
    
    def get_free_slot(self) -> Optional[int]:
        """Get first free inventory slot."""
        for slot in range(self.inventory_capacity):
            if slot not in self.inventory:
                return slot
        return None
    
    def is_inventory_full(self) -> bool:
        """Check if inventory is full."""
        return len(self.inventory) >= self.inventory_capacity
    
    # =========================================================================
    # EQUIPMENT METHODS
    # =========================================================================
    
    def set_equipment(self, equipment_data: Dict[str, Any]) -> None:
        """Set full equipment from server response. Expects list format."""
        self.equipment.clear()
        
        slots = equipment_data.get("slots", [])
        for slot_info in slots:
            slot_name = slot_info.get("slot", "")
            item_data = slot_info.get("item")
            if item_data and slot_name:
                self.equipment[slot_name] = self._parse_inventory_item(item_data)
    
    def set_equipment_slot(self, slot: str, item_data: Optional[Dict[str, Any]]) -> None:
        """Update a single equipment slot."""
        if item_data is None:
            self.equipment.pop(slot, None)
        else:
            self.equipment[slot] = self._parse_inventory_item(item_data)
    
    # =========================================================================
    # SKILLS METHODS
    # =========================================================================
    
    def set_skills(self, skills_data: List[Dict[str, Any]]) -> None:
        """Set skills from server response. Expects list format."""
        self.skills.clear()
        
        for skill_info in skills_data:
            skill_name = skill_info.get("name", "")
            if skill_name:
                self.skills[skill_name] = Skill(
                    name=skill_name,
                    level=skill_info.get("current_level", skill_info.get("level", 1)),
                    experience=skill_info.get("experience", 0),
                    next_level_xp=skill_info.get("xp_for_next_level", skill_info.get("next_level_xp", 83))
                )
    
    def update_skill(self, skill_name: str, level: int, experience: int) -> None:
        """Update a single skill."""
        if skill_name in self.skills:
            self.skills[skill_name].level = level
            self.skills[skill_name].experience = experience
        else:
            self.skills[skill_name] = Skill(
                name=skill_name,
                level=level,
                experience=experience
            )
    
    # =========================================================================
    # STATS METHODS
    # =========================================================================
    
    def set_stats(self, stats_data: Dict[str, Any]) -> None:
        """Set aggregated stats from server response."""
        self.stats = PlayerStats(
            attack_bonus=stats_data.get("attack_bonus", 0),
            strength_bonus=stats_data.get("strength_bonus", 0),
            defence_bonus=stats_data.get("defence_bonus", 0),
            ranged_attack=stats_data.get("ranged_attack", 0),
            ranged_strength=stats_data.get("ranged_strength", 0),
            magic_attack=stats_data.get("magic_attack", 0),
            magic_defence=stats_data.get("magic_defence", 0),
            health_bonus=stats_data.get("health_bonus", 0),
            speed_bonus=stats_data.get("speed_bonus", 0),
        )
    
    # =========================================================================
    # ENTITY METHODS
    # =========================================================================
    
    def update_entities(self, entities_data: List[Dict[str, Any]], removed_ids: List[str]) -> None:
        """Update visible entities from game update event."""
        # Remove entities
        for entity_id in removed_ids:
            # Could be int or string depending on type
            try:
                int_id = int(entity_id)
                self.entities.pop(int_id, None)
            except ValueError:
                # It's a string ID (ground item)
                self.ground_items.pop(entity_id, None)
        
        # Update/add entities
        for entity_data in entities_data:
            entity_type = entity_data.get("type", "")
            
            if entity_type == "player":
                player_id = entity_data.get("player_id")
                username = entity_data.get("username", "")
                
                # Check if this is our own player (by player_id or username)
                if player_id == self.player_id or username == self.username:
                    # Update own player position
                    new_x = entity_data.get("x", self.x)
                    new_y = entity_data.get("y", self.y)
                    self.update_player_position(new_x, new_y)
                    
                    # Update HP if provided
                    if "current_hp" in entity_data:
                        self.update_player_hp(
                            entity_data.get("current_hp", self.current_hp),
                            entity_data.get("max_hp", self.max_hp)
                        )
                elif player_id:
                    self._update_other_player(player_id, username, entity_data)
            
            elif entity_type in ["npc", "monster", "humanoid"]:
                instance_id = entity_data.get("instance_id", 0)
                self._update_entity(instance_id, entity_data)
            
            elif entity_type == "ground_item":
                ground_item_id = entity_data.get("ground_item_id", "")
                self._update_ground_item(ground_item_id, entity_data)
    
    def _update_other_player(self, player_id: int, username: str, data: Dict[str, Any]) -> None:
        """Update or create another player entity (identified by player_id)."""
        if player_id not in self.other_players:
            self.other_players[player_id] = Entity(
                instance_id=player_id,
                entity_type=EntityType.PLAYER,
                name=username,
                display_name=username,
                x=data.get("x", 0),
                y=data.get("y", 0),
                display_x=float(data.get("x", 0)),
                display_y=float(data.get("y", 0)),
            )
        
        player = self.other_players[player_id]
        # Update username in case it changed
        player.name = username
        player.display_name = username
        
        new_x = data.get("x", player.x)
        new_y = data.get("y", player.y)
        
        # Animate if position changed
        if new_x != player.x or new_y != player.y:
            # Start animation from current display position (smooth continuous movement)
            player._start_x = player.display_x
            player._start_y = player.display_y
            player.is_moving = True
            player.move_start_time = time.time()
            
            if new_x > player.x:
                player.facing_direction = Direction.RIGHT
            elif new_x < player.x:
                player.facing_direction = Direction.LEFT
            elif new_y > player.y:
                player.facing_direction = Direction.DOWN
            elif new_y < player.y:
                player.facing_direction = Direction.UP
        
        player.x = new_x
        player.y = new_y
        player.current_hp = data.get("current_hp", player.current_hp)
        player.max_hp = data.get("max_hp", player.max_hp)
        player.combat_level = data.get("combat_level", player.combat_level)
        player.appearance = data.get("appearance")
        # Paperdoll visual state
        if "visual_state" in data:
            player.visual_state = data.get("visual_state")
        if "visual_hash" in data:
            player.visual_hash = data.get("visual_hash")
    
    def _update_entity(self, instance_id: int, data: Dict[str, Any]) -> None:
        """Update or create an NPC/monster entity."""
        entity_type_str = data.get("type", "monster")
        entity_type = EntityType.MONSTER if entity_type_str == "monster" else EntityType.NPC
        
        if instance_id not in self.entities:
            self.entities[instance_id] = Entity(
                instance_id=instance_id,
                entity_type=entity_type,
                name=data.get("name", "Unknown"),
                display_name=data.get("display_name", data.get("name", "Unknown")),
                x=data.get("x", 0),
                y=data.get("y", 0),
                display_x=float(data.get("x", 0)),
                display_y=float(data.get("y", 0)),
            )
        
        entity = self.entities[instance_id]
        new_x = data.get("x", entity.x)
        new_y = data.get("y", entity.y)
        
        # Animate if position changed
        if new_x != entity.x or new_y != entity.y:
            # Start animation from current display position (smooth continuous movement)
            entity._start_x = entity.display_x
            entity._start_y = entity.display_y
            entity.is_moving = True
            entity.move_start_time = time.time()
            
            # Update facing direction
            if new_x > entity.x:
                entity.facing_direction = Direction.RIGHT
            elif new_x < entity.x:
                entity.facing_direction = Direction.LEFT
            elif new_y > entity.y:
                entity.facing_direction = Direction.DOWN
            elif new_y < entity.y:
                entity.facing_direction = Direction.UP
        
        entity.x = new_x
        entity.y = new_y
        entity.current_hp = data.get("current_hp", entity.current_hp)
        entity.max_hp = data.get("max_hp", entity.max_hp)
        entity.combat_level = data.get("combat_level", entity.combat_level)
        entity.is_attackable = data.get("is_attackable", entity.is_attackable)
        entity.in_combat = data.get("in_combat", entity.in_combat)
        # Paperdoll visual state for humanoid entities
        if "visual_state" in data:
            entity.visual_state = data.get("visual_state")
        if "visual_hash" in data:
            entity.visual_hash = data.get("visual_hash")
    
    def _update_ground_item(self, ground_item_id: str, data: Dict[str, Any]) -> None:
        """Update or create a ground item."""
        self.ground_items[ground_item_id] = GroundItem(
            ground_item_id=ground_item_id,
            item_id=data.get("item_id", 0),
            quantity=data.get("quantity", 1),
            x=data.get("x", 0),
            y=data.get("y", 0),
            name=data.get("name", "Item"),
            display_name=data.get("display_name", data.get("name", "Item")),
            despawn_time=data.get("despawn_time"),
            owner=data.get("owner"),
        )
    
    def remove_player(self, player_id: int) -> None:
        """Remove a player from the game state by player_id."""
        self.other_players.pop(player_id, None)
    
    # =========================================================================
    # ANIMATION UPDATES
    # =========================================================================
    
    def update_animations(self, current_time: float, move_duration: float = 0.2) -> None:
        """Update all entity animations."""
        # Update own player
        if self.is_moving:
            elapsed = current_time - self.move_start_time
            progress = min(elapsed / move_duration, 1.0)
            
            if progress >= 1.0:
                self.display_x = float(self.x)
                self.display_y = float(self.y)
                self.is_moving = False
            else:
                self.display_x = self._start_x + (self.x - self._start_x) * progress
                self.display_y = self._start_y + (self.y - self._start_y) * progress
        
        # Update other players
        for player in self.other_players.values():
            self._update_entity_animation(player, current_time, move_duration)
        
        # Update entities
        for entity in self.entities.values():
            self._update_entity_animation(entity, current_time, move_duration)
        
        # Clean up expired floating messages
        self.floating_messages = [
            msg for msg in self.floating_messages
            if not msg.is_expired(current_time)
        ]
        
        # Clean up expired hit splats
        self.hit_splats = [
            splat for splat in self.hit_splats
            if not splat.is_expired(current_time)
        ]
    
    def _update_entity_animation(self, entity: Entity, current_time: float, move_duration: float) -> None:
        """Update animation for a single entity."""
        if entity.is_moving:
            elapsed = current_time - entity.move_start_time
            progress = min(elapsed / move_duration, 1.0)
            
            if progress >= 1.0:
                entity.display_x = float(entity.x)
                entity.display_y = float(entity.y)
                entity.is_moving = False
            else:
                entity.display_x = entity._start_x + (entity.x - entity._start_x) * progress
                entity.display_y = entity._start_y + (entity.y - entity._start_y) * progress
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _parse_inventory_item(self, data: Dict[str, Any]) -> InventoryItem:
        """Parse item data into InventoryItem."""
        item_id = data.get("item_id", 0)
        
        # Get cached metadata if available
        meta = self._item_cache.get(item_id, {})
        
        return InventoryItem(
            item_id=item_id,
            quantity=data.get("quantity", 1),
            durability=data.get("current_durability", data.get("durability", 1.0)),
            name=data.get("name", meta.get("name", f"Item {item_id}")),
            display_name=data.get("display_name", meta.get("display_name", f"Item {item_id}")),
            description=data.get("description", meta.get("description", "")),
            category=data.get("category", meta.get("category", "misc")),
            rarity=data.get("rarity", meta.get("rarity", "common")),
            value=data.get("value", meta.get("value", 0)),
            equipable=data.get("equipable", meta.get("equipable", False)),
            equipment_slot=data.get("equipment_slot", meta.get("equipment_slot")),
            stackable=data.get("max_stack_size", meta.get("max_stack_size", 1)) > 1,
            max_stack=data.get("max_stack_size", meta.get("max_stack_size", 1)),
            attack_bonus=data.get("attack_bonus", meta.get("attack_bonus", 0)),
            strength_bonus=data.get("strength_bonus", meta.get("strength_bonus", 0)),
            defence_bonus=data.get("defence_bonus", meta.get("defence_bonus", 0)),
        )
    
    def cache_item_metadata(self, item_id: int, metadata: Dict[str, Any]) -> None:
        """Cache item metadata for future use."""
        self._item_cache[item_id] = metadata
