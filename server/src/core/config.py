import os
import yaml
from pathlib import Path
from typing import Dict, Any, List
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def load_game_config() -> Dict[str, Any]:
    """Load game configuration from config.yml"""
    config_path = Path("/app/server/config.yml")
    if not config_path.exists():
        # Fallback to relative path for development
        config_path = Path("server/config.yml")

    if config_path.exists():
        with open(config_path, "r") as f:
            return yaml.safe_load(f) or {}
    return {}


# Load game config from YAML
game_config = load_game_config()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    # Database settings
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "postgresql+asyncpg://rpg:rpgpassword@db:5432/rpg"
    )
    VALKEY_URL: str = os.getenv("VALKEY_URL", "redis://valkey:6379/0")

    # Authentication settings
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "your_super_secret_key_change_me")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv(
            "ACCESS_TOKEN_EXPIRE_MINUTES",
            str(game_config.get("game", {}).get("auth", {}).get("access_token_expire_minutes", 30))
        )
    )

    # Game settings from config.yml with fallbacks
    GAME_TICK_RATE: float = float(
        os.getenv(
            "GAME_TICK_RATE", str(game_config.get("game", {}).get("tick_rate", 20.0))
        )
    )

    # Movement settings from config.yml with fallbacks
    MOVE_COOLDOWN: float = float(
        os.getenv(
            "MOVE_COOLDOWN",
            str(
                game_config.get("game", {})
                .get("movement", {})
                .get("move_cooldown", 0.15)
            ),
        )
    )
    ANIMATION_DURATION: float = float(
        os.getenv(
            "ANIMATION_DURATION",
            str(
                game_config.get("game", {})
                .get("movement", {})
                .get("animation_duration", 0.3)
            ),
        )
    )

    # Map settings from config.yml with fallbacks
    DEFAULT_MAP: str = game_config.get("game", {}).get("spawn", {}).get("map_id", "samplemap")
    DEFAULT_SPAWN_X: int = int(game_config.get("game", {}).get("spawn", {}).get("x", 25))
    DEFAULT_SPAWN_Y: int = int(game_config.get("game", {}).get("spawn", {}).get("y", 25))
    COLLISION_LAYER_NAMES: List[str] = ["tree", "building", "water", "farm", "obstacles", "collision"]

    # Valkey settings from config.yml
    USE_VALKEY: bool = os.getenv(
        "USE_VALKEY",
        str(game_config.get("server", {}).get("valkey", {}).get("enabled", "true"))
    ).lower() in ("true", "1", "yes", "on")
    VALKEY_HOST: str = os.getenv(
        "VALKEY_HOST",
        game_config.get("server", {}).get("valkey", {}).get("host", "valkey")
    )
    VALKEY_PORT: int = int(
        os.getenv(
            "VALKEY_PORT",
            str(game_config.get("server", {}).get("valkey", {}).get("port", 6379))
        )
    )
    MAPS_DIRECTORY: str = os.getenv("MAPS_DIRECTORY", "/app/server/maps")

    # Logging settings
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    
    # Welcome message settings from config.yml
    WELCOME_MESSAGE: str = game_config.get("game", {}).get("welcome", {}).get(
        "message", "Welcome to RPG Engine, {username}!"
    )
    WELCOME_MOTD: str = game_config.get("game", {}).get("welcome", {}).get(
        "motd", "WebSocket Protocol - Enhanced with correlation IDs and structured responses"
    )

    # Skill settings from config.yml
    SKILL_MAX_LEVEL: int = int(
        game_config.get("game", {}).get("skills", {}).get("max_level", 99)
    )
    SKILL_XP_MULTIPLIERS: Dict[str, float] = game_config.get("game", {}).get(
        "skills", {}
    ).get("xp_multipliers", {})
    SKILL_DEFAULT_XP_MULTIPLIER: float = float(
        game_config.get("game", {}).get("skills", {}).get("default_xp_multiplier", 1.0)
    )

    # Inventory settings from config.yml
    INVENTORY_MAX_SLOTS: int = int(
        game_config.get("game", {}).get("inventory", {}).get("max_slots", 28)
    )

    # Equipment settings from config.yml
    EQUIPMENT_DURABILITY_LOSS_PER_HIT: int = int(
        game_config.get("game", {}).get("equipment", {}).get("durability_loss_per_hit", 1)
    )
    EQUIPMENT_REPAIR_COST_MULTIPLIER: float = float(
        game_config.get("game", {}).get("equipment", {}).get("repair_cost_multiplier", 0.1)
    )

    # Ground items settings from config.yml
    GROUND_ITEMS_DESPAWN_TIMES: Dict[str, int] = game_config.get("game", {}).get(
        "ground_items", {}
    ).get("despawn_times", {
        "poor": 60,
        "common": 120,
        "uncommon": 180,
        "rare": 300,
        "epic": 600,
        "legendary": 900,
    })
    GROUND_ITEMS_LOOT_PROTECTION_TIMES: Dict[str, int] = game_config.get("game", {}).get(
        "ground_items", {}
    ).get("loot_protection_times", {
        "poor": 30,
        "common": 45,
        "uncommon": 60,
        "rare": 90,
        "epic": 120,
        "legendary": 180,
    })
    GROUND_ITEMS_CLEANUP_INTERVAL: int = int(
        game_config.get("game", {}).get("ground_items", {}).get("cleanup_interval", 30)
    )

    # Cache TTL settings from config.yml
    OFFLINE_PLAYER_CACHE_TTL: int = int(
        os.getenv(
            "OFFLINE_PLAYER_CACHE_TTL", 
            str(game_config.get("cache", {}).get("offline_player_ttl_seconds", 1800))
        )
    )

    # Security settings from config.yml
    CHAT_MAX_MESSAGE_LENGTH: int = int(
        os.getenv(
            "CHAT_MAX_MESSAGE_LENGTH",
            str(game_config.get("game", {}).get("security", {}).get("chat_max_message_length", 500))
        )
    )
    INVENTORY_OPERATION_COOLDOWN: float = float(
        os.getenv(
            "INVENTORY_OPERATION_COOLDOWN",
            str(game_config.get("game", {}).get("security", {}).get("inventory_operation_cooldown", 0.1))
        )
    )
    EQUIPMENT_OPERATION_COOLDOWN: float = float(
        os.getenv(
            "EQUIPMENT_OPERATION_COOLDOWN",
            str(game_config.get("game", {}).get("security", {}).get("equipment_operation_cooldown", 0.1))
        )
    )

    # Chat system settings from config.yml
    CHAT_GLOBAL_ENABLED: bool = bool(
        game_config.get("game", {}).get("chat", {}).get("global", {}).get("enabled", True)
    )
    CHAT_GLOBAL_ALLOWED_ROLES: List[str] = game_config.get("game", {}).get(
        "chat", {}
    ).get("global", {}).get("allowed_roles", ["ADMIN", "MODERATOR"])
    
    CHAT_MAX_MESSAGE_LENGTH_LOCAL: int = int(
        game_config.get("game", {}).get("chat", {}).get("max_message_length", {}).get("local", 280)
    )
    CHAT_MAX_MESSAGE_LENGTH_GLOBAL: int = int(
        game_config.get("game", {}).get("chat", {}).get("max_message_length", {}).get("global", 200)
    )
    CHAT_MAX_MESSAGE_LENGTH_DM: int = int(
        game_config.get("game", {}).get("chat", {}).get("max_message_length", {}).get("dm", 500)
    )
    
    CHAT_RATE_LIMIT_LOCAL: float = float(
        game_config.get("game", {}).get("chat", {}).get("rate_limits", {}).get("local", 1.0)
    )
    CHAT_RATE_LIMIT_GLOBAL: float = float(
        game_config.get("game", {}).get("chat", {}).get("rate_limits", {}).get("global", 5.0)
    )
    CHAT_RATE_LIMIT_DM: float = float(
        game_config.get("game", {}).get("chat", {}).get("rate_limits", {}).get("dm", 0.5)
    )
    
    CHAT_LOCAL_CHUNK_RADIUS: int = int(
        game_config.get("game", {}).get("chat", {}).get("local_chunk_radius", 2)
    )

    # HP regeneration settings from config.yml
    HP_REGEN_INTERVAL_TICKS: int = int(
        game_config.get("game", {}).get("hp_regen", {}).get("interval_ticks", 200)
    )

    # Database sync interval (in game ticks)
    # All gameplay data is cached in Valkey and batch-synced to PostgreSQL at this interval
    DB_SYNC_INTERVAL_TICKS: int = int(
        game_config.get("game", {}).get("db_sync_interval_ticks", 200)
    )

    # Death and respawn settings from config.yml
    DEATH_RESPAWN_DELAY: float = float(
        game_config.get("game", {}).get("death", {}).get("respawn_delay", 5.0)
    )

    # Entity AI settings from config.yml
    ENTITY_AI_ENABLED: bool = game_config.get("game", {}).get("entity_ai", {}).get("enabled", True)
    ENTITY_AI_WANDER_INTERVAL: int = int(
        game_config.get("game", {}).get("entity_ai", {}).get("wander_interval_ticks", 40)
    )
    ENTITY_AI_CHASE_INTERVAL: int = int(
        game_config.get("game", {}).get("entity_ai", {}).get("chase_interval_ticks", 10)
    )
    ENTITY_AI_ATTACK_INTERVAL: int = int(
        game_config.get("game", {}).get("entity_ai", {}).get("attack_interval_ticks", 60)
    )
    ENTITY_AI_AGGRO_CHECK_INTERVAL: int = int(
        game_config.get("game", {}).get("entity_ai", {}).get("aggro_check_interval_ticks", 5)
    )
    ENTITY_AI_LOS_TIMEOUT: int = int(
        game_config.get("game", {}).get("entity_ai", {}).get("los_timeout_ticks", 100)
    )
    ENTITY_AI_MAX_PATHFINDING_DISTANCE: int = int(
        game_config.get("game", {}).get("entity_ai", {}).get("max_pathfinding_distance", 50)
    )
    ENTITY_AI_IDLE_MIN: int = int(
        game_config.get("game", {}).get("entity_ai", {}).get("idle_to_wander_min_ticks", 20)
    )
    ENTITY_AI_IDLE_MAX: int = int(
        game_config.get("game", {}).get("entity_ai", {}).get("idle_to_wander_max_ticks", 100)
    )

    # Database settings
    DATABASE_ECHO: bool = os.getenv("DATABASE_ECHO", "").lower() in ("true", "1", "yes")
    
    # Database Connection Pool Settings (for production scalability)
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "20"))
    DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "30")) 
    DB_POOL_TIMEOUT: int = int(os.getenv("DB_POOL_TIMEOUT", "30"))
    DB_POOL_RECYCLE: int = int(os.getenv("DB_POOL_RECYCLE", "3600"))
    DB_POOL_PRE_PING: bool = os.getenv("DB_POOL_PRE_PING", "true").lower() in ("true", "1", "yes")

    # Server capacity settings from config.yml
    MAX_PLAYERS: int = int(
        os.getenv(
            "MAX_PLAYERS",
            str(game_config.get("server", {}).get("capacity", {}).get("max_players", 500))
        )
    )

    @model_validator(mode="after")
    def validate_jwt_secret(self) -> "Settings":
        """Ensure JWT secret is changed from default in non-development environments."""
        default_secret = "your_super_secret_key_change_me"
        if self.ENVIRONMENT != "development" and self.JWT_SECRET_KEY == default_secret:
            raise ValueError(
                "JWT_SECRET_KEY must be changed from default in non-development environments. "
                "Set the JWT_SECRET_KEY environment variable to a secure random value."
            )
        return self


settings = Settings()
