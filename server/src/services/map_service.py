"""
Map management system for the RPG server.

Handles loading Tiled TMX maps, tile collision detection, and spatial queries.
Provides an interface for the game logic to validate player movements and
interact with the game world.
"""

import os
import asyncio
from typing import Dict, Optional, Tuple, Set, Union, List, Any
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
        self.collision_layers: List[pytmx.TiledTileLayer] = []

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
                        if hasattr(layer, "data") and layer.name.lower() in settings.COLLISION_LAYER_NAMES:
                            self.collision_layers.append(layer)

            logger.info(
                "Map loaded successfully",
                extra={
                    "map_path": self.map_path,
                    "dimensions": f"{self.width}x{self.height}",
                    "tile_size": f"{self.tile_width}x{self.tile_height}",
                    "walkable_tiles": len(self.walkable_tiles),
                    "collision_layers": [layer.name for layer in self.collision_layers],
                    "tilesets": len(self.tmx_data.tilesets) if self.tmx_data else 0,
                },
            )

        except Exception as e:
            logger.error(
                "Failed to load map", extra={"map_path": self.map_path, "error": str(e)}
            )
            raise

    def get_tileset_metadata(self) -> List[Dict]:
        """
        Extract tileset metadata for client asset management.
        
        Returns:
            List of tileset metadata dicts with image paths, dimensions, and GID ranges
        """
        if not self.tmx_data:
            return []
            
        tilesets = []
        for tileset in self.tmx_data.tilesets:
            # pytmx automatically resolves external .tsx files, so we can treat all tilesets uniformly
            logger.info(f"Processing tileset: name={getattr(tileset, 'name', 'unnamed')}, "
                       f"source={getattr(tileset, 'source', 'none')}, "
                       f"firstgid={getattr(tileset, 'firstgid', 'none')}")
            
            image_source = None
            
            # Get image source from tileset (pytmx has already resolved .tsx references)
            if hasattr(tileset, 'image') and tileset.image:
                image_source = tileset.image.source
            elif hasattr(tileset, 'source') and tileset.source:
                # If source exists, it's likely the image source (pytmx resolved .tsx)
                image_source = tileset.source
            
            # Calculate proper GID range
            tilecount = getattr(tileset, 'tilecount', 0)
            last_gid = tileset.firstgid + tilecount - 1 if tilecount > 0 else tileset.firstgid
            
            tileset_info = {
                "id": tileset.name or f"tileset_{tileset.firstgid}",
                "type": "manual",  # Using manual resolution to fix pytmx bugs
                "image_source": image_source,
                "first_gid": tileset.firstgid,
                "last_gid": last_gid,
                "tile_width": getattr(tileset, 'tilewidth', 32),
                "tile_height": getattr(tileset, 'tileheight', 32),
                "tile_count": tilecount,
                "columns": getattr(tileset, 'columns', 1),
                "spacing": getattr(tileset, 'spacing', 0),
                "margin": getattr(tileset, 'margin', 0),
            }
            
            logger.info(f"Tileset metadata: {tileset_info}")
            tilesets.append(tileset_info)
        
        return tilesets

    def get_correct_tile_data(self, gid: int) -> Optional[Dict[str, Any]]:
        """
        Get correct tile data by manually resolving tileset instead of using buggy pytmx methods.
        
        Args:
            gid: Global tile ID
            
        Returns:
            Dict with correct tileset info and local coordinates, or None if not found
        """
        if not self.tmx_data or gid <= 0:
            return None
            
        # Manual tileset lookup to work around pytmx bugs
        correct_tileset = None
        for tileset in self.tmx_data.tilesets:
            if hasattr(tileset, 'tilecount') and hasattr(tileset, 'firstgid'):
                last_gid = tileset.firstgid + tileset.tilecount - 1
                if tileset.firstgid <= gid <= last_gid:
                    correct_tileset = tileset
                    break
        
        if not correct_tileset:
            return None
            
        # Calculate correct local tile ID
        local_id = gid - correct_tileset.firstgid
        
        # Get tileset image source
        image_source = None
        if hasattr(correct_tileset, 'image') and correct_tileset.image:
            image_source = correct_tileset.image.source
        elif hasattr(correct_tileset, 'source'):
            image_source = correct_tileset.source
            
        if not image_source:
            return None
            
        # Calculate tile position in the tileset image
        columns = getattr(correct_tileset, 'columns', 1)
        tile_width = getattr(correct_tileset, 'tilewidth', 32)
        tile_height = getattr(correct_tileset, 'tileheight', 32)
        spacing = getattr(correct_tileset, 'spacing', 0)
        margin = getattr(correct_tileset, 'margin', 0)
        
        # Calculate x, y position in tileset
        col = local_id % columns
        row = local_id // columns
        
        x = margin + col * (tile_width + spacing)
        y = margin + row * (tile_height + spacing)
        
        return {
            "tileset_name": getattr(correct_tileset, 'name', f'tileset_{correct_tileset.firstgid}'),
            "image_source": os.path.basename(image_source),
            "local_id": local_id,
            "x": x,
            "y": y,
            "width": tile_width,
            "height": tile_height,
            "gid": gid
        }
        
    def _convert_local_to_global_gid(self, local_gid: int, tile_x: int, tile_y: int, layer_index: int = 0) -> int:
        """
        Convert pytmx local GID back to global GID by parsing raw TMX data.
        
        pytmx converts global GIDs to local tile IDs automatically, but we need 
        global GIDs for proper tileset mapping. The only reliable way is to 
        parse the raw TMX CSV data directly.
        
        Args:
            local_gid: Local tile ID from pytmx layer.data
            tile_x: Tile X coordinate
            tile_y: Tile Y coordinate
            layer_index: Which layer to get the GID from
            
        Returns:
            Global GID from original TMX file
        """
        if local_gid <= 0:
            return 0
            
        # Use cached raw TMX data if available
        if not hasattr(self, '_raw_tmx_layers'):
            self._load_raw_tmx_data()
        
        # Get the real GID from raw TMX data for the specific layer
        if (hasattr(self, '_raw_tmx_layers') and self._raw_tmx_layers and 
            layer_index < len(self._raw_tmx_layers)):
            layer_data = self._raw_tmx_layers[layer_index]
            if tile_y < len(layer_data) and tile_x < len(layer_data[tile_y]):
                raw_gid = layer_data[tile_y][tile_x]
                if raw_gid > 0:
                    return raw_gid
        
        # Fallback to original local GID if raw parsing fails
        return local_gid
        
    def _load_raw_tmx_data(self):
        """Load raw TMX layer data directly from the XML file."""
        import xml.etree.ElementTree as ET
        
        try:
            tree = ET.parse(self.map_path)
            root = tree.getroot()
            
            self._raw_tmx_layers = []
            
            # Parse each layer's CSV data
            for layer_elem in root.findall('layer'):
                data_elem = layer_elem.find('data')
                if data_elem is not None and data_elem.get('encoding') == 'csv':
                    csv_data = data_elem.text
                    if csv_data:
                        csv_data = csv_data.strip()
                        layer_rows = []
                        
                        for line in csv_data.split('\n'):
                            if line.strip():
                                # Parse CSV row, handling trailing commas
                                row_gids = []
                                for gid_str in line.split(','):
                                    gid_str = gid_str.strip()
                                    if gid_str:
                                        row_gids.append(int(gid_str))
                                if row_gids:
                                    layer_rows.append(row_gids)
                        
                        self._raw_tmx_layers.append(layer_rows)
                    
        except Exception as e:
            logger.warning(f"Error loading raw TMX data: {e}")
            self._raw_tmx_layers = []
    
    def _parse_external_tileset(self, tileset) -> Optional[Dict]:
        """
        Parse an external .tsx tileset file to extract metadata.
        
        Args:
            tileset: The tileset object with source reference
            
        Returns:
            Tileset metadata dictionary or None if parsing fails
        """
        import xml.etree.ElementTree as ET
        from pathlib import Path
        
        try:
            # Build path to .tsx file
            tsx_path = Path(self.map_path).parent / tileset.source
            logger.info(f"Looking for external tileset at: {tsx_path}")
            
            if not tsx_path.exists():
                logger.warning(f"External tileset file not found: {tsx_path}")
                return None
            
            # Parse the .tsx file
            tree = ET.parse(tsx_path)
            root = tree.getroot()
            
            # Extract tileset information
            name = root.get('name', tileset.name or f"tileset_{tileset.firstgid}")
            tile_width = int(root.get('tilewidth', 32))
            tile_height = int(root.get('tileheight', 32))
            tile_count = int(root.get('tilecount', 0))
            columns = int(root.get('columns', 1))
            
            # Extract image source
            image_element = root.find('image')
            image_source = None
            if image_element is not None:
                image_source = image_element.get('source')
            
            tileset_info = {
                "id": name,
                "type": "external",
                "source": tileset.source,
                "image_source": image_source,
                "first_gid": tileset.firstgid,
                "tile_width": tile_width,
                "tile_height": tile_height,
                "tile_count": tile_count,
                "columns": columns,
            }
            
            return tileset_info
            
        except Exception as e:
            logger.error(f"Failed to parse external tileset {tileset.source}: {e}")
            return None

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

        # Check for collision on any of the designated collision layers
        if self.collision_layers:
            for layer in self.collision_layers:
                if layer.data[y][x] != 0:
                    return False  # Tile is on a collision layer

        # Check for walkable property on the tile itself
        # This part of the logic might need adjustment based on how your tilesets are configured
        # For now, we assume that if it's not on a collision layer, it's walkable.
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

                # Get tiles from all visible layers
                layer_gids = []
                tile_properties = {}
                collision_info = {}

                if self.tmx_data and hasattr(self.tmx_data, "layers"):
                    # Collect tiles from all visible layers
                    for layer_index, layer in enumerate(self.tmx_data.layers):
                        if hasattr(layer, "data") and layer.visible:
                            local_gid = layer.data[tile_y][tile_x]
                            if local_gid > 0:  # Only include non-empty tiles
                                # Convert pytmx local GID to global GID using raw TMX data
                                global_gid = self._convert_local_to_global_gid(local_gid, tile_x, tile_y, layer_index)
                                if global_gid > 0:
                                    layer_gids.append({
                                        "gid": global_gid,
                                        "layer_name": layer.name
                                    })

                    # Check collision layers for additional rendering info
                    for layer in self.collision_layers:
                        if hasattr(layer, "data"):
                            collision_gid = layer.data[tile_y][tile_x]
                            if collision_gid > 0:  # Non-empty tile on collision layer
                                collision_info[layer.name] = collision_gid

                    # Get tile properties from the bottom-most layer with a tile
                    if layer_gids:
                        # Use the first (bottom) layer's GID for properties
                        bottom_gid = layer_gids[0]["gid"]
                        tile_properties = (
                            self.tmx_data.get_tile_properties_by_gid(bottom_gid) or {}
                        )

                # Add computed properties
                tile_properties["walkable"] = self.is_walkable(tile_x, tile_y)
                if collision_info:
                    tile_properties["collision_layers"] = collision_info

                # Create tile data with all layers
                tile_data = {
                    "layers": layer_gids,  # All layers for this tile
                    "properties": tile_properties
                }
                
                # For backward compatibility, include primary GID from bottom layer
                if layer_gids:
                    tile_data["gid"] = layer_gids[0]["gid"]
                else:
                    tile_data["gid"] = 0

                row.append(tile_data)

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

        spawn_x, spawn_y = tile_map.get_spawn_position()
        return default_map_id, spawn_x, spawn_y

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
