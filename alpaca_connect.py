"""Connexion à Alpaca via la bibliothèque officielle alpaca-py.

(L'ancienne bibliothèque alpaca-trade-api et sa méthode get_barset ne sont plus supportées.)
"""
from dataclasses import dataclass

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.historical.screener import ScreenerClient
from alpaca.trading.client import TradingClient

from config import Config


@dataclass
class AlpacaClients:
    trading: TradingClient
    data: StockHistoricalDataClient
    screener: ScreenerClient


def get_clients(cfg: Config) -> AlpacaClients:
    cfg.validate()
    return AlpacaClients(
        trading=TradingClient(cfg.api_key, cfg.secret_key, paper=cfg.paper),
        data=StockHistoricalDataClient(cfg.api_key, cfg.secret_key),
        screener=ScreenerClient(cfg.api_key, cfg.secret_key),
    )


def print_account(clients: AlpacaClients) -> None:
    account = clients.trading.get_account()
    print(f"Compte        : {account.account_number} ({account.status})")
    print(f"Equity        : {account.equity}")
    print(f"Cash          : {account.cash}")
    print(f"Buying power  : {account.buying_power}")


if __name__ == "__main__":
    print_account(get_clients(Config.from_env()))
