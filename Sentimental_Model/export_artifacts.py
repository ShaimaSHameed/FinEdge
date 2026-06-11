import argparse
import csv
import json
import math
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "outputs"

MODEL_IDS = {
    "gpt54": "openai/gpt-5.4",
    "opus47": "anthropic/claude-opus-4.7",
    "gemini31_pro": "google/gemini-3.1-pro-preview",
    "mimo_v2_pro": "xiaomi/mimo-v2-pro",
    "deepseek_v32": "deepseek/deepseek-v3.2",
    "sonnet46": "anthropic/claude-sonnet-4.6",
    "haiku45": "anthropic/claude-haiku-4.5",
    "finbert": "finbert",
    "vader": "vader",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export sentimental model artifacts for FinEdge.")
    parser.add_argument("--ticker", default="GOOGL")
    parser.add_argument("--market", default="US")
    parser.add_argument("--model", default="gemini31_pro")
    parser.add_argument("--strategy", default="v1")
    parser.add_argument("--run-id", default=datetime.now(timezone.utc).strftime("%Y%m%d"))
    parser.add_argument("--news-file", default=None)
    parser.add_argument("--score-cache-file", default=None)
    parser.add_argument("--trade-file", default=None)
    parser.add_argument("--leaderboard-file", default=None)
    parser.add_argument("--max-articles", type=int, default=50)
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Required CSV artifact not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_score_cache(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Required score cache artifact not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        cache = json.load(handle)
    if isinstance(cache, dict):
        values = list(cache.values())
    elif isinstance(cache, list):
        values = cache
    else:
        raise ValueError(f"Unsupported score cache shape in {path}")
    return [value for value in values if isinstance(value, dict)]


def parse_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
        if math.isfinite(parsed):
            return parsed
    except (TypeError, ValueError):
        pass
    return default


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def parse_datetime(value: Any) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        return datetime.min.replace(tzinfo=timezone.utc)
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed = datetime.strptime(raw[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def score_to_sentiment(score: float) -> str:
    if score > 0.05:
        return "Positive"
    if score < -0.05:
        return "Negative"
    return "Neutral"


def score_to_verdict(score: float) -> str:
    if score > 0.05:
        return "BUY"
    if score < -0.05:
        return "SELL"
    return "HOLD"


def build_scored_articles(
    news_rows: list[dict[str, str]],
    score_rows: list[dict[str, Any]],
    ticker: str,
    max_articles: int,
) -> list[dict[str, Any]]:
    sorted_news = sorted(news_rows, key=lambda row: parse_datetime(row.get("published") or row.get("published_at")))
    paired: list[dict[str, Any]] = []

    for news, score in zip(sorted_news, score_rows):
        sentiment_score = parse_float(score.get("score"))
        paired.append(
            {
                "ticker": ticker,
                "title": news.get("title") or "Untitled article",
                "published_at": news.get("published") or news.get("published_at"),
                "source": news.get("source") or "Unknown",
                "url": news.get("url"),
                "sentiment_score": sentiment_score,
                "verdict": score.get("verdict") or score_to_verdict(sentiment_score),
                "reasoning": score.get("reasoning") or "",
                "confidence": parse_float(score.get("confidence"), 0.0),
                "materiality": parse_float(score.get("materiality"), 0.0),
                "horizon": score.get("horizon") or "days",
                "event_type": score.get("event_type") or "other",
            }
        )

    paired.sort(key=lambda row: parse_datetime(row.get("published_at")), reverse=True)
    return paired[:max_articles]


def calculate_trend(articles: list[dict[str, Any]]) -> str:
    if len(articles) < 3:
        return "Stable"
    recent = [parse_float(article.get("sentiment_score")) for article in articles[:3]]
    recent_avg = sum(recent) / len(recent)
    if len(articles) >= 6:
        previous = [parse_float(article.get("sentiment_score")) for article in articles[3:6]]
        previous_avg = sum(previous) / len(previous)
        change = recent_avg - previous_avg
        if change > 0.1:
            return "Improving"
        if change < -0.1:
            return "Declining"
    if recent_avg > 0.1:
        return "Improving"
    if recent_avg < -0.1:
        return "Declining"
    return "Stable"


def build_breakdown(ticker: str, articles: list[dict[str, Any]]) -> dict[str, Any]:
    scores = [parse_float(article.get("sentiment_score")) for article in articles]
    positive = [article for article in articles if parse_float(article.get("sentiment_score")) > 0.05]
    negative = [article for article in articles if parse_float(article.get("sentiment_score")) < -0.05]
    neutral = [
        article
        for article in articles
        if -0.05 <= parse_float(article.get("sentiment_score")) <= 0.05
    ]
    average_score = sum(scores) / len(scores) if scores else 0.0

    def top_article(article: dict[str, Any]) -> dict[str, Any]:
        return {
            "title": article.get("title"),
            "score": round(parse_float(article.get("sentiment_score")), 3),
            "verdict": article.get("verdict"),
            "source": article.get("source"),
        }

    return {
        "ticker": ticker,
        "article_count": len(articles),
        "positive_count": len(positive),
        "negative_count": len(negative),
        "neutral_count": len(neutral),
        "average_score": round(average_score, 3),
        "top_positive_articles": [
            top_article(article)
            for article in sorted(positive, key=lambda item: parse_float(item.get("sentiment_score")), reverse=True)[:3]
        ],
        "top_negative_articles": [
            top_article(article)
            for article in sorted(negative, key=lambda item: parse_float(item.get("sentiment_score")))[:3]
        ],
    }


def calculate_confidence(articles: list[dict[str, Any]], breakdown: dict[str, Any]) -> float:
    if not articles:
        return 0.0
    article_factor = min(len(articles) / 10, 1.0)
    average_model_confidence = sum(parse_float(article.get("confidence")) for article in articles) / len(articles)
    largest_bucket = max(
        breakdown["positive_count"],
        breakdown["negative_count"],
        breakdown["neutral_count"],
    ) / len(articles)
    return round((article_factor * 0.35) + (average_model_confidence * 0.4) + (largest_bucket * 0.25), 2)


def latest_trade(trade_rows: list[dict[str, str]], model: str, strategy: str) -> dict[str, str] | None:
    matches = [
        row
        for row in trade_rows
        if row.get("model") == model and row.get("strategy") == strategy
    ]
    if not matches:
        return None
    return sorted(matches, key=lambda row: parse_datetime(row.get("date")), reverse=True)[0]


def build_influential_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(
        articles,
        key=lambda article: abs(parse_float(article.get("sentiment_score"))),
        reverse=True,
    )
    return [
        {
            "title": article.get("title"),
            "sentiment": round(parse_float(article.get("sentiment_score")), 3),
            "verdict": article.get("verdict"),
            "reasoning": article.get("reasoning"),
            "source": article.get("source"),
            "url": article.get("url"),
            "event_type": article.get("event_type"),
            "materiality": round(parse_float(article.get("materiality")), 3),
            "horizon": article.get("horizon"),
        }
        for article in ranked[:5]
    ]


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def artifact_path(path: Path) -> str:
    display = path.relative_to(ROOT) if path.exists() and path.is_relative_to(ROOT) else path
    return str(display).replace("\\", "/")


def main() -> None:
    args = parse_args()
    ticker = args.ticker.upper()
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    news_file = Path(args.news_file) if args.news_file else DATA_DIR / f"test_{ticker}_news_ctx_alloc_1y.csv"
    score_cache_file = (
        Path(args.score_cache_file)
        if args.score_cache_file
        else DATA_DIR / "score_cache" / f"test_ctx1y_{args.model}.json"
    )
    trade_file = (
        Path(args.trade_file)
        if args.trade_file
        else DATA_DIR / f"test_trades_ctx1y_allocator_{ticker}.csv"
    )
    leaderboard_file = Path(args.leaderboard_file) if args.leaderboard_file else DATA_DIR / "leaderboard.csv"

    news_rows = read_csv(news_file)
    score_rows = read_score_cache(score_cache_file)
    trade_rows = read_csv(trade_file)
    trade = latest_trade(trade_rows, args.model, args.strategy)
    if trade is None:
        raise ValueError(f"No trade rows found for model={args.model} strategy={args.strategy} in {trade_file}")

    articles = build_scored_articles(news_rows, score_rows, ticker, args.max_articles)
    if not articles:
        raise ValueError(f"No scored articles could be reconstructed from {news_file} and {score_cache_file}")

    breakdown = build_breakdown(ticker, articles)
    normalized_score = max(-1.0, min(1.0, parse_float(breakdown["average_score"])))
    overall_sentiment = score_to_sentiment(normalized_score)
    trend = calculate_trend(articles)
    confidence = calculate_confidence(articles, breakdown)

    artifact = {
        "ticker": ticker,
        "market": args.market,
        "as_of": generated_at,
        "source_model": args.model,
        "source_model_id": MODEL_IDS.get(args.model, args.model),
        "strategy": args.strategy,
        "article_count": len(articles),
        "score": round(normalized_score, 3),
        "overall_sentiment": overall_sentiment,
        "trend": trend,
        "confidence": confidence,
        "model_signal": round(parse_float(trade.get("signal")), 6),
        "allocation": {
            "direction": trade.get("direction"),
            "raw_target_exposure": round(parse_float(trade.get("raw_target_exp")), 6),
            "chosen_exposure": round(parse_float(trade.get("chosen_exp")), 6),
            "predicted_edge": round(parse_float(trade.get("predicted_edge")), 6),
            "model_ready": parse_bool(trade.get("model_ready")),
            "model_rows": int(parse_float(trade.get("model_rows"), 0.0)),
        },
        "news_breakdown": breakdown,
        "influential_articles": build_influential_articles(articles),
        "analysis_summary": (
            f"{ticker} has {overall_sentiment.lower()} sentimental model tone from "
            f"{args.model} using {len(articles)} scored articles. Average article score is "
            f"{round(normalized_score, 3)} with {trend.lower()} article trend."
        ),
        "provenance": {
            "artifact_version": args.run_id,
            "generated_at": generated_at,
            "news_file": artifact_path(news_file),
            "score_cache_file": artifact_path(score_cache_file),
            "trade_file": artifact_path(trade_file),
            "leaderboard_file": artifact_path(leaderboard_file),
        },
    }

    run_dir = OUTPUT_DIR / "runs" / args.run_id
    latest_dir = OUTPUT_DIR / "latest"
    run_artifact = run_dir / f"{ticker}.json"
    latest_artifact = latest_dir / f"{ticker}.json"
    write_json(run_artifact, artifact)
    latest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(run_artifact, latest_artifact)

    manifest = {
        "run_id": args.run_id,
        "generated_at": generated_at,
        "default_model": args.model,
        "covered_tickers": [ticker],
        "files": [f"{ticker}.json"],
        "source_artifacts": {
            "news": artifact["provenance"]["news_file"],
            "score_cache": artifact["provenance"]["score_cache_file"],
            "trades": artifact["provenance"]["trade_file"],
            "leaderboard": artifact["provenance"]["leaderboard_file"],
        },
    }
    write_json(run_dir / "manifest.json", manifest)
    write_json(latest_dir / "manifest.json", manifest)
    print(f"Exported sentimental artifact: {latest_artifact}")


if __name__ == "__main__":
    main()
