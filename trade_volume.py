"""Sélection de l'action à trader : la plus active en volume parmi les titres éligibles."""
import logging

from alpaca.data.requests import MostActivesRequest, StockLatestTradeRequest
from alpaca.data.enums import DataFeed
from alpaca.trading.enums import AssetClass, AssetStatus
from alpaca.trading.requests import GetAssetsRequest

from config import Config

log = logging.getLogger(__name__)


def get_tradable_symbols(trading_client, exchanges) -> set[str]:
    assets = trading_client.get_all_assets(
        GetAssetsRequest(status=AssetStatus.ACTIVE, asset_class=AssetClass.US_EQUITY)
    )
    return {
        a.symbol for a in assets
        if a.tradable and str(getattr(a.exchange, "value", a.exchange)) in exchanges
    }


def select_stock(clients, cfg: Config) -> str | None:
    """Renvoie le symbole le plus échangé (screener Alpaca), filtré par bourse et fourchette de prix."""
    sel = cfg.selection
    most_actives = clients.screener.get_most_actives(MostActivesRequest(top=sel.top_n, by="volume"))
    candidates = [m.symbol for m in most_actives.most_actives]
    if not candidates:
        log.warning("Le screener n'a renvoyé aucun titre.")
        return None

    tradable = get_tradable_symbols(clients.trading, sel.exchanges)
    candidates = [s for s in candidates if s in tradable]
    if not candidates:
        return None

    latest = clients.data.get_stock_latest_trade(
        StockLatestTradeRequest(symbol_or_symbols=candidates, feed=DataFeed(cfg.data_feed))
    )
    # candidates est déjà trié par volume décroissant
    for symbol in candidates:
        trade = latest.get(symbol)
        if trade and sel.min_price <= trade.price <= sel.max_price:
            log.info("Action sélectionnée : %s (prix %.2f)", symbol, trade.price)
            return symbol
    return None


if __name__ == "__main__":
    from alpaca_connect import get_clients

    logging.basicConfig(level=logging.INFO)
    config = Config.from_env()
    print(f"Selected stock: {select_stock(get_clients(config), config)}")
