from fastapi import APIRouter
import asyncio
import xml.etree.ElementTree as ET
import httpx
from concurrent.futures import ThreadPoolExecutor
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/market", tags=["market"])

executor = ThreadPoolExecutor(max_workers=4)

INDEX_SYMBOLS = {
    "S&P 500":     "^GSPC",
    "Nasdaq 100":  "^NDX",
    "Dow Jones":   "^DJI",
    "Russell 2000":"^RUT",
}

WATCHLIST_TICKERS = ["MSFT", "GOOGL", "AAPL", "NVDA"]


def _fetch_quotes_sync(symbols: list[str]) -> dict:
    """Fetch quotes using yfinance synchronously."""
    try:
        import yfinance as yf
        result = {}
        tickers = yf.Tickers(" ".join(symbols))
        for sym in symbols:
            try:
                info = tickers.tickers[sym].fast_info
                price = float(info.last_price or 0)
                prev  = float(info.previous_close or price)
                change = price - prev
                change_pct = (change / prev * 100) if prev else 0
                result[sym] = {
                    "symbol": sym,
                    "price": round(price, 2),
                    "change": round(change, 2),
                    "changePercent": round(change_pct, 2),
                }
            except Exception as e:
                logger.warning(f"Quote failed for {sym}: {e}")
        return result
    except Exception as e:
        logger.error(f"yfinance batch quote failed: {e}")
        return {}


def _fetch_movers_sync(scr_id: str, count: int = 5) -> list:
    """Fetch market movers using yfinance screener."""
    try:
        import yfinance as yf
        screener = yf.Screener()
        screener.set_predefined_body(scr_id)
        screener.set_params({"count": count})
        resp = screener.response
        quotes = resp.get("quotes", [])
        result = []
        for q in quotes:
            pct = q.get("regularMarketChangePercent", 0)
            result.append({
                "ticker": q.get("symbol", ""),
                "name": q.get("shortName") or q.get("longName", ""),
                "price": f"${q.get('regularMarketPrice', 0):.2f}",
                "change": f"{'+' if pct >= 0 else ''}{pct:.2f}%",
                "positive": pct >= 0,
            })
        return result
    except Exception as e:
        logger.warning(f"Movers fetch failed ({scr_id}): {e}")
        return _fetch_movers_fallback(scr_id, count)


def _fetch_movers_fallback(scr_id: str, count: int) -> list:
    """Fallback using httpx if yfinance screener fails."""
    try:
        import httpx as hx
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
        url = f"https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?scrIds={scr_id}&count={count}"
        r = hx.get(url, headers=headers, timeout=8)
        quotes = r.json().get("finance", {}).get("result", [{}])[0].get("quotes", [])
        result = []
        for q in quotes:
            pct = q.get("regularMarketChangePercent", 0)
            result.append({
                "ticker": q.get("symbol", ""),
                "name": q.get("shortName") or q.get("longName", ""),
                "price": f"${q.get('regularMarketPrice', 0):.2f}",
                "change": f"{'+' if pct >= 0 else ''}{pct:.2f}%",
                "positive": pct >= 0,
            })
        return result
    except Exception as e:
        logger.warning(f"Movers fallback failed: {e}")
        return []


def _fetch_market_news_sync() -> list:
    """Fetch market news from EventRegistry using real NewsAPI key."""
    try:
        from app.config import settings
        from eventregistry import EventRegistry, QueryArticlesIter, ReturnInfo, ArticleInfoFlags
        from datetime import datetime, timedelta, timezone

        er = EventRegistry(apiKey=settings.NEWS_API_KEY)
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=2)

        query = QueryArticlesIter(
            keywords="stock market investing S&P 500 earnings Federal Reserve",
            lang="eng",
            dateStart=start_date.strftime("%Y-%m-%d"),
            dateEnd=end_date.strftime("%Y-%m-%d"),
        )

        news = []
        seen_urls = set()
        return_info = ReturnInfo(articleInfo=ArticleInfoFlags(body=False))

        for article in query.execQuery(er, maxItems=12, returnInfo=return_info):
            url = article.get("url", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            title = article.get("title", "").strip()
            source_obj = article.get("source", {})
            source = source_obj.get("title", "News") if isinstance(source_obj, dict) else "News"
            pub = article.get("dateTime") or article.get("dateTimePub") or ""
            if title:
                news.append({
                    "headline": title,
                    "url": url,
                    "source": source,
                    "time": str(pub)[:16].replace("T", " ") if pub else "",
                })

        logger.info(f"Fetched {len(news)} market news articles from EventRegistry")
        return news

    except Exception as e:
        logger.warning(f"EventRegistry news failed: {e}, falling back to Yahoo RSS")
        return _fetch_news_rss_sync()


def _fetch_news_rss_sync() -> list:
    """Fallback: Yahoo Finance RSS."""
    try:
        import httpx as hx
        import xml.etree.ElementTree as ET2
        headers = {"User-Agent": "Mozilla/5.0"}
        url = "https://feeds.finance.yahoo.com/rss/2.0/headline?s=SPY,QQQ,MSFT,GOOGL,AAPL&lang=en-US"
        r = hx.get(url, headers=headers, timeout=8)
        root = ET2.fromstring(r.text)
        items = root.findall(".//item")
        news = []
        for item in items[:10]:
            title = item.findtext("title", "").strip()
            link  = item.findtext("link", "").strip()
            pub   = item.findtext("pubDate", "").strip()
            src_el = item.find("source")
            source = src_el.text if src_el is not None else "Yahoo Finance"
            if title and link:
                news.append({"headline": title, "url": link, "source": source, "time": pub})
        return news
    except Exception as e:
        logger.warning(f"RSS fallback also failed: {e}")
        return []


async def _fetch_news() -> list:
    """Fetch news — RSS first (fast), then try EventRegistry to enrich sources."""
    loop = asyncio.get_event_loop()
    # Start with fast RSS
    rss_news = await loop.run_in_executor(executor, _fetch_news_rss_sync)
    if rss_news:
        # Try EventRegistry in background for diversity, but don't block
        try:
            er_news = await asyncio.wait_for(
                loop.run_in_executor(executor, _fetch_market_news_sync),
                timeout=6.0
            )
            if er_news:
                # Merge: EventRegistry first (diverse sources), then RSS for remainder
                seen = {n['headline'] for n in er_news}
                extras = [n for n in rss_news if n['headline'] not in seen]
                return (er_news + extras)[:10]
        except Exception:
            pass
    return rss_news[:10]


@router.get("/overview")
async def get_market_overview():
    loop = asyncio.get_event_loop()

    all_symbols = list(INDEX_SYMBOLS.values()) + WATCHLIST_TICKERS

    quotes_future  = loop.run_in_executor(executor, _fetch_quotes_sync, all_symbols)
    gainers_future = loop.run_in_executor(executor, _fetch_movers_sync, "day_gainers", 5)
    losers_future  = loop.run_in_executor(executor, _fetch_movers_sync, "day_losers", 5)
    news_future    = _fetch_news()

    quotes, gainers, losers, news = await asyncio.gather(
        quotes_future, gainers_future, losers_future, news_future,
        return_exceptions=True,
    )

    if isinstance(quotes, Exception):
        quotes = {}
    if isinstance(gainers, Exception):
        gainers = []
    if isinstance(losers, Exception):
        losers = []
    if isinstance(news, Exception):
        news = []

    indexes = []
    for label, sym in INDEX_SYMBOLS.items():
        q = quotes.get(sym)
        if q:
            indexes.append({
                "label": label,
                "value": f"{q['price']:,.2f}",
                "change": f"{'+' if q['changePercent'] >= 0 else ''}{q['changePercent']:.2f}%",
                "positive": q["changePercent"] >= 0,
            })

    prices = {t: quotes[t] for t in WATCHLIST_TICKERS if t in quotes}

    return {
        "indexes": indexes,
        "prices": prices,
        "gainers": gainers,
        "losers": losers,
        "news": news,
    }


@router.get("/price/{ticker}")
async def get_price(ticker: str):
    loop = asyncio.get_event_loop()
    quotes = await loop.run_in_executor(executor, _fetch_quotes_sync, [ticker.upper()])
    q = quotes.get(ticker.upper())
    if not q:
        return {"error": "Price unavailable"}
    return q


def _fetch_stats_sync(ticker: str) -> dict:
    """Fetch key financial stats from yfinance."""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        info = t.info or {}

        def _pct(val):
            if val is None: return None
            return round(val * 100, 2)

        def _fmt_large(val):
            if val is None: return None
            if val >= 1e12: return f"${val/1e12:.2f}T"
            if val >= 1e9:  return f"${val/1e9:.2f}B"
            if val >= 1e6:  return f"${val/1e6:.2f}M"
            return f"${val:,.0f}"

        return {
            "ticker": ticker,
            "company_name": info.get("longName") or info.get("shortName"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "market_cap": _fmt_large(info.get("marketCap")),
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "peg_ratio": info.get("pegRatio"),
            "ps_ratio": info.get("priceToSalesTrailing12Months"),
            "pb_ratio": info.get("priceToBook"),
            "ev_ebitda": info.get("enterpriseToEbitda"),
            "roe": _pct(info.get("returnOnEquity")),
            "roa": _pct(info.get("returnOnAssets")),
            "gross_margin": _pct(info.get("grossMargins")),
            "operating_margin": _pct(info.get("operatingMargins")),
            "net_margin": _pct(info.get("profitMargins")),
            "revenue_growth": _pct(info.get("revenueGrowth")),
            "earnings_growth": _pct(info.get("earningsGrowth")),
            "debt_to_equity": info.get("debtToEquity"),
            "current_ratio": info.get("currentRatio"),
            "quick_ratio": info.get("quickRatio"),
            "fcf_margin": None,  # derived if needed
            "beta": info.get("beta"),
            "week_52_high": info.get("fiftyTwoWeekHigh"),
            "week_52_low": info.get("fiftyTwoWeekLow"),
            "avg_volume": info.get("averageVolume"),
            "shares_outstanding": _fmt_large(info.get("sharesOutstanding")) if info.get("sharesOutstanding") else None,
            "dividend_yield": _pct(info.get("dividendYield")),
            "forward_eps": info.get("forwardEps"),
            "total_cash": _fmt_large(info.get("totalCash")),
            "total_debt": _fmt_large(info.get("totalDebt")),
            "free_cashflow": _fmt_large(info.get("freeCashflow")),
            "revenue": _fmt_large(info.get("totalRevenue")),
            "net_income": _fmt_large(info.get("netIncomeToCommon")),
            "next_earnings": info.get("nextFiscalYearEnd"),
            "analyst_target": info.get("targetMeanPrice"),
            "analyst_rating": info.get("recommendationKey"),
        }
    except Exception as exc:
        logger.warning(f"Failed to fetch stats for {ticker}: {exc}")
        return {"ticker": ticker, "error": str(exc)}


@router.get("/stats/{ticker}")
async def get_stats(ticker: str):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, _fetch_stats_sync, ticker.upper())


def _fetch_features_sync(ticker: str) -> dict:
    """Read latest row from features.csv for a ticker — our ML model's training features."""
    import csv
    from pathlib import Path

    candidates = [
        Path("/artifacts/features.csv"),
        Path(__file__).resolve().parents[4] / "fundamental_model" / "data" / "features.csv",
    ]
    features_path = next((p for p in candidates if p.exists()), None)
    if not features_path:
        return {"ticker": ticker, "error": "features.csv not found"}

    latest_row = None
    try:
        with features_path.open("r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if (row.get("ticker") or "").upper() == ticker:
                    latest_row = row  # keep last (most recent)
    except Exception as exc:
        return {"ticker": ticker, "error": str(exc)}

    if not latest_row:
        return {"ticker": ticker, "error": f"No features data found for {ticker}"}

    def sf(k):
        v = latest_row.get(k, "")
        try:
            return float(v) if v not in ("", "nan", "None", "NaN") else None
        except (ValueError, TypeError):
            return None

    return {
        "ticker": ticker,
        "snapshot_date": latest_row.get("snapshot_date"),
        "sector": latest_row.get("sector"),
        "industry": latest_row.get("industry"),
        # Margins
        "gross_margin":      sf("gross_margin"),
        "operating_margin":  sf("operating_margin"),
        "net_margin":        sf("net_margin"),
        "fcf_margin":        sf("fcf_margin"),
        # Returns
        "roe":  sf("roe"),
        "roa":  sf("roa"),
        "roic": sf("roic"),
        # Growth
        "revenue_growth_yoy":  sf("revenue_growth_yoy"),
        "earnings_growth_yoy": sf("earnings_growth_yoy"),
        "fcf_growth_yoy":      sf("fcf_growth_yoy"),
        "revenue_growth_qoq":  sf("revenue_growth_qoq"),
        # Valuation
        "pe_ratio":   sf("pe_ratio"),
        "pb_ratio":   sf("pb_ratio"),
        "ps_ratio":   sf("ps_ratio"),
        "ev_ebitda":  sf("ev_ebitda"),
        "fcf_yield":  sf("fcf_yield"),
        "earnings_yield": sf("earnings_yield"),
        "buyback_yield":  sf("buyback_yield"),
        # Health
        "debt_to_equity": sf("debt_to_equity"),
        "current_ratio":  sf("current_ratio"),
        "net_debt_ebitda": sf("net_debt_ebitda"),
        "interest_coverage": sf("interest_coverage"),
        # Quality scores
        "piotroski_score":      sf("piotroski_score"),
        "piotroski_normalized": sf("piotroski_normalized"),
        "analyst_bull_score":   sf("analyst_bull_score"),
        "eps_beat_rate":        sf("eps_beat_rate"),
        "eps_momentum":         sf("eps_momentum"),
        "short_interest_pct":   sf("short_interest_pct"),
        # Balance sheet dollar amounts
        "cash":          sf("cash"),
        "total_debt_raw": sf("total_debt"),
        "fcf_ttm":       sf("fcf_ttm"),
        "revenue_ttm":   sf("revenue_ttm"),
        "net_income_ttm": sf("net_income_ttm"),
        "ebitda_ttm":    sf("ebitda_ttm"),
        "cfo_ttm":       sf("cfo_ttm"),
        "market_cap":    sf("market_cap"),
    }


@router.get("/fundamentals-features/{ticker}")
async def get_fundamentals_features(ticker: str):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, _fetch_features_sync, ticker.upper())
