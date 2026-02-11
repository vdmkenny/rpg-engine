"""
Main entry point for the RPG client.

Initializes logging and starts the client.
"""

import asyncio

from .client import Client
from .logging_config import setup_logging
from .config import get_config


def main():
    """Main entry point."""
    # Setup logging first
    setup_logging()
    
    # Log startup info
    config = get_config()
    print(f"RPG Client v2.0")
    print(f"Server: {config.server.host}:{config.server.port}")
    print(f"Display: {config.display.width}x{config.display.height}")
    
    # Create and run client
    try:
        client = Client()
        asyncio.run(client.run())
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
