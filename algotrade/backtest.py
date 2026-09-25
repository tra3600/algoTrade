"""Backtest simple de la strategie sur une serie de prix de cloture.

Hypotheses (volontairement prudentes et simples) :
- entree / sortie au prix de cloture de la bougie du signal ;
- stop-loss / take-profit verifies sur les clotures (pas sur les plus hauts / plus bas) ;
- un cout par transaction (`fee_pct`) couvre commissions et slippage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from .strategy import Signal, crossover_signal, decide


@dataclass
class Trade:
    entry_index: int
    entry_price: float
    exit_index: int
    exit_price: float
    reason: str

    @property
    def return_pct(self) -> float:
        return self.exit_price / self.entry_price - 1


@dataclass
class BacktestResult:
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)

    @property
    def total_return(self) -> float:
        return self.equity_curve[-1] / self.equity_curve[0] - 1 if self.equity_curve else 0.0

    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        return sum(t.return_pct > 0 for t in self.trades) / len(self.trades)

    @property
    def max_drawdown(self) -> float:
        peak, worst = float("-inf"), 0.0
        for value in self.equity_curve:
            peak = max(peak, value)
            worst = min(worst, value / peak - 1)
        return worst

    def summary(self) -> str:
        return (
            f"trades={len(self.trades)} rendement={self.total_return:+.2%} "
            f"taux_gain={self.win_rate:.0%} drawdown_max={self.max_drawdown:.2%}"
        )


def backtest(
    closes: Sequence[float],
    short_window: int,
    long_window: int,
    stop_loss_pct: float,
    take_profit_pct: float,
    fee_pct: float = 0.0005,
    initial_equity: float = 10_000.0,
) -> BacktestResult:
    result = BacktestResult()
    cash, shares = initial_equity, 0.0
    entry_index, entry_price = -1, 0.0

    def close_trade(i: int, price: float, reason: str) -> None:
        nonlocal cash, shares
        cash += shares * price * (1 - fee_pct)
        shares = 0.0
        result.trades.append(Trade(entry_index, entry_price, i, price, reason))

    for i, price in enumerate(closes):
        if shares:
            if price <= entry_price * (1 - stop_loss_pct):
                close_trade(i, price, "stop_loss")
            elif price >= entry_price * (1 + take_profit_pct):
                close_trade(i, price, "take_profit")

        action = decide(crossover_signal(closes[: i + 1], short_window, long_window), bool(shares))
        if action is Signal.BUY:
            shares = cash * (1 - fee_pct) / price
            cash, entry_index, entry_price = 0.0, i, price
        elif action is Signal.SELL:
            close_trade(i, price, "signal")

        result.equity_curve.append(cash + shares * price)

    if shares:
        close_trade(len(closes) - 1, closes[-1], "fin")
        result.equity_curve[-1] = cash
    return result
