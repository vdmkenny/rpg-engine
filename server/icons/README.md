# Icon Assets

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
