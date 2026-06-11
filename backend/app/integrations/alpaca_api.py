from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Tuple

import httpx

from app.config import settings
from app.schemas.technical import TechnicalCandle
from app.utils.logger import get_logger

logger = get_logger(__name__)


class AlpacaMarketDataClient:
    def __init__(self) -> None:
        self.data_url = (settings.ALPACA_DATA_URL or "https://data.alpaca.markets").rstrip("/")
        self.api_key = settings.ALPACA_API_KEY
        self.secret_key = settings.ALPACA_SECRET_KEY

    async def fetch_recent_minute_bars(self, ticker: str, limit: int = 60) -> Tuple[List[TechnicalCandle], str]:
        if self.api_key and self.secret_key:
            try:
                candles = await self._fetch_from_alpaca(ticker, limit)
                if candles:
                    return candles, "alpaca"
            except Exception as exc:
                logger.warning(f"Alpaca fetch failed for {ticker}, falling back to Yahoo data: {exc}")

        candles = await self._fetch_from_yahoo(ticker, limit)
        if not candles:
            raise ValueError(f"No minute-bar data available for {ticker}")
        return candles, "yahoo-fallback"

    async def _fetch_from_alpaca(self, ticker: str, limit: int) -> List[TechnicalCandle]:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=7)
        url = f"{self.data_url}/v2/stocks/{ticker}/bars"
        params = {
            "timeframe": "1Min",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "limit": limit,
            "adjustment": "raw",
            "feed": "iex",
            "sort": "desc",
        }
        headers = {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()

        bars = payload.get("bars", [])
        return self._normalize_alpaca_bars(bars)

    async def _fetch_from_yahoo(self, ticker: str, limit: int) -> List[TechnicalCandle]:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        params = {
            "interval": "1m",
            "range": "1d",
            "includePrePost": "false",
            "events": "div%2Csplit",
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()

        result = (payload.get("chart", {}).get("result") or [{}])[0]
        timestamps = result.get("timestamp") or []
        quotes = (result.get("indicators", {}).get("quote") or [{}])[0]

        candles: List[TechnicalCandle] = []
        for idx, timestamp in enumerate(timestamps):
            open_price = self._get_index_value(quotes.get("open"), idx)
            high_price = self._get_index_value(quotes.get("high"), idx)
            low_price = self._get_index_value(quotes.get("low"), idx)
            close_price = self._get_index_value(quotes.get("close"), idx)
            volume = self._get_index_value(quotes.get("volume"), idx, default=0)

            if None in (open_price, high_price, low_price, close_price):
                continue

            candles.append(
                TechnicalCandle(
                    timestamp=datetime.fromtimestamp(timestamp, tz=timezone.utc),
                    open=float(open_price),
                    high=float(high_price),
                    low=float(low_price),
                    close=float(close_price),
                    volume=int(volume or 0),
                )
            )

        return candles[-limit:]

    def _normalize_alpaca_bars(self, bars: List[dict]) -> List[TechnicalCandle]:
        normalized = [
            TechnicalCandle(
                timestamp=datetime.fromisoformat(bar["t"].replace("Z", "+00:00")),
                open=float(bar["o"]),
                high=float(bar["h"]),
                low=float(bar["l"]),
                close=float(bar["c"]),
                volume=int(bar.get("v", 0)),
            )
            for bar in reversed(bars)
        ]
        return normalized

    @staticmethod
    def _get_index_value(values: list | None, index: int, default: float | None = None):
        if values is None or index >= len(values):
            return default
        value = values[index]
        return default if value is None else value
