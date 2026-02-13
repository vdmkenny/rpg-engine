#!/usr/bin/env python3
"""
Idylwild Icon Assets Setup Script

Downloads and organizes inventory/ground-item icon assets from Idylwild's
OpenGameArt packs. These are CC0 licensed 32x32 pixel art icons perfect
for inventory and ground item display.

Usage:
    python scripts/setup_idylwild_icons.py

This script will:
1. Download icon packs from OpenGameArt (no git needed)
2. Extract individual .png files (skip sprite sheets and .ase files)
3. Organize into server/icons/idylwild/<pack>/
4. Generate a manifest of all available icons
5. Create attribution and documentation files

The assets are licensed under CC0 (public domain).
Attribution is appreciated but not required.

Packs downloaded:
- Inventory: 50 icons (ores, tools, materials, food, containers)
- Arsenal: 50 icons (swords, daggers, axes, maces, bows, etc.)
- Armory: 50 icons (armor sets, shields, rings, amulets)
- Arcanum: 50 icons (staves, potions, crystals, scrolls)
- Aerial Arsenal: 109 icons (ranged weapons, ammo, explosives)

Source: https://opengameart.org/users/idylwild
"""

import os
import sys
import shutil
import json
import zipfile
import urllib.request
import urllib.error
from pathlib import Path
from typing import List, Dict, Optional, Tuple


# Configuration
PACKS: List[Tuple[str, str, str]] = [
    # (pack_name, download_url, description)
    ("inventory", "https://opengameart.org/sites/default/files/idylwilds_inventory.zip", "Materials, tools, food, containers"),
    ("arsenal", "https://opengameart.org/sites/default/files/idylwilds_arsenal.zip", "Melee weapons and bows"),
    ("armory", "https://opengameart.org/sites/default/files/idylwilds_armory.zip", "Armor, shields, jewelry"),
    ("arcanum", "https://opengameart.org/sites/default/files/idylwilds_arcanum.zip", "Arcane items, staves, potions, scrolls"),
    ("aerial_arsenal", "https://opengameart.org/sites/default/files/idylwilds_aerial_arsenal.zip", "Ranged weapons, ammo, explosives"),
]

# Get project root (parent of scripts directory)
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent
OUTPUT_DIR = PROJECT_ROOT / "server" / "icons"
IDYLWILD_OUTPUT_DIR = OUTPUT_DIR / "idylwild"


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


def download_file(url: str, dest_path: Path) -> bool:
    """Download a file from URL to destination path."""
    print(f"  Downloading from {url}...")
    try:
        urllib.request.urlretrieve(url, dest_path)
        file_size = dest_path.stat().st_size
        print(f"  Downloaded: {file_size:,} bytes")
        return True
    except urllib.error.URLError as e:
        print(f"  ERROR: Failed to download: {e}")
        return False
    except Exception as e:
        print(f"  ERROR: Unexpected error: {e}")
        return False


def extract_icons(zip_path: Path, extract_dir: Path) -> int:
    """
    Extract individual .png icon files from zip.
    
    Skips:
    - .ase files (Aseprite source files)
    - Sprite sheets (files with 'sheet', 'spritesheet', or 'sheet' in name)
    - Any files not ending in .png
    
    Returns:
        Number of icon files extracted
    """
    print(f"  Extracting icons to {extract_dir}...")
    
    extracted_count = 0
    
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        for file_info in zip_ref.infolist():
            filename = file_info.filename
            
            # Skip directories
            if file_info.is_dir():
                continue
            
            # Skip non-png files
            if not filename.lower().endswith('.png'):
                continue
            
            # Skip sprite sheets (usually named with 'sheet', 'spritesheet', 'tilesheet')
            lower_name = filename.lower()
            if any(keyword in lower_name for keyword in ['sheet', 'spritesheet', 'tilesheet', 'preview', 'cover', 'example']):
                print(f"    Skipping sheet: {filename}")
                continue
            
            # Extract this file
            # Get just the filename part (strip any directory structure from the zip)
            base_name = Path(filename).name
            dest_file = extract_dir / base_name
            
            # Read and write the file
            with zip_ref.open(file_info) as src, open(dest_file, 'wb') as dst:
                shutil.copyfileobj(src, dst)
            
            extracted_count += 1
    
    print(f"  Extracted {extracted_count} icon files")
    return extracted_count


def download_and_extract_pack(pack_name: str, url: str, temp_dir: Path) -> Tuple[int, bool]:
    """
    Download and extract a single icon pack.
    
    Returns:
        Tuple of (extracted_count, success)
    """
    print(f"\n  Processing pack: {pack_name}")
    
    # Create temp download path
    zip_path = temp_dir / f"{pack_name}.zip"
    
    # Download
    if not download_file(url, zip_path):
        return 0, False
    
    # Create extraction directory
    extract_dir = IDYLWILD_OUTPUT_DIR / pack_name
    extract_dir.mkdir(parents=True, exist_ok=True)
    
    # Extract
    count = extract_icons(zip_path, extract_dir)
    
    # Clean up zip
    zip_path.unlink()
    
    return count, True


def write_attribution_file() -> None:
    """Write the ATTRIBUTION.md file."""
    content = '''# Idylwild Icon Attribution

These icons are from **Idylwild** on OpenGameArt.org.

## License

All assets in this directory are licensed under **CC0** (Creative Commons Zero).
You are free to share, copy, redistribute, remix, transform, and build upon this
material for any purpose, including commercial use.

**Attribution is appreciated but not required.**

## Artist

- **Idylwild** - https://opengameart.org/users/idylwild
- **Itch.io** - https://idylwild.itch.io/
- **Bluesky** - @idyl-wild.bsky.social

## Packs Included

1. **Idylwild's Inventory** - 50 icons (ores, tools, materials, food, containers)
2. **Idylwild's Arsenal** - 50 icons (swords, daggers, axes, maces, bows, crossbows)
3. **Idylwild's Armory** - 50 icons (armor sets, shields, rings, amulets, cloaks)
4. **Idylwild's Arcanum** - 50 icons (staves, wands, potions, crystals, scrolls)
5. **Idylwild's Aerial Arsenal** - 109 icons (ranged weapons, ammunition, explosives)

Total: 309 unique icon files.

All icons are 32x32 pixels, hand-pixeled by Idylwild.
No AI tools or automation were used in their creation.

## Downloaded From

- https://opengameart.org/content/idylwilds-inventory
- https://opengameart.org/content/idylwilds-arsenal
- https://opengameart.org/content/idylwilds-armory
- https://opengameart.org/content/idylwilds-arcanum
- https://opengameart.org/content/idylwilds-aerial-arsenal
'''
    
    with open(OUTPUT_DIR / "ATTRIBUTION.md", "w") as f:
        f.write(content)
    
    print("  Created ATTRIBUTION.md")


def write_readme() -> None:
    """Write a README for the icons directory."""
    content = '''# Icon Assets

This directory contains 32x32 pixel art icons for inventory and ground item display.

## Idylwild Icons (`idylwild/`)

The `idylwild/` directory contains icons from Idylwild's OpenGameArt packs.
These are downloaded by running:

```bash
python scripts/setup_idylwild_icons.py
```

**Important:** The `idylwild/` directory is git-ignored. You must run the setup
script after cloning the repository.

## License

All icons are licensed under CC0 (public domain).
Attribution is appreciated but not required.
See `ATTRIBUTION.md` for full details.

## Directory Structure

```
icons/
├── ATTRIBUTION.md       # License and attribution info
├── README.md            # This file
├── .gitignore           # Ignore downloaded assets
└── idylwild/            # Downloaded icons (git-ignored)
    ├── inventory/         # Ores, tools, materials, food
    ├── arsenal/          # Melee weapons, bows
    ├── armory/           # Armor, shields, jewelry
    ├── arcanum/          # Staves, potions, crystals, scrolls
    ├── aerial_arsenal/   # Ranged weapons, ammo, explosives
    └── manifest.json     # List of all available icons
```

## Tinting for Variants

Many icons can be tinted client-side to create metal tier variants.
For example, a single "dagger.png" can be tinted to copper (#B87333),
bronze (#CD7F32), iron (#71797E), or steel (#B4C4D0) colors.

See `common/src/sprites/icon_mapping.py` for the mapping of item IDs to
icon paths and tint colors.
'''
    
    with open(OUTPUT_DIR / "README.md", "w") as f:
        f.write(content)
    
    print("  Created README.md")


def write_gitignore() -> None:
    """Write .gitignore for the icons directory."""
    content = '''# Downloaded Idylwild icons - run scripts/setup_idylwild_icons.py to populate
idylwild/

# Keep these tracked
!ATTRIBUTION.md
!README.md
!.gitignore
'''
    
    with open(OUTPUT_DIR / ".gitignore", "w") as f:
        f.write(content)
    
    print("  Created .gitignore")


def generate_manifest() -> int:
    """
    Generate manifest.json listing all available icons.
    
    Returns:
        Number of icons in manifest.
    """
    manifest = {
        "version": "1.0",
        "source": "Idylwild (OpenGameArt)",
        "license": "CC0",
        "icons": [],
    }
    
    for pack_dir in sorted(IDYLWILD_OUTPUT_DIR.iterdir()):
        if pack_dir.is_dir():
            pack_name = pack_dir.name
            for png_file in sorted(pack_dir.glob("*.png")):
                rel_path = png_file.relative_to(IDYLWILD_OUTPUT_DIR)
                manifest["icons"].append({
                    "pack": pack_name,
                    "path": str(rel_path),
                    "filename": png_file.name,
                })
    
    manifest_path = IDYLWILD_OUTPUT_DIR / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    
    count = len(manifest["icons"])
    print(f"  Generated manifest with {count} icons")
    
    return count


def cleanup(temp_dir: Path) -> None:
    """Remove temporary files."""
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
        print("  Removed temporary files")


def main() -> int:
    """
    Main setup function.
    
    Returns:
        0 on success, 1 on failure.
    """
    print_header("Idylwild Icon Setup")
    
    print("This script downloads icon assets from Idylwild's OpenGameArt packs.")
    print("These assets are CC0 licensed (public domain).")
    print("Attribution is appreciated but not required.")
    print()
    print("Packs to download:")
    for name, _, desc in PACKS:
        print(f"  - {name}: {desc}")
    
    total_steps = len(PACKS) + 2  # Download packs + attribution + manifest
    total_icons = 0
    
    # Create temp directory
    temp_dir = PROJECT_ROOT / ".idylwild_temp"
    temp_dir.mkdir(exist_ok=True)
    
    # Clear existing icons
    if IDYLWILD_OUTPUT_DIR.exists():
        print("\n  Removing existing Idylwild icons...")
        shutil.rmtree(IDYLWILD_OUTPUT_DIR)
    
    IDYLWILD_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Download and extract each pack
    for i, (pack_name, url, _) in enumerate(PACKS, 1):
        print_step(i, total_steps, f"Downloading {pack_name}...")
        count, success = download_and_extract_pack(pack_name, url, temp_dir)
        
        if success:
            total_icons += count
        else:
            print(f"  WARNING: Failed to download {pack_name}")
    
    # Write attribution files
    print_step(len(PACKS) + 1, total_steps, "Creating attribution and documentation...")
    write_attribution_file()
    write_readme()
    write_gitignore()
    
    # Generate manifest
    print_step(len(PACKS) + 2, total_steps, "Generating icon manifest...")
    generate_manifest()
    
    # Cleanup
    cleanup(temp_dir)
    
    print_header("Setup Complete!")
    print(f"Icons installed to: {IDYLWILD_OUTPUT_DIR}")
    print(f"Total icons: {total_icons}")
    print()
    print("Next steps:")
    print("  1. Review ATTRIBUTION.md for license information")
    print("  2. Start your server - icons will be served via /api/icons/")
    print("  3. Check common/src/sprites/icon_mapping.py for icon mappings")
    print()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
