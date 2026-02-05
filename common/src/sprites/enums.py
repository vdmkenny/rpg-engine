"""
LPC (Liberated Pixel Cup) Sprite Enums

Type-safe enumerations for all LPC sprite attributes.
These enums match the file/folder structure of the LPC Universal Spritesheet Generator.

License: The sprites these enums reference are licensed under CC-BY-SA 3.0, OGA-BY 3.0, and GPL 3.0.
See server/sprites/CREDITS.csv for full attribution.
"""

from enum import Enum
from typing import Set, Dict


class BodyType(str, Enum):
    """
    LPC body base types.
    
    These correspond to folders in spritesheets/body/bodies/
    Note: muscular and pregnant are available but excluded per project requirements.
    """
    MALE = "male"
    FEMALE = "female"
    CHILD = "child"
    TEEN = "teen"
    SKELETON = "skeleton"
    ZOMBIE = "zombie"


class SkinTone(str, Enum):
    """
    LPC skin tone variants.
    
    Matches PNG filenames in body/{type}/ folders.
    Includes human, fantasy, undead, and fur tones.
    """
    # Human skin tones
    LIGHT = "light"
    OLIVE = "olive"
    BROWN = "brown"
    BRONZE = "bronze"
    TAUPE = "taupe"
    BLACK = "black"
    AMBER = "amber"
    
    # Fantasy skin tones (for orcs, goblins, etc.)
    BLUE = "blue"
    GREEN = "green"
    BRIGHT_GREEN = "bright_green"
    DARK_GREEN = "dark_green"
    PALE_GREEN = "pale_green"
    LAVENDER = "lavender"
    
    # Undead skin tones
    ZOMBIE = "zombie"
    ZOMBIE_GREEN = "zombie_green"
    
    # Fur tones (for beast/animal races)
    FUR_BLACK = "fur_black"
    FUR_BROWN = "fur_brown"
    FUR_WHITE = "fur_white"
    FUR_GREY = "fur_grey"
    FUR_TAN = "fur_tan"
    FUR_COPPER = "fur_copper"
    FUR_GOLD = "fur_gold"


class HeadType(str, Enum):
    """
    LPC head types.
    
    Values are path segments for head sprite lookup (e.g., "human/male").
    Combines race and variant into a single enum for simplicity.
    """
    # Human heads - standard
    HUMAN_MALE = "human/male"
    HUMAN_FEMALE = "human/female"
    HUMAN_CHILD = "human/child"
    
    # Human heads - age variants
    HUMAN_MALE_ELDERLY = "human/male_elderly"
    HUMAN_FEMALE_ELDERLY = "human/female_elderly"
    
    # Human heads - body variants
    HUMAN_MALE_GAUNT = "human/male_gaunt"
    HUMAN_MALE_PLUMP = "human/male_plump"
    HUMAN_MALE_SMALL = "human/male_small"
    HUMAN_FEMALE_SMALL = "human/female_small"
    HUMAN_ELDERLY_SMALL = "human/elderly_small"
    
    # Monster/creature heads
    SKELETON = "skeleton/default"
    ZOMBIE = "zombie/default"
    VAMPIRE = "vampire/default"
    ORC = "orc/default"
    GOBLIN = "goblin/default"
    TROLL = "troll/default"
    WOLF = "wolf/default"
    LIZARD = "lizard/default"
    MINOTAUR = "minotaur/default"
    
    # Special heads
    FRANKENSTEIN = "frankenstein/default"
    JACK = "jack/default"  # Jack-o-lantern


class HairStyle(str, Enum):
    """
    LPC hair styles.
    
    Curated subset of available styles. Values match folder names in hair/.
    Most styles only support "adult" age group.
    """
    # No hair
    BALD = "bald"
    
    # Short styles
    SHORT = "short"
    SHORTHAWK = "shorthawk"
    SHORTKNOT = "shortknot"
    BUZZCUT = "buzzcut"
    PIXIE = "pixie"
    PLAIN = "plain"
    PARTED = "parted"
    MESSY1 = "messy1"
    MESSY2 = "messy2"
    BEDHEAD = "bedhead"
    
    # Medium styles
    BANGS = "bangs"
    BANGSLONG = "bangslong"
    BANGSLONG2 = "bangslong2"
    BANGSSHORT = "bangsshort"
    PAGE = "page"
    BOB = "bob"
    SWOOP = "swoop"
    UNKEMPT = "unkempt"
    HALFMESSY = "halfmessy"
    CURLY_SHORT = "curly_short"
    
    # Long styles
    LONG = "long"
    LONGHAWK = "longhawk"
    LONGKNOT = "longknot"
    LOOSE = "loose"
    XLONG = "xlong"
    XLONGKNOT = "xlongknot"
    SHOULDERL = "shoulderl"
    SHOULDERR = "shoulderr"
    PRINCESS = "princess"
    CURLY_LONG = "curly_long"
    
    # Ponytails and updos
    PONYTAIL = "ponytail"
    PONYTAIL2 = "ponytail2"
    HIGH_PONYTAIL = "high_ponytail"
    BUNCHES = "bunches"
    BRAID = "braid"
    
    # Special styles
    MOHAWK = "mohawk"
    JEWFRO = "jewfro"
    AFRO = "afro"
    DREADLOCKS_SHORT = "dreadlocks_short"
    DREADLOCKS_LONG = "dreadlocks_long"
    CORNROWS = "cornrows"


class HairColor(str, Enum):
    """
    LPC hair colors.
    
    Values match folder names in hair/{style}/.
    """
    # Natural colors
    BLACK = "black"
    BROWN = "brown"
    BROWN2 = "brown2"
    BRUNETTE = "brunette"
    BRUNETTE2 = "brunette2"
    BLONDE = "blonde"
    BLONDE2 = "blonde2"
    DARK_BLONDE = "dark-blonde"
    LIGHT_BLONDE = "light-blonde"
    LIGHT_BLONDE2 = "light-blonde2"
    GOLD = "gold"
    RED = "red"
    REDHEAD = "redhead"
    REDHEAD2 = "redhead2"
    RAVEN = "raven"
    RAVEN2 = "raven2"
    GRAY = "gray"
    WHITE = "white"
    WHITE_BLONDE = "white-blonde"
    WHITE_BLONDE2 = "white-blonde2"
    
    # Fantasy colors
    BLUE = "blue"
    BLUE2 = "blue2"
    GREEN = "green"
    GREEN2 = "green2"
    PINK = "pink"
    PINK2 = "pink2"
    PURPLE = "purple"
    ORANGE = "orange"
    WHITE_CYAN = "white-cyan"


class EyeColor(str, Enum):
    """
    LPC eye colors.
    
    Values match filenames in eyes/human/{age_group}/.
    """
    BLUE = "blue"
    BROWN = "brown"
    GRAY = "gray"
    GREEN = "green"
    ORANGE = "orange"
    PURPLE = "purple"
    RED = "red"
    YELLOW = "yellow"


class EyeAgeGroup(str, Enum):
    """
    Age groups for eye sprites.

    Different eye sprites exist for different age groups.
    """
    ADULT = "adult"
    CHILD = "child"
    ELDERLY = "elderly"


class FacialHairStyle(str, Enum):
    """
    Facial hair styles (beards, mustaches).

    Available in LPC face/beard/ spritesheets.
    Can be used by any body type, defaults to none for female bodies.
    """
    NONE = "none"
    STUBBLE = "stubble"
    BEARD_BLACK = "beard_black"  # Full black beard
    BEARD_BLONDE = "beard_blonde"  # Full blonde beard
    BEARD_BROWN = "beard_brown"  # Full brown beard
    BEARD_GRAY = "beard_gray"  # Gray beard (for elders)
    MUSTACHE_BLACK = "mustache_black"
    MUSTACHE_BLONDE = "mustache_blonde"
    MUSTACHE_BROWN = "mustache_brown"
    GOATEE_BLACK = "goatee_black"
    GOATEE_BLONDE = "goatee_blonde"
    GOATEE_BROWN = "goatee_brown"


class AnimationType(str, Enum):
    """
    LPC animation types.
    
    Not all body types support all animations.
    Use supports_animation() to check compatibility.
    """
    # Core animations (most body types)
    WALK = "walk"
    HURT = "hurt"
    
    # Combat animations
    SLASH = "slash"
    THRUST = "thrust"
    SPELLCAST = "spellcast"
    SHOOT = "shoot"
    BACKSLASH = "backslash"
    HALFSLASH = "halfslash"
    
    # Idle animations (not available for skeleton/zombie)
    IDLE = "idle"
    COMBAT_IDLE = "combat_idle"
    
    # Extended animations (adult bodies only)
    RUN = "run"
    CLIMB = "climb"
    JUMP = "jump"
    SIT = "sit"
    EMOTE = "emote"


class ClothingStyle(str, Enum):
    """
    Base clothing styles for characters.

    These are worn under armor and determine the visual base layer.
    LPC assets have both style and color variations.
    """
    # Shirts/Tops
    NONE = "none"
    LONGSLEEVE = "longsleeve2"
    SHORTSLEEVE = "shortsleeve"
    SLEEVELESS = "sleeveless"
    TUNIC = "tunic"
    VEST = "vest"
    BLOUSE = "blouse"
    CORSET = "corset"
    ROBE = "robe"


class PantsStyle(str, Enum):
    """
    Base pants/leg styles for characters.

    Worn under leg armor.
    """
    NONE = "none"
    PANTS = "pants"
    SHORTS = "shorts"
    LEGGINGS = "leggings"
    PANTALOONS = "pantaloons"
    SKIRT = "skirts"


class ShoesStyle(str, Enum):
    """
    Base footwear styles for characters.

    Worn under boots/armor.
    """
    NONE = "none"
    SHOES = "shoes/basic"
    BOOTS = "boots"  # Basic boots
    SANDALS = "sandals"
    SLIPPERS = "slippers"


class ClothingColor(str, Enum):
    """
    Colors for base clothing items.

    Available in LPC clothing spritesheets.
    """
    # Neutrals
    WHITE = "white"
    BLACK = "black"
    GRAY = "gray"
    CHARCOAL = "charcoal"
    SLATE = "slate"

    # Browns
    BROWN = "brown"
    TAN = "tan"
    LEATHER = "leather"
    WALNUT = "walnut"

    # Blues
    BLUE = "blue"
    NAVY = "navy"
    SKY = "sky"
    BLUEGRAY = "bluegray"
    TEAL = "teal"

    # Greens
    GREEN = "green"
    FOREST = "forest"

    # Reds/Pinks
    RED = "red"
    MAROON = "maroon"
    PINK = "pink"
    ROSE = "rose"
    ORANGE = "orange"

    # Other
    PURPLE = "purple"
    LAVENDER = "lavender"
    YELLOW = "yellow"


class SpriteLayer(int, Enum):
    """
    Rendering order for paperdoll sprite compositing.

    Lower values are rendered first (behind).
    Higher values are rendered on top.
    """
    # Base layers
    BODY = 0
    HEAD = 1
    EYES = 2

    # Facial features
    FACIAL_HAIR = 3
    HAIR = 4

    # Base clothing (new layers between body and armor)
    CLOTHING_PANTS = 7
    CLOTHING_SHOES = 8
    CLOTHING_SHIRT = 9

    # Equipment - body
    ARMOR_BODY = 10
    ARMOR_FEET = 11
    ARMOR_LEGS = 12
    ARMOR_HANDS = 13
    ARMOR_HEAD = 14

    # Equipment - accessories
    CAPE_BEHIND = 18
    BACK = 19  # Backpacks, quivers

    # Equipment - weapons
    WEAPON_BEHIND = 20
    SHIELD = 22
    WEAPON_FRONT = 25

    # Overlay effects
    CAPE_FRONT = 30


class EquipmentSlot(str, Enum):
    """
    Equipment slots for character paperdoll.

    Matches server/src/schemas/item.py EquipmentSlot for consistency.
    Maps to visual rendering layers.
    """
    HEAD = "head"           # Helmets, hats
    CAPE = "cape"           # Capes and cloaks
    AMULET = "amulet"       # Neck slot (not visible)
    WEAPON = "weapon"       # Primary weapon
    BODY = "body"           # Chest armor, robes
    SHIELD = "shield"       # Shield, offhand weapon
    LEGS = "legs"           # Leg armor, pants
    GLOVES = "gloves"       # Gloves, gauntlets (renamed from HANDS)
    BOOTS = "boots"         # Boots, shoes (renamed from FEET)
    RING = "ring"           # Ring slot (not visible)
    AMMO = "ammo"           # Ammunition (arrows, bolts, etc.)


# =============================================================================
# Animation Compatibility Mapping
# =============================================================================

# Which animations each body type supports
BODY_ANIMATIONS: Dict[BodyType, Set[AnimationType]] = {
    BodyType.MALE: {
        AnimationType.WALK, AnimationType.IDLE, AnimationType.HURT,
        AnimationType.SLASH, AnimationType.THRUST, AnimationType.SPELLCAST,
        AnimationType.SHOOT, AnimationType.RUN, AnimationType.CLIMB,
        AnimationType.JUMP, AnimationType.SIT, AnimationType.EMOTE,
        AnimationType.COMBAT_IDLE, AnimationType.BACKSLASH, AnimationType.HALFSLASH,
    },
    BodyType.FEMALE: {
        AnimationType.WALK, AnimationType.IDLE, AnimationType.HURT,
        AnimationType.SLASH, AnimationType.THRUST, AnimationType.SPELLCAST,
        AnimationType.SHOOT, AnimationType.RUN, AnimationType.CLIMB,
        AnimationType.JUMP, AnimationType.SIT, AnimationType.EMOTE,
        AnimationType.COMBAT_IDLE, AnimationType.BACKSLASH, AnimationType.HALFSLASH,
    },
    BodyType.TEEN: {
        AnimationType.WALK, AnimationType.IDLE, AnimationType.HURT,
        AnimationType.SLASH, AnimationType.THRUST, AnimationType.SPELLCAST,
        AnimationType.SHOOT, AnimationType.RUN, AnimationType.CLIMB,
        AnimationType.JUMP, AnimationType.SIT, AnimationType.EMOTE,
        AnimationType.COMBAT_IDLE, AnimationType.BACKSLASH, AnimationType.HALFSLASH,
    },
    BodyType.CHILD: {
        AnimationType.WALK, AnimationType.IDLE, AnimationType.HURT,
        AnimationType.SLASH, AnimationType.JUMP, AnimationType.SIT,
    },
    BodyType.SKELETON: {
        AnimationType.WALK, AnimationType.HURT, AnimationType.SLASH,
        AnimationType.THRUST, AnimationType.SPELLCAST, AnimationType.SHOOT,
    },
    BodyType.ZOMBIE: {
        AnimationType.WALK, AnimationType.HURT, AnimationType.SLASH,
        AnimationType.THRUST, AnimationType.SPELLCAST, AnimationType.SHOOT,
    },
}


def supports_animation(body_type: BodyType, animation: AnimationType) -> bool:
    """
    Check if a body type supports a specific animation.
    
    Args:
        body_type: The body type to check
        animation: The animation type to check
        
    Returns:
        True if the body type supports the animation, False otherwise
    """
    supported = BODY_ANIMATIONS.get(body_type, set())
    return animation in supported


def get_fallback_animation(body_type: BodyType, animation: AnimationType) -> AnimationType:
    """
    Get fallback animation for unsupported animation on a body type.
    
    For example, skeleton/zombie don't have IDLE, so we fall back to WALK frame 0.
    
    Args:
        body_type: The body type
        animation: The desired animation
        
    Returns:
        The original animation if supported, or a fallback animation
    """
    if supports_animation(body_type, animation):
        return animation
    
    # Skeleton/Zombie have no IDLE - use WALK (render frame 0 for idle effect)
    if animation == AnimationType.IDLE:
        return AnimationType.WALK
    
    # Combat idle fallback
    if animation == AnimationType.COMBAT_IDLE:
        if supports_animation(body_type, AnimationType.IDLE):
            return AnimationType.IDLE
        return AnimationType.WALK
    
    # Extended animations fallback to walk
    if animation in {AnimationType.RUN, AnimationType.CLIMB, AnimationType.JUMP}:
        return AnimationType.WALK
    
    # Default fallback
    return AnimationType.WALK


def get_eye_age_group(body_type: BodyType, head_type: HeadType) -> EyeAgeGroup:
    """
    Determine the appropriate eye age group for a body/head combination.
    
    Args:
        body_type: The character's body type
        head_type: The character's head type
        
    Returns:
        The appropriate eye age group
    """
    if body_type == BodyType.CHILD:
        return EyeAgeGroup.CHILD
    
    if head_type in {
        HeadType.HUMAN_MALE_ELDERLY,
        HeadType.HUMAN_FEMALE_ELDERLY,
        HeadType.HUMAN_ELDERLY_SMALL,
    }:
        return EyeAgeGroup.ELDERLY
    
    return EyeAgeGroup.ADULT
