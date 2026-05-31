"""
PSX Trading Bot - Value Engine
Analyzes company fundamentals: P/E, EPS, Book Value, P/B ratio.
Scores each company on a 0-100 value scale.
"""

from datetime import datetime
from typing import Optional
from loguru import logger
from data_engine import data_engine
from config import settings


class ValueEngine:
    """Fundamental / value analysis for PSX stocks."""

    _value_overrides: dict = {}

    SECTOR_BENCHMARKS = {
        "banking": {"pe_avg": 6.0, "pb_avg": 1.2, "div_yield_avg": 7.0},
        "cement": {"pe_avg": 10.0, "pb_avg": 1.8, "div_yield_avg": 4.0},
        "oil_gas": {"pe_avg": 7.0, "pb_avg": 1.5, "div_yield_avg": 6.0},
        "fertilizer": {"pe_avg": 8.0, "pb_avg": 3.0, "div_yield_avg": 8.0},
        "technology": {"pe_avg": 15.0, "pb_avg": 4.0, "div_yield_avg": 2.0},
        "power": {"pe_avg": 5.0, "pb_avg": 1.0, "div_yield_avg": 10.0},
        "pharma": {"pe_avg": 12.0, "pb_avg": 3.0, "div_yield_avg": 3.0},
        "default": {"pe_avg": 8.0, "pb_avg": 1.5, "div_yield_avg": 5.0},
    }

    TICKER_SECTOR_MAP = {
        "MEBL": "banking", "HBL": "banking", "UBL": "banking",
        "MCB": "banking", "BAFL": "banking", "NBP": "banking",
        "ABL": "banking", "BAHL": "banking",
        "LUCK": "cement", "DGKC": "cement", "MLCF": "cement",
        "FCCL": "cement", "PIOC": "cement", "CHCC": "cement",
        "OGDC": "oil_gas", "PPL": "oil_gas", "PSO": "oil_gas",
        "SNGP": "oil_gas", "MARI": "oil_gas", "POL": "oil_gas", "ATRL": "oil_gas",
        "FFC": "fertilizer", "EFERT": "fertilizer", "FFBL": "fertilizer",
        "SYS": "technology", "TRG": "technology", "AVN": "technology",
        "HUBC": "power", "KEL": "power", "KAPCO": "power", "NCPL": "power",
        "SEARL": "pharma", "GLAXO": "pharma", "AGP": "pharma",
    }

    def get_fundamentals(self, symbol: str) -> dict:
        fund = data_engine.get_fundamentals(symbol)
        result = {
            "symbol": symbol,
            "pe_ratio": self._safe_float(fund.get("pe_ratio") or fund.get("PE")),
            "eps": self._safe_float(fund.get("eps") or fund.get("EPS")),
            "book_value": self._safe_float(fund.get("book_value") or fund.get("BookValue")),
            "market_cap": self._safe_float(fund.get("market_cap") or fund.get("MarketCap")),
            "dividend_yield": self._safe_float(fund.get("dividend_yield") or fund.get("DivYield")),
            "sector": self.TICKER_SECTOR_MAP.get(symbol, "default"),
        }
        if result["book_value"] and result["book_value"] > 0:
            quote = data_engine.get_live_quote(symbol)
            cp = quote.get("close", 0)
            result["pb_ratio"] = round(cp / result["book_value"], 2) if cp > 0 else None
        else:
            result["pb_ratio"] = None
        return result

    @staticmethod
    def _safe_float(val) -> Optional[float]:
        if val is None: return None
        try: return float(val)
        except (ValueError, TypeError): return None

    def value_score(self, symbol: str) -> dict:
        """Score company value 0-100: P/E(30) + P/B(25) + EPS(20) + Div(15) + Sector(10)."""
        fund = self.get_fundamentals(symbol)
        sector = fund.get("sector", "default")
        bm = self.SECTOR_BENCHMARKS.get(sector, self.SECTOR_BENCHMARKS["default"])
        score, details = 0, {}

        pe = fund.get("pe_ratio")
        if pe and pe > 0:
            r = pe / bm["pe_avg"]
            pe_pts = 30 if r < 0.5 else 25 if r < 0.75 else 18 if r < 1.0 else 10 if r < 1.25 else 5 if r < 1.5 else 0
        else: pe_pts = 0
        score += pe_pts; details["pe_ratio"] = {"value": pe, "benchmark": bm["pe_avg"], "points": pe_pts, "max": 30}

        pb = fund.get("pb_ratio")
        if pb and pb > 0:
            pb_pts = 25 if pb < 0.8 else 20 if pb < 1.0 else 14 if pb < 1.5 else 8 if pb < 2.0 else 3 if pb < 3.0 else 0
        else: pb_pts = 0
        score += pb_pts; details["pb_ratio"] = {"value": pb, "points": pb_pts, "max": 25}

        eps = fund.get("eps")
        if eps is not None:
            eps_pts = 20 if eps > 50 else 16 if eps > 30 else 12 if eps > 15 else 8 if eps > 5 else 4 if eps > 0 else 0
        else: eps_pts = 0
        score += eps_pts; details["eps"] = {"value": eps, "points": eps_pts, "max": 20}

        dy = fund.get("dividend_yield")
        if dy and dy > 0:
            div_pts = 15 if dy > 10 else 12 if dy > 7 else 8 if dy > 5 else 4 if dy > 3 else 2
        else: div_pts = 0
        score += div_pts; details["dividend_yield"] = {"value": dy, "points": div_pts, "max": 15}

        rate = settings.SBP_POLICY_RATE
        sector_scores = {"banking": 10 if rate >= 10 else 6, "fertilizer": 7, "oil_gas": 6, "power": 5, "technology": 5, "pharma": 4, "cement": 3 if rate >= 10 else 6, "default": 5}
        s_pts = sector_scores.get(sector, 5)
        score += s_pts; details["sector"] = {"sector": sector, "rate": f"{rate}%", "points": s_pts, "max": 10}

        grade = "A+ (Excellent Value)" if score >= 80 else "A  (Good Value)" if score >= 65 else "B  (Fair Value)" if score >= 50 else "C  (Overvalued)" if score >= 35 else "D  (Expensive / No Data)"
        return {"symbol": symbol, "score": min(score, 100), "grade": grade, "fundamentals": fund, "details": details}

    def generate_value_prompt(self, symbol: str, company_name: str = "") -> str:
        fund = self.get_fundamentals(symbol)
        vs = self.value_score(symbol)
        prompt = f"""
======================================================
   COMPANY VALUE & QUALITY ANALYSIS REQUEST
   Generated: {datetime.now().strftime('%Y-%m-%d %H:%M PKT')}
======================================================

STOCK: {symbol}
COMPANY: {company_name or symbol}
SECTOR: {fund.get('sector', 'Unknown')}

=== FUNDAMENTAL DATA ===
  P/E Ratio:       {fund.get('pe_ratio', 'N/A')}
  P/B Ratio:       {fund.get('pb_ratio', 'N/A')}
  EPS:             Rs. {fund.get('eps', 'N/A')}
  Book Value:      Rs. {fund.get('book_value', 'N/A')}
  Dividend Yield:  {fund.get('dividend_yield', 'N/A')}%

=== BOT's VALUE SCORE ===
  Score: {vs['score']}/100
  Grade: {vs['grade']}

=== YOUR TASK ===
Analyze {company_name or symbol} on PSX:
1. COMPANY QUALITY SCORE: 0-100 (management, moat, growth)
2. IS IT A GOOD VALUE? Compare P/E to peers, EPS trend
3. SECTOR OUTLOOK in current SBP rate environment ({settings.SBP_POLICY_RATE}%)
4. RED FLAGS: Debt, governance, legal risks
5. FAIR VALUE ESTIMATE

Format: VALUE_SCORE: [0-100]
"""
        return prompt.strip()

    def set_value_override(self, symbol: str, score: float, notes: str = "") -> dict:
        score = max(0, min(100, score))
        self._value_overrides[symbol.upper()] = {"score": score, "notes": notes, "timestamp": datetime.now().isoformat()}
        logger.info(f"Value override set for {symbol}: {score}/100")
        return self._value_overrides[symbol.upper()]

    def get_effective_value_score(self, symbol: str) -> float:
        override = self._value_overrides.get(symbol.upper())
        if override: return override["score"]
        return self.value_score(symbol).get("score", 0)


# Singleton
value_engine = ValueEngine()
