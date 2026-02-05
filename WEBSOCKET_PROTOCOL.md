# WebSocket Protocol Documentation

> **This document has moved.**
>
> The authoritative WebSocket protocol specification is now at:
> **[docs/WEBSOCKET_PROTOCOL.md](docs/WEBSOCKET_PROTOCOL.md)**
>
> Please update your bookmarks.

---

## Quick Links

- **[Full Protocol Specification](docs/WEBSOCKET_PROTOCOL.md)** - Complete documentation
- **[Quick Reference](docs/WEBSOCKET_QUICK_REFERENCE.md)** - Tables and lookup reference
- **[Examples](docs/WEBSOCKET_EXAMPLES.md)** - Message flow examples

---

## Overview

The RPG Engine WebSocket protocol uses:
- **MessagePack** for binary serialization
- **Correlation IDs** for request-response matching
- **Structured error codes** for consistent error handling
- **Diff-based updates** for efficient game state sync (20 TPS)

See the full documentation in the docs folder for complete specifications.
