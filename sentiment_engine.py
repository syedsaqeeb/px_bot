"""
PSX Trading Bot - Sentiment Engine
Scrapes news headlines from Pakistani financial sources and generates
structured prompts for ChatGPT/Claude to analyze sentiment.
"""

import re
from datetime import datetime
from typing import Optional
from loguru import logger

try:
    import requests
    from bs4 import BeautifulSoup
    SCRAPING_AVAILABLE = True
except ImportError:
    SCRAPING_AVAILABLE = False
    logger.warning("requests/bs4 not installed for scraping")

HTML_PARSER = "lxml"
try:
    import lxml  # noqa: F401
except ImportError:
    HTML_PARSER = "html.parser"

from config import settings


class SentimentEngine:
    """Scrape headlines and generate AI prompts for sentiment analysis."""

    _sentiment_scores: dict = {}

    NEWS_SOURCES = {
        "business_recorder": {"url": "https://www.brecorder.com/business-finance", "name": "Business Recorder"},
        "dawn_business": {"url": "https://www.dawn.com/business", "name": "Dawn Business"},
        "the_news_business": {"url": "https://www.thenews.com.pk/latest/category/business", "name": "The News International"},
        "geo_business": {"url": "https://www.geo.tv/category/business", "name": "Geo News Business"},
    }

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    }

    def scrape_headlines(self, max_per_source: int = 10) -> dict[str, list[str]]:
        """Scrape recent headlines from Pakistani financial news sources."""
        if not SCRAPING_AVAILABLE:
            return {"error": ["Scraping libraries not installed"]}
        all_headlines = {}
        for source_key, source_info in self.NEWS_SOURCES.items():
            try:
                resp = requests.get(source_info["url"], headers=self.HEADERS, timeout=15)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, HTML_PARSER)
                headlines = []
                for tag in soup.find_all(["h2", "h3", "h4", "a"]):
                    text = tag.get_text(strip=True)
                    if text and 20 < len(text) < 300:
                        text = re.sub(r"\s+", " ", text)
                        if text not in headlines:
                            headlines.append(text)
                    if len(headlines) >= max_per_source:
                        break
                all_headlines[source_info["name"]] = headlines
                logger.info(f"Scraped {len(headlines)} headlines from {source_info['name']}")
            except Exception as e:
                logger.warning(f"Failed to scrape {source_info['name']}: {e}")
                all_headlines[source_info["name"]] = [f"[Scraping failed: {e}]"]
        return all_headlines

    def scrape_headlines_for_stock(self, symbol: str, company_name: str = "") -> list[str]:
        """Scrape headlines specifically mentioning a stock symbol or company."""
        all_headlines = self.scrape_headlines()
        keywords = [symbol.lower()]
        if company_name:
            keywords.extend(company_name.lower().split())
        matching = []
        for source, headlines in all_headlines.items():
            for h in headlines:
                if any(kw in h.lower() for kw in keywords):
                    matching.append(f"[{source}] {h}")
        return matching

    @staticmethod
    def get_monetary_policy_context() -> str:
        """Return current SBP monetary policy summary for AI prompts."""
        return f"""
=== SBP MONETARY POLICY CONTEXT ===
Current Policy Rate: {settings.SBP_POLICY_RATE}%
Last MPC Decision Date: {settings.SBP_LAST_UPDATE}
CPI Inflation (March 2026): 7.3%
Core Inflation: 7.8%
GDP Growth (H1-FY26): 3.8%
Current Account: Surplus of $1.07 billion in March 2026
FX Reserves: ~$15.8 billion
IMF: Staff-level agreement reached March 27, 2026

Impact on Stocks:
- Banking sector: Higher rates -> wider net interest margins -> POSITIVE
- Real estate/construction: Higher rates -> costlier borrowing -> NEGATIVE
- Export-oriented: Depends on PKR stability
- Consumer discretionary: Higher rates -> reduced spending -> NEGATIVE
=======================================
"""

    def generate_sentiment_prompt(self, symbol: str = "", company_name: str = "", headlines: Optional[list[str]] = None) -> str:
        """Generate a structured prompt for ChatGPT/Claude for sentiment analysis."""
        if headlines is None:
            headlines = self.scrape_headlines_for_stock(symbol, company_name)
            if not headlines:
                all_h = self.scrape_headlines(max_per_source=5)
                headlines = []
                for source, hs in all_h.items():
                    for h in hs[:5]:
                        headlines.append(f"[{source}] {h}")
        headline_text = "\n".join(f"  {i+1}. {h}" for i, h in enumerate(headlines[:20]))
        prompt = f"""
======================================================
   PSX SENTIMENT ANALYSIS REQUEST
   Generated: {datetime.now().strftime('%Y-%m-%d %H:%M PKT')}
======================================================

STOCK: {symbol or 'GENERAL MARKET'}
COMPANY: {company_name or 'Pakistan Stock Exchange (PSX) Overall'}

{self.get_monetary_policy_context()}

=== RECENT NEWS HEADLINES ===
{headline_text}

=== YOUR TASK ===
Analyze the above headlines and monetary policy context. Provide:

1. OVERALL SENTIMENT SCORE: -100 (extremely bearish) to +100 (extremely bullish)
   Format: SENTIMENT_SCORE: [number]

2. KEY FACTORS:
   - Top 3 bullish factors
   - Top 3 bearish factors

3. SECTOR IMPACT: How does the current interest rate ({settings.SBP_POLICY_RATE}%) affect this stock/sector?

4. SHORT-TERM OUTLOOK (1-2 weeks): Bullish / Neutral / Bearish
5. MEDIUM-TERM OUTLOOK (1-3 months): Bullish / Neutral / Bearish

6. RISK EVENTS: Any upcoming events that could significantly move this stock?

Please be specific to the Pakistan market context.
"""
        return prompt.strip()

    def generate_market_sentiment_prompt(self) -> str:
        """Generate a prompt for overall PSX market sentiment analysis."""
        all_headlines = self.scrape_headlines(max_per_source=8)
        headline_text = ""
        for source, headlines in all_headlines.items():
            headline_text += f"\n--- {source} ---\n"
            for i, h in enumerate(headlines[:8]):
                headline_text += f"  {i+1}. {h}\n"
        prompt = f"""
======================================================
   PSX MARKET SENTIMENT ANALYSIS
   Generated: {datetime.now().strftime('%Y-%m-%d %H:%M PKT')}
======================================================

{self.get_monetary_policy_context()}

=== TODAY'S HEADLINES FROM PAKISTANI FINANCIAL MEDIA ===
{headline_text}

=== YOUR TASK ===
Analyze overall PSX sentiment. Provide:
1. MARKET_SENTIMENT: -100 to +100
2. SECTOR RANKINGS (most bullish to most bearish): Banking, Cement, Oil & Gas, Fertilizer, Technology, Power, Pharma, Textile
3. INTEREST RATE IMPACT: With SBP at {settings.SBP_POLICY_RATE}%, which sectors benefit/suffer?
4. TOP 3 STOCKS TO WATCH today
5. KEY RISKS for the coming week
"""
        return prompt.strip()

    def set_sentiment_score(self, symbol: str, score: float, outlook_short: str = "neutral", outlook_medium: str = "neutral", notes: str = "") -> dict:
        """After AI analysis, input the sentiment score here. Score: -100 to +100."""
        score = max(-100, min(100, score))
        self._sentiment_scores[symbol.upper()] = {
            "score": score, "normalized_score": (score + 100) / 2,
            "outlook_short": outlook_short, "outlook_medium": outlook_medium,
            "notes": notes, "timestamp": datetime.now().isoformat(),
        }
        logger.info(f"Sentiment score set for {symbol}: {score}")
        return self._sentiment_scores[symbol.upper()]

    def get_sentiment_score(self, symbol: str) -> dict:
        return self._sentiment_scores.get(symbol.upper(), {"score": 0, "normalized_score": 50, "outlook_short": "unknown", "timestamp": None})

    def get_all_sentiment_scores(self) -> dict:
        return self._sentiment_scores.copy()


# Singleton
sentiment_engine = SentimentEngine()
