"""Backtest de la stratégie sur des bougies historiques.

Hypothèses (volontairement prudentes) :
- le signal est calculé à la clôture d'une bougie, l'ordre est exécuté à l'ouverture de la suivante ;
- si le stop et l'objectif sont touchés dans la même bougie, on considère que le stop est touché ;
- toute position est clôturée à la dernière bougie de chaque séance (pas de position overnight) ;
- un glissement (slippage) est appliqué à chaque exécution.
"""
from dataclasses import dataclass, field

import pandas as pd

from config import StrategyConfig
from signals import Signal, compute_indicators, generate_signal, min_bars_required, plan_trade


@dataclass
class Trade:
    entry_time: pd.Timestamp
    entry_price: float
    qty: int
    exit_time: pd.Timestamp | None = None
    exit_price: float | None = None
    reason: str = ""

    @property
    def pnl(self) -> float:
        return (self.exit_price - self.entry_price) * self.qty if self.exit_price is not None else 0.0


@dataclass
class BacktestResult:
    initial_equity: float
    final_equity: float
    trades: list[Trade] = field(default_factory=list)
    equity_curve: pd.Series | None = None

    @property
    def total_return(self) -> float:
        return self.final_equity / self.initial_equity - 1

    @property
    def win_rate(self) -> float:
        return sum(t.pnl > 0 for t in self.trades) / len(self.trades) if self.trades else 0.0

    @property
    def profit_factor(self) -> float:
        gains = sum(t.pnl for t in self.trades if t.pnl > 0)
        losses = -sum(t.pnl for t in self.trades if t.pnl < 0)
        return gains / losses if losses else float("inf") if gains else 0.0

    @property
    def max_drawdown(self) -> float:
        if self.equity_curve is None or self.equity_curve.empty:
            return 0.0
        return float((self.equity_curve / self.equity_curve.cummax() - 1).min())

    def summary(self) -> str:
        return (
            f"Trades           : {len(self.trades)}\n"
            f"Capital final    : {self.final_equity:,.2f} (départ {self.initial_equity:,.2f})\n"
            f"Rendement        : {self.total_return:+.2%}\n"
            f"Taux de réussite : {self.win_rate:.1%}\n"
            f"Profit factor    : {self.profit_factor:.2f}\n"
            f"Drawdown max     : {self.max_drawdown:.2%}"
        )


def _session_dates(index: pd.DatetimeIndex) -> pd.Series:
    idx = index.tz_convert("America/New_York") if index.tz is not None else index
    return pd.Series(idx.date, index=index)


def run_backtest(bars: pd.DataFrame, cfg: StrategyConfig, initial_equity: float = 10_000.0,
                 slippage: float = 0.0002) -> BacktestResult:
    ind = compute_indicators(bars, cfg)
    dates = _session_dates(ind.index)
    n_min = min_bars_required(cfg)

    cash = initial_equity
    trade: Trade | None = None
    stop = target = 0.0
    trades: list[Trade] = []
    curve = []
    pending: Signal | None = None  # ordre décidé à la clôture précédente
    pending_plan = None

    def close(i: int, price: float, reason: str) -> None:
        nonlocal cash, trade
        trade.exit_time, trade.exit_price, trade.reason = ind.index[i], price, reason
        cash += price * trade.qty
        trades.append(trade)
        trade = None

    for i in range(len(ind)):
        row = ind.iloc[i]
        is_last_of_day = i == len(ind) - 1 or dates.iloc[i + 1] != dates.iloc[i]

        # 1) Exécution à l'ouverture des décisions prises à la bougie précédente
        if pending == Signal.BUY and trade is None and pending_plan is not None:
            price = row["open"] * (1 + slippage)
            qty = min(pending_plan.qty, int(cash // price))
            if qty >= 1:
                trade = Trade(ind.index[i], price, qty)
                cash -= price * qty
                # stop / objectif recalés sur le prix réel d'exécution
                stop = price - (pending_plan.entry - pending_plan.stop_loss)
                target = price + (pending_plan.take_profit - pending_plan.entry)
        elif pending == Signal.SELL and trade is not None:
            close(i, row["open"] * (1 - slippage), "signal")
        pending, pending_plan = None, None

        # 2) Stop-loss / take-profit pendant la bougie
        if trade is not None:
            if row["low"] <= stop:
                close(i, min(stop, row["open"]) * (1 - slippage), "stop")
            elif row["high"] >= target:
                close(i, max(target, row["open"]) * (1 - slippage), "objectif")

        # 3) Fin de séance : on sort à la clôture
        if trade is not None and is_last_of_day:
            close(i, row["close"] * (1 - slippage), "fin de séance")

        # 4) Signal à la clôture pour la bougie suivante
        if i + 1 >= n_min and not is_last_of_day:
            window = ind.iloc[i + 1 - n_min:i + 1]
            signal = generate_signal(window, cfg, in_position=trade is not None)
            if signal == Signal.BUY:
                equity = cash
                plan = plan_trade(float(row["close"]), float(row["atr"]), equity, cfg)
                if plan is not None:
                    pending, pending_plan = signal, plan
            elif signal == Signal.SELL:
                pending = signal

        curve.append(cash + (trade.qty * row["close"] if trade else 0.0))

    equity_curve = pd.Series(curve, index=ind.index, dtype=float)
    final = float(equity_curve.iloc[-1]) if len(equity_curve) else initial_equity
    return BacktestResult(initial_equity, final, trades, equity_curve)
