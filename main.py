"""Point d'entrée.

Exemples :
    python main.py account                       # afficher le compte
    python main.py select                        # afficher l'action sélectionnée
    python main.py backtest --symbol AAPL --days 10
    python main.py live --dry-run                # boucle temps réel sans passer d'ordres
    python main.py live --symbol AAPL            # trading (paper par défaut)
"""
import argparse
import logging
from datetime import datetime, timedelta, timezone

from alpaca_connect import get_clients, print_account
from config import Config


def main() -> None:
    parser = argparse.ArgumentParser(description="Algorithme de scalping Alpaca")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("account", help="Afficher les informations du compte")
    sub.add_parser("select", help="Afficher l'action la plus active retenue")

    bt = sub.add_parser("backtest", help="Tester la stratégie sur l'historique")
    bt.add_argument("--symbol", required=True)
    bt.add_argument("--days", type=int, default=10)
    bt.add_argument("--equity", type=float, default=10_000.0)

    live = sub.add_parser("live", help="Lancer le trading en temps réel")
    live.add_argument("--symbol", help="Symbole à trader (sinon : le plus actif du jour)")
    live.add_argument("--dry-run", action="store_true", help="Ne passe aucun ordre")
    live.add_argument("--keep-position-on-exit", action="store_true",
                      help="Ne pas clôturer la position à l'arrêt (Ctrl+C)")

    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    cfg = Config.from_env()
    clients = get_clients(cfg)

    if args.command == "account":
        print_account(clients)

    elif args.command == "select":
        from trade_volume import select_stock
        print(f"Selected stock: {select_stock(clients, cfg)}")

    elif args.command == "backtest":
        from backtest import run_backtest
        from market_data import get_bars

        end = datetime.now(timezone.utc) - timedelta(minutes=16)  # données récentes SIP = abonnement
        start = end - timedelta(days=args.days)
        bars = get_bars(clients.data, args.symbol, cfg.strategy.timeframe_minutes, start, end,
                        feed=cfg.data_feed).get(args.symbol)
        if bars is None or bars.empty:
            raise SystemExit(f"Aucune donnée pour {args.symbol}.")
        bars = bars.tz_convert("America/New_York").between_time("09:30", "15:59")
        result = run_backtest(bars, cfg.strategy, initial_equity=args.equity)
        print(f"Backtest {args.symbol} — {len(bars)} bougies du {bars.index[0]} au {bars.index[-1]}")
        print(result.summary())

    elif args.command == "live":
        from scalp_strategy import ScalpTrader
        cfg.dry_run = args.dry_run
        ScalpTrader(clients, cfg, args.symbol).run(flatten_on_exit=not args.keep_position_on_exit)


if __name__ == "__main__":
    main()
