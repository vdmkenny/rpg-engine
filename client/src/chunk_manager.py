"""
Chunk management for map data.
"""

from typing import Dict, Tuple, Any, Optional


class ChunkManager:
    """Manages map chunks for rendering."""

    def __init__(self):
        self.chunks: Dict[Tuple[int, int], Dict[str, Any]] = {}  # (chunk_x, chunk_y) -> chunk_data

    def add_chunk(self, chunk_data: Dict[str, Any]) -> None:
        """Add a chunk to the manager."""
        chunk_x = chunk_data.get("chunk_x", 0)
        chunk_y = chunk_data.get("chunk_y", 0)
        self.chunks[(chunk_x, chunk_y)] = chunk_data

    def get_tile_at(self, world_x: int, world_y: int) -> Optional[Any]:
        """Get tile data at world coordinates."""
        chunk_x = world_x // 16
        chunk_y = world_y // 16

        chunk_data = self.chunks.get((chunk_x, chunk_y))
        if not chunk_data:
            return None

        tiles = chunk_data.get("tiles", [])
        local_x = world_x % 16
        local_y = world_y % 16

        if local_y < len(tiles) and local_x < len(tiles[local_y]):
            return tiles[local_y][local_x]

        return None