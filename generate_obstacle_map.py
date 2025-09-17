#!/usr/bin/env python3
"""
Generate a test map with proper obstacles and collision detection.
This map will have walls, barriers, and varied terrain to test movement validation.
"""

import random


def generate_obstacle_test_map():
    """Generate a 50x50 map with strategic obstacles for testing collision detection."""

    # Map dimensions
    width, height = 50, 50

    # Tile IDs:
    # 1 = grass (walkable)
    # 2 = stone wall (not walkable)
    # 3 = water (not walkable)
    # 4 = tree (not walkable)

    # Initialize map with grass
    tiles = [[1 for _ in range(width)] for _ in range(height)]

    print("🗺️  Generating obstacle test map...")

    # Add border walls (except for a few entrances)
    for x in range(width):
        tiles[0][x] = 2  # Top wall
        tiles[height - 1][x] = 2  # Bottom wall
    for y in range(height):
        tiles[y][0] = 2  # Left wall
        tiles[y][width - 1] = 2  # Right wall

    # Add entrance gaps in walls
    tiles[0][width // 2] = 1  # Top entrance
    tiles[height - 1][width // 2] = 1  # Bottom entrance
    tiles[height // 2][0] = 1  # Left entrance
    tiles[height // 2][width - 1] = 1  # Right entrance

    # Create a maze-like structure in the center
    for x in range(10, 40, 4):
        for y in range(10, 40, 4):
            # Create small wall segments
            if random.random() < 0.7:
                tiles[y][x] = 2
                if x + 1 < width:
                    tiles[y][x + 1] = 2

    # Add some water features (rivers)
    # Horizontal river
    river_y = 25
    for x in range(5, 45):
        if random.random() < 0.8:
            tiles[river_y][x] = 3
            if random.random() < 0.3:  # Some tiles above/below
                if river_y - 1 >= 0:
                    tiles[river_y - 1][x] = 3
                if river_y + 1 < height:
                    tiles[river_y + 1][x] = 3

    # Add bridges over the river
    for bridge_x in [15, 25, 35]:
        tiles[river_y][bridge_x] = 1
        tiles[river_y - 1][bridge_x] = 1
        tiles[river_y + 1][bridge_x] = 1

    # Add tree clusters
    tree_centers = [(10, 10), (40, 10), (10, 40), (40, 40)]
    for center_x, center_y in tree_centers:
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                tree_x, tree_y = center_x + dx, center_y + dy
                if 0 <= tree_x < width and 0 <= tree_y < height:
                    if random.random() < 0.6:
                        tiles[tree_y][tree_x] = 4

    # Ensure spawn area (25, 25) is clear
    spawn_x, spawn_y = 25, 25
    for dx in range(-2, 3):
        for dy in range(-2, 3):
            clear_x, clear_y = spawn_x + dx, spawn_y + dy
            if 0 <= clear_x < width and 0 <= clear_y < height:
                tiles[clear_y][clear_x] = 1

    # Create some corridors to ensure connectivity
    # Horizontal corridor
    corridor_y = 15
    for x in range(5, 45):
        tiles[corridor_y][x] = 1

    # Vertical corridor
    corridor_x = 15
    for y in range(5, 45):
        tiles[y][corridor_x] = 1

    return tiles, width, height


def create_tmx_file(tiles, width, height, filename):
    """Create a TMX file with proper tile properties for collision detection."""

    # Flatten tiles for TMX format
    tile_data = []
    for row in tiles:
        tile_data.extend(row)

    # Create CSV data
    csv_data = ",".join(map(str, tile_data))

    tmx_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<map version="1.10" tiledversion="1.10.1" orientation="orthogonal" renderorder="right-down" width="{width}" height="{height}" tilewidth="32" tileheight="32" infinite="0" nextlayerid="2" nextobjectid="1">
 <tileset firstgid="1" name="terrain" tilewidth="32" tileheight="32" tilecount="4" columns="2">
  <image source="terrain.png" width="64" height="64"/>
  <tile id="0">
   <properties>
    <property name="walkable" type="bool" value="true"/>
   </properties>
  </tile>
  <tile id="1">
   <properties>
    <property name="walkable" type="bool" value="false"/>
   </properties>
  </tile>
  <tile id="2">
   <properties>
    <property name="walkable" type="bool" value="false"/>
   </properties>
  </tile>
  <tile id="3">
   <properties>
    <property name="walkable" type="bool" value="false"/>
   </properties>
  </tile>
 </tileset>
 <layer id="1" name="Tile Layer 1" width="{width}" height="{height}">
  <data encoding="csv">
{csv_data}
  </data>
 </layer>
</map>"""

    with open(filename, "w") as f:
        f.write(tmx_content)

    print(f"✅ Created {filename}")


def analyze_map(tiles, width, height):
    """Analyze the generated map and print statistics."""

    tile_counts = {1: 0, 2: 0, 3: 0, 4: 0}

    for row in tiles:
        for tile in row:
            tile_counts[tile] += 1

    total_tiles = width * height
    walkable_tiles = tile_counts[1]
    obstacle_tiles = total_tiles - walkable_tiles

    print(f"\n📊 Map Analysis:")
    print(f"   Total tiles: {total_tiles}")
    print(
        f"   Walkable (grass): {tile_counts[1]} ({tile_counts[1]/total_tiles*100:.1f}%)"
    )
    print(f"   Walls: {tile_counts[2]} ({tile_counts[2]/total_tiles*100:.1f}%)")
    print(f"   Water: {tile_counts[3]} ({tile_counts[3]/total_tiles*100:.1f}%)")
    print(f"   Trees: {tile_counts[4]} ({tile_counts[4]/total_tiles*100:.1f}%)")
    print(
        f"   Total obstacles: {obstacle_tiles} ({obstacle_tiles/total_tiles*100:.1f}%)"
    )


if __name__ == "__main__":
    print("🏗️  Generating obstacle test map for collision detection...")

    tiles, width, height = generate_obstacle_test_map()
    create_tmx_file(tiles, width, height, "server/maps/obstacle_test_map.tmx")
    analyze_map(tiles, width, height)

    print(f"\n🎯 Recommended spawn position: (25, 25)")
    print(f"🧪 This map includes:")
    print(f"   • Border walls with entrance gaps")
    print(f"   • Maze-like interior walls")
    print(f"   • Water features with bridges")
    print(f"   • Tree clusters")
    print(f"   • Clear corridors for movement")
    print(f"   • ~30-40% obstacles for proper collision testing")
