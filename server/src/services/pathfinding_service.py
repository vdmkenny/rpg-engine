"""
Service for pathfinding and line of sight calculations.

This service is responsible for:
1. A* pathfinding for entity movement
2. Line of sight (raycasting) checks for visibility and combat
3. Map grid access and collision detection (via GameStateManager if needed, or cached map data)
"""

from typing import List, Tuple, Optional, Set, Dict
import math
import heapq

class PathfindingService:
    def __init__(self):
        # We might want to inject a map service or grid provider here later.
        # For now, we'll assume methods receive the necessary grid/collision data.
        pass

    def find_path(
        self,
        start: Tuple[int, int],
        goal: Tuple[int, int],
        collision_grid: List[List[bool]],
        max_path_length: int = 50
    ) -> Optional[List[Tuple[int, int]]]:
        """
        Find a path from start to goal using A* algorithm.
        
        Uses Manhattan distance heuristic for 4-directional movement.
        Explores orthogonal neighbors only (no diagonal movement).
        
        Args:
            start: (x, y) starting tile coordinates
            goal: (x, y) target tile coordinates
            collision_grid: 2D grid where True indicates a blocked tile
            max_path_length: Maximum path length to prevent infinite searches
            
        Returns:
            List of (x, y) tuples representing the path (excluding start, including goal),
            or None if no path found.
        """
        if not collision_grid or len(collision_grid) == 0:
            return None
        
        height = len(collision_grid)
        width = len(collision_grid[0]) if height > 0 else 0
        
        # Validate coordinates
        if not self._in_bounds(start, width, height) or not self._in_bounds(goal, width, height):
            return None
        
        # Check if start or goal is blocked
        if collision_grid[start[1]][start[0]] or collision_grid[goal[1]][goal[0]]:
            return None
        
        # If already at goal
        if start == goal:
            return []
        
        # A* implementation
        # Priority queue: (f_score, counter, node)
        counter = 0  # Tie-breaker for nodes with same f_score
        open_set: List[Tuple[float, int, Tuple[int, int]]] = [(0.0, counter, start)]
        counter += 1
        
        # Track best path to each node
        came_from: Dict[Tuple[int, int], Tuple[int, int]] = {}
        
        # Cost from start to node
        g_score: Dict[Tuple[int, int], float] = {start: 0}
        
        # Estimated total cost (g_score + heuristic)
        f_score: Dict[Tuple[int, int], float] = {start: self._manhattan_distance(start, goal)}
        
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
                return self._reconstruct_path(came_from, current, start)
            
            closed_set.add(current)
            current_g = g_score[current]
            
            # Check path length limit
            if current_g >= max_path_length:
                continue
            
            # Explore neighbors (4-directional movement)
            for neighbor in self._get_neighbors(current, width, height):
                if neighbor in closed_set:
                    continue
                
                # Check if walkable
                nx, ny = neighbor
                if collision_grid[ny][nx]:
                    continue
                
                # Calculate tentative g_score
                tentative_g = current_g + 1.0  # Cost = 1 for orthogonal movement
                
                # If this path to neighbor is better than previous
                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f = tentative_g + self._manhattan_distance(neighbor, goal)
                    f_score[neighbor] = f
                    heapq.heappush(open_set, (float(f), counter, neighbor))
                    counter += 1
        
        # No path found
        return None
    
    def _in_bounds(self, pos: Tuple[int, int], width: int, height: int) -> bool:
        """Check if position is within grid bounds."""
        x, y = pos
        return 0 <= x < width and 0 <= y < height
    
    def _get_neighbors(self, pos: Tuple[int, int], width: int, height: int) -> List[Tuple[int, int]]:
        """Get orthogonal neighbors (up, down, left, right)."""
        x, y = pos
        neighbors = [
            (x, y - 1),  # Up
            (x, y + 1),  # Down
            (x - 1, y),  # Left
            (x + 1, y),  # Right
        ]
        return [n for n in neighbors if self._in_bounds(n, width, height)]
    
    def _manhattan_distance(self, a: Tuple[int, int], b: Tuple[int, int]) -> float:
        """Manhattan distance heuristic for 4-directional movement."""
        return abs(a[0] - b[0]) + abs(a[1] - b[1])
    
    def _reconstruct_path(
        self, 
        came_from: Dict[Tuple[int, int], Tuple[int, int]], 
        current: Tuple[int, int],
        start: Tuple[int, int]
    ) -> List[Tuple[int, int]]:
        """Reconstruct path from goal to start, return reversed (start to goal)."""
        path = []
        while current in came_from:
            path.append(current)
            current = came_from[current]
        path.reverse()
        return path

    def has_line_of_sight(
        self,
        start: Tuple[int, int],
        end: Tuple[int, int],
        collision_grid: List[List[bool]]
    ) -> bool:
        """
        Check if there is a clear line of sight between two points using Bresenham's Line Algorithm.
        
        Args:
            start: (x, y) starting tile coordinates
            end: (x, y) target tile coordinates
            collision_grid: 2D grid where True indicates a blocked tile
            
        Returns:
            True if line of sight is clear (no collision tiles in the way), False otherwise.
        """
        x0, y0 = start
        x1, y1 = end
        
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        
        while True:
            # Check collision at current point (except possibly start/end if allowed)
            # For strict LOS, walls block vision.
            # Safety check for grid bounds
            if 0 <= y0 < len(collision_grid) and 0 <= x0 < len(collision_grid[0]):
                 if collision_grid[y0][x0]:
                     # If the blocked tile is the target, we might allow it (e.g. seeing a wall)
                     # But typically for "can I shoot/see target", if the target is ON a wall 
                     # (which shouldn't happen for entities) it's edge case.
                     # If the wall is strictly between start and end, it blocks.
                     if (x0, y0) != start and (x0, y0) != end:
                         return False

            if x0 == x1 and y0 == y1:
                break
                
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy
                
        return True

    def get_distance(self, start: Tuple[int, int], end: Tuple[int, int]) -> float:
        """Euclidean distance between two points."""
        return math.sqrt((start[0] - end[0])**2 + (start[1] - end[1])**2)
