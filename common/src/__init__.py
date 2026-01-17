"""Common protocol definitions shared between client and server."""

from .protocol import (
    # Core message types
    GameMessage,
    MessageType,
    Direction,
    # Movement
    MoveIntentPayload,
    MovementValidator,
    # Game state
    GameStateUpdatePayload,
    # Chunks
    ChunkRequestPayload,
    ChunkData,
    ChunkDataPayload,
    TileData,
    # Authentication
    AuthenticatePayload,
    # Welcome
    PlayerInfo,
    GameConfig,
    WelcomePayload,
    # Chat
    SendChatMessagePayload,
    ChatMessagePayload,
    # Error
    ErrorPayload,
    # Player lifecycle
    PlayerDisconnectPayload,
    ServerShutdownPayload,
    PlayerDiedPayload,
    PlayerRespawnPayload,
    # Inventory
    MoveInventoryItemPayload,
    SortInventoryPayload,
    DropItemPayload,
    # Equipment
    EquipItemPayload,
    UnequipItemPayload,
    # Ground items
    PickupItemPayload,
    # Operation results
    OperationResultPayload,
)

from .constants import (
    # Animation and Timing
    MOVEMENT_ANIMATION_DURATION,
    CLIENT_MOVE_COOLDOWN,
    WEBSOCKET_TIMEOUT,
    ASYNC_SLEEP_SHORT,
    ASYNC_SLEEP_MEDIUM,
    # Game World
    CHUNK_REQUEST_DISTANCE,
    MILLISECONDS_TO_SECONDS,
    # UI and Display
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    TILE_SIZE,
    # Colors
    BLACK,
    WHITE,
    RED,
    GREEN,
    BLUE,
    GRAY,
    DARK_GRAY,
    # Server
    DEFAULT_CHUNK_SIZE,
    SERVER_MOVE_COOLDOWN,
    # Progress and Animation
    ANIMATION_COMPLETE,
    ANIMATION_START,
)

__version__ = "1.0"
