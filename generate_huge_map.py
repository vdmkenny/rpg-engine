#!/usr/bin/env python3
"""
Generate a large 200x200 TMX map with varied terrain and obstacles.
This will create proper chunk boundaries to test the streaming system.
"""
import random
import math


def generate_map_data():
    """Generate a 200x200 map with varied terrain patterns."""
    width, height = 200, 200
    data = []

    # Tile IDs: 1=walkable grass, 2=wall/obstacle, 3=walkable dirt, 4=unwalkable rocks

    for y in range(height):
        row = []
        for x in range(width):
            # Create different terrain zones

            # Zone 1: Starting area (safe zone around spawn 50,50)
            if 40 <= x <= 60 and 40 <= y <= 60:
                if (x - 50) ** 2 + (y - 50) ** 2 <= 100:  # Circle around spawn
                    row.append(1)  # Safe walkable grass
                else:
                    row.append(3)  # Walkable dirt

            # Zone 2: Maze-like area (top-left quadrant)
            elif x < 100 and y < 100:
                if (x % 8 == 0 or y % 8 == 0) and random.random() < 0.6:
                    row.append(2)  # Wall
                else:
                    row.append(1)  # Grass

            # Zone 3: Scattered obstacles (top-right quadrant)
            elif x >= 100 and y < 100:
                if random.random() < 0.15:  # 15% obstacles
                    row.append(4)  # Rocks
                elif random.random() < 0.3:
                    row.append(3)  # Dirt
                else:
                    row.append(1)  # Grass

            # Zone 4: Dense forest (bottom-left quadrant)
            elif x < 100 and y >= 100:
                if random.random() < 0.4:  # 40% obstacles (dense forest)
                    row.append(2)  # Trees
                else:
                    row.append(3)  # Forest floor

            # Zone 5: Open plains with rivers (bottom-right quadrant)
            else:
                # Create "river" patterns
                river1 = abs((x - 150) + (y - 150) * 0.5) < 3
                river2 = abs((x - 120) - (y - 180) * 0.3) < 2

                if river1 or river2:
                    row.append(4)  # Water (unwalkable)
                elif random.random() < 0.05:  # Sparse obstacles
                    row.append(2)  # Rocks
                else:
                    row.append(1)  # Grass plains

            # Add chunk boundaries (for debugging) - every 16 tiles
            if x % 16 == 0 or y % 16 == 0:
                if random.random() < 0.1:  # 10% chance for boundary markers
                    row.append(3)  # Dirt path

        data.append(row)

    return data


def write_tmx_file():
    """Write the complete TMX file with generated data."""
    print("🗺️  Generating 200x200 world map...")
    data = generate_map_data()

    # Convert 2D array to CSV string with exact formatting
    csv_lines = []
    for y, row in enumerate(data):
        if y == len(data) - 1:  # Last row - no trailing comma
            csv_lines.append(",".join(map(str, row)))
        else:
            csv_lines.append(",".join(map(str, row)) + ",")

    csv_data = "\n".join(csv_lines)

    # Complete TMX content
    tmx_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<map version="1.10" tiledversion="1.10.1" orientation="orthogonal" renderorder="right-down" width="200" height="200" tilewidth="32" tileheight="32" infinite="0" nextlayerid="3" nextobjectid="1">
 <tileset firstgid="1" name="basic" tilewidth="32" tileheight="32" tilecount="4" columns="2">
  <image source="basic.png" width="64" height="64"/>
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
    <property name="walkable" type="bool" value="true"/>
   </properties>
  </tile>
  <tile id="3">
   <properties>
    <property name="walkable" type="bool" value="false"/>
   </properties>
  </tile>
 </tileset>
 <layer id="1" name="background" width="200" height="200">
  <data encoding="csv">
{csv_data}
  </data>
 </layer>
</map>"""

    with open("/Users/vdmkenny/rpg2/server/maps/huge_world_map.tmx", "w") as f:
        f.write(tmx_content)

    print("✅ Generated huge_world_map.tmx (200x200 = 40,000 tiles)")
    print("🏗️  Map features:")
    print("   - Safe spawn area around (50,50)")
    print("   - Maze zone (top-left)")
    print("   - Scattered obstacles (top-right)")
    print("   - Dense forest (bottom-left)")
    print("   - Plains with rivers (bottom-right)")
    print("   - Chunk boundaries every 16 tiles")


if __name__ == "__main__":
    write_tmx_file()
