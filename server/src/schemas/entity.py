"""
Pydantic schemas for Entity definitions (NPCs and Monsters).

These schemas represent the Entity ORM model for API responses.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any, List
from enum import Enum


class EntityType(str, Enum):
    """Entity type classification."""
    HUMANOID_NPC = "humanoid_npc"
    MONSTER = "monster"


class EntityBehavior(str, Enum):
    """AI behavior patterns for entities."""
    PASSIVE = "passive"
    AGGRESSIVE = "aggressive"
    DEFENSIVE = "defensive"
    STATIONARY = "stationary"


class EntityData(BaseModel):
    """
    Complete entity definition schema.
    
    Mirrors the Entity ORM model for API serialization.
    """
    model_config = ConfigDict(from_attributes=True)
    
    # Identity
    id: int = Field(..., description="Entity database ID")
    name: str = Field(..., description="Entity enum name (e.g., 'GOBLIN')")
    entity_type: EntityType = Field(..., description="Entity classification")
    display_name: str = Field(..., description="Human-readable name")
    description: Optional[str] = Field(None, description="Flavor text")
    behavior: EntityBehavior = Field(..., description="AI behavior pattern")
    is_attackable: bool = Field(default=True, description="Can be targeted in combat")
    
    # Visuals - Monsters
    sprite_sheet_id: Optional[str] = Field(None, description="Sprite sheet identifier for monsters")
    width: int = Field(default=1, description="Width in tiles")
    height: int = Field(default=1, description="Height in tiles")
    scale: float = Field(default=1.0, description="Visual scaling factor")
    
    # Visuals - Humanoids
    appearance: Optional[Dict[str, Any]] = Field(None, description="Appearance data for humanoids (JSON)")
    equipped_items: Optional[Dict[str, str]] = Field(None, description="Equipped items for humanoids (JSON)")
    
    # Stats
    level: int = Field(default=1, description="Entity level")
    max_hp: int = Field(default=10, description="Maximum hitpoints")
    xp_reward: int = Field(default=0, description="XP awarded on kill")
    
    # Combat behavior
    aggro_radius: int = Field(default=0, description="Tiles to spot player")
    disengage_radius: int = Field(default=0, description="Max tiles from spawn before returning")
    respawn_time: int = Field(default=30, description="Seconds to respawn after death")
    
    # Skills
    skills: Dict[str, int] = Field(default_factory=dict, description="Skill levels")
    
    # Humanoid interaction
    dialogue: Optional[List[str]] = Field(None, description="Dialogue lines for NPCs")
    shop_id: Optional[str] = Field(None, description="Shop identifier if NPC is a merchant")
    
    # Combat bonuses (offensive)
    attack_bonus: int = Field(default=0, description="Melee accuracy bonus")
    strength_bonus: int = Field(default=0, description="Melee damage bonus")
    ranged_attack_bonus: int = Field(default=0, description="Ranged accuracy bonus")
    ranged_strength_bonus: int = Field(default=0, description="Ranged damage bonus")
    magic_attack_bonus: int = Field(default=0, description="Magic accuracy bonus")
    magic_damage_bonus: int = Field(default=0, description="Magic damage bonus")
    
    # Combat bonuses (defensive)
    physical_defence_bonus: int = Field(default=0, description="Physical defence bonus")
    magic_defence_bonus: int = Field(default=0, description="Magic defence bonus")
    
    # Other bonuses
    speed_bonus: int = Field(default=0, description="Movement speed bonus")


class EntityInstance(BaseModel):
    """
    Runtime entity instance data.
    
    Represents a spawned entity in the game world.
    """
    model_config = ConfigDict(from_attributes=True)
    
    instance_id: int = Field(..., description="Unique instance ID")
    entity_id: int = Field(..., description="Entity definition ID")
    entity_name: str = Field(..., description="Entity enum name")
    entity_type: EntityType = Field(..., description="Entity classification")
    
    # Position
    map_id: str = Field(..., description="Current map")
    x: int = Field(..., description="X coordinate")
    y: int = Field(..., description="Y coordinate")
    
    # Combat state
    current_hp: int = Field(..., description="Current hitpoints")
    max_hp: int = Field(..., description="Maximum hitpoints")
    state: str = Field(default="idle", description="Current state (idle, walk, attack, dead)")
    target_player_id: Optional[int] = Field(None, description="Target player ID if in combat")
    
    # Spawn tracking
    spawn_x: int = Field(..., description="Original spawn X")
    spawn_y: int = Field(..., description="Original spawn Y")
    wander_radius: int = Field(default=0, description="Maximum tiles from spawn")
    spawn_point_id: int = Field(..., description="Spawn point identifier")
    
    # Behavior overrides
    aggro_radius: Optional[int] = Field(None, description="Override aggro radius")
    disengage_radius: Optional[int] = Field(None, description="Override disengage radius")
    
    # Timestamps
    spawned_at: float = Field(..., description="Unix timestamp when spawned")
    respawn_delay_seconds: int = Field(default=30, description="Seconds before respawn")


class EntitySpawnPoint(BaseModel):
    """
    Static spawn point configuration from map files.
    """
    id: int = Field(..., description="Spawn point identifier")
    name: str = Field(..., description="Spawn point name")
    entity_id: str = Field(..., description="Entity enum name to spawn")
    x: int = Field(..., description="Spawn X coordinate")
    y: int = Field(..., description="Spawn Y coordinate")
    wander_radius: int = Field(default=0, description="Maximum tiles from spawn")
    aggro_override: Optional[int] = Field(None, description="Override entity aggro radius")
    disengage_override: Optional[int] = Field(None, description="Override entity disengage radius")
    patrol_route: Optional[List[Dict[str, int]]] = Field(None, description="Patrol waypoints if any")
