"""
API endpoints for serving game assets (tilesets, images, etc.) with authentication.
"""

import os
from pathlib import Path
from typing import List, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from server.src.core.database import get_db
from server.src.core.logging_config import get_logger
from server.src.core.security import get_current_user
from server.src.models.player import Player
from server.src.services.map_service import get_map_manager
from server.src.core.config import settings

router = APIRouter()
logger = get_logger(__name__)


@router.get(
    "/maps/{map_id}/tilesets",
    response_model=List[Dict],
    summary="Get tileset metadata for a specific map",
    description="Returns list of tilesets used by the specified map with metadata for asset loading",
)
async def get_map_tilesets(
    map_id: str,
    current_user: Player = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
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
    
    logger.info(
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
    current_user: Player = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
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
                logger.info(
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
    current_user: Player = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
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
    
    logger.info(
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