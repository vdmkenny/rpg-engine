#!/usr/bin/env python3
"""
Main entry point for the refactored RPG client.
"""

import asyncio
from rpg_client import main

if __name__ == "__main__":
    asyncio.run(main())