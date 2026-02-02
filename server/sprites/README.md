# Sprite Assets

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
