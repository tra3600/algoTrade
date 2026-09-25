"""Indicateurs techniques et logique de signal (sans dépendance à l'API : testable hors ligne).

Stratégie : croisement EMA rapide / EMA lente sur bougies 1 minute,
filtré par le RSI et une confirmation de volume. Stop-loss et take-profit
calculés à partir de l'ATR (volatilité).
"""
from dataclasses import dataclass
from enum import Enum
import math

import pandas as pd

from config import StrategyConfig


class Signal(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """RSI de Wilder."""
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = gain / loss
    out = 100 - 100 / (1 + rs)
    # Aucune perte sur la période -> RSI = 100
    return out.where(loss != 0, 100.0).where(gain.notna())


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def compute_indicators(df: pd.DataFrame, cfg: StrategyConfig) -> pd.DataFrame:
    """Ajoute les colonnes d'indicateurs. df doit contenir open/high/low/close/volume."""
    out = df.copy()
    out["ema_fast"] = ema(out["close"], cfg.ema_fast)
    out["ema_slow"] = ema(out["close"], cfg.ema_slow)
    out["rsi"] = rsi(out["close"], cfg.rsi_period)
    out["atr"] = atr(out, cfg.atr_period)
    out["volume_ma"] = out["volume"].rolling(cfg.volume_ma_period).mean()
    return out


def min_bars_required(cfg: StrategyConfig) -> int:
    return max(cfg.ema_slow, cfg.rsi_period, cfg.atr_period, cfg.volume_ma_period) + 2


def generate_signal(ind: pd.DataFrame, cfg: StrategyConfig, in_position: bool) -> Signal:
    """Signal basé sur les deux dernières bougies clôturées (indicateurs déjà calculés)."""
    if len(ind) < min_bars_required(cfg):
        return Signal.HOLD

    prev, last = ind.iloc[-2], ind.iloc[-1]
    if last[["ema_fast", "ema_slow", "rsi", "atr"]].isna().any():
        return Signal.HOLD

    crossed_up = prev["ema_fast"] <= prev["ema_slow"] and last["ema_fast"] > last["ema_slow"]
    crossed_down = prev["ema_fast"] >= prev["ema_slow"] and last["ema_fast"] < last["ema_slow"]

    if in_position:
        if crossed_down or last["rsi"] >= cfg.rsi_exit:
            return Signal.SELL
        return Signal.HOLD

    if crossed_up and last["rsi"] < cfg.rsi_overbought and last["close"] > last["ema_slow"]:
        if cfg.require_volume_confirmation:
            if pd.isna(last["volume_ma"]) or last["volume"] < last["volume_ma"]:
                return Signal.HOLD
        return Signal.BUY
    return Signal.HOLD


@dataclass
class TradePlan:
    qty: int
    entry: float
    stop_loss: float
    take_profit: float


def plan_trade(entry: float, atr_value: float, equity: float, cfg: StrategyConfig) -> TradePlan | None:
    """Calcule taille de position, stop et objectif. Renvoie None si le trade n'est pas viable."""
    if entry <= 0 or equity <= 0 or not atr_value or math.isnan(atr_value) or atr_value <= 0:
        return None
    stop_distance = cfg.stop_loss_atr_mult * atr_value
    stop_loss = round(entry - stop_distance, 2)
    take_profit = round(entry + cfg.take_profit_atr_mult * atr_value, 2)
    # Alpaca exige un écart d'au moins 0.01 $ entre prix et stop / take-profit
    if stop_loss <= 0 or entry - stop_loss < 0.01 or take_profit - entry < 0.01:
        return None

    qty_by_risk = (equity * cfg.risk_per_trade) / (entry - stop_loss)
    qty_by_cap = (equity * cfg.max_position_pct) / entry
    qty = int(min(qty_by_risk, qty_by_cap))
    if qty < 1:
        return None
    return TradePlan(qty=qty, entry=entry, stop_loss=stop_loss, take_profit=take_profit)
