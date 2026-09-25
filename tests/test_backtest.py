import pytest

from algotrade.backtest import backtest


def test_tendance_haussiere_rentable():
    closes = [100.0] * 10 + [100 + i * 0.5 for i in range(1, 40)]
    result = backtest(closes, 3, 6, stop_loss_pct=0.05, take_profit_pct=0.05, fee_pct=0)
    assert result.trades
    assert result.total_return > 0
    assert result.trades[0].reason == "take_profit"


def test_stop_loss_limite_la_perte():
    closes = [100.0] * 10 + [101, 102, 90, 80, 70]
    result = backtest(closes, 2, 5, stop_loss_pct=0.05, take_profit_pct=0.5, fee_pct=0)
    assert result.trades[0].reason == "stop_loss"
    assert result.total_return < 0
    assert result.max_drawdown < 0


def test_sans_signal_capital_inchange():
    result = backtest([100.0] * 50, 3, 6, 0.01, 0.02)
    assert result.trades == []
    assert result.total_return == pytest.approx(0)


def test_frais_appliques():
    closes = [100.0] * 10 + [100 + i for i in range(1, 20)]
    sans = backtest(closes, 3, 6, 0.5, 0.05, fee_pct=0)
    avec = backtest(closes, 3, 6, 0.5, 0.05, fee_pct=0.01)
    assert avec.total_return < sans.total_return
