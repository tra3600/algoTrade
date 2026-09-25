"""Strategie de croisement de moyennes mobiles (logique pure, sans appel reseau)."""

from __future__ import annotations

from enum import Enum
from typing import Sequence


class Signal(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


def sma(values: Sequence[float], window: int) -> float:
    if len(values) < window:
        raise ValueError(f"{window} valeurs requises, {len(values)} fournies")
    return sum(values[-window:]) / window


def crossover_signal(closes: Sequence[float], short_window: int, long_window: int) -> Signal:
    """Signal sur le *croisement* des moyennes (et non leur simple position),
    pour ne pas racheter a chaque bougie tant que la courte reste au-dessus de la longue."""
    if len(closes) < long_window + 1:
        return Signal.HOLD
    prev = closes[:-1]
    prev_short, prev_long = sma(prev, short_window), sma(prev, long_window)
    short, long = sma(closes, short_window), sma(closes, long_window)
    if prev_short <= prev_long and short > long:
        return Signal.BUY
    if prev_short >= prev_long and short < long:
        return Signal.SELL
    return Signal.HOLD


def decide(signal: Signal, has_position: bool) -> Signal:
    """Filtre le signal selon la position : on n'achete que si on est a plat
    et on ne vend que ce que l'on detient (pas de vente a decouvert)."""
    if signal is Signal.BUY and not has_position:
        return Signal.BUY
    if signal is Signal.SELL and has_position:
        return Signal.SELL
    return Signal.HOLD
