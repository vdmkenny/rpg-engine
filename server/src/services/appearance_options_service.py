"""
Appearance options service for character customisation.

Provides player-allowed appearance options with server-side enforcement.
This ensures players cannot use options not intended for regular players.
"""

from typing import Dict, List, Any
from common.src.sprites.enums import (
    BodyType, SkinTone, HeadType, HairStyle, HairColor,
    EyeColor, FacialHairStyle, ClothingStyle, PantsStyle,
    ShoesStyle, ClothingColor
)


# Player-allowed options per category
# These restrict what values players can set via the customisation UI
PLAYER_ALLOWED_OPTIONS: Dict[str, List[str]] = {
    # Body type: only human male/female (no child/teen/skeleton/zombie for players)
    "body_type": [
        BodyType.MALE.value,
        BodyType.FEMALE.value,
    ],
    
    # Skin tone: all human + all fantasy (no zombie/fur tones)
    "skin_tone": [
        # Human skin tones
        SkinTone.LIGHT.value,
        SkinTone.OLIVE.value,
        SkinTone.BROWN.value,
        SkinTone.BRONZE.value,
        SkinTone.TAUPE.value,
        SkinTone.BLACK.value,
        SkinTone.AMBER.value,
        # Fantasy skin tones
        SkinTone.BLUE.value,
        SkinTone.GREEN.value,
        SkinTone.BRIGHT_GREEN.value,
        SkinTone.DARK_GREEN.value,
        SkinTone.PALE_GREEN.value,
        SkinTone.LAVENDER.value,
    ],
    
    # Head type: only human male/female (no elderly/gaunt/plump/small/monster heads)
    "head_type": [
        HeadType.HUMAN_MALE.value,
        HeadType.HUMAN_FEMALE.value,
    ],
    
    # Hair style: exclude styles with no sprites on disk
    "hair_style": [
        style.value for style in HairStyle
        if style.value not in {"mohawk", "shortknot", "messy"}
    ],
    
    # Hair color: all colors allowed
    "hair_color": [color.value for color in HairColor],
    
    # Eye color: all colors allowed
    "eye_color": [color.value for color in EyeColor],
    
    # Facial hair style: all styles allowed (including 'none')
    "facial_hair_style": [style.value for style in FacialHairStyle],
    
    # Facial hair color: all hair colors allowed
    "facial_hair_color": [color.value for color in HairColor],
    
    # Shirt style: all styles except "none" (NPCs can go shirtless, players cannot)
    "shirt_style": [style.value for style in ClothingStyle if style != ClothingStyle.NONE],
    
    # Shirt color: all clothing colors allowed
    "shirt_color": [color.value for color in ClothingColor],
    
    # Pants style: all styles except "none" (NPCs can go pantsless, players cannot)
    "pants_style": [style.value for style in PantsStyle if style != PantsStyle.NONE],
    
    # Pants color: all clothing colors allowed
    "pants_color": [color.value for color in ClothingColor],
    
    # Shoes style: all styles allowed
    "shoes_style": [style.value for style in ShoesStyle],
    
    # Shoes color: all clothing colors allowed
    "shoes_color": [color.value for color in ClothingColor],
}


# Field labels for UI display
FIELD_LABELS: Dict[str, str] = {
    "body_type": "Body Type",
    "skin_tone": "Skin Tone",
    "head_type": "Head Type",
    "hair_style": "Hair Style",
    "hair_color": "Hair Color",
    "eye_color": "Eye Color",
    "facial_hair_style": "Facial Hair Style",
    "facial_hair_color": "Facial Hair Color",
    "shirt_style": "Shirt Style",
    "shirt_color": "Shirt Color",
    "pants_style": "Pants Style",
    "pants_color": "Pants Color",
    "shoes_style": "Shoes Style",
    "shoes_color": "Shoes Color",
}


# Restriction metadata for cross-field filtering (e.g., gender-restricted clothing)
# Format: field -> restriction_type -> {option_value: [allowed_values_of_other_field]}
RESTRICTIONS: Dict[str, Dict[str, Any]] = {
    # Shirt styles restricted by body type
    "shirt_style": {
        "body_type_filter": {
            "blouse": ["female"],
            "corset": ["female"],
            "tunic": ["female"],
            "robe": ["female"],
            "vest": ["male"],
        }
    },
    # Shirt colors restricted by shirt style (robe has limited palette)
    "shirt_color": {
        "shirt_style_filter": {
            "robe": [
                "black", "blue", "brown", "dark_brown", "dark_gray",
                "forest_green", "light_gray", "purple", "red", "white", "_brown"
            ]
        }
    },
}


# Option labels for UI display (optional human-friendly names)
OPTION_LABELS: Dict[str, Dict[str, str]] = {
    "body_type": {
        "male": "Male",
        "female": "Female",
    },
    "skin_tone": {
        "light": "Light",
        "olive": "Olive",
        "brown": "Brown",
        "bronze": "Bronze",
        "taupe": "Taupe",
        "black": "Black",
        "amber": "Amber",
        "blue": "Blue",
        "green": "Green",
        "bright_green": "Bright Green",
        "dark_green": "Dark Green",
        "pale_green": "Pale Green",
        "lavender": "Lavender",
    },
    "head_type": {
        "human/male": "Human Male",
        "human/female": "Human Female",
    },
}


def _format_option_label(field: str, value: str) -> str:
    """Format an option value for display.
    
    Args:
        field: The appearance field name
        value: The enum value
        
    Returns:
        Human-readable label for the option
    """
    # Check if we have a specific label for this field+value
    if field in OPTION_LABELS and value in OPTION_LABELS[field]:
        return OPTION_LABELS[field][value]
    
    # Otherwise, convert snake_case to Title Case
    # Handle special cases like "flat_top_fade" -> "Flat Top Fade"
    words = value.replace("_", " ").split()
    
    # Handle "none" specially
    if value == "none":
        return "None"
    
    # Capitalize each word
    return " ".join(word.capitalize() for word in words)


def get_player_appearance_options() -> Dict[str, Any]:
    """Get all appearance options available to regular players.
    
    Returns a structured response suitable for the customisation UI.
    Includes restrictions metadata for cross-field filtering (e.g., gender-specific clothing).
    
    Returns:
        Dictionary with categories list containing field, label, options, and restrictions
    """
    categories = []
    
    for field, allowed_values in PLAYER_ALLOWED_OPTIONS.items():
        options = [
            {
                "value": value,
                "label": _format_option_label(field, value)
            }
            for value in allowed_values
        ]
        
        category = {
            "field": field,
            "label": FIELD_LABELS.get(field, field.replace("_", " ").title()),
            "options": options
        }
        
        # Add restrictions metadata if this field has any
        if field in RESTRICTIONS:
            category["restrictions"] = RESTRICTIONS[field]
        
        categories.append(category)
    
    return {"categories": categories}


def is_value_allowed_for_player(field: str, value: str) -> bool:
    """Check if a specific appearance value is allowed for players.
    
    Args:
        field: The appearance field name (e.g., "body_type")
        value: The value to check (e.g., "male")
        
    Returns:
        True if the value is in the player allowlist, False otherwise
    """
    if field not in PLAYER_ALLOWED_OPTIONS:
        # Unknown fields are not allowed
        return False
    
    return value in PLAYER_ALLOWED_OPTIONS[field]
