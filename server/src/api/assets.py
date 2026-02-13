"""
API endpoints for serving game assets (tilesets, sprites, images, etc.) with authentication.

This module provides:
- Tileset endpoints for map rendering
- Sprite endpoints for LPC character spritesheets

Sprite files are served from server/sprites/lpc/ which should be populated by
running scripts/setup_lpc_sprites.py before first use.
"""

import json
from pathlib import Path
from typing import List, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse

from server.src.core.logging_config import get_logger
from server.src.core.security import get_current_user
from server.src.services.map_service import get_map_manager
from server.src.core.config import settings

router = APIRouter()
logger = get_logger(__name__)

# =============================================================================
# Sprite directory configuration
# =============================================================================

# Base directory for LPC sprite assets
SPRITES_BASE_DIR = Path("server/sprites/lpc")

# Allowed sprite file extensions
ALLOWED_SPRITE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


@router.get(
    "/maps/{map_id}/tilesets",
    response_model=List[Dict],
    summary="Get tileset metadata for a specific map",
    description="Returns list of tilesets used by the specified map with metadata for asset loading",
)
async def get_map_tilesets(
    map_id: str,
    current_user = Depends(get_current_user),
) -> List[Dict]:
    """
    Get tileset metadata for a map. Requires authentication.
    
    Args:
        map_id: The ID of the map to get tilesets for
        current_user: Authenticated user (dependency injection)
        db: Database session (dependency injection)
        
    Returns:
        List of tileset metadata dictionaries
        
    Raises:
        HTTPException: If map not found or user not authenticated
    """
    map_manager = get_map_manager()
    
    if map_id not in map_manager.maps:
        logger.warning(
            "Map tileset request for non-existent map",
            extra={"map_id": map_id, "user": current_user.username}
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Map '{map_id}' not found"
        )
    
    tile_map = map_manager.maps[map_id]
    tilesets = tile_map.get_tileset_metadata()
    
    logger.debug(
        "Tileset metadata requested",
        extra={
            "map_id": map_id,
            "user": current_user.username,
            "tileset_count": len(tilesets)
        }
    )
    
    return tilesets


@router.get(
    "/tilesets/{tileset_id}/metadata", 
    response_model=Dict,
    summary="Get metadata for a specific tileset",
    description="Returns detailed metadata for a tileset including dimensions and tile count",
)
async def get_tileset_metadata(
    tileset_id: str,
    current_user = Depends(get_current_user),
) -> Dict:
    """
    Get detailed metadata for a specific tileset. Requires authentication.
    
    Args:
        tileset_id: The ID of the tileset
        current_user: Authenticated user (dependency injection)
        db: Database session (dependency injection)
        
    Returns:
        Tileset metadata dictionary
        
    Raises:
        HTTPException: If tileset not found or user not authenticated
    """
    map_manager = get_map_manager()
    
    # Search all maps for the tileset
    for map_id, tile_map in map_manager.maps.items():
        tilesets = tile_map.get_tileset_metadata()
        for tileset in tilesets:
            if tileset.get("id") == tileset_id:
                logger.debug(
                    "Tileset metadata requested",
                    extra={
                        "tileset_id": tileset_id,
                        "user": current_user.username,
                        "source_map": map_id
                    }
                )
                return tileset
    
    logger.warning(
        "Tileset metadata request for non-existent tileset",
        extra={"tileset_id": tileset_id, "user": current_user.username}
    )
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Tileset '{tileset_id}' not found"
    )


@router.get(
    "/tilesets/{image_filename}",
    summary="Download tileset image file",
    description="Serves tileset image files (PNG) for client rendering. Requires authentication.",
    response_class=FileResponse,
)
async def get_tileset_image(
    image_filename: str,
    current_user = Depends(get_current_user),
) -> FileResponse:
    """
    Serve tileset image files. Requires authentication for security.
    
    Args:
        image_filename: Name of the image file (e.g., "[Base]BaseChip_pipo.png")
        current_user: Authenticated user (dependency injection)
        db: Database session (dependency injection)
        
    Returns:
        FileResponse containing the image file
        
    Raises:
        HTTPException: If file not found or user not authenticated
    """
    # Construct the full path to the image file
    tilesets_dir = Path("server/tilesets")
    image_path = tilesets_dir / image_filename
    
    # Security check: ensure the path is within the tilesets directory
    try:
        image_path = image_path.resolve()
        tilesets_dir = tilesets_dir.resolve()
        if not str(image_path).startswith(str(tilesets_dir)):
            logger.warning(
                "Attempted path traversal attack",
                extra={
                    "image_file": image_filename,
                    "user": current_user.username,
                    "resolved_path": str(image_path)
                }
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
    except (OSError, ValueError):
        logger.warning(
            "Invalid image filename requested",
            extra={"image_file": image_filename, "user": current_user.username}
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename"
        )
    
    # Check if file exists
    if not image_path.exists() or not image_path.is_file():
        logger.warning(
            "Tileset image not found",
            extra={"image_file": image_filename, "user": current_user.username}
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image file '{image_filename}' not found"
        )
    
    # Verify it's an image file
    if not image_filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
        logger.warning(
            "Non-image file requested",
            extra={"image_file": image_filename, "user": current_user.username}
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only image files are allowed"
        )
    
    logger.debug(
        "Tileset image served",
        extra={
            "image_file": image_filename,
            "user": current_user.username,
            "file_size": image_path.stat().st_size
        }
    )
    
    return FileResponse(
        path=str(image_path),
        media_type="image/png",
        filename=image_filename
    )


# =============================================================================
# Sprite Endpoints - LPC Character Spritesheets
# =============================================================================


@router.get(
    "/sprites/manifest",
    response_model=Dict,
    summary="Get sprite manifest",
    description="Returns the manifest of available LPC sprite assets.",
)
async def get_sprite_manifest(
    current_user = Depends(get_current_user),
) -> Dict:
    """
    Get the sprite manifest listing all available sprite assets.
    
    The manifest is generated by scripts/setup_lpc_sprites.py when
    downloading sprite assets.
    
    Args:
        current_user: Authenticated user (dependency injection)
        
    Returns:
        Manifest dictionary with sprite categories and paths
        
    Raises:
        HTTPException: If manifest not found or sprites not downloaded
    """
    manifest_path = SPRITES_BASE_DIR / "manifest.json"
    
    if not manifest_path.exists():
        logger.warning(
            "Sprite manifest not found - sprites may not be downloaded",
            extra={"user": current_user.username}
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sprite manifest not found. Run scripts/setup_lpc_sprites.py to download sprites."
        )
    
    try:
        with open(manifest_path, "r") as f:
            manifest = json.load(f)
        
        logger.debug(
            "Sprite manifest served",
            extra={
                "user": current_user.username,
                "category_count": len(manifest.get("categories", {})),
            }
        )
        
        return manifest
        
    except json.JSONDecodeError as e:
        logger.error(
            "Invalid sprite manifest JSON",
            extra={"user": current_user.username, "error": str(e)}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Sprite manifest is corrupted"
        )


@router.get(
    "/sprites/{sprite_path:path}",
    summary="Download sprite image file",
    description="Serves LPC sprite image files (PNG) for client rendering. Requires authentication.",
    response_class=FileResponse,
)
async def get_sprite_image(
    sprite_path: str,
    current_user = Depends(get_current_user),
) -> FileResponse:
    """
    Serve sprite image files from the LPC sprite directory.
    
    The path is relative to server/sprites/lpc/ and can include
    subdirectories (e.g., "body/male/light.png").
    
    Args:
        sprite_path: Path to the sprite file relative to sprites/lpc/
        current_user: Authenticated user (dependency injection)
        
    Returns:
        FileResponse containing the sprite image
        
    Raises:
        HTTPException: If file not found, path traversal attempted, or invalid file type
    """
    # Construct the full path to the sprite file
    sprite_file = SPRITES_BASE_DIR / sprite_path
    
    # Security check: resolve the path and ensure it's within the sprites directory
    try:
        resolved_sprite = sprite_file.resolve()
        resolved_base = SPRITES_BASE_DIR.resolve()
        
        logger.debug(
            "Resolving sprite path",
            extra={
                "sprite_path": sprite_path,
                "sprite_file": str(sprite_file),
                "resolved_sprite": str(resolved_sprite),
                "resolved_base": str(resolved_base),
                "exists": resolved_sprite.exists(),
            }
        )
        
        # Check for path traversal attacks
        if not str(resolved_sprite).startswith(str(resolved_base)):
            logger.warning(
                "Attempted path traversal attack on sprites",
                extra={
                    "sprite_path": sprite_path,
                    "user": current_user.username,
                    "resolved_path": str(resolved_sprite),
                }
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
    except (OSError, ValueError):
        logger.warning(
            "Invalid sprite path requested",
            extra={"sprite_path": sprite_path, "user": current_user.username}
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid sprite path"
        )
    
    # Check if file exists
    if not resolved_sprite.exists() or not resolved_sprite.is_file():
        logger.warning(
            "Sprite file not found - sprites may not be downloaded",
            extra={
                "sprite_path": sprite_path, 
                "user": current_user.username,
                "resolved_path": str(resolved_sprite),
                "hint": "Run scripts/setup_lpc_sprites.py to download sprites"
            }
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sprite file not found: {sprite_path}. Run scripts/setup_lpc_sprites.py to download sprites."
        )
    
    # Verify it's an allowed image file type
    suffix = resolved_sprite.suffix.lower()
    if suffix not in ALLOWED_SPRITE_EXTENSIONS:
        logger.warning(
            "Non-image sprite file requested",
            extra={
                "sprite_path": sprite_path,
                "suffix": suffix,
                "user": current_user.username,
            }
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PNG/JPG sprite files are allowed"
        )
    
    # Determine media type
    media_type = "image/png" if suffix == ".png" else "image/jpeg"
    
    logger.debug(
        "Sprite image served",
        extra={
            "sprite_path": sprite_path,
            "user": current_user.username,
            "file_size": resolved_sprite.stat().st_size,
        }
    )
    
    return FileResponse(
        path=str(resolved_sprite),
        media_type=media_type,
        filename=resolved_sprite.name,
    )


@router.get(
    "/sprites-status",
    response_model=Dict,
    summary="Check sprite asset status",
    description="Returns information about the sprite asset download status.",
)
async def get_sprite_status(
    current_user = Depends(get_current_user),
) -> Dict:
    """
    Check if sprites have been downloaded and their status.
    
    Returns information useful for the client to determine if
    sprite assets are available.
    
    Args:
        current_user: Authenticated user (dependency injection)
        
    Returns:
        Status dictionary with download state and basic stats
    """
    sprites_exist = SPRITES_BASE_DIR.exists()
    manifest_exists = (SPRITES_BASE_DIR / "manifest.json").exists() if sprites_exist else False
    credits_exist = (SPRITES_BASE_DIR / "CREDITS.csv").exists() if sprites_exist else False
    
    response = {
        "sprites_available": sprites_exist and manifest_exists,
        "manifest_available": manifest_exists,
        "credits_available": credits_exist,
        # base_path intentionally omitted - server filesystem paths should not be exposed to clients
    }
    
    # If manifest exists, include some basic stats
    if manifest_exists:
        try:
            with open(SPRITES_BASE_DIR / "manifest.json", "r") as f:
                manifest = json.load(f)
            response["category_count"] = len(manifest.get("categories", {}))
            response["total_sprites"] = manifest.get("total_sprites", 0)
            response["generated_at"] = manifest.get("generated_at", "unknown")
        except (json.JSONDecodeError, IOError):
            pass
    
    logger.debug(
        "Sprite status checked",
        extra={
            "user": current_user.username,
            "available": response["sprites_available"],
        }
    )
    
    return response


# =============================================================================
# Icon Endpoints - Idylwild Inventory/Ground Item Icons
# =============================================================================

# Base directory for icon assets
ICONS_BASE_DIR = Path("server/icons/idylwild")

# Allowed icon file extensions
ALLOWED_ICON_EXTENSIONS = {".png"}


@router.get(
    "/icons/manifest",
    response_model=Dict,
    summary="Get icon manifest",
    description="Returns the manifest of available inventory/ground item icon assets.",
)
async def get_icon_manifest(
    current_user = Depends(get_current_user),
) -> Dict:
    """
    Get the icon manifest listing all available icon assets.
    
    The manifest is generated by scripts/setup_idylwild_icons.py when
    downloading icon assets.
    
    Args:
        current_user: Authenticated user (dependency injection)
        
    Returns:
        Manifest dictionary with icon pack and paths
        
    Raises:
        HTTPException: If manifest not found or icons not downloaded
    """
    manifest_path = ICONS_BASE_DIR / "manifest.json"
    
    if not manifest_path.exists():
        logger.warning(
            "Icon manifest not found - icons may not be downloaded",
            extra={"user": current_user.username}
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Icon manifest not found. Run scripts/setup_idylwild_icons.py to download icons."
        )
    
    try:
        with open(manifest_path, "r") as f:
            manifest = json.load(f)
        
        logger.debug(
            "Icon manifest served",
            extra={
                "user": current_user.username,
                "icon_count": len(manifest.get("icons", [])),
            }
        )
        
        return manifest
        
    except json.JSONDecodeError as e:
        logger.error(
            "Invalid icon manifest JSON",
            extra={"user": current_user.username, "error": str(e)}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Icon manifest is corrupted"
        )


@router.get(
    "/icons/{icon_path:path}",
    summary="Download icon image file",
    description="Serves Idylwild icon image files (PNG) for inventory and ground item display. Requires authentication.",
    response_class=FileResponse,
)
async def get_icon_image(
    icon_path: str,
    current_user = Depends(get_current_user),
) -> FileResponse:
    """
    Serve icon image files from the Idylwild icon directory.
    
    The path is relative to server/icons/idylwild/ and can include
    subdirectories (e.g., "inventory/copper_ore.png").
    
    Args:
        icon_path: Path to the icon file relative to icons/idylwild/
        current_user: Authenticated user (dependency injection)
        
    Returns:
        FileResponse containing the icon image
        
    Raises:
        HTTPException: If file not found, path traversal attempted, or invalid file type
    """
    # Construct the full path to the icon file
    icon_file = ICONS_BASE_DIR / icon_path
    
    # Security check: resolve the path and ensure it's within the icons directory
    try:
        resolved_icon = icon_file.resolve()
        resolved_base = ICONS_BASE_DIR.resolve()
        
        # Check for path traversal attacks
        if not str(resolved_icon).startswith(str(resolved_base)):
            logger.warning(
                "Attempted path traversal attack on icons",
                extra={
                    "icon_path": icon_path,
                    "user": current_user.username,
                    "resolved_path": str(resolved_icon),
                }
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
    except (OSError, ValueError):
        logger.warning(
            "Invalid icon path requested",
            extra={"icon_path": icon_path, "user": current_user.username}
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid icon path"
        )
    
    # Check if file exists
    if not resolved_icon.exists() or not resolved_icon.is_file():
        logger.warning(
            "Icon file not found - icons may not be downloaded",
            extra={
                "icon_path": icon_path, 
                "user": current_user.username,
                "resolved_path": str(resolved_icon),
                "hint": "Run scripts/setup_idylwild_icons.py to download icons"
            }
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Icon file not found: {icon_path}. Run scripts/setup_idylwild_icons.py to download icons."
        )
    
    # Verify it's an allowed image file type
    suffix = resolved_icon.suffix.lower()
    if suffix not in ALLOWED_ICON_EXTENSIONS:
        logger.warning(
            "Non-PNG icon file requested",
            extra={
                "icon_path": icon_path,
                "suffix": suffix,
                "user": current_user.username,
            }
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PNG icon files are allowed"
        )
    
    logger.debug(
        "Icon image served",
        extra={
            "icon_path": icon_path,
            "user": current_user.username,
            "file_size": resolved_icon.stat().st_size,
        }
    )
    
    return FileResponse(
        path=str(resolved_icon),
        media_type="image/png",
        filename=resolved_icon.name,
    )


@router.get(
    "/icons-status",
    response_model=Dict,
    summary="Check icon asset status",
    description="Returns information about the icon asset download status.",
)
async def get_icon_status(
    current_user = Depends(get_current_user),
) -> Dict:
    """
    Check if icons have been downloaded and their status.
    
    Returns information useful for the client to determine if
    icon assets are available.
    
    Args:
        current_user: Authenticated user (dependency injection)
        
    Returns:
        Status dictionary with download state and basic stats
    """
    icons_exist = ICONS_BASE_DIR.exists()
    manifest_exists = (ICONS_BASE_DIR / "manifest.json").exists() if icons_exist else False
    attribution_exists = (ICONS_BASE_DIR.parent / "ATTRIBUTION.md").exists() if icons_exist else False
    
    response = {
        "icons_available": icons_exist and manifest_exists,
        "manifest_available": manifest_exists,
        "attribution_available": attribution_exists,
        # base_path intentionally omitted - server filesystem paths should not be exposed to clients
    }
    
    # If manifest exists, include some basic stats
    if manifest_exists:
        try:
            with open(ICONS_BASE_DIR / "manifest.json", "r") as f:
                manifest = json.load(f)
            response["pack_count"] = len(set(icon.get("pack") for icon in manifest.get("icons", [])))
            response["total_icons"] = len(manifest.get("icons", []))
            response["license"] = manifest.get("license", "unknown")
        except (json.JSONDecodeError, IOError):
            pass
    
    logger.debug(
        "Icon status checked",
        extra={
            "user": current_user.username,
            "available": response["icons_available"],
        }
    )
    
    return response