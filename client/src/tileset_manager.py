"""
Client-side asset manager for handling tileset downloads, caching, and sprite management.
"""

import os
import asyncio
import aiohttp
import pygame
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json
from client.src.logging_config import get_logger
from client.src.config import get_config

logger = get_logger(__name__)


class TilesetManager:
    """
    Manages tileset assets for the client including downloading, caching, and sprite extraction.
    """
    
    def __init__(self, cache_dir: str = "client_assets"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        
        # In-memory caches
        self.tileset_metadata: Dict[str, Dict] = {}
        self.loaded_surfaces: Dict[str, pygame.Surface] = {}
        self.sprite_cache: Dict[Tuple[str, int], pygame.Surface] = {}  # (tileset_id, gid) -> sprite
        
        # HTTP session for authenticated requests
        self.session: Optional[aiohttp.ClientSession] = None
        self.auth_token: Optional[str] = None
        
        # Load cached metadata on startup
        self._load_cached_metadata()
    
    def set_auth_token(self, token: str):
        """Set the authentication token for API requests."""
        self.auth_token = token
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self.session is None:
            # Don't bake auth token into session - pass per-request instead (M6 fix)
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self.session
    
    def _get_auth_headers(self) -> dict:
        """Get headers with current auth token for each request."""
        if self.auth_token:
            return {"Authorization": f"Bearer {self.auth_token}"}
        return {}
    
    async def close(self):
        """Clean up resources."""
        if self.session:
            await self.session.close()
            self.session = None
    
    def _load_cached_metadata(self):
        """Load tileset metadata from cache."""
        metadata_file = self.cache_dir / "tileset_metadata.json"
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r') as f:
                    self.tileset_metadata = json.load(f)
            except (json.JSONDecodeError, IOError):
                # If cache is corrupted, start fresh
                self.tileset_metadata = {}
    
    def _save_metadata_cache(self):
        """Save tileset metadata to cache."""
        metadata_file = self.cache_dir / "tileset_metadata.json"
        try:
            with open(metadata_file, 'w') as f:
                json.dump(self.tileset_metadata, f, indent=2)
        except IOError:
            print(f"Warning: Could not save metadata cache to {metadata_file}")
    
    async def load_map_tilesets(self, map_id: str) -> List[Dict]:
        """
        Load all tilesets required for a specific map.
        
        Args:
            map_id: The ID of the map
            
        Returns:
            List of tileset metadata
        """
        try:
            session = await self._get_session()
            url = f"{get_config().server.base_url}/api/maps/{map_id}/tilesets"
            
            async with session.get(url, headers=self._get_auth_headers()) as response:
                if response.status == 200:
                    tilesets = await response.json()
                    
                    # Download and cache each tileset
                    for tileset in tilesets:
                        await self._ensure_tileset_cached(tileset)
                    
                    return tilesets
                elif response.status == 401:
                    logger.error("Authentication failed - please log in again")
                    return []
                else:
                    logger.error(f"Failed to load tilesets for map {map_id}: {response.status}")
                    return []
                    
        except Exception as e:
            logger.error(f"Error loading tilesets for map {map_id}: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    async def _ensure_tileset_cached(self, tileset_metadata: Dict):
        """
        Ensure a tileset is downloaded and cached locally.
        
        Args:
            tileset_metadata: Metadata dictionary for the tileset
        """
        tileset_id = tileset_metadata.get("id")
        if not tileset_id:
            return
        
        # Store metadata
        self.tileset_metadata[tileset_id] = tileset_metadata
        
        # Determine image filename
        image_source = None
        if tileset_metadata.get("type") == "embedded":
            image_source = tileset_metadata.get("image_source")
        elif tileset_metadata.get("type") == "external":
            # For external tilesets, we'd need to parse the .tsx file
            # For now, assume the source points to the image
            source = tileset_metadata.get("source", "")
            if source.endswith(".tsx"):
                # Convert .tsx to .png (simple heuristic)
                image_source = source.replace(".tsx", ".png")
        elif tileset_metadata.get("type") in ["resolved", "manual"]:
            # pytmx has already resolved external references, or we manually resolved them
            image_source = tileset_metadata.get("image_source")
        
        if not image_source:
            print(f"Warning: No image source for tileset {tileset_id}")
            return
        
        # Check if already cached
        cache_file = self.cache_dir / image_source
        if cache_file.exists():
            # Load into pygame if not already loaded
            if tileset_id not in self.loaded_surfaces:
                try:
                    self.loaded_surfaces[tileset_id] = pygame.image.load(str(cache_file))
                    print(f"Loaded cached tileset: {tileset_id}")
                except pygame.error as e:
                    print(f"Error loading cached tileset {tileset_id}: {e}")
            return
        
        # Download the tileset image
        await self._download_tileset_image(tileset_id, image_source)
    
    async def _download_tileset_image(self, tileset_id: str, image_filename: str):
        """
        Download a tileset image from the server.
        
        Args:
            tileset_id: ID of the tileset
            image_filename: Filename of the image to download
        """
        try:
            session = await self._get_session()
            url = f"{get_config().server.base_url}/api/tilesets/{image_filename}"
            
            async with session.get(url, headers=self._get_auth_headers()) as response:
                if response.status == 200:
                    # Save to cache
                    cache_file = self.cache_dir / image_filename
                    cache_file.parent.mkdir(parents=True, exist_ok=True)
                    
                    with open(cache_file, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            f.write(chunk)
                    
                    # Load into pygame
                    try:
                        self.loaded_surfaces[tileset_id] = pygame.image.load(str(cache_file))
                        print(f"Downloaded and loaded tileset: {tileset_id}")
                    except pygame.error as e:
                        print(f"Error loading downloaded tileset {tileset_id}: {e}")
                        cache_file.unlink(missing_ok=True)  # Remove corrupted file
                        
                elif response.status == 401:
                    print("Authentication failed while downloading tileset")
                elif response.status == 404:
                    print(f"Tileset image not found: {image_filename}")
                else:
                    print(f"Failed to download tileset {image_filename}: {response.status}")
                    
        except Exception as e:
            print(f"Error downloading tileset {image_filename}: {e}")
    
    def get_tile_sprite(self, gid: int, map_id: str) -> Optional[pygame.Surface]:
        """
        Get a sprite surface for a specific GID.
        
        Args:
            gid: Global tile ID
            map_id: Map ID to determine which tilesets to use
            
        Returns:
            pygame.Surface for the tile, or None if not found
        """
        if gid == 0:  # Empty tile
            return None
        
        # Check sprite cache first
        cache_key = (map_id, gid)
        if cache_key in self.sprite_cache:
            return self.sprite_cache[cache_key]
        
        # Find the tileset that contains this GID
        tileset_id, tileset_metadata = self._find_tileset_for_gid(gid, map_id)
        
        if not tileset_id or not tileset_metadata or tileset_id not in self.loaded_surfaces:
            return None
        
        # Extract sprite from tileset
        sprite = self._extract_sprite_from_tileset(gid, tileset_id, tileset_metadata)
        if sprite:
            self.sprite_cache[cache_key] = sprite
        
        return sprite
    
    def _find_tileset_for_gid(self, gid: int, map_id: str) -> Tuple[Optional[str], Optional[Dict]]:
        """
        Find which tileset contains a specific GID for a map.
        
        Args:
            gid: Global tile ID
            map_id: Map ID
            
        Returns:
            Tuple of (tileset_id, tileset_metadata) or (None, None) if not found
        """
        # Find the tileset with the highest firstgid that's still <= gid
        best_tileset = None
        best_metadata = None
        best_firstgid = 0
        
        for tileset_id, metadata in self.tileset_metadata.items():
            first_gid = metadata.get("first_gid", 0)
            tile_count = metadata.get("tile_count", 0)
            
            if first_gid <= gid < (first_gid + tile_count) and first_gid > best_firstgid:
                best_tileset = tileset_id
                best_metadata = metadata
                best_firstgid = first_gid
        
        return best_tileset, best_metadata
    
    def _extract_sprite_from_tileset(self, gid: int, tileset_id: str, tileset_metadata: Dict) -> Optional[pygame.Surface]:
        """
        Extract a single sprite from a tileset surface.
        
        Args:
            gid: Global tile ID
            tileset_id: ID of the tileset
            tileset_metadata: Metadata for the tileset
            
        Returns:
            pygame.Surface for the sprite, or None if extraction failed
        """
        if tileset_id not in self.loaded_surfaces:
            return None
        
        tileset_surface = self.loaded_surfaces[tileset_id]
        
        # Calculate local tile ID within this tileset
        first_gid = tileset_metadata.get("first_gid", 0)
        local_id = gid - first_gid
        
        # Get tileset dimensions
        tile_width = tileset_metadata.get("tile_width", 32)
        tile_height = tileset_metadata.get("tile_height", 32)
        columns = tileset_metadata.get("columns", 1)
        
        # Calculate sprite position in tileset
        col = local_id % columns
        row = local_id // columns
        
        x = col * tile_width
        y = row * tile_height
        
        # Extract sprite
        try:
            sprite = pygame.Surface((tile_width, tile_height), pygame.SRCALPHA)
            sprite.blit(tileset_surface, (0, 0), (x, y, tile_width, tile_height))
            return sprite
        except Exception as e:
            print(f"Error extracting sprite for GID {gid} from tileset {tileset_id}: {e}")
            return None
    
    def clear_cache(self):
        """Clear all cached data."""
        self.sprite_cache.clear()
        self.loaded_surfaces.clear()
        self.tileset_metadata.clear()
        
        # Optionally remove cached files
        # for file in self.cache_dir.glob("*"):
        #     file.unlink()
    
    def get_cache_info(self) -> Dict:
        """Get information about the current cache state."""
        return {
            "loaded_tilesets": len(self.loaded_surfaces),
            "cached_sprites": len(self.sprite_cache),
            "metadata_entries": len(self.tileset_metadata),
            "cache_dir": str(self.cache_dir),
            "cache_dir_exists": self.cache_dir.exists()
        }


# Singleton instance
_tileset_manager_instance = None

def get_tileset_manager() -> TilesetManager:
    """Get or create the singleton TilesetManager instance."""
    global _tileset_manager_instance
    if _tileset_manager_instance is None:
        _tileset_manager_instance = TilesetManager()
    return _tileset_manager_instance