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
    SKELETON = "skeleton/adult"
    ZOMBIE = "zombie/adult"
    VAMPIRE = "vampire/adult"
    ORC = "orc/male"
    GOBLIN = "goblin/child"
    TROLL = "troll/adult"
    WOLF = "wolf/male"
    LIZARD = "lizard/male"
    MINOTAUR = "minotaur/male"

    # Special heads
    FRANKENSTEIN = "frankenstein/adult"
    JACK = "jack/adult"  # Jack-o-lantern


class HairStyle(str, Enum):
    """
    LPC hair styles.
    
    Complete enumeration of all available styles. Values match folder names in hair/.
    Most styles only support "adult" age group.
    """
    # No hair
    BALD = "bald"
    BALDING = "balding"
    
    # Very short / buzzed styles
    BUZZCUT = "buzzcut"
    HIGH_AND_TIGHT = "high_and_tight"
    FLAT_TOP_FADE = "flat_top_fade"
    FLAT_TOP_STRAIGHT = "flat_top_straight"
    
    # Short styles
    PLAIN = "plain"
    PIXIE = "pixie"
    SHORTHAWK = "shorthawk"
    SHORTKNOT = "shortknot"
    MESSY = "messy"
    MESSY1 = "messy1"
    MESSY2 = "messy2"
    MESSY3 = "messy3"
    BEDHEAD = "bedhead"
    PARTED = "parted"
    PARTED2 = "parted2"
    PARTED3 = "parted3"
    PARTED_SIDE_BANGS = "parted_side_bangs"
    PARTED_SIDE_BANGS2 = "parted_side_bangs2"
    CURLY_SHORT = "curly_short"
    CURLY_SHORT2 = "curly_short2"
    
    # Spiked styles
    SPIKED = "spiked"
    SPIKED2 = "spiked2"
    SPIKED_BEEHIVE = "spiked_beehive"
    SPIKED_LIBERTY = "spiked_liberty"
    SPIKED_LIBERTY2 = "spiked_liberty2"
    SPIKED_PORCUPINE = "spiked_porcupine"
    MOHAWK = "mohawk"
    
    # Bob / medium-short styles
    BOB = "bob"
    BOB_SIDE_PART = "bob_side_part"
    PAGE = "page"
    PAGE2 = "page2"
    LOB = "lob"
    SWOOP = "swoop"
    SWOOP_SIDE = "swoop_side"
    BANGS = "bangs"
    BANGSSHORT = "bangsshort"
    BANGS_BUN = "bangs_bun"
    
    # Bangs / long bangs styles
    BANGSLONG = "bangslong"
    BANGSLONG2 = "bangslong2"
    CURTAINS = "curtains"
    CURTAINS_LONG = "curtains_long"
    
    # Medium length styles
    MOP = "mop"
    SINGLE = "single"
    UNKEMPT = "unkempt"
    NATURAL = "natural"
    HALFMESSY = "halfmessy"
    HALF_UP = "half_up"
    IDOL = "idol"
    
    # Braids and twists
    BRAID = "braid"
    BRAID2 = "braid2"
    CORNROWS = "cornrows"
    DREADLOCKS_SHORT = "dreadlocks_short"
    DREADLOCKS_LONG = "dreadlocks_long"
    TWISTS_FADE = "twists_fade"
    TWISTS_STRAIGHT = "twists_straight"
    
    # Curls and waves (medium)
    CURLS_LARGE = "curls_large"
    WAVY = "wavy"
    
    # Long styles
    LONG = "long"
    LONG_BAND = "long_band"
    LONG_CENTER_PART = "long_center_part"
    LONG_MESSY = "long_messy"
    LONG_MESSY2 = "long_messy2"
    LONG_STRAIGHT = "long_straight"
    LONG_TIED = "long_tied"
    LONGHAWK = "longhawk"
    
    # Extra long styles
    XLONG = "xlong"
    XLONG_WAVY = "xlong_wavy"
    CURLS_LARGE_XLONG = "curls_large_xlong"
    CURLY_LONG = "curly_long"
    RELM_XLONG = "relm_xlong"
    
    # Shoulder length
    SHOULDERL = "shoulderl"
    SHOULDERR = "shoulderr"
    
    # Ponytails and pigtails
    PONYTAIL = "ponytail"
    PONYTAIL2 = "ponytail2"
    HIGH_PONYTAIL = "high_ponytail"
    RELM_PONYTAIL = "relm_ponytail"
    PIGTAILS = "pigtails"
    PIGTAILS_BANGS = "pigtails_bangs"
    BUNCHES = "bunches"
    
    # Updos and buns
    PRINCESS = "princess"
    RELM_SHORT = "relm_short"
    
    # Voluminous / afro styles
    AFRO = "afro"
    JEWFRO = "jewfro"
    
    # Character-specific styles
    SARA = "sara"


class HairColor(str, Enum):
    """
    LPC hair colors.
    
    Values match actual filenames in hair/{style}/{age_group}/{animation}/.
    """
    # All colors that exist as actual .png files
    ASH = "ash"
    BLACK = "black"
    BLONDE = "blonde"
    BLUE = "blue"
    CARROT = "carrot"
    CHESTNUT = "chestnut"
    DARK_BROWN = "dark_brown"
    DARK_GRAY = "dark_gray"
    GINGER = "ginger"
    GOLD = "gold"
    GRAY = "gray"
    GREEN = "green"
    LIGHT_BROWN = "light_brown"
    NAVY = "navy"
    ORANGE = "orange"
    PINK = "pink"
    PLATINUM = "platinum"
    PURPLE = "purple"
    RAVEN = "raven"
    RED = "red"
    REDHEAD = "redhead"
    ROSE = "rose"
    SANDY = "sandy"
    STRAWBERRY = "strawberry"
    VIOLET = "violet"
    WHITE = "white"


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
    Color is controlled separately via facial_hair_color field.
    """
    NONE = "none"
    STUBBLE = "stubble"
    BEARD = "beard"
    MUSTACHE = "mustache"
    GOATEE = "goatee"


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
    SHIRT = "shirt"
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
    # Hair behind head (for multi-layer styles like ponytail)
    HAIR_BEHIND = -1
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
