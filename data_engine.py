"""
PSX Trading Bot - Data Engine
Handles all data collection from PSX via psxdata library and yfinance fallback.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional
from loguru import logger
import requests
from bs4 import BeautifulSoup

try:
    import psxdata
    PSXDATA_AVAILABLE = True
except ImportError:
    PSXDATA_AVAILABLE = False
    logger.warning("psxdata not installed. Install with: pip install psxdata")

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    logger.warning("yfinance not installed. Install with: pip install yfinance")

from config import settings


class DataEngine:
    """Collect and manage PSX stock data."""

    KSE100_DPS_URL = "https://dps.psx.com.pk/indices/KSE100"

    def __init__(self):
        self._kse100_cache: Optional[list] = None
        self._data_cache: dict = {}
        self._fallback_tickers = [
            "MEBL", "HBL", "UBL", "MCB", "BAFL", "NBP", "ABL", "BAHL",
            "ENGRO", "LUCK", "DGKC", "MLCF", "FCCL", "PIOC", "CHCC",
            "OGDC", "PPL", "PSO", "SNGP", "MARI", "POL", "ATRL",
            "HUBC", "KEL", "KAPCO", "NCPL",
            "FFC", "EFERT", "FFBL",
            "SYS", "TRG", "AVN",
            "NESTLE", "COLG", "UNITY",
            "MTL", "ISL", "AICL", "PAKT", "ILP",
            "SEARL", "GLAXO", "AGP",
            "MUGHAL", "ASTL",
        ]
        self._universe_source = "kse100"
        logger.info("DataEngine initialized")

    def _normalize_symbol(self, symbol: str) -> str:
        """Clean index constituent symbols scraped from PSX pages."""
        return symbol.strip().upper().split()[0]

    def _fallback_kse100_tickers(self) -> list[str]:
        """Return the bundled fallback ticker list."""
        return list(self._fallback_tickers)

    def _fetch_kse100_tickers_via_dps(self) -> list[str]:
        """Scrape current KSE-100 constituents from PSX DPS when psxdata is unavailable."""
        response = requests.get(self.KSE100_DPS_URL, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        symbols = []
        for row in soup.select("table tbody tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            symbol = self._normalize_symbol(cells[0].get_text(" ", strip=True))
            company_name = cells[1].get_text(" ", strip=True)
            if symbol and company_name:
                symbols.append(symbol)

        deduped = list(dict.fromkeys(symbols))
        if len(deduped) >= 90:
            logger.info(f"Loaded {len(deduped)} KSE-100 tickers via DPS scrape")
            return deduped
        raise ValueError("Could not parse KSE-100 constituents from DPS page")

    def set_universe_source(self, source: str) -> dict:
        """Switch the active ranking universe source."""
        normalized = source.strip().lower()
        if normalized not in {"kse100", "fallback"}:
            raise ValueError("Universe source must be 'kse100' or 'fallback'")

        self._universe_source = normalized
        self._kse100_cache = None
        return self.get_universe_status()

    def get_universe_status(self) -> dict:
        """Describe the currently selected ticker universe."""
        tickers = self.get_kse100_tickers()
        using_live_data = self._universe_source == "kse100" and len(tickers) > len(self._fallback_tickers)
        return {
            "selected_source": self._universe_source,
            "resolved_source": "kse100" if using_live_data else "fallback",
            "display_name": "KSE-100" if using_live_data else "Hardcoded",
            "total_tickers": len(tickers),
            "psxdata_available": PSXDATA_AVAILABLE,
            "sources": [
                {"value": "kse100", "label": "KSE-100"},
                {"value": "fallback", "label": "Hardcoded"},
            ],
        }

    def get_kse100_tickers(self) -> list[str]:
        """Return list of KSE-100 constituent tickers."""
        if self._kse100_cache:
            return self._kse100_cache

        if self._universe_source == "fallback":
            fallback = self._fallback_kse100_tickers()
            self._kse100_cache = fallback
            logger.info(f"Using fallback ticker list ({len(fallback)} stocks)")
            return fallback

        if PSXDATA_AVAILABLE:
            try:
                kse100_df = psxdata.indices("KSE100")
                tickers = [self._normalize_symbol(symbol) for symbol in kse100_df["symbol"].tolist()]
                self._kse100_cache = tickers
                logger.info(f"Loaded {len(tickers)} KSE-100 tickers via psxdata")
                return tickers
            except Exception as e:
                logger.error(f"psxdata indices() failed: {e}")

        try:
            tickers = self._fetch_kse100_tickers_via_dps()
            self._kse100_cache = tickers
            return tickers
        except Exception as e:
            logger.error(f"DPS KSE-100 fetch failed: {e}")

        fallback = self._fallback_kse100_tickers()
        self._kse100_cache = fallback
        logger.info(f"Falling back to bundled ticker list ({len(fallback)} stocks)")
        return fallback

    def get_all_tickers(self) -> list[str]:
        """Return all listed tickers on PSX."""
        if PSXDATA_AVAILABLE:
            try:
                return psxdata.tickers()
            except Exception as e:
                logger.error(f"psxdata tickers() failed: {e}")
        return self.get_kse100_tickers()

    def clear_cache(self, symbol: Optional[str] = None):
        """Clear cached historical data for one symbol or the full cache."""
        if symbol is None:
            self._data_cache.clear()
            return

        symbol_prefix = f"{symbol.upper()}_"
        keys = [key for key in self._data_cache if key.startswith(symbol_prefix)]
        for key in keys:
            self._data_cache.pop(key, None)

    def get_historical(self, symbol: str, start: Optional[str] = None, end: Optional[str] = None, force_refresh: bool = False) -> pd.DataFrame:
        """Fetch historical OHLCV data for a symbol."""
        if start is None:
            start = (datetime.now() - timedelta(days=365 * settings.HISTORY_YEARS)).strftime("%Y-%m-%d")
        if end is None:
            end = datetime.now().strftime("%Y-%m-%d")

        cache_key = f"{symbol}_{start}_{end}"
        if force_refresh:
            self._data_cache.pop(cache_key, None)
        if cache_key in self._data_cache:
            return self._data_cache[cache_key]

        df = pd.DataFrame()

        if PSXDATA_AVAILABLE:
            try:
                df = psxdata.stocks(symbol, start=start, end=end)
                if not df.empty:
                    logger.info(f"[psxdata] {symbol}: {len(df)} rows fetched")
            except Exception as e:
                logger.warning(f"[psxdata] {symbol} failed: {e}")

        if df.empty and YFINANCE_AVAILABLE:
            try:
                yf_symbol = f"{symbol}.KA"
                ticker = yf.Ticker(yf_symbol)
                df = ticker.history(start=start, end=end)
                if not df.empty:
                    df = df.reset_index()
                    df.columns = [c.lower() for c in df.columns]
                    logger.info(f"[yfinance] {symbol}: {len(df)} rows fetched")
            except Exception as e:
                logger.warning(f"[yfinance] {symbol} failed: {e}")

        if not df.empty:
            df.columns = [c.lower().strip() for c in df.columns]
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
                df = df.sort_values("date").reset_index(drop=True)
            self._data_cache[cache_key] = df

        return df

    def get_live_quote(self, symbol: str) -> dict:
        """Get real-time quote for a symbol."""
        if PSXDATA_AVAILABLE:
            try:
                quote = psxdata.quote(symbol)
                if isinstance(quote, pd.DataFrame) and not quote.empty:
                    return quote.iloc[0].to_dict()
                elif isinstance(quote, dict):
                    return quote
            except Exception as e:
                logger.warning(f"Live quote failed for {symbol}: {e}")

        df = self.get_historical(symbol)
        if not df.empty:
            last = df.iloc[-1]
            return {
                "symbol": symbol,
                "close": last.get("close", 0),
                "open": last.get("open", 0),
                "high": last.get("high", 0),
                "low": last.get("low", 0),
                "volume": last.get("volume", 0),
                "source": "historical_last_row",
            }
        return {"symbol": symbol, "error": "No data available"}

    def get_fundamentals(self, symbol: str) -> dict:
        """Get fundamental data (P/E, EPS, book value, etc.)."""
        if PSXDATA_AVAILABLE:
            try:
                fund = psxdata.fundamentals(symbol)
                if isinstance(fund, pd.DataFrame) and not fund.empty:
                    return fund.iloc[-1].to_dict()
                elif isinstance(fund, dict):
                    return fund
            except Exception as e:
                logger.warning(f"Fundamentals failed for {symbol}: {e}")
        return {"symbol": symbol, "pe_ratio": None, "eps": None, "book_value": None}

    def get_sectors(self) -> pd.DataFrame:
        """Get sector aggregates."""
        if PSXDATA_AVAILABLE:
            try:
                return psxdata.sectors()
            except Exception as e:
                logger.warning(f"Sectors fetch failed: {e}")
        return pd.DataFrame()

    def fetch_all_kse100_data(self, force_refresh: bool = False) -> dict[str, pd.DataFrame]:
        """Fetch historical data for all KSE-100 stocks."""
        tickers = self.get_kse100_tickers()
        results = {}
        for i, symbol in enumerate(tickers):
            try:
                df = self.get_historical(symbol, force_refresh=force_refresh)
                if not df.empty:
                    results[symbol] = df
                    logger.info(f"[{i+1}/{len(tickers)}] {symbol}: OK ({len(df)} rows)")
                else:
                    logger.warning(f"[{i+1}/{len(tickers)}] {symbol}: No data")
            except Exception as e:
                logger.error(f"[{i+1}/{len(tickers)}] {symbol}: Error - {e}")
        return results


# Singleton
data_engine = DataEngine()
