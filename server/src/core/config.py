import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List
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
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
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

    # Valkey settings
    VALKEY_HOST: str = "valkey"
    VALKEY_PORT: int = 6379
    MAPS_DIRECTORY: str = os.getenv("MAPS_DIRECTORY", "/app/server/maps")

    # Logging settings
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

    # Database settings
    DATABASE_ECHO: bool = os.getenv("DATABASE_ECHO", "").lower() in ("true", "1", "yes")

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
