#!/bin/bash
# Me4BrAIn Development Server
# Runs the API locally with uvicorn hot-reload
# Requires: Docker services (qdrant, neo4j, redis, postgres) running

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Load environment variables
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# Override for local development
export QDRANT_HOST=localhost
export QDRANT_HTTP_PORT=6333
export NEO4J_HOST=localhost
export NEO4J_BOLT_PORT=7697
export REDIS_HOST=localhost
export REDIS_PORT=6389
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5489

# Check if Docker services are running
echo "Checking Docker services..."
docker ps --filter name=me4brain-qdrant --format "{{.Names}}: {{.Status}}" || echo "⚠️  Qdrant not running"
docker ps --filter name=me4brain-neo4j --format "{{.Names}}: {{.Status}}" || echo "⚠️  Neo4j not running"
docker ps --filter name=me4brain-redis --format "{{.Names}}: {{.Status}}" || echo "⚠️  Redis not running"
docker ps --filter name=me4brain-postgres --format "{{.Names}}: {{.Status}}" || echo "⚠️  Postgres not running"

echo ""
echo "Starting Me4BrAIn API with hot-reload..."
echo "API will be available at http://localhost:8000"
echo ""

# Run uvicorn with reload (disable uvloop for nest_asyncio compatibility)
cd "$PROJECT_ROOT"
PYTHONPATH="$PROJECT_ROOT/src:$PYTHONPATH" uvicorn me4brain.api.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload \
    --reload-dir src/me4brain \
    --log-level info \
    --loop asyncio
