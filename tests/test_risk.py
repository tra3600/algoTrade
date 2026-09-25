from algotrade.risk import bracket_prices, daily_loss_exceeded, position_size


def test_position_size():
    assert position_size(10_000, 50_000, 100, 0.1) == 10
    assert position_size(10_000, 500, 100, 0.1) == 5  # limite par le pouvoir d'achat
    assert position_size(100, 100, 150, 0.1) == 0
    assert position_size(10_000, 10_000, 0, 0.1) == 0


def test_bracket_prices():
    b = bracket_prices(100.0, 0.01, 0.02)
    assert b.stop_loss == 99.0
    assert b.take_profit == 102.0


def test_daily_loss():
    assert daily_loss_exceeded(9_600, 10_000, 0.03)
    assert not daily_loss_exceeded(9_800, 10_000, 0.03)
    assert not daily_loss_exceeded(9_800, 0, 0.03)
