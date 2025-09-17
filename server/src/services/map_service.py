"""
Map management system for the RPG server.

Handles loading Tiled TMX maps, tile collision detection, and spatial queries.
Provides an interface for the game logic to validate player movements and
interact with the game world.
"""

import os
import asyncio
from typing import Dict, Optional, Tuple, Set, Union, List
from pathlib import Path

try:
    import pytmx

    PYTMX_AVAILABLE = True
except ImportError:
    PYTMX_AVAILABLE = False

from server.src.core.logging_config import get_logger
from server.src.core.metrics import errors_total
from server.src.core.config import settings

logger = get_logger(__name__)


class TileMap:
    """Represents a loaded Tiled map with collision detection capabilities."""

    def __init__(self, map_path: str):
        """
        Load a TMX map file.

        Args:
            map_path: Path to the TMX file
        """
        self.map_path = map_path
        self.tmx_data = None
        self.width = 0
        self.height = 0
        self.tile_width = 32
        self.tile_height = 32
        self.walkable_tiles: Set[int] = set()
        self.collision_layer = None

        self._load_map()

    def _load_map(self):
        """Load and parse the TMX map file."""
        if not PYTMX_AVAILABLE:
            logger.error("pytmx not available, cannot load maps")
            raise ImportError("pytmx library is required for map loading")

        try:
            # Load TMX file with pygame support
            self.tmx_data = pytmx.TiledMap(self.map_path)
            self.width = self.tmx_data.width
            self.height = self.tmx_data.height
            self.tile_width = self.tmx_data.tilewidth
            self.tile_height = self.tmx_data.tileheight

            # Build walkable tiles set from tileset properties
            # For now, consider all tiles walkable except specific collision tiles
            # This can be enhanced later with proper tile properties
            for tileset in self.tmx_data.tilesets:
                for tile_id in range(tileset.tilecount):
                    global_id = tileset.firstgid + tile_id
                    # Use get_tile_properties_by_gid for tile properties
                    tile_props = self.tmx_data.get_tile_properties_by_gid(global_id)
                    if tile_props and tile_props.get(
                        "walkable", True
                    ):  # Default to walkable
                        self.walkable_tiles.add(global_id)
                    elif not tile_props:  # No properties = walkable by default
                        self.walkable_tiles.add(global_id)

            # Find collision/obstacle layers
            if hasattr(self.tmx_data, "layers"):
                for layer in self.tmx_data.layers:
                    if hasattr(layer, "data") and layer.name.lower() in [
                        "obstacles",
                        "collision",
                    ]:
                        self.collision_layer = layer
                        break

            logger.info(
                "Map loaded successfully",
                extra={
                    "map_path": self.map_path,
                    "dimensions": f"{self.width}x{self.height}",
                    "tile_size": f"{self.tile_width}x{self.tile_height}",
                    "walkable_tiles": len(self.walkable_tiles),
                },
            )

        except Exception as e:
            logger.error(
                "Failed to load map", extra={"map_path": self.map_path, "error": str(e)}
            )
            raise

    def is_walkable(self, x: int, y: int) -> bool:
        """
        Check if a tile position is walkable.

        Args:
            x: Tile X coordinate
            y: Tile Y coordinate

        Returns:
            True if the tile is walkable, False otherwise
        """
        # Check bounds
        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            return False

        # Check layers for walkability
        if self.tmx_data and hasattr(self.tmx_data, "layers"):
            # First check for dedicated obstacles/collision layers (these override everything)
            for layer in self.tmx_data.layers:
                if hasattr(layer, "data") and layer.name.lower() in [
                    "obstacles",
                    "collision",
                ]:
                    tile_gid = layer.data[y][x]
                    if tile_gid > 0:  # Any tile in obstacles layer blocks movement
                        return False

            # Then check ALL tile layers for tile properties
            for layer in self.tmx_data.layers:
                if hasattr(layer, "data") and hasattr(layer.data, "__getitem__"):
                    try:
                        # Get the tile GID at this position
                        if isinstance(layer.data, list) and len(layer.data) > y:
                            if (
                                isinstance(layer.data[y], list)
                                and len(layer.data[y]) > x
                            ):
                                tile_gid = layer.data[y][x]
                            else:
                                continue
                        else:
                            continue

                        # If there's a tile here, check its properties
                        if tile_gid > 0:
                            tile_props = self.tmx_data.get_tile_properties_by_gid(
                                tile_gid
                            )
                            if tile_props and "walkable" in tile_props:
                                return tile_props.get("walkable", True)
                    except (IndexError, TypeError):
                        continue

        return True  # Default to walkable if no blocking tiles found

    def get_spawn_position(self) -> Tuple[int, int]:
        """
        Get a valid spawn position on the map.

        Returns:
            Tuple of (x, y) coordinates for spawning
        """
        # Try to find a walkable tile, starting from center
        center_x, center_y = self.width // 2, self.height // 2

        # Spiral search from center
        for radius in range(min(self.width, self.height) // 2):
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    if abs(dx) == radius or abs(dy) == radius:
                        x, y = center_x + dx, center_y + dy
                        if self.is_walkable(x, y):
                            return (x, y)

        # Fallback to (1, 1) if no walkable tile found
        return (1, 1)

    def get_tile_info(self, x: int, y: int) -> Dict:
        """Get detailed information about a tile."""
        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            return {"valid": False, "walkable": False}

        info = {"valid": True, "walkable": self.is_walkable(x, y), "layers": {}}

        if self.tmx_data and hasattr(self.tmx_data, "layers"):
            for layer in self.tmx_data.layers:
                if hasattr(layer, "data"):
                    tile_gid = layer.data[y][x]
                    info["layers"][layer.name] = tile_gid

        return info

    def get_chunk_data(
        self, chunk_x: int, chunk_y: int, chunk_size: int = 16
    ) -> Optional[Dict]:
        """
        Extract a chunk of map data as a 2D array of tile information.

        Args:
            chunk_x: Chunk coordinate X (in chunk units)
            chunk_y: Chunk coordinate Y (in chunk units)
            chunk_size: Size of chunk in tiles (default 16x16)

        Returns:
            Dict containing chunk data or None if chunk is out of bounds
        """
        # Calculate tile boundaries for this chunk
        start_tile_x = chunk_x * chunk_size
        start_tile_y = chunk_y * chunk_size
        end_tile_x = start_tile_x + chunk_size
        end_tile_y = start_tile_y + chunk_size

        # Check if chunk is completely out of bounds
        if (
            start_tile_x >= self.width
            or start_tile_y >= self.height
            or end_tile_x <= 0
            or end_tile_y <= 0
        ):
            return None

        # Extract tile data for this chunk
        tiles = []
        for y in range(chunk_size):
            row = []
            for x in range(chunk_size):
                tile_x = start_tile_x + x
                tile_y = start_tile_y + y

                # Handle out-of-bounds tiles
                if (
                    tile_x >= self.width
                    or tile_y >= self.height
                    or tile_x < 0
                    or tile_y < 0
                ):
                    row.append(
                        {
                            "gid": 0,  # Empty tile
                            "properties": {"walkable": False, "out_of_bounds": True},
                        }
                    )
                    continue

                # Get primary layer tile (usually ground/base layer)
                primary_gid = 0
                tile_properties = {}

                if self.tmx_data and hasattr(self.tmx_data, "layers"):
                    # Get tile from first visible layer (ground layer)
                    for layer in self.tmx_data.layers:
                        if hasattr(layer, "data") and layer.visible:
                            primary_gid = layer.data[tile_y][tile_x]
                            break

                    # Get tile properties
                    if primary_gid > 0:
                        tile_properties = (
                            self.tmx_data.get_tile_properties_by_gid(primary_gid) or {}
                        )

                # Add computed properties
                tile_properties["walkable"] = self.is_walkable(tile_x, tile_y)

                row.append({"gid": primary_gid, "properties": tile_properties})

            tiles.append(row)

        return {
            "chunk_x": chunk_x,
            "chunk_y": chunk_y,
            "tiles": tiles,
            "width": chunk_size,
            "height": chunk_size,
        }

    def get_chunks_around_position(
        self, center_x: int, center_y: int, radius: int = 1, chunk_size: int = 16
    ) -> List[Dict]:
        """
        Get chunks around a player position.

        Args:
            center_x: Player's tile X position
            center_y: Player's tile Y position
            radius: Number of chunks in each direction (1 = 3x3 grid)
            chunk_size: Size of each chunk in tiles

        Returns:
            List of chunk data dictionaries
        """
        # Convert player position to chunk coordinates
        center_chunk_x = center_x // chunk_size
        center_chunk_y = center_y // chunk_size

        chunks = []
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                chunk_x = center_chunk_x + dx
                chunk_y = center_chunk_y + dy

                chunk_data = self.get_chunk_data(chunk_x, chunk_y, chunk_size)
                if chunk_data:  # Only include valid chunks
                    chunks.append(chunk_data)

        return chunks


class MapManager:
    """
    Manages all game maps, providing a single point of access for map data.
    
    This class is responsible for:
    - Discovering and loading all available maps from the filesystem.
    - Providing access to map objects.
    - Handling map-related operations like spawn points and movement validation.
    """

    _instance = None

    def __init__(self):
        """
        Initializes the MapManager.
        
        Note: Map loading is handled by the async `load_maps` method,
        which should be called during server startup.
        """
        self.maps: Dict[str, TileMap] = {}
        self.maps_path = Path(__file__).parent.parent.parent / "maps"

    async def load_maps(self):
        """
        Discover and load all .tmx maps from the maps directory asynchronously.
        """
        logger.info(f"Searching for maps in: {self.maps_path}")
        map_files = list(self.maps_path.glob("*.tmx"))

        if not map_files:
            logger.warning("No maps found in the maps directory.")
            return

        tasks = []
        for map_path in map_files:
            map_id = map_path.stem
            task = asyncio.to_thread(self._load_map_sync, map_path, map_id)
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result, map_path in zip(results, map_files):
            if isinstance(result, Exception):
                logger.error(
                    f"Failed to load map {map_path.name}", extra={"error": result}
                )
            else:
                logger.info(f"Successfully loaded map: {map_path.name}")

    def _load_map_sync(self, map_path: Path, map_id: str):
        """Synchronous helper to load a single map. To be run in a thread."""
        self.maps[map_id] = TileMap(str(map_path))

    def get_map(self, map_id: str) -> Optional[TileMap]:
        """
        Get a loaded map by its ID.

        Args:
            map_id: The map identifier (filename without .tmx extension)

        Returns:
            TileMap instance if found, None otherwise
        """
        return self.maps.get(map_id)

    def get_default_spawn_position(self) -> Tuple[str, int, int]:
        """
        Get the default spawn position for new players.
        
        Returns:
            A tuple of (map_id, x, y).
        """
        # Try to find a default map, otherwise use the first loaded map
        default_map_id = settings.DEFAULT_MAP
        if default_map_id not in self.maps:
            if not self.maps:
                logger.error("No maps are loaded. Cannot determine a spawn point.")
                # Return a fallback value if no maps are available at all
                return "fallback_map", 0, 0
            default_map_id = list(self.maps.keys())[0]
            logger.warning(
                f"Default map '{settings.DEFAULT_MAP}' not found. "
                f"Falling back to first loaded map: '{default_map_id}'."
            )

        tile_map = self.get_map(default_map_id)
        if not tile_map:
            logger.error("Default map not found, cannot determine spawn position")
            # Fallback to hardcoded values if default map is not found
            return "test_map", settings.DEFAULT_SPAWN_X, settings.DEFAULT_SPAWN_Y

        spawn_point = tile_map.get_spawn_position()
        return default_map_id, spawn_point.x, spawn_point.y

    def get_player_spawn_position(
        self, map_id: str, player_id: str
    ) -> Tuple[str, int, int]:
        """
        Get the spawn position for a player.

        Args:
            map_id: The map identifier
            player_id: The player identifier

        Returns:
            Tuple of (map_id, x, y) for the player's spawn location
        """
        tile_map = self.get_map(map_id)
        if not tile_map:
            logger.warning(
                "Map not found for player spawn, falling back to default",
                extra={"map_id": map_id, "player_id": player_id},
            )
            return self.get_default_spawn_position()

        # For now, just use the default spawn of the target map
        # This can be extended to support multiple named spawn points
        spawn_point = tile_map.get_spawn_point()
        if not spawn_point:
            logger.warning(
                "No spawn point found on map, falling back to default",
                extra={"map_id": map_id},
            )
            return self.get_default_spawn_position()

        return map_id, spawn_point.x, spawn_point.y

    def validate_player_position(
        self, map_id: str, x: int, y: int
    ) -> Tuple[str, int, int]:
        """
        Validate a player's position and return corrected values if needed.
        
        Args:
            map_id: The player's current map ID
            x, y: The player's current coordinates
            
        Returns:
            Tuple of (validated_map_id, validated_x, validated_y)
        """
        # Check if the map exists
        tile_map = self.get_map(map_id)
        if not tile_map:
            logger.warning(
                "Invalid map for player, falling back to default spawn",
                extra={"map_id": map_id, "x": x, "y": y},
            )
            return self.get_default_spawn_position()
        
        # Check if the position is walkable
        if tile_map.is_walkable(x, y):
            # Position is valid
            return map_id, x, y
        else:
            # Position is invalid, use map's spawn point
            logger.warning(
                "Invalid position for player, using map spawn point",
                extra={"map_id": map_id, "x": x, "y": y},
            )
            spawn_x, spawn_y = tile_map.get_spawn_position()
            return map_id, spawn_x, spawn_y

    def is_valid_move(
        self, map_id: str, from_x: int, from_y: int, to_x: int, to_y: int
    ) -> bool:
        """
        Check if a movement from one position to another is valid.

        Args:
            map_id: ID of the map
            from_x, from_y: Starting position
            to_x, to_y: Target position

        Returns:
            True if the move is valid, False otherwise
        """
        tile_map = self.get_map(map_id)
        if not tile_map:
            logger.warning(
                "Map not found for movement validation", extra={"map_id": map_id}
            )
            return False

        # Check if target position is walkable
        walkable = tile_map.is_walkable(to_x, to_y)

        if not walkable:
            logger.debug(
                "Movement blocked by collision",
                extra={
                    "map_id": map_id,
                    "from": f"({from_x}, {from_y})",
                    "to": f"({to_x}, {to_y})",
                    "tile_info": tile_map.get_tile_info(to_x, to_y),
                },
            )
            errors_total.labels(component="map", error_type="collision").inc()

        return walkable

    def get_chunks_for_player(
        self, map_id: str, player_x: int, player_y: int, radius: int = 1
    ) -> Optional[List[Dict]]:
        """
        Get chunk data around a player's position.

        Args:
            map_id: The map identifier
            player_x: Player's tile X position
            player_y: Player's tile Y position
            radius: Number of chunks in each direction from player

        Returns:
            List of chunk data or None if map doesn't exist
        """
        tile_map = self.get_map(map_id)
        if not tile_map:
            logger.warning(
                "Map not found for chunk request",
                extra={
                    "map_id": map_id,
                    "player_position": f"({player_x}, {player_y})",
                },
            )
            return None

        chunks = tile_map.get_chunks_around_position(player_x, player_y, radius)

        logger.debug(
            "Generated chunks for player",
            extra={
                "map_id": map_id,
                "player_position": f"({player_x}, {player_y})",
                "radius": radius,
                "chunk_count": len(chunks),
            },
        )

        return chunks

    def get_chunk_data(self, map_id: str, chunk_x: int, chunk_y: int) -> Optional[Dict]:
        """
        Get data for a specific chunk.

        Args:
            map_id: The map identifier
            chunk_x: Chunk coordinate X
            chunk_y: Chunk coordinate Y

        Returns:
            Chunk data dictionary or None if not available
        """
        tile_map = self.get_map(map_id)
        if not tile_map:
            return None

        return tile_map.get_chunk_data(chunk_x, chunk_y)

    def get_spawn_position(self, map_id: str) -> Tuple[int, int]:
        """Get a spawn position for the specified map."""
        tile_map = self.get_map(map_id)
        if tile_map:
            return tile_map.get_spawn_position()
        return (0, 0)  # Fallback

    def get_map_info(self, map_id: str) -> Dict:
        """Get information about a map."""
        tile_map = self.get_map(map_id)
        if not tile_map:
            return {"exists": False}

        return {
            "exists": True,
            "id": map_id,
            "width": tile_map.width,
            "height": tile_map.height,
            "tile_size": {"width": tile_map.tile_width, "height": tile_map.tile_height},
            "walkable_tiles": len(tile_map.walkable_tiles),
        }


# Global map manager instance - lazy initialization
_map_manager_instance = None


def get_map_manager() -> "MapManager":
    """
    Singleton factory for the MapManager.
    """
    global _map_manager_instance
    if _map_manager_instance is None:
        _map_manager_instance = MapManager()
    return _map_manager_instance


# For backward compatibility, expose as map_manager
class MapManagerProxy:
    """Proxy to provide backward compatibility while enabling lazy initialization."""

    def __getattr__(self, name):
        return getattr(get_map_manager(), name)


map_manager = MapManagerProxy()
