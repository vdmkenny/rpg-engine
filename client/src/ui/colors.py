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
    TEXT_DARK = (49, 42, 35)
    
    # Health bar colors
    HP_GREEN = (0, 255, 0)
    HP_RED = (255, 0, 0)
    HP_BG = (0, 0, 0)
    HP_BORDER = (0, 0, 0)
    
    # XP bar colors
    XP_GREEN = (0, 180, 0)
    XP_BG = (40, 40, 40)
    
    # Rarity colors
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
    
    # Combat
    HIT_SPLAT_DAMAGE = (255, 0, 0)
    HIT_SPLAT_MISS = (0, 128, 255)
    HIT_SPLAT_HEAL = (0, 255, 0)
    
    # Button colors (used by modals, customisation panel, etc.)
    BUTTON_BG = (49, 42, 35)       # Same as PANEL_BG
    BUTTON_HOVER = (69, 59, 49)    # Same as PANEL_INNER_BORDER
    WHITE = (255, 255, 255)        # Alias for TEXT_WHITE
    BLACK = (0, 0, 0)              # Pure black
