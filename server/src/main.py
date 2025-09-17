"""
Main server entrypoint.
Initializes the FastAPI application and includes the API routers.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Response
from server.src.api import websockets, auth
from server.src.core.logging_config import setup_logging, get_logger
from server.src.core.metrics import init_metrics, get_metrics, get_metrics_content_type
from server.src.services.map_service import get_map_manager

# Initialize logging and metrics as early as possible
setup_logging()
init_metrics()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    logger.info("RPG Server starting up", extra={"version": "0.1.0"})
    
    # Initialize and load all maps asynchronously
    map_manager = get_map_manager()
    await map_manager.load_maps()
    logger.info(f"Loaded {len(map_manager.maps)} maps")
    
    yield
    # Shutdown
    logger.info("RPG Server shutting down")


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
