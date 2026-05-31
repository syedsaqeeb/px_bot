# PSX Trading Bot 📈

A semi-automated Pakistan Stock Exchange (PSX) trading bot that combines **quantitative analysis**, **AI-assisted sentiment analysis**, and **fundamental valuation** to rank KSE-100 stocks by profit probability.

Built for traders who have **ChatGPT Plus / Claude Plus** subscriptions but no dedicated AI APIs.

**All signals are served live via a secured web dashboard** — no Telegram or email needed.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    AUTOMATED (Python)                         │
│                                                              │
│  ┌────────────┐   ┌──────────────┐   ┌───────────────────┐  │
│  │ Data Engine │──▶│ Math Engine  │──▶│ Ranking Engine    │  │
│  │ (psxdata/  │   │ (Z-score,RSI │   │ (Composite Score) │  │
│  │  yfinance) │   │  Bollinger,  │   │                   │  │
│  │            │   │  Range,      │   │  Math:   50%      │  │
│  └────────────┘   │  Regime)     │   │  Sent:   25%      │  │
│                    └──────────────┘   │  Value:  25%      │  │
│  ┌────────────┐                      │                   │  │
│  │ Sentiment  │─ scrapes headlines ─▶│                   │  │
│  │ Engine     │                      └────────┬──────────┘  │
│  └────────────┘                               │             │
│  ┌────────────┐                      ┌────────▼──────────┐  │
│  │ Value      │─ fundamentals ──────▶│ Prompt Generator  │  │
│  │ Engine     │                      │ (for ChatGPT/     │  │
│  └────────────┘                      │  Claude)          │  │
│                                      └────────┬──────────┘  │
│  ┌────────────┐                               │             │
│  │ Scheduler  │  (auto-refreshes rankings)    │             │
│  │ (APSched)  │                               │             │
│  └────────────┘                               │             │
│  ┌────────────────────────────────────────────▼───────────┐  │
│  │ FastAPI Web Dashboard (JWT Auth)                       │  │
│  │  /dashboard  /signals  /prompts  /sentiment-input      │  │
│  │  ★ LIVE — all signals shown here, auto-refreshes ★     │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
                           │
                   ┌───────▼───────┐
                   │  YOU (Human)  │
                   │  Copy prompt  │
                   │  → Paste into │
                   │    Claude /   │
                   │    ChatGPT    │
                   │  → Input AI   │
                   │    scores back│
                   └───────┬───────┘
                           │
                   ┌───────▼───────┐
                   │ Execute Trade │
                   │ via broker    │
                   │ (manual)      │
                   └───────────────┘
```

---

## The Three Pillars

### 1. 📐 Mathematics (50% weight)
- **Z-Score Analysis**: Measures how far a stock price is from its 20-day mean
  - Z ≤ -2.0 → BUY signal (like MEBL dropping from 496 to 452)
  - Z ≈ 0.0  → SELL signal (like MEBL recovering to 490-492)
  - Z ≤ -3.5 → STOP LOSS (something is seriously wrong)
- **RSI**: Relative Strength Index (oversold < 30, overbought > 70)
- **Bollinger Bands**: Volatility-based price channels
- **Weekly/Bi-weekly Range**: Find the stock's range and buy at the dip
- **Regime Filter**: 200-day SMA to avoid buying in downtrends
- **Volume Analysis**: High volume at lows = potential capitulation (good buy)

### 2. 📰 Sentiment (25% weight)
- Auto-scrapes headlines from Dawn, Business Recorder, The News, Geo
- Generates structured prompts for ChatGPT/Claude
- Includes SBP monetary policy context (current rate: 11.5%)
- You paste the prompt, get AI analysis, and input the score back via dashboard

### 3. 💎 Value (25% weight)
- P/E ratio vs sector benchmarks
- P/B ratio (Price-to-Book)
- EPS (Earnings Per Share)
- Dividend yield
- Sector favorability in current rate environment

---

## MEBL Example (Your Real Trade)

```
Your trade:  Bought at 496 → Dropped to 452 → Recovered to 490-492
Bot's logic: Z-score went from 0 → -2.5 (BUY signal) → back to ~0 (SELL signal)

If the bot was running:
  1. At 496: Z ≈ 0 → HOLD (price at mean)
  2. At 475: Z ≈ -1.0 → WATCH (dipping)
  3. At 452: Z ≈ -2.5 → BUY SIGNAL on dashboard (2.5σ below mean!)
     Entry: 452, Target: 490, Stop: 435
  4. At 490: Z ≈ 0 → SELL SIGNAL on dashboard (reverted to mean)
     Profit: +8.4%
```

---

## Quick Start

### Option A: Direct (Development)
```bash
cd psx_trading_bot

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
nano .env  # Set your username and password

python app.py
# Visit http://localhost:8000
```

### Option B: Docker
```bash
cp .env.example .env
nano .env
docker-compose up -d
# Visit http://localhost
```

### Option C: Production Linux Server
```bash
chmod +x deploy.sh
sudo ./deploy.sh
# Follow the post-deployment instructions
```

---

## API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/` | No | Login page |
| POST | `/login` | No | Get JWT token |
| GET | `/dashboard` | Token | Live web dashboard |
| GET | `/api/rankings` | Token | All stock rankings |
| GET | `/api/stock/{symbol}` | Token | Detailed stock analysis |
| GET | `/api/signals` | Token | Buy/Sell signals |
| GET | `/api/prompts/daily` | Token | Daily analysis prompt |
| GET | `/api/prompts/market_sentiment` | Token | Market sentiment prompt |
| GET | `/api/prompts/sentiment/{symbol}` | Token | Stock sentiment prompt |
| GET | `/api/prompts/validate/{symbol}` | Token | Trade validation prompt |
| GET | `/api/prompts/value/{symbol}` | Token | Company value prompt |
| POST | `/api/sentiment` | Token | Input sentiment score |
| POST | `/api/value-override` | Token | Input value score |
| GET | `/api/scheduler/status` | Token | Scheduler status |
| POST | `/api/scheduler/start` | Token | Start scheduler |
| POST | `/api/scheduler/stop` | Token | Stop scheduler |

---

## Daily Workflow

1. **9:25 AM** — Bot auto-fetches latest data for all KSE-100 stocks
2. **9:30 AM** — Bot runs full analysis, updates live dashboard
3. **You** — Open dashboard, check rankings & signals
4. **AI Prompts tab** — Click "Daily Analysis" → Copy → Paste into Claude
5. **Claude gives analysis** → Go to "Input Scores" → Enter sentiment scores
6. **Dashboard auto-refreshes** every 5 minutes with updated rankings
7. **Every 30 min** — Bot re-ranks with fresh data
8. **3:45 PM** — Final end-of-day ranking

---

## Scheduled Jobs

| Time (PKT) | Job | Description |
|------------|-----|-------------|
| 09:25 | Pre-Market Fetch | Download latest data |
| 09:30 | Market Open Analysis | Full ranking |
| 10:00-14:30 (every 30m) | Intraday Scan | Re-rank with fresh data |
| 15:45 | End-of-Day Summary | Final daily ranking |

---

## Security

- JWT authentication on all API endpoints
- Password hashed with bcrypt
- Rate limiting on login endpoint (via Nginx)
- Environment variables for all secrets
- Systemd sandboxing (NoNewPrivileges, ProtectSystem)

---

## Project Structure

```
psx_trading_bot/
├── app.py                 # FastAPI web server + API
├── config.py              # Configuration from .env
├── data_engine.py         # PSX data collection
├── math_engine.py         # Quantitative analysis
├── sentiment_engine.py    # News scraping + AI prompts
├── value_engine.py        # Fundamental analysis
├── ranking_engine.py      # Composite scoring + ranking
├── prompt_generator.py    # AI prompt templates
├── scheduler.py           # APScheduler job management
├── templates/
│   └── dashboard.html     # Live web dashboard UI
├── requirements.txt       # Python dependencies
├── .env.example           # Environment template
├── Dockerfile             # Container build
├── docker-compose.yml     # Multi-container setup
├── nginx.conf             # Reverse proxy config
├── deploy.sh              # Linux deployment script
└── README.md              # This file
```

---

## Disclaimer

This bot is for **educational and research purposes** only. It does not constitute financial advice. Always:
- Do your own research (DYOR)
- Paper trade first before using real money
- Consult a licensed financial advisor for investment decisions
- Comply with SECP regulations

---

Built with ❤️ for the PSX trading community.
