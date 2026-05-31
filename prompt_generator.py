"""
PSX Trading Bot - Prompt Generator
Creates structured, copy-paste-ready prompts for ChatGPT / Claude.
"""

from datetime import datetime
from config import settings
from data_engine import data_engine
from math_engine import math_engine
from sentiment_engine import sentiment_engine
from value_engine import value_engine


class PromptGenerator:
    """Generate all types of AI prompts."""

    def daily_analysis_prompt(self, top_n: int = 10) -> str:
        tickers = data_engine.get_kse100_tickers()[:top_n]
        summaries = []
        for symbol in tickers:
            df = data_engine.get_historical(symbol)
            if df.empty or len(df) < 30: continue
            sig = math_engine.generate_signals(df, symbol)
            rng = math_engine.weekly_range(df, weeks=2)
            regime = math_engine.regime_filter(df)
            summaries.append(
                f"  {symbol:>8} | Price: {sig.get('current_price',0):>8.1f} | "
                f"Z: {sig.get('zscore',0):>6.2f} | RSI: {sig.get('rsi',0):>5.1f} | "
                f"Signal: {sig.get('signal','N/A'):<12} | "
                f"2W Range: {rng.get('low',0):.0f}-{rng.get('high',0):.0f} | "
                f"Regime: {regime.get('regime','N/A')}"
            )
        stocks_text = "\n".join(summaries)
        monetary = sentiment_engine.get_monetary_policy_context()
        prompt = f"""
======================================================================
                    PSX DAILY ANALYSIS REQUEST
                    {datetime.now().strftime('%Y-%m-%d %H:%M PKT')}
======================================================================

{monetary}

=== TOP {top_n} KSE-100 STOCKS - TECHNICAL SNAPSHOT ===
{stocks_text}

=== YOUR TASK ===
You are a senior Pakistan stock market analyst. Provide:
1. MARKET OUTLOOK: Overall PSX direction + key macro drivers
2. TOP 3 BUY RECOMMENDATIONS: Entry, Target, Stop Loss, Holding Period, Risk Level, Reasoning
3. STOCKS TO AVOID / SELL: Which look risky and why
4. SECTOR ROTATION: With SBP at {settings.SBP_POLICY_RATE}%, which sectors to favor?
5. KEY RISK EVENTS THIS WEEK

Format: RECOMMENDATION: [SYMBOL] | Action: BUY | Entry: [price] | Target: [price] | Stop: [price] | Confidence: [1-10]
"""
        return prompt.strip()

    def trade_validation_prompt(self, symbol: str) -> str:
        df = data_engine.get_historical(symbol)
        if df.empty: return f"No data available for {symbol}"
        sig = math_engine.generate_signals(df, symbol)
        dip = math_engine.dip_score(df)
        rng = math_engine.multi_period_range(df)
        regime = math_engine.regime_filter(df)
        sr = math_engine.support_resistance(df)
        vol = math_engine.volume_analysis(df)
        val = value_engine.value_score(symbol)
        prompt = f"""
======================================================
   TRADE VALIDATION REQUEST - {symbol}
   {datetime.now().strftime('%Y-%m-%d %H:%M PKT')}
======================================================

BOT SIGNAL: {sig.get('signal','')} -- {sig.get('action','')}

=== TECHNICAL DATA ===
  Price: Rs. {sig.get('current_price',0)} | Z-Score: {sig.get('zscore',0)} | RSI: {sig.get('rsi',0)}
  Target: Rs. {sig.get('target_price',0)} | Stop Loss: Rs. {sig.get('stop_loss',0)}

=== PRICE RANGES ===
  1W: {rng.get('1_week',{}).get('low','?')}-{rng.get('1_week',{}).get('high','?')}
  2W: {rng.get('2_weeks',{}).get('low','?')}-{rng.get('2_weeks',{}).get('high','?')}
  1M: {rng.get('1_month',{}).get('low','?')}-{rng.get('1_month',{}).get('high','?')}
  3M: {rng.get('3_months',{}).get('low','?')}-{rng.get('3_months',{}).get('high','?')}

=== TREND ===
  Regime: {regime.get('regime','')} | SMA50: {regime.get('sma_50','')} | SMA200: {regime.get('sma_200','')}
  Support: {sr.get('support_levels',[])} | Resistance: {sr.get('resistance_levels',[])}

=== VOLUME ===
  Current: {vol.get('current_volume','')} | Avg20d: {vol.get('avg_volume_20d','')} | Ratio: {vol.get('volume_ratio','')}x

=== BOT SCORES ===
  Dip: {dip.get('score',0)}/100 ({dip.get('grade','')})
  Value: {val.get('score',0)}/100 ({val.get('grade','')})

=== YOUR TASK ===
1. VALIDATE OR REJECT this entry (YES/NO, confidence 1-10)
2. BETTER ENTRY price?
3. TARGET realistic?
4. POSITION SIZE (% of portfolio)?
5. TIMING: Buy now or wait?
6. RISK FACTORS?

Format: TRADE_DECISION: [BUY/WAIT/SKIP] | Confidence: [1-10] | Entry: [price] | Target: [price]
"""
        return prompt.strip()

    def sentiment_prompt(self, symbol: str = "", company_name: str = "") -> str:
        return sentiment_engine.generate_sentiment_prompt(symbol, company_name)

    def market_sentiment_prompt(self) -> str:
        return sentiment_engine.generate_market_sentiment_prompt()

    def value_prompt(self, symbol: str, company_name: str = "") -> str:
        return value_engine.generate_value_prompt(symbol, company_name)


# Singleton
prompt_generator = PromptGenerator()
