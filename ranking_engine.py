"""
PSX Trading Bot - Ranking Engine
Combines Math (50%) + Sentiment (25%) + Value (25%) into a composite score.
Ranks all KSE-100 stocks with entry/target/stop-loss.
"""

import pandas as pd
from datetime import datetime
from loguru import logger
from typing import Optional
from config import settings
from data_engine import data_engine
from math_engine import math_engine
from sentiment_engine import sentiment_engine
from value_engine import value_engine


class RankingEngine:
    """Combine all scores and rank KSE-100 stocks."""

    def __init__(self):
        self._last_ranking: Optional[pd.DataFrame] = None
        self._last_ranking_time: Optional[str] = None

    def score_stock(self, symbol: str) -> dict:
        """Calculate composite score for a single stock."""
        df = data_engine.get_historical(symbol)
        if df.empty or len(df) < 30:
            return {"symbol": symbol, "composite_score": 0, "signal": "INSUFFICIENT_DATA", "error": "Not enough data"}

        dip = math_engine.dip_score(df)
        math_score = dip.get("score", 0)
        sent = sentiment_engine.get_sentiment_score(symbol)
        sentiment_score = sent.get("normalized_score", 50)
        val_score = value_engine.get_effective_value_score(symbol)
        composite = math_score * settings.MATH_WEIGHT + sentiment_score * settings.SENTIMENT_WEIGHT + val_score * settings.VALUE_WEIGHT
        signal = math_engine.generate_signals(df, symbol)

        return {
            "symbol": symbol, "composite_score": round(composite, 1),
            "math_score": math_score, "sentiment_score": round(sentiment_score, 1), "value_score": val_score,
            "signal": signal.get("signal", "UNKNOWN"), "action": signal.get("action", ""),
            "current_price": signal.get("current_price", 0), "target_price": signal.get("target_price", 0),
            "stop_loss": signal.get("stop_loss", 0), "expected_return_pct": signal.get("expected_return_pct", 0),
            "zscore": signal.get("zscore", 0), "rsi": signal.get("rsi", 0),
            "regime": signal.get("regime", ""), "dip_grade": dip.get("grade", ""),
        }

    def rank_all(self, tickers: Optional[list[str]] = None) -> pd.DataFrame:
        """Score and rank all stocks."""
        if tickers is None:
            tickers = data_engine.get_kse100_tickers()
        results = []
        for i, symbol in enumerate(tickers):
            try:
                score_data = self.score_stock(symbol)
                results.append(score_data)
                logger.info(f"[{i+1}/{len(tickers)}] {symbol}: Composite={score_data['composite_score']}, Signal={score_data['signal']}")
            except Exception as e:
                logger.error(f"[{i+1}/{len(tickers)}] {symbol}: Error - {e}")
                results.append({"symbol": symbol, "composite_score": 0, "signal": "ERROR"})

        df = pd.DataFrame(results)
        if not df.empty:
            df = df.sort_values("composite_score", ascending=False).reset_index(drop=True)
            df.insert(0, "rank", range(1, len(df) + 1))
            if "current_price" in df.columns and "stop_loss" in df.columns:
                df["entry_zone_low"] = df.apply(lambda r: round((r["current_price"] + r["stop_loss"]) / 2, 2) if r["current_price"] > 0 else 0, axis=1)
                df["entry_zone_high"] = df["current_price"]

        self._last_ranking = df
        self._last_ranking_time = datetime.now().isoformat()
        logger.info(f"Ranking complete: {len(df)} stocks at {self._last_ranking_time}")
        return df

    def get_top_buys(self, n: int = 10) -> pd.DataFrame:
        df = self._last_ranking
        if df is None or df.empty: df = self.rank_all()
        return df[df["signal"].isin(["BUY", "ACCUMULATE", "WATCH"])].head(n)

    def get_sell_signals(self) -> pd.DataFrame:
        df = self._last_ranking
        if df is None or df.empty: df = self.rank_all()
        return df[df["signal"].isin(["SELL", "TAKE_PROFIT", "OVERBOUGHT", "STOP_LOSS"])]

    def generate_summary(self) -> str:
        df = self._last_ranking
        if df is None or df.empty: df = self.rank_all()
        report = []
        report.append("=" * 70)
        report.append(f"  PSX TRADING BOT - STOCK RANKINGS")
        report.append(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M PKT')}")
        report.append(f"  SBP Policy Rate: {settings.SBP_POLICY_RATE}%")
        report.append("=" * 70)
        buys = df[df["signal"].isin(["BUY", "ACCUMULATE", "WATCH"])].head(10)
        if not buys.empty:
            report.append("\nTOP BUY OPPORTUNITIES:")
            report.append("-" * 70)
            report.append(f"{'#':>3} {'Symbol':<8} {'Signal':<12} {'Price':>8} {'Target':>8} {'Stop':>8} {'Ret%':>7} {'Score':>6}")
            report.append("-" * 70)
            for _, row in buys.iterrows():
                report.append(f"{row.get('rank',''):>3} {row['symbol']:<8} {row['signal']:<12} {row.get('current_price',0):>8.1f} {row.get('target_price',0):>8.1f} {row.get('stop_loss',0):>8.1f} {row.get('expected_return_pct',0):>6.1f}% {row['composite_score']:>6.1f}")
        sells = df[df["signal"].isin(["SELL", "TAKE_PROFIT", "OVERBOUGHT"])]
        if not sells.empty:
            report.append("\nSELL / TAKE PROFIT SIGNALS:")
            report.append("-" * 70)
            for _, row in sells.iterrows():
                report.append(f"  {row['symbol']:<8} {row['signal']:<12} Price: {row.get('current_price',0):.1f}  Z: {row.get('zscore',0):.2f}")
        report.append("\n" + "=" * 70)
        report.append(
            f"  Total: {len(df)} | BUY: {len(df[df['signal']=='BUY'])} | ACCUMULATE: {len(df[df['signal']=='ACCUMULATE'])} | WATCH: {len(df[df['signal']=='WATCH'])} | TAKE_PROFIT: {len(df[df['signal']=='TAKE_PROFIT'])} | SELL: {len(df[df['signal']=='SELL'])}"
        )
        report.append("=" * 70)
        return "\n".join(report)

    def get_last_ranking(self) -> Optional[pd.DataFrame]:
        return self._last_ranking


# Singleton
ranking_engine = RankingEngine()
