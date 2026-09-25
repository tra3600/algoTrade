"""Gestion du risque : taille de position, stop-loss / take-profit, perte journaliere max."""

from __future__ import annotations

import math
from dataclasses import dataclass


def position_size(equity: float, buying_power: float, price: float, fraction: float) -> int:
    """Nombre d'actions entieres pour engager `fraction` du capital, limite au pouvoir d'achat."""
    if price <= 0:
        return 0
    budget = min(equity * fraction, buying_power)
    return max(0, math.floor(budget / price))


@dataclass(frozen=True)
class BracketPrices:
    stop_loss: float
    take_profit: float


def bracket_prices(entry: float, stop_loss_pct: float, take_profit_pct: float) -> BracketPrices:
    # Alpaca exige des prix arrondis au centime pour les actions >= 1 $.
    return BracketPrices(
        stop_loss=round(entry * (1 - stop_loss_pct), 2),
        take_profit=round(entry * (1 + take_profit_pct), 2),
    )


def daily_loss_exceeded(equity: float, last_equity: float, max_loss_pct: float) -> bool:
    """Vrai si le capital a baisse de plus de `max_loss_pct` depuis la cloture precedente."""
    if last_equity <= 0:
        return False
    return (last_equity - equity) / last_equity >= max_loss_pct
