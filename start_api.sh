#!/bin/bash
# Start Paper Trading API Server

cd "$(dirname "$0")"

# Activate venv
source ../oracle/venv312/bin/activate

# Check environment variables
if [ -z "$DATABASE_URL" ]; then
    echo "ERROR: DATABASE_URL not set"
    exit 1
fi

# Start API server
echo "🚀 Starting Paper Trading API on http://localhost:8000"
echo "📊 API docs: http://localhost:8000/docs"
echo ""

uvicorn api.main:app --reload --port 8000 --host 0.0.0.0
