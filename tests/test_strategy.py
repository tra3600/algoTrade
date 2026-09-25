import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest import run_backtest  # noqa: E402
from config import StrategyConfig  # noqa: E402
from signals import Signal, compute_indicators, generate_signal, plan_trade, rsi  # noqa: E402


def make_bars(closes, volume=1000, start="2024-01-02 09:30", tz="America/New_York"):
    closes = np.asarray(closes, dtype=float)
    idx = pd.date_range(start, periods=len(closes), freq="1min", tz=tz)
    opens = np.concatenate([[closes[0]], closes[:-1]])
    vol = np.full(len(closes), volume, dtype=float) if np.isscalar(volume) else np.asarray(volume, float)
    return pd.DataFrame({
        "open": opens,
        "high": np.maximum(opens, closes) + 0.05,
        "low": np.minimum(opens, closes) - 0.05,
        "close": closes,
        "volume": vol,
    }, index=idx)


def test_rsi_bounds():
    close = pd.Series(np.linspace(100, 120, 50))
    r = rsi(close, 14)
    assert r.iloc[-1] == pytest.approx(100.0)
    close = pd.Series(np.linspace(120, 100, 50))
    assert rsi(close, 14).iloc[-1] == pytest.approx(0.0, abs=1e-9)


def test_buy_signal_on_bullish_crossover():
    cfg = StrategyConfig(require_volume_confirmation=False)
    # Baisse douce puis rebond franc -> croisement haussier des EMA
    closes = list(np.linspace(110, 100, 40))
    ind = None
    for k in range(1, 30):
        seq = closes + list(100 + 0.4 * np.arange(1, k + 1))
        ind = compute_indicators(make_bars(seq), cfg)
        sig = generate_signal(ind, cfg, in_position=False)
        if sig == Signal.BUY:
            break
    assert sig == Signal.BUY
    assert ind.iloc[-1]["ema_fast"] > ind.iloc[-1]["ema_slow"]


def test_no_buy_when_already_in_position_and_sell_on_bearish_crossover():
    cfg = StrategyConfig(require_volume_confirmation=False, rsi_exit=101)
    closes = list(np.linspace(100, 110, 40))
    signals = []
    for k in range(1, 30):
        seq = closes + list(110 - 0.4 * np.arange(1, k + 1))
        ind = compute_indicators(make_bars(seq), cfg)
        signals.append(generate_signal(ind, cfg, in_position=True))
    assert Signal.BUY not in signals
    assert Signal.SELL in signals


def test_hold_with_insufficient_data():
    cfg = StrategyConfig()
    ind = compute_indicators(make_bars([100, 101, 102]), cfg)
    assert generate_signal(ind, cfg, in_position=False) == Signal.HOLD


def test_plan_trade_risk_sizing():
    cfg = StrategyConfig(risk_per_trade=0.01, max_position_pct=1.0,
                         stop_loss_atr_mult=1.0, take_profit_atr_mult=2.0)
    plan = plan_trade(entry=100.0, atr_value=0.5, equity=10_000, cfg=cfg)
    assert plan.stop_loss == 99.5 and plan.take_profit == 101.0
    assert plan.qty == 100  # 100 $ de risque / 0.50 $ par action
    # Plafond de taille de position
    cfg.max_position_pct = 0.1
    assert plan_trade(100.0, 0.5, 10_000, cfg).qty == 10
    # Cas invalides
    assert plan_trade(100.0, 0.0, 10_000, cfg) is None
    assert plan_trade(100.0, float("nan"), 10_000, cfg) is None
    assert plan_trade(100.0, 0.5, 10, cfg) is None


def test_backtest_runs_and_closes_positions_each_day():
    rng = np.random.default_rng(42)
    day1 = 100 + np.cumsum(rng.normal(0, 0.1, 390))
    day2 = day1[-1] + np.cumsum(rng.normal(0, 0.1, 390))
    bars = pd.concat([
        make_bars(day1, volume=rng.integers(500, 2000, 390), start="2024-01-02 09:30"),
        make_bars(day2, volume=rng.integers(500, 2000, 390), start="2024-01-03 09:30"),
    ])
    result = run_backtest(bars, StrategyConfig(), initial_equity=10_000)
    assert len(result.equity_curve) == len(bars)
    assert result.final_equity > 0
    for t in result.trades:
        assert t.exit_time is not None
        assert t.exit_time.date() == t.entry_time.date()  # jamais de position overnight
        assert t.exit_time > t.entry_time or t.reason in ("stop", "objectif")
    # Sans position ouverte en fin de test, le capital final = cash
    assert result.final_equity == pytest.approx(10_000 + sum(t.pnl for t in result.trades))


def test_backtest_trend_is_profitable():
    cfg = StrategyConfig(require_volume_confirmation=False)
    # Consolidation puis forte tendance haussière : la stratégie doit en capter une partie
    closes = list(np.linspace(100, 99, 60)) + list(99 + 0.05 * np.arange(1, 200))
    result = run_backtest(make_bars(closes), cfg, initial_equity=10_000, slippage=0)
    assert result.trades
    assert result.final_equity > 10_000
