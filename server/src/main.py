"""
Main server entrypoint.
Initializes the FastAPI application and includes the API routers.
"""

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response
import msgpack
from server.src.api import websockets, auth, assets, appearance
from server.src.core.logging_config import setup_logging, get_logger
from server.src.core.config import settings
from server.src.core.metrics import init_metrics, get_metrics, get_metrics_content_type, metrics
from server.src.services.map_service import get_map_manager
from server.src.core.database import get_valkey, AsyncSessionLocal
from server.src.game.game_loop import game_loop, cleanup_disconnected_player
from server.src.services.game_state import (
    init_all_managers,
    get_reference_data_manager,
    get_entity_manager,
    get_ground_item_manager,
    get_batch_sync_coordinator,
)
from server.src.core.concurrency import initialize_concurrency_infrastructure
from common.src.protocol import MessageType, WSMessage

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
    logger.info("Maps loaded", extra={"map_count": len(map_manager.maps)})
    
    # Initialize Valkey connection
    valkey = await get_valkey()
    
    # Initialize all game state managers
    init_all_managers(valkey, AsyncSessionLocal)
    ref_manager = get_reference_data_manager()
    entity_mgr = get_entity_manager()
    ground_item_mgr = get_ground_item_manager()
    
    # Initialize concurrency infrastructure with Valkey client
    initialize_concurrency_infrastructure(valkey)
    
    # Sync items to database and load item cache for reference data
    try:
        # Ensure all ItemType entries exist in database
        from server.src.services.item_service import ItemService
        await ItemService.sync_items_to_db()
        
        # Load item metadata cache (permanent cache for reference data)
        items_cached = await ref_manager.load_item_cache_from_db()
        logger.info("Items cached", extra={"item_count": items_cached})
    except Exception as e:
        logger.warning("Could not load item cache", extra={"error": str(e)})
        
    # Sync entities to database (mirroring code definitions)
    try:
        from server.src.services.entity_service import EntityService
        await EntityService.sync_entities_to_db()
        logger.info("Entities synced to database")
    except Exception as e:
        logger.warning("Could not sync entities to database", extra={"error": str(e)})
    
    # Clear stale entity instances and spawn entities from Tiled maps
    try:
        # Clear any stale entity instances from previous server run
        await entity_mgr.clear_all_entity_instances()
        logger.info("Cleared stale entity instances from Valkey")
        
        # Spawn entities for all loaded maps
        from server.src.services.entity_spawn_service import EntitySpawnService
        from server.src.services.game_state import get_player_state_manager
        total_spawned = 0
        player_mgr = get_player_state_manager()
        for map_id in map_manager.maps.keys():
            spawned = await EntitySpawnService.spawn_map_entities(player_mgr, entity_mgr, map_id)
            total_spawned += spawned
        
        logger.info("Entities spawned", extra={"entity_count": total_spawned})
    except Exception as e:
        logger.warning("Could not spawn entity instances", extra={"error": str(e)})
    
    # Load ground items from database to Valkey
    try:
        ground_items_loaded = await ground_item_mgr.load_ground_items_from_db()
        logger.info("Ground items loaded", extra={"item_count": ground_items_loaded})
    except Exception as e:
        logger.warning("Could not load ground items from database", extra={"error": str(e)})
    
    # Start game loop
    _game_loop_task = asyncio.create_task(
        game_loop(websockets.manager, valkey),
        name="game_loop"
    )
    logger.info("Game loop started", extra={"tick_rate": "20 TPS"})
    
    yield
    
    # Shutdown
    logger.info("RPG Server shutting down")
    
    # Broadcast SERVER_SHUTDOWN to all connected clients
    shutdown_message = WSMessage(
        id=None,  # No correlation ID needed for broadcast events
        type=MessageType.EVENT_SERVER_SHUTDOWN,
        payload={
            "message": "Server shutting down",
            "countdown_seconds": 30,
        },
        version="2.0"
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
    
    # Sync all active player state to database before shutdown using GSM
    try:
        # Build map of active players from the connection manager
        active_players = {}
        for map_id, map_connections in websockets.manager.connections_by_map.items():
            for username in map_connections.keys():
                from .services.connection_service import ConnectionService
                player_id = await ConnectionService.get_online_player_id_by_username(username)
                if player_id:
                    active_players[username] = player_id
        
        # Sync all active players before shutdown
        if active_players:
            sync_coordinator = get_batch_sync_coordinator()
            await sync_coordinator.sync_all_on_shutdown()
            logger.info("Players synced on shutdown", extra={"player_count": len(active_players)})
    except Exception as e:
        logger.error("Error syncing players on shutdown", extra={"error": str(e)}, exc_info=True)
    
    # Sync ground items from Valkey to database before shutdown
    try:
        async with AsyncSessionLocal() as db:
            await ground_item_mgr.sync_ground_items_to_db(db)
            await db.commit()
        logger.info("Synced ground items to database")
    except Exception as e:
        logger.warning("Could not sync ground items to database", extra={"error": str(e)})
    
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
- **Transport**: `msgpack` for efficient serialization with correlation ID support.
- **Features**: 
    - Unified request/response patterns with correlation IDs
    - Structured error codes and handling
    - Enhanced state update system with broadcasting targets
    - Rate limiting with per-operation cooldowns
- **Handshake**:
    1. Client connects to `/ws`.
    2. Client sends a binary `msgpack` message with `CMD_AUTHENTICATE` type.
    3. Server responds with `RESP_SUCCESS` or `RESP_ERROR`.
    4. Server sends `EVENT_WELCOME` on successful authentication.
- **Communication**: All messages follow the `WSMessage` envelope with correlation ID support.
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


@app.get("/status", summary="Get server status and capacity", tags=["Status"])
async def get_server_status():
    """
    Returns server status including capacity information.
    Shows real player count even if over maximum capacity (admin overrides).
    """
    logger.debug("Status endpoint accessed")
    
    from server.src.services.game_state import get_player_state_manager
    player_mgr = get_player_state_manager()
    current_players = await player_mgr.get_active_player_count()
    max_players = settings.MAX_PLAYERS
    
    # Update Prometheus metrics
    metrics.update_server_capacity_metrics(current_players, max_players)
    
    # Calculate capacity metrics
    over_capacity = current_players > max_players
    utilization_percent = (current_players / max_players * 100) if max_players > 0 else 0
    available_slots = max(0, max_players - current_players)
    admin_overrides_active = max(0, current_players - max_players) if over_capacity else 0
    
    return {
        "status": "ok",
        "motd": settings.WELCOME_MOTD,
        "capacity": {
            "max_players": max_players,
            "current_players": current_players,
            "available_slots": available_slots,
            "over_capacity": over_capacity,
            "utilization_percent": round(utilization_percent, 1),
            "admin_overrides_active": admin_overrides_active
        },
        "performance": {
            # TODO: Add actual performance metrics here later
            "avg_tick_time_ms": None
        }
    }


# Include API routers
app.include_router(websockets.router)
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(assets.router, prefix="/api", tags=["Assets"])
app.include_router(appearance.router, prefix="/api", tags=["Appearance"])
