"""
GOOGL Sentiment-Only Trading Benchmark
======================================
Compares multiple sentiment scorers (LLMs + FinBERT + VADER) on the same
news corpus and evaluates each by (a) signal quality metrics and (b) a
pure sentiment-driven backtest.

Author: Zein's senior design project
"""

import os
import json
import time
import hashlib
import requests
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from scipy.stats import spearmanr, pearsonr, norm, skew as sp_skew, kurtosis as sp_kurt
from sklearn.metrics import (
    precision_score, recall_score, f1_score,
    accuracy_score, matthews_corrcoef, confusion_matrix,
)
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import warnings
warnings.filterwarnings("ignore")

# Lazy imports — only loaded when actually fetching data, so the analytical
# functions can be unit-tested without these heavy / network-bound deps.
def _lazy_yfinance():
    import yfinance as yf
    return yf

def _lazy_eventregistry():
    from eventregistry import (
        EventRegistry, QueryArticlesIter, ReturnInfo,
        ArticleInfoFlags, QueryItems,
    )
    return EventRegistry, QueryArticlesIter, ReturnInfo, ArticleInfoFlags, QueryItems

# ==========================================================================
# 1. CONFIG
# ==========================================================================
EVENT_REGISTRY_KEY = os.getenv("NEWS_API_KEY", "")
OPENROUTER_KEY     = os.getenv("OPENROUTER_API_KEY", "")

def _require_api_key(value: str, env_name: str) -> str:
    if not value:
        raise RuntimeError(f"{env_name} is required for this sentimental model operation")
    return value

STOCK_NAME     = "Alphabet Inc"
STOCK_TICKER   = "GOOGL"
STOCK_SECTOR   = "Big Tech / Online Advertising / Cloud / AI"

# Concept labels for EventRegistry entity resolution (NOT keyword strings).
# er.getConceptUri("Alphabet Inc") resolves to the Wikipedia entity for Alphabet,
# not the string "Google" appearing in some bibliography.
STOCK_CONCEPTS = ["Alphabet Inc", "Google", "YouTube"]
# Subsidiary/person concepts — searched separately with AND(company concept)
# to avoid matching "Sundar Pichai" in generic tech-CEO listicles.
STOCK_PERSON_CONCEPTS = ["Sundar Pichai"]

LOOKBACK_DAYS           = 365
MAX_ARTICLES_PER_MONTH  = 200   # high cap — quality gates filter downstream
INITIAL_CAPITAL         = 1000.0
TRANSACTION_COST_PCT    = 0.001
MIN_TRADE_VALUE         = 10.0
MAX_EXPOSURE            = 2.5
MIN_EXPOSURE            = 0.0   # allow full cash flee (was 0.3)

# News fetch config — these defaults preserve exact GOOGL behavior. Override
# these at the module level (e.g. sb_mod.FETCH_CATEGORIES = [...]) from a
# driver script to widen/narrow coverage for other tickers without touching
# this file. Motivating case: GOOGL's ~$3T mega-cap financial news density
# saturates the business-only top-30% source pool, but TSLA/INTC coverage
# lives heavily in technology and automotive categories, and often in
# specialty publications (Electrek, CleanTechnica) outside the top-30%.
FETCH_CATEGORIES               = ["business"]  # list of EventRegistry category labels
FETCH_SOURCE_RANK_PCTILE_END   = 30            # 30 = top 30% sources only; 100 = all

# Rebalancing band: only rebalance if exposure change >= this fraction of portfolio
# This eliminates daily micro-trading fees from ridge's small day-to-day prediction noise
REBALANCE_BAND_PCT      = 0.12   # Default 12% — appropriate for noisy ridge/GBM predictions
# Separate band for smooth-signal strategies (v1 EMA, v2 impulse). These signals
# move gradually, so 12% is too wide and freezes them into buy-and-hold behavior.
REBALANCE_BAND_PCT_SMOOTH = 0.03  # 3% for smooth sentiment strategies
# Event gate: only ridge strategies consider rebalancing on days where the raw
# sentiment surprise exceeds this threshold (abs value). Other days: hold.
EVENT_GATE_SURPRISE     = 0.0    # 0 = off (keep daily rebal). Set to e.g. 0.05 to enable

# --- V6 event-driven classifier config ---
# Target horizon in trading days. Classifier predicts direction of 5-day forward return.
V6_HORIZON_DAYS         = 5
# Return bands for 3-class labeling: UP / FLAT / DOWN
V6_FLAT_BAND            = 0.005  # ret within ±0.5% over 5 days → FLAT
# Event gate: classifier only trades on days where |today's surprise| > this threshold
V6_EVENT_THRESHOLD      = 0.05   # require meaningful news surprise to re-enter market
# Size multiplier: position scales with raw |impulse_signal| (clipped to this max)
V6_SIZE_IMPULSE_CAP     = 0.5    # |impulse| > 0.5 treated as "loud day" (full size)

# How aggressively sentiment translates to exposure.
# exposure = clip( 1 + EXPOSURE_GAIN * tanh(sentiment_ema / EXPOSURE_SCALE), MIN, MAX )
EXPOSURE_GAIN   = 1.2
EXPOSURE_SCALE  = 30.0

# Sentiment EMA config
SENT_EMA_ALPHA_NEW  = 0.35   # weight on new day's score
SENT_EMA_DECAY      = 0.92   # daily decay when no news
SENT_EMA_SCALE      = 100.0  # multiplier so signal lives on a human-readable scale

DATA_DIR  = "data"
CACHE_DIR = os.path.join(DATA_DIR, "score_cache")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

NEWS_FILE = os.path.join(DATA_DIR, f"{STOCK_TICKER}_news_v2.csv")  # v2: concept-based fetch

# ==========================================================================
# SOTA UPGRADE CONFIG
# ==========================================================================
# 1) Lookahead-leakage guard: only EVALUATE on news after every model's
#    training cutoff. We still fetch earlier news so the EMA can warm up.
TEST_START_DATE = "2026-01-01"   # everything before this is warmup only

# 2) Multi-trial deflation: how many models we're testing — used for DSR
#    (set automatically from len(scorers) at runtime, this is just a fallback)
N_TRIALS_DEFAULT = 8

# 3) Event clustering / deduplication
EVENT_SIM_THRESHOLD    = 0.78    # TF-IDF cosine similarity to merge stories
EVENT_TIME_WINDOW_DAYS = 4       # only cluster articles within this window

# 4) Walk-forward folds for out-of-sample stability
N_FOLDS = 3

# 5) Event taxonomy — fixed set so we can bucket cleanly
EVENT_TYPES = [
    "earnings", "guidance", "mna", "antitrust_regulatory",
    "product_launch", "ai_announcement", "partnership",
    "exec_change", "lawsuit", "layoff_restructuring",
    "macro_market", "analyst_action", "other",
]


# ==========================================================================
# 2. SOPHISTICATED PROMPT
# ==========================================================================
ANALYST_SYSTEM_PROMPT = """You are an automated financial text-analysis tool producing
structured JSON outputs for a research pipeline. Your outputs are NOT financial advice;
they are sentiment labels used by a downstream benchmark. Never refuse to score an
article — if information is insufficient, return score=0.0 with low confidence and
materiality, and explain in the reasoning field.

You are a senior equity research analyst with 20 years of
experience covering {stock_name} and the broader {sector} sector. You evaluate news
with full awareness of market context, second-order effects, and historical analogues.
You are skeptical of headline drama and allergic to recycled filler.

When scoring an article, think through:

1. DIRECT IMPACT — Does this move revenue, margins, costs, TAM, or competitive moat?
2. MACRO CONTEXT — Rates, growth regime, risk-on/off. How does this news land *right now*?
3. SECTOR DYNAMICS — Positioning vs. MSFT/META/AMZN/AAPL/NVDA. Ad cycle, cloud capex,
   AI arms race, regulatory heat.
4. GEOPOLITICAL / REGULATORY — DOJ antitrust, EU DMA, China exposure, export controls,
   US and global geopolitical tensions, trade policy, sanctions, export controls,
   any conflict or diplomatic developments with macro market read-through.
5. SECOND-ORDER EFFECTS — If this plays out over 1–3 months, what cascades? Customer
   behavior, supplier reaction, competitor response, employee/talent signals.
6. HISTORICAL ANALOGUES — Have we seen this before? Think 2018 antitrust scares, 2022
   ad recession, Bard launch miss, Gemini launch. How did the tape react?
7. MARKET PSYCHOLOGY — Is it already priced in? Is the narrative shifting or just
   being restated? Retail vs. institutional read.
8. TIME HORIZON — One-day pop, one-month theme, or multi-quarter thesis change?
9. NOISE FILTER — Most articles are recycled, SEO filler, or off-topic. Score 0.0 and
   low materiality. Be ruthless.

PRICED-IN RULE (important):
 If the news is consistent with the prevailing narrative and already reflected in recent
 price action or prior coverage, materiality should be LOW (<0.3) even if the score itself
 is strong. SCORE and MATERIALITY are separate axes — score measures directional impact
 of the fundamental news, materiality measures how much *fresh* information it carries.
 The 4th earnings-beat article in a row has the same score as the 1st but lower materiality.

INSUFFICIENT INFORMATION RULE:
 If the article body is truncated, missing, ambiguous, or too generic to score responsibly,
 return score=0.0, materiality=0.0, confidence<0.3, and explicitly say so in reasoning.
 Do NOT fabricate a confident score on garbage input.

SCORING SCALE (-1.0 to +1.0):
 +0.8 to +1.0  Major positive — thesis-level tailwind, large surprise beat
 +0.4 to +0.7  Clearly positive — measurable benefit, likely tape reaction
 +0.1 to +0.3  Mildly positive
  0.0          Noise / irrelevant / priced in / balanced / insufficient info
 -0.1 to -0.3  Mildly negative
 -0.4 to -0.7  Clearly negative
 -0.8 to -1.0  Major negative — thesis break, scandal, large surprise miss

CALIBRATION ANCHORS (use this scale, not your own):
 +0.80  "Alphabet beats Q-on-Q EPS by 15%, raises full-year guidance"
 +0.55  "Google Cloud signs multi-year enterprise deal with major bank"
 +0.15  "Analyst reiterates Buy with modestly higher price target"
  0.00  "Sundar Pichai quoted in general AI-industry roundup article"
  0.00  "SEO filler piece recycling last quarter's earnings narrative"
 -0.20  "Minor analyst downgrade with price target trimmed ~5%"
 -0.55  "EU regulator announces formal probe into Google ad practices"
 -0.80  "DOJ files case seeking structural remedies including ad-business divestiture"

Also output:
 - confidence  (0–1): how sure you are about the score
 - materiality (0–1): how much FRESH information this carries (see priced-in rule)
 - horizon     : "intraday" | "days" | "weeks" | "months"
 - event_type  : EXACTLY ONE of:
     earnings, guidance, mna, antitrust_regulatory, product_launch,
     ai_announcement, partnership, exec_change, lawsuit,
     layoff_restructuring, macro_market, analyst_action, other

REASONING FORMAT: Exactly two sentences.
 Sentence 1: What happened and why it matters fundamentally.
 Sentence 2: Why you chose this specific (score, materiality) combination
             given the context block below.

Return ONLY a JSON object with keys: reasoning, score, confidence, materiality,
horizon, event_type. No preamble, no markdown."""

def build_price_context(article_date, price_df: pd.DataFrame,
                         macro_narrative: pd.DataFrame = None) -> str:
    """
    Deterministic price/market context as of the article's publish date.
    Includes GOOGL technicals, macro regime (SPY/VIX/oil), competitor
    read-through (META/MSFT/NVDA), earnings calendar proximity, and optional
    weekly macro narrative summary.
    Only uses data strictly BEFORE the article date — no lookahead.
    """
    d = pd.to_datetime(article_date).normalize()
    p = price_df.copy()
    p["date"] = pd.to_datetime(p["date"]).dt.normalize()
    hist = p[p["date"] < d].sort_values("date")
    if len(hist) < 20:
        return "  (insufficient price history for context)"

    last = hist.iloc[-1]
    last_close = last["close"]
    ma20  = hist["close"].tail(20).mean()
    ma50  = hist["close"].tail(50).mean() if len(hist) >= 50 else np.nan
    ret_5d  = (last_close / hist["close"].iloc[-6]  - 1) if len(hist) >= 6  else np.nan
    ret_20d = (last_close / hist["close"].iloc[-21] - 1) if len(hist) >= 21 else np.nan

    rets = hist["close"].pct_change().dropna().tail(30)
    rv = float(rets.std() * np.sqrt(252)) if len(rets) > 5 else np.nan
    hi_52w = hist["close"].tail(252).max() if len(hist) >= 20 else last_close
    dist_hi = last_close / hi_52w - 1

    def _f(v, fmt): return fmt.format(v) if pd.notna(v) else "n/a"

    lines = [
        f"  STOCK ({STOCK_TICKER}):",
        f"    Last close: ${_f(last_close, '{:.2f}')}   |   "
        f"vs 20d MA: {_f((last_close/ma20-1)*100, '{:+.1f}%')}   |   "
        f"vs 50d MA: {_f((last_close/ma50-1)*100 if pd.notna(ma50) else np.nan, '{:+.1f}%')}",
        f"    Trail 5d: {_f(ret_5d*100, '{:+.2f}%')}   |   "
        f"Trail 20d: {_f(ret_20d*100, '{:+.2f}%')}   |   "
        f"RVol(30d): {_f(rv*100, '{:.1f}%')} ann   |   "
        f"From 52w hi: {_f(dist_hi*100, '{:+.1f}%')}",
    ]

    # --- Macro regime ---
    def _trail_ret(col, n):
        if col not in hist.columns or len(hist) < n + 1:
            return np.nan
        v = hist[col].dropna()
        if len(v) < n + 1:
            return np.nan
        return v.iloc[-1] / v.iloc[-n-1] - 1

    spy_5d  = _trail_ret("spy_close", 5)
    spy_20d = _trail_ret("spy_close", 20)
    vix_now = hist["vix_close"].dropna().iloc[-1] if "vix_close" in hist.columns and not hist["vix_close"].dropna().empty else np.nan
    oil_now = hist["oil_close"].dropna().iloc[-1] if "oil_close" in hist.columns and not hist["oil_close"].dropna().empty else np.nan
    oil_5d  = _trail_ret("oil_close", 5)
    spy_dd  = last.get("spy_drawdown", np.nan) if "spy_drawdown" in hist.columns else np.nan

    # GOOGL vs SPY relative performance
    googl_vs_spy_5d = (ret_5d - spy_5d) if pd.notna(ret_5d) and pd.notna(spy_5d) else np.nan

    lines.append(f"  MACRO ENVIRONMENT:")
    lines.append(f"    S&P 500: trail 5d {_f(spy_5d*100 if pd.notna(spy_5d) else np.nan, '{:+.1f}%')}  |  "
                 f"trail 20d {_f(spy_20d*100 if pd.notna(spy_20d) else np.nan, '{:+.1f}%')}  |  "
                 f"drawdown {_f(spy_dd*100 if pd.notna(spy_dd) else np.nan, '{:+.1f}%')}")
    lines.append(f"    VIX: {_f(vix_now, '{:.1f}')}  |  "
                 f"Oil (WTI): ${_f(oil_now, '{:.1f}')} (5d {_f(oil_5d*100 if pd.notna(oil_5d) else np.nan, '{:+.1f}%')})")
    lines.append(f"    {STOCK_TICKER} vs S&P 500 (5d): {_f(googl_vs_spy_5d*100 if pd.notna(googl_vs_spy_5d) else np.nan, '{:+.1f}%')}"
                 f" ({'macro-driven' if pd.notna(googl_vs_spy_5d) and abs(googl_vs_spy_5d) < 0.02 else 'stock-specific move' if pd.notna(googl_vs_spy_5d) else 'n/a'})")

    # --- VIX regime tag ---
    if pd.notna(vix_now):
        if vix_now > 30:
            lines.append(f"    ⚠ ELEVATED VOLATILITY REGIME — macro dominates stock-specific news")
        elif vix_now > 20:
            lines.append(f"    NOTE: Above-average volatility — macro factors may dampen stock-specific signal")

    # --- Competitor read-through ---
    comp_lines = []
    for comp, label in [("meta_close", "META"), ("msft_close", "MSFT"), ("nvda_close", "NVDA")]:
        r5 = _trail_ret(comp, 5)
        if pd.notna(r5):
            comp_lines.append(f"{label} {_f(r5*100, '{:+.1f}%')}")
    if comp_lines:
        lines.append(f"  COMPETITORS (trailing 5d): {' | '.join(comp_lines)}")

    # --- Earnings proximity (nearest past or upcoming) ---
    earnings_list = price_df.attrs.get("earnings_dates", []) if hasattr(price_df, "attrs") else []
    if earnings_list:
        # Find nearest earnings date to article date
        diffs = [(abs((ed - d).days), (ed - d).days, ed) for ed in earnings_list]
        diffs.sort()
        if diffs:
            _, signed_days, nearest_ed = diffs[0]
            if -30 <= signed_days <= 30:  # within a month either side
                if signed_days > 0:
                    lines.append(f"  EARNINGS: next report in {signed_days} days "
                                 f"({nearest_ed.strftime('%b %d')})")
                    if signed_days <= 3:
                        lines.append(f"    ⚠ PRE-EARNINGS WINDOW — market in wait-and-see, "
                                     f"reduce materiality for non-earnings news")
                    elif signed_days <= 7:
                        lines.append(f"    NOTE: earnings within a week — pre-announcement "
                                     f"news carries elevated weight")
                elif signed_days == 0:
                    lines.append(f"  EARNINGS: reporting TODAY")
                else:
                    lines.append(f"  EARNINGS: reported {abs(signed_days)} day(s) ago "
                                 f"({nearest_ed.strftime('%b %d')})")
                    if signed_days >= -2:
                        lines.append(f"    NOTE: post-earnings reaction window — "
                                     f"price sensitive to related news")

    # --- Weekly macro narrative (geopolitical/market backdrop) ---
    if macro_narrative is not None and not macro_narrative.empty:
        macro_summary = get_macro_summary_for_date(d, macro_narrative)
        if macro_summary:
            lines.append(f"  MACRO BACKDROP (this week):")
            # Indent the summary
            for s_line in macro_summary.split("\n"):
                lines.append(f"    {s_line}")

    return "\n".join(lines)


def build_event_history_context(article_date, event_type: str,
                                  prior_scored: pd.DataFrame,
                                  scorer_name: str,
                                  lookback_days: int = 30) -> str:
    """
    Summarize the scorer's own prior canonical articles of the same event_type
    within the lookback window. This is the 'has this already been priced in?'
    signal — same-type event count + cumulative prior sentiment.

    prior_scored: dataframe of articles already scored by THIS scorer,
                  strictly before article_date. May be empty on warmup.
    """
    if prior_scored is None or prior_scored.empty:
        return "  - No prior scored articles (warmup window)"

    ev_col = f"{scorer_name}_event_type"
    sc_col = f"{scorer_name}_score"
    mt_col = f"{scorer_name}_materiality"
    if ev_col not in prior_scored.columns:
        return "  - No prior event-type data available yet"

    d = pd.to_datetime(article_date)
    cutoff = d - pd.Timedelta(days=lookback_days)
    prior = prior_scored.copy()
    prior["published"] = pd.to_datetime(prior["published"])
    window = prior[(prior["published"] < d) & (prior["published"] >= cutoff)]
    if "is_canonical" in window.columns:
        window = window[window["is_canonical"].fillna(True).astype(bool)]

    if window.empty:
        return f"  - No prior coverage in last {lookback_days}d"

    total_n = len(window)
    same_type = window[window[ev_col] == event_type]
    n_same = len(same_type)

    all_mean     = float(window[sc_col].mean())
    same_mean    = float(same_type[sc_col].mean()) if n_same > 0 else 0.0
    recent_7d    = window[window["published"] >= d - pd.Timedelta(days=7)]
    n_7d         = len(recent_7d)
    mean_7d      = float(recent_7d[sc_col].mean()) if n_7d > 0 else 0.0

    lines = [
        f"  - Prior coverage last {lookback_days}d: {total_n} canonical articles, "
        f"mean sentiment {all_mean:+.2f}",
        f"  - Same-type ({event_type}) last {lookback_days}d: {n_same} articles, "
        f"mean sentiment {same_mean:+.2f}",
        f"  - Very recent (last 7d):     {n_7d} articles, mean sentiment {mean_7d:+.2f}",
    ]
    # Pre-computed staleness hint
    if n_same >= 3 and abs(same_mean) > 0.3:
        lines.append(f"  - NOTE: This is the #{n_same+1} {event_type} article in {lookback_days}d — "
                     f"narrative may be saturated. Consider lower materiality if redundant.")
    return "\n".join(lines)


def build_user_prompt(title: str, body: str, published: str,
                       price_context: str = "",
                       event_history_context: str = "",
                       event_type_hint: str = "",
                       source: str = "") -> str:
    ctx_block = ""
    if price_context or event_history_context:
        ctx_block = (
            "\n\nCONTEXT AS OF ARTICLE DATE (use this to calibrate materiality):\n"
            + (price_context or "  (none)") +
            "\nPRIOR NEWS COVERAGE:\n" + (event_history_context or "  (none)")
        )
    source_line = f"\nSource: {source}" if source else ""
    return (
        f"Stock: {STOCK_NAME} ({STOCK_TICKER})\n"
        f"Sector: {STOCK_SECTOR}\n"
        f"Article date: {published}{source_line}\n"
        f"Headline: {title}\n"
        f"Body: {body[:1200]}"
        f"{ctx_block}"
    )


# ==========================================================================
# 3. SCORER INTERFACE
# ==========================================================================
class SentimentScorer:
    """Base class. Subclass and implement _score_one."""
    name: str = "base"
    uses_context: bool = False  # set True in subclasses that consume context

    def __init__(self):
        self.cache_path = os.path.join(CACHE_DIR, f"{self.name}.json")
        self.cache = {}
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r") as f:
                    self.cache = json.load(f)
            except Exception:
                self.cache = {}

    def _save_cache(self):
        with open(self.cache_path, "w") as f:
            json.dump(self.cache, f)

    def _key(self, article_id: str, context_hash: str = "") -> str:
        # Context-aware cache key: same article with different context
        # gets cached separately. context_hash is "" for stateless scorers.
        return hashlib.md5(f"{self.name}:{article_id}:{context_hash}".encode()).hexdigest()

    def _score_one(self, title: str, body: str, published: str,
                    price_context: str = "",
                    event_history_context: str = "",
                    source: str = "") -> dict:
        raise NotImplementedError

    def score_article(self, article_id: str, title: str, body: str, published: str,
                       price_context: str = "",
                       event_history_context: str = "",
                       source: str = "") -> dict:
        # Only hash context if this scorer actually uses it
        ctx_hash = ""
        if self.uses_context and (price_context or event_history_context):
            ctx_hash = hashlib.md5(
                (price_context + "||" + event_history_context).encode()
            ).hexdigest()[:12]
        k = self._key(article_id, ctx_hash)
        if k in self.cache:
            cached = self.cache[k]
            # Repair: if we previously cached an error result (from a failed
            # API call or missing library), re-attempt scoring now. Error
            # results are identified by reasoning starting with "error:".
            reasoning = cached.get("reasoning", "") if isinstance(cached, dict) else ""
            if not (isinstance(reasoning, str) and reasoning.startswith("error:")):
                return cached
            # Otherwise fall through and retry
        try:
            result = self._score_one(title, body, published,
                                      price_context=price_context,
                                      event_history_context=event_history_context,
                                      source=source)
            # Only cache SUCCESSFUL results — not errors.
            self.cache[k] = result
            return result
        except Exception as e:
            # Log the first few errors per scorer to help diagnose refusals
            # (e.g., Claude safety filter, Gemini refusal, malformed JSON)
            if not hasattr(self, "_errors_logged"):
                self._errors_logged = 0
            if self._errors_logged < 5:
                print(f"  [{self.name}] score error: {type(e).__name__}: {str(e)[:200]}")
                self._errors_logged += 1
            # Return zero result WITHOUT caching — next run will retry
            return {"score": 0.0, "confidence": 0.0, "materiality": 0.0,
                    "horizon": "days", "event_type": "other",
                    "reasoning": f"error: {e}"}


    def score_batch(self, articles: pd.DataFrame, max_workers: int = 8,
                     price_df: pd.DataFrame = None,
                     macro_narrative: pd.DataFrame = None,
                     chunk_size: int = 20) -> pd.DataFrame:
        """
        Score articles in time-ordered chunks. Each chunk is parallelized
        across threads. Between chunks, the accumulated scored history is
        used to build context for the next chunk. This gives ~95% of the
        parallelism benefit while still producing meaningful event history.

        Non-canonical articles are skipped entirely (they're duplicates).
        """
        print(f"  [{self.name}] scoring {len(articles)} articles"
              f"{' with context' if self.uses_context else ''}...")

        df = articles.reset_index(drop=True).copy()
        df["published"] = pd.to_datetime(df["published"])
        df = df.sort_values("published").reset_index(drop=True)

        # Split canonical vs non-canonical. Non-canonical get zero-scored.
        if "is_canonical" in df.columns:
            canonical_mask = df["is_canonical"].fillna(True).astype(bool)
        else:
            canonical_mask = pd.Series(True, index=df.index)

        n = len(df)
        results = [None] * n

        # Pre-fill non-canonical with zero results (they contribute nothing)
        zero_result = {"score": 0.0, "confidence": 0.0, "materiality": 0.0,
                       "horizon": "days", "event_type": "other",
                       "reasoning": "duplicate (non-canonical)"}
        for i in range(n):
            if not canonical_mask.iloc[i]:
                results[i] = zero_result

        # Accumulating scored history — grows as chunks complete
        scored_so_far = df.iloc[:0].copy()
        score_cols = [f"{self.name}_score", f"{self.name}_confidence",
                      f"{self.name}_materiality", f"{self.name}_event_type"]
        for c in score_cols:
            scored_so_far[c] = pd.Series(dtype=object)

        canonical_indices = [i for i in range(n) if canonical_mask.iloc[i]]

        for chunk_start in range(0, len(canonical_indices), chunk_size):
            chunk_idx = canonical_indices[chunk_start:chunk_start + chunk_size]

            # Build context for each article in the chunk — based on scored_so_far
            # (frozen snapshot so all parallel workers see the same history)
            contexts = {}
            for i in chunk_idx:
                row = df.iloc[i]
                if self.uses_context and price_df is not None:
                    # We don't yet know event_type of this article → use "other"
                    # as a placeholder. The history filter widens to ALL types when
                    # the hint is "other", so we get total prior count.
                    pc = build_price_context(row["published"], price_df,
                                              macro_narrative=macro_narrative)
                    eh = build_event_history_context(
                        row["published"], "other", scored_so_far, self.name
                    )
                    contexts[i] = (pc, eh)
                else:
                    contexts[i] = ("", "")

            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                futs = {}
                for i in chunk_idx:
                    row = df.iloc[i]
                    pc, eh = contexts[i]
                    src = row.get("source", "") if "source" in df.columns else ""
                    futs[ex.submit(
                        self.score_article,
                        row["id"], row["title"], row["body"], str(row["published"]),
                        pc, eh, src,
                    )] = i
                for fut in as_completed(futs):
                    i = futs[fut]
                    try:
                        results[i] = fut.result()
                    except Exception as e:
                        results[i] = {"score": 0.0, "confidence": 0.0,
                                      "materiality": 0.0, "horizon": "days",
                                      "event_type": "other",
                                      "reasoning": f"error: {e}"}

            # Fold this chunk's results into scored_so_far before next chunk
            chunk_df = df.iloc[chunk_idx].copy()
            chunk_df[f"{self.name}_score"]       = [results[i]["score"]       for i in chunk_idx]
            chunk_df[f"{self.name}_confidence"]  = [results[i]["confidence"]  for i in chunk_idx]
            chunk_df[f"{self.name}_materiality"] = [results[i]["materiality"] for i in chunk_idx]
            chunk_df[f"{self.name}_event_type"]  = [results[i].get("event_type", "other")
                                                     for i in chunk_idx]
            scored_so_far = pd.concat([scored_so_far, chunk_df], ignore_index=True)

        self._save_cache()

        out = df.copy()
        out[f"{self.name}_score"]       = [r["score"]       for r in results]
        out[f"{self.name}_confidence"]  = [r["confidence"]  for r in results]
        out[f"{self.name}_materiality"] = [r["materiality"] for r in results]
        out[f"{self.name}_event_type"]  = [r.get("event_type", "other") for r in results]
        return out


# ------------------- 3a. OpenRouter LLM scorer ----------------------------
class OpenRouterScorer(SentimentScorer):
    uses_context = True

    def __init__(self, model_id: str, nickname: str):
        _require_api_key(OPENROUTER_KEY, "OPENROUTER_API_KEY")
        self.model_id = model_id
        self.name = nickname
        super().__init__()

    def _score_one(self, title: str, body: str, published: str,
                    price_context: str = "",
                    event_history_context: str = "",
                    source: str = "") -> dict:
        sys_msg = ANALYST_SYSTEM_PROMPT.format(
            stock_name=STOCK_NAME, sector=STOCK_SECTOR
        )
        user_msg = build_user_prompt(
            title, body, published,
            price_context=price_context,
            event_history_context=event_history_context,
            source=source,
        )

        # Strict JSON schema forces the model to emit exactly the keys we want
        # in the right types. Not all providers support json_schema — fall back
        # to json_object if the strict schema is rejected.
        schema = {
            "type": "object",
            "properties": {
                "reasoning":   {"type": "string"},
                "score":       {"type": "number", "minimum": -1.0, "maximum": 1.0},
                "confidence":  {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "materiality": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "horizon":     {"type": "string",
                                "enum": ["intraday", "days", "weeks", "months"]},
                "event_type":  {"type": "string", "enum": EVENT_TYPES},
            },
            "required": ["score", "confidence", "materiality", "event_type", "reasoning"],
            "additionalProperties": False,
        }

        def _try_post(response_format):
            return requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_KEY}"},
                json={
                    "model": self.model_id,
                    "messages": [
                        {"role": "system", "content": sys_msg},
                        {"role": "user",   "content": user_msg},
                    ],
                    "response_format": response_format,
                    "temperature": 0.1,
                },
                timeout=40,
            )

        # Try strict schema first
        resp = _try_post({
            "type": "json_schema",
            "json_schema": {
                "name": "sentiment_score",
                "strict": True,
                "schema": schema,
            },
        })
        # Fall back to looser json_object if provider doesn't support strict schema
        if resp.status_code != 200:
            resp = _try_post({"type": "json_object"})
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")

        # Robust response parsing — providers return inconsistent formats
        try:
            resp_json = resp.json()
        except Exception as e:
            raise RuntimeError(f"Non-JSON response: {resp.text[:200]}") from e

        choices = resp_json.get("choices")
        if not choices or not isinstance(choices, list) or len(choices) == 0:
            # Some providers return {"error": ...} instead of choices on refusal
            err_msg = resp_json.get("error", {})
            if isinstance(err_msg, dict):
                err_msg = err_msg.get("message", str(err_msg))
            raise RuntimeError(f"No choices in response: {err_msg or resp.text[:200]}")

        content = choices[0].get("message", {}).get("content", "")
        if not content or not content.strip():
            # Empty content = refusal or model failed to emit anything
            raise RuntimeError("Empty content (likely safety refusal or model error)")

        # Try direct parse first
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            # Salvage: some models wrap JSON in markdown fences or prose
            # Try to extract first {...} block
            import re
            m = re.search(r'\{.*\}', content, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group(0))
                except json.JSONDecodeError:
                    # Still malformed — try removing any trailing junk after last }
                    candidate = m.group(0)
                    last_brace = candidate.rfind('}')
                    if last_brace > 0:
                        data = json.loads(candidate[:last_brace+1])
                    else:
                        raise
            else:
                raise

        et = data.get("event_type", "other")
        if et not in EVENT_TYPES:
            et = "other"
        return {
            "score":       float(np.clip(data.get("score", 0.0), -1, 1)),
            "confidence":  float(np.clip(data.get("confidence", 0.5), 0, 1)),
            "materiality": float(np.clip(data.get("materiality", 0.5), 0, 1)),
            "horizon":     data.get("horizon", "days"),
            "event_type":  et,
            "reasoning":   data.get("reasoning", "")[:300],
        }


# ------------------- 3b. FinBERT scorer -----------------------------------
class FinBERTScorer(SentimentScorer):
    name = "finbert"

    def __init__(self):
        super().__init__()
        self._pipe = None

    def _ensure_loaded(self):
        if self._pipe is None:
            from transformers import (
                AutoTokenizer, AutoModelForSequenceClassification, pipeline
            )
            tok = AutoTokenizer.from_pretrained("ProsusAI/finbert")
            mdl = AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert")
            self._pipe = pipeline("sentiment-analysis", model=mdl, tokenizer=tok,
                                  top_k=None, truncation=True, max_length=512)

    def _score_one(self, title: str, body: str, published: str,
                    price_context: str = "",
                    event_history_context: str = "",
                    source: str = "") -> dict:
        self._ensure_loaded()
        text = (title + ". " + body)[:1500]
        out = self._pipe(text)[0]  # list of {label, score}
        probs = {d["label"].lower(): d["score"] for d in out}
        # Map to signed score: positive - negative, weighted by (1 - neutral)
        signed = probs.get("positive", 0) - probs.get("negative", 0)
        conf = max(probs.values()) if probs else 0.5
        materiality = 1.0 - probs.get("neutral", 0.0)
        return {
            "score": float(signed),
            "confidence": float(conf),
            "materiality": float(materiality),
            "horizon": "days",
            "event_type": "other",
            "reasoning": f"finbert probs: {probs}",
        }

    def score_batch(self, articles, max_workers=1, price_df=None,
                      macro_narrative=None, chunk_size=20):
        # FinBERT is local — don't parallelize across threads.
        return super().score_batch(articles, max_workers=1,
                                    price_df=price_df,
                                    macro_narrative=macro_narrative,
                                    chunk_size=chunk_size)


# ------------------- 3c. VADER lexicon baseline ---------------------------
class VaderScorer(SentimentScorer):
    name = "vader"

    def __init__(self):
        super().__init__()
        self._analyzer = None

    def _ensure_loaded(self):
        if self._analyzer is None:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            self._analyzer = SentimentIntensityAnalyzer()

    def _score_one(self, title: str, body: str, published: str,
                    price_context: str = "",
                    event_history_context: str = "",
                    source: str = "") -> dict:
        self._ensure_loaded()
        text = title + ". " + body[:1000]
        s = self._analyzer.polarity_scores(text)
        return {
            "score": float(s["compound"]),
            "confidence": float(abs(s["compound"])),
            "materiality": float(1 - s["neu"]),
            "horizon": "days",
            "event_type": "other",
            "reasoning": f"vader: {s}",
        }

    def score_batch(self, articles, max_workers=1, price_df=None,
                      macro_narrative=None, chunk_size=20):
        return super().score_batch(articles, max_workers=1,
                                    price_df=price_df,
                                    macro_narrative=macro_narrative,
                                    chunk_size=chunk_size)


# ==========================================================================
# 4. MARKET DATA (minimal — we only need close prices)
# ==========================================================================
def get_prices(ticker: str, start: str) -> pd.DataFrame:
    print(f"Fetching prices for {ticker} + macro indicators...")
    yf = _lazy_yfinance()

    # Main stock
    df = yf.Ticker(ticker).history(start=start, interval="1d", auto_adjust=True)
    df = df.reset_index()
    date_col = [c for c in df.columns if "date" in str(c).lower()][0]
    df[date_col] = pd.to_datetime(df[date_col]).dt.tz_localize(None)
    df = df.rename(columns={date_col: "date"})
    df.columns = [c.lower() for c in df.columns]
    df["fwd_ret_1d"] = df["close"].shift(-1) / df["close"] - 1
    df["fwd_ret_5d"] = df["close"].shift(-5) / df["close"] - 1

    # Realized volatility
    df["rvol_20d"] = df["close"].pct_change().rolling(20).std() * np.sqrt(252)

    # Macro: SPY, VIX, Oil + competitors
    macro_tickers = {
        "spy": "SPY", "vix": "^VIX", "oil": "CL=F",
        "meta": "META", "msft": "MSFT", "nvda": "NVDA",
    }
    for col_name, mticker in macro_tickers.items():
        try:
            mdf = yf.Ticker(mticker).history(start=start, interval="1d", auto_adjust=True)
            mdf = mdf.reset_index()
            md = [c for c in mdf.columns if "date" in str(c).lower()][0]
            mdf[md] = pd.to_datetime(mdf[md]).dt.tz_localize(None)
            mdf = mdf.rename(columns={md: "date", "Close": f"{col_name}_close",
                                       "close": f"{col_name}_close"})
            mdf.columns = [c.lower() for c in mdf.columns]
            if f"{col_name}_close" not in mdf.columns:
                close_col = [c for c in mdf.columns if "close" in c and c != "close"][0]
                mdf = mdf.rename(columns={close_col: f"{col_name}_close"})
            df = df.merge(mdf[["date", f"{col_name}_close"]], on="date", how="left")
            print(f"  + {mticker} ({col_name})")
        except Exception as e:
            print(f"  ! {mticker} failed: {e}")
            df[f"{col_name}_close"] = np.nan

    # SPY drawdown from rolling max
    if "spy_close" in df.columns:
        spy_max = df["spy_close"].cummax()
        df["spy_drawdown"] = df["spy_close"] / spy_max - 1

    # Earnings dates (historical + upcoming)
    try:
        tk = yf.Ticker(ticker)
        earnings_dates_list = []
        # Historical earnings dates (yfinance returns a DataFrame indexed by date)
        try:
            ed = tk.earnings_dates
            if ed is not None and not ed.empty:
                earnings_dates_list.extend([
                    pd.to_datetime(d).tz_localize(None) if pd.to_datetime(d).tzinfo is not None
                    else pd.to_datetime(d)
                    for d in ed.index
                ])
        except Exception:
            pass
        # Calendar (upcoming)
        try:
            cal = tk.calendar
            if cal is not None:
                if isinstance(cal, pd.DataFrame) and not cal.empty:
                    earnings_dates_list.append(pd.to_datetime(cal.iloc[0, 0]))
                elif isinstance(cal, dict):
                    edates = cal.get("Earnings Date", [])
                    if edates:
                        earnings_dates_list.append(pd.to_datetime(edates[0]))
        except Exception:
            pass

        # Deduplicate and sort
        earnings_dates_list = sorted(set(pd.to_datetime(d).normalize()
                                          for d in earnings_dates_list
                                          if pd.notna(d)))
        df.attrs["earnings_dates"] = earnings_dates_list
        print(f"  + Earnings dates: {len(earnings_dates_list)} "
              f"({earnings_dates_list[0].date() if earnings_dates_list else 'none'} → "
              f"{earnings_dates_list[-1].date() if earnings_dates_list else 'none'})")
    except Exception as e:
        df.attrs["earnings_dates"] = []
        print(f"  ! earnings dates failed: {e}")

    print(f"  -> {len(df)} trading days")
    return df


# ==========================================================================
# 5. NEWS
# ==========================================================================
def fetch_news(start_date, end_date) -> pd.DataFrame:
    """
    Fetch GOOGL-relevant news using EventRegistry's CONCEPT search (not keywords).

    Three layers of quality filtering:
      1) API-LEVEL: conceptUri resolves to Wikipedia entities (Alphabet Inc, not
         the string "Google" in a bibliography). categoryUri restricts to
         business/tech. sourceRankPercentile restricts to top-30% sources.
         isDuplicateFilter skips wire-service dupes. Sorted by relevance.
      2) POST-FETCH BODY GATE: articles with <100 chars of body, or where none
         of the concept terms appear in title+body[:300], are dropped as noise.
      3) DOWNSTREAM: cluster_articles() deduplicates near-identical stories.
    """
    print(f"\nFetching news {start_date} -> {end_date}")
    print("  Using concept-based search (entity resolution, not keyword match)")
    _require_api_key(EVENT_REGISTRY_KEY, "NEWS_API_KEY")
    (EventRegistry, QueryArticlesIter, ReturnInfo,
     ArticleInfoFlags, QueryItems) = _lazy_eventregistry()
    er = EventRegistry(apiKey=EVENT_REGISTRY_KEY)

    # --- Resolve concepts to URIs (entity IDs, not strings) ---
    concept_uris = []
    for label in STOCK_CONCEPTS:
        try:
            uri = er.getConceptUri(label)
            if uri:
                concept_uris.append(uri)
                print(f"    concept '{label}' -> {uri}")
        except Exception as e:
            print(f"    warning: could not resolve concept '{label}': {e}")

    if not concept_uris:
        print("  ERROR: No concepts resolved. Falling back to keyword search.")
        return _fetch_news_keyword_fallback(start_date, end_date, er,
                                             QueryArticlesIter, ReturnInfo,
                                             ArticleInfoFlags, QueryItems)

    # --- Resolve category URIs (list-based; reads module-level FETCH_CATEGORIES) ---
    # Default is ["business"] which preserves exact prior behavior. Override the
    # module-level constant from a driver script to widen coverage (e.g. ["business",
    # "technology", "automotive"]) for tickers whose news density is split across
    # sector-specific categories.
    category_uris = []
    for cat_label in FETCH_CATEGORIES:
        try:
            uri = er.getCategoryUri(cat_label)
            if uri:
                category_uris.append(uri)
                print(f"    category '{cat_label}' -> {uri}")
        except Exception:
            print(f"    warning: could not resolve category '{cat_label}'")

    # --- Resolve source URIs to EXCLUDE at API level ---
    # These are known auto-generators of 13F filings, holdings spam, and
    # boilerplate stock roundups. Excluding them at the API level means
    # the article slots are filled with real journalism instead.
    sources_to_exclude = [
        "Defense World", "ETF Daily News", "MarketBeat",
        "Ticker Report", "Daily Political",
    ]
    ignore_source_uris = []
    for src in sources_to_exclude:
        try:
            uri = er.getNewsSourceUri(src)
            if uri:
                ignore_source_uris.append(uri)
                print(f"    excluding source '{src}' -> {uri}")
        except Exception:
            pass  # source not found — skip silently

    # --- Fetch in monthly windows ---
    rows = []
    cur = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)

    while cur < end:
        nxt = min(cur + timedelta(days=30), end)
        print(f"  {cur.strftime('%Y-%m-%d')} -> {nxt.strftime('%Y-%m-%d')}...", end=" ")

        try:
            query_kwargs = dict(
                conceptUri=QueryItems.OR(concept_uris),
                lang="eng",
                dateStart=cur.strftime("%Y-%m-%d"),
                dateEnd=nxt.strftime("%Y-%m-%d"),
                isDuplicateFilter="skipDuplicates",
                startSourceRankPercentile=0,
                endSourceRankPercentile=FETCH_SOURCE_RANK_PCTILE_END,
                dataType=["news", "blog"],
            )
            if category_uris:
                # OR across multiple categories so an article in ANY of them matches.
                # For a single category (default GOOGL case), this is equivalent to
                # the prior scalar categoryUri=business_cat.
                query_kwargs["categoryUri"] = (
                    QueryItems.OR(category_uris) if len(category_uris) > 1
                    else category_uris[0]
                )
            if ignore_source_uris:
                query_kwargs["ignoreSourceUri"] = ignore_source_uris

            q = QueryArticlesIter(**query_kwargs)
            month_count = 0
            for art in q.execQuery(
                er,
                sortBy="rel",
                returnInfo=ReturnInfo(
                    articleInfo=ArticleInfoFlags(body=True, concepts=True)
                ),
                maxItems=MAX_ARTICLES_PER_MONTH,
            ):
                body = (art.get("body") or "")[:1500]
                rows.append({
                    "id":        art.get("uri"),
                    "title":     art.get("title", ""),
                    "published": art.get("dateTime") or art.get("date"),
                    "body":      body,
                    "source":    art.get("source", {}).get("title", ""),
                })
                month_count += 1
            print(f"{month_count} articles")
        except Exception as e:
            print(f"error: {e}")
        cur = nxt

    df = pd.DataFrame(rows)
    if df.empty:
        print("  -> 0 articles (empty)")
        return df

    df["published"] = pd.to_datetime(df["published"], utc=True, errors="coerce")
    df["published"] = df["published"].dt.tz_localize(None)
    df = df.drop_duplicates(subset=["id"]).sort_values("published").reset_index(drop=True)

    # --- POST-FETCH BODY QUALITY GATE ---
    pre_filter = len(df)

    # Gate 1: minimum body length (academic citation lists are short fragments)
    df = df[df["body"].str.len() >= 100].reset_index(drop=True)

    # Gate 2: at least one relevance term must appear in title or first 300 chars of body
    relevance_terms = ["google", "alphabet", "googl", "youtube", "sundar",
                       "pichai", "android", "chrome", "waymo", "deepmind",
                       "gemini", "cloud", "pixel", "ads", "search"]
    def _is_relevant(row):
        text = (row["title"] + " " + row["body"][:300]).lower()
        return any(term in text for term in relevance_terms)
    df = df[df.apply(_is_relevant, axis=1)].reset_index(drop=True)

    # Gate 3: 13F / institutional filing spam filter.
    # Sites like Defense World auto-generate articles from SEC 13F filings:
    # "[Fund Name] Buys/Sells X Shares of Alphabet Inc."
    # These are real GOOGL articles but carry zero sentiment signal — they're
    # machine-generated boilerplate about quarterly position disclosures.
    import re
    _13f_pattern = re.compile(
        r"(shares?\s+(of|in|sold|bought|purchased|acquired)|"
        r"(buys|sells|acquires|purchases|cuts|trims|lowers|raises|increases|reduces|invests)"
        r"\s+(\$[\d,.]+\s+in\s+|new\s+)?(stake|position|holdings?|shares?)|"
        r"(buys|sells|acquires|purchases|cuts|trims|lowers|raises|increases|reduces|invests)"
        r"\s+\$[\d,.]+\s+in\s|"
        r"(largest|biggest)\s+position|"
        r"stock\s+position\s+in|"
        r"holdings?\s+(trimmed|lowered|raised|increased|cut|reduced)\s+by)",
        re.IGNORECASE
    )
    def _is_13f_spam(title):
        return bool(_13f_pattern.search(title))
    n_before_13f = len(df)
    df = df[~df["title"].apply(_is_13f_spam)].reset_index(drop=True)
    n_13f_dropped = n_before_13f - len(df)
    if n_13f_dropped > 0:
        print(f"  13F filing spam filter dropped {n_13f_dropped} articles")

    # Gate 4: source blacklist for known low-signal auto-generators
    source_blacklist = [
        "defense world",       # 13F filing article farm
        "etfdailynews",        # ETF holdings spam
        "marketbeat",          # auto-generated holdings/ratings roundups
        "tickerreport",        # same
        "dailypolitical",      # same
    ]
    def _is_blacklisted_source(source):
        return any(bl in str(source).lower() for bl in source_blacklist)
    n_before_bl = len(df)
    df = df[~df["source"].apply(_is_blacklisted_source)].reset_index(drop=True)
    n_bl_dropped = n_before_bl - len(df)
    if n_bl_dropped > 0:
        print(f"  Source blacklist dropped {n_bl_dropped} articles")

    dropped = pre_filter - len(df)
    if dropped > 0:
        print(f"  Total quality gate: {dropped}/{pre_filter} articles dropped")

    print(f"  -> {len(df)} clean articles")
    return df


def _fetch_news_keyword_fallback(start_date, end_date, er,
                                   QueryArticlesIter, ReturnInfo,
                                   ArticleInfoFlags, QueryItems) -> pd.DataFrame:
    """Legacy keyword search — only used if concept resolution fails entirely."""
    print("  WARNING: using keyword fallback (lower quality)")
    fallback_keywords = ["Alphabet Inc", "GOOGL", "Google earnings",
                         "Google Cloud", "YouTube revenue"]
    rows = []
    cur = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    while cur < end:
        nxt = min(cur + timedelta(days=30), end)
        try:
            q = QueryArticlesIter(
                keywords=QueryItems.OR(fallback_keywords),
                keywordsLoc="title",   # keywords must be in TITLE, not body
                lang="eng",
                dateStart=cur.strftime("%Y-%m-%d"),
                dateEnd=nxt.strftime("%Y-%m-%d"),
                isDuplicateFilter="skipDuplicates",
                startSourceRankPercentile=0,
                endSourceRankPercentile=30,
            )
            for art in q.execQuery(
                er,
                sortBy="rel",
                returnInfo=ReturnInfo(articleInfo=ArticleInfoFlags(body=True)),
                maxItems=MAX_ARTICLES_PER_MONTH,
            ):
                rows.append({
                    "id":        art.get("uri"),
                    "title":     art.get("title", ""),
                    "published": art.get("dateTime") or art.get("date"),
                    "body":      (art.get("body") or "")[:1500],
                    "source":    art.get("source", {}).get("title", ""),
                })
        except Exception as e:
            print(f"  error: {e}")
        cur = nxt
    df = pd.DataFrame(rows)
    if not df.empty:
        df["published"] = pd.to_datetime(df["published"], utc=True, errors="coerce")
        df["published"] = df["published"].dt.tz_localize(None)
        df = df.drop_duplicates(subset=["id"]).sort_values("published").reset_index(drop=True)
    print(f"  -> {len(df)} articles (keyword fallback)")
    return df


def load_or_fetch_news(start_date, end_date):
    if os.path.exists(NEWS_FILE):
        df = pd.read_csv(NEWS_FILE)
        if len(df) > 50:
            df["published"] = pd.to_datetime(df["published"], errors="coerce")
            print(f"Loaded cached news: {len(df)} articles from {NEWS_FILE}")
            return df
    df = fetch_news(start_date, end_date)
    if not df.empty:
        df.to_csv(NEWS_FILE, index=False)
    return df


# ==========================================================================
# 5a. WEEKLY MACRO NARRATIVE (separate from GOOGL-specific news)
# ==========================================================================
MACRO_NEWS_FILE = os.path.join(DATA_DIR, "macro_narrative.csv")
MACRO_SUMMARIZER_MODEL = "deepseek/deepseek-v3.2"


def _fetch_weekly_macro_headlines(start_date, end_date) -> pd.DataFrame:
    """
    Fetch top macro/geopolitical headlines week by week.
    This is SEPARATE from GOOGL news — these are broad market-moving events
    (wars, Fed decisions, oil shocks, trade disputes) that explain price
    action that can't be attributed to company-specific news.
    """
    _require_api_key(EVENT_REGISTRY_KEY, "NEWS_API_KEY")
    (EventRegistry, QueryArticlesIter, ReturnInfo,
     ArticleInfoFlags, QueryItems) = _lazy_eventregistry()
    er = EventRegistry(apiKey=EVENT_REGISTRY_KEY)

    # Broad macro concepts
    macro_concept_labels = [
        "Federal Reserve", "Stock market",
        "Geopolitics", "Crude oil", "Inflation",
    ]
    concept_uris = []
    for label in macro_concept_labels:
        try:
            uri = er.getConceptUri(label)
            if uri:
                concept_uris.append(uri)
        except Exception as e:
            print(f"  macro concept resolve failed for '{label}': {e}")
    print(f"  resolved {len(concept_uris)}/{len(macro_concept_labels)} macro concepts")

    try:
        business_cat = er.getCategoryUri("business")
    except Exception:
        business_cat = None

    # Exclude the usual spam
    sources_to_exclude = ["Defense World", "ETF Daily News", "MarketBeat",
                          "Ticker Report", "Daily Political"]
    ignore_source_uris = []
    for src in sources_to_exclude:
        try:
            uri = er.getNewsSourceUri(src)
            if uri:
                ignore_source_uris.append(uri)
        except Exception:
            pass

    rows = []
    cur = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    weeks_processed = 0
    weeks_empty = 0
    while cur < end:
        nxt = min(cur + timedelta(days=7), end)
        weeks_processed += 1
        week_arts = []

        # --- Attempt 1: tight filter (concepts + business + top 15%) ---
        try:
            kwargs = dict(
                lang="eng",
                dateStart=cur.strftime("%Y-%m-%d"),
                dateEnd=nxt.strftime("%Y-%m-%d"),
                isDuplicateFilter="skipDuplicates",
                startSourceRankPercentile=0,
                endSourceRankPercentile=15,
                dataType=["news"],
            )
            if concept_uris:
                kwargs["conceptUri"] = QueryItems.OR(concept_uris)
            if business_cat:
                kwargs["categoryUri"] = business_cat
            if ignore_source_uris:
                kwargs["ignoreSourceUri"] = ignore_source_uris
            q = QueryArticlesIter(**kwargs)
            for art in q.execQuery(
                er, sortBy="rel",
                returnInfo=ReturnInfo(articleInfo=ArticleInfoFlags(body=True)),
                maxItems=10,
            ):
                week_arts.append({
                    "week_start": cur.strftime("%Y-%m-%d"),
                    "title": art.get("title", ""),
                    "body": (art.get("body") or "")[:500],
                })
        except Exception as e:
            print(f"  macro tight query week {cur.date()}: {e}")

        # --- Attempt 2 (fallback): broader — drop business category, widen percentile ---
        if len(week_arts) == 0:
            try:
                kwargs = dict(
                    lang="eng",
                    dateStart=cur.strftime("%Y-%m-%d"),
                    dateEnd=nxt.strftime("%Y-%m-%d"),
                    isDuplicateFilter="skipDuplicates",
                    startSourceRankPercentile=0,
                    endSourceRankPercentile=30,
                    dataType=["news"],
                )
                if concept_uris:
                    kwargs["conceptUri"] = QueryItems.OR(concept_uris)
                if ignore_source_uris:
                    kwargs["ignoreSourceUri"] = ignore_source_uris
                q = QueryArticlesIter(**kwargs)
                for art in q.execQuery(
                    er, sortBy="rel",
                    returnInfo=ReturnInfo(articleInfo=ArticleInfoFlags(body=True)),
                    maxItems=10,
                ):
                    week_arts.append({
                        "week_start": cur.strftime("%Y-%m-%d"),
                        "title": art.get("title", ""),
                        "body": (art.get("body") or "")[:500],
                    })
            except Exception as e:
                print(f"  macro fallback query week {cur.date()}: {e}")

        # --- Attempt 3 (final fallback): keyword search ---
        if len(week_arts) == 0:
            try:
                kwargs = dict(
                    keywords="Federal Reserve OR stocks OR inflation OR oil OR war",
                    lang="eng",
                    dateStart=cur.strftime("%Y-%m-%d"),
                    dateEnd=nxt.strftime("%Y-%m-%d"),
                    isDuplicateFilter="skipDuplicates",
                    dataType=["news"],
                )
                q = QueryArticlesIter(**kwargs)
                for art in q.execQuery(
                    er, sortBy="rel",
                    returnInfo=ReturnInfo(articleInfo=ArticleInfoFlags(body=True)),
                    maxItems=10,
                ):
                    week_arts.append({
                        "week_start": cur.strftime("%Y-%m-%d"),
                        "title": art.get("title", ""),
                        "body": (art.get("body") or "")[:500],
                    })
            except Exception as e:
                print(f"  macro keyword query week {cur.date()}: {e}")

        rows.extend(week_arts)
        if len(week_arts) == 0:
            weeks_empty += 1
        cur = nxt

    print(f"  macro fetch complete: {weeks_processed} weeks, {weeks_empty} empty, {len(rows)} total articles")
    return pd.DataFrame(rows)


def _summarize_week(week_start: str, articles: list) -> str:
    """One LLM call per week: summarize top headlines into 2-3 sentence backdrop."""
    if not articles:
        return ""

    headlines_block = "\n".join(
        f"- {a['title']}: {a['body'][:200]}" for a in articles[:8]
    )
    prompt = (
        f"Summarize the most important macro and geopolitical developments "
        f"of the week starting {week_start} in 2-3 sentences. Focus on "
        f"events that would move the broad US stock market (Fed policy, "
        f"wars, oil shocks, trade disputes, recession signals). "
        f"Be factual and specific. Do not speculate.\n\n"
        f"HEADLINES FROM THIS WEEK:\n{headlines_block}\n\n"
        f"2-3 sentence summary:"
    )

    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_KEY}"},
            json={
                "model": MACRO_SUMMARIZER_MODEL,
                "messages": [
                    {"role": "system", "content": "You are a financial analyst. "
                                                    "Respond with only the summary, no preamble."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
            },
            timeout=40,
        )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"  macro summarize failed for {week_start}: {e}")
    return ""


def build_macro_narrative(start_date, end_date) -> pd.DataFrame:
    """
    Build week-by-week macro narrative using DeepSeek summaries.
    Cached to disk so it only runs once.

    Returns DataFrame with columns: week_start (Timestamp), summary (str)
    """
    if os.path.exists(MACRO_NEWS_FILE):
        try:
            df = pd.read_csv(MACRO_NEWS_FILE)
            df["week_start"] = pd.to_datetime(df["week_start"])
            print(f"Loaded cached macro narrative: {len(df)} weeks")
            return df
        except Exception:
            pass

    print("\nBuilding weekly macro narrative (one DeepSeek call per week)...")
    raw = _fetch_weekly_macro_headlines(start_date, end_date)
    if raw.empty:
        print("  no macro headlines fetched — skipping macro narrative")
        return pd.DataFrame(columns=["week_start", "summary"])

    summaries = []
    weeks = raw.groupby("week_start")
    for week_start, group in weeks:
        arts = group.to_dict("records")
        summary = _summarize_week(week_start, arts)
        if summary:
            summaries.append({"week_start": week_start, "summary": summary})
            print(f"  {week_start}: {summary[:100]}...")

    out = pd.DataFrame(summaries)
    if not out.empty:
        out["week_start"] = pd.to_datetime(out["week_start"])
        out.to_csv(MACRO_NEWS_FILE, index=False)
        print(f"  -> saved {len(out)} weekly summaries to {MACRO_NEWS_FILE}")
    return out


def get_macro_summary_for_date(d, macro_df: pd.DataFrame) -> str:
    """Return the macro summary for the week containing date d."""
    if macro_df is None or macro_df.empty:
        return ""
    d = pd.to_datetime(d).normalize()
    past = macro_df[macro_df["week_start"] <= d]
    if past.empty:
        return ""
    latest = past.iloc[-1]
    return latest["summary"]


# ==========================================================================
# 5b. EVENT CLUSTERING / DEDUPLICATION (SOTA upgrade 3)
# ==========================================================================
def cluster_articles(news_df: pd.DataFrame,
                     sim_threshold: float = EVENT_SIM_THRESHOLD,
                     time_window_days: int = EVENT_TIME_WINDOW_DAYS) -> pd.DataFrame:
    """
    TF-IDF cosine similarity + greedy temporal clustering.
    Near-duplicate articles within a rolling time window are collapsed into
    one "event". Only the EARLIEST article in each cluster is marked canonical.
    Non-canonical articles will get score=0 downstream, so each event contributes
    to the daily sentiment exactly once — implementing both dedup and novelty
    filtering in one pass.
    """
    if news_df.empty:
        return news_df.assign(cluster_id=[], is_canonical=[])

    df = news_df.sort_values("published").reset_index(drop=True).copy()
    df["published"] = pd.to_datetime(df["published"])

    texts = (df["title"].fillna("") + " " + df["body"].fillna("").str[:400]).tolist()
    vec = TfidfVectorizer(max_features=5000, ngram_range=(1, 2),
                          stop_words="english", min_df=2)
    try:
        X = vec.fit_transform(texts)
    except ValueError:
        # not enough docs / vocab — everything gets its own cluster
        df["cluster_id"] = range(len(df))
        df["is_canonical"] = True
        return df

    sim = cosine_similarity(X)

    cluster_ids = [-1] * len(df)
    next_cid = 0
    times = df["published"].values

    for i in range(len(df)):
        if cluster_ids[i] != -1:
            continue
        cluster_ids[i] = next_cid
        t_i = times[i]
        for j in range(i + 1, len(df)):
            if cluster_ids[j] != -1:
                continue
            dt_days = (times[j] - t_i) / np.timedelta64(1, "D")
            if dt_days > time_window_days:
                break  # sorted by time — nothing further will qualify
            if sim[i, j] >= sim_threshold:
                cluster_ids[j] = next_cid
        next_cid += 1

    df["cluster_id"] = cluster_ids
    df["is_canonical"] = False
    canonical_idx = df.groupby("cluster_id", sort=False).head(1).index
    df.loc[canonical_idx, "is_canonical"] = True

    n_events = df["cluster_id"].nunique()
    dedup_ratio = 1 - n_events / len(df)
    print(f"Clustered {len(df)} articles -> {n_events} events "
          f"(deduplicated {dedup_ratio:.1%})")
    return df


# ==========================================================================
# 6. AGGREGATE ARTICLE SCORES -> DAILY SERIES
# ==========================================================================
def aggregate_daily(scored_articles: pd.DataFrame, score_col: str,
                    conf_col: str, mat_col: str) -> pd.DataFrame:
    """
    Weighted daily sum of CANONICAL article scores (one per event), weighted
    by confidence * materiality. Clipped to [-1, 1] per day.
    Non-canonical (duplicate) articles contribute zero — the canonical carries
    the signal for the whole event cluster.
    """
    df = scored_articles.copy()
    df["date"] = pd.to_datetime(df["published"]).dt.normalize()

    if "is_canonical" in df.columns:
        canonical_mask = df["is_canonical"].fillna(True).astype(bool)
    else:
        canonical_mask = pd.Series(True, index=df.index)

    df["weighted"] = np.where(
        canonical_mask,
        df[score_col] * df[conf_col] * df[mat_col],
        0.0,
    )

    daily = df.groupby("date").agg(
        score=("weighted", "sum"),
        n_articles=("weighted", "size"),
        n_events=("is_canonical", "sum") if "is_canonical" in df.columns
                 else ("weighted", "size"),
        mean_conf=(conf_col, "mean"),
    ).reset_index()
    daily["score"] = daily["score"].clip(-1, 1)
    return daily


def build_sentiment_ema(price_df: pd.DataFrame, daily_scores: pd.DataFrame) -> pd.DataFrame:
    """Merge daily scores onto trading calendar and compute EMA."""
    p = price_df.copy()
    p["date"] = pd.to_datetime(p["date"]).dt.normalize()
    merged = p.merge(daily_scores[["date", "score"]], on="date", how="left")
    merged["score"] = merged["score"].fillna(0.0)

    ema = 0.0
    emas = []
    for s in merged["score"]:
        if s != 0:
            ema = SENT_EMA_SCALE * s * SENT_EMA_ALPHA_NEW + ema * (1 - SENT_EMA_ALPHA_NEW)
        else:
            ema *= SENT_EMA_DECAY
        emas.append(ema)
    merged["sent_ema"] = emas
    return merged


# ==========================================================================
# 7. SENTIMENT-ONLY BACKTEST
# ==========================================================================
class Portfolio:
    def __init__(self, capital=INITIAL_CAPITAL):
        self.initial_capital = capital
        self.cash = capital
        self.shares = 0.0
        self.log = []

    def value(self, price):
        return self.cash + self.shares * price

    def rebalance(self, target_exp, price, date, band_pct=None):
        """
        band_pct: fraction of portfolio exposure change required to trigger trade.
        Defaults to REBALANCE_BAND_PCT (0.12). Smooth-signal strategies should
        pass band_pct=REBALANCE_BAND_PCT_SMOOTH (0.03).
        """
        if band_pct is None:
            band_pct = REBALANCE_BAND_PCT
        total = self.value(price)
        if total <= 0:
            return
        target_stock = total * target_exp
        current_stock = self.shares * price
        current_exp = current_stock / total if total > 0 else 0.0
        trade_val = target_stock - current_stock

        # Rebalancing band: require exposure to deviate by at least band_pct
        if abs(target_exp - current_exp) < band_pct:
            return

        if abs(trade_val) < MIN_TRADE_VALUE:
            return
        cost = abs(trade_val) * TRANSACTION_COST_PCT
        self.shares += trade_val / price
        self.cash  -= trade_val + cost
        self.log.append({
            "date": date, "price": price, "trade_value": trade_val,
            "cost": cost, "portfolio_value": self.value(price),
            "exposure": target_exp,
        })


def sentiment_to_exposure(sent_ema: float) -> float:
    """Smooth mapping from sentiment EMA to exposure."""
    raw = 1.0 + EXPOSURE_GAIN * np.tanh(sent_ema / EXPOSURE_SCALE)
    return float(np.clip(raw, MIN_EXPOSURE, MAX_EXPOSURE))


def backtest_sentiment_only(merged: pd.DataFrame) -> dict:
    """merged must have: date, close, sent_ema, fwd_ret_1d"""
    port = Portfolio(INITIAL_CAPITAL)
    daily = []
    for _, row in merged.iterrows():
        exp = sentiment_to_exposure(row["sent_ema"])
        port.rebalance(exp, row["close"], row["date"], band_pct=REBALANCE_BAND_PCT_SMOOTH)
        daily.append({
            "date": row["date"],
            "close": row["close"],
            "portfolio_value": port.value(row["close"]),
            "exposure": exp,
            "sent_ema": row["sent_ema"],
        })
    daily_df = pd.DataFrame(daily)
    daily_df["ret"] = daily_df["portfolio_value"].pct_change().fillna(0)

    total_ret = daily_df["portfolio_value"].iloc[-1] / INITIAL_CAPITAL - 1
    sharpe = (daily_df["ret"].mean() / daily_df["ret"].std() * np.sqrt(252)
              if daily_df["ret"].std() > 0 else 0.0)
    roll_max = daily_df["portfolio_value"].cummax()
    max_dd = ((daily_df["portfolio_value"] / roll_max) - 1).min()

    return {
        "daily": daily_df,
        "total_return": total_ret,
        "sharpe": sharpe,
        "max_dd": max_dd,
        "final_value": daily_df["portfolio_value"].iloc[-1],
    }


# ==========================================================================
# 7b. EVENT-IMPULSE MODEL (replaces EMA)
# ==========================================================================
# Per-event-type half-lives (days). Events with short half-lives are priced in
# quickly; events with long half-lives have persistent impact.
EVENT_HALF_LIVES = {
    "earnings":             3.0,
    "guidance":             4.0,
    "mna":                  5.0,
    "antitrust_regulatory": 15.0,
    "product_launch":       5.0,
    "ai_announcement":      3.0,
    "partnership":          4.0,
    "exec_change":          7.0,
    "lawsuit":              10.0,
    "layoff_restructuring": 5.0,
    "macro_market":         2.0,
    "analyst_action":       2.0,
    "other":                3.0,
}

# Event weights updated based on EMPIRICAL cross-model IC findings from the
# 9-model benchmark. Lawsuit consistently shows IC +0.43 to +0.68 across ALL
# models (strongest single signal). AI announcement shows IC -0.10 to -0.56
# (strong anti-predictor). These weights reflect observed data, not priors.
EVENT_WEIGHTS = {
    "earnings":              1.0,   # IC +0.08 to +0.35 — moderate positive
    "guidance":              1.2,   # IC +0.27 to +0.90 when graded — strong
    "mna":                   1.5,   # IC +0.44 to +0.88 across models — very strong
    "antitrust_regulatory":  0.9,   # IC -0.08 to +0.16 — mixed, moderate weight
    "product_launch":       -0.3,   # IC -0.36 to -0.97 — anti-predicts
    "ai_announcement":      -0.4,   # IC -0.10 to -0.56 — strongly anti-predicts
    "partnership":           0.0,   # IC -0.06 to -0.38 — kill it
    "exec_change":           0.5,   # low n, keep modest
    "lawsuit":               2.0,   # IC +0.43 to +0.68 — STRONGEST signal, boost
    "layoff_restructuring": -0.2,   # IC -0.08 to -0.92 — small negative
    "macro_market":          0.3,   # uncertain, low weight
    "analyst_action":       -0.1,   # IC -0.02 to -0.21 — slightly anti
    "other":                 0.05,  # noise, near-zero weight
}

# Target vol for vol-adjusted sizing
TARGET_VOL = 0.15  # 15% annualized


def compute_impulse_signal(scored_articles: pd.DataFrame, price_df: pd.DataFrame,
                            scorer_name: str) -> pd.DataFrame:
    """
    Replace the EMA with an event-impulse model.

    For each canonical scored article:
      impulse = score × confidence × materiality × event_weight
    Each impulse decays with event-type-specific half-life.

    The daily signal is the SUM of all active (not yet fully decayed) impulses.
    Also computes surprise = today's impulse sum minus trailing 20-day mean
    (markets move on deviations from expectations, not levels).
    """
    sc_col = f"{scorer_name}_score"
    cn_col = f"{scorer_name}_confidence"
    mt_col = f"{scorer_name}_materiality"
    et_col = f"{scorer_name}_event_type"

    # Build list of impulse events from canonical articles
    arts = scored_articles.copy()
    if "is_canonical" in arts.columns:
        arts = arts[arts["is_canonical"].fillna(True).astype(bool)]
    arts["date"] = pd.to_datetime(arts["published"]).dt.normalize()

    events = []
    for _, row in arts.iterrows():
        et = row.get(et_col, "other")
        weight = EVENT_WEIGHTS.get(et, 0.1)
        if weight == 0:
            continue
        half_life = EVENT_HALF_LIVES.get(et, 3.0)
        decay_rate = np.log(2) / half_life
        impulse = row[sc_col] * row[cn_col] * row[mt_col] * weight
        if abs(impulse) < 1e-6:
            continue
        events.append({
            "date": row["date"],
            "impulse": impulse,
            "decay_rate": decay_rate,
        })

    # Compute daily signal by summing decaying impulses
    p = price_df.copy()
    p["date"] = pd.to_datetime(p["date"]).dt.normalize()
    p = p.sort_values("date").reset_index(drop=True)

    signals = []
    for _, prow in p.iterrows():
        d = prow["date"]
        total = 0.0
        for ev in events:
            dt = (d - ev["date"]).days
            if dt < 0:
                continue  # event hasn't happened yet
            if dt > 60:
                continue  # fully decayed
            total += ev["impulse"] * np.exp(-ev["decay_rate"] * dt)
        signals.append(total)

    p["impulse_signal"] = signals

    # Surprise = deviation from trailing 20-day mean
    p["signal_ma20"] = p["impulse_signal"].rolling(20, min_periods=1).mean()
    p["surprise"] = p["impulse_signal"] - p["signal_ma20"]

    # v2b variant: smoothed impulse (3-day trailing mean) then surprise
    # Tests whether filtering daily noise improves alpha extraction.
    # Theme-driven trades (not reactive to single noisy articles).
    p["impulse_smooth3"] = p["impulse_signal"].rolling(3, min_periods=1).mean()
    p["signal_ma20_smooth"] = p["impulse_smooth3"].rolling(20, min_periods=1).mean()
    p["surprise_smooth"] = p["impulse_smooth3"] - p["signal_ma20_smooth"]

    return p


def backtest_v2(merged: pd.DataFrame) -> dict:
    """
    V2 backtest: PURE SENTIMENT using impulse signal + surprise-relative scoring.
    No technical features (no VIX, no vol-scaling, no regime dampener).
    Tests whether the impulse architecture extracts more alpha from the same
    sentiment signal than the EMA architecture (v1).

    merged must have: date, close, impulse_signal, surprise, fwd_ret_1d
    """
    port = Portfolio(INITIAL_CAPITAL)
    daily = []

    for _, row in merged.iterrows():
        # --- Surprise-relative signal (pure sentiment) ---
        sig = row.get("surprise", 0.0)
        if pd.isna(sig):
            sig = 0.0

        # --- Exposure from sentiment surprise only ---
        # 0.15 is the impulse signal scale (much smaller than EMA values)
        raw_exp = 1.0 + EXPOSURE_GAIN * np.tanh(sig / 0.15)
        exp = float(np.clip(raw_exp, MIN_EXPOSURE, MAX_EXPOSURE))

        port.rebalance(exp, row["close"], row["date"], band_pct=REBALANCE_BAND_PCT_SMOOTH)
        daily.append({
            "date": row["date"],
            "close": row["close"],
            "portfolio_value": port.value(row["close"]),
            "exposure": exp,
            "sent_ema": row.get("impulse_signal", 0.0),
            "surprise": sig,
        })

    daily_df = pd.DataFrame(daily)
    daily_df["ret"] = daily_df["portfolio_value"].pct_change().fillna(0)

    total_ret = daily_df["portfolio_value"].iloc[-1] / INITIAL_CAPITAL - 1
    sharpe = (daily_df["ret"].mean() / daily_df["ret"].std() * np.sqrt(252)
              if daily_df["ret"].std() > 0 else 0.0)
    roll_max = daily_df["portfolio_value"].cummax()
    max_dd = ((daily_df["portfolio_value"] / roll_max) - 1).min()

    return {
        "daily": daily_df,
        "total_return": total_ret,
        "sharpe": sharpe,
        "max_dd": max_dd,
        "final_value": daily_df["portfolio_value"].iloc[-1],
    }


def backtest_v2_smoothed(merged: pd.DataFrame) -> dict:
    """
    V2b: PURE SENTIMENT with 3-day smoothed impulse signal.
    Instead of surprise = today's impulse - 20d mean, uses
    surprise = (3-day avg of impulse) - (20-day avg of that).
    Filters daily noise; trades on sustained themes rather than single articles.
    """
    port = Portfolio(INITIAL_CAPITAL)
    daily = []
    for _, row in merged.iterrows():
        sig = row.get("surprise_smooth", 0.0)
        if pd.isna(sig):
            sig = 0.0
        raw_exp = 1.0 + EXPOSURE_GAIN * np.tanh(sig / 0.15)
        exp = float(np.clip(raw_exp, MIN_EXPOSURE, MAX_EXPOSURE))
        port.rebalance(exp, row["close"], row["date"], band_pct=REBALANCE_BAND_PCT_SMOOTH)
        daily.append({
            "date": row["date"],
            "close": row["close"],
            "portfolio_value": port.value(row["close"]),
            "exposure": exp,
            "sent_ema": row.get("impulse_smooth3", 0.0),
            "surprise": sig,
        })
    daily_df = pd.DataFrame(daily)
    daily_df["ret"] = daily_df["portfolio_value"].pct_change().fillna(0)
    total_ret = daily_df["portfolio_value"].iloc[-1] / INITIAL_CAPITAL - 1
    sharpe = (daily_df["ret"].mean() / daily_df["ret"].std() * np.sqrt(252)
              if daily_df["ret"].std() > 0 else 0.0)
    roll_max = daily_df["portfolio_value"].cummax()
    max_dd = ((daily_df["portfolio_value"] / roll_max) - 1).min()
    return {
        "daily": daily_df,
        "total_return": total_ret,
        "sharpe": sharpe,
        "max_dd": max_dd,
        "final_value": daily_df["portfolio_value"].iloc[-1],
    }


# ==========================================================================
# 7c. RIDGE ML TRADER (learns optimal exposure from features)
# ==========================================================================
from sklearn.linear_model import RidgeCV, LassoCV

class RidgeMLTrader:
    """
    Walk-forward ridge regression that learns optimal exposure from features.
    Two modes:
      - sentiment_only=True  (v3): only uses sentiment-derived features
      - sentiment_only=False (v4): adds technical + macro features
    """

    def __init__(self, sentiment_only: bool = True):
        self.sentiment_only = sentiment_only
        self.feature_cols = []

    def build_features(self, merged: pd.DataFrame) -> pd.DataFrame:
        """Build feature matrix from merged price+signal data."""
        df = merged.copy()

        # ---- SENTIMENT-DERIVED FEATURES (used by both v3 and v4) ----
        imp = df.get("impulse_signal", pd.Series(0.0, index=df.index)).fillna(0)
        sur = df.get("surprise", pd.Series(0.0, index=df.index)).fillna(0)

        df["f_impulse"]       = imp
        df["f_surprise"]      = sur
        df["f_impulse_abs"]   = imp.abs()
        df["f_impulse_lag5"]  = imp.shift(5).fillna(0)
        df["f_surprise_lag1"] = sur.shift(1).fillna(0)
        df["f_impulse_accel"] = (imp - imp.shift(3)).fillna(0)
        df["f_impulse_x_abs"] = imp * imp.abs()

        if not self.sentiment_only:
            # ---- TECHNICAL + MACRO FEATURES (v4 only) ----
            df["f_ret_5d"]  = df["close"].pct_change(5).fillna(0)
            df["f_ret_10d"] = df["close"].pct_change(10).fillna(0)
            df["f_ret_20d"] = df["close"].pct_change(20).fillna(0)
            df["f_rvol"]    = df.get("rvol_20d",
                                      pd.Series(TARGET_VOL, index=df.index)).fillna(TARGET_VOL)
            df["f_vix"]     = df.get("vix_close",
                                      pd.Series(20.0, index=df.index)).fillna(20)
            df["f_spy_dd"]  = df.get("spy_drawdown",
                                      pd.Series(0.0, index=df.index)).fillna(0)
            if "oil_close" in df.columns:
                df["f_oil_5d"] = df["oil_close"].pct_change(5).fillna(0)
            else:
                df["f_oil_5d"] = 0.0
            hi20 = df["close"].rolling(20).max()
            lo20 = df["close"].rolling(20).min()
            df["f_range_pos"] = ((df["close"] - lo20) / (hi20 - lo20 + 1e-8)).fillna(0.5)
            df["f_impulse_x_vol"] = df["f_impulse"] * df["f_rvol"]
            df["f_impulse_x_mom"] = df["f_impulse"] * df["f_ret_5d"]

        self.feature_cols = [c for c in df.columns if c.startswith("f_")]
        return df

    def walk_forward_backtest(self, df: pd.DataFrame,
                               min_train_days: int = 30,
                               retrain_every: int = 20) -> dict:
        """
        Walk-forward: train on past, predict next chunk, roll forward.
        Target: fwd_ret_1d — predict return magnitude + direction.

        Timing guarantees:
          - At decision time i: features X[i] use only data through close[i]
          - Training y[:i] uses fwd_ret_1d[:i], which requires close[:i+1] —
            all known at decision time (close[i] is observed when trading)
          - CV inside training window uses TimeSeriesSplit (no future leakage)
          - Features are standardized inside the CV fold (no scale leakage)
          - Portfolio value is recorded INSIDE the rebalance loop (not after)
        """
        from sklearn.preprocessing import StandardScaler
        from sklearn.pipeline import Pipeline
        from sklearn.model_selection import TimeSeriesSplit

        df = df.dropna(subset=["fwd_ret_1d"]).reset_index(drop=True)
        if len(df) < min_train_days + 20:
            return {"daily": pd.DataFrame(), "total_return": 0, "sharpe": 0,
                    "max_dd": 0, "final_value": INITIAL_CAPITAL,
                    "feature_importances": {}, "best_alpha": None}

        X = df[self.feature_cols].fillna(0).values
        y = df["fwd_ret_1d"].values
        dates = df["date"].values
        closes = df["close"].values

        port = Portfolio(INITIAL_CAPITAL)
        predictions = np.full(len(df), np.nan)
        exposures  = np.full(len(df), np.nan)
        pipeline = None
        last_alpha = None
        last_coefs = None

        # --- Backtest loop — record portfolio state inline, not after ---
        # Collect predictions first, then use rolling std of past predictions
        # to z-score normalize before tanh. This replaces the hardcoded /0.01
        # so the algorithm actually utilizes the full MIN→MAX exposure range.
        daily_records = []
        raw_preds_so_far = []  # for rolling std
        for i in range(min_train_days, len(df)):
            # Retrain periodically
            if pipeline is None or (i - min_train_days) % retrain_every == 0:
                X_train = X[:i]
                y_train = y[:i]
                n_splits = min(5, max(2, (i - 10) // 10))
                try:
                    ridge = RidgeCV(
                        alphas=[0.1, 1.0, 10.0, 100.0, 1000.0],
                        cv=TimeSeriesSplit(n_splits=n_splits),
                    )
                    pipeline = Pipeline([
                        ("scale", StandardScaler()),
                        ("ridge", ridge),
                    ])
                    pipeline.fit(X_train, y_train)
                    last_alpha = float(pipeline.named_steps["ridge"].alpha_)
                    last_coefs = pipeline.named_steps["ridge"].coef_.copy()
                except Exception as e:
                    print(f"  ridge fit failed at day {i}: {e}")
                    pipeline = None

            # Predict for this day
            if pipeline is not None:
                pred = float(pipeline.predict(X[i:i+1])[0])
                predictions[i] = pred
                raw_preds_so_far.append(pred)

                # Z-score normalize using rolling std of past predictions
                # Need at least 10 predictions before we trust the std estimate
                if len(raw_preds_so_far) >= 10:
                    recent = np.array(raw_preds_so_far[-30:])
                    std = recent.std()
                    if std > 1e-8:
                        z_score = pred / std
                    else:
                        z_score = 0.0
                else:
                    # Warm-up: fall back to the old hardcoded scale
                    z_score = pred / 0.01

                # tanh of z-score squashes to [-1, 1], then map to exposure
                exp = 1.0 + EXPOSURE_GAIN * np.tanh(z_score / 2.0)
                exp = float(np.clip(exp, MIN_EXPOSURE, MAX_EXPOSURE))
            else:
                exp = 1.0

            exposures[i] = exp
            port.rebalance(exp, closes[i], dates[i])

            # Record portfolio value IMMEDIATELY after rebalance
            daily_records.append({
                "date": dates[i],
                "close": closes[i],
                "portfolio_value": port.value(closes[i]),
                "exposure": exp,
                "prediction": predictions[i],
            })

        daily_df = pd.DataFrame(daily_records)
        daily_df["ret"] = daily_df["portfolio_value"].pct_change().fillna(0)

        total_ret = daily_df["portfolio_value"].iloc[-1] / INITIAL_CAPITAL - 1
        sharpe = (daily_df["ret"].mean() / daily_df["ret"].std() * np.sqrt(252)
                  if daily_df["ret"].std() > 0 else 0.0)
        roll_max = daily_df["portfolio_value"].cummax()
        max_dd = ((daily_df["portfolio_value"] / roll_max) - 1).min()

        # Feature importances (from final trained scaler+ridge)
        importances = {}
        if last_coefs is not None:
            for col, coef in zip(self.feature_cols, last_coefs):
                importances[col] = float(coef)

        return {
            "daily": daily_df,
            "total_return": total_ret,
            "sharpe": sharpe,
            "max_dd": max_dd,
            "final_value": daily_df["portfolio_value"].iloc[-1],
            "feature_importances": importances,
            "best_alpha": last_alpha,
        }


# ==========================================================================
# 7d. GRADIENT BOOSTING ML TRADER (v5 — nonlinear alternative to v3/v4 ridge)
# ==========================================================================
class GBMMLTrader:
    """
    Walk-forward gradient boosting regression. Same feature set and walk-forward
    structure as RidgeMLTrader, but uses HistGradientBoostingRegressor so it can
    learn non-linear interactions like "bad technicals + great news = buy".

    Heavily regularized: max_depth=3, small max_iter, min_samples_leaf=5.
    This prevents overfitting on the 40-day training window.
    """
    def __init__(self, sentiment_only: bool = True):
        self.sentiment_only = sentiment_only
        # Reuse RidgeMLTrader's feature logic
        self._ridge_for_features = RidgeMLTrader(sentiment_only=sentiment_only)
        self.feature_cols = []

    def build_features(self, merged: pd.DataFrame) -> pd.DataFrame:
        df = self._ridge_for_features.build_features(merged)
        self.feature_cols = self._ridge_for_features.feature_cols
        return df

    def walk_forward_backtest(self, df: pd.DataFrame,
                               min_train_days: int = 30,
                               retrain_every: int = 20) -> dict:
        from sklearn.ensemble import HistGradientBoostingRegressor

        df = df.dropna(subset=["fwd_ret_1d"]).reset_index(drop=True)
        if len(df) < min_train_days + 20:
            return {"daily": pd.DataFrame(), "total_return": 0, "sharpe": 0,
                    "max_dd": 0, "final_value": INITIAL_CAPITAL,
                    "feature_importances": {}}

        X = df[self.feature_cols].fillna(0).values
        y = df["fwd_ret_1d"].values
        dates = df["date"].values
        closes = df["close"].values

        port = Portfolio(INITIAL_CAPITAL)
        predictions = np.full(len(df), np.nan)
        model = None
        daily_records = []
        raw_preds_so_far = []

        for i in range(min_train_days, len(df)):
            if model is None or (i - min_train_days) % retrain_every == 0:
                X_train = X[:i]
                y_train = y[:i]
                try:
                    # Heavy regularization to prevent overfitting on 40-day window
                    model = HistGradientBoostingRegressor(
                        max_depth=3,
                        max_iter=50,
                        min_samples_leaf=5,
                        l2_regularization=1.0,
                        learning_rate=0.05,
                        random_state=42,
                    )
                    model.fit(X_train, y_train)
                except Exception as e:
                    print(f"  gbm fit failed at day {i}: {e}")
                    model = None

            if model is not None:
                pred = float(model.predict(X[i:i+1])[0])
                predictions[i] = pred
                raw_preds_so_far.append(pred)

                # Same z-score normalization as ridge
                if len(raw_preds_so_far) >= 10:
                    recent = np.array(raw_preds_so_far[-30:])
                    std = recent.std()
                    z_score = pred / std if std > 1e-8 else 0.0
                else:
                    z_score = pred / 0.01

                exp = 1.0 + EXPOSURE_GAIN * np.tanh(z_score / 2.0)
                exp = float(np.clip(exp, MIN_EXPOSURE, MAX_EXPOSURE))
            else:
                exp = 1.0

            port.rebalance(exp, closes[i], dates[i])
            daily_records.append({
                "date": dates[i],
                "close": closes[i],
                "portfolio_value": port.value(closes[i]),
                "exposure": exp,
                "prediction": predictions[i],
            })

        daily_df = pd.DataFrame(daily_records)
        daily_df["ret"] = daily_df["portfolio_value"].pct_change().fillna(0)

        total_ret = daily_df["portfolio_value"].iloc[-1] / INITIAL_CAPITAL - 1
        sharpe = (daily_df["ret"].mean() / daily_df["ret"].std() * np.sqrt(252)
                  if daily_df["ret"].std() > 0 else 0.0)
        roll_max = daily_df["portfolio_value"].cummax()
        max_dd = ((daily_df["portfolio_value"] / roll_max) - 1).min()

        # GBM feature importances (permutation-based, via model attribute)
        importances = {}
        if model is not None and hasattr(model, "_predictors"):
            # HGBT doesn't expose coef_ — use permutation importance on training data
            try:
                from sklearn.inspection import permutation_importance
                # Quick permutation importance on last train split
                perm = permutation_importance(
                    model, X[:len(X)//2], y[:len(y)//2],
                    n_repeats=5, random_state=42,
                )
                for col, imp in zip(self.feature_cols, perm.importances_mean):
                    importances[col] = float(imp)
            except Exception:
                pass

        return {
            "daily": daily_df,
            "total_return": total_ret,
            "sharpe": sharpe,
            "max_dd": max_dd,
            "final_value": daily_df["portfolio_value"].iloc[-1],
            "feature_importances": importances,
        }


# ==========================================================================
# 7e. EVENT-DRIVEN CLASSIFIER (v6 — 5-day direction, trades only on news events)
# ==========================================================================
class EventClassifierTrader:
    """
    Fundamentally different from v3/v4/v5:
      - TARGET: 3-class direction over 5-day horizon (UP / FLAT / DOWN), not
        next-day percentage. The model guesses direction, not magnitude.
      - MODEL: HistGradientBoostingClassifier — handles non-linear event
        interactions natively (e.g. "bad technicals + lawsuit = buy").
      - EVENT GATE: only considers re-trading on days where |surprise| exceeds
        V6_EVENT_THRESHOLD. On quiet days, holds prior position.
      - POSITION SIZING: direction from classifier probabilities, size from raw
        |impulse_signal| (loud news = big position; quiet news = small).
      - SHORTS ALLOWED: MIN_EXPOSURE still 0.0 (no short) unless you flip it.

    Features: same 7 pure-sentiment features as v3/v5 — apples-to-apples.

    Known limitation: target is fwd_ret_5d. Last 5 rows of any training window
    have NaN targets and must be dropped during fit. This costs ~5 effective
    training days.
    """
    FEATURE_COLS = [
        "f_impulse", "f_surprise", "f_impulse_abs",
        "f_impulse_lag5", "f_surprise_lag1",
        "f_impulse_accel", "f_impulse_x_abs",
    ]

    def __init__(self):
        # Reuse RidgeMLTrader's build_features — same feature set
        self._features_builder = RidgeMLTrader(sentiment_only=True)
        self.feature_cols = self.FEATURE_COLS

    def build_features(self, merged: pd.DataFrame) -> pd.DataFrame:
        df = self._features_builder.build_features(merged)
        # Make sure fwd_ret_5d is present (should be from price_df)
        if "fwd_ret_5d" not in df.columns:
            df["fwd_ret_5d"] = df["close"].shift(-V6_HORIZON_DAYS) / df["close"] - 1
        # Make sure surprise and impulse_signal are present
        if "surprise" not in df.columns:
            df["surprise"] = 0.0
        if "impulse_signal" not in df.columns:
            df["impulse_signal"] = 0.0
        return df

    def _label_3class(self, ret_5d: np.ndarray) -> np.ndarray:
        """Bin 5-day returns into {-1: DOWN, 0: FLAT, +1: UP} based on V6_FLAT_BAND."""
        labels = np.zeros(len(ret_5d), dtype=int)
        labels[ret_5d >  V6_FLAT_BAND] = 1
        labels[ret_5d < -V6_FLAT_BAND] = -1
        return labels

    def walk_forward_backtest(self, df: pd.DataFrame,
                               min_train_days: int = 30,
                               retrain_every: int = 20) -> dict:
        from sklearn.ensemble import HistGradientBoostingClassifier

        df = df.dropna(subset=["fwd_ret_1d"]).reset_index(drop=True)
        if len(df) < min_train_days + 20:
            return {"daily": pd.DataFrame(), "total_return": 0, "sharpe": 0,
                    "max_dd": 0, "final_value": INITIAL_CAPITAL,
                    "feature_importances": {}, "n_events": 0, "n_holds": 0}

        X = df[self.feature_cols].fillna(0).values
        y_ret_5d = df["fwd_ret_5d"].values  # target: 5-day forward return
        dates = df["date"].values
        closes = df["close"].values
        surprise = df["surprise"].fillna(0).values
        impulse = df["impulse_signal"].fillna(0).values

        port = Portfolio(INITIAL_CAPITAL)
        predictions = np.full(len(df), np.nan)      # signed conviction
        classes_pred = np.full(len(df), np.nan)     # predicted class (-1/0/+1)
        model = None
        daily_records = []
        n_events = 0
        n_holds = 0
        # Start in CASH. Require a real surprise event to establish any position.
        # This is the key difference from v3/v4/v5 — those default to 1.0 (long)
        # and ride the market up even when the model has zero conviction.
        # v6 is event-driven: no signal → no exposure.
        current_exp = 0.0

        for i in range(min_train_days, len(df)):
            # Retrain periodically
            if model is None or (i - min_train_days) % retrain_every == 0:
                X_train = X[:i]
                y_train_ret = y_ret_5d[:i]
                # Drop rows with NaN target (last 5 days of training window)
                valid = ~np.isnan(y_train_ret)
                X_train_v = X_train[valid]
                y_train_v = self._label_3class(y_train_ret[valid])

                # Need at least 2 classes present to train classifier
                if len(np.unique(y_train_v)) < 2 or len(X_train_v) < 20:
                    model = None
                else:
                    try:
                        model = HistGradientBoostingClassifier(
                            max_depth=3,
                            max_iter=50,
                            min_samples_leaf=5,
                            l2_regularization=1.0,
                            learning_rate=0.05,
                            random_state=42,
                        )
                        model.fit(X_train_v, y_train_v)
                    except Exception as e:
                        print(f"  v6 clf fit failed at day {i}: {e}")
                        model = None

            # Event gate: only consider rebalancing if today is a "news event day"
            is_event = abs(surprise[i]) > V6_EVENT_THRESHOLD

            if is_event and model is not None:
                n_events += 1
                # Probability of each class
                proba = model.predict_proba(X[i:i+1])[0]
                class_labels = model.classes_
                p_up = proba[list(class_labels).index(1)] if 1 in class_labels else 0.0
                p_dn = proba[list(class_labels).index(-1)] if -1 in class_labels else 0.0
                p_flat = proba[list(class_labels).index(0)] if 0 in class_labels else 0.0

                # If model predicts FLAT (p_flat highest), return to cash rather
                # than keep the previous position.
                if p_flat > max(p_up, p_dn):
                    current_exp = 0.0
                    predictions[i] = 0.0
                    classes_pred[i] = 0.0
                else:
                    # Directional bet. Conviction weighted by non-flat probability mass.
                    conviction = (p_up - p_dn) * (1.0 - p_flat)
                    predictions[i] = conviction
                    classes_pred[i] = p_up - p_dn

                    # Size modifier: bigger positions on louder news days
                    size_mult = min(abs(impulse[i]) / V6_SIZE_IMPULSE_CAP, 1.0)

                    # Target exposure: conviction × size × gain
                    # When p_up dominates → exposure above 1 (leveraged long)
                    # When p_dn dominates → exposure below MIN_EXPOSURE floor (cash/no short)
                    raw_exp = 1.0 + EXPOSURE_GAIN * conviction * size_mult
                    current_exp = float(np.clip(raw_exp, MIN_EXPOSURE, MAX_EXPOSURE))
            else:
                # Not an event day (or no model yet) — hold prior position
                # (which defaults to cash at start and only gets set by events)
                n_holds += 1

            port.rebalance(current_exp, closes[i], dates[i])

            daily_records.append({
                "date": dates[i],
                "close": closes[i],
                "portfolio_value": port.value(closes[i]),
                "exposure": current_exp,
                "prediction": predictions[i],
                "is_event": is_event,
                "class_pred": classes_pred[i],
            })

        daily_df = pd.DataFrame(daily_records)
        daily_df["ret"] = daily_df["portfolio_value"].pct_change().fillna(0)

        total_ret = daily_df["portfolio_value"].iloc[-1] / INITIAL_CAPITAL - 1
        sharpe = (daily_df["ret"].mean() / daily_df["ret"].std() * np.sqrt(252)
                  if daily_df["ret"].std() > 0 else 0.0)
        roll_max = daily_df["portfolio_value"].cummax()
        max_dd = ((daily_df["portfolio_value"] / roll_max) - 1).min()

        # Permutation feature importances on recent training data
        importances = {}
        if model is not None:
            try:
                from sklearn.inspection import permutation_importance
                # Build a valid training slice
                cutoff = len(y_ret_5d) - V6_HORIZON_DAYS - 10
                if cutoff > 20:
                    X_pi = X[:cutoff]
                    y_pi = self._label_3class(y_ret_5d[:cutoff])
                    if len(np.unique(y_pi)) >= 2:
                        perm = permutation_importance(
                            model, X_pi, y_pi,
                            n_repeats=5, random_state=42, scoring="accuracy",
                        )
                        for col, imp in zip(self.feature_cols, perm.importances_mean):
                            importances[col] = float(imp)
            except Exception:
                pass

        return {
            "daily": daily_df,
            "total_return": total_ret,
            "sharpe": sharpe,
            "max_dd": max_dd,
            "final_value": daily_df["portfolio_value"].iloc[-1],
            "feature_importances": importances,
            "n_events": int(n_events),
            "n_holds": int(n_holds),
        }


def compute_signal_metrics(merged: pd.DataFrame) -> dict:
    """
    merged must have: sent_ema, fwd_ret_1d, fwd_ret_5d, score (raw daily score)
    """
    df = merged.dropna(subset=["fwd_ret_1d"]).copy()
    if len(df) < 10:
        return {}

    # Primary: Information Coefficient — Spearman corr of signal vs next-day return
    ic_spear_1d, _ = spearmanr(df["sent_ema"], df["fwd_ret_1d"])
    ic_pear_1d,  _ = pearsonr (df["sent_ema"], df["fwd_ret_1d"])
    ic_spear_5d, _ = spearmanr(df["sent_ema"], df["fwd_ret_5d"].fillna(0))

    # Directional hit rate on days where signal is meaningful
    signal_days = df[df["sent_ema"].abs() > df["sent_ema"].abs().median()]
    if len(signal_days) > 0:
        hit = (np.sign(signal_days["sent_ema"]) == np.sign(signal_days["fwd_ret_1d"])).mean()
    else:
        hit = np.nan

    # Coverage: fraction of days with nonzero raw score
    coverage = (df["score"].abs() > 1e-6).mean() if "score" in df.columns else np.nan

    # Distribution
    score_mean = df["sent_ema"].mean()
    score_std  = df["sent_ema"].std()

    # Rolling IC stability (std of rolling 30-day IC)
    rolling_ic = []
    window = 30
    for i in range(window, len(df)):
        w = df.iloc[i-window:i]
        if w["sent_ema"].std() > 0 and w["fwd_ret_1d"].std() > 0:
            r, _ = spearmanr(w["sent_ema"], w["fwd_ret_1d"])
            rolling_ic.append(r)
    ic_stability = np.std(rolling_ic) if rolling_ic else np.nan
    ic_mean_roll = np.mean(rolling_ic) if rolling_ic else np.nan

    return {
        "IC_spearman_1d": ic_spear_1d,
        "IC_pearson_1d":  ic_pear_1d,
        "IC_spearman_5d": ic_spear_5d,
        "hit_rate":       hit,
        "coverage":       coverage,
        "signal_mean":    score_mean,
        "signal_std":     score_std,
        "rolling_IC_mean": ic_mean_roll,
        "rolling_IC_std":  ic_stability,
    }


def compute_classification_metrics(merged: pd.DataFrame,
                                    flat_return_thresh: float = 0.001,
                                    abstain_signal_thresh: float = 2.0) -> dict:
    """
    Treat sentiment as a directional classifier.
      Label:      UP if fwd_ret_1d >  flat_return_thresh
                  DOWN if fwd_ret_1d < -flat_return_thresh
                  (else dropped — market was flat, unfair to grade)
      Prediction: UP if sent_ema >  abstain_signal_thresh
                  DOWN if sent_ema < -abstain_signal_thresh
                  (else model abstains — excluded from precision/recall)
    Returns precision, recall, F1 per class, plus macro F1, accuracy, MCC,
    confusion matrix, and abstain rate.
    """
    df = merged.dropna(subset=["fwd_ret_1d"]).copy()
    n_total = len(df)
    if n_total == 0:
        return {}

    # Label
    df["y_true"] = np.where(
        df["fwd_ret_1d"] >  flat_return_thresh, 1,
        np.where(df["fwd_ret_1d"] < -flat_return_thresh, -1, 0)
    )
    # Prediction (0 = abstain)
    df["y_pred"] = np.where(
        df["sent_ema"] >  abstain_signal_thresh, 1,
        np.where(df["sent_ema"] < -abstain_signal_thresh, -1, 0)
    )

    abstain_rate = (df["y_pred"] == 0).mean()
    flat_rate    = (df["y_true"] == 0).mean()

    # Keep only days where both a direction exists
    graded = df[(df["y_true"] != 0) & (df["y_pred"] != 0)]
    if len(graded) < 10:
        return {
            "accuracy": np.nan, "precision_up": np.nan, "recall_up": np.nan,
            "f1_up": np.nan, "precision_down": np.nan, "recall_down": np.nan,
            "f1_down": np.nan, "macro_f1": np.nan, "mcc": np.nan,
            "abstain_rate": abstain_rate, "flat_rate": flat_rate,
            "graded_days": len(graded), "cm": None,
        }

    y_t = graded["y_true"].values
    y_p = graded["y_pred"].values

    acc = accuracy_score(y_t, y_p)
    # Per-class (pos_label style)
    prec_up   = precision_score(y_t, y_p, pos_label= 1, zero_division=0)
    rec_up    = recall_score   (y_t, y_p, pos_label= 1, zero_division=0)
    f1_up     = f1_score       (y_t, y_p, pos_label= 1, zero_division=0)
    prec_down = precision_score(y_t, y_p, pos_label=-1, zero_division=0)
    rec_down  = recall_score   (y_t, y_p, pos_label=-1, zero_division=0)
    f1_down   = f1_score       (y_t, y_p, pos_label=-1, zero_division=0)
    macro_f1  = f1_score(y_t, y_p, average="macro", zero_division=0)
    mcc       = matthews_corrcoef(y_t, y_p)
    cm        = confusion_matrix(y_t, y_p, labels=[-1, 1])

    return {
        "accuracy":       acc,
        "precision_up":   prec_up,
        "recall_up":      rec_up,
        "f1_up":          f1_up,
        "precision_down": prec_down,
        "recall_down":    rec_down,
        "f1_down":        f1_down,
        "macro_f1":       macro_f1,
        "mcc":            mcc,
        "abstain_rate":   abstain_rate,
        "flat_rate":      flat_rate,
        "graded_days":    len(graded),
        "cm":             cm,
    }


def inter_model_agreement(per_model_merged: dict) -> pd.DataFrame:
    """Spearman corr matrix of daily sent_ema across models."""
    wide = None
    for name, m in per_model_merged.items():
        col = m[["date", "sent_ema"]].rename(columns={"sent_ema": name})
        wide = col if wide is None else wide.merge(col, on="date", how="outer")
    wide = wide.fillna(0).drop(columns=["date"])
    return wide.corr(method="spearman")


# ==========================================================================
# 8b. PROBABILISTIC & DEFLATED SHARPE (SOTA upgrade 2)
# ==========================================================================
def probabilistic_sharpe_ratio(sr_obs: float, sr_bench: float,
                                n_returns: int, skew: float, kurt: float) -> float:
    """
    PSR = P(true SR > sr_bench | observed SR is sr_obs).
    sr_obs and sr_bench must be on the SAME period basis (we use daily).
    kurt is the excess kurtosis (raw kurtosis - 3).
    López de Prado 2012.
    """
    if n_returns < 2:
        return float("nan")
    denom = np.sqrt(max(1e-12, 1 - skew * sr_obs + ((kurt) / 4.0) * sr_obs ** 2))
    z = (sr_obs - sr_bench) * np.sqrt(n_returns - 1) / denom
    return float(norm.cdf(z))


def expected_max_sharpe_under_null(n_trials: int, var_trials: float = 1.0) -> float:
    """
    Expected maximum Sharpe (daily) across N independent trials under the null
    (true SR = 0 for all). López de Prado 2014 closed form.
    """
    if n_trials < 2:
        return 0.0
    gamma = 0.5772156649  # Euler-Mascheroni
    e = np.e
    term = ((1 - gamma) * norm.ppf(1 - 1.0 / n_trials)
            + gamma * norm.ppf(1 - 1.0 / (n_trials * e)))
    return float(np.sqrt(max(var_trials, 1e-12)) * term)


def deflated_sharpe_ratio(sr_obs_daily: float, n_returns: int,
                           skew: float, kurt: float,
                           n_trials: int, var_trials: float) -> float:
    """
    DSR = PSR against SR_0 = E[max SR across N null trials].
    Interpretation: probability the observed Sharpe is genuine alpha rather
    than the best of N noise draws. >0.95 is "publication grade".
    All Sharpes DAILY (not annualized). Convert before calling.
    """
    sr0 = expected_max_sharpe_under_null(n_trials, var_trials)
    return probabilistic_sharpe_ratio(sr_obs_daily, sr0, n_returns, skew, kurt)


def compute_sharpe_stats(daily_rets: pd.Series) -> dict:
    """Return per-day Sharpe + higher moments needed for PSR/DSR."""
    r = daily_rets.dropna()
    if len(r) < 5 or r.std() == 0:
        return {"sr_daily": 0.0, "skew": 0.0, "kurt": 0.0, "n": len(r)}
    return {
        "sr_daily": float(r.mean() / r.std()),
        "skew":     float(sp_skew(r, bias=False)),
        "kurt":     float(sp_kurt(r, fisher=True, bias=False)),  # excess kurtosis
        "n":        int(len(r)),
    }


# ==========================================================================
# 8c. WALK-FORWARD OUT-OF-SAMPLE EVALUATION (SOTA upgrade 4)
# ==========================================================================
def walk_forward_evaluate(merged: pd.DataFrame, n_folds: int = N_FOLDS) -> dict:
    """
    Split the test-window merged dataframe into n_folds contiguous time slices.
    Compute IC, macro F1, MCC, Sharpe, return per fold — then mean ± std.
    This is honest rolling OOS evaluation: if one model only looks good on one
    fold, the std will blow up and you'll see it.
    """
    df = merged.dropna(subset=["fwd_ret_1d"]).reset_index(drop=True)
    if len(df) < n_folds * 15:
        return {"folds": pd.DataFrame(), "summary": {}}

    fold_size = len(df) // n_folds
    rows = []
    for k in range(n_folds):
        lo = k * fold_size
        hi = (k + 1) * fold_size if k < n_folds - 1 else len(df)
        fold = df.iloc[lo:hi].reset_index(drop=True)
        if len(fold) < 10:
            continue
        sig = compute_signal_metrics(fold)
        cls = compute_classification_metrics(fold)
        bt  = backtest_sentiment_only(fold)
        rows.append({
            "fold":    k + 1,
            "start":   fold["date"].iloc[0],
            "end":     fold["date"].iloc[-1],
            "n_days":  len(fold),
            "ic":      sig.get("IC_spearman_1d", np.nan),
            "f1":      cls.get("macro_f1", np.nan),
            "mcc":     cls.get("mcc", np.nan),
            "sharpe":  bt["sharpe"],
            "return":  bt["total_return"],
        })
    fdf = pd.DataFrame(rows)
    if fdf.empty:
        return {"folds": fdf, "summary": {}}

    summary = {
        f"{col}_{agg}": getattr(fdf[col], agg)()
        for col in ("ic", "f1", "mcc", "sharpe", "return")
        for agg in ("mean", "std")
    }
    return {"folds": fdf, "summary": summary}


def metrics_for_signal(df: pd.DataFrame, signal_col: str,
                        flat_thresh: float = 0.001,
                        signal_thresh_pct: float = 50) -> dict:
    """
    Compute IC and classification metrics for any signal column.
    Used to evaluate v2's impulse signal, v3/v4's ridge predictions, etc. —
    not just v1's EMA. Reuses compute_signal_metrics and
    compute_classification_metrics by remapping the requested column to
    'sent_ema' temporarily.

    signal_thresh_pct: signal must be above this percentile (in abs value)
    to produce a non-abstain prediction. 50 = median (same as default).
    """
    if signal_col not in df.columns:
        return {"IC_spearman_1d": np.nan, "macro_f1": np.nan, "mcc": np.nan}

    temp = df.copy()
    # Save existing sent_ema if present
    original_ema = temp["sent_ema"].copy() if "sent_ema" in temp.columns else None
    temp["sent_ema"] = temp[signal_col]

    # Use a data-driven threshold based on the signal's own distribution
    abs_sig = temp[signal_col].abs()
    if abs_sig.notna().any() and (abs_sig > 0).any():
        thresh = np.nanpercentile(abs_sig[abs_sig > 0], signal_thresh_pct)
    else:
        thresh = 0.0

    sig_metrics = compute_signal_metrics(temp)
    cls_metrics = compute_classification_metrics(
        temp, flat_return_thresh=flat_thresh,
        abstain_signal_thresh=thresh,
    )

    # Restore
    if original_ema is not None:
        temp["sent_ema"] = original_ema

    return {
        "IC_spearman_1d": sig_metrics.get("IC_spearman_1d", np.nan),
        "IC_spearman_5d": sig_metrics.get("IC_spearman_5d", np.nan),
        "hit_rate":       sig_metrics.get("hit_rate", np.nan),
        "rolling_IC_mean": sig_metrics.get("rolling_IC_mean", np.nan),
        "rolling_IC_std":  sig_metrics.get("rolling_IC_std", np.nan),
        "accuracy":       cls_metrics.get("accuracy", np.nan),
        "macro_f1":       cls_metrics.get("macro_f1", np.nan),
        "mcc":            cls_metrics.get("mcc", np.nan),
        "abstain_rate":   cls_metrics.get("abstain_rate", np.nan),
        "graded_days":    cls_metrics.get("graded_days", 0),
    }


def walk_forward_for_signal(df: pd.DataFrame, signal_col: str,
                              n_folds: int = N_FOLDS) -> dict:
    """Walk-forward evaluation on any signal column (not just sent_ema)."""
    if signal_col not in df.columns or signal_col == "sent_ema":
        return walk_forward_evaluate(df, n_folds=n_folds)

    temp = df.copy()
    original_ema = temp["sent_ema"].copy() if "sent_ema" in temp.columns else None
    temp["sent_ema"] = temp[signal_col]
    result = walk_forward_evaluate(temp, n_folds=n_folds)
    if original_ema is not None:
        temp["sent_ema"] = original_ema
    return result



# ==========================================================================
# 8d. PER-EVENT-TYPE ANALYSIS (SOTA upgrade 5)
# ==========================================================================
def per_event_type_analysis(scored: pd.DataFrame, price_df: pd.DataFrame,
                             scorer_name: str) -> pd.DataFrame:
    """
    For each event_type bucket:
      - count (canonical articles only)
      - mean score
      - IC (spearman) of score vs same-day forward return
      - mean fwd return on strong-positive-score days
      - mean fwd return on strong-negative-score days
    Only canonical articles are counted — duplicates are excluded.
    """
    ev_col = f"{scorer_name}_event_type"
    sc_col = f"{scorer_name}_score"
    if ev_col not in scored.columns:
        return pd.DataFrame()

    df = scored.copy()
    if "is_canonical" in df.columns:
        df = df[df["is_canonical"].fillna(True).astype(bool)]
    df["date"] = pd.to_datetime(df["published"]).dt.normalize()

    # Join with price to get forward returns at article level
    p = price_df.copy()
    p["date"] = pd.to_datetime(p["date"]).dt.normalize()
    df = df.merge(p[["date", "fwd_ret_1d"]], on="date", how="left")
    df = df.dropna(subset=["fwd_ret_1d"])

    rows = []
    for et in EVENT_TYPES:
        sub = df[df[ev_col] == et]
        if len(sub) < 3:
            continue
        ic = np.nan
        if sub[sc_col].std() > 0 and sub["fwd_ret_1d"].std() > 0:
            ic, _ = spearmanr(sub[sc_col], sub["fwd_ret_1d"])
        pos = sub[sub[sc_col] >  0.3]["fwd_ret_1d"]
        neg = sub[sub[sc_col] < -0.3]["fwd_ret_1d"]
        rows.append({
            "event_type":  et,
            "n":           len(sub),
            "mean_score":  sub[sc_col].mean(),
            "ic":          ic,
            "pos_ret_bps": pos.mean() * 10_000 if len(pos) > 0 else np.nan,
            "neg_ret_bps": neg.mean() * 10_000 if len(neg) > 0 else np.nan,
            "n_pos":       len(pos),
            "n_neg":       len(neg),
        })
    return pd.DataFrame(rows).sort_values("n", ascending=False)


# ==========================================================================
# 9. EVALUATION HARNESS
# ==========================================================================
def evaluate_all(scorers, news_df, price_df,
                 test_start: str = TEST_START_DATE,
                 macro_narrative: pd.DataFrame = None) -> dict:
    """
    For each scorer:
      1. Score canonical articles (warmup + test window)
      2. Aggregate to daily
      3. Compute EMA across the FULL range (warmup feeds into test)
      4. Slice merged to test window only → all metrics & backtest
      5. Walk-forward folds on the test window
      6. Per-event-type IC breakdown
    Then: compute DSR across all scorers using the full set as the trial count.
    """
    test_start_ts = pd.to_datetime(test_start).normalize()
    results = {}

    for scorer in scorers:
        print(f"\n=== {scorer.name.upper()} ===")
        t0 = time.time()
        scored = scorer.score_batch(news_df, price_df=price_df,
                                     macro_narrative=macro_narrative)

        # Diagnostic: detect all-zero scoring (model refused or safety-filtered)
        score_col = f"{scorer.name}_score"
        if score_col in scored.columns:
            n_total = len(scored)
            n_zero = int((scored[score_col].fillna(0.0) == 0.0).sum())
            n_nonzero = n_total - n_zero
            if n_nonzero == 0:
                print(f"  ⚠️  [{scorer.name}] ALL {n_total} scores are zero — "
                      f"model produced no signal. Downstream Sharpe/Return numbers "
                      f"are buy-and-hold-over-evaluation-window artifacts, not alpha.")
            elif n_nonzero < n_total * 0.1:
                print(f"  ⚠️  [{scorer.name}] Only {n_nonzero}/{n_total} scores "
                      f"non-zero ({n_nonzero/n_total:.0%}). Sparse signal — "
                      f"ML results especially fragile to individual scored days.")
            else:
                print(f"  [{scorer.name}] {n_nonzero}/{n_total} scores non-zero "
                      f"({n_nonzero/n_total:.0%}), mean={scored[score_col].mean():+.3f}, "
                      f"std={scored[score_col].std():.3f}")

        daily = aggregate_daily(
            scored,
            score_col=f"{scorer.name}_score",
            conf_col=f"{scorer.name}_confidence",
            mat_col=f"{scorer.name}_materiality",
        )
        merged_full = build_sentiment_ema(price_df, daily)

        # Attach raw daily score for coverage metric
        merged_full = merged_full.merge(
            daily[["date", "score"]].rename(columns={"score": "raw_score"}),
            on="date", how="left",
        )
        merged_full["score"] = merged_full["raw_score"].fillna(0.0)

        # ---- SLICE TO TEST WINDOW ONLY (lookahead-leakage guard) ----
        test_mask = merged_full["date"] >= test_start_ts
        merged_test = merged_full[test_mask].reset_index(drop=True).copy()

        bt          = backtest_sentiment_only(merged_test)
        metrics     = compute_signal_metrics(merged_test)
        cls_metrics = compute_classification_metrics(merged_test)
        wf          = walk_forward_evaluate(merged_test)
        ev_break    = per_event_type_analysis(scored, price_df, scorer.name)
        sharpe_stats = compute_sharpe_stats(bt["daily"]["ret"])

        # ---- V2: EVENT-IMPULSE + REGIME DAMPENER BACKTEST ----
        impulse_full = compute_impulse_signal(scored, price_df, scorer.name)
        # Merge impulse signal with price data (which has macro columns)
        impulse_merged = price_df.copy()
        impulse_merged["date"] = pd.to_datetime(impulse_merged["date"]).dt.normalize()
        impulse_full["date"] = pd.to_datetime(impulse_full["date"]).dt.normalize()
        impulse_merged = impulse_merged.merge(
            impulse_full[["date", "impulse_signal", "surprise", "signal_ma20",
                           "impulse_smooth3", "surprise_smooth"]],
            on="date", how="left"
        )
        impulse_merged["impulse_signal"] = impulse_merged["impulse_signal"].fillna(0)
        impulse_merged["surprise"] = impulse_merged["surprise"].fillna(0)
        impulse_merged["impulse_smooth3"] = impulse_merged["impulse_smooth3"].fillna(0)
        impulse_merged["surprise_smooth"] = impulse_merged["surprise_smooth"].fillna(0)

        # Slice to test window
        imp_test = impulse_merged[impulse_merged["date"] >= test_start_ts].reset_index(drop=True)
        bt_v2 = backtest_v2(imp_test) if len(imp_test) > 10 else None
        bt_v2b = backtest_v2_smoothed(imp_test) if len(imp_test) > 10 else None

        # ---- V7: CONTRARIAN FLIP (applied to v1-EMA signal) ----
        # Compute IC on a WARMUP window (data before test_start) to decide
        # whether to flip this model's signal. If warmup IC is negative, the
        # model is systematically contrarian — flip its sign before trading.
        # This is a per-model, data-driven decision made ONLY with pre-test data.
        warmup = merged_full[merged_full["date"] < test_start_ts].copy()
        warmup = warmup.dropna(subset=["fwd_ret_1d", "sent_ema"])
        flip_decision = False
        warmup_ic = float("nan")
        if len(warmup) >= 30:
            try:
                from scipy.stats import spearmanr as _spearmanr
                warmup_ic, _ = _spearmanr(warmup["sent_ema"], warmup["fwd_ret_1d"])
                # Flip only if warmup IC is meaningfully negative (not just noise)
                if not np.isnan(warmup_ic) and warmup_ic < -0.05:
                    flip_decision = True
            except Exception:
                pass

        if flip_decision:
            merged_test_v7 = merged_test.copy()
            merged_test_v7["sent_ema"] = -merged_test_v7["sent_ema"]
            bt_v7 = backtest_sentiment_only(merged_test_v7)
        else:
            # Model has positive (or near-zero) warmup IC — no flip, v7 = v1
            bt_v7 = dict(bt)  # same result as v1

        # ---- V3: RIDGE ML TRADER (sentiment-only) ----
        ridge_pure = RidgeMLTrader(sentiment_only=True)
        ridge_df = ridge_pure.build_features(impulse_merged)
        ridge_test = ridge_df[ridge_df["date"] >= test_start_ts].reset_index(drop=True)
        bt_ridge = ridge_pure.walk_forward_backtest(ridge_test) if len(ridge_test) > 60 else None

        # ---- V4: RIDGE ML TRADER (hybrid: sentiment + technical) ----
        ridge_hybrid = RidgeMLTrader(sentiment_only=False)
        ridge_df_h = ridge_hybrid.build_features(impulse_merged)
        ridge_test_h = ridge_df_h[ridge_df_h["date"] >= test_start_ts].reset_index(drop=True)
        bt_ridge_h = ridge_hybrid.walk_forward_backtest(ridge_test_h) if len(ridge_test_h) > 60 else None

        # ---- V5: GRADIENT BOOSTING ML TRADER (pure sentiment, nonlinear) ----
        gbm_pure = GBMMLTrader(sentiment_only=True)
        gbm_df = gbm_pure.build_features(impulse_merged)
        gbm_test = gbm_df[gbm_df["date"] >= test_start_ts].reset_index(drop=True)
        bt_gbm = gbm_pure.walk_forward_backtest(gbm_test) if len(gbm_test) > 60 else None

        # ---- V6: EVENT-DRIVEN CLASSIFIER (5-day direction, trades only on events) ----
        evt_clf = EventClassifierTrader()
        evt_df = evt_clf.build_features(impulse_merged)
        evt_test = evt_df[evt_df["date"] >= test_start_ts].reset_index(drop=True)
        bt_evt = evt_clf.walk_forward_backtest(evt_test) if len(evt_test) > 60 else None

        # ---- PER-STRATEGY METRICS ----
        # v1: uses sent_ema on merged_test (already done above in `metrics` and `cls_metrics`)
        metrics_v1 = {"signal": metrics, "cls": cls_metrics, "wf": wf}

        # v2: use impulse 'surprise' as signal on imp_test + fwd_ret_1d
        if imp_test is not None and not imp_test.empty and "fwd_ret_1d" in imp_test.columns:
            imp_test_m = imp_test.copy()
            # Need sent_ema for metrics_for_signal to use — use surprise directly
            imp_test_m["sent_ema"] = imp_test_m["surprise"]
            m_v2 = metrics_for_signal(imp_test_m, "surprise")
            wf_v2 = walk_forward_for_signal(imp_test_m, "surprise")
            # v2b: same but using smoothed surprise
            imp_test_b = imp_test.copy()
            imp_test_b["sent_ema"] = imp_test_b["surprise_smooth"]
            m_v2b = metrics_for_signal(imp_test_b, "surprise_smooth")
            wf_v2b = walk_forward_for_signal(imp_test_b, "surprise_smooth")
        else:
            m_v2 = {}
            wf_v2 = {"folds": pd.DataFrame(), "summary": {}}
            m_v2b = {}
            wf_v2b = {"folds": pd.DataFrame(), "summary": {}}

        # v3: ridge predictions on ridge_test + fwd_ret_1d
        def _build_ridge_metrics_df(bt_obj, ridge_df_ref):
            """Merge ridge predictions back with fwd_ret_1d for metric computation."""
            if bt_obj is None or bt_obj.get("daily") is None or bt_obj["daily"].empty:
                return None
            dd = bt_obj["daily"][["date", "prediction"]].copy()
            merge_src = ridge_df_ref[["date", "fwd_ret_1d", "close"]].copy()
            merge_src["date"] = pd.to_datetime(merge_src["date"]).dt.normalize()
            dd["date"] = pd.to_datetime(dd["date"]).dt.normalize()
            merged = merge_src.merge(dd, on="date", how="inner")
            if "fwd_ret_5d" in ridge_df_ref.columns:
                fwd5 = ridge_df_ref[["date", "fwd_ret_5d"]].copy()
                fwd5["date"] = pd.to_datetime(fwd5["date"]).dt.normalize()
                merged = merged.merge(fwd5, on="date", how="left")
            else:
                merged["fwd_ret_5d"] = np.nan
            merged["sent_ema"] = merged["prediction"]
            merged["score"] = merged["prediction"]  # for coverage
            return merged

        v3_metric_df = _build_ridge_metrics_df(bt_ridge, ridge_test)
        if v3_metric_df is not None and not v3_metric_df.empty:
            m_v3 = metrics_for_signal(v3_metric_df, "prediction")
            wf_v3 = walk_forward_for_signal(v3_metric_df, "prediction")
        else:
            m_v3 = {}
            wf_v3 = {"folds": pd.DataFrame(), "summary": {}}

        v4_metric_df = _build_ridge_metrics_df(bt_ridge_h, ridge_test_h)
        if v4_metric_df is not None and not v4_metric_df.empty:
            m_v4 = metrics_for_signal(v4_metric_df, "prediction")
            wf_v4 = walk_forward_for_signal(v4_metric_df, "prediction")
        else:
            m_v4 = {}
            wf_v4 = {"folds": pd.DataFrame(), "summary": {}}

        v5_metric_df = _build_ridge_metrics_df(bt_gbm, gbm_test)
        if v5_metric_df is not None and not v5_metric_df.empty:
            m_v5 = metrics_for_signal(v5_metric_df, "prediction")
            wf_v5 = walk_forward_for_signal(v5_metric_df, "prediction")
        else:
            m_v5 = {}
            wf_v5 = {"folds": pd.DataFrame(), "summary": {}}

        v6_metric_df = _build_ridge_metrics_df(bt_evt, evt_test)
        if v6_metric_df is not None and not v6_metric_df.empty:
            m_v6 = metrics_for_signal(v6_metric_df, "prediction")
            wf_v6 = walk_forward_for_signal(v6_metric_df, "prediction")
        else:
            m_v6 = {}
            wf_v6 = {"folds": pd.DataFrame(), "summary": {}}

        elapsed = time.time() - t0
        results[scorer.name] = {
            "scored":       scored,
            "daily":        daily,
            "merged":       merged_test,
            "merged_full":  merged_full,
            "bt":           bt,            # v1: EMA-based (pure sentiment)
            "bt_v2":        bt_v2,         # v2: impulse (pure sentiment)
            "bt_v2b":       bt_v2b,        # v2b: smoothed impulse (pure sentiment)
            "bt_ridge":     bt_ridge,      # v3: ridge ML (pure sentiment)
            "bt_ridge_h":   bt_ridge_h,    # v4: ridge ML (hybrid)
            "bt_gbm":       bt_gbm,        # v5: gradient boosting (pure sentiment, nonlinear)
            "bt_evt":       bt_evt,        # v6: event-driven classifier (5d direction)
            "bt_v7":        bt_v7,         # v7: contrarian-flipped v1 (if warmup IC < -0.05)
            "v7_flipped":   flip_decision,
            "v7_warmup_ic": warmup_ic,
            "metrics":      metrics,       # v1 signal metrics (legacy)
            "cls_metrics":  cls_metrics,   # v1 classification metrics (legacy)
            "walk_forward": wf,            # v1 walk-forward (legacy)
            "per_strategy_metrics": {
                "v1":  {"signal": metrics, "cls": cls_metrics, "wf": wf},
                "v2":  {"signal": m_v2,  "cls": m_v2,  "wf": wf_v2},
                "v2b": {"signal": m_v2b, "cls": m_v2b, "wf": wf_v2b},
                "v3":  {"signal": m_v3,  "cls": m_v3,  "wf": wf_v3},
                "v4":  {"signal": m_v4,  "cls": m_v4,  "wf": wf_v4},
                "v5":  {"signal": m_v5,  "cls": m_v5,  "wf": wf_v5},
                "v6":  {"signal": m_v6,  "cls": m_v6,  "wf": wf_v6},
            },
            "event_types":  ev_break,
            "sharpe_stats": sharpe_stats,
            "time_s":       elapsed,
        }

        # Print comparison of all four strategies
        v1_s = bt["sharpe"]; v1_r = bt["total_return"]
        v2_s = bt_v2["sharpe"] if bt_v2 else float("nan")
        v2_r = bt_v2["total_return"] if bt_v2 else float("nan")
        v2b_s = bt_v2b["sharpe"] if bt_v2b else float("nan")
        v2b_r = bt_v2b["total_return"] if bt_v2b else float("nan")
        v3_s = bt_ridge["sharpe"] if bt_ridge else float("nan")
        v3_r = bt_ridge["total_return"] if bt_ridge else float("nan")
        v4_s = bt_ridge_h["sharpe"] if bt_ridge_h else float("nan")
        v4_r = bt_ridge_h["total_return"] if bt_ridge_h else float("nan")
        v5_s = bt_gbm["sharpe"] if bt_gbm else float("nan")
        v5_r = bt_gbm["total_return"] if bt_gbm else float("nan")
        v6_s = bt_evt["sharpe"] if bt_evt else float("nan")
        v6_r = bt_evt["total_return"] if bt_evt else float("nan")
        print(f"  done in {elapsed:.1f}s")
        print(f"    v1 (EMA, pure):          Sharpe={v1_s:+.2f}  Return={v1_r:+.2%}")
        print(f"    v2 (impulse, pure):      Sharpe={v2_s:+.2f}  Return={v2_r:+.2%}")
        print(f"    v2b (smooth impulse):    Sharpe={v2b_s:+.2f}  Return={v2b_r:+.2%}")
        print(f"    v3 (ridge ML, pure):     Sharpe={v3_s:+.2f}  Return={v3_r:+.2%}")
        print(f"    v4 (ridge ML, hybrid):   Sharpe={v4_s:+.2f}  Return={v4_r:+.2%}")
        print(f"    v5 (GBM, pure sent.):    Sharpe={v5_s:+.2f}  Return={v5_r:+.2%}")
        if bt_evt:
            ev_pct = bt_evt.get("n_events", 0) / max(1, bt_evt.get("n_events", 0) + bt_evt.get("n_holds", 0))
            print(f"    v6 (event clf 5d):       Sharpe={v6_s:+.2f}  Return={v6_r:+.2%}  "
                  f"(traded {bt_evt.get('n_events',0)}/{bt_evt.get('n_events',0)+bt_evt.get('n_holds',0)} days, {ev_pct:.0%})")
        else:
            print(f"    v6 (event clf 5d):       Sharpe={v6_s:+.2f}  Return={v6_r:+.2%}")

        v7_s = bt_v7["sharpe"] if bt_v7 else float("nan")
        v7_r = bt_v7["total_return"] if bt_v7 else float("nan")
        flip_marker = "FLIPPED" if flip_decision else "no-flip"
        print(f"    v7 (contrarian v1):      Sharpe={v7_s:+.2f}  Return={v7_r:+.2%}  "
              f"[{flip_marker}, warmup IC={warmup_ic:+.3f}]")
        if bt_ridge and bt_ridge.get("feature_importances"):
            top = sorted(bt_ridge["feature_importances"].items(),
                        key=lambda x: abs(x[1]), reverse=True)[:5]
            print(f"    v3 top features: {', '.join(f'{k}={v:+.4f}' for k,v in top)}")
        if bt_ridge_h and bt_ridge_h.get("feature_importances"):
            top = sorted(bt_ridge_h["feature_importances"].items(),
                        key=lambda x: abs(x[1]), reverse=True)[:5]
            print(f"    v4 top features: {', '.join(f'{k}={v:+.4f}' for k,v in top)}")
        if bt_gbm and bt_gbm.get("feature_importances"):
            top = sorted(bt_gbm["feature_importances"].items(),
                        key=lambda x: abs(x[1]), reverse=True)[:5]
            print(f"    v5 top features: {', '.join(f'{k}={v:+.4f}' for k,v in top)}")

    # ---- DEFLATED SHARPE (requires cross-model variance) ----
    daily_srs = np.array([r["sharpe_stats"]["sr_daily"] for r in results.values()])
    var_trials = float(np.var(daily_srs, ddof=1)) if len(daily_srs) > 1 else 1.0
    n_trials = len(results)
    for name, r in results.items():
        s = r["sharpe_stats"]
        psr = probabilistic_sharpe_ratio(s["sr_daily"], 0.0, s["n"], s["skew"], s["kurt"])
        dsr = deflated_sharpe_ratio(s["sr_daily"], s["n"], s["skew"], s["kurt"],
                                    n_trials, var_trials)
        r["psr"] = psr
        r["dsr"] = dsr

    return results


# ==========================================================================
# 10. REPORTING
# ==========================================================================
def print_leaderboard(results: dict, price_df: pd.DataFrame):
    # Buy & hold over TEST WINDOW ONLY (not full 365d), matches strategies
    test_start_ts = pd.to_datetime(TEST_START_DATE)
    test_px = price_df[pd.to_datetime(price_df["date"]) >= test_start_ts]
    if not test_px.empty:
        bh_ret = test_px["close"].iloc[-1] / test_px["close"].iloc[0] - 1
    else:
        bh_ret = float("nan")

    rows = []
    for name, r in results.items():
        m  = r["metrics"]
        cm = r["cls_metrics"]
        bt = r["bt"]
        rows.append({
            "model":    name,
            "IC_1d":    m.get("IC_spearman_1d", np.nan),
            "roll_IC":  m.get("rolling_IC_mean", np.nan),
            "hit":      m.get("hit_rate", np.nan),
            "acc":      cm.get("accuracy", np.nan),
            "macroF1":  cm.get("macro_f1", np.nan),
            "mcc":      cm.get("mcc", np.nan),
            "absten":   cm.get("abstain_rate", np.nan),
            "sharpe":   bt["sharpe"],
            "PSR":      r.get("psr", np.nan),
            "DSR":      r.get("dsr", np.nan),
            "return":   bt["total_return"],
            "max_dd":   bt["max_dd"],
            "final_$":  bt["final_value"],
            "time_s":   r["time_s"],
        })
    lb = pd.DataFrame(rows).sort_values("DSR", ascending=False)

    print("\n" + "=" * 130)
    print("LEADERBOARD — signal quality + classification + deflated backtest")
    print("(DSR = Deflated Sharpe Ratio; >0.95 means robust to multi-testing across all trialed models)")
    print("Sorted by DSR.")
    print("=" * 130)
    print(f"{'model':<16} {'IC_1d':>7} {'rollIC':>7} {'hit':>6} "
          f"{'acc':>6} {'F1m':>6} {'MCC':>7} {'absten':>7} "
          f"{'sharpe':>7} {'PSR':>6} {'DSR':>6} "
          f"{'return':>8} {'maxDD':>8} {'final$':>10}")
    print("-" * 130)
    for _, r in lb.iterrows():
        print(f"{r['model']:<16} {r['IC_1d']:+.3f}  {r['roll_IC']:+.3f}  "
              f"{r['hit']:.2f}  {r['acc']:.2f}  {r['macroF1']:.2f}  "
              f"{r['mcc']:+.3f}  {r['absten']:.2f}  "
              f"{r['sharpe']:+.2f}  {r['PSR']:.3f}  {r['DSR']:.3f}  "
              f"{r['return']:+.2%}  {r['max_dd']:+.2%}  "
              f"${r['final_$']:>8.2f}")
    print("-" * 130)
    print(f"{'buy & hold':<16} {'-':>7} {'-':>7} {'-':>6} {'-':>6} {'-':>6} "
          f"{'-':>7} {'-':>7} {'-':>7} {'-':>6} {'-':>6} {bh_ret:+.2%}")
    print("=" * 130)
    return lb


def print_strategy_comparison(results: dict, price_df: pd.DataFrame):
    """Compare v1 through v5 across all models."""
    test_prices = price_df[pd.to_datetime(price_df["date"]) >= pd.to_datetime(TEST_START_DATE)]
    if not test_prices.empty:
        bh_ret = test_prices["close"].iloc[-1] / test_prices["close"].iloc[0] - 1
    else:
        bh_ret = float("nan")

    print("\n" + "=" * 210)
    print("STRATEGY COMPARISON — v1, v2, v2b are PURE SENTIMENT. v3/v5/v6 are pure-sent. ML. v4 is hybrid ML.")
    print("  v1: EMA  |  v2: Impulse+surprise  |  v2b: 3-day smoothed impulse  |  v3: Ridge ML (pure sent.)")
    print("  v4: Ridge ML (hybrid)            |  v5: GBM ML (pure sent., nonlinear)")
    print("  v6: EVENT-DRIVEN CLASSIFIER — 5-day direction, trades only when |surprise| > {:.2f}".format(V6_EVENT_THRESHOLD))
    print("=" * 210)
    print(f"{'model':<14} {'--- v1 ---':>22} {'--- v2 ---':>22} {'--- v2b ---':>22} "
          f"{'--- v3 Ridge ---':>22} {'--- v4 Hybrid ---':>22} {'--- v5 GBM ---':>22} "
          f"{'--- v6 EvClf ---':>22}")
    print(f"{'':14} {'Shrp':>5} {'Ret':>7} {'MDD':>7}   "
          f"{'Shrp':>5} {'Ret':>7} {'MDD':>7}   "
          f"{'Shrp':>5} {'Ret':>7} {'MDD':>7}   "
          f"{'Shrp':>5} {'Ret':>7} {'MDD':>7}   "
          f"{'Shrp':>5} {'Ret':>7} {'MDD':>7}   "
          f"{'Shrp':>5} {'Ret':>7} {'MDD':>7}   "
          f"{'Shrp':>5} {'Ret':>7} {'MDD':>7}")
    print("-" * 210)

    for name, r in results.items():
        bt1 = r["bt"]
        bt2 = r.get("bt_v2")
        bt2b = r.get("bt_v2b")
        bt3 = r.get("bt_ridge")
        bt4 = r.get("bt_ridge_h")
        bt5 = r.get("bt_gbm")
        bt6 = r.get("bt_evt")

        def _fmt_bt(bt):
            if bt is None:
                return f"{'--':>5} {'--':>7} {'--':>7}"
            return (f"{bt['sharpe']:>+5.2f} {bt['total_return']:>+7.2%} "
                    f"{bt['max_dd']:>+7.2%}")

        print(f"{name:<14} {_fmt_bt(bt1)}   {_fmt_bt(bt2)}   {_fmt_bt(bt2b)}   "
              f"{_fmt_bt(bt3)}   {_fmt_bt(bt4)}   {_fmt_bt(bt5)}   {_fmt_bt(bt6)}")

    print("-" * 210)
    print(f"{'buy & hold':<14} {'':>5} {bh_ret:>+7.2%}")
    print("=" * 210)

    # Feature importances for best model in each ML strategy
    def _find_best(key, label):
        best = None; best_sharpe = -999
        for name, r in results.items():
            bt = r.get(key)
            if bt and bt.get("sharpe", -999) > best_sharpe:
                best_sharpe = bt["sharpe"]
                best = (name, bt, label)
        return best

    best_v3 = _find_best("bt_ridge", "v3 Ridge (pure sent.)")
    best_v4 = _find_best("bt_ridge_h", "v4 Ridge (hybrid)")
    best_v5 = _find_best("bt_gbm", "v5 GBM (pure sent.)")

    for best in [best_v3, best_v4, best_v5]:
        if best is None:
            continue
        name, bt_best, label = best
        fi = bt_best.get("feature_importances", {})
        if not fi:
            continue
        alpha_str = f", alpha={bt_best.get('best_alpha', '?')}" if "best_alpha" in bt_best else ""
        print(f"\nBEST {label} FEATURE IMPORTANCES (model: {name}{alpha_str})")
        print("-" * 60)
        sorted_fi = sorted(fi.items(), key=lambda x: abs(x[1]), reverse=True)
        # Normalize bar length to largest magnitude in this set
        max_abs = max(abs(v) for _, v in sorted_fi) if sorted_fi else 1e-8
        for feat, coef in sorted_fi:
            bar = "█" * int(min(30 * abs(coef) / max_abs, 30)) if max_abs > 0 else ""
            sign = "+" if coef > 0 else "-"
            print(f"  {feat:<22} {sign}{abs(coef):.4f}  {bar}")
    print()


def print_per_strategy_metrics(results: dict):
    """
    For each strategy (v1..v5), print IC / F1 / MCC / abstain per model.
    """
    strategies = [
        ("v1", "v1 EMA (pure sent.)"),
        ("v2", "v2 Impulse (pure sent.)"),
        ("v2b", "v2b Smoothed Impulse (pure sent.)"),
        ("v3", "v3 Ridge ML (pure sent.)"),
        ("v4", "v4 Ridge ML (hybrid)"),
        ("v5", "v5 GBM ML (pure sent., nonlinear)"),
        ("v6", "v6 Event Classifier (5d direction)"),
    ]
    for strat_key, strat_label in strategies:
        print("\n" + "=" * 110)
        print(f"SIGNAL QUALITY METRICS — {strat_label}")
        print("=" * 110)
        print(f"{'model':<16} {'IC_1d':>8} {'IC_5d':>8} {'rollIC':>8} {'rollICσ':>8} "
              f"{'hit':>6} {'acc':>6} {'F1m':>6} {'MCC':>7} {'absten':>7} {'graded':>7}")
        print("-" * 110)
        for name, r in results.items():
            psm = r.get("per_strategy_metrics", {}).get(strat_key, {})
            m = psm.get("signal", {}) or {}
            def _fmt(k, fmt, default="--"):
                v = m.get(k, np.nan)
                if pd.isna(v):
                    return f"{default:>8}" if fmt.endswith("f}") else f"{default:>6}"
                try:
                    return fmt.format(v)
                except Exception:
                    return f"{default:>8}"
            print(f"{name:<16} "
                  f"{_fmt('IC_spearman_1d', '{:>+8.3f}'):>8} "
                  f"{_fmt('IC_spearman_5d', '{:>+8.3f}'):>8} "
                  f"{_fmt('rolling_IC_mean', '{:>+8.3f}'):>8} "
                  f"{_fmt('rolling_IC_std', '{:>8.3f}'):>8} "
                  f"{_fmt('hit_rate', '{:>6.2f}'):>6} "
                  f"{_fmt('accuracy', '{:>6.2f}'):>6} "
                  f"{_fmt('macro_f1', '{:>6.2f}'):>6} "
                  f"{_fmt('mcc', '{:>+7.3f}'):>7} "
                  f"{_fmt('abstain_rate', '{:>7.2f}'):>7} "
                  f"{int(m.get('graded_days', 0)):>7d}")
        print("=" * 110)


def print_per_strategy_walk_forward(results: dict):
    """Walk-forward stability for each strategy separately."""
    strategies = [
        ("v1", "v1 EMA (pure sent.)"),
        ("v2", "v2 Impulse (pure sent.)"),
        ("v2b", "v2b Smoothed Impulse (pure sent.)"),
        ("v3", "v3 Ridge ML (pure sent.)"),
        ("v4", "v4 Ridge ML (hybrid)"),
        ("v5", "v5 GBM ML (pure sent., nonlinear)"),
        ("v6", "v6 Event Classifier (5d direction)"),
    ]
    for strat_key, strat_label in strategies:
        print("\n" + "=" * 110)
        print(f"WALK-FORWARD OOS STABILITY — {strat_label}  (mean ± std across folds)")
        print("=" * 110)
        print(f"{'model':<16} {'IC':>18} {'macroF1':>18} {'MCC':>18} "
              f"{'Sharpe':>18} {'Return':>18}")
        print("-" * 110)
        for name, r in results.items():
            psm = r.get("per_strategy_metrics", {}).get(strat_key, {})
            wf = (psm.get("wf") or {}).get("summary", {})
            if not wf:
                print(f"{name:<16}   (insufficient data)")
                continue
            def _g(k):
                return wf.get(k, np.nan)
            print(f"{name:<16} "
                  f"{_g('ic_mean'):>+8.3f} ± {_g('ic_std'):.3f}    "
                  f"{_g('f1_mean'):>6.3f} ± {_g('f1_std'):.3f}    "
                  f"{_g('mcc_mean'):>+6.3f} ± {_g('mcc_std'):.3f}   "
                  f"{_g('sharpe_mean'):>+5.2f} ± {_g('sharpe_std'):.2f}   "
                  f"{_g('return_mean'):>+6.2%} ± {_g('return_std'):.2%}")
        print("=" * 110)


def print_walk_forward(results: dict):
    print("\n" + "=" * 100)
    print("WALK-FORWARD OUT-OF-SAMPLE STABILITY  (mean ± std across folds)")
    print("A model with high mean but high std is one-fold luck, not alpha.")
    print("=" * 100)
    print(f"{'model':<16} {'IC':>16} {'macroF1':>16} {'MCC':>16} "
          f"{'Sharpe':>16} {'Return':>16}")
    print("-" * 100)
    for name, r in results.items():
        wf = r["walk_forward"]["summary"]
        if not wf:
            print(f"{name:<16}   (insufficient data for walk-forward)")
            continue
        print(f"{name:<16} "
              f"{wf['ic_mean']:+.3f} ± {wf['ic_std']:.3f}    "
              f"{wf['f1_mean']:.3f} ± {wf['f1_std']:.3f}    "
              f"{wf['mcc_mean']:+.3f} ± {wf['mcc_std']:.3f}   "
              f"{wf['sharpe_mean']:+.2f} ± {wf['sharpe_std']:.2f}   "
              f"{wf['return_mean']:+.2%} ± {wf['return_std']:.2%}")
    print("=" * 100)


def print_event_type_breakdown(results: dict):
    """Only meaningful for LLM scorers (FinBERT/VADER tag everything as 'other')."""
    print("\n" + "=" * 100)
    print("PER-EVENT-TYPE SIGNAL QUALITY  (canonical articles only)")
    print("Which categories of news actually predict next-day returns for each model?")
    print("=" * 100)
    for name, r in results.items():
        ev = r["event_types"]
        if ev is None or ev.empty:
            continue
        # Only show if there's meaningful categorical variety
        if ev["event_type"].nunique() < 2:
            continue
        print(f"\n  [{name}]")
        print(f"    {'event_type':<22} {'n':>5} {'IC':>7} "
              f"{'pos_bps':>9} {'neg_bps':>9}")
        print(f"    {'-' * 22} {'-' * 5} {'-' * 7} {'-' * 9} {'-' * 9}")
        for _, row in ev.iterrows():
            ic_str = f"{row['ic']:+.3f}" if pd.notna(row['ic']) else "   --"
            pos_str = f"{row['pos_ret_bps']:+.1f}" if pd.notna(row['pos_ret_bps']) else "    --"
            neg_str = f"{row['neg_ret_bps']:+.1f}" if pd.notna(row['neg_ret_bps']) else "    --"
            print(f"    {row['event_type']:<22} {row['n']:>5d} {ic_str:>7} "
                  f"{pos_str:>9} {neg_str:>9}")
    print("=" * 100)


def print_classification_report(results: dict):
    print("\n" + "=" * 90)
    print("PER-CLASS CLASSIFICATION REPORT")
    print("(y_true = sign(fwd_ret_1d), y_pred = sign(sent_ema); flat days & abstentions excluded)")
    print("=" * 90)
    print(f"{'model':<16} {'prec_up':>8} {'rec_up':>8} {'F1_up':>8} "
          f"{'prec_dn':>8} {'rec_dn':>8} {'F1_dn':>8} {'graded':>8}")
    print("-" * 90)
    for name, r in results.items():
        c = r["cls_metrics"]
        print(f"{name:<16} "
              f"{c.get('precision_up',   float('nan')):>8.3f} "
              f"{c.get('recall_up',      float('nan')):>8.3f} "
              f"{c.get('f1_up',          float('nan')):>8.3f} "
              f"{c.get('precision_down', float('nan')):>8.3f} "
              f"{c.get('recall_down',    float('nan')):>8.3f} "
              f"{c.get('f1_down',        float('nan')):>8.3f} "
              f"{c.get('graded_days',    0):>8d}")
    print("=" * 90)

    # Confusion matrices
    print("\nCONFUSION MATRICES  (rows = actual, cols = predicted; order: [DOWN, UP])")
    print("-" * 60)
    for name, r in results.items():
        cm = r["cls_metrics"].get("cm")
        if cm is None:
            continue
        print(f"\n  {name}")
        print(f"              pred_DOWN  pred_UP")
        print(f"   act_DOWN      {cm[0,0]:>6d}   {cm[0,1]:>6d}")
        print(f"   act_UP        {cm[1,0]:>6d}   {cm[1,1]:>6d}")
    print()


def plot_comparison(results: dict, price_df: pd.DataFrame,
                    test_start: str = TEST_START_DATE):
    """
    Plotly figure with a dropdown selector to switch between v1/v2/v3/v4.
    Each view shows equity curves for all models + buy & hold reference.
    """
    test_start_ts = pd.to_datetime(test_start)
    px = price_df[pd.to_datetime(price_df["date"]) >= test_start_ts].copy()
    if px.empty:
        print("No price data in test window — skipping plot.")
        return

    fig = go.Figure()
    palette = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728",
               "#9467bd", "#8c564b", "#e377c2", "#7f7f7f",
               "#bcbd22", "#17becf"]

    strategies = [
        ("v1", "v1 EMA (pure sent.)", "bt"),
        ("v2", "v2 Impulse (pure sent.)", "bt_v2"),
        ("v2b", "v2b Smoothed Impulse (pure sent.)", "bt_v2b"),
        ("v3", "v3 Ridge ML (pure sent.)", "bt_ridge"),
        ("v4", "v4 Ridge ML (hybrid)", "bt_ridge_h"),
        ("v5", "v5 GBM ML (pure sent., nonlinear)", "bt_gbm"),
        ("v6", "v6 Event Classifier (5d direction)", "bt_evt"),
    ]

    # Buy & Hold reference (same across all strategies, always visible)
    bh_shares = INITIAL_CAPITAL / px["close"].iloc[0]
    bh_y = bh_shares * px["close"].values
    fig.add_trace(go.Scatter(
        x=px["date"], y=bh_y,
        name="Buy & Hold", line=dict(color="black", dash="dash", width=2),
        visible=True,
        legendgroup="bh",
    ))

    # Track which traces belong to which strategy
    trace_strategy = ["all"]  # buy & hold

    # Add one trace per (strategy, model) combination
    for strat_key, strat_label, bt_key in strategies:
        for i, (name, r) in enumerate(results.items()):
            c = palette[i % len(palette)]
            bt_obj = r.get(bt_key)
            if bt_obj is None or bt_obj.get("daily") is None or bt_obj["daily"].empty:
                # Placeholder trace so trace counts stay consistent
                fig.add_trace(go.Scatter(
                    x=[px["date"].iloc[0]], y=[INITIAL_CAPITAL],
                    name=f"{name} ({strat_key})",
                    line=dict(color=c, width=2),
                    visible=(strat_key == "v1"),
                    legendgroup=strat_key,
                ))
            else:
                d = bt_obj["daily"]
                fig.add_trace(go.Scatter(
                    x=d["date"], y=d["portfolio_value"],
                    name=f"{name}",
                    line=dict(color=c, width=2),
                    visible=(strat_key == "v1"),
                    legendgroup=strat_key,
                ))
            trace_strategy.append(strat_key)

    # Build visibility vectors for each dropdown option
    def _visibility(selected_strat):
        vis = []
        for s in trace_strategy:
            if s == "all":
                vis.append(True)
            else:
                vis.append(s == selected_strat)
        return vis

    buttons = []
    for strat_key, strat_label, _ in strategies:
        buttons.append(dict(
            label=strat_label,
            method="update",
            args=[
                {"visible": _visibility(strat_key)},
                {"title": f"Sentiment Benchmark — {STOCK_TICKER} — {strat_label} "
                          f"(test window: {test_start} → today)"},
            ],
        ))

    fig.update_layout(
        height=650,
        template="plotly_white",
        title=f"Sentiment Benchmark — {STOCK_TICKER} — v1 EMA (pure sent.) "
              f"(test window: {test_start} → today)",
        xaxis_title="Date",
        yaxis_title="Portfolio Value ($)",
        updatemenus=[dict(
            active=0,
            buttons=buttons,
            direction="down",
            x=0.01, xanchor="left",
            y=1.12, yanchor="top",
            bgcolor="white",
            bordercolor="#888",
        )],
        annotations=[dict(
            text="Strategy:", x=0.01, xref="paper",
            y=1.16, yref="paper", showarrow=False,
            xanchor="left", font=dict(size=12),
        )],
    )
    fig.show()


def print_agreement(results: dict):
    per_model = {name: r["merged_full"] for name, r in results.items()}
    corr = inter_model_agreement(per_model)
    print("\nINTER-MODEL AGREEMENT (Spearman corr of daily sent_ema, full range)")
    print("=" * 60)
    print(corr.round(2).to_string())
    print("=" * 60)


# ==========================================================================
# 11. MAIN
# ==========================================================================
if __name__ == "__main__":
    end_date = datetime.now()
    start_date = end_date - timedelta(days=LOOKBACK_DAYS)

    print("=" * 60)
    print(f"SENTIMENT-ONLY BENCHMARK — {STOCK_TICKER}")
    print(f"Fetch window: {start_date.date()} -> {end_date.date()}")
    print(f"TEST window:  {TEST_START_DATE} -> {end_date.date()}")
    print(f"(pre-test data is warmup only — lookahead-leakage guard)")
    print(f"Capital: ${INITIAL_CAPITAL:,.0f}")
    print("=" * 60)

    # 1. Data
    prices = get_prices(STOCK_TICKER, start_date.strftime("%Y-%m-%d"))
    news   = load_or_fetch_news(
        start_date.strftime("%Y-%m-%d"),
        end_date.strftime("%Y-%m-%d"),
    )
    if news.empty or prices.empty:
        raise SystemExit("No data.")

    # 1b. Event clustering / deduplication (SOTA upgrade 3)
    news = cluster_articles(news)

    # 1c. Build weekly macro narrative (separate DeepSeek call per week)
    macro_narr = build_macro_narrative(
        start_date.strftime("%Y-%m-%d"),
        end_date.strftime("%Y-%m-%d"),
    )

    # 2. Scorer roster — April 2026 frontier lineup on OpenRouter.
    #    ACTIVE = 8-model minimum: good provider diversity, frontier + value + classical.
    #    Uncomment the others once your cache is warm and you want a wider sweep.
    scorers = [
        # --- OpenAI ---
        OpenRouterScorer("openai/gpt-5.4",                       "gpt54"),
        # OpenRouterScorer("openai/gpt-5.1",                       "gpt51"),
        # OpenRouterScorer("openai/gpt-oss-120b",                  "gpt_oss_120b"),

        # --- Anthropic ---
        OpenRouterScorer("anthropic/claude-opus-4.7",            "opus47"),
        # OpenRouterScorer("anthropic/claude-opus-4.6",            "opus46"),
        OpenRouterScorer("anthropic/claude-sonnet-4.6",          "sonnet46"),
        OpenRouterScorer("anthropic/claude-haiku-4.5",           "haiku45"),

        # --- Google ---
        OpenRouterScorer("google/gemini-3.1-pro-preview",        "gemini31_pro"),
        # OpenRouterScorer("google/gemini-3-flash-preview",        "gemini3_flash"),

        # --- DeepSeek (frontier-quality value play) ---
        OpenRouterScorer("deepseek/deepseek-v3.2",               "deepseek_v32"),

        # --- Chinese frontier (the 2026 story) ---
        OpenRouterScorer("xiaomi/mimo-v2-pro",                   "mimo_v2_pro"),
        # OpenRouterScorer("minimax/minimax-m2.7",                 "minimax_m27"),
        # OpenRouterScorer("qwen/qwen-3.6-plus",                   "qwen36_plus"),
        # OpenRouterScorer("moonshot/kimi-k2.5",                   "kimi_k25"),

        # --- xAI ---
        # OpenRouterScorer("x-ai/grok-4.1-fast",                   "grok41_fast"),

        # --- Open-source baselines ---
        # OpenRouterScorer("nvidia/nemotron-3-super-120b",         "nemotron3"),
        # OpenRouterScorer("meta-llama/llama-3.3-70b-instruct",    "llama_70b"),

        # --- Classical finance-NLP baselines (always keep — they're free) ---
        FinBERTScorer(),
        VaderScorer(),
    ]

    # 3. Run all evaluations (slicing to test window happens inside)
    results = evaluate_all(scorers, news, prices,
                            test_start=TEST_START_DATE,
                            macro_narrative=macro_narr)

    # 4. Reports
    leaderboard = print_leaderboard(results, prices)
    print_strategy_comparison(results, prices)
    print_per_strategy_metrics(results)
    print_per_strategy_walk_forward(results)
    print_classification_report(results)
    print_event_type_breakdown(results)
    print_agreement(results)
    plot_comparison(results, prices, test_start=TEST_START_DATE)

    # 5. Save leaderboard
    leaderboard.to_csv(os.path.join(DATA_DIR, "leaderboard.csv"), index=False)
    print(f"\nLeaderboard saved to {DATA_DIR}/leaderboard.csv")
