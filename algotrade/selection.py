"""Selection de l'action a trader : la plus echangee (en volume) dans une fourchette de prix."""

from __future__ import annotations

import logging

from alpaca.data.enums import DataFeed, MostActivesBy
from alpaca.data.requests import MostActivesRequest, StockLatestTradeRequest

log = logging.getLogger(__name__)


def select_stock(screener, data_client, min_price: float, max_price: float, top: int = 20, feed: str = "iex") -> str | None:
    actives = screener.get_most_actives(MostActivesRequest(top=top, by=MostActivesBy.VOLUME)).most_actives
    if not actives:
        return None
    symbols = [a.symbol for a in actives]
    trades = data_client.get_stock_latest_trade(StockLatestTradeRequest(symbol_or_symbols=symbols, feed=DataFeed(feed)))

    # `actives` est deja trie par volume decroissant
    for active in actives:
        trade = trades.get(active.symbol)
        if trade is not None and min_price <= trade.price <= max_price:
            log.info("Action selectionnee : %s (volume=%s, prix=%.2f)", active.symbol, active.volume, trade.price)
            return active.symbol
    return None
