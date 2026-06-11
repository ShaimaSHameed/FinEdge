import json
import asyncio
from typing import Dict, Any, List
import httpx

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class LLMAnalyzer:
    def __init__(self):
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        self.api_key = settings.OPENROUTER_API_KEY
        self.model = settings.LLM_MODEL

    async def analyze_news_article(
        self,
        ticker: str,
        title: str,
        body: str
    ) -> Dict[str, Any]:
        article_text = body or title or ""
        if len(article_text.strip()) < 30:
            return {
                "score": 0.0,
                "verdict": "HOLD",
                "reasoning": "Insufficient context for analysis.",
                "confidence": 0.0,
                "relevance": 0.0,
                "materiality": 0.0,
                "event_type": "other",
                "horizon": "days",
                "key_drivers": []
            }

        system_message = {
            "role": "system",
            "content": (
                "You are an equity research sentiment analyst. Score one news article for the named stock only. "
                "Return strict JSON with score, verdict, reasoning, confidence, relevance, materiality, event_type, horizon, and key_drivers."
            )
        }

        user_message = {
            "role": "user",
            "content": f"""Analyze the following news article for {ticker}:

Title: {title}

Content: {article_text[:8000]}

Return JSON only:
{{
  "score": <number from -1.0 to 1.0>,
  "verdict": "BUY" | "SELL" | "HOLD",
  "reasoning": "<brief stock-specific rationale>",
  "confidence": <number from 0.0 to 1.0>,
  "relevance": <number from 0.0 to 1.0 measuring how directly this article concerns {ticker}>,
  "materiality": <number from 0.0 to 1.0 measuring expected market importance>,
  "event_type": "<earnings|guidance|product|legal|macro|analyst|market|other>",
  "horizon": "<intraday|days|weeks|months>",
  "key_drivers": ["<driver 1>", "<driver 2>"]
}}"""
        }

        payload = {
            "model": self.model,
            "messages": [system_message, user_message],
            "temperature": 0.3,
            "response_format": {"type": "json_object"},
            "max_tokens": 1000
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://finedge.com",
            "X-Title": "FinEdge"
        }

        max_retries = 2
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        self.api_url,
                        json=payload,
                        headers=headers
                    )

                    if response.status_code == 200:
                        result_data = response.json()
                        content = result_data.get("choices", [{}])[0].get("message", {}).get("content", "{}")

                        try:
                            result = self._normalise_response(json.loads(self._extract_json(content)))
                            logger.info(f"LLM analysis for {ticker}: {result.get('verdict')}")
                            return result
                        except json.JSONDecodeError:
                            logger.error(f"Failed to parse LLM response: {content}")
                            return self._fallback_response()

                    else:
                        logger.warning(f"LLM API returned status {response.status_code}: {response.text}")
                        await asyncio.sleep(2)

            except Exception as e:
                logger.warning(f"LLM analysis attempt {attempt + 1} failed: {str(e)}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)

        return self._fallback_response()

    def _extract_json(self, content: str) -> str:
        text = content.strip()
        if text.startswith("```"):
            text = text.strip("`").strip()
            if text.lower().startswith("json"):
                text = text[4:].strip()

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start:end + 1]
        return text

    def _normalise_response(self, result: Dict[str, Any]) -> Dict[str, Any]:
        score = self._clamp_float(result.get("score"), -1.0, 1.0, 0.0)
        confidence = self._clamp_float(result.get("confidence"), 0.0, 1.0, 0.0)
        relevance = self._clamp_float(result.get("relevance"), 0.0, 1.0, 0.5)
        materiality = self._clamp_float(result.get("materiality"), 0.0, 1.0, relevance)

        verdict = str(result.get("verdict") or "").upper()
        if verdict not in {"BUY", "SELL", "HOLD"}:
            if score > 0.2:
                verdict = "BUY"
            elif score < -0.2:
                verdict = "SELL"
            else:
                verdict = "HOLD"

        key_drivers = result.get("key_drivers")
        if not isinstance(key_drivers, list):
            key_drivers = []

        return {
            "score": score,
            "verdict": verdict,
            "reasoning": str(result.get("reasoning") or "No rationale returned."),
            "confidence": confidence,
            "relevance": relevance,
            "materiality": materiality,
            "event_type": str(result.get("event_type") or "other"),
            "horizon": str(result.get("horizon") or "days"),
            "key_drivers": [str(driver) for driver in key_drivers[:5]],
        }

    @staticmethod
    def _clamp_float(value: Any, minimum: float, maximum: float, default: float) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        return max(minimum, min(maximum, number))

    def _fallback_response(self) -> Dict[str, Any]:
        return {
            "score": 0.0,
            "verdict": "HOLD",
            "reasoning": "Analysis failed due to API limitations.",
            "confidence": 0.0,
            "relevance": 0.0,
            "materiality": 0.0,
            "event_type": "other",
            "horizon": "days",
            "key_drivers": []
        }

    async def analyze_news_batch(
        self,
        articles: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        results = []

        for article in articles:
            analysis = await self.analyze_news_article(
                ticker=article.get('ticker', ''),
                title=article.get('title', ''),
                body=article.get('body', '')
            )
            results.append({
                **article,
                'sentiment_score': analysis.get('score', 0.0),
                'verdict': analysis.get('verdict', 'HOLD'),
                'reasoning': analysis.get('reasoning', ''),
                'confidence': analysis.get('confidence', 0.0),
                'relevance': analysis.get('relevance', 0.0),
                'materiality': analysis.get('materiality', 0.0),
                'event_type': analysis.get('event_type', 'other'),
                'horizon': analysis.get('horizon', 'days'),
                'key_drivers': analysis.get('key_drivers', [])
            })

        return results
