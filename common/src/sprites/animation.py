"""
Animation configuration for LPC spritesheets.

Defines frame counts, timing, and row offsets for each animation type.
Based on the LPC Universal Spritesheet format.

License: Part of the LPC sprite integration.
See server/sprites/CREDITS.csv for sprite attribution.
"""

from dataclasses import dataclass
from typing import Dict, Optional

from .enums import AnimationType, BodyType, get_fallback_animation


@dataclass(frozen=True)
class AnimationConfig:
    """
    Configuration for a single animation type.
    
    Defines how to extract and play animation frames from LPC spritesheets.
    
    Attributes:
        row_offset: Starting row in spritesheet (each direction adds 1 row)
        frame_count: Number of frames in the animation
        frame_duration: Seconds per frame (for playback timing)
        loops: Whether the animation should loop (False for one-shot like hurt)
        idle_frame: Which frame to use when showing static/idle (usually 0)
    """
    row_offset: int
    frame_count: int
    frame_duration: float
    loops: bool = True
    idle_frame: int = 0


# =============================================================================
# Standard LPC Animation Configurations
# =============================================================================

# Row offsets are based on the LPC Universal Spritesheet layout.
# Each animation occupies 4 rows (one per direction: up, left, down, right).
# The row_offset is the starting row for the UP direction.

ANIMATION_CONFIGS: Dict[AnimationType, AnimationConfig] = {
    # Spellcast: 7 frames, rows 0-3
    AnimationType.SPELLCAST: AnimationConfig(
        row_offset=0,
        frame_count=7,
        frame_duration=0.1,
        loops=False,
    ),
    
    # Thrust (polearm attack): 8 frames, rows 4-7
    AnimationType.THRUST: AnimationConfig(
        row_offset=4,
        frame_count=8,
        frame_duration=0.08,
        loops=False,
    ),
    
    # Walk: 9 frames, rows 8-11
    AnimationType.WALK: AnimationConfig(
        row_offset=8,
        frame_count=9,
        frame_duration=0.08,
        loops=True,
        idle_frame=0,  # Standing frame
    ),
    
    # Slash (sword attack): 6 frames, rows 12-15
    AnimationType.SLASH: AnimationConfig(
        row_offset=12,
        frame_count=6,
        frame_duration=0.08,
        loops=False,
    ),
    
    # Shoot (bow/crossbow): 13 frames, rows 16-19
    AnimationType.SHOOT: AnimationConfig(
        row_offset=16,
        frame_count=13,
        frame_duration=0.06,
        loops=False,
    ),
    
    # Hurt (taking damage): 6 frames, rows 20-23
    AnimationType.HURT: AnimationConfig(
        row_offset=20,
        frame_count=6,
        frame_duration=0.1,
        loops=False,
    ),
    
    # Idle: varies, but typically 1 frame or short loop
    # Note: Not available for skeleton/zombie - use WALK frame 0
    AnimationType.IDLE: AnimationConfig(
        row_offset=24,
        frame_count=1,
        frame_duration=1.0,  # Long duration for single frame
        loops=True,
    ),
    
    # =========================================================================
    # Extended Animations (LPC Expanded - not all body types support these)
    # =========================================================================
    
    # Run: 8 frames, rows 28-31
    AnimationType.RUN: AnimationConfig(
        row_offset=28,
        frame_count=8,
        frame_duration=0.06,
        loops=True,
    ),
    
    # Climb: 6 frames, rows 32-35
    AnimationType.CLIMB: AnimationConfig(
        row_offset=32,
        frame_count=6,
        frame_duration=0.1,
        loops=True,
    ),
    
    # Combat Idle: 4 frames, rows 36-39
    AnimationType.COMBAT_IDLE: AnimationConfig(
        row_offset=36,
        frame_count=4,
        frame_duration=0.2,
        loops=True,
    ),
    
    # Jump: 6 frames, rows 40-43 (one-shot)
    AnimationType.JUMP: AnimationConfig(
        row_offset=40,
        frame_count=6,
        frame_duration=0.1,
        loops=False,
    ),
    
    # Sit: 3 frames, rows 44-47
    AnimationType.SIT: AnimationConfig(
        row_offset=44,
        frame_count=3,
        frame_duration=0.2,
        loops=True,
        idle_frame=2,  # Seated frame
    ),
    
    # Emote: 4 frames, rows 48-51
    AnimationType.EMOTE: AnimationConfig(
        row_offset=48,
        frame_count=4,
        frame_duration=0.15,
        loops=False,
    ),
    
    # Backslash: 6 frames (sword swing from behind)
    AnimationType.BACKSLASH: AnimationConfig(
        row_offset=52,
        frame_count=6,
        frame_duration=0.08,
        loops=False,
    ),
    
    # Halfslash: 6 frames (quick slash)
    AnimationType.HALFSLASH: AnimationConfig(
        row_offset=56,
        frame_count=6,
        frame_duration=0.08,
        loops=False,
    ),
}


def get_animation_config(animation: AnimationType) -> Optional[AnimationConfig]:
    """
    Get the configuration for an animation type.
    
    Args:
        animation: The animation type to look up.
        
    Returns:
        AnimationConfig if found, None otherwise.
    """
    return ANIMATION_CONFIGS.get(animation)


def get_animation_config_for_body(
    body_type: BodyType,
    animation: AnimationType,
) -> AnimationConfig:
    """
    Get animation config with fallback for unsupported animations.
    
    If the body type doesn't support the requested animation,
    returns config for a fallback animation.
    
    Args:
        body_type: The character's body type.
        animation: The desired animation.
        
    Returns:
        AnimationConfig for the animation (or its fallback).
    """
    actual_animation = get_fallback_animation(body_type, animation)
    config = ANIMATION_CONFIGS.get(actual_animation)
    
    if config is None:
        # Ultimate fallback to walk
        config = ANIMATION_CONFIGS[AnimationType.WALK]
    
    return config


# =============================================================================
# Animation State Machine
# =============================================================================

@dataclass
class AnimationState:
    """
    Tracks the current animation state for a character.
    
    Mutable state for tracking animation playback.
    
    Attributes:
        animation: Current animation type
        frame: Current frame index
        elapsed: Time elapsed in current frame
        finished: Whether a non-looping animation has completed
    """
    animation: AnimationType = AnimationType.IDLE
    frame: int = 0
    elapsed: float = 0.0
    finished: bool = False
    
    def update(self, dt: float, body_type: BodyType) -> bool:
        """
        Update animation state based on elapsed time.
        
        Args:
            dt: Delta time in seconds since last update.
            body_type: Character's body type (for fallback handling).
            
        Returns:
            True if the frame changed, False otherwise.
        """
        config = get_animation_config_for_body(body_type, self.animation)
        
        if self.finished:
            return False
        
        self.elapsed += dt
        
        if self.elapsed >= config.frame_duration:
            self.elapsed -= config.frame_duration
            self.frame += 1
            
            if self.frame >= config.frame_count:
                if config.loops:
                    self.frame = 0
                else:
                    self.frame = config.frame_count - 1
                    self.finished = True
            
            return True
        
        return False
    
    def play(self, animation: AnimationType, reset: bool = True) -> None:
        """
        Start playing a new animation.
        
        Args:
            animation: The animation to play.
            reset: If True, reset to frame 0. If False, continue from current frame
                   (useful for looping animations that shouldn't restart).
        """
        if self.animation != animation or reset:
            self.animation = animation
            if reset:
                self.frame = 0
                self.elapsed = 0.0
            self.finished = False
    
    def get_static_frame(self, body_type: BodyType) -> int:
        """
        Get the appropriate static/idle frame for this animation.
        
        Args:
            body_type: Character's body type.
            
        Returns:
            Frame index to use for static display.
        """
        config = get_animation_config_for_body(body_type, self.animation)
        return config.idle_frame


# =============================================================================
# Direction Row Mapping
# =============================================================================

# LPC spritesheets have 4 rows per animation, one for each direction.
# This maps Direction enum values to row offsets within an animation.

from common.src.protocol import Direction

DIRECTION_ROW_OFFSET: Dict[Direction, int] = {
    Direction.UP: 0,
    Direction.LEFT: 1,
    Direction.DOWN: 2,
    Direction.RIGHT: 3,
}


def get_animation_row(animation: AnimationType, direction: Direction) -> int:
    """
    Get the spritesheet row for an animation and direction.
    
    NOTE: LPC sprites store each animation in separate files (walk.png, idle.png, etc.)
    where each file has 4 rows (one per direction). So we only use the direction offset,
    not the animation row_offset (which is for unified spritesheets).
    
    Args:
        animation: The animation type.
        direction: The facing direction.
        
    Returns:
        Row index in the spritesheet (0-3 for UP, LEFT, DOWN, RIGHT).
    """
    direction_offset = DIRECTION_ROW_OFFSET.get(direction, 2)  # Default to DOWN
    return direction_offset
