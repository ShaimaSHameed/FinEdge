#!/bin/bash

# FinEdge Backend Docker Startup Script
# This script helps you set up and run the backend using Docker Compose

set -e  # Exit on error

echo "=========================================="
echo "FinEdge Backend Docker Setup"
echo "=========================================="
echo ""

# Check if .env file exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found!"
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo "✅ Created .env file"
    echo ""
    echo "⚠️  IMPORTANT: Please edit .env and add your API keys:"
    echo "   - NEWS_API_KEY (EventRegistry API key)"
    echo "   - OPENROUTER_API_KEY (OpenRouter API key)"
    echo ""
    read -p "Press Enter to continue after editing .env, or Ctrl+C to cancel..."
fi

# Check if required environment variables are set
source .env

if [ "$NEWS_API_KEY" = "your_event_registry_api_key_here" ] || [ -z "$NEWS_API_KEY" ]; then
    echo "❌ ERROR: NEWS_API_KEY is not set in .env file"
    echo "Please edit .env and add your EventRegistry API key"
    exit 1
fi

if [ "$OPENROUTER_API_KEY" = "your_openrouter_api_key_here" ] || [ -z "$OPENROUTER_API_KEY" ]; then
    echo "❌ ERROR: OPENROUTER_API_KEY is not set in .env file"
    echo "Please edit .env and add your OpenRouter API key"
    exit 1
fi

echo "✅ Environment variables verified"
echo ""

# Stop any existing containers
echo "🛑 Stopping existing containers..."
docker-compose down

# Build and start containers
echo "🔨 Building Docker images..."
docker-compose build

echo "🚀 Starting containers..."
docker-compose up -d

# Wait for backend to be healthy
echo "⏳ Waiting for backend service to be ready..."
max_attempts=30
attempt=0

while [ $attempt -lt $max_attempts ]; do
    if docker-compose ps | grep -q "backend.*Up"; then
        # Check if backend is responding
        if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
            echo "✅ Backend is ready!"
            echo ""
            echo "=========================================="
            echo "Services running:"
            docker-compose ps
            echo ""
            echo "API available at: http://localhost:8000"
            echo "API docs at: http://localhost:8000/docs"
            echo ""
            echo "To view logs: docker-compose logs -f backend"
            echo "To stop: docker-compose down"
            echo "=========================================="
            exit 0
        fi
    fi
    
    attempt=$((attempt + 1))
    echo "Attempt $attempt/$max_attempts..."
    sleep 2
done

echo "❌ ERROR: Backend failed to start within expected time"
echo "Check logs with: docker-compose logs backend"
exit 1
