#!/usr/bin/env python3
"""
LPC Sprite Setup Script

Downloads and organizes LPC (Liberated Pixel Cup) sprite assets from the
Universal LPC Spritesheet Character Generator repository.

Usage:
    python scripts/setup_lpc_sprites.py

This script will:
1. Clone the LPC repository (shallow clone for speed)
2. Copy sprite assets to server/sprites/lpc/
3. Copy attribution files (CREDITS.csv, licenses)
4. Generate a manifest of available sprites

The assets are licensed under CC-BY-SA 3.0, OGA-BY 3.0, and GPL 3.0.
You MUST credit the original artists when using these sprites.
See server/sprites/CREDITS.csv for full attribution.

For more information about LPC:
- https://lpc.opengameart.org/
- https://github.com/LiberatedPixelCup/Universal-LPC-Spritesheet-Character-Generator
"""

import os
import sys
import shutil
import subprocess
import json
from pathlib import Path
from typing import List, Optional


# Configuration
LPC_REPO_URL = "https://github.com/LiberatedPixelCup/Universal-LPC-Spritesheet-Character-Generator.git"
TEMP_CLONE_DIR = ".lpc_temp"

# Get project root (parent of scripts directory)
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent
OUTPUT_DIR = PROJECT_ROOT / "server" / "sprites"
LPC_OUTPUT_DIR = OUTPUT_DIR / "lpc"


def print_header(text: str) -> None:
    """Print a formatted header."""
    print()
    print("=" * 60)
    print(f"  {text}")
    print("=" * 60)
    print()


def print_step(step: int, total: int, text: str) -> None:
    """Print a step indicator."""
    print(f"[{step}/{total}] {text}")


def check_git() -> bool:
    """Check if git is available."""
    try:
        subprocess.run(
            ["git", "--version"],
            check=True,
            capture_output=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def clone_repository() -> bool:
    """Clone the LPC repository (shallow clone for speed)."""
    temp_path = PROJECT_ROOT / TEMP_CLONE_DIR
    
    # Remove existing temp directory
    if temp_path.exists():
        print("  Removing existing temp directory...")
        shutil.rmtree(temp_path)
    
    print("  Cloning LPC repository (this may take a minute)...")
    try:
        subprocess.run(
            [
                "git", "clone",
                "--depth", "1",  # Shallow clone
                "--single-branch",
                LPC_REPO_URL,
                str(temp_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ERROR: Failed to clone repository: {e.stderr}")
        return False


def organize_assets() -> int:
    """
    Copy and organize assets from cloned repo.
    
    Returns:
        Number of sprite files copied.
    """
    temp_path = PROJECT_ROOT / TEMP_CLONE_DIR
    source_dir = temp_path / "spritesheets"
    
    if not source_dir.exists():
        print(f"  ERROR: Source directory not found: {source_dir}")
        return 0
    
    # Clear existing LPC assets
    if LPC_OUTPUT_DIR.exists():
        print("  Removing existing LPC assets...")
        shutil.rmtree(LPC_OUTPUT_DIR)
    
    print("  Copying sprite assets...")
    LPC_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Copy entire spritesheets directory, preserving structure
    shutil.copytree(source_dir, LPC_OUTPUT_DIR, dirs_exist_ok=True)
    
    # Count files
    png_count = len(list(LPC_OUTPUT_DIR.rglob("*.png")))
    print(f"  Copied {png_count} sprite files")
    
    return png_count


def copy_license_files() -> None:
    """Copy credits and license files."""
    temp_path = PROJECT_ROOT / TEMP_CLONE_DIR
    
    files_to_copy = [
        ("CREDITS.csv", "CREDITS.csv"),
        ("cc-by-sa-3_0.txt", "LICENSE-CC-BY-SA-3.0"),
        ("gpl-3_0.txt", "LICENSE-GPL-3.0"),
    ]
    
    for source_name, dest_name in files_to_copy:
        source = temp_path / source_name
        dest = OUTPUT_DIR / dest_name
        
        if source.exists():
            shutil.copy(source, dest)
            print(f"  Copied {dest_name}")
        else:
            print(f"  WARNING: {source_name} not found in repository")


def write_attribution_file() -> None:
    """Write the ATTRIBUTION.md file."""
    content = '''# LPC Sprite Attribution

These sprites are from the **Liberated Pixel Cup** project.

## License

The sprites in the `lpc/` directory are licensed under multiple open licenses:
- **CC-BY-SA 3.0** (Creative Commons Attribution-ShareAlike)
- **OGA-BY 3.0** (OpenGameArt Attribution)
- **GPL 3.0** (GNU General Public License)

## Attribution Requirements

**You MUST credit the original artists when using these sprites.**

See `CREDITS.csv` for detailed attribution by file.

### Quick Attribution (for Credits Screen)

```
Sprites by: Johannes Sjölund (wulax), Michael Whitlock (bigbeargames), 
Matthew Krohn (makrohn), Nila122, David Conway Jr. (JaidynReiman), 
Carlo Enrico Victoria (Nemisys), Thane Brimhall (pennomi), laetissima, 
bluecarrot16, Luke Mehl, Benjamin K. Smith (BenCreating), MuffinElZangano, 
Durrani, kheftel, Stephen Challener (Redshrike), William.Thompsonj, 
Marcel van de Steeg (MadMarcel), TheraHedwig, Evert, Pierre Vigier (pvigier), 
Eliza Wyatt (ElizaWy), Sander Frenken (castelonia), dalonedrau, 
Lanea Zimmerman (Sharm), Manuel Riecke (MrBeast), Barbara Riviera, 
Joe White, Mandi Paugh, and many others.

Sprites contributed as part of the Liberated Pixel Cup project from 
OpenGameArt.org: http://opengameart.org/content/lpc-collection

Licenses: 
- CC-BY-SA 3.0: http://creativecommons.org/licenses/by-sa/3.0/
- OGA-BY 3.0: https://static.opengameart.org/OGA-BY-3.0.txt
- GPL 3.0: https://www.gnu.org/licenses/gpl-3.0.html

See CREDITS.csv for detailed per-file attribution.
```

## Source

Downloaded from: https://github.com/LiberatedPixelCup/Universal-LPC-Spritesheet-Character-Generator

For the full project and online generator:
https://liberatedpixelcup.github.io/Universal-LPC-Spritesheet-Character-Generator/

## About LPC

The Liberated Pixel Cup was a competition sponsored by Creative Commons, 
Mozilla, the Free Software Foundation, and OpenGameArt.org to create a 
body of free culture artwork for games.

For more information: https://lpc.opengameart.org/
'''
    
    with open(OUTPUT_DIR / "ATTRIBUTION.md", "w") as f:
        f.write(content)
    
    print("  Created ATTRIBUTION.md")


def write_readme() -> None:
    """Write a README for the sprites directory."""
    content = '''# Sprite Assets

This directory contains sprite assets for character rendering.

## LPC Sprites (`lpc/`)

The `lpc/` directory contains sprites from the Liberated Pixel Cup project.
These are downloaded by running:

```bash
python scripts/setup_lpc_sprites.py
```

**Important:** The `lpc/` directory is git-ignored. You must run the setup
script after cloning the repository.

See `ATTRIBUTION.md` for license and attribution requirements.

## Directory Structure

```
sprites/
├── ATTRIBUTION.md       # License and attribution info
├── CREDITS.csv          # Detailed per-file credits
├── LICENSE-CC-BY-SA-3.0 # CC-BY-SA license text
├── LICENSE-GPL-3.0      # GPL license text
├── README.md            # This file
└── lpc/                 # Downloaded LPC sprites (git-ignored)
    ├── body/            # Body sprites by type and skin tone
    ├── head/            # Head sprites by race and skin tone
    ├── hair/            # Hair styles and colors
    ├── eyes/            # Eye sprites
    ├── beards/          # Facial hair
    ├── equipment/       # Armor, weapons, etc.
    └── manifest.json    # List of all available sprites
```
'''
    
    with open(OUTPUT_DIR / "README.md", "w") as f:
        f.write(content)
    
    print("  Created README.md")


def generate_manifest() -> int:
    """
    Generate manifest.json listing all available sprites.
    
    Returns:
        Number of sprites in manifest.
    """
    manifest = {
        "version": "1.0",
        "source": "LiberatedPixelCup/Universal-LPC-Spritesheet-Character-Generator",
        "sprites": [],
    }
    
    for png_file in sorted(LPC_OUTPUT_DIR.rglob("*.png")):
        rel_path = png_file.relative_to(LPC_OUTPUT_DIR)
        manifest["sprites"].append(str(rel_path))
    
    manifest_path = LPC_OUTPUT_DIR / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    
    count = len(manifest["sprites"])
    print(f"  Generated manifest with {count} sprites")
    
    return count


def write_gitignore() -> None:
    """Write .gitignore for the sprites directory."""
    content = '''# Downloaded LPC assets - run scripts/setup_lpc_sprites.py to populate
lpc/

# Keep these tracked
!CREDITS.csv
!LICENSE-*
!ATTRIBUTION.md
!README.md
!.gitignore
'''
    
    with open(OUTPUT_DIR / ".gitignore", "w") as f:
        f.write(content)
    
    print("  Created .gitignore")


def cleanup() -> None:
    """Remove temporary files."""
    temp_path = PROJECT_ROOT / TEMP_CLONE_DIR
    if temp_path.exists():
        shutil.rmtree(temp_path)
        print("  Removed temporary files")


def main() -> int:
    """
    Main setup function.
    
    Returns:
        0 on success, 1 on failure.
    """
    print_header("LPC Sprite Setup")
    
    print("This script downloads sprite assets from the Liberated Pixel Cup")
    print("project. These assets are licensed under open licenses including")
    print("CC-BY-SA 3.0, OGA-BY 3.0, and GPL 3.0.")
    print()
    print("You MUST credit the original authors when using these sprites.")
    print("See server/sprites/CREDITS.csv for full attribution details.")
    
    total_steps = 6
    
    # Step 1: Check prerequisites
    print_step(1, total_steps, "Checking prerequisites...")
    if not check_git():
        print("  ERROR: git is required but not found in PATH")
        return 1
    print("  git is available")
    
    # Step 2: Clone the repository
    print_step(2, total_steps, "Downloading LPC repository...")
    if not clone_repository():
        cleanup()
        return 1
    
    # Step 3: Copy assets
    print_step(3, total_steps, "Organizing sprite assets...")
    sprite_count = organize_assets()
    if sprite_count == 0:
        cleanup()
        return 1
    
    # Step 4: Copy license files
    print_step(4, total_steps, "Copying license and attribution files...")
    copy_license_files()
    write_attribution_file()
    write_readme()
    write_gitignore()
    
    # Step 5: Generate manifest
    print_step(5, total_steps, "Generating sprite manifest...")
    generate_manifest()
    
    # Step 6: Cleanup
    print_step(6, total_steps, "Cleaning up...")
    cleanup()
    
    print_header("Setup Complete!")
    print(f"Sprites installed to: {LPC_OUTPUT_DIR}")
    print(f"Total sprites: {sprite_count}")
    print()
    print("Next steps:")
    print("  1. Review ATTRIBUTION.md for license requirements")
    print("  2. Ensure your game credits the LPC artists")
    print("  3. Start your server - sprites will be served via /api/sprites/")
    print()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
