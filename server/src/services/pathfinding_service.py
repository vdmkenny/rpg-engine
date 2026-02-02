"""
Pathfinding service with A* algorithm.

PURE ALGORITHM - No GSM access.
Receives collision data as parameters.
Cardinal movement only (no diagonals).

This service is responsible for:
1. A* pathfinding for entity movement
2. Line of sight (Bresenham's) checks for visibility and combat
3. Finding nearest open tiles for respawn collision avoidance
"""

from typing import List, Tuple, Optional, Set, Dict
from dataclasses import dataclass
import heapq


@dataclass
class PathResult:
    """Result of a pathfinding query."""
    success: bool
    path: List[Tuple[int, int]]  # List of (x, y) waypoints including start
    distance: int  # Total path length (number of steps)


class PathfindingService:
    """
    A* pathfinding service with cardinal movement only.
    
    This is a pure algorithm class with no external dependencies.
    All required data (collision grids, blocked positions) must be
    passed as parameters.
    
    All methods are static for consistency with other services.
    """
    
    # Cardinal directions only (no diagonals): North, South, West, East
    DIRECTIONS: List[Tuple[int, int]] = [(0, -1), (0, 1), (-1, 0), (1, 0)]
    
    @staticmethod
    def find_path(
        start: Tuple[int, int],
        goal: Tuple[int, int],
        collision_grid: List[List[bool]],
        blocked_positions: Optional[Set[Tuple[int, int]]] = None,
        max_distance: int = 50,
    ) -> PathResult:
        """
        Find a path from start to goal using A* algorithm.
        
        Uses Manhattan distance heuristic for 4-directional movement.
        Explores orthogonal neighbors only (no diagonal movement).
        
        Args:
            start: (x, y) starting tile coordinates
            goal: (x, y) target tile coordinates
            collision_grid: 2D grid where True = blocked, False = walkable.
                           Indexed as collision_grid[y][x].
            blocked_positions: Additional blocked positions (e.g., other entities).
                              The goal position is allowed even if in blocked_positions.
            max_distance: Maximum path length to prevent expensive searches
            
        Returns:
            PathResult with success flag, path waypoints (including start), and distance
        """
        if blocked_positions is None:
            blocked_positions = set()
        
        # Validate grid
        if not collision_grid or len(collision_grid) == 0:
            return PathResult(success=False, path=[], distance=0)
        
        height = len(collision_grid)
        width = len(collision_grid[0]) if height > 0 else 0
        
        # Validate coordinates
        if not PathfindingService._in_bounds(start, width, height):
            return PathResult(success=False, path=[], distance=0)
        if not PathfindingService._in_bounds(goal, width, height):
            return PathResult(success=False, path=[], distance=0)
        
        # Check if start or goal is blocked by collision
        if collision_grid[start[1]][start[0]] or collision_grid[goal[1]][goal[0]]:
            return PathResult(success=False, path=[], distance=0)
        
        # If already at goal
        if start == goal:
            return PathResult(success=True, path=[start], distance=0)
        
        # A* implementation
        # Priority queue: (f_score, counter, node)
        counter = 0  # Tie-breaker for nodes with same f_score
        open_set: List[Tuple[float, int, Tuple[int, int]]] = [(0.0, counter, start)]
        counter += 1
        
        # Track best path to each node
        came_from: Dict[Tuple[int, int], Tuple[int, int]] = {}
        
        # Cost from start to node
        g_score: Dict[Tuple[int, int], float] = {start: 0}
        
        # Track visited nodes
        closed_set: Set[Tuple[int, int]] = set()
        
        while open_set:
            # Get node with lowest f_score
            _, _, current = heapq.heappop(open_set)
            
            # Skip if already processed
            if current in closed_set:
                continue
            
            # Found goal
            if current == goal:
                path = PathfindingService._reconstruct_path(came_from, current)
                return PathResult(success=True, path=path, distance=len(path) - 1)
            
            closed_set.add(current)
            current_g = g_score[current]
            
            # Check path length limit
            if current_g >= max_distance:
                continue
            
            # Explore neighbors (4-directional movement)
            for dx, dy in PathfindingService.DIRECTIONS:
                neighbor = (current[0] + dx, current[1] + dy)
                nx, ny = neighbor
                
                # Bounds check
                if not PathfindingService._in_bounds(neighbor, width, height):
                    continue
                
                # Skip if already processed
                if neighbor in closed_set:
                    continue
                
                # Collision check (wall/obstacle)
                if collision_grid[ny][nx]:
                    continue
                
                # Entity blocking check (skip for goal position - we want to reach it)
                if neighbor != goal and neighbor in blocked_positions:
                    continue
                
                # Calculate tentative g_score (all moves cost 1)
                tentative_g = current_g + 1.0
                
                # If this path to neighbor is better than previous
                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f = tentative_g + PathfindingService.manhattan_distance(neighbor, goal)
                    heapq.heappush(open_set, (float(f), counter, neighbor))
                    counter += 1
        
        # No path found
        return PathResult(success=False, path=[], distance=0)
    
    @staticmethod
    def get_next_step(
        current: Tuple[int, int],
        target: Tuple[int, int],
        collision_grid: List[List[bool]],
        blocked_positions: Optional[Set[Tuple[int, int]]] = None,
        max_distance: int = 50,
    ) -> Optional[Tuple[int, int]]:
        """
        Get the next tile to move toward when navigating to target.
        
        This is a convenience method that finds the full path and returns
        just the next step.
        
        Args:
            current: Current (x, y) position
            target: Target (x, y) position
            collision_grid: 2D collision grid (True = blocked)
            blocked_positions: Additional blocked positions (other entities)
            max_distance: Maximum pathfinding distance
            
        Returns:
            Next (x, y) position to move to, or None if no valid path
        """
        result = PathfindingService.find_path(
            start=current,
            goal=target,
            collision_grid=collision_grid,
            blocked_positions=blocked_positions,
            max_distance=max_distance,
        )
        
        if result.success and len(result.path) >= 2:
            return result.path[1]  # First step after current position
        
        return None
    
    @staticmethod
    def has_line_of_sight(
        start: Tuple[int, int],
        end: Tuple[int, int],
        collision_grid: List[List[bool]],
    ) -> bool:
        """
        Check if there is a clear line of sight between two points.
        
        Uses Bresenham's Line Algorithm to trace a line from start to end
        and checks if any tile along the way is blocked.
        
        Args:
            start: (x, y) starting tile coordinates
            end: (x, y) target tile coordinates
            collision_grid: 2D grid where True indicates a blocked tile
            
        Returns:
            True if line of sight is clear (no collision tiles in the way), 
            False otherwise.
        """
        if not collision_grid or len(collision_grid) == 0:
            return False
        
        height = len(collision_grid)
        width = len(collision_grid[0]) if height > 0 else 0
        
        x0, y0 = start
        x1, y1 = end
        
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        
        x, y = x0, y0
        
        while True:
            # Check bounds
            if not (0 <= x < width and 0 <= y < height):
                return False
            
            # Check collision at current point (except start and end)
            if (x, y) != start and (x, y) != end:
                if collision_grid[y][x]:
                    return False
            
            # Reached end?
            if x == x1 and y == y1:
                break
            
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x += sx
            if e2 < dx:
                err += dx
                y += sy
        
        return True
    
    @staticmethod
    def manhattan_distance(a: Tuple[int, int], b: Tuple[int, int]) -> int:
        """
        Calculate Manhattan distance between two points.
        
        This is the appropriate heuristic for cardinal-only movement.
        
        Args:
            a: First (x, y) position
            b: Second (x, y) position
            
        Returns:
            Manhattan distance (|dx| + |dy|)
        """
        return abs(a[0] - b[0]) + abs(a[1] - b[1])
    
    @staticmethod
    def find_nearest_open_tile(
        center: Tuple[int, int],
        collision_grid: List[List[bool]],
        blocked_positions: Optional[Set[Tuple[int, int]]] = None,
        max_radius: int = 10,
    ) -> Optional[Tuple[int, int]]:
        """
        Find the nearest open (walkable) tile using spiral search.
        
        Used for finding valid respawn positions when the spawn tile
        is occupied by another entity.
        
        Args:
            center: Center (x, y) position to search from
            collision_grid: 2D collision grid (True = blocked)
            blocked_positions: Additional blocked positions (other entities)
            max_radius: Maximum search radius in tiles
            
        Returns:
            Nearest open (x, y) position, or None if none found within radius
        """
        if blocked_positions is None:
            blocked_positions = set()
        
        if not collision_grid or len(collision_grid) == 0:
            return None
        
        height = len(collision_grid)
        width = len(collision_grid[0]) if height > 0 else 0
        
        cx, cy = center
        
        # Check center first
        if PathfindingService._is_tile_open(
            cx, cy, collision_grid, blocked_positions, width, height
        ):
            return center
        
        # Spiral search outward by Manhattan distance
        for radius in range(1, max_radius + 1):
            # Check all tiles at exactly this Manhattan distance
            for dx in range(-radius, radius + 1):
                dy_abs = radius - abs(dx)
                for dy in ([-dy_abs, dy_abs] if dy_abs > 0 else [0]):
                    x, y = cx + dx, cy + dy
                    
                    if PathfindingService._is_tile_open(
                        x, y, collision_grid, blocked_positions, width, height
                    ):
                        return (x, y)
        
        return None
    
    @staticmethod
    def _in_bounds(pos: Tuple[int, int], width: int, height: int) -> bool:
        """Check if position is within grid bounds."""
        x, y = pos
        return 0 <= x < width and 0 <= y < height
    
    @staticmethod
    def _is_tile_open(
        x: int,
        y: int,
        collision_grid: List[List[bool]],
        blocked_positions: Set[Tuple[int, int]],
        width: int,
        height: int,
    ) -> bool:
        """Check if a tile is walkable and not blocked by an entity."""
        # Bounds check
        if not (0 <= x < width and 0 <= y < height):
            return False
        
        # Collision check
        if collision_grid[y][x]:
            return False
        
        # Entity blocking check
        if (x, y) in blocked_positions:
            return False
        
        return True
    
    @staticmethod
    def _reconstruct_path(
        came_from: Dict[Tuple[int, int], Tuple[int, int]],
        current: Tuple[int, int],
    ) -> List[Tuple[int, int]]:
        """Reconstruct path from came_from map, including start position."""
        path = [current]
        while current in came_from:
            current = came_from[current]
            path.append(current)
        path.reverse()
        return path
