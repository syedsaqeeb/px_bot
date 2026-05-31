"""
PSX Trading Bot - Paper Trading Engine
Tracks simulated orders, positions, cash, and portfolio performance.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

from config import settings
from data_engine import data_engine


class PaperTradingEngine:
    """Simple persistent paper-trading ledger for simulated orders."""

    def __init__(self):
        self._state_path = Path(settings.DATA_CACHE_DIR) / "paper_portfolio.json"
        self._default_cash = 1_000_000.0
        self._state = {
            "starting_cash": self._default_cash,
            "cash": self._default_cash,
            "realized_pnl": 0.0,
            "positions": {},
            "trades": [],
            "closed_trades": [],
            "updated_at": datetime.now().isoformat(),
        }
        self._load()

    def _load(self):
        if not self._state_path.exists():
            self._save()
            return
        try:
            self._state = json.loads(self._state_path.read_text(encoding="utf-8"))
            self._migrate_state()
        except Exception as exc:
            logger.warning(f"Failed to load paper portfolio, resetting state: {exc}")
            self.reset()

    def _migrate_state(self):
        self._state.setdefault("closed_trades", [])
        self._state.setdefault("trades", [])
        self._state.setdefault("positions", {})
        for symbol, position in list(self._state["positions"].items()):
            quantity = int(position.get("quantity", 0))
            avg_cost = float(position.get("avg_cost", 0.0))
            lots = position.get("lots") or []
            if quantity <= 0:
                self._state["positions"].pop(symbol, None)
                continue
            if not lots:
                position["lots"] = [{
                    "quantity": quantity,
                    "price": avg_cost,
                    "timestamp": self._state.get("updated_at", datetime.now().isoformat()),
                }]
            position["quantity"] = quantity
            position["avg_cost"] = avg_cost

    def _save(self):
        self._state["updated_at"] = datetime.now().isoformat()
        self._state_path.write_text(json.dumps(self._state, indent=2), encoding="utf-8")

    @staticmethod
    def _iso_now() -> str:
        return datetime.now().isoformat()

    @staticmethod
    def _average_cost(lots: list[dict]) -> float:
        total_qty = sum(int(lot["quantity"]) for lot in lots)
        if total_qty <= 0:
            return 0.0
        total_cost = sum(float(lot["price"]) * int(lot["quantity"]) for lot in lots)
        return round(total_cost / total_qty, 4)

    @staticmethod
    def _holding_hours(started_at: str, ended_at: str) -> float:
        opened = datetime.fromisoformat(started_at)
        closed = datetime.fromisoformat(ended_at)
        return round((closed - opened).total_seconds() / 3600, 2)

    def _current_price(self, symbol: str) -> float:
        quote = data_engine.get_live_quote(symbol.upper())
        price = quote.get("close") or quote.get("current_price") or 0
        return round(float(price), 2) if price else 0.0

    def reset(self, starting_cash: Optional[float] = None) -> dict:
        cash = float(starting_cash) if starting_cash is not None else self._default_cash
        self._state = {
            "starting_cash": cash,
            "cash": cash,
            "realized_pnl": 0.0,
            "positions": {},
            "trades": [],
            "closed_trades": [],
            "updated_at": datetime.now().isoformat(),
        }
        self._save()
        return self.get_summary()

    def place_order(self, symbol: str, side: str, quantity: int, price: Optional[float] = None, notes: str = "") -> dict:
        symbol = symbol.upper().strip()
        normalized_side = side.upper().strip()
        if normalized_side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        if quantity <= 0:
            raise ValueError("quantity must be positive")

        fill_price = round(float(price), 2) if price is not None else self._current_price(symbol)
        if fill_price <= 0:
            raise ValueError(f"No tradable price available for {symbol}")

        positions = self._state["positions"]
        timestamp = self._iso_now()
        position = positions.get(symbol, {"quantity": 0, "avg_cost": 0.0, "lots": []})
        trade_value = round(fill_price * quantity, 2)

        if normalized_side == "BUY":
            if trade_value > self._state["cash"]:
                raise ValueError("Insufficient paper cash for this buy order")
            lots = list(position.get("lots", []))
            lots.append({"quantity": quantity, "price": fill_price, "timestamp": timestamp})
            new_quantity = position["quantity"] + quantity
            positions[symbol] = {
                "quantity": new_quantity,
                "avg_cost": self._average_cost(lots),
                "lots": lots,
            }
            self._state["cash"] = round(self._state["cash"] - trade_value, 2)
            realized_pnl = 0.0
        else:
            if position["quantity"] < quantity:
                raise ValueError("Insufficient paper holdings for this sell order")
            remaining_to_sell = quantity
            lots = list(position.get("lots", []))
            updated_lots = []
            closed_trades = []
            realized_pnl_total = 0.0
            for lot in lots:
                lot_quantity = int(lot["quantity"])
                if remaining_to_sell <= 0:
                    updated_lots.append(lot)
                    continue
                matched_qty = min(remaining_to_sell, lot_quantity)
                realized_pnl = round((fill_price - float(lot["price"])) * matched_qty, 2)
                closed_trade = {
                    "symbol": symbol,
                    "quantity": matched_qty,
                    "buy_price": round(float(lot["price"]), 2),
                    "sell_price": fill_price,
                    "buy_timestamp": lot["timestamp"],
                    "sell_timestamp": timestamp,
                    "holding_hours": self._holding_hours(lot["timestamp"], timestamp),
                    "realized_pnl": realized_pnl,
                    "realized_pct": round(((fill_price - float(lot["price"])) / float(lot["price"])) * 100, 2) if float(lot["price"]) > 0 else 0.0,
                }
                closed_trades.append(closed_trade)
                realized_pnl_total += realized_pnl
                remaining_to_sell -= matched_qty
                if lot_quantity > matched_qty:
                    updated_lots.append({
                        "quantity": lot_quantity - matched_qty,
                        "price": lot["price"],
                        "timestamp": lot["timestamp"],
                    })

            realized_pnl = round(realized_pnl_total, 2)
            remaining_quantity = position["quantity"] - quantity
            if remaining_quantity == 0:
                positions.pop(symbol, None)
            else:
                positions[symbol] = {
                    "quantity": remaining_quantity,
                    "avg_cost": self._average_cost(updated_lots),
                    "lots": updated_lots,
                }
            self._state["cash"] = round(self._state["cash"] + trade_value, 2)
            self._state["realized_pnl"] = round(self._state["realized_pnl"] + realized_pnl, 2)
            self._state["closed_trades"] = closed_trades + self._state["closed_trades"]

        trade = {
            "timestamp": timestamp,
            "symbol": symbol,
            "side": normalized_side,
            "quantity": quantity,
            "price": fill_price,
            "trade_value": trade_value,
            "realized_pnl": realized_pnl,
            "notes": notes,
        }
        self._state["trades"].insert(0, trade)
        self._save()
        return {"trade": trade, "portfolio": self.get_summary()}

    def _analytics(self) -> dict:
        closed_trades = self._state.get("closed_trades", [])
        closed_count = len(closed_trades)
        if closed_count == 0:
            return {
                "closed_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate_pct": 0.0,
                "average_hold_hours": 0.0,
                "average_closed_pnl": 0.0,
                "gross_profit": 0.0,
                "gross_loss": 0.0,
                "closed_trade_pnl": 0.0,
            }

        winning = [trade for trade in closed_trades if float(trade["realized_pnl"]) > 0]
        losing = [trade for trade in closed_trades if float(trade["realized_pnl"]) < 0]
        gross_profit = round(sum(float(trade["realized_pnl"]) for trade in winning), 2)
        gross_loss = round(sum(float(trade["realized_pnl"]) for trade in losing), 2)
        closed_trade_pnl = round(sum(float(trade["realized_pnl"]) for trade in closed_trades), 2)
        average_hold_hours = round(sum(float(trade["holding_hours"]) for trade in closed_trades) / closed_count, 2)
        average_closed_pnl = round(closed_trade_pnl / closed_count, 2)
        return {
            "closed_trades": closed_count,
            "winning_trades": len(winning),
            "losing_trades": len(losing),
            "win_rate_pct": round((len(winning) / closed_count) * 100, 2),
            "average_hold_hours": average_hold_hours,
            "average_closed_pnl": average_closed_pnl,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "closed_trade_pnl": closed_trade_pnl,
        }

    def get_summary(self) -> dict:
        positions_summary = []
        market_value = 0.0
        for symbol, position in sorted(self._state["positions"].items()):
            current_price = self._current_price(symbol)
            quantity = position["quantity"]
            avg_cost = float(position["avg_cost"])
            cost_basis = round(quantity * avg_cost, 2)
            current_value = round(quantity * current_price, 2)
            unrealized_pnl = round(current_value - cost_basis, 2)
            unrealized_pct = round((unrealized_pnl / cost_basis) * 100, 2) if cost_basis > 0 else 0.0
            market_value += current_value
            positions_summary.append({
                "symbol": symbol,
                "quantity": quantity,
                "avg_cost": round(avg_cost, 2),
                "current_price": current_price,
                "cost_basis": cost_basis,
                "market_value": current_value,
                "unrealized_pnl": unrealized_pnl,
                "unrealized_pct": unrealized_pct,
            })

        cash = round(float(self._state["cash"]), 2)
        realized_pnl = round(float(self._state["realized_pnl"]), 2)
        equity = round(cash + market_value, 2)
        total_pnl = round((equity - float(self._state["starting_cash"])), 2)
        total_return_pct = round((total_pnl / float(self._state["starting_cash"])) * 100, 2) if self._state["starting_cash"] else 0.0
        analytics = self._analytics()
        return {
            "starting_cash": round(float(self._state["starting_cash"]), 2),
            "cash": cash,
            "market_value": round(market_value, 2),
            "equity": equity,
            "realized_pnl": realized_pnl,
            "total_pnl": total_pnl,
            "total_return_pct": total_return_pct,
            "analytics": analytics,
            "positions": positions_summary,
            "trades": self._state["trades"][:100],
            "closed_trades": self._state.get("closed_trades", [])[:100],
            "updated_at": self._state["updated_at"],
        }


paper_trading_engine = PaperTradingEngine()
