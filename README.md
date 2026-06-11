<img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&height=150&text=FinEdge&fontSize=48&fontColor=fff&animation=fadeIn&desc=AI+Stock+Analysis+Platform+%7C+Senior+Design+Project+%7C+AUS+2025-2026&descSize=14&descFontColor=fff&descAlignY=78" width="100%"/>

---

A full-stack AI-powered stock analysis platform built as a Senior Design project over two semesters at AUS. 4-person team. I was the Project Manager and Fundamental Analysis Lead.

The platform runs three independent ML models and fuses them into a single weighted Buy, Sell, or Hold recommendation across 237 US large-cap stocks.

---

## Fundamental Analysis
**My model · LightGBM classifier trained on 10 years of quarterly financial data**

Benchmarked Logistic Regression, Random Forest, and LightGBM before settling on LightGBM with Optuna hyperparameter tuning. Built sector-specific models rather than one global model so each sector's financial patterns are captured independently.

| Metric | Result |
|--------|--------|
| IC Score | 0.1477 (professional threshold is 0.05) |
| AUC | 0.5817 |
| Directional hit rate | 56.5% across 9,026 predictions |
| Market outperformance | +12 percentage points on Strong Buy picks |

---

## Technical Analysis
**Arya's model · GRU ensemble**

| Metric | Result |
|--------|--------|
| MSFT forecast | $414 to $418 |
| Policy confidence | 0.497 |
| MAE | 0.479 |

---

## Sentiment Analysis
**Zein's model · News and social media analysis**

| Metric | Result |
|--------|--------|
| Return | +178% vs 130% buy-and-hold benchmark |

---

## Fusion Model

All three models feed into an IC-weighted combined recommendation with the following logic. Caps at HOLD when Fundamental signals SELL. Requires agreement from at least 2 models for a STRONG BUY or STRONG SELL signal.

| Metric | Result |
|--------|--------|
| Combined Sharpe ratio | 3.69 |

---

## Stack

<p align="center">
  <img src="https://skillicons.dev/icons?i=python,fastapi,nextjs,postgres,docker" />
</p>

**ML** &nbsp;·&nbsp; LightGBM · Optuna · scikit-learn  
**Data** &nbsp;·&nbsp; yfinance · NewsAPI · EventRegistry · Alpaca API  
**Charts** &nbsp;·&nbsp; TradingView real-time  
**AI** &nbsp;·&nbsp; OpenRouter · Gemini Flash 3  

---

## Research

A peer-reviewed IEEE conference paper was co-authored based on this project. Results were presented on an academic poster to faculty at AUS.

<img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&height=100&section=footer" width="100%"/>
