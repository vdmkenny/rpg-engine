"""
Prometheus metrics configuration for the RPG server.

This module provides comprehensive metrics collection for monitoring
server performance, game activity, and user behavior.
"""

from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    Info,
    CollectorRegistry,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from typing import Dict, Any, Optional
import time
import functools
from server.src.core.logging_config import get_logger

logger = get_logger(__name__)

# Create a custom registry for our metrics
REGISTRY = CollectorRegistry()

# =============================================================================
# APPLICATION INFO METRICS
# =============================================================================

app_info = Info(
    "rpg_server_info", "RPG Server application information", registry=REGISTRY
)

# =============================================================================
# HTTP/API METRICS
# =============================================================================

http_requests_total = Counter(
    "rpg_http_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "status_code"],
    registry=REGISTRY,
)

http_request_duration_seconds = Histogram(
    "rpg_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    registry=REGISTRY,
)

# =============================================================================
# AUTHENTICATION METRICS
# =============================================================================

auth_attempts_total = Counter(
    "rpg_auth_attempts_total",
    "Total number of authentication attempts",
    ["endpoint", "status"],
    registry=REGISTRY,
)

auth_tokens_issued_total = Counter(
    "rpg_auth_tokens_issued_total",
    "Total number of authentication tokens issued",
    registry=REGISTRY,
)

auth_failures_total = Counter(
    "rpg_auth_failures_total",
    "Total number of authentication failures",
    ["reason"],
    registry=REGISTRY,
)

# =============================================================================
# WEBSOCKET METRICS
# =============================================================================

websocket_connections_total = Counter(
    "rpg_websocket_connections_total",
    "Total number of WebSocket connections",
    ["status"],
    registry=REGISTRY,
)

websocket_connections_active = Gauge(
    "rpg_websocket_connections_active",
    "Current number of active WebSocket connections",
    registry=REGISTRY,
)

websocket_messages_total = Counter(
    "rpg_websocket_messages_total",
    "Total number of WebSocket messages",
    ["type", "direction"],
    registry=REGISTRY,
)

websocket_connection_duration_seconds = Histogram(
    "rpg_websocket_connection_duration_seconds",
    "WebSocket connection duration in seconds",
    registry=REGISTRY,
)

# =============================================================================
# GAME METRICS
# =============================================================================

players_registered_total = Counter(
    "rpg_players_registered_total",
    "Total number of players registered",
    registry=REGISTRY,
)

players_online = Gauge(
    "rpg_players_online", "Current number of players online", registry=REGISTRY
)

players_by_map = Gauge(
    "rpg_players_by_map", "Number of players on each map", ["map_id"], registry=REGISTRY
)

player_movements_total = Counter(
    "rpg_player_movements_total",
    "Total number of player movements",
    ["direction"],
    registry=REGISTRY,
)

game_loop_iterations_total = Counter(
    "rpg_game_loop_iterations_total",
    "Total number of game loop iterations",
    registry=REGISTRY,
)

game_loop_duration_seconds = Histogram(
    "rpg_game_loop_duration_seconds",
    "Game loop iteration duration in seconds",
    registry=REGISTRY,
)

game_state_broadcasts_total = Counter(
    "rpg_game_state_broadcasts_total",
    "Total number of game state broadcasts",
    ["map_id"],
    registry=REGISTRY,
)

# =============================================================================
# DATABASE METRICS
# =============================================================================

database_operations_total = Counter(
    "rpg_database_operations_total",
    "Total number of database operations",
    ["operation", "table"],
    registry=REGISTRY,
)

database_operation_duration_seconds = Histogram(
    "rpg_database_operation_duration_seconds",
    "Database operation duration in seconds",
    ["operation", "table"],
    registry=REGISTRY,
)

database_connections_active = Gauge(
    "rpg_database_connections_active",
    "Current number of active database connections",
    registry=REGISTRY,
)

# =============================================================================
# CACHE/REDIS METRICS
# =============================================================================

cache_operations_total = Counter(
    "rpg_cache_operations_total",
    "Total number of cache operations",
    ["operation", "key_type"],
    registry=REGISTRY,
)

cache_operation_duration_seconds = Histogram(
    "rpg_cache_operation_duration_seconds",
    "Cache operation duration in seconds",
    ["operation", "key_type"],
    registry=REGISTRY,
)

cache_hits_total = Counter(
    "rpg_cache_hits_total",
    "Total number of cache hits",
    ["key_type"],
    registry=REGISTRY,
)

cache_misses_total = Counter(
    "rpg_cache_misses_total",
    "Total number of cache misses",
    ["key_type"],
    registry=REGISTRY,
)

# =============================================================================
# ERROR METRICS
# =============================================================================

errors_total = Counter(
    "rpg_errors_total",
    "Total number of errors",
    ["component", "error_type"],
    registry=REGISTRY,
)

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def init_metrics():
    """Initialize metrics with application information."""
    app_info.info(
        {
            "version": "0.1.0",
            "service": "rpg-server",
            "environment": "development",  # This could come from config
        }
    )
    logger.info("Prometheus metrics initialized")


def get_metrics() -> str:
    """Get current metrics in Prometheus format."""
    return generate_latest(REGISTRY)


def get_metrics_content_type() -> str:
    """Get the content type for Prometheus metrics."""
    return CONTENT_TYPE_LATEST


# =============================================================================
# DECORATORS FOR AUTOMATIC METRICS
# =============================================================================


def track_time(metric: Histogram, labels: Optional[Dict[str, str]] = None):
    """Decorator to track execution time of functions."""

    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                if labels:
                    metric.labels(**labels).observe(duration)
                else:
                    metric.observe(duration)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                if labels:
                    metric.labels(**labels).observe(duration)
                else:
                    metric.observe(duration)

        # Return appropriate wrapper based on function type
        if hasattr(func, "__code__") and func.__code__.co_flags & 0x80:  # CO_COROUTINE
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def count_calls(metric: Counter, labels: Optional[Dict[str, str]] = None):
    """Decorator to count function calls."""

    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                result = await func(*args, **kwargs)
                if labels:
                    metric.labels(**labels).inc()
                else:
                    metric.inc()
                return result
            except Exception as e:
                if labels:
                    error_labels = {**labels, "status": "error"}
                    metric.labels(**error_labels).inc()
                else:
                    metric.inc()
                raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                if labels:
                    metric.labels(**labels).inc()
                else:
                    metric.inc()
                return result
            except Exception as e:
                if labels:
                    error_labels = {**labels, "status": "error"}
                    metric.labels(**error_labels).inc()
                else:
                    metric.inc()
                raise

        # Return appropriate wrapper based on function type
        if hasattr(func, "__code__") and func.__code__.co_flags & 0x80:  # CO_COROUTINE
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


# =============================================================================
# HELPER FUNCTIONS FOR MANUAL METRICS
# =============================================================================


class MetricsHelper:
    """Helper class for manual metrics tracking."""

    @staticmethod
    def track_websocket_connection(status: str):
        """Track WebSocket connection events."""
        websocket_connections_total.labels(status=status).inc()

    @staticmethod
    def set_active_connections(count: int):
        """Set the current number of active WebSocket connections."""
        websocket_connections_active.set(count)

    @staticmethod
    def track_websocket_message(message_type: str, direction: str):
        """Track WebSocket message events."""
        websocket_messages_total.labels(type=message_type, direction=direction).inc()

    @staticmethod
    def track_player_movement(direction: str):
        """Track player movement events."""
        player_movements_total.labels(direction=direction).inc()

    @staticmethod
    def set_players_by_map(map_id: str, count: int):
        """Set the number of players on a specific map."""
        players_by_map.labels(map_id=map_id).set(count)

    @staticmethod
    def track_auth_attempt(endpoint: str, status: str):
        """Track authentication attempts."""
        auth_attempts_total.labels(endpoint=endpoint, status=status).inc()

    @staticmethod
    def track_auth_failure(reason: str):
        """Track authentication failures."""
        auth_failures_total.labels(reason=reason).inc()

    @staticmethod
    def track_database_operation(operation: str, table: str, duration: float):
        """Track database operations."""
        database_operations_total.labels(operation=operation, table=table).inc()
        database_operation_duration_seconds.labels(
            operation=operation, table=table
        ).observe(duration)

    @staticmethod
    def track_cache_operation(
        operation: str, key_type: str, duration: float, hit: Optional[bool] = None
    ):
        """Track cache operations."""
        cache_operations_total.labels(operation=operation, key_type=key_type).inc()
        cache_operation_duration_seconds.labels(
            operation=operation, key_type=key_type
        ).observe(duration)

        if hit is True:
            cache_hits_total.labels(key_type=key_type).inc()
        elif hit is False:
            cache_misses_total.labels(key_type=key_type).inc()

    @staticmethod
    def track_error(component: str, error_type: str):
        """Track application errors."""
        errors_total.labels(component=component, error_type=error_type).inc()


# Global metrics helper instance
metrics = MetricsHelper()
