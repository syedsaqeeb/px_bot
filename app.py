"""
PSX Trading Bot - FastAPI Web Dashboard
Protected with JWT authentication. Access restricted to your credentials.
Live dashboard — all signals and rankings served in real-time.

Endpoints:
  POST /login            -> Get JWT token
  GET  /dashboard        -> Main dashboard with ranked stocks
  GET  /api/rankings     -> All stock rankings (JSON)
  GET  /api/stock/{sym}  -> Detailed analysis for a stock
  GET  /api/signals      -> Current buy/sell signals
  GET  /api/prompts/*    -> AI prompts ready to copy
  POST /api/sentiment    -> Input AI sentiment scores back
  POST /api/value-override -> Input AI value scores back
"""

from datetime import datetime, timedelta
import math
import secrets

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.templating import Jinja2Templates

from jose import JWTError, jwt
from pydantic import BaseModel
from loguru import logger

from config import settings
from data_engine import data_engine
from math_engine import math_engine
from ranking_engine import ranking_engine
from sentiment_engine import sentiment_engine
from value_engine import value_engine
from paper_trading import paper_trading_engine
from prompt_generator import prompt_generator
from scheduler import trading_scheduler

# ------------------------------------------------------------------
# App Setup
# ------------------------------------------------------------------
app = FastAPI(
    title="PSX Trading Bot",
    description="Semi-automated PSX stock analysis and ranking system",
    version="1.0.0",
)

templates = Jinja2Templates(directory="templates")

# ------------------------------------------------------------------
# Auth Setup
# ------------------------------------------------------------------
security = HTTPBearer(auto_error=False)


def sanitize_json(value):
    """Convert NaN/infinite floats from pandas-derived payloads into JSON-safe values."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: sanitize_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_json(item) for item in value]
    return value


def create_token(username: str) -> str:
    """Create a JWT access token."""
    expire = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {"sub": username, "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Verify JWT token and return username."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return username
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ------------------------------------------------------------------
# Request / Response Models
# ------------------------------------------------------------------
class LoginRequest(BaseModel):
    username: str
    password: str


class SentimentInput(BaseModel):
    symbol: str
    score: float          # -100 to +100
    outlook_short: str = "neutral"
    outlook_medium: str = "neutral"
    notes: str = ""


class ValueOverrideInput(BaseModel):
    symbol: str
    score: float          # 0 to 100
    notes: str = ""


class UniverseSourceInput(BaseModel):
    source: str


class PaperTradeInput(BaseModel):
    symbol: str
    side: str
    quantity: int
    price: float | None = None
    notes: str = ""


class PaperResetInput(BaseModel):
    starting_cash: float | None = None


# ------------------------------------------------------------------
# Public Endpoints
# ------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def root():
    """Login page."""
    return """
    <html>
    <head><title>PSX Trading Bot - Login</title>
    <style>
        body { font-family: 'Segoe UI', sans-serif; background: #1a1a2e; color: #eee;
               display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .login-box { background: #16213e; padding: 40px; border-radius: 12px;
                     box-shadow: 0 8px 32px rgba(0,0,0,0.3); width: 350px; }
        h2 { text-align: center; color: #00d2ff; margin-bottom: 30px; }
        input { width: 100%; padding: 12px; margin: 8px 0; border: 1px solid #333;
                border-radius: 6px; background: #0f3460; color: #fff; box-sizing: border-box; }
        button { width: 100%; padding: 14px; background: #00d2ff; color: #1a1a2e;
                 border: none; border-radius: 6px; font-weight: bold; cursor: pointer;
                 font-size: 16px; margin-top: 16px; }
        button:hover { background: #00b4d8; }
        .subtitle { text-align: center; color: #888; font-size: 13px; }
    </style>
    </head>
    <body>
        <div class="login-box">
            <h2>&#x1F4C8; PSX Trading Bot</h2>
            <p class="subtitle">Restricted Access</p>
            <form id="loginForm">
                <input type="text" id="username" placeholder="Username" required>
                <input type="password" id="password" placeholder="Password" required>
                <button type="submit">Login</button>
            </form>
            <script>
                document.getElementById('loginForm').addEventListener('submit', async (e) => {
                    e.preventDefault();
                    const resp = await fetch('/login', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            username: document.getElementById('username').value,
                            password: document.getElementById('password').value,
                        })
                    });
                    const data = await resp.json();
                    if (data.access_token) {
                        localStorage.setItem('token', data.access_token);
                        window.location.href = '/dashboard';
                    } else {
                        alert(data.detail || 'Login failed');
                    }
                });
            </script>
        </div>
    </body>
    </html>
    """


@app.post("/login")
async def login(req: LoginRequest):
    """Authenticate and return JWT token."""
    password_matches = secrets.compare_digest(req.password, settings.BOT_PASSWORD)
    if req.username != settings.BOT_USERNAME or not password_matches:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token(req.username)
    return {"access_token": token, "token_type": "bearer", "expires_in": settings.JWT_EXPIRE_MINUTES * 60}


# ------------------------------------------------------------------
# Protected Endpoints
# ------------------------------------------------------------------
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard — serves the HTML template."""
    return templates.TemplateResponse(request, "dashboard.html", {"request": request})


@app.get("/api/rankings")
async def api_rankings(user: str = Depends(verify_token)):
    """Get current stock rankings as JSON."""
    df = ranking_engine.get_last_ranking()
    if df is None or df.empty:
        df = ranking_engine.rank_all()
    records = sanitize_json(df.to_dict(orient="records") if not df.empty else [])
    universe = data_engine.get_universe_status()
    return {
        "rankings": records,
        "timestamp": ranking_engine._last_ranking_time,
        "total_stocks": len(records),
        "sbp_rate": settings.SBP_POLICY_RATE,
        "universe": universe,
    }


@app.get("/api/universe")
async def api_universe_status(user: str = Depends(verify_token)):
    """Get the active stock-universe source and current ticker count."""
    return data_engine.get_universe_status()


@app.post("/api/universe")
async def api_set_universe(data: UniverseSourceInput, user: str = Depends(verify_token)):
    """Switch stock universe and clear stale rankings."""
    try:
        universe = data_engine.set_universe_source(data.source)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    ranking_engine._last_ranking = None
    ranking_engine._last_ranking_time = None
    return universe


@app.get("/api/stock/{symbol}")
async def api_stock_detail(symbol: str, user: str = Depends(verify_token)):
    """Detailed analysis for a specific stock."""
    symbol = symbol.upper()
    df = data_engine.get_historical(symbol)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"No data for {symbol}")
    analysis = math_engine.full_analysis(df, symbol)
    value = value_engine.value_score(symbol)
    sentiment = sentiment_engine.get_sentiment_score(symbol)
    return sanitize_json({"symbol": symbol, "analysis": analysis, "value": value, "sentiment": sentiment})


@app.get("/api/signals")
async def api_signals(user: str = Depends(verify_token)):
    """Get current buy/sell signals."""
    buys = ranking_engine.get_top_buys(10)
    sells = ranking_engine.get_sell_signals()
    return sanitize_json({
        "buy_signals": buys.to_dict(orient="records") if not buys.empty else [],
        "sell_signals": sells.to_dict(orient="records") if not sells.empty else [],
        "timestamp": datetime.now().isoformat(),
    })


@app.get("/api/prompts")
async def api_prompts(user: str = Depends(verify_token)):
    """List all available AI prompt types."""
    return {
        "available_prompts": [
            {"type": "daily", "url": "/api/prompts/daily"},
            {"type": "market_sentiment", "url": "/api/prompts/market_sentiment"},
            {"type": "stock_sentiment", "url": "/api/prompts/sentiment/{symbol}"},
            {"type": "trade_validation", "url": "/api/prompts/validate/{symbol}"},
            {"type": "value", "url": "/api/prompts/value/{symbol}"},
        ]
    }


@app.get("/api/prompts/daily")
async def api_prompt_daily(user: str = Depends(verify_token)):
    return {"prompt": prompt_generator.daily_analysis_prompt(), "type": "daily"}


@app.get("/api/prompts/market_sentiment")
async def api_prompt_market(user: str = Depends(verify_token)):
    return {"prompt": prompt_generator.market_sentiment_prompt(), "type": "market_sentiment"}


@app.get("/api/prompts/sentiment/{symbol}")
async def api_prompt_sentiment(symbol: str, user: str = Depends(verify_token)):
    return {"prompt": prompt_generator.sentiment_prompt(symbol.upper()), "type": "sentiment"}


@app.get("/api/prompts/validate/{symbol}")
async def api_prompt_validate(symbol: str, user: str = Depends(verify_token)):
    return {"prompt": prompt_generator.trade_validation_prompt(symbol.upper()), "type": "trade_validation"}


@app.get("/api/prompts/value/{symbol}")
async def api_prompt_value(symbol: str, user: str = Depends(verify_token)):
    return {"prompt": prompt_generator.value_prompt(symbol.upper()), "type": "value"}


@app.post("/api/sentiment")
async def api_set_sentiment(data: SentimentInput, user: str = Depends(verify_token)):
    """Input AI-generated sentiment score."""
    result = sentiment_engine.set_sentiment_score(
        symbol=data.symbol.upper(), score=data.score,
        outlook_short=data.outlook_short, outlook_medium=data.outlook_medium,
        notes=data.notes,
    )
    return {"status": "ok", "data": result}


@app.post("/api/value-override")
async def api_set_value(data: ValueOverrideInput, user: str = Depends(verify_token)):
    """Input AI-generated value score override."""
    result = value_engine.set_value_override(
        symbol=data.symbol.upper(), score=data.score, notes=data.notes,
    )
    return {"status": "ok", "data": result}


@app.get("/api/paper-portfolio")
async def api_paper_portfolio(user: str = Depends(verify_token)):
    """Get paper-trading portfolio, positions, and trade history."""
    return sanitize_json(paper_trading_engine.get_summary())


@app.post("/api/paper-trades")
async def api_paper_trade(data: PaperTradeInput, user: str = Depends(verify_token)):
    """Execute a simulated buy or sell order in the paper portfolio."""
    try:
        result = paper_trading_engine.place_order(
            symbol=data.symbol,
            side=data.side,
            quantity=data.quantity,
            price=data.price,
            notes=data.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return sanitize_json(result)


@app.post("/api/paper-reset")
async def api_paper_reset(data: PaperResetInput, user: str = Depends(verify_token)):
    """Reset the paper portfolio to a fresh starting balance."""
    return sanitize_json(paper_trading_engine.reset(data.starting_cash))


@app.get("/api/scheduler/status")
async def api_scheduler_status(user: str = Depends(verify_token)):
    return {"running": trading_scheduler.is_running}


@app.post("/api/scheduler/start")
async def api_scheduler_start(user: str = Depends(verify_token)):
    trading_scheduler.start()
    return {"status": "started"}


@app.post("/api/scheduler/stop")
async def api_scheduler_stop(user: str = Depends(verify_token)):
    trading_scheduler.stop()
    return {"status": "stopped"}


# ------------------------------------------------------------------
# Run: uvicorn app:app --host 0.0.0.0 --port 8000
# ------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    trading_scheduler.start()
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
