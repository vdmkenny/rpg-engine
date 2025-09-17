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
    cd rpg2/docker
    ```
3.  **Build and run the services:**
    ```bash
    docker-compose up --build
    ```
This command will start the database, valkey cache, server, and a single client instance.

You can monitor the logs for each service in the terminal. To run multiple clients, you can start them in separate terminals or scale the service.

## Project Structure

```
rpg2/
├── client/             # Thin client application
│   ├── src/
│   ├── Dockerfile
│   └── requirements.txt
├── common/             # Code shared between client and server
│   └── src/
├── docker/
│   └── docker-compose.yml
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
