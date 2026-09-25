"""Point d'entree : python -m algotrade {account,select,run,backtest}"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timedelta, timezone

from .backtest import backtest
from .config import Settings


def _clients(settings: Settings):
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.historical.screener import ScreenerClient
    from alpaca.trading.client import TradingClient

    return (
        TradingClient(settings.api_key, settings.secret_key, paper=settings.paper),
        StockHistoricalDataClient(settings.api_key, settings.secret_key),
        ScreenerClient(settings.api_key, settings.secret_key),
    )


def _resolve_symbol(settings: Settings, data, screener) -> str:
    from .selection import select_stock

    symbol = settings.symbol or select_stock(screener, data, settings.min_price, settings.max_price, feed=settings.data_feed)
    if not symbol:
        raise SystemExit("Aucune action ne correspond aux criteres")
    return symbol


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="algotrade", description="Bot de trading Alpaca")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("account", help="Affiche l'etat du compte")
    sub.add_parser("select", help="Affiche l'action qui serait selectionnee")
    sub.add_parser("run", help="Lance le bot")
    bt = sub.add_parser("backtest", help="Teste la strategie sur l'historique")
    bt.add_argument("--days", type=int, default=5, help="Nombre de jours de bougies 1 minute")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = Settings.from_env()
    trading, data, screener = _clients(settings)

    if args.command == "account":
        account = trading.get_account()
        print(f"Compte {'paper' if settings.paper else 'REEL'} : capital={account.equity} pouvoir_achat={account.buying_power}")
    elif args.command == "select":
        print(_resolve_symbol(settings, data, screener))
    elif args.command == "run":
        from .bot import TradingBot

        TradingBot(settings, trading, data, _resolve_symbol(settings, data, screener)).run()
    elif args.command == "backtest":
        from alpaca.data.enums import DataFeed
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        symbol = _resolve_symbol(settings, data, screener)
        bars = data.get_stock_bars(
            StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame.Minute,
                start=datetime.now(timezone.utc) - timedelta(days=args.days),
                feed=DataFeed(settings.data_feed),
            )
        )
        closes = [b.close for b in bars.data.get(symbol, [])]
        result = backtest(closes, settings.short_window, settings.long_window, settings.stop_loss_pct, settings.take_profit_pct)
        print(f"{symbol} sur {len(closes)} bougies : {result.summary()}")


if __name__ == "__main__":
    main()
