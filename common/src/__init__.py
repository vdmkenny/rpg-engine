"""Common protocol definitions shared between client and server."""

from .protocol import (
    # Core message structure
    WSMessage,
    MessageType,
    # Enums
    ErrorCodes,
    ErrorCategory,
    Direction,
    ChatChannel,
    # Command payloads
    AuthenticatePayload,
    MovePayload,
    ChatSendPayload,
    InventoryMovePayload,
    InventorySortPayload,
    ItemDropPayload,
    ItemPickupPayload,
    ItemEquipPayload,
    ItemUnequipPayload,
    AttackPayload,
    ToggleAutoRetaliatePayload,
    AppearanceUpdatePayload,
    AdminGivePayload,
    # Query payloads
    InventoryQueryPayload,
    EquipmentQueryPayload,
    StatsQueryPayload,
    MapChunksQueryPayload,
    # Response payloads
    SuccessResponsePayload,
    ErrorResponsePayload,
    DataResponsePayload,
    # Event payloads
    WelcomeEventPayload,
    StateUpdateEventPayload,
    GameUpdateEventPayload,
    ChatMessageEventPayload,
    PlayerJoinedEventPayload,
    PlayerLeftEventPayload,
    ServerShutdownEventPayload,
    CombatActionEventPayload,
    AppearanceUpdateEventPayload,
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

__version__ = "2.0"