# 2D RPG Server & Client

This repository contains the source code for a Python-based 2D RPG, featuring a scalable server and a thin client.

## Project Overview

- **Server**: Built with FastAPI, using WebSockets for real-time communication and a REST API for authentication and data fetching. It connects to a PostgreSQL database via SQLAlchemy and uses Valkey for caching and handling "hot" data.
- **Client**: A thin client built with Pygame that streams map data and assets from the server.
- **Containerized**: All services (server, client, db, valkey) are containerized with Docker and managed via `docker-compose`.
- **Shared Code**: A `common` directory holds code shared between the client and server, such as the communication protocol.

## Getting Started

### Prerequisites
- Docker
- Docker Compose

### Running the Application
1.  **Clone the repository.**
2.  **Navigate to the `docker` directory:**
    ```bash
    cd rpg-engine/docker
    ```
3.  **Build and run the services:**
    ```bash
    docker-compose up --build
    ```
This command will start the database, valkey cache, server, and a single client instance.

You can monitor the logs for each service in the terminal. To run multiple clients, you can start them in separate terminals or scale the service.

## Project Structure

```
rpg-engine/
├── client/             # Thin client application
│   ├── src/
│   ├── Dockerfile
│   └── requirements.txt
├── common/             # Code shared between client and server
│   └── src/
├── docker/
│   └── docker-compose.yml
├── docs/               # Documentation
│   ├── WEBSOCKET_PROTOCOL.md
│   ├── WEBSOCKET_EXAMPLES.md
│   └── WEBSOCKET_QUICK_REFERENCE.md
├── server/             # Server application
│   ├── src/
│   │   ├── api/        # API endpoints (WebSockets, HTTP)
│   │   ├── core/       # Core logic, config
│   │   ├── models/     # SQLAlchemy models
│   │   ├── schemas/    # Pydantic schemas
│   │   └── services/   # Business logic
│   ├── alembic/        # Alembic migrations
│   ├── alembic.ini
│   ├── Dockerfile
│   └── requirements.txt
└── tests/              # Unit and integration tests
```

## WebSocket Protocol

The RPG Engine uses a comprehensive WebSocket protocol for real-time communication:

- **Protocol Version**: 2.0
- **Serialization**: MessagePack (msgpack)
- **Authentication**: JWT-based
- **Features**: Correlation IDs, structured error handling, rate limiting

### Documentation

- **[WebSocket Protocol](docs/WEBSOCKET_PROTOCOL.md)** - Complete protocol specification
- **[Message Examples](docs/WEBSOCKET_EXAMPLES.md)** - Detailed message flow examples  
- **[Quick Reference](docs/WEBSOCKET_QUICK_REFERENCE.md)** - Developer quick reference guide

### Key Features

- **Real-time Communication**: Player movement, chat, inventory operations
- **Structured Messages**: All messages use standardized envelope format
- **Error Handling**: Semantic error codes with actionable responses
- **Rate Limiting**: Per-operation cooldowns prevent abuse
- **State Management**: Efficient delta updates and broadcasting

## Testing

### Running Tests

```bash
# Start test environment
cd docker && docker-compose -f docker-compose.test.yml up -d --build

# Run all tests
docker exec docker-server-1 pytest -v

# Run WebSocket integration tests
docker exec docker-server-1 bash -c "RUN_INTEGRATION_TESTS=1 pytest server/src/tests/test_websocket_chat.py -v"

# Stop test environment
cd docker && docker-compose -f docker-compose.test.yml down
```

### Test Status
- **WebSocket Protocol**: 16/16 tests passing (100%)
- **Integration Tests**: Full authentication, chat, movement, inventory coverage
- **Unit Tests**: Comprehensive service layer testing

## Development

### Architecture Highlights

- **GameStateManager (GSM)**: Centralized state management with hot/cold data lifecycle
- **Service Layer**: Clean separation between business logic and data access
- **Protocol Modernization**: Semantic error codes for better developer experience
- **Message Validation**: Pydantic-based validation with structured error responses

### Key Technologies

- **FastAPI**: High-performance async web framework
- **WebSockets**: Real-time bidirectional communication
- **SQLAlchemy**: Async ORM with PostgreSQL
- **Valkey**: Redis-compatible caching layer
- **MessagePack**: Efficient binary serialization
- **Pydantic**: Runtime validation and settings management
- **Pygame**: Cross-platform game client
- **Docker**: Containerized deployment

## Status

**Current Status**: Production Ready
- ✅ WebSocket infrastructure fully operational
- ✅ Real-time features (chat, movement, inventory) working
- ✅ Comprehensive test coverage with 100% pass rate
- ✅ Modern error handling with semantic error codes
- ✅ Complete protocol documentation
