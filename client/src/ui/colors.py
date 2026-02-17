"""
Colors and styles for the RPG client UI.

Classic stone/brown theme matching legacy MMO aesthetics.
"""


class Colors:
    """Classic RPG color palette."""
    # Stone/Brown Theme
    STONE_DARK = (59, 50, 41)
    STONE_MEDIUM = (79, 67, 55)
    STONE_LIGHT = (99, 84, 69)
    STONE_HIGHLIGHT = (139, 119, 99)
    
    # Core colors
    WHITE = (255, 255, 255)
    BLACK = (0, 0, 0)
    
    # Panel backgrounds
    PANEL_BG = (49, 42, 35)
    PANEL_BORDER = (29, 25, 21)
    PANEL_INNER_BORDER = (69, 59, 49)
    
    # Slot backgrounds
    SLOT_BG = (39, 33, 27)
    SLOT_BORDER = (79, 67, 55)
    SLOT_HOVER = (59, 50, 41)
    SLOT_SELECTED = (99, 84, 69)
    
    # Text colors
    TEXT_YELLOW = (255, 255, 0)
    TEXT_WHITE = (255, 255, 255)
    TEXT_ORANGE = (255, 152, 31)
    TEXT_GREEN = (0, 255, 0)
    TEXT_RED = (255, 0, 0)
    TEXT_CYAN = (0, 255, 255)
    TEXT_PURPLE = (255, 0, 255)
    TEXT_GRAY = (128, 128, 128)
    TEXT_LIGHT_GRAY = (200, 200, 200)
    TEXT_DARK = (49, 42, 35)
    TEXT_XP = (200, 200, 200)
    
    # Health bar colors
    HP_GREEN = (0, 255, 0)
    HP_RED = (255, 0, 0)
    HP_BG = (0, 0, 0)
    HP_BORDER = (0, 0, 0)
    
    # HP orb colors
    HP_ORB_BG = (20, 5, 5)
    HP_ORB_FILL = (180, 20, 20)
    HP_ORB_HIGHLIGHT = (220, 60, 60)
    
    # XP bar colors
    XP_GREEN = (0, 180, 0)
    XP_BG = (40, 40, 40)
    
    # Rarity colors
    RARITY_POOR = (157, 157, 157)
    RARITY_COMMON = (255, 255, 255)
    RARITY_UNCOMMON = (30, 255, 0)
    RARITY_RARE = (0, 112, 221)
    RARITY_EPIC = (163, 53, 238)
    RARITY_LEGENDARY = (255, 128, 0)
    
    # Minimap
    MINIMAP_BG = (0, 0, 0)
    MINIMAP_PLAYER = (255, 255, 255)
    MINIMAP_OTHER_PLAYER = (0, 255, 255)
    MINIMAP_NPC = (255, 255, 0)
    MINIMAP_MONSTER = (255, 0, 0)
    
    # Hit splat colors
    HIT_SPLAT_DAMAGE_BG = (200, 0, 0)
    HIT_SPLAT_DAMAGE_TEXT = (255, 255, 255)
    HIT_SPLAT_ZERO_BG = (0, 100, 200)
    HIT_SPLAT_ZERO_TEXT = (255, 255, 255)
    HIT_SPLAT_MISS_BG = (100, 100, 100)
    HIT_SPLAT_MISS_TEXT = (200, 200, 200)
    HIT_SPLAT_HEAL_BG = (0, 200, 0)
    HIT_SPLAT_HEAL_TEXT = (255, 255, 255)
    HIT_SPLAT_BORDER = (50, 50, 50)
    
    # Floating text
    FLOATING_TEXT = (255, 255, 200)
    
    # Entity fallback colors (when sprites not loaded)
    ENTITY_PLAYER = (0, 150, 255)
    ENTITY_OTHER_PLAYER = (255, 200, 0)
    ENTITY_NPC = (0, 200, 100)
    ENTITY_MONSTER = (200, 50, 50)
    ENTITY_ITEM = (255, 215, 0)
    ENTITY_FALLBACK_BORDER = (50, 50, 50)
    
    # Tile fallback colors (when tileset not loaded)
    TILE_GRASS = (34, 139, 34)
    TILE_DIRT = (139, 69, 19)
    TILE_STONE = (100, 100, 100)
    TILE_WATER = (0, 105, 148)
    TILE_SAND = (210, 180, 140)
    TILE_FOREST = (34, 100, 34)
    TILE_WALL = (80, 80, 80)
    TILE_DEFAULT = (128, 128, 128)
    
    # Missing chunk indicator
    CHUNK_MISSING_BORDER = (50, 50, 50)
    CHUNK_MISSING_TEXT = (100, 100, 100)
    
    # Context menu
    CONTEXT_ATTACK = (255, 100, 100)
    CONTEXT_EXAMINE = (100, 200, 255)
    
    # Skill category text colors
    SKILL_COMBAT_TEXT = (255, 100, 100)
    SKILL_GATHERING_TEXT = (100, 255, 100)
    SKILL_CRAFTING_TEXT = (100, 200, 255)
    SKILL_OTHER_TEXT = (200, 200, 200)
    
    # Skill category icon colors
    SKILL_COMBAT_ICON = (180, 50, 50)
    SKILL_GATHERING_ICON = (50, 180, 50)
    SKILL_CRAFTING_ICON = (50, 120, 200)
    SKILL_OTHER_ICON = (140, 140, 140)
    
    # Skill block background
    SKILL_BLOCK_BG = (44, 37, 31)
    SKILL_ICON_BORDER = (30, 30, 30)
    
    # Sort button colors
    SORT_BUTTON_ACTIVE_BG = (100, 100, 140)
    SORT_BUTTON_ACTIVE_BORDER = (140, 140, 180)
    SORT_BUTTON_BG = (60, 60, 80)
    
    # Logout button colors
    LOGOUT_HOVER_BG = (180, 80, 80)
    LOGOUT_HOVER_BORDER = (220, 120, 120)
    LOGOUT_BG = (100, 50, 50)
    
    # Button colors (used by modals, customisation panel, etc.)
    BUTTON_BG = (49, 42, 35)
    BUTTON_HOVER = (69, 59, 49)
    
    # Chat hint
    CHAT_HINT_TEXT = (150, 150, 150)
    CHAT_HINT_BG = (30, 30, 30, 180)
    
    # Shutdown warning
    SHUTDOWN_BG = (150, 50, 50)
    SHUTDOWN_BORDER = (255, 100, 100)
    SHUTDOWN_INFO_TEXT = (255, 200, 200)
    
    # Overlay
    OVERLAY_DARK = (0, 0, 0, 180)
    
    # Preview area
    PREVIEW_BG = (40, 40, 40)
    
    # Debug text
    DEBUG_TEXT = (255, 255, 0)
