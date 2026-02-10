# Code Review: rpg-engine (common/ and server/)

**Review Date:** 2026-02-10
**Scope:** All Python source files in `common/src/` and `server/src/` (excluding tests and non-text files)
**Method:** Multi-file analysis using AGENTS.md coding standards and GSM architecture patterns

---

## Summary Statistics

| Severity | Count | Description |
|----------|-------|-------------|
| **CRITICAL** | 0 | All 9 critical issues resolved ✅ |
| **HIGH** | 1 | GSM violations remain |
| **MEDIUM** | 11 | In progress |
| **LOW** | 0 | All 12 low issues resolved ✅ |
| **Total** | **12** | 36 issues resolved, 12 remaining |

---

## HIGH (Architecture Violations / Significant Bugs)

### 1. Services Accessing Database Directly (GSM Violations)
**Files:**
- `server/src/services/player_service.py:360` — `logout_player` uses `AsyncSessionLocal()`
- `server/src/services/entity_spawn_service.py:155-167,195-208` — Direct `_valkey` access
- `server/src/services/game_state/reference_data_manager.py:198` — Imports from service layer
**Fix:** All data access must go through GSM managers.

---

## MEDIUM (Code Quality / Maintainability)

### 1. Wrong Error Codes Throughout Handler Mixins
**Files:** All handler mixins in `server/src/api/handlers/`
**Examples:**
- `movement_mixin`: Uses `MOVE_RATE_LIMITED` for offline/system errors
- `chat_mixin`: Uses `CHAT_PERMISSION_DENIED` for system errors
- `inventory_mixin`: Uses `INV_SLOT_EMPTY` for generic failures
- `ground_item_mixin`: Uses `INV_CANNOT_STACK` for position lookup failure
- `equipment_mixin`: Uses `EQ_REQUIREMENTS_NOT_MET` for system errors
- `appearance_mixin`: Uses string literals instead of `ErrorCodes` enum
**Fix:** Use semantically correct error codes from `ErrorCodes` enum.

### 2. `websocket` Parameters Typed as `Any`
**File:** `server/src/api/handlers/base_mixin.py:38` and all mixins
**Description:** Loses all type safety. Should be `WebSocket` type.
**Fix:** Import and use proper WebSocket type hints.

### 3. `_send_error_response` — Dead Parameters
**File:** `server/src/api/handlers/base_mixin.py:63-64`
**Description:** `retry_after` and `suggested_action` are accepted but never used.
**Fix:** Either implement them in payload or remove parameters.

### 4. Magic Numbers for WebSocket State
**Files:** `server/src/api/handlers/base_mixin.py:108,114`, `server/src/api/connection_manager.py:138,232`
**Description:** Raw integers `2` and `3` for WebSocket states.
**Fix:** Use named constants.

### 5. `config.py` — Redundant `os.getenv()` Wrapping
**File:** `server/src/core/config.py`
**Description:** Bypasses pydantic-settings' env var parsing.
**Fix:** Remove `os.getenv()` wrappers, let pydantic handle it.

### 6. Duplicate Config Sources
**Files:**
- `server/src/core/security.py:20-21` — Hardcodes JWT values instead of `settings`
- `server/src/core/skills.py:88` — Hardcodes `MAX_LEVEL = 99`
- `server/src/core/logging_config.py` — Reads env vars directly
**Fix:** Use `settings` as single source of truth.

### 7. Private Attribute Access Across Module Boundaries
**Files:**
- `server/src/services/equipment_service.py:63,107,982` — `item_wrapper._data`
- `server/src/services/ground_item_service.py:363,437,633` — `item_wrapper._data`
- `server/src/services/sprite_registry.py:246-248` — `sprite_registry._available_sprites`
- `server/src/services/entity_spawn_service.py` — `entity_mgr._valkey`
**Fix:** Use public APIs only.

### 8. Unused Imports (Partial List)
**Files:**
- `server/src/api/auth.py` — `SkillService`
- `server/src/api/assets.py` — `os`, `Optional`
- `server/src/api/websockets.py` — `JWTError`, `EquipmentService`, `AuthenticatePayload`
- `server/src/game/game_loop.py` — `AsyncSessionLocal`, `GameUpdateEventPayload`, `GroundItem`
- `server/src/services/inventory_service.py:10-13` — SQLAlchemy imports
**Fix:** Remove all unused imports.

### 9. Entity Instances Fetched N+1 Times Per Tick
**File:** `server/src/game/game_loop.py:953,1032`
**Description:** `entity_mgr.get_map_entities()` called 101 times for 100 players on same map.
**Fix:** Fetch once, reuse for all players.

### 10. Equipment Fetched Per Player Per Tick
**File:** `server/src/game/game_loop.py:926`
**Description:** 10,000 lookups/second at 500 players / 20 TPS.
**Fix:** Cache equipment data and invalidate on change.

### 11. `player.py` Model — Cross-Layer Import
**File:** `server/src/models/player.py:10`
**Description:** Imports `PlayerRole` from `schemas.player`.
**Fix:** Move shared enums to a constants module.

---

*End of active issues. See `code_review_done.md` for resolved issues log.*
