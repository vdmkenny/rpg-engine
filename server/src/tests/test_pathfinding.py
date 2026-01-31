"""
Unit tests for pathfinding service.
"""

import pytest
from server.src.services.pathfinding_service import PathfindingService


class TestPathfindingService:
    """Test A* pathfinding algorithm."""
    
    def test_straight_path_horizontal(self):
        """Test pathfinding in a straight line horizontally."""
        # Create empty grid (all walkable)
        grid = [[False] * 10 for _ in range(10)]
        service = PathfindingService()
        
        # Find path from (0, 5) to (9, 5)
        path = service.find_path(
            start=(0, 5),
            goal=(9, 5),
            collision_grid=grid
        )
        
        assert path is not None
        assert len(path) == 9  # 9 steps to go from x=0 to x=9
        assert path[0] == (1, 5)  # First step
        assert path[-1] == (9, 5)  # Last step (goal)
        
        # Verify path is a straight line
        for i, (x, y) in enumerate(path):
            assert x == i + 1
            assert y == 5
    
    def test_straight_path_vertical(self):
        """Test pathfinding in a straight line vertically."""
        grid = [[False] * 10 for _ in range(10)]
        service = PathfindingService()
        
        # Find path from (5, 0) to (5, 9)
        path = service.find_path(
            start=(5, 0),
            goal=(5, 9),
            collision_grid=grid
        )
        
        assert path is not None
        assert len(path) == 9
        assert path[0] == (5, 1)
        assert path[-1] == (5, 9)
        
        # Verify path is a straight line
        for i, (x, y) in enumerate(path):
            assert x == 5
            assert y == i + 1
    
    def test_path_around_single_obstacle(self):
        """Test pathfinding around a single obstacle."""
        # Create grid with one blocking tile
        grid = [[False] * 5 for _ in range(5)]
        grid[2][2] = True  # Block center tile
        service = PathfindingService()
        
        # Find path from (0, 2) to (4, 2) - must go around obstacle
        path = service.find_path(
            start=(0, 2),
            goal=(4, 2),
            collision_grid=grid
        )
        
        assert path is not None
        assert (2, 2) not in path  # Path should not go through obstacle
        assert path[-1] == (4, 2)  # Should reach goal
        
        # Path should be longer than straight line due to detour
        assert len(path) > 4
    
    def test_path_around_wall(self):
        """Test pathfinding around a vertical wall."""
        # Create grid with vertical wall
        grid = [[False] * 10 for _ in range(10)]
        
        # Create vertical wall at x=5, from y=2 to y=7
        for y in range(2, 8):
            grid[y][5] = True
        
        service = PathfindingService()
        # Find path from (3, 5) to (7, 5) - must go around wall
        path = service.find_path(
            start=(3, 5),
            goal=(7, 5),
            collision_grid=grid
        )
        
        assert path is not None
        assert path[-1] == (7, 5)
        
        # Verify path doesn't go through wall
        for x, y in path:
            if x == 5:
                assert y < 2 or y > 7  # If at x=5, must be above or below wall
    
    def test_unreachable_goal_blocked(self):
        """Test pathfinding when goal is completely blocked."""
        grid = [[False] * 5 for _ in range(5)]
        
        # Surround center tile completely
        grid[1][2] = True  # Top
        grid[3][2] = True  # Bottom
        grid[2][1] = True  # Left
        grid[2][3] = True  # Right
        
        service = PathfindingService()
        # Try to reach blocked center from outside
        path = service.find_path(
            start=(0, 0),
            goal=(2, 2),
            collision_grid=grid
        )
        
        assert path is None  # Should return None for unreachable goal
    
    def test_start_equals_goal(self):
        """Test pathfinding when start equals goal."""
        grid = [[False] * 5 for _ in range(5)]
        service = PathfindingService()
        
        path = service.find_path(
            start=(2, 2),
            goal=(2, 2),
            collision_grid=grid
        )
        
        assert path == []  # Empty path when already at goal
    
    def test_adjacent_goal(self):
        """Test pathfinding to adjacent tile."""
        grid = [[False] * 5 for _ in range(5)]
        service = PathfindingService()
        
        # Move one step right
        path = service.find_path(
            start=(2, 2),
            goal=(3, 2),
            collision_grid=grid
        )
        
        assert path is not None
        assert len(path) == 1
        assert path[0] == (3, 2)
    
    def test_diagonal_blocked(self):
        """Test that pathfinding only uses 4-directional movement (no diagonals)."""
        grid = [[False] * 5 for _ in range(5)]
        service = PathfindingService()
        
        # Find path from (0, 0) to (2, 2)
        path = service.find_path(
            start=(0, 0),
            goal=(2, 2),
            collision_grid=grid
        )
        
        assert path is not None
        assert len(path) == 4  # Must take 4 steps (no diagonal shortcuts)
        
        # Verify no diagonal movements
        prev_x, prev_y = 0, 0
        for x, y in path:
            # Each step should only change x OR y, not both
            assert (x == prev_x and abs(y - prev_y) == 1) or \
                   (y == prev_y and abs(x - prev_x) == 1)
            prev_x, prev_y = x, y
    
    def test_max_path_length_exceeded(self):
        """Test pathfinding respects max path length limit."""
        # Create very large empty grid
        grid = [[False] * 100 for _ in range(100)]
        service = PathfindingService()
        
        # Try to find path that would exceed max_path_length (50)
        path = service.find_path(
            start=(0, 0),
            goal=(99, 0),
            collision_grid=grid,
            max_path_length=50
        )
        
        # Should return None because path would be too long
        assert path is None
    
    def test_path_excludes_start_includes_goal(self):
        """Test that returned path excludes start but includes goal."""
        grid = [[False] * 5 for _ in range(5)]
        service = PathfindingService()
        
        path = service.find_path(
            start=(0, 0),
            goal=(3, 0),
            collision_grid=grid
        )
        
        assert path is not None
        assert (0, 0) not in path  # Start should not be in path
        assert (3, 0) in path  # Goal should be in path
        assert path[-1] == (3, 0)  # Goal should be last element
    
    def test_complex_maze(self):
        """Test pathfinding through a complex maze."""
        # Create a maze pattern
        grid = [
            [False, True,  False, False, False],
            [False, True,  False, True,  False],
            [False, False, False, True,  False],
            [False, True,  True,  True,  False],
            [False, False, False, False, False],
        ]
        
        service = PathfindingService()
        # Find path from top-left to bottom-right
        path = service.find_path(
            start=(0, 0),
            goal=(4, 4),
            collision_grid=grid
        )
        
        assert path is not None
        assert path[-1] == (4, 4)
        
        # Verify path doesn't go through any blocked tiles
        for x, y in path:
            assert not grid[y][x], f"Path goes through blocked tile at ({x}, {y})"
    
    def test_edge_cases_boundaries(self):
        """Test pathfinding at grid boundaries."""
        grid = [[False] * 10 for _ in range(10)]
        service = PathfindingService()
        
        # Test path along top edge
        path = service.find_path(
            start=(0, 0),
            goal=(9, 0),
            collision_grid=grid
        )
        
        assert path is not None
        assert all(y == 0 for x, y in path)  # Should stay on top edge
        
        # Test path along bottom edge
        path = service.find_path(
            start=(0, 9),
            goal=(9, 9),
            collision_grid=grid
        )
        
        assert path is not None
        assert all(y == 9 for x, y in path)  # Should stay on bottom edge
    
    def test_path_efficiency_straight_line(self):
        """Test that pathfinding finds optimal (shortest) path."""
        grid = [[False] * 10 for _ in range(10)]
        service = PathfindingService()
        
        # For a straight line, path length should equal Manhattan distance
        start_x, start_y = 0, 0
        goal_x, goal_y = 5, 5
        
        path = service.find_path(
            start=(start_x, start_y),
            goal=(goal_x, goal_y),
            collision_grid=grid
        )
        
        assert path is not None
        manhattan_distance = abs(goal_x - start_x) + abs(goal_y - start_y)
        assert len(path) == manhattan_distance  # Path should be optimal
    
    def test_narrow_corridor(self):
        """Test pathfinding through a narrow 1-tile corridor."""
        # Create grid with walls everywhere
        grid = [[True] * 10 for _ in range(10)]
        
        # Create a narrow horizontal corridor at y=5
        for x in range(10):
            grid[5][x] = False
        
        # Create vertical connections to start/goal
        for y in range(6):
            grid[y][0] = False  # Left side connection
        for y in range(5, 10):
            grid[y][9] = False  # Right side connection
        
        service = PathfindingService()
        path = service.find_path(
            start=(0, 0),
            goal=(9, 9),
            collision_grid=grid
        )
        
        assert path is not None
        assert path[-1] == (9, 9)
        
        # Verify path goes through the corridor
        corridor_tiles = [(x, 5) for x in range(10)]
        has_corridor_tile = any(tile in corridor_tiles for tile in path)
        assert has_corridor_tile
