"""
Client configuration management.

Loads configuration from client_config.yml with environment variable overrides.
Uses Pydantic for validation and type safety.
"""

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field

DEFAULT_CONFIG_PATH = Path(__file__).parent / "client_config.yml"


class ServerConfig(BaseModel):
    """Server connection settings."""
    host: str = Field(default="localhost", description="Server hostname or IP")
    port: int = Field(default=8000, description="Server HTTP port")
    websocket_path: str = Field(default="/ws", description="WebSocket endpoint path")
    
    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"
    
    @property
    def websocket_url(self) -> str:
        return f"ws://{self.host}:{self.port}{self.websocket_path}"


class DisplayConfig(BaseModel):
    """Display and window settings."""
    width: int = Field(default=1024, description="Window width in pixels")
    height: int = Field(default=768, description="Window height in pixels")
    title: str = Field(default="RPG Engine", description="Window title")
    fps: int = Field(default=60, description="Target frames per second")
    vsync: bool = Field(default=True, description="Enable VSync")
    fullscreen: bool = Field(default=False, description="Start in fullscreen mode")
    

class GameConfig(BaseModel):
    """Game-specific settings."""
    tile_size: int = Field(default=32, description="Size of each tile in pixels")
    chunk_size: int = Field(default=16, description="Chunk size in tiles")
    move_cooldown: float = Field(default=0.15, description="Movement cooldown in seconds")
    move_duration: float = Field(default=0.2, description="Movement animation duration in seconds")
    chunk_request_distance: int = Field(default=8, description="Distance in tiles before requesting new chunks")


class KeyBindings(BaseModel):
    """Keyboard shortcuts configuration."""
    move_up: list[str] = Field(default=["w", "up"], description="Move up keys")
    move_down: list[str] = Field(default=["s", "down"], description="Move down keys")
    move_left: list[str] = Field(default=["a", "left"], description="Move left keys")
    move_right: list[str] = Field(default=["d", "right"], description="Move right keys")
    open_inventory: str = Field(default="i", description="Open inventory panel")
    open_equipment: str = Field(default="e", description="Open equipment panel")
    open_stats: str = Field(default="s", description="Open stats panel")
    toggle_chat: str = Field(default="t", description="Toggle chat input focus")
    hide_chat: str = Field(default="c", description="Toggle chat visibility")
    help: str = Field(default="?", description="Toggle help panel")
    escape: str = Field(default="escape", description="Close panels/cancel")


class DebugConfig(BaseModel):
    """Debug and development settings."""
    enabled: bool = Field(default=False, description="Enable debug mode")
    show_fps: bool = Field(default=True, description="Show FPS counter")
    show_hitboxes: bool = Field(default=False, description="Show entity hitboxes")
    show_chunks: bool = Field(default=False, description="Show chunk boundaries")
    log_level: str = Field(default="INFO", description="Logging level (DEBUG, INFO, WARNING, ERROR)")


class ClientConfig(BaseModel):
    """Complete client configuration."""
    server: ServerConfig = Field(default_factory=ServerConfig)
    display: DisplayConfig = Field(default_factory=DisplayConfig)
    game: GameConfig = Field(default_factory=GameConfig)
    key_bindings: KeyBindings = Field(default_factory=KeyBindings)
    debug: DebugConfig = Field(default_factory=DebugConfig)
    
    @classmethod
    def from_yaml(cls, path: Optional[Path] = None) -> "ClientConfig":
        """Load configuration from YAML file."""
        path = path or DEFAULT_CONFIG_PATH
        
        if not path.exists():
            # Return default configuration
            config = cls()
            config._save_default(path)
            return config
        
        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}
        
        # Apply environment variable overrides
        data = cls._apply_env_overrides(data)
        
        return cls(**data)
    
    @staticmethod
    def _apply_env_overrides(data: dict) -> dict:
        """Apply environment variable overrides to config data."""
        env_mappings = {
            "SERVER_HOST": ("server", "host"),
            "SERVER_PORT": ("server", "port"),
            "DISPLAY_WIDTH": ("display", "width"),
            "DISPLAY_HEIGHT": ("display", "height"),
            "DISPLAY_FULLSCREEN": ("display", "fullscreen"),
            "DEBUG_ENABLED": ("debug", "enabled"),
            "LOG_LEVEL": ("debug", "log_level"),
        }
        
        for env_var, (section, key) in env_mappings.items():
            value = os.environ.get(env_var)
            if value is not None:
                if section not in data:
                    data[section] = {}
                
                # Convert types based on default
                if key in ("port", "width", "height"):
                    data[section][key] = int(value)
                elif key in ("fullscreen", "enabled"):
                    data[section][key] = value.lower() in ("true", "1", "yes")
                else:
                    data[section][key] = value
        
        return data
    
    def _save_default(self, path: Path) -> None:
        """Save default configuration to file."""
        data = self.model_dump()
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def get_config() -> ClientConfig:
    """Get the singleton configuration instance."""
    if not hasattr(get_config, "_instance"):
        get_config._instance = ClientConfig.from_yaml()
    return get_config._instance


def reload_config() -> ClientConfig:
    """Reload configuration from file."""
    get_config._instance = ClientConfig.from_yaml()
    return get_config._instance
