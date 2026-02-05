# Production Server Startup Guide

This guide documents how to properly start the RPG Server in production mode with database migrations.

## Overview

The production server requires:
1. PostgreSQL database with proper schema (managed via Alembic migrations)
2. Valkey (Redis-compatible cache) for game state
3. All migrations applied before starting the server

## Prerequisites

Before starting the server, ensure you have:
- Docker and Docker Compose installed
- Access to production environment variables
- Database backup procedures in place (for production upgrades)

## Quick Start (Production)

### Option 1: Using Docker Compose (Recommended)

```bash
# 1. Start all infrastructure services
cd docker
docker-compose up -d postgres valkey

# 2. Run database migrations
docker-compose run --rm server bash -c "cd server && alembic upgrade head"

# 3. Start the full application
docker-compose up -d

# 4. Verify migrations are applied
docker-compose exec postgres psql -U rpg_user -d rpg_db -c "SELECT version_num FROM alembic_version;"
```

### Option 2: Manual Steps

If you need more control over the startup process:

```bash
# 1. Build the server image
cd docker
docker-compose build server

# 2. Start database and cache only
docker-compose up -d postgres valkey

# 3. Wait for PostgreSQL to be ready (important!)
docker-compose exec postgres pg_isready -U rpg_user -d rpg_db

# 4. Run migrations in the server container
docker-compose run --rm server bash -c "cd server && alembic upgrade head"

# 5. Start the server
docker-compose up -d server
```

## Migration Management

### Check Current Migration Status

```bash
# In Docker
docker-compose run --rm server bash -c "cd server && alembic current"

# Expected output:
# ead1d3f3e1c2 (head)  # or whatever is the current head
```

### View Migration History

```bash
docker-compose run --rm server bash -c "cd server && alembic history"
```

### Create New Migration (Development Only)

When you modify SQLAlchemy models:

```bash
docker-compose run --rm server bash -c "cd server && alembic revision --autogenerate -m 'description of changes'"

# Then apply it
docker-compose run --rm server bash -c "cd server && alembic upgrade head"
```

### Rollback Migrations (Emergency Use Only)

```bash
# Rollback one revision
docker-compose run --rm server bash -c "cd server && alembic downgrade -1"

# Rollback to specific revision
docker-compose run --rm server bash -c "cd server && alembic downgrade <revision_id>"

# Rollback all the way
docker-compose run --rm server bash -c "cd server && alembic downgrade base"
```

## Troubleshooting

### Error: "column X does not exist"

**Symptom:** Server fails to start with an error like:
```
column "icon_sprite_id" of relation "items" does not exist
```

**Solution:** Apply pending migrations:
```bash
cd docker
docker-compose run --rm server bash -c "cd server && alembic upgrade head"
```

### Error: "relation does not exist"

**Symptom:** Server fails with SQL errors about missing tables.

**Solution:** You may be starting from scratch or have a corrupted database. Run:
```bash
# Reset database (WARNING: DESTROYS ALL DATA)
cd docker
docker-compose down -v  # Removes volumes including postgres data
docker-compose up -d postgres
docker-compose run --rm server bash -c "cd server && alembic upgrade head"
```

### Migration Conflicts

**Symptom:** Alembic reports multiple heads or conflicts.

**Solution:**
```bash
# Merge multiple heads
docker-compose run --rm server bash -c "cd server && alembic merge -m 'merge heads' head1 head2"
```

## Environment Variables

Production server requires these environment variables:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://rpg_user:rpg_password@postgres:5432/rpg_db

# Valkey/Redis
VALKEY_HOST=valkey
VALKEY_PORT=6379

# Security (CRITICAL - CHANGE THESE!)
JWT_SECRET_KEY=your-production-secret-key-min-32-chars-long!!!
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Game Settings
GAME_TICK_RATE=20
GAME_MOVEMENT_COOLDOWN=0.3
USE_VALKEY=true

# Logging
LOG_LEVEL=INFO
ENVIRONMENT=production
```

## Health Checks

After startup, verify the server is healthy:

```bash
# Check API health
curl http://localhost:8000/
# Expected: {"status": "ok"}

# Check if migrations are current
docker-compose exec postgres psql -U rpg_user -d rpg_db -c "SELECT version_num FROM alembic_version;"

# Check logs for errors
docker-compose logs -f server
```

## Continuous Deployment Pipeline

Example CI/CD steps for production deployment:

```bash
#!/bin/bash
set -e

# 1. Build
docker-compose build server

# 2. Start infrastructure
docker-compose up -d postgres valkey

# 3. Wait for database
sleep 5
docker-compose exec postgres pg_isready -U rpg_user -d rpg_db

# 4. Run migrations
docker-compose run --rm server bash -c "cd server && alembic upgrade head"

# 5. Deploy new server version
docker-compose up -d server

# 6. Health check
curl -f http://localhost:8000/ || exit 1

echo "Deployment successful!"
```

## Production Checklist

Before going live:

- [ ] All migrations applied (`alembic current` shows head)
- [ ] Database backups configured
- [ ] Environment variables set correctly
- [ ] JWT_SECRET_KEY changed from default
- [ ] Valkey/Redis running and accessible
- [ ] Health checks passing
- [ ] Log aggregation configured
- [ ] Monitoring/alerts set up

## Important Notes

1. **Never skip migrations**: Always run `alembic upgrade head` before starting the server
2. **Backup before migrations**: Production databases should be backed up before schema changes
3. **Migration failures**: If migrations fail, do not start the server - fix the issue first
4. **Rollback capability**: Keep previous server version available in case rollback is needed

## Migration Files Location

Migration files are stored at:
```
server/alembic/versions/
```

Each migration has a unique revision ID. The current database state is tracked in the `alembic_version` table in PostgreSQL.
