"""
PSX Trading Bot - Mathematics Engine
Core quantitative analysis: Z-scores, mean reversion signals, RSI,
Bollinger Bands, support/resistance, range analysis, and dip scoring.

Your Meezan Bank (MEBL) trade was a textbook mean-reversion:
  Bought at 496 -> dropped to 452 (z-score went very negative) ->
  recovered to 490-492 (z-score reverted toward 0).
This engine automates that exact logic across all KSE-100 stocks.
"""

import pandas as pd
import numpy as np
from loguru import logger
from config import settings


class MathEngine:
    """All quantitative / technical analysis for PSX stocks."""

    @staticmethod
    def rolling_zscore(series: pd.Series, window: int = 20) -> pd.Series:
        """Rolling z-score: how many std devs the current price is from its rolling mean."""
        rolling_mean = series.rolling(window=window, min_periods=window).mean()
        rolling_std = series.rolling(window=window, min_periods=window).std()
        return (series - rolling_mean) / rolling_std.replace(0, np.nan)

    @staticmethod
    def weekly_range(df: pd.DataFrame, weeks: int = 1) -> dict:
        """Calculate the typical price range over the last N weeks."""
        if df.empty or len(df) < 5:
            return {"error": "Insufficient data"}
        days = weeks * 5
        recent = df.tail(days)
        high = recent["high"].max()
        low = recent["low"].min()
        price_range = high - low
        current = df["close"].iloc[-1]
        position_pct = ((current - low) / price_range * 100) if price_range > 0 else 50.0
        return {
            "period_weeks": weeks, "high": round(high, 2), "low": round(low, 2),
            "range": round(price_range, 2),
            "range_pct": round(price_range / low * 100, 2) if low > 0 else 0,
            "current_price": round(current, 2),
            "position_in_range_pct": round(position_pct, 2),
            "near_bottom": position_pct < 25, "near_top": position_pct > 75,
        }

    @staticmethod
    def multi_period_range(df: pd.DataFrame) -> dict:
        """Compute ranges for 1-week, 2-week, 1-month, 3-month periods."""
        return {
            "1_week": MathEngine.weekly_range(df, weeks=1),
            "2_weeks": MathEngine.weekly_range(df, weeks=2),
            "1_month": MathEngine.weekly_range(df, weeks=4),
            "3_months": MathEngine.weekly_range(df, weeks=13),
        }

    @staticmethod
    def rsi(series: pd.Series, period: int = 14) -> pd.Series:
        """RSI: 0-100 oscillator. < 30 = oversold, > 70 = overbought."""
        delta = series.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.rolling(window=period, min_periods=period).mean()
        avg_loss = loss.rolling(window=period, min_periods=period).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    @staticmethod
    def bollinger_bands(series: pd.Series, window: int = 20, num_std: float = 2.0) -> pd.DataFrame:
        """Bollinger Bands: middle (SMA), upper (+2 sigma), lower (-2 sigma)."""
        sma = series.rolling(window=window).mean()
        std = series.rolling(window=window).std()
        return pd.DataFrame({
            "bb_middle": sma, "bb_upper": sma + (num_std * std),
            "bb_lower": sma - (num_std * std),
            "bb_width": (num_std * 2 * std) / sma * 100,
        })

    @staticmethod
    def support_resistance(df: pd.DataFrame, window: int = 20) -> dict:
        """Detect support and resistance levels using rolling min/max."""
        if df.empty:
            return {"support_levels": [], "resistance_levels": []}
        close = df["close"]
        supports, resistances = [], []
        for w in [10, 20, 50]:
            if len(close) >= w:
                supports.append(round(close.rolling(w).min().iloc[-1], 2))
                resistances.append(round(close.rolling(w).max().iloc[-1], 2))
        supports = sorted(set(supports))
        resistances = sorted(set(resistances), reverse=True)
        return {
            "support_levels": supports, "resistance_levels": resistances,
            "nearest_support": supports[-1] if supports else None,
            "nearest_resistance": resistances[-1] if resistances else None,
        }

    @staticmethod
    def regime_filter(df: pd.DataFrame) -> dict:
        """Uptrend/Downtrend filter using 50 & 200 day SMAs."""
        if len(df) < 200:
            return {"regime": "INSUFFICIENT_DATA", "safe_for_mean_reversion": False}
        close = df["close"]
        sma_200 = close.rolling(200).mean().iloc[-1]
        current_price = close.iloc[-1]
        sma_50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else current_price
        if current_price > sma_200:
            regime = "UPTREND"
        elif current_price > sma_50:
            regime = "NEUTRAL"
        else:
            regime = "DOWNTREND"
        return {
            "regime": regime, "current_price": round(current_price, 2),
            "sma_50": round(sma_50, 2), "sma_200": round(sma_200, 2),
            "above_sma200": current_price > sma_200,
            "safe_for_mean_reversion": regime in ("UPTREND", "NEUTRAL"),
        }

    @staticmethod
    def volume_analysis(df: pd.DataFrame, window: int = 20) -> dict:
        """Analyze volume relative to its average."""
        if df.empty or "volume" not in df.columns:
            return {"error": "No volume data"}
        vol = df["volume"]
        avg_vol = vol.rolling(window).mean().iloc[-1]
        current_vol = vol.iloc[-1]
        vol_ratio = current_vol / avg_vol if avg_vol > 0 else 0
        return {
            "current_volume": int(current_vol),
            "avg_volume_20d": int(avg_vol) if not np.isnan(avg_vol) else 0,
            "volume_ratio": round(vol_ratio, 2),
            "high_volume": vol_ratio > 1.5, "low_volume": vol_ratio < 0.5,
        }

    def dip_score(self, df: pd.DataFrame) -> dict:
        """
        Score how good a 'buy the dip' opportunity is (0-100).
        Z-score (0-30) + RSI (0-20) + Range position (0-20) + Regime (0-15) + Volume (0-15)
        """
        if df.empty or len(df) < 50:
            return {"score": 0, "details": "Insufficient data (need 50+ days)"}
        score = 0
        details = {}
        close = df["close"]

        # Z-Score (0-30)
        z = self.rolling_zscore(close, window=20)
        current_z = float(z.iloc[-1]) if not z.isna().all() else 0
        z_pts = 30 if current_z <= -3.0 else 25 if current_z <= -2.0 else 18 if current_z <= -1.5 else 10 if current_z <= -1.0 else 5 if current_z <= -0.5 else 0
        score += z_pts
        details["zscore"] = {"value": round(current_z, 2), "points": z_pts, "max": 30}

        # RSI (0-20)
        rsi_s = self.rsi(close)
        current_rsi = float(rsi_s.iloc[-1]) if not rsi_s.isna().all() else 50
        rsi_pts = 20 if current_rsi <= 20 else 15 if current_rsi <= 30 else 8 if current_rsi <= 40 else 3 if current_rsi <= 45 else 0
        score += rsi_pts
        details["rsi"] = {"value": round(current_rsi, 2), "points": rsi_pts, "max": 20}

        # Range Position (0-20)
        rng = self.weekly_range(df, weeks=2)
        pos = rng.get("position_in_range_pct")
        if pos is not None:
            range_pts = 20 if pos <= 10 else 16 if pos <= 20 else 10 if pos <= 30 else 5 if pos <= 40 else 0
        else:
            range_pts = 0
        score += range_pts
        details["range_position"] = {"value": pos, "points": range_pts, "max": 20}

        # Regime (0-15)
        regime_info = self.regime_filter(df)
        regime_pts = 15 if regime_info["regime"] == "UPTREND" else 8 if regime_info["regime"] == "NEUTRAL" else 0
        score += regime_pts
        details["regime"] = {"value": regime_info["regime"], "points": regime_pts, "max": 15}

        # Volume at Lows (0-15)
        vol_info = self.volume_analysis(df)
        vol_ratio = vol_info.get("volume_ratio", 1)
        is_dipping = current_z < -1.0
        vol_pts = 15 if is_dipping and vol_ratio > 2.0 else 10 if is_dipping and vol_ratio > 1.5 else 5 if is_dipping and vol_ratio > 1.0 else 0
        score += vol_pts
        details["volume"] = {"ratio": vol_ratio, "points": vol_pts, "max": 15}

        return {
            "score": min(score, 100),
            "grade": self._score_to_grade(score),
            "details": details,
            "zscore": round(current_z, 2),
            "rsi": round(current_rsi, 2),
            "regime": regime_info["regime"],
        }

    @staticmethod
    def _score_to_grade(score: int) -> str:
        if score >= 80: return "A+ (Strong Buy Dip)"
        elif score >= 65: return "A  (Buy Dip)"
        elif score >= 50: return "B  (Moderate Opportunity)"
        elif score >= 35: return "C  (Weak Signal)"
        else: return "D  (No Signal)"

    def generate_signals(self, df: pd.DataFrame, symbol: str = "") -> dict:
        """
        Generate a richer signal ladder based on mean-reversion and regime.
        """
        if df.empty or len(df) < 30:
            return {"signal": "INSUFFICIENT_DATA", "symbol": symbol}
        close = df["close"]
        current_price = float(close.iloc[-1])
        z = self.rolling_zscore(close, window=20)
        current_z = float(z.iloc[-1]) if not z.isna().all() else 0.0
        regime = self.regime_filter(df)
        dip = self.dip_score(df)
        bb = self.bollinger_bands(close)
        sr = self.support_resistance(df)
        target_price = float(close.rolling(20).mean().iloc[-1])
        stop_loss_price = target_price - 3.5 * float(close.rolling(20).std().iloc[-1])
        rsi_series = self.rsi(close)
        rsi_val = float(rsi_series.iloc[-1]) if not rsi_series.isna().all() else 0.0
        safe_regime = regime.get("safe_for_mean_reversion", False)

        if current_z <= settings.STOP_Z:
            signal, action = "STOP_LOSS", "EXIT immediately - price in freefall beyond -3.5 sigma"
        elif current_z <= settings.ENTRY_Z and safe_regime:
            signal, action = "BUY", f"Mean-reversion BUY - price is {abs(current_z):.1f} sigma below mean in {regime['regime']}"
        elif current_z <= settings.ENTRY_Z:
            signal, action = "WATCH", f"Dip detected ({current_z:.1f} sigma) but regime is {regime['regime']} - risky"
        elif current_z <= -1.0 and safe_regime and rsi_val <= 40:
            signal, action = "ACCUMULATE", f"Build position on controlled pullback ({current_z:.1f} sigma, RSI {rsi_val:.0f})"
        elif current_z <= -1.0:
            signal, action = "WATCH", f"Early dip forming ({current_z:.1f} sigma) but confirmation is incomplete"
        elif current_z >= 1.5 or (current_z >= 0.75 and rsi_val >= 65):
            signal, action = "TAKE_PROFIT", "Lock gains into strength - price is stretched above fair value"
        elif current_z >= settings.EXIT_Z and current_z <= 0.75:
            signal, action = "SELL", "Price has reverted to fair value - reduce tactical position"
        elif current_z > 0.75:
            signal, action = "OVERBOUGHT", "Price above mean - avoid fresh entry, wait for pullback"
        else:
            signal, action = "HOLD", "No strong signal - wait for better entry"

        expected_return = ((target_price - current_price) / current_price * 100) if current_price > 0 else 0
        bb_l = bb["bb_lower"].iloc[-1]; bb_u = bb["bb_upper"].iloc[-1]
        return {
            "symbol": symbol, "signal": signal, "action": action,
            "current_price": round(current_price, 2), "target_price": round(target_price, 2),
            "stop_loss": round(max(stop_loss_price, 0), 2),
            "expected_return_pct": round(expected_return, 2),
            "zscore": round(current_z, 2), "rsi": round(rsi_val, 2),
            "regime": regime["regime"], "dip_score": dip["score"],
            "bb_lower": round(float(bb_l), 2) if not np.isnan(bb_l) else None,
            "bb_upper": round(float(bb_u), 2) if not np.isnan(bb_u) else None,
            "support": sr.get("nearest_support"), "resistance": sr.get("nearest_resistance"),
        }

    def full_analysis(self, df: pd.DataFrame, symbol: str = "") -> dict:
        """Run all technical analysis on a stock."""
        return {
            "symbol": symbol, "signal": self.generate_signals(df, symbol),
            "dip_score": self.dip_score(df), "ranges": self.multi_period_range(df),
            "regime": self.regime_filter(df), "support_resistance": self.support_resistance(df),
            "volume": self.volume_analysis(df),
        }


# Singleton
math_engine = MathEngine()
