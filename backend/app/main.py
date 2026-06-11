from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import ensemble_router, fundamental_router, sentimental_router, technical_router, user_router
from app.routers.email_router import router as email_router
from app.routers.market_router import router as market_router
from app.database import engine, Base
from app import models  # Ensures all models are registered before create_all
from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting application...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    logger.info("Shutting down application...")


app = FastAPI(
    title="FinEdge Stock Analytics API",
    description="Multi-dimensional stock market analysis platform",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sentimental_router)
app.include_router(technical_router)
app.include_router(fundamental_router)
app.include_router(ensemble_router)
app.include_router(user_router)
app.include_router(email_router)
app.include_router(market_router)


@app.get("/")
async def root():
    return {
        "message": "FinEdge Stock Analytics API",
        "version": "1.0.0",
        "endpoints": {
            "sentimental": "/api/analyze/sentimental",
            "technical": "/api/analyze/technical",
            "fundamental": "/api/analyze/fundamental",
            "ensemble_backtest": "/api/analyze/ensemble/backtest",
            "health": "/api/health"
        }
    }


@app.get("/api/health")
async def health():
    return {"status": "healthy"}
