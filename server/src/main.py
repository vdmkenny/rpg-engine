"""
Main server entrypoint.
Initializes the FastAPI application and includes the API routers.
"""

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response
import msgpack
from server.src.api import websockets, auth, assets
from server.src.core.logging_config import setup_logging, get_logger
from server.src.core.metrics import init_metrics, get_metrics, get_metrics_content_type
from server.src.services.map_service import get_map_manager
from server.src.core.database import get_valkey, AsyncSessionLocal
from server.src.game.game_loop import game_loop, cleanup_disconnected_player
from server.src.services.ground_item_service import GroundItemService
from common.src.protocol import MessageType, GameMessage, ServerShutdownPayload

# Initialize logging and metrics as early as possible
setup_logging()
init_metrics()
logger = get_logger(__name__)

# Game loop task reference for cleanup
_game_loop_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global _game_loop_task
    
    # Startup
    logger.info("RPG Server starting up", extra={"version": "0.1.0"})
    
    # Initialize and load all maps asynchronously
    map_manager = get_map_manager()
    await map_manager.load_maps()
    logger.info(f"Loaded {len(map_manager.maps)} maps")
    
    # Initialize Valkey connection and start game loop
    valkey = await get_valkey()
    
    # Load ground items from database to Valkey
    try:
        async with AsyncSessionLocal() as db:
            ground_items_loaded = await GroundItemService.load_ground_items_to_valkey(db, valkey)
            logger.info(f"Loaded {ground_items_loaded} ground items from database to Valkey")
    except Exception as e:
        logger.warning(f"Could not load ground items from database: {e}")
    
    _game_loop_task = asyncio.create_task(
        game_loop(websockets.manager, valkey),
        name="game_loop"
    )
    logger.info("Game loop started", extra={"tick_rate": "20 TPS"})
    
    yield
    
    # Shutdown
    logger.info("RPG Server shutting down")
    
    # Broadcast SERVER_SHUTDOWN to all connected clients
    shutdown_message = GameMessage(
        type=MessageType.SERVER_SHUTDOWN,
        payload=ServerShutdownPayload(
            reason="Server shutting down",
            reconnect_seconds=30,
        ).model_dump(),
    )
    packed_shutdown = msgpack.packb(shutdown_message.model_dump(), use_bin_type=True)
    
    # Send to all connected clients
    for map_connections in websockets.manager.connections_by_map.values():
        for ws in map_connections.values():
            try:
                await ws.send_bytes(packed_shutdown)
            except Exception:
                pass  # Client may already be disconnected
    
    logger.info("Sent SERVER_SHUTDOWN to all clients")
    
    # Sync ground items from Valkey to database before shutdown
    try:
        async with AsyncSessionLocal() as db:
            synced = await GroundItemService.sync_valkey_to_database(db, valkey)
            logger.info(f"Synced {synced} ground items to database")
    except Exception as e:
        logger.warning(f"Could not sync ground items to database: {e}")
    
    # Cancel game loop
    if _game_loop_task:
        _game_loop_task.cancel()
        try:
            await _game_loop_task
        except asyncio.CancelledError:
            logger.info("Game loop stopped")


# OpenAPI Documentation for WebSockets is not directly supported in the same way as HTTP endpoints.
# A common practice is to describe the WebSocket endpoint in the main app description.
app_description = """
The main server for the 2D RPG game.

## Features
- **Authentication**: REST endpoints for player registration and login.
- **Real-time Communication**: A WebSocket endpoint at `/ws` for gameplay.

### WebSocket Protocol (`/ws`)
- **Transport**: `msgpack` for efficient serialization.
- **Handshake**:
    1. Client connects to `/ws`.
    2. Client sends a binary `msgpack` message containing an auth token.
    3. Server validates the token and sends a `WELCOME` message.
- **Communication**: All subsequent messages follow the `GameMessage` schema defined in the `common` package.
"""

app = FastAPI(
    title="RPG Server", description=app_description, version="0.1.0", lifespan=lifespan
)


@app.get("/metrics", summary="Prometheus metrics endpoint", tags=["Monitoring"])
def get_metrics_endpoint():
    """
    Prometheus metrics endpoint.
    Returns server metrics in Prometheus format for monitoring and alerting.
    """
    logger.debug("Metrics endpoint accessed")
    return Response(content=get_metrics(), media_type=get_metrics_content_type())


@app.get("/", summary="Health check endpoint", tags=["Status"])
def read_root():
    """Root endpoint for health checks."""
    logger.debug("Health check endpoint accessed")
    return {"status": "ok"}


@app.get("/version", summary="Get server version", tags=["Status"])
def read_version():
    """Returns the current version of the server application."""
    logger.debug("Version endpoint accessed")
    return {"version": "0.1.0"}


# Include API routers
app.include_router(websockets.router)
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(assets.router, prefix="/api", tags=["Assets"])
