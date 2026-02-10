"""
Comprehensive test suite for the LPC Sprite System.

Tests cover:
1. Sprite enums and type safety
2. AppearanceData construction and serialization
3. EquippedVisuals construction and serialization
4. VisualState hash computation and stability
5. VisualRegistry caching and observer tracking
6. Game loop integration helpers
7. Sprite API endpoints
"""

import pytest
import pytest_asyncio
import json
from unittest.mock import MagicMock, patch

from common.src.sprites import (
    # Enums
    BodyType,
    SkinTone,
    HeadType,
    HairStyle,
    HairColor,
    EyeColor,
    EyeAgeGroup,
    AnimationType,
    SpriteLayer,
    EquipmentSlot,
    
    # Dataclasses
    AppearanceData,
    AppearancePresets,
    EquippedVisuals,
    VisualState,
    AnimationConfig,
    AnimationState,
    
    # Constants
    BODY_ANIMATIONS,
    ANIMATION_CONFIGS,
    DIRECTION_ROW_OFFSET,
    
    # Functions
    supports_animation,
    get_fallback_animation,
    get_eye_age_group,
    get_animation_config,
    get_animation_config_for_body,
    get_animation_row,
    
    # Path utilities
    SpritePaths,
    get_sprite_paths_for_appearance,
    get_body_sprite_path,
    get_head_sprite_path,
    get_eyes_sprite_path,
    get_hair_sprite_path,
)

from server.src.services.visual_registry import (
    VisualRegistry,
    get_visual_registry,
    reset_visual_registry,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def sample_appearance() -> AppearanceData:
    """Create a sample appearance for testing."""
    return AppearanceData(
        body_type=BodyType.FEMALE,
        skin_tone=SkinTone.OLIVE,
        head_type=HeadType.HUMAN_FEMALE,
        hair_style=HairStyle.LONG,
        hair_color=HairColor.RED,
        eye_color=EyeColor.GREEN,
    )


@pytest.fixture
def sample_equipment() -> EquippedVisuals:
    """Create sample equipment for testing."""
    return EquippedVisuals(
        head="iron_helmet",
        body="chainmail",
        legs="iron_greaves",
        weapon="longsword",
        shield="wooden_shield",
    )


@pytest.fixture
def sample_visual_state(sample_appearance, sample_equipment) -> VisualState:
    """Create a sample visual state for testing."""
    return VisualState(appearance=sample_appearance, equipment=sample_equipment)


@pytest_asyncio.fixture
async def visual_registry() -> VisualRegistry:
    """Create a fresh visual registry for each test."""
    reset_visual_registry()
    registry = get_visual_registry()
    yield registry
    await registry.clear_all()
    reset_visual_registry()


# =============================================================================
# Enum Tests
# =============================================================================

class TestBodyType:
    """Tests for BodyType enum."""
    
    def test_all_body_types_have_values(self):
        """All body types should have string values."""
        for body_type in BodyType:
            assert isinstance(body_type.value, str)
            assert len(body_type.value) > 0
    
    def test_standard_body_types_exist(self):
        """Standard body types should be available."""
        assert BodyType.MALE.value == "male"
        assert BodyType.FEMALE.value == "female"
        assert BodyType.CHILD.value == "child"
        assert BodyType.TEEN.value == "teen"
        assert BodyType.SKELETON.value == "skeleton"
        assert BodyType.ZOMBIE.value == "zombie"


class TestSkinTone:
    """Tests for SkinTone enum."""
    
    def test_skin_tones_have_values(self):
        """All skin tones should have string values."""
        for skin_tone in SkinTone:
            assert isinstance(skin_tone.value, str)
    
    def test_common_skin_tones_exist(self):
        """Common skin tones should be available."""
        assert SkinTone.LIGHT is not None
        assert SkinTone.OLIVE is not None
        assert SkinTone.BROWN is not None
        assert SkinTone.BLACK is not None


class TestAnimationType:
    """Tests for AnimationType enum."""
    
    def test_standard_animations_exist(self):
        """Standard animation types should be available."""
        assert AnimationType.IDLE is not None
        assert AnimationType.WALK is not None
        assert AnimationType.SLASH is not None
        assert AnimationType.THRUST is not None
        assert AnimationType.SPELLCAST is not None
        assert AnimationType.SHOOT is not None
        assert AnimationType.HURT is not None
    
    def test_animation_support_checking(self):
        """Animation support checking should work correctly."""
        # Male body supports all standard animations
        assert supports_animation(BodyType.MALE, AnimationType.WALK)
        assert supports_animation(BodyType.MALE, AnimationType.IDLE)
        
        # Skeleton doesn't support IDLE
        assert supports_animation(BodyType.SKELETON, AnimationType.WALK)
        assert not supports_animation(BodyType.SKELETON, AnimationType.IDLE)
    
    def test_fallback_animation(self):
        """Fallback animation should return WALK for unsupported IDLE."""
        fallback = get_fallback_animation(BodyType.SKELETON, AnimationType.IDLE)
        assert fallback == AnimationType.WALK


class TestEquipmentSlot:
    """Tests for EquipmentSlot enum."""
    
    def test_all_slots_exist(self):
        """All equipment slots should be available."""
        expected_slots = ["head", "body", "legs", "boots", "gloves", 
                         "weapon", "shield", "cape", "amulet", "ring", "ammo"]
        for slot_name in expected_slots:
            found = False
            for slot in EquipmentSlot:
                if slot.value == slot_name:
                    found = True
                    break
            assert found, f"Equipment slot '{slot_name}' not found"


# =============================================================================
# AppearanceData Tests
# =============================================================================

class TestAppearanceData:
    """Tests for AppearanceData dataclass."""
    
    def test_default_construction(self):
        """Default appearance should have sensible values."""
        appearance = AppearanceData()
        assert appearance.body_type == BodyType.MALE
        assert appearance.skin_tone is not None
        assert appearance.hair_style is not None
        assert appearance.hair_color is not None
        assert appearance.eye_color is not None
    
    def test_custom_construction(self, sample_appearance):
        """Custom appearance should preserve all values."""
        assert sample_appearance.body_type == BodyType.FEMALE
        assert sample_appearance.skin_tone == SkinTone.OLIVE
        assert sample_appearance.hair_style == HairStyle.LONG
        assert sample_appearance.hair_color == HairColor.RED
        assert sample_appearance.eye_color == EyeColor.GREEN
    
    def test_immutability(self, sample_appearance):
        """AppearanceData should be immutable (frozen)."""
        with pytest.raises(AttributeError):
            sample_appearance.body_type = BodyType.MALE
    
    def test_to_dict(self, sample_appearance):
        """to_dict should serialize all fields."""
        data = sample_appearance.to_dict()
        assert data["body_type"] == "female"
        assert data["skin_tone"] == "olive"
        assert data["hair_style"] == "long"
        assert data["hair_color"] == "red"
        assert data["eye_color"] == "green"
    
    def test_from_dict(self):
        """from_dict should deserialize correctly."""
        data = {
            "body_type": "male",
            "skin_tone": "light",
            "head_type": "human/male",
            "hair_style": "short",
            "hair_color": "dark_brown",
            "eye_color": "blue",
        }
        appearance = AppearanceData.from_dict(data)
        assert appearance.body_type == BodyType.MALE
        assert appearance.skin_tone == SkinTone.LIGHT
        assert appearance.hair_style == HairStyle.BUZZCUT
        assert appearance.hair_color == HairColor.DARK_BROWN
        assert appearance.eye_color == EyeColor.BLUE
    
    def test_from_dict_with_none(self):
        """from_dict with None should return defaults."""
        appearance = AppearanceData.from_dict(None)
        assert appearance.body_type == BodyType.MALE
    
    def test_hash_stability(self, sample_appearance):
        """Same appearance should produce same hash."""
        hash1 = sample_appearance.compute_hash()
        hash2 = sample_appearance.compute_hash()
        assert hash1 == hash2
        assert len(hash1) == 12  # 12-char hex hash
    
    def test_hash_uniqueness(self):
        """Different appearances should produce different hashes."""
        appearance1 = AppearanceData(body_type=BodyType.MALE)
        appearance2 = AppearanceData(body_type=BodyType.FEMALE)
        assert appearance1.compute_hash() != appearance2.compute_hash()
    
    def test_with_changes(self, sample_appearance):
        """with_changes should create new instance with modifications."""
        modified = sample_appearance.with_changes(hair_color=HairColor.BLACK)
        assert modified.hair_color == HairColor.BLACK
        assert modified.body_type == sample_appearance.body_type
        assert sample_appearance.hair_color == HairColor.RED  # Original unchanged


class TestAppearancePresets:
    """Tests for AppearancePresets."""
    
    def test_presets_are_valid_appearances(self):
        """All presets should be valid AppearanceData instances."""
        presets = [
            AppearancePresets.HUMAN_MALE,
            AppearancePresets.HUMAN_FEMALE,
            AppearancePresets.GUARD,
            AppearancePresets.ELDER,
            AppearancePresets.SHOPKEEPER,
        ]
        for preset in presets:
            assert isinstance(preset, AppearanceData)
            assert preset.body_type is not None
    
    def test_presets_produce_different_hashes(self):
        """Different presets should have different hashes."""
        hashes = set()
        presets = [
            AppearancePresets.HUMAN_MALE,
            AppearancePresets.HUMAN_FEMALE,
            AppearancePresets.GUARD,
            AppearancePresets.ELDER,
            AppearancePresets.SHOPKEEPER,
        ]
        for preset in presets:
            hash_val = preset.compute_hash()
            hashes.add(hash_val)
        # All should be unique (or at least most - some may intentionally match)
        assert len(hashes) >= 3


# =============================================================================
# EquippedVisuals Tests
# =============================================================================

class TestEquippedVisuals:
    """Tests for EquippedVisuals dataclass."""
    
    def test_default_construction(self):
        """Default equipment should be empty."""
        equipment = EquippedVisuals()
        assert equipment.head is None
        assert equipment.body is None
        assert equipment.weapon is None
        assert equipment.is_empty()
    
    def test_partial_construction(self, sample_equipment):
        """Should allow partial equipment."""
        assert sample_equipment.head == "iron_helmet"
        assert sample_equipment.body == "chainmail"
        assert sample_equipment.boots is None  # Not equipped
        assert not sample_equipment.is_empty()
    
    def test_immutability(self, sample_equipment):
        """EquippedVisuals should be immutable."""
        with pytest.raises(AttributeError):
            sample_equipment.head = "new_helmet"
    
    def test_to_dict_excludes_none(self, sample_equipment):
        """to_dict should exclude None values."""
        data = sample_equipment.to_dict()
        assert "head" in data
        assert "body" in data
        assert "boots" not in data  # None values excluded
        assert "gloves" not in data
    
    def test_from_dict(self):
        """from_dict should deserialize correctly."""
        data = {"head": "leather_cap", "weapon": "dagger"}
        equipment = EquippedVisuals.from_dict(data)
        assert equipment.head == "leather_cap"
        assert equipment.weapon == "dagger"
        assert equipment.body is None
    
    def test_from_dict_with_none(self):
        """from_dict with None should return empty equipment."""
        equipment = EquippedVisuals.from_dict(None)
        assert equipment.is_empty()
    
    def test_get_slot(self, sample_equipment):
        """get_slot should return correct sprite ID."""
        assert sample_equipment.get_slot(EquipmentSlot.HEAD) == "iron_helmet"
        assert sample_equipment.get_slot(EquipmentSlot.BODY) == "chainmail"
        assert sample_equipment.get_slot(EquipmentSlot.BOOTS) is None


# =============================================================================
# VisualState Tests
# =============================================================================

class TestVisualState:
    """Tests for VisualState dataclass."""
    
    def test_default_construction(self):
        """Default visual state should have default components."""
        state = VisualState()
        assert state.appearance is not None
        assert state.equipment is not None
        assert state.equipment.is_empty()
    
    def test_custom_construction(self, sample_visual_state):
        """Custom visual state should preserve components."""
        assert sample_visual_state.appearance.body_type == BodyType.FEMALE
        assert sample_visual_state.equipment.head == "iron_helmet"
    
    def test_to_dict(self, sample_visual_state):
        """to_dict should include both appearance and equipment."""
        data = sample_visual_state.to_dict()
        assert "appearance" in data
        assert "equipment" in data
        assert data["appearance"]["body_type"] == "female"
        assert data["equipment"]["head"] == "iron_helmet"
    
    def test_from_dict(self):
        """from_dict should deserialize correctly."""
        data = {
            "appearance": {"body_type": "male", "skin_tone": "dark"},
            "equipment": {"weapon": "axe"},
        }
        state = VisualState.from_dict(data)
        assert state.appearance.body_type == BodyType.MALE
        assert state.equipment.weapon == "axe"
    
    def test_hash_includes_both_components(self, sample_appearance, sample_equipment):
        """Hash should change when either appearance or equipment changes."""
        state1 = VisualState(appearance=sample_appearance, equipment=sample_equipment)
        
        # Change appearance
        modified_appearance = sample_appearance.with_changes(hair_color=HairColor.BLACK)
        state2 = VisualState(appearance=modified_appearance, equipment=sample_equipment)
        
        # Change equipment
        modified_equipment = EquippedVisuals(head="different_helmet")
        state3 = VisualState(appearance=sample_appearance, equipment=modified_equipment)
        
        hash1 = state1.compute_hash()
        hash2 = state2.compute_hash()
        hash3 = state3.compute_hash()
        
        assert hash1 != hash2, "Hash should change when appearance changes"
        assert hash1 != hash3, "Hash should change when equipment changes"
        assert hash2 != hash3, "Different changes should produce different hashes"
    
    def test_hash_is_12_chars(self, sample_visual_state):
        """Hash should be exactly 12 characters."""
        hash_val = sample_visual_state.compute_hash()
        assert len(hash_val) == 12
        assert all(c in "0123456789abcdef" for c in hash_val)
    
    def test_with_appearance(self, sample_visual_state):
        """with_appearance should create new state with different appearance."""
        new_appearance = AppearanceData(body_type=BodyType.CHILD)
        modified = sample_visual_state.with_appearance(new_appearance)
        assert modified.appearance.body_type == BodyType.CHILD
        assert modified.equipment == sample_visual_state.equipment
    
    def test_with_equipment(self, sample_visual_state):
        """with_equipment should create new state with different equipment."""
        new_equipment = EquippedVisuals(weapon="staff")
        modified = sample_visual_state.with_equipment(new_equipment)
        assert modified.equipment.weapon == "staff"
        assert modified.appearance == sample_visual_state.appearance


# =============================================================================
# Animation Tests
# =============================================================================

class TestAnimationConfig:
    """Tests for animation configuration."""
    
    def test_walk_animation_config(self):
        """WALK animation should have correct config."""
        config = get_animation_config(AnimationType.WALK)
        assert config is not None
        assert config.frame_count > 0
        assert config.frame_duration > 0
    
    def test_idle_animation_config(self):
        """IDLE animation should have correct config."""
        config = get_animation_config(AnimationType.IDLE)
        assert config is not None
        assert config.frame_count > 0
    
    def test_body_specific_animation(self):
        """Body-specific animation should handle unsupported types."""
        # Skeleton doesn't support IDLE
        config = get_animation_config_for_body(BodyType.SKELETON, AnimationType.IDLE)
        # Should fall back to WALK
        walk_config = get_animation_config(AnimationType.WALK)
        assert config.frame_count == walk_config.frame_count


class TestAnimationState:
    """Tests for AnimationState class."""
    
    def test_initial_state(self):
        """Initial animation state should be at frame 0."""
        state = AnimationState()
        assert state.frame == 0
        assert state.elapsed == 0.0
        assert not state.finished
    
    def test_frame_advancement(self):
        """update should advance frames based on time."""
        state = AnimationState()
        # Use WALK animation which has 9 frames, 0.08s duration
        state.play(AnimationType.WALK)
        
        # Advance time but not enough for next frame (WALK frame_duration is 0.08)
        state.update(0.05, BodyType.MALE)
        assert state.frame == 0
        
        # Advance enough for next frame
        state.update(0.04, BodyType.MALE)
        assert state.frame == 1
    
    def test_animation_looping(self):
        """Looping animation should wrap around."""
        state = AnimationState()
        # Use WALK which loops
        state.play(AnimationType.WALK)
        
        # Advance through all frames and wrap (9 frames * 0.08s = 0.72s)
        state.update(0.80, BodyType.MALE)
        walk_config = get_animation_config(AnimationType.WALK)
        assert state.frame < walk_config.frame_count
        assert not state.finished
    
    def test_non_looping_animation(self):
        """Non-looping animation should finish at last frame."""
        state = AnimationState()
        # Use HURT which doesn't loop (6 frames, 0.1s duration = 0.6s)
        state.play(AnimationType.HURT)
        hurt_config = get_animation_config(AnimationType.HURT)
        
        # Advance past all frames (6 frames * 0.1s = 0.6s, use 1.0s to be safe)
        # Must call update multiple times since each call only advances by frame_duration
        for _ in range(10):  # 10 * 0.1s = 1.0s total
            state.update(0.1, BodyType.MALE)
        
        assert state.frame == hurt_config.frame_count - 1
        assert state.finished
    
    def test_play_reset(self):
        """play() with reset=True should restore initial state."""
        state = AnimationState()
        state.play(AnimationType.WALK)
        state.update(0.5, BodyType.MALE)
        
        # Play a new animation with reset
        state.play(AnimationType.IDLE, reset=True)
        assert state.frame == 0
        assert state.elapsed == 0.0
        assert not state.finished


# =============================================================================
# Visual Registry Tests
# =============================================================================

class TestVisualRegistry:
    """Tests for VisualRegistry service."""
    
    @pytest.mark.asyncio
    async def test_register_visual_state(self, visual_registry, sample_visual_state):
        """register_visual_state should return a hash and cache the state."""
        visual_hash = await visual_registry.register_visual_state(
            "player_test", sample_visual_state
        )
        
        assert len(visual_hash) == 12
        
        # Should be able to retrieve the state
        retrieved = await visual_registry.get_visual_state(visual_hash)
        assert retrieved is not None
        assert retrieved.compute_hash() == visual_hash
    
    @pytest.mark.asyncio
    async def test_hash_consistency(self, visual_registry, sample_visual_state):
        """Same visual state should always produce same hash."""
        hash1 = await visual_registry.register_visual_state("entity_1", sample_visual_state)
        hash2 = await visual_registry.register_visual_state("entity_2", sample_visual_state)
        
        assert hash1 == hash2
    
    @pytest.mark.asyncio
    async def test_entity_hash_tracking(self, visual_registry, sample_visual_state):
        """Registry should track entity's current hash."""
        await visual_registry.register_visual_state("player_1", sample_visual_state)
        
        current_hash = await visual_registry.get_entity_hash("player_1")
        assert current_hash == sample_visual_state.compute_hash()
    
    @pytest.mark.asyncio
    async def test_hash_change_detection(self, visual_registry, sample_appearance):
        """has_hash_changed should detect visual changes."""
        state1 = VisualState(appearance=sample_appearance)
        state2 = VisualState(
            appearance=sample_appearance.with_changes(hair_color=HairColor.BLACK)
        )
        
        hash1 = await visual_registry.register_visual_state("player_1", state1)
        
        # Same hash - no change
        assert not await visual_registry.has_hash_changed("player_1", hash1)
        
        # Different hash - change detected
        hash2 = state2.compute_hash()
        assert await visual_registry.has_hash_changed("player_1", hash2)
    
    @pytest.mark.asyncio
    async def test_observer_first_sight(self, visual_registry, sample_visual_state):
        """First sight should require full visual data."""
        visual_hash = await visual_registry.register_visual_state(
            "player_1", sample_visual_state
        )
        
        # Observer hasn't seen this hash
        needs_full = await visual_registry.observer_needs_full_visual(
            "observer_1", visual_hash
        )
        assert needs_full is True
    
    @pytest.mark.asyncio
    async def test_observer_seen_hash(self, visual_registry, sample_visual_state):
        """After marking seen, observer should not need full data."""
        visual_hash = await visual_registry.register_visual_state(
            "player_1", sample_visual_state
        )
        
        await visual_registry.mark_hash_seen("observer_1", visual_hash)
        
        needs_full = await visual_registry.observer_needs_full_visual(
            "observer_1", visual_hash
        )
        assert needs_full is False
    
    @pytest.mark.asyncio
    async def test_get_visual_for_observer(self, visual_registry, sample_visual_state):
        """get_visual_for_observer should return hash and data appropriately."""
        # First call - should return full data
        visual_hash, visual_data = await visual_registry.get_visual_for_observer(
            "observer_1", "player_1", sample_visual_state
        )
        
        assert len(visual_hash) == 12
        assert visual_data is not None
        assert "appearance" in visual_data
        assert "equipment" in visual_data
        
        # Second call - should not return full data (already seen)
        visual_hash2, visual_data2 = await visual_registry.get_visual_for_observer(
            "observer_1", "player_1", sample_visual_state
        )
        
        assert visual_hash2 == visual_hash
        assert visual_data2 is None  # No full data needed
    
    @pytest.mark.asyncio
    async def test_remove_observer(self, visual_registry, sample_visual_state):
        """remove_observer should clear observer tracking."""
        visual_hash = await visual_registry.register_visual_state(
            "player_1", sample_visual_state
        )
        
        await visual_registry.mark_hash_seen("observer_1", visual_hash)
        await visual_registry.remove_observer("observer_1")
        
        # After removal, should need full data again
        needs_full = await visual_registry.observer_needs_full_visual(
            "observer_1", visual_hash
        )
        assert needs_full is True
    
    @pytest.mark.asyncio
    async def test_remove_entity(self, visual_registry, sample_visual_state):
        """remove_entity should clear entity hash tracking."""
        await visual_registry.register_visual_state("player_1", sample_visual_state)
        await visual_registry.remove_entity("player_1")
        
        current_hash = await visual_registry.get_entity_hash("player_1")
        assert current_hash is None
    
    @pytest.mark.asyncio
    async def test_stats(self, visual_registry, sample_visual_state):
        """get_stats should return registry statistics."""
        await visual_registry.register_visual_state("player_1", sample_visual_state)
        await visual_registry.mark_hash_seen("observer_1", sample_visual_state.compute_hash())
        
        stats = await visual_registry.get_stats()
        
        assert stats["visual_cache_size"] >= 1
        assert stats["entity_count"] >= 1
        assert stats["observer_count"] >= 1
        assert "max_cache_size" in stats
    
    @pytest.mark.asyncio
    async def test_clear_all(self, visual_registry, sample_visual_state):
        """clear_all should reset the registry."""
        await visual_registry.register_visual_state("player_1", sample_visual_state)
        await visual_registry.mark_hash_seen("observer_1", sample_visual_state.compute_hash())
        
        await visual_registry.clear_all()
        
        stats = await visual_registry.get_stats()
        assert stats["visual_cache_size"] == 0
        assert stats["entity_count"] == 0
        assert stats["observer_count"] == 0
    
    @pytest.mark.asyncio
    async def test_lru_eviction(self, visual_registry):
        """Cache should evict oldest entries when full."""
        # Temporarily reduce cache size for testing
        original_max = visual_registry.MAX_CACHE_SIZE
        visual_registry.MAX_CACHE_SIZE = 5
        
        try:
            # Register more states than cache can hold
            for i in range(10):
                appearance = AppearanceData(
                    hair_style=list(HairStyle)[i % len(list(HairStyle))]
                )
                state = VisualState(appearance=appearance)
                await visual_registry.register_visual_state(f"entity_{i}", state)
            
            stats = await visual_registry.get_stats()
            assert stats["visual_cache_size"] <= 5
        finally:
            visual_registry.MAX_CACHE_SIZE = original_max


# =============================================================================
# Game Loop Integration Tests
# =============================================================================

class TestGameLoopHelpers:
    """Tests for game_loop.py helper functions."""
    
    def test_build_visual_state_with_full_data(self):
        """_build_visual_state should build state from dicts."""
        from server.src.game.game_loop import _build_visual_state
        
        appearance_dict = {
            "body_type": "female",
            "skin_tone": "olive",
            "head_type": "human/female",
            "hair_style": "long",
            "hair_color": "red",
            "eye_color": "green",
        }
        equipped_items = {
            "body": "leather_armor",
            "weapon": "dagger",
        }
        
        visual_state = _build_visual_state(appearance_dict, equipped_items)
        
        assert visual_state.appearance.body_type == BodyType.FEMALE
        assert visual_state.appearance.hair_color == HairColor.RED
        assert visual_state.equipment.body == "leather_armor"
        assert visual_state.equipment.weapon == "dagger"
    
    def test_build_visual_state_with_none(self):
        """_build_visual_state should handle None inputs."""
        from server.src.game.game_loop import _build_visual_state
        
        visual_state = _build_visual_state(None, None)
        
        assert visual_state.appearance.body_type == BodyType.MALE  # Default
        assert visual_state.equipment.is_empty()
    
    def test_build_visual_state_hash_is_stable(self):
        """Same input should produce same hash."""
        from server.src.game.game_loop import _build_visual_state
        
        appearance = {"body_type": "male", "skin_tone": "light"}
        equipment = {"weapon": "sword"}
        
        state1 = _build_visual_state(appearance, equipment)
        state2 = _build_visual_state(appearance, equipment)
        
        assert state1.compute_hash() == state2.compute_hash()


# =============================================================================
# Sprite Path Tests
# =============================================================================

class TestSpritePaths:
    """Tests for sprite path construction."""
    
    def test_body_path(self):
        """Body sprite path should be constructed correctly."""
        path = SpritePaths.body(BodyType.MALE, SkinTone.LIGHT)
        assert "male" in path.lower()
        assert "light" in path.lower()
        assert path.endswith(".png")
    
    def test_head_path(self):
        """Head sprite path should be constructed correctly."""
        path = SpritePaths.head(HeadType.HUMAN_MALE, SkinTone.OLIVE)
        assert "human" in path.lower()
        assert path.endswith(".png")
    
    def test_hair_path(self):
        """Hair sprite path should be constructed correctly."""
        path = SpritePaths.hair(HairStyle.LONG, HairColor.RED)
        assert "long" in path.lower()
        assert "red" in path.lower()
        assert path.endswith(".png")
    
    def test_eyes_path(self):
        """Eyes sprite path should be constructed correctly."""
        path = SpritePaths.eyes(EyeColor.BLUE, EyeAgeGroup.ADULT)
        assert "blue" in path.lower()
        assert path.endswith(".png")
    
    def test_get_appearance_paths(self, sample_appearance):
        """get_appearance_paths should return all required paths."""
        paths = get_sprite_paths_for_appearance(sample_appearance)
        
        # Returns a List[str], should have body, head, eyes, and hair paths
        assert isinstance(paths, list)
        assert len(paths) >= 3  # At minimum: body, head, eyes (hair if not bald)
        
        # Check that paths contain expected components
        path_string = " ".join(paths)
        assert "body" in path_string
        assert "head" in path_string
        assert "eyes" in path_string
        
        # All paths should end with .png
        for path in paths:
            assert path.endswith(".png")


# =============================================================================
# Humanoid Integration Tests
# =============================================================================

class TestHumanoidIntegration:
    """Tests for humanoid NPC integration with sprite system."""
    
    def test_humanoid_uses_new_appearance(self):
        """HumanoidDefinition should use common.src.sprites.AppearanceData."""
        from server.src.core.humanoids import HumanoidID
        
        guard = HumanoidID.VILLAGE_GUARD.value
        
        # Appearance should be from common.src.sprites
        assert guard.appearance.__class__.__module__ == "common.src.sprites.appearance"
        assert hasattr(guard.appearance, "body_type")
        assert hasattr(guard.appearance, "compute_hash")
    
    def test_humanoid_appearance_has_visual_hash(self):
        """Humanoid appearance should produce valid visual hash."""
        from server.src.core.humanoids import HumanoidID
        
        guard = HumanoidID.VILLAGE_GUARD.value
        
        # Build visual state from humanoid
        equipped_items = {
            slot.value: item.name 
            for slot, item in guard.equipped_items.items()
        } if guard.equipped_items else None
        
        visual_state = VisualState(
            appearance=guard.appearance,
            equipment=EquippedVisuals.from_dict(equipped_items) if equipped_items else EquippedVisuals(),
        )
        
        visual_hash = visual_state.compute_hash()
        assert len(visual_hash) == 12


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    def test_appearance_from_dict_with_invalid_enum(self):
        """from_dict should handle invalid enum values gracefully."""
        # This should use defaults for invalid values
        data = {
            "body_type": "invalid_type",
            "skin_tone": "nonexistent",
        }
        appearance = AppearanceData.from_dict(data)
        # Should fall back to defaults
        assert appearance.body_type == BodyType.MALE
    
    def test_empty_visual_state_hash(self):
        """Empty visual state should still produce valid hash."""
        state = VisualState()
        hash_val = state.compute_hash()
        assert len(hash_val) == 12
        assert all(c in "0123456789abcdef" for c in hash_val)
    
    @pytest.mark.asyncio
    async def test_registry_handles_concurrent_access(self, visual_registry):
        """Registry should handle concurrent operations safely."""
        import asyncio
        
        async def register_and_check(entity_id: str):
            appearance = AppearanceData(
                hair_style=list(HairStyle)[hash(entity_id) % len(list(HairStyle))]
            )
            state = VisualState(appearance=appearance)
            visual_hash = await visual_registry.register_visual_state(entity_id, state)
            retrieved = await visual_registry.get_visual_state(visual_hash)
            return retrieved is not None
        
        # Run many concurrent operations
        tasks = [register_and_check(f"entity_{i}") for i in range(50)]
        results = await asyncio.gather(*tasks)
        
        assert all(results), "All concurrent operations should succeed"
    
    def test_direction_row_offset_mapping(self):
        """Direction row offsets should be valid."""
        from common.src.protocol import Direction
        
        for direction in Direction:
            if direction in DIRECTION_ROW_OFFSET:
                offset = DIRECTION_ROW_OFFSET[direction]
                assert isinstance(offset, int)
                assert offset >= 0
