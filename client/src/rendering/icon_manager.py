"""
Icon Manager - Client-side icon asset management for inventory and ground items.

This module provides:
- Download caching of icon assets from the server
- In-memory surface cache for fast rendering
- Client-side tinting support for icon variants

All icons are 32x32 pixels from Idylwild's CC0 packs.
Icons are downloaded on-demand and cached both on disk and in memory.

Example usage:
    icon_manager = get_icon_manager()
    icon_surface = await icon_manager.get_icon("inventory/copper_ore.png")
    tinted_surface = icon_manager.apply_tint(icon_surface, "#B87333")
"""

import os
import asyncio
import pygame
from pathlib import Path
from typing import Dict, Optional, Tuple, Set
import aiohttp

from common.src.sprites.icon_mapping import resolve_icon, IconSprite, get_icon_info


# Cache directory for downloaded icons
ICON_CACHE_DIR = Path("client/icon_cache")


def parse_hex_color(hex_color: str) -> Tuple[int, int, int]:
    """
    Parse a hex color string to RGB tuple.
    
    Args:
        hex_color: Hex color string (e.g., "#B87333")
        
    Returns:
        RGB tuple (r, g, b)
    """
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


class IconManager:
    """
    Manages icon assets for inventory and ground item display.
    
    Handles downloading, caching, and tinting of 32x32 icon images.
    
    Attributes:
        base_url: Server base URL for icon downloads
        auth_token: JWT token for authenticated requests
        cache_dir: Local directory for icon caching
        _surface_cache: In-memory cache of loaded icon surfaces
        _download_locks: Prevents concurrent duplicate downloads
        _failed_icons: Tracks permanently failed icon IDs
    """
    
    def __init__(self, server_base_url: str, auth_token: str):
        """
        Initialize the icon manager.
        
        Args:
            server_base_url: Base URL of the game server (e.g., "http://localhost:8000")
            auth_token: JWT authentication token
        """
        self.base_url = server_base_url.rstrip("/")
        self.auth_token = auth_token
        self.cache_dir = ICON_CACHE_DIR
        
        # In-memory surface cache: path -> pygame.Surface
        self._surface_cache: Dict[str, pygame.Surface] = {}
        
        # Track downloads in progress to avoid duplicates
        self._download_locks: Set[str] = set()
        
        # Track permanently failed icons (e.g., 404)
        self._failed_icons: Set[str] = set()
        
        # Ensure cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_cache_path(self, icon_path: str) -> Path:
        """Get the local cache path for an icon."""
        # Sanitize path: replace / with _ to create flat cache structure
        safe_name = icon_path.replace("/", "_").replace("\\", "_")
        return self.cache_dir / safe_name
    
    def _get_full_url(self, icon_path: str) -> str:
        """Get the full URL for downloading an icon."""
        return f"{self.base_url}/api/icons/{icon_path}"
    
    async def download_icon(self, icon_path: str) -> bool:
        """
        Download an icon from the server.
        
        Args:
            icon_path: Path to the icon (e.g., "inventory/copper_ore.png")
            
        Returns:
            True if download successful, False otherwise
        """
        # Skip if already failed
        if icon_path in self._failed_icons:
            return False
        
        # Skip if already in memory cache
        if icon_path in self._surface_cache:
            return True
        
        # Check disk cache
        cache_path = self._get_cache_path(icon_path)
        if cache_path.exists():
            return True
        
        # Check if download already in progress
        if icon_path in self._download_locks:
            # Wait for existing download to complete
            while icon_path in self._download_locks:
                await asyncio.sleep(0.01)
            return icon_path not in self._failed_icons
        
        # Start download
        self._download_locks.add(icon_path)
        
        try:
            success = await self._do_download(icon_path)
            return success
        finally:
            self._download_locks.discard(icon_path)
    
    async def _do_download(self, icon_path: str) -> bool:
        """
        Perform the actual icon download.
        
        Args:
            icon_path: Path to the icon
            
        Returns:
            True if download successful
        """
        url = self._get_full_url(icon_path)
        cache_path = self._get_cache_path(icon_path)
        
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        # Save to cache
                        data = await response.read()
                        with open(cache_path, "wb") as f:
                            f.write(data)
                        return True
                    elif response.status == 404:
                        # Permanently failed - don't retry
                        self._failed_icons.add(icon_path)
                        return False
                    else:
                        return False
        except Exception:
            return False
    
    def get_surface(self, icon_path: str) -> Optional[pygame.Surface]:
        """
        Get an icon surface from cache or disk.
        
        Args:
            icon_path: Path to the icon
            
        Returns:
            pygame.Surface or None if not available
        """
        # Check memory cache
        if icon_path in self._surface_cache:
            return self._surface_cache[icon_path]
        
        # Check disk cache
        cache_path = self._get_cache_path(icon_path)
        if cache_path.exists():
            try:
                surface = pygame.image.load(str(cache_path)).convert_alpha()
                self._surface_cache[icon_path] = surface
                return surface
            except pygame.error:
                return None
        
        return None
    
    def get_icon_surface_sync(self, icon_sprite_id: str) -> Optional[pygame.Surface]:
        """
        Synchronously get an icon surface from cache (if available).
        
        This is safe to call from the render loop - it never blocks or downloads.
        If the icon is not yet cached, returns None and the caller should
        schedule a background download via schedule_download().
        
        Args:
            icon_sprite_id: The icon sprite ID (e.g., "icon_copper_dagger")
            
        Returns:
            pygame.Surface (possibly tinted) from cache, or None if not available
        """
        # Resolve the icon
        resolved = resolve_icon(icon_sprite_id)
        if resolved is None:
            return None
        
        icon_path, tint = resolved
        
        # Get base surface from cache (memory or disk)
        surface = self.get_surface(icon_path)
        if surface is None:
            return None
        
        # Apply tint if specified
        if tint:
            # Check tinted cache first
            tinted_key = f"{icon_path}#{tint}"
            if tinted_key in self._surface_cache:
                return self._surface_cache[tinted_key]
            
            # Apply tint and cache
            surface = self.apply_tint(surface, tint)
            self._surface_cache[tinted_key] = surface
        
        return surface
    
    def schedule_download(self, icon_sprite_id: str) -> None:
        """
        Schedule an icon for background download.
        
        Call this from sync render code when an icon is needed but not cached.
        The download happens asynchronously in the background.
        
        Args:
            icon_sprite_id: The icon sprite ID to download
        """
        resolved = resolve_icon(icon_sprite_id)
        if resolved is None:
            return
        
        icon_path, _ = resolved
        
        # Skip if already cached or downloading
        if icon_path in self._surface_cache:
            return
        if self._get_cache_path(icon_path).exists():
            return
        if icon_path in self._download_locks or icon_path in self._failed_icons:
            return
        
        # Schedule background download
        asyncio.create_task(self.download_icon(icon_path))
    
    async def get_icon_by_sprite_id(self, icon_sprite_id: str) -> Optional[pygame.Surface]:
        """
        Get an icon surface by its sprite ID (e.g., "icon_copper_dagger").
        
        This is the main async method to use - it resolves the sprite ID to a path,
        downloads if needed, and applies tinting.
        
        Args:
            icon_sprite_id: The icon sprite ID
            
        Returns:
            pygame.Surface with tint applied, or None if not found
        """
        # Resolve the icon
        resolved = resolve_icon(icon_sprite_id)
        if resolved is None:
            return None
        
        icon_path, tint = resolved
        
        # Ensure downloaded
        if not await self.download_icon(icon_path):
            return None
        
        # Get surface
        surface = self.get_surface(icon_path)
        if surface is None:
            return None
        
        # Apply tint if specified
        if tint:
            surface = self.apply_tint(surface, tint)
        
        return surface
    
    def apply_tint(self, surface: pygame.Surface, hex_color: str) -> pygame.Surface:
        """
        Apply a color tint to an icon surface.
        
        Uses multiplicative blending (BLEND_RGBA_MULT) to apply the tint
        while preserving the alpha channel.
        
        Args:
            surface: Source surface
            hex_color: Hex color string (e.g., "#B87333")
            
        Returns:
            New surface with tint applied
        """
        # Parse color
        r, g, b = parse_hex_color(hex_color)
        
        # Create a copy of the surface
        tinted = surface.copy()
        
        # Create tint overlay with the RGB color
        tint_overlay = pygame.Surface(tinted.get_size(), pygame.SRCALPHA)
        tint_overlay.fill((r, g, b, 255))
        
        # Apply multiplicative blend
        tinted.blit(tint_overlay, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        
        return tinted
    
    def clear_cache(self) -> None:
        """Clear the in-memory surface cache."""
        self._surface_cache.clear()
    
    def preload_common_icons(self) -> None:
        """
        Preload commonly used icons into memory.
        
        This is called once during initialization to ensure frequently
        used icons are ready for display.
        """
        # Preload from disk cache if available
        for cache_file in self.cache_dir.glob("*.png"):
            try:
                # Convert filename back to path format
                icon_path = cache_file.stem.replace("_", "/") + ".png"
                if icon_path not in self._surface_cache:
                    surface = pygame.image.load(str(cache_file)).convert_alpha()
                    self._surface_cache[icon_path] = surface
            except pygame.error:
                pass


# Global icon manager instance
_icon_manager: Optional[IconManager] = None


def get_icon_manager() -> Optional[IconManager]:
    """
    Get the global icon manager instance.
    
    Returns:
        IconManager instance or None if not initialized
    """
    return _icon_manager


def set_icon_manager(manager: IconManager) -> None:
    """
    Set the global icon manager instance.
    
    Args:
        manager: IconManager instance to use globally
    """
    global _icon_manager
    _icon_manager = manager
