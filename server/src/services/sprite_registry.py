"""
Sprite Registry Service

Server-side validation for LPC sprites and equipment sprite mappings.
Ensures all referenced sprite IDs have valid LPC assets.
"""

import json
import csv
from pathlib import Path
from typing import Set, Optional, Dict, Any
from dataclasses import dataclass

from server.src.core.logging_config import get_logger
from common.src.sprites.equipment_mapping import EQUIPMENT_SPRITES

logger = get_logger(__name__)


@dataclass
class SpriteValidationResult:
    """Result of sprite validation."""
    valid: bool
    error_message: Optional[str] = None
    missing_sprites: list = None


class SpriteRegistry:
    """
    Registry of available LPC sprites for server-side validation.
    
    Loads sprite manifest from disk and validates equipment sprite IDs.
    """
    
    def __init__(self, sprites_dir: Optional[Path] = None):
        """
        Initialize sprite registry.
        
        Args:
            sprites_dir: Path to sprites directory (default: server/sprites/lpc)
        """
        if sprites_dir is None:
            # Default to server/sprites relative to project root
            self.sprites_dir = Path(__file__).parent.parent.parent / "sprites" / "lpc"
        else:
            self.sprites_dir = Path(sprites_dir)
        
        self._available_sprites: Set[str] = set()
        self._credits_data: Dict[str, Dict[str, Any]] = {}
        self._loaded = False
    
    def load(self) -> None:
        """Load sprite manifest from CREDITS.csv."""
        if self._loaded:
            return
        
        credits_file = self.sprites_dir.parent / "CREDITS.csv"
        
        if not credits_file.exists():
            logger.warning(
                "CREDITS.csv not found, skipping sprite validation",
                extra={"path": str(credits_file)}
            )
            self._loaded = True
            return
        
        try:
            with open(credits_file, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None)  # Skip header
                
                for row in reader:
                    if len(row) >= 1:
                        sprite_path = row[0].strip('"')
                        if sprite_path:
                            self._available_sprites.add(sprite_path)
                            
                            # Store credits info if available
                            if len(row) >= 5:
                                self._credits_data[sprite_path] = {
                                    "notes": row[1] if len(row) > 1 else "",
                                    "authors": row[2] if len(row) > 2 else "",
                                    "licenses": row[3] if len(row) > 3 else "",
                                    "urls": row[4] if len(row) > 4 else ""
                                }
            
            logger.info(
                "Loaded sprite registry",
                extra={"sprite_count": len(self._available_sprites)}
            )
            self._loaded = True
            
        except Exception as e:
            logger.error(
                "Error loading sprite registry",
                extra={"error": str(e)}
            )
            self._loaded = True  # Mark as loaded to prevent repeated attempts
    
    def is_valid_sprite(self, sprite_path: str) -> bool:
        """
        Check if a sprite path exists in the registry.
        
        Args:
            sprite_path: Path like "hair/short/adult/walk/brown.png"
            
        Returns:
            True if sprite exists
        """
        if not self._loaded:
            self.load()
        
        return sprite_path in self._available_sprites
    
    def validate_equipment_sprite(self, sprite_id: str) -> SpriteValidationResult:
        """
        Validate that an equipment sprite ID has a valid mapping.
        
        Args:
            sprite_id: The equipped_sprite_id from ItemDefinition
            
        Returns:
            SpriteValidationResult with validation status
        """
        if not self._loaded:
            self.load()
        
        # Check if sprite ID exists in equipment mapping
        if sprite_id not in EQUIPMENT_SPRITES:
            return SpriteValidationResult(
                valid=False,
                error_message=f"Equipment sprite ID '{sprite_id}' not found in mapping",
                missing_sprites=[sprite_id]
            )
        
        return SpriteValidationResult(valid=True)
    
    def validate_batch(self, sprite_ids: list) -> SpriteValidationResult:
        """
        Validate multiple equipment sprite IDs.
        
        Args:
            sprite_ids: List of equipped_sprite_id values
            
        Returns:
            SpriteValidationResult with validation status
        """
        if not self._loaded:
            self.load()
        
        missing = []
        for sprite_id in sprite_ids:
            if sprite_id not in EQUIPMENT_SPRITES:
                missing.append(sprite_id)
        
        if missing:
            return SpriteValidationResult(
                valid=False,
                error_message=f"{len(missing)} equipment sprite ID(s) not found in mapping",
                missing_sprites=missing
            )
        
        return SpriteValidationResult(valid=True)
    
    def get_missing_sprites_report(self) -> str:
        """Generate report of all equipment sprites with missing LPC assets."""
        if not self._loaded:
            self.load()
        
        missing = []
        for sprite_id, sprite_info in EQUIPMENT_SPRITES.items():
            # Get the base path for this sprite
            path = sprite_info.get_path(animation="walk")
            
            # Check if this path exists (note: this is a simplified check)
            # In reality, we'd need to check all animation variants
            if not self.is_valid_sprite(path):
                missing.append({
                    "sprite_id": sprite_id,
                    "expected_path": path,
                    "base_path": sprite_info.base_path,
                    "variant": sprite_info.variant
                })
        
        if not missing:
            return "All equipment sprites have valid LPC assets."
        
        report = f"Missing LPC Assets ({len(missing)} sprites):\n"
        for item in missing[:20]:  # Limit to first 20
            report += f"  - {item['sprite_id']}: {item['expected_path']}\n"
        
        if len(missing) > 20:
            report += f"  ... and {len(missing) - 20} more\n"
        
        return report


# Global registry instance
sprite_registry = SpriteRegistry()


def validate_item_sprite_sync() -> None:
    """
    Validate all equipment sprites at item sync time.
    
    This should be called during application startup to ensure
    all item definitions reference valid sprites.
    """
    from server.src.core.items import ItemType, ItemDefinition
    
    logger.info("Validating equipment sprites at sync time")
    
    invalid_items = []
    
    for item_type in ItemType:
        defn = item_type.value
        if defn.equipped_sprite_id:
            result = sprite_registry.validate_equipment_sprite(defn.equipped_sprite_id)
            if not result.valid:
                invalid_items.append({
                    "item": item_type.name,
                    "sprite_id": defn.equipped_sprite_id,
                    "error": result.error_message
                })
                logger.warning(
                    "Item has invalid sprite ID",
                    extra={
                        "item": item_type.name,
                        "sprite_id": defn.equipped_sprite_id,
                        "error": result.error_message
                    }
                )
    
    if invalid_items:
        logger.warning(
            f"Found {len(invalid_items)} items with invalid sprite IDs",
            extra={"invalid_count": len(invalid_items)}
        )
    else:
        logger.info("All equipment sprite IDs are valid")


def get_sprite_validation_summary() -> Dict[str, Any]:
    """Get summary of sprite validation status."""
    return {
        "sprites_loaded": len(sprite_registry._available_sprites),
        "equipment_mappings": len(EQUIPMENT_SPRITES),
        "validation_ready": sprite_registry._loaded
    }
