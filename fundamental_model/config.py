# ============================================================
# config.py
# Central settings file for the Fundamental ML Stock Model
# ALL other files import from here — never hardcode values elsewhere
# ============================================================

import os
from pathlib import Path

# ─────────────────────────────────────────────────────────────
# 1. API KEY
# ─────────────────────────────────────────────────────────────
EODHD_API_KEY = "698dc9a128cd33.93083824"   # <-- only edit this line

# ─────────────────────────────────────────────────────────────
# 2. THE 5 TARGET STOCKS
# These are the stocks we generate final BUY/HOLD/SELL signals for.
# All 5 must also appear somewhere in UNIVERSE below.
# ─────────────────────────────────────────────────────────────
TARGET_STOCKS = ["TSLA", "META", "GOOGL", "MSFT", "AAPL"]

# ─────────────────────────────────────────────────────────────
# 3. THE 100-STOCK TRAINING UNIVERSE
# Diverse across sectors so the model learns general patterns.
# Includes all 5 target stocks.
# ─────────────────────────────────────────────────────────────
UNIVERSE = [
    # ── TECHNOLOGY (30) ──────────────────────────────────
    "AAPL", "MSFT", "NVDA", "GOOGL", "META",
    "AVGO", "ORCL", "CRM", "AMD", "INTC",
    "QCOM", "IBM", "ADBE", "NOW", "SNOW",
    "UBER", "PLTR", "NET", "DDOG", "LYFT",
    "AMAT", "MU", "LRCX", "KLAC", "MRVL",
    "PANW", "CRWD", "ZS", "OKTA", "TEAM",

    # ── FINANCIALS (30) ──────────────────────────────────
    "JPM", "BAC", "GS", "MS", "WFC",
    "C", "V", "MA", "AXP", "BLK",
    "SCHW", "COF", "USB", "PNC", "TFC",
    "CB", "MMC", "AON", "TRV", "ALL",
    "MET", "PRU", "AFL", "AIG", "PGR",
    "ICE", "CME", "SPGI", "MCO", "FIS",

    # ── HEALTHCARE (30) ──────────────────────────────────
    "JNJ", "UNH", "PFE", "ABBV", "MRK",
    "LLY", "TMO", "ABT", "BMY", "AMGN",
    "GILD", "CVS", "CI", "HUM", "ISRG",
    "BSX", "MDT", "SYK", "ZBH", "BAX",
    "IDXX", "IQV", "DGX", "LH",  "HOLX",
    "BIIB", "REGN", "VRTX", "MRNA", "ILMN",

    # ── CONSUMER (40) ────────────────────────────────────
    "AMZN", "TSLA", "WMT", "COST", "MCD",
    "SBUX", "NKE", "PG",  "KO",  "PEP",
    "CL",   "EL",  "TGT", "LOW", "HD",
    "TJX",  "ROST","DLTR","DG",  "ULTA",
    "YUM",  "CMG", "DRI", "MKC", "GIS",
    "K",    "CPB", "HRL", "SJM", "CAG",
    "CL",   "CHD", "ENR", "SPB", "WD",
    "F",    "GM",  "RIVN","LCID","NKLA",

    # ── ENERGY (25) ──────────────────────────────────────
    "XOM", "CVX", "COP", "SLB", "EOG",
    "PSX", "VLO", "MPC", "OXY", "HAL",
    "DVN", "FANG","MRO", "APA", "HES",
    "BKR", "NOV", "WMB", "OKE", "KMI",
    "LNG", "CTRA","PR",  "SM",  "RRC",

    # ── INDUSTRIALS (30) ─────────────────────────────────
    "BA",  "CAT", "HON", "GE",  "MMM",
    "RTX", "LMT", "DE",  "EMR", "ITW",
    "ETN", "PH",  "ROK", "DOV", "XYL",
    "GWW", "FAST","SWK", "TT",  "IR",
    "CARR","OTIS","WAB", "CSX", "UNP",
    "NSC", "UPS", "FDX", "DAL", "UAL",

    # ── COMMUNICATION (20) ───────────────────────────────
    "GOOGL","META","NFLX","DIS", "CMCSA",
    "T",   "VZ",  "TMUS","WBD", "PARA",
    "FOX", "NYT", "IAC", "MTCH","PINS",
    "SNAP","RDDT","ZM",  "TWLO","BAND",

    # ── REAL ESTATE (15) ─────────────────────────────────
    "PLD", "AMT", "EQIX","SPG", "O",
    "PSA", "WELL","AVB", "EQR", "MAA",
    "UDR", "CPT", "ESS", "AIV", "NLY",

    # ── MATERIALS & UTILITIES (20) ───────────────────────
    "LIN", "APD", "SHW", "ECL", "DD",
    "DOW", "NEM", "FCX", "NUE", "RS",
    "NEE", "DUK", "SO",  "D",   "AEP",
    "EXC", "XEL", "WEC", "ES",  "AWK",
]

# ─────────────────────────────────────────────────────────────
# 4. DATA SETTINGS
# ─────────────────────────────────────────────────────────────
PRICE_START_DATE   = "max"  # Pull price history from max date
PRICE_END_DATE     = "today"  # Pull price history to this date
FORWARD_MONTHS     = 6             # Predict returns 6 months ahead
MIN_HISTORY_YEARS  = 5             # Skip stocks with less than 5 years data
MIN_QUARTERS = 20   # Each stock needs at least 20 quarters (5 years) of data to be included

# ─────────────────────────────────────────────────────────────
# 5. SIGNAL RULES — Two-layer system
# Layer 1: Rank the 5 target stocks against each other (1 = best)
# Layer 2: Check score vs full 100-stock universe (percentile)
#
# Final signal logic:
#   Rank 1-2 AND top 50% of universe     → STRONG BUY
#   Rank 1-2 AND bottom 50% of universe  → WEAK BUY (caution)
#   Rank 3                               → HOLD
#   Rank 4-5 AND top 50% of universe     → WEAK SELL
#   Rank 4-5 AND bottom 50% of universe  → STRONG SELL
# ─────────────────────────────────────────────────────────────
SIGNAL_BUY_RANKS        = [1, 2]
SIGNAL_HOLD_RANKS       = [3]
SIGNAL_SELL_RANKS       = [4, 5]
STRONG_SIGNAL_THRESHOLD = 0.50

# ─────────────────────────────────────────────────────────────
# 6. PATHS  (all relative to this file's location)
# ─────────────────────────────────────────────────────────────
BASE_DIR       = Path(__file__).resolve().parent

DATA_RAW_FUND  = BASE_DIR / "data" / "raw" / "fundamentals"
DATA_RAW_PRICE = BASE_DIR / "data" / "raw" / "prices"
DATA_PROC      = BASE_DIR / "data" / "processed"
OUT_MODELS     = BASE_DIR / "outputs" / "models"
OUT_PLOTS      = BASE_DIR / "outputs" / "plots"
OUT_SIGNALS    = BASE_DIR / "outputs" / "signals"

# ─────────────────────────────────────────────────────────────
# 7. AUTO-CREATE ALL FOLDERS ON IMPORT
# Runs every time any file does: from config import ...
# Safe to run multiple times (exist_ok=True)
# ─────────────────────────────────────────────────────────────
for _folder in [DATA_RAW_FUND, DATA_RAW_PRICE, DATA_PROC,
                OUT_MODELS, OUT_PLOTS, OUT_SIGNALS]:
    os.makedirs(_folder, exist_ok=True)

# ─────────────────────────────────────────────────────────────
# 8. SANITY CHECKS  (catches mistakes immediately on import)
# ─────────────────────────────────────────────────────────────
assert len(UNIVERSE) >= 50, \
    f"UNIVERSE must have at least 50 stocks, got {len(UNIVERSE)}"

assert all(t in UNIVERSE for t in TARGET_STOCKS), \
    f"All TARGET_STOCKS must be in UNIVERSE. Missing: {[t for t in TARGET_STOCKS if t not in UNIVERSE]}"

assert EODHD_API_KEY != "PASTE_YOUR_EODHD_KEY_HERE", \
    "Forgot to paste your EODHD API key in config.py!"

# ─────────────────────────────────────────────────────────────
# 9. CONFIRMATION PRINT
# ─────────────────────────────────────────────────────────────
print("=" * 55)
print("Config loaded successfully")
print(f"    Universe   : {len(UNIVERSE)} stocks across 8 sectors")
print(f"    Targets    : {TARGET_STOCKS}")
print(f"    Predict    : {FORWARD_MONTHS}-month forward returns")
print(f"    Signal rule: Top 2 = BUY | Rank 3 = HOLD | Bottom 2 = SELL")
print(f"    Data folder: {BASE_DIR}")
print("=" * 55)


# ─────────────────────────────────────────────────────────────
# RUN THIS FILE DIRECTLY TO VERIFY SETUP:
#   python config.py
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\nFolder check:")
    all_folders = [DATA_RAW_FUND, DATA_RAW_PRICE, DATA_PROC,
                   OUT_MODELS, OUT_PLOTS, OUT_SIGNALS]
    for folder in all_folders:
        status = "Exists" if folder.exists() else "MISSING!"
        print(f"  {status}  →  {folder.relative_to(BASE_DIR)}")
