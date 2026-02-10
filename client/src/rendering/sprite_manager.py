"""
Sprite Manager - Downloads and caches LPC sprites from the server.

Handles:
- Async sprite downloading from server HTTP endpoints
- Local caching of downloaded sprites
- Sprite sheet loading into pygame surfaces
"""

import pygame
import aiohttp
import asyncio
import os
import io
import shutil
from typing import Dict, Optional, Tuple
from pathlib import Path

from ..config import get_config


# =============================================================================
# CONSTANTS
# =============================================================================

# Cache directory relative to client source
SPRITE_CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "sprite_cache")
FRAME_SIZE = 64  # LPC standard frame size


# =============================================================================
# SPRITE MANAGER
# =============================================================================

class SpriteManager:
    """
    Manages sprite downloading and caching.
    
    Downloads LPC sprites from the server on demand and caches them locally.
    Provides pygame surfaces for rendering.
    """
    
    def __init__(self):
        config = get_config()
        self.server_base_url = config.server.base_url
        self.auth_token: Optional[str] = None
        self.http_session: Optional[aiohttp.ClientSession] = None
        
        # In-memory surface cache: path -> pygame.Surface
        self._surface_cache: Dict[str, pygame.Surface] = {}
        
        # Pending downloads (avoid duplicate requests)
        self._pending_downloads: Dict[str, asyncio.Task] = {}
        
        # Failed downloads (don't retry immediately)
        self._failed_paths: set = set()
        
        # Ensure cache directory exists
        os.makedirs(SPRITE_CACHE_DIR, exist_ok=True)
    
    def set_auth_token(self, token: str) -> None:
        """Set the authentication token for API requests."""
        self.auth_token = token
    
    def set_server_url(self, server_base_url: str) -> None:
        """Update the server base URL."""
        self.server_base_url = server_base_url
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self.http_session is None or self.http_session.closed:
            self.http_session = aiohttp.ClientSession()
        return self.http_session
    
    async def close(self) -> None:
        """Close HTTP session."""
        if self.http_session and not self.http_session.closed:
            await self.http_session.close()
    
    def get_cached_path(self, sprite_path: str) -> str:
        """Get the local cache path for a sprite."""
        # Normalize path separators
        safe_path = sprite_path.replace("/", os.sep).replace("\\", os.sep)
        return os.path.join(SPRITE_CACHE_DIR, safe_path)
    
    def is_cached(self, sprite_path: str) -> bool:
        """Check if a sprite is cached locally."""
        return os.path.exists(self.get_cached_path(sprite_path))
    
    async def download_sprite(self, sprite_path: str) -> bool:
        """
        Download a sprite from the server.
        
        Args:
            sprite_path: Path relative to lpc/ directory (e.g., "body/bodies/male/light.png")
            
        Returns:
            True if download succeeded, False otherwise.
        """
        if sprite_path in self._failed_paths:
            return False
        
        if self.is_cached(sprite_path):
            return True
        
        # Check if already downloading
        if sprite_path in self._pending_downloads:
            try:
                return await self._pending_downloads[sprite_path]
            except Exception:
                return False
        
        # Start download
        task = asyncio.create_task(self._do_download(sprite_path))
        self._pending_downloads[sprite_path] = task
        
        try:
            return await task
        finally:
            self._pending_downloads.pop(sprite_path, None)
    
    async def _do_download(self, sprite_path: str) -> bool:
        """Actually perform the download."""
        if not self.auth_token:
            print(f"No auth token, cannot download {sprite_path}")
            return False
        
        try:
            session = await self._get_session()
            url = f"{self.server_base_url}/api/sprites/{sprite_path}"
            headers = {"Authorization": f"Bearer {self.auth_token}"}
            
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    print(f"Failed to download {sprite_path}: {response.status}")
                    self._failed_paths.add(sprite_path)
                    return False
                
                data = await response.read()
                
                # Save to cache
                cache_path = self.get_cached_path(sprite_path)
                os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                
                with open(cache_path, "wb") as f:
                    f.write(data)
                
                return True
                
        except Exception as e:
            print(f"Error downloading {sprite_path}: {e}")
            self._failed_paths.add(sprite_path)
            return False
    
    def get_surface(self, sprite_path: str) -> Optional[pygame.Surface]:
        """
        Get a pygame surface for a sprite.
        
        Returns cached surface or loads from disk if available.
        Returns None if sprite is not cached.
        
        Args:
            sprite_path: Path relative to lpc/ directory
            
        Returns:
            pygame.Surface or None
        """
        # Check memory cache
        if sprite_path in self._surface_cache:
            return self._surface_cache[sprite_path]
        
        # Try to load from disk cache
        cache_path = self.get_cached_path(sprite_path)
        if not os.path.exists(cache_path):
            return None
        
        try:
            surface = pygame.image.load(cache_path).convert_alpha()
            self._surface_cache[sprite_path] = surface
            return surface
        except Exception as e:
            print(f"Error loading sprite {sprite_path}: {e}")
            return None
    
    async def get_surface_async(self, sprite_path: str) -> Optional[pygame.Surface]:
        """
        Get a sprite surface, downloading if necessary.
        
        Args:
            sprite_path: Path relative to lpc/ directory
            
        Returns:
            pygame.Surface or None
        """
        # Check memory cache first
        if sprite_path in self._surface_cache:
            return self._surface_cache[sprite_path]
        
        # Download if not cached
        if not self.is_cached(sprite_path):
            success = await self.download_sprite(sprite_path)
            if not success:
                return None
        
        # Load from disk
        return self.get_surface(sprite_path)
    
    def extract_frame(
        self,
        surface: pygame.Surface,
        row: int,
        col: int,
        frame_size: int = FRAME_SIZE
    ) -> pygame.Surface:
        """
        Extract a single frame from a spritesheet.
        
        Args:
            surface: The spritesheet surface
            row: Row index (0-based)
            col: Column index (0-based)
            frame_size: Size of each frame (default 64x64)
            
        Returns:
            pygame.Surface containing the single frame
        """
        frame = pygame.Surface((frame_size, frame_size), pygame.SRCALPHA)
        frame.blit(
            surface,
            (0, 0),
            (col * frame_size, row * frame_size, frame_size, frame_size)
        )
        return frame
    
    def apply_tint(
        self,
        surface: pygame.Surface,
        tint_color: str
    ) -> pygame.Surface:
        """
        Apply a tint color to a sprite surface.
        
        Used for equipment that needs recoloring (e.g., copper vs iron weapons).
        
        Args:
            surface: The sprite surface to tint
            tint_color: Hex color string (e.g., "#B87333")
            
        Returns:
            New tinted surface
        """
        # Parse hex color
        if tint_color.startswith("#"):
            tint_color = tint_color[1:]
        
        r = int(tint_color[0:2], 16)
        g = int(tint_color[2:4], 16)
        b = int(tint_color[4:6], 16)
        
        # Create a copy
        tinted = surface.copy()
        
        # Apply multiply blend
        tint_surface = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        tint_surface.fill((r, g, b, 255))
        
        # Use BLEND_MULT for color multiplication
        tinted.blit(tint_surface, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        
        return tinted
    
    def clear_memory_cache(self) -> None:
        """Clear the in-memory surface cache."""
        self._surface_cache.clear()
    
    def clear_failed(self) -> None:
        """Clear the failed downloads list to allow retrying."""
        self._failed_paths.clear()
    
    def preload_common_sprites(self) -> asyncio.Task:
        """
        Start preloading commonly used sprites.
        
        Returns a task that can be awaited.
        """
        return asyncio.create_task(self._preload_common())
    
    async def _preload_common(self) -> None:
        """Preload common body and appearance sprites."""
        common_sprites = [
            # Male body
            "body/bodies/male/light.png",
            "body/bodies/male/olive.png",
            "body/bodies/male/brown.png",
            # Female body
            "body/bodies/female/light.png",
            "body/bodies/female/olive.png",
            "body/bodies/female/brown.png",
            # Common hair
            "hair/short/brown.png",
            "hair/short/black.png",
            "hair/long/brown.png",
            # Eyes
            "eyes/human/adult/brown.png",
            "eyes/human/adult/blue.png",
        ]
        
        tasks = [self.download_sprite(path) for path in common_sprites]
        await asyncio.gather(*tasks, return_exceptions=True)


# Singleton instance
_sprite_manager: Optional[SpriteManager] = None

def get_sprite_manager() -> SpriteManager:
    """Get or create the sprite manager singleton."""
    global _sprite_manager
    if _sprite_manager is None:
        _sprite_manager = SpriteManager()
    return _sprite_manager

def reset_sprite_manager() -> None:
    """Reset the sprite manager singleton (for testing)."""
    global _sprite_manager
    _sprite_manager = None
