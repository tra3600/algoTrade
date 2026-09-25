from types import SimpleNamespace

import pytest
from alpaca.common.exceptions import APIError
from alpaca.trading.enums import OrderClass, OrderSide

from algotrade.bot import TradingBot
from algotrade.config import Settings
from algotrade.selection import select_stock
from algotrade.strategy import Signal

UP_CROSS = [10.0] * 4 + [9.0, 12.0]
DOWN_CROSS = [10.0] * 4 + [11.0, 8.0]


class FakeTrading:
    def __init__(self, is_open=True, position_qty=0, equity=10_000, last_equity=10_000):
        self.is_open = is_open
        self.position_qty = position_qty
        self.account = SimpleNamespace(equity=str(equity), last_equity=str(last_equity), buying_power="20000")
        self.orders, self.cancelled, self.closed = [], [], []

    def get_clock(self):
        return SimpleNamespace(is_open=self.is_open)

    def get_account(self):
        return self.account

    def get_open_position(self, symbol):
        if not self.position_qty:
            raise APIError("position does not exist")
        return SimpleNamespace(qty=str(self.position_qty))

    def submit_order(self, req):
        self.orders.append(req)

    def get_orders(self, req):
        return [SimpleNamespace(id="leg-1"), SimpleNamespace(id="leg-2")]

    def cancel_order_by_id(self, order_id):
        self.cancelled.append(order_id)

    def close_position(self, symbol):
        self.closed.append(symbol)


class FakeData:
    def __init__(self, closes):
        self.closes = closes

    def get_stock_bars(self, req):
        return SimpleNamespace(data={"AAPL": [SimpleNamespace(close=c) for c in self.closes]})


def make_bot(closes, dry_run=False, **trading_kwargs):
    settings = Settings(api_key="k", secret_key="s", dry_run=dry_run, short_window=2, long_window=4)
    trading = FakeTrading(**trading_kwargs)
    return TradingBot(settings, trading, FakeData(closes), "AAPL"), trading


def test_achat_bracket_sur_croisement_haussier():
    bot, trading = make_bot(UP_CROSS)
    assert bot.run_once() is Signal.BUY
    order = trading.orders[0]
    assert order.side == OrderSide.BUY
    assert order.order_class == OrderClass.BRACKET
    assert order.qty == 83  # 10% de 10 000 $ / 12 $
    assert order.stop_loss.stop_price == pytest.approx(11.88)
    assert order.take_profit.limit_price == pytest.approx(12.24)


def test_pas_de_rachat_si_deja_en_position():
    bot, trading = make_bot(UP_CROSS, position_qty=10)
    assert bot.run_once() is Signal.HOLD
    assert trading.orders == []


def test_vente_annule_les_jambes_puis_ferme():
    bot, trading = make_bot(DOWN_CROSS, position_qty=10)
    assert bot.run_once() is Signal.SELL
    assert trading.cancelled == ["leg-1", "leg-2"]
    assert trading.closed == ["AAPL"]


def test_marche_ferme():
    bot, trading = make_bot(UP_CROSS, is_open=False)
    assert bot.run_once() is Signal.HOLD
    assert trading.orders == []


def test_simulation_n_envoie_aucun_ordre():
    bot, trading = make_bot(UP_CROSS, dry_run=True)
    assert bot.run_once() is Signal.BUY
    assert trading.orders == []


def test_perte_journaliere_max_ferme_la_position():
    bot, trading = make_bot(UP_CROSS, position_qty=10, equity=9_500, last_equity=10_000)
    assert bot.run_once() is Signal.SELL
    assert trading.closed == ["AAPL"]
    assert trading.orders == []


def test_selection_par_volume_et_prix():
    actives = [
        SimpleNamespace(symbol="PENNY", volume=900),
        SimpleNamespace(symbol="BIG", volume=800),
        SimpleNamespace(symbol="AAPL", volume=700),
    ]
    screener = SimpleNamespace(get_most_actives=lambda req: SimpleNamespace(most_actives=actives))
    prices = {"PENNY": 0.5, "BIG": 900.0, "AAPL": 200.0}
    data = SimpleNamespace(get_stock_latest_trade=lambda req: {s: SimpleNamespace(price=p) for s, p in prices.items()})
    assert select_stock(screener, data, min_price=5, max_price=500) == "AAPL"


def test_config_invalide():
    with pytest.raises(ValueError):
        Settings(api_key="k", secret_key="s", short_window=5, long_window=5)
