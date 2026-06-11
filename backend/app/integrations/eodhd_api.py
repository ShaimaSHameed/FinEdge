from __future__ import annotations

from typing import Any, Dict

import httpx

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class EODHDClient:
    def __init__(self) -> None:
        self.api_key = settings.EODHD_API_KEY
        self.base_url = settings.EODHD_BASE_URL.rstrip("/")

    async def fetch_fundamentals(self, ticker: str, market: str = "US") -> Dict[str, Any] | None:
        if not self.api_key:
            logger.info("EODHD_API_KEY is not configured; skipping live fundamental fetch")
            return None

        exchange = self._exchange_for_market(market)
        url = f"{self.base_url}/fundamentals/{ticker}.{exchange}"
        params = {"api_token": self.api_key, "fmt": "json"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)

        if response.status_code == 404:
            return None

        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) and payload.get("General") else None

    @staticmethod
    def _exchange_for_market(market: str) -> str:
        if market.upper() == "US":
            return "US"
        raise ValueError("Fundamental analysis currently supports US market data only")
