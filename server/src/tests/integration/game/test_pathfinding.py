"""
Unit tests for pathfinding service.

Tests cover the static PathfindingService methods:
- find_path() with A* algorithm
- get_next_step() convenience method
- has_line_of_sight() with Bresenham's algorithm
- find_nearest_open_tile() for respawn collision avoidance
- manhattan_distance() utility
"""

import pytest
from server.src.services.pathfinding_service import PathfindingService, PathResult


class TestPathfindingService:
    """Test A* pathfinding algorithm."""
    
    def test_straight_path_horizontal(self):
        """Test pathfinding in a straight line horizontally."""
        # Create empty grid (all walkable)
        grid = [[False] * 10 for _ in range(10)]
        
        # Find path from (0, 5) to (9, 5)
        result = PathfindingService.find_path(
            start=(0, 5),
            goal=(9, 5),
            collision_grid=grid
        )
        
        assert result.success
        assert result.distance == 9  # 9 steps to go from x=0 to x=9
        # Path includes start position
        assert result.path[0] == (0, 5)
        assert result.path[-1] == (9, 5)  # Last step (goal)
        
        # Verify path is a straight line
        for i, (x, y) in enumerate(result.path):
            assert x == i
            assert y == 5
    
    def test_straight_path_vertical(self):
        """Test pathfinding in a straight line vertically."""
        grid = [[False] * 10 for _ in range(10)]
        
        # Find path from (5, 0) to (5, 9)
        result = PathfindingService.find_path(
            start=(5, 0),
            goal=(5, 9),
            collision_grid=grid
        )
        
        assert result.success
        assert result.distance == 9
        assert result.path[0] == (5, 0)
        assert result.path[-1] == (5, 9)
        
        # Verify path is a straight line
        for i, (x, y) in enumerate(result.path):
            assert x == 5
            assert y == i
    
    def test_path_around_single_obstacle(self):
        """Test pathfinding around a single obstacle."""
        # Create grid with one blocking tile
        grid = [[False] * 5 for _ in range(5)]
        grid[2][2] = True  # Block center tile
        
        # Find path from (0, 2) to (4, 2) - must go around obstacle
        result = PathfindingService.find_path(
            start=(0, 2),
            goal=(4, 2),
            collision_grid=grid
        )
        
        assert result.success
        assert (2, 2) not in result.path  # Path should not go through obstacle
        assert result.path[-1] == (4, 2)  # Should reach goal
        
        # Path should be longer than straight line due to detour
        assert result.distance > 4
    
    def test_path_around_wall(self):
        """Test pathfinding around a vertical wall."""
        # Create grid with vertical wall
        grid = [[False] * 10 for _ in range(10)]
        
        # Create vertical wall at x=5, from y=2 to y=7
        for y in range(2, 8):
            grid[y][5] = True
        
        # Find path from (3, 5) to (7, 5) - must go around wall
        result = PathfindingService.find_path(
            start=(3, 5),
            goal=(7, 5),
            collision_grid=grid
        )
        
        assert result.success
        assert result.path[-1] == (7, 5)
        
        # Verify path doesn't go through wall
        for x, y in result.path:
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
        
        # Try to reach blocked center from outside
        result = PathfindingService.find_path(
            start=(0, 0),
            goal=(2, 2),
            collision_grid=grid
        )
        
        assert not result.success
        assert result.path == []
        assert result.distance == 0
    
    def test_start_equals_goal(self):
        """Test pathfinding when start equals goal."""
        grid = [[False] * 5 for _ in range(5)]
        
        result = PathfindingService.find_path(
            start=(2, 2),
            goal=(2, 2),
            collision_grid=grid
        )
        
        assert result.success
        assert result.path == [(2, 2)]  # Just the start/goal position
        assert result.distance == 0
    
    def test_adjacent_goal(self):
        """Test pathfinding to adjacent tile."""
        grid = [[False] * 5 for _ in range(5)]
        
        # Move one step right
        result = PathfindingService.find_path(
            start=(2, 2),
            goal=(3, 2),
            collision_grid=grid
        )
        
        assert result.success
        assert result.distance == 1
        assert result.path == [(2, 2), (3, 2)]
    
    def test_diagonal_blocked(self):
        """Test that pathfinding only uses 4-directional movement (no diagonals)."""
        grid = [[False] * 5 for _ in range(5)]
        
        # Find path from (0, 0) to (2, 2)
        result = PathfindingService.find_path(
            start=(0, 0),
            goal=(2, 2),
            collision_grid=grid
        )
        
        assert result.success
        assert result.distance == 4  # Must take 4 steps (no diagonal shortcuts)
        
        # Verify no diagonal movements
        for i in range(1, len(result.path)):
            x_prev, y_prev = result.path[i-1]
            x, y = result.path[i]
            # Each step should only change x OR y, not both
            assert (x == x_prev and abs(y - y_prev) == 1) or \
                   (y == y_prev and abs(x - x_prev) == 1)
    
    def test_max_distance_exceeded(self):
        """Test pathfinding respects max distance limit."""
        # Create very large empty grid
        grid = [[False] * 100 for _ in range(100)]
        
        # Try to find path that would exceed max_distance (50)
        result = PathfindingService.find_path(
            start=(0, 0),
            goal=(99, 0),
            collision_grid=grid,
            max_distance=50
        )
        
        # Should return failure because path would be too long
        assert not result.success
    
    def test_path_includes_start_and_goal(self):
        """Test that returned path includes both start and goal."""
        grid = [[False] * 5 for _ in range(5)]
        
        result = PathfindingService.find_path(
            start=(0, 0),
            goal=(3, 0),
            collision_grid=grid
        )
        
        assert result.success
        assert (0, 0) in result.path  # Start should be in path
        assert (3, 0) in result.path  # Goal should be in path
        assert result.path[0] == (0, 0)  # Start should be first
        assert result.path[-1] == (3, 0)  # Goal should be last
    
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
        
        # Find path from top-left to bottom-right
        result = PathfindingService.find_path(
            start=(0, 0),
            goal=(4, 4),
            collision_grid=grid
        )
        
        assert result.success
        assert result.path[-1] == (4, 4)
        
        # Verify path doesn't go through any blocked tiles
        for x, y in result.path:
            assert not grid[y][x], f"Path goes through blocked tile at ({x}, {y})"
    
    def test_edge_cases_boundaries(self):
        """Test pathfinding at grid boundaries."""
        grid = [[False] * 10 for _ in range(10)]
        
        # Test path along top edge
        result = PathfindingService.find_path(
            start=(0, 0),
            goal=(9, 0),
            collision_grid=grid
        )
        
        assert result.success
        assert all(y == 0 for x, y in result.path)  # Should stay on top edge
        
        # Test path along bottom edge
        result = PathfindingService.find_path(
            start=(0, 9),
            goal=(9, 9),
            collision_grid=grid
        )
        
        assert result.success
        assert all(y == 9 for x, y in result.path)  # Should stay on bottom edge
    
    def test_path_efficiency_straight_line(self):
        """Test that pathfinding finds optimal (shortest) path."""
        grid = [[False] * 10 for _ in range(10)]
        
        # For a straight line, path length should equal Manhattan distance
        start_x, start_y = 0, 0
        goal_x, goal_y = 5, 5
        
        result = PathfindingService.find_path(
            start=(start_x, start_y),
            goal=(goal_x, goal_y),
            collision_grid=grid
        )
        
        assert result.success
        manhattan_distance = abs(goal_x - start_x) + abs(goal_y - start_y)
        assert result.distance == manhattan_distance  # Path should be optimal
    
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
        
        result = PathfindingService.find_path(
            start=(0, 0),
            goal=(9, 9),
            collision_grid=grid
        )
        
        assert result.success
        assert result.path[-1] == (9, 9)
        
        # Verify path goes through the corridor
        corridor_tiles = [(x, 5) for x in range(10)]
        has_corridor_tile = any(tile in corridor_tiles for tile in result.path)
        assert has_corridor_tile


class TestGetNextStep:
    """Test get_next_step convenience method."""
    
    def test_next_step_toward_goal(self):
        """Test getting next step toward a goal."""
        grid = [[False] * 5 for _ in range(5)]
        
        next_step = PathfindingService.get_next_step(
            current=(0, 0),
            target=(3, 0),
            collision_grid=grid
        )
        
        assert next_step == (1, 0)  # Should move one step right
    
    def test_next_step_no_path(self):
        """Test getting next step when no path exists."""
        grid = [[False] * 5 for _ in range(5)]
        # Block all paths
        grid[0][1] = True
        grid[1][0] = True
        
        next_step = PathfindingService.get_next_step(
            current=(0, 0),
            target=(4, 4),
            collision_grid=grid
        )
        
        assert next_step is None
    
    def test_next_step_already_at_goal(self):
        """Test getting next step when already at goal."""
        grid = [[False] * 5 for _ in range(5)]
        
        next_step = PathfindingService.get_next_step(
            current=(2, 2),
            target=(2, 2),
            collision_grid=grid
        )
        
        assert next_step is None  # No next step when already there


class TestBlockedPositions:
    """Test entity collision avoidance via blocked_positions."""
    
    def test_path_avoids_blocked_positions(self):
        """Test that pathfinding avoids entity positions."""
        grid = [[False] * 5 for _ in range(5)]
        blocked = {(1, 0), (2, 0)}  # Two entities blocking straight path
        
        result = PathfindingService.find_path(
            start=(0, 0),
            goal=(3, 0),
            collision_grid=grid,
            blocked_positions=blocked
        )
        
        assert result.success
        assert (1, 0) not in result.path
        assert (2, 0) not in result.path
    
    def test_goal_position_allowed_even_if_blocked(self):
        """Test that goal position is reachable even if in blocked_positions."""
        grid = [[False] * 5 for _ in range(5)]
        blocked = {(3, 0)}  # Entity at goal position
        
        result = PathfindingService.find_path(
            start=(0, 0),
            goal=(3, 0),
            collision_grid=grid,
            blocked_positions=blocked
        )
        
        assert result.success
        assert result.path[-1] == (3, 0)


class TestLineOfSight:
    """Test Bresenham's line of sight algorithm."""
    
    def test_clear_los_straight(self):
        """Test clear line of sight in straight line."""
        grid = [[False] * 10 for _ in range(10)]
        
        assert PathfindingService.has_line_of_sight((0, 0), (5, 0), grid)
        assert PathfindingService.has_line_of_sight((5, 5), (5, 9), grid)
    
    def test_clear_los_diagonal(self):
        """Test clear line of sight diagonally."""
        grid = [[False] * 10 for _ in range(10)]
        
        assert PathfindingService.has_line_of_sight((0, 0), (5, 5), grid)
    
    def test_blocked_los(self):
        """Test blocked line of sight."""
        grid = [[False] * 10 for _ in range(10)]
        grid[2][2] = True  # Obstacle in the way
        
        assert not PathfindingService.has_line_of_sight((0, 0), (4, 4), grid)
    
    def test_los_to_adjacent(self):
        """Test line of sight to adjacent tile."""
        grid = [[False] * 5 for _ in range(5)]
        
        assert PathfindingService.has_line_of_sight((2, 2), (3, 2), grid)
        assert PathfindingService.has_line_of_sight((2, 2), (2, 3), grid)
    
    def test_los_same_tile(self):
        """Test line of sight to same tile."""
        grid = [[False] * 5 for _ in range(5)]
        
        assert PathfindingService.has_line_of_sight((2, 2), (2, 2), grid)


class TestFindNearestOpenTile:
    """Test spiral search for nearest open tile."""
    
    def test_center_is_open(self):
        """Test when center tile is already open."""
        grid = [[False] * 5 for _ in range(5)]
        
        result = PathfindingService.find_nearest_open_tile(
            center=(2, 2),
            collision_grid=grid
        )
        
        assert result == (2, 2)
    
    def test_center_blocked_by_collision(self):
        """Test finding nearest tile when center is blocked by collision."""
        grid = [[False] * 5 for _ in range(5)]
        grid[2][2] = True  # Block center
        
        result = PathfindingService.find_nearest_open_tile(
            center=(2, 2),
            collision_grid=grid
        )
        
        assert result is not None
        assert result != (2, 2)
        # Should be adjacent (Manhattan distance 1)
        assert PathfindingService.manhattan_distance((2, 2), result) == 1
    
    def test_center_blocked_by_entity(self):
        """Test finding nearest tile when center is blocked by entity."""
        grid = [[False] * 5 for _ in range(5)]
        blocked = {(2, 2)}  # Entity at center
        
        result = PathfindingService.find_nearest_open_tile(
            center=(2, 2),
            collision_grid=grid,
            blocked_positions=blocked
        )
        
        assert result is not None
        assert result != (2, 2)
        # Should be adjacent (Manhattan distance 1)
        assert PathfindingService.manhattan_distance((2, 2), result) == 1
    
    def test_max_radius_respected(self):
        """Test that search respects max_radius."""
        grid = [[True] * 10 for _ in range(10)]  # All blocked
        grid[5][8] = False  # One open tile at distance 3
        
        # With radius 2, should not find it
        result = PathfindingService.find_nearest_open_tile(
            center=(5, 5),
            collision_grid=grid,
            max_radius=2
        )
        
        assert result is None
        
        # With radius 3, should find it
        result = PathfindingService.find_nearest_open_tile(
            center=(5, 5),
            collision_grid=grid,
            max_radius=3
        )
        
        assert result == (8, 5)


class TestManhattanDistance:
    """Test Manhattan distance calculation."""
    
    def test_horizontal_distance(self):
        """Test horizontal Manhattan distance."""
        assert PathfindingService.manhattan_distance((0, 5), (10, 5)) == 10
    
    def test_vertical_distance(self):
        """Test vertical Manhattan distance."""
        assert PathfindingService.manhattan_distance((5, 0), (5, 10)) == 10
    
    def test_diagonal_distance(self):
        """Test diagonal Manhattan distance."""
        assert PathfindingService.manhattan_distance((0, 0), (5, 5)) == 10
    
    def test_same_position(self):
        """Test Manhattan distance to same position."""
        assert PathfindingService.manhattan_distance((5, 5), (5, 5)) == 0
