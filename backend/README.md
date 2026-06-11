# FinEdge Stock Analytics Backend - Sentimental Engine

This module provides sentiment analysis of stock news using LLM-based analysis
via OpenRouter API accessing Google Gemini 3 Flash Preview model.
It follows the architecture patterns defined in architecture.md.

## Features

- **Sentiment Analysis**: Analyzes news articles for stock sentiment using LLM
- **Caching**: 24-hour cache for news data to reduce API calls
- **Multi-Market Support**: Supports both US and Indian stock markets
- **Async Processing**: Non-blocking I/O for better performance

## Quick Start with Docker

### Prerequisites

- Docker and Docker Compose installed
- API keys for EventRegistry and OpenRouter

### Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd FinEdge/backend
   ```

2. **Configure environment variables**
   ```bash
   # Copy the example environment file
   cp .env.example .env

   # Edit .env and add your API keys
   nano .env
   ```

   Required environment variables:
   - `NEWS_API_KEY`: Your EventRegistry API key
   - `OPENROUTER_API_KEY`: Your OpenRouter API key
   - `DATABASE_URL`: PostgreSQL connection string (default provided for Docker)
   - `LLM_MODEL`: LLM model to use (default: google/gemini-3-flash-preview)

3. **Start the services**
   ```bash
   # Make the startup script executable
   chmod +x docker-start.sh

   # Run the startup script
   ./docker-start.sh
   ```

   Or manually:
   ```bash
   docker-compose up -d --build
   ```

### Verify Installation

Once running, verify the service is healthy:

```bash
curl http://localhost:8000/api/health
```

Expected response:
```json
{"status":"healthy"}
```

### Access API Documentation

Open your browser and navigate to:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## API Endpoints

### Sentiment Analysis

**POST** `/api/analyze/sentimental`

Analyze sentiment for a given stock ticker.

**Request Body:**
```json
{
  "ticker": "AAPL",
  "market": "US"
}
```

**Response:**
```json
{
  "ticker": "AAPL",
  "market": "US",
  "overall_sentiment": "Positive",
  "score": 0.342,
  "news_breakdown": {
    "ticker": "AAPL",
    "article_count": 10,
    "positive_count": 6,
    "negative_count": 2,
    "neutral_count": 2,
    "average_score": 0.342,
    "top_positive_articles": [...],
    "top_negative_articles": [...]
  },
  "trend": "Improving",
  "confidence": 0.75,
  "analysis_summary": "Based on 10 news articles, sentiment is Positive...",
  "influential_articles": [...],
  "cached": false,
  "analyzed_at": "2026-01-24T06:00:00Z"
}
```

### Health Check

**GET** `/api/health`

Check if the service is running.

## Supported Tickers

The system supports the following stock tickers:

**US Market:**
- AAPL, MSFT, NVDA, GOOGL, AMZN, META, TSLA, AVGO, AMD, INTC, QCOM, TXN, MU, AMAT, LRCX, ORCL, CRM, ADBE, NOW, SNOW, SHOP, INTU, PANW, CRWD, ZS, NFLX, IBM, UBER, ABNB, CSCO

**Indian Market:**
- RELIANCE.NS, TCS.NS, INFY.NS, HDFCBANK.NS, ICICIBANK.NS

## Development

### Local Development

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up environment**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

3. **Run the application**
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

### Project Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application entry point
│   ├── config.py             # Configuration management
│   ├── database.py            # Database connection and session
│   ├── engines/
│   │   └── sentimental/
│   │       ├── engine.py      # Sentiment analysis orchestrator
│   │       └── llm_analyzer.py # LLM-based sentiment scoring
│   ├── integrations/
│   │   └── news_api.py     # EventRegistry integration
│   ├── models/
│   │   ├── analysis_history.py
│   │   └── cache_news.py
│   ├── routers/
│   │   └── sentimental.py    # API endpoints
│   ├── schemas/
│   │   └── sentimental.py    # Pydantic models
│   ├── services/
│   │   └── cache_manager.py # Cache management
│   └── utils/
│       └── logger.py         # Logging configuration
├── Dockerfile
├── docker-compose.yml
├── docker-start.sh          # Startup script
├── requirements.txt
├── .env.example
└── README.md
```

## Troubleshooting

### Database Connection Issues

If you see database connection errors:
1. Ensure PostgreSQL container is running: `docker-compose ps`
2. Check database logs: `docker-compose logs postgres`
3. Verify DATABASE_URL in .env matches docker-compose.yml

### API Key Issues

If API calls fail:
1. Verify NEWS_API_KEY is valid and active
2. Verify OPENROUTER_API_KEY has sufficient credits
3. Check API logs: `docker-compose logs backend`

### Cache Not Working

If caching seems ineffective:
1. Check cache_news table exists: Connect to database and verify
2. Verify cache TTL is 24 hours
3. Check logs for cache-related errors

## License

MIT

## Version

__version__ = "1.0.0"
