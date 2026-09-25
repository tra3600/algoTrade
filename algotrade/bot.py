"""Boucle de trading : donnees -> signal -> gestion du risque -> ordres."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from alpaca.common.exceptions import APIError
from alpaca.data.enums import DataFeed
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.enums import OrderClass, OrderSide, QueryOrderStatus, TimeInForce
from alpaca.trading.requests import GetOrdersRequest, MarketOrderRequest, StopLossRequest, TakeProfitRequest

from .config import Settings
from .risk import bracket_prices, daily_loss_exceeded, position_size
from .strategy import Signal, crossover_signal, decide

log = logging.getLogger(__name__)


class TradingBot:
    def __init__(self, settings: Settings, trading_client, data_client, symbol: str):
        self.settings = settings
        self.trading = trading_client
        self.data = data_client
        self.symbol = symbol

    # --- lecture ---------------------------------------------------------

    def fetch_closes(self) -> list[float]:
        s = self.settings
        # Marge x3 pour couvrir les minutes sans echange sur le flux IEX
        start = datetime.now(timezone.utc) - timedelta(minutes=(s.long_window + 1) * 3)
        bars = self.data.get_stock_bars(
            StockBarsRequest(
                symbol_or_symbols=self.symbol,
                timeframe=TimeFrame.Minute,
                start=start,
                feed=DataFeed(s.data_feed),
            )
        )
        return [bar.close for bar in bars.data.get(self.symbol, [])]

    def current_position_qty(self) -> float:
        try:
            return float(self.trading.get_open_position(self.symbol).qty)
        except APIError:
            return 0.0  # pas de position ouverte

    # --- actions ---------------------------------------------------------

    def buy(self, price: float) -> None:
        s = self.settings
        account = self.trading.get_account()
        qty = position_size(float(account.equity), float(account.buying_power), price, s.position_fraction)
        if qty < 1:
            log.warning("Capital insuffisant pour acheter 1 action de %s a %.2f", self.symbol, price)
            return
        bracket = bracket_prices(price, s.stop_loss_pct, s.take_profit_pct)
        log.info(
            "ACHAT %d %s ~%.2f (stop=%.2f, objectif=%.2f)%s",
            qty, self.symbol, price, bracket.stop_loss, bracket.take_profit, " [simulation]" if s.dry_run else "",
        )
        if s.dry_run:
            return
        # Ordre "bracket" : stop-loss et take-profit sont portes par le broker,
        # ils restent actifs meme si le bot s'arrete.
        self.trading.submit_order(
            MarketOrderRequest(
                symbol=self.symbol,
                qty=qty,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
                order_class=OrderClass.BRACKET,
                stop_loss=StopLossRequest(stop_price=bracket.stop_loss),
                take_profit=TakeProfitRequest(limit_price=bracket.take_profit),
            )
        )

    def sell_all(self, reason: str) -> None:
        log.info("VENTE de toute la position %s (%s)%s", self.symbol, reason, " [simulation]" if self.settings.dry_run else "")
        if self.settings.dry_run:
            return
        # Les jambes stop/take-profit bloquent les actions : on les annule avant de fermer.
        open_orders = self.trading.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[self.symbol]))
        for order in open_orders:
            self.trading.cancel_order_by_id(order.id)
        self.trading.close_position(self.symbol)

    # --- boucle ----------------------------------------------------------

    def run_once(self) -> Signal:
        """Une iteration. Retourne l'action effectuee."""
        s = self.settings
        if not self.trading.get_clock().is_open:
            log.info("Marche ferme, en attente")
            return Signal.HOLD

        account = self.trading.get_account()
        has_position = self.current_position_qty() > 0
        if daily_loss_exceeded(float(account.equity), float(account.last_equity), s.max_daily_loss_pct):
            log.warning("Perte journaliere max atteinte (%.1f%%) : trading suspendu", s.max_daily_loss_pct * 100)
            if has_position:
                self.sell_all("perte journaliere max")
                return Signal.SELL
            return Signal.HOLD

        closes = self.fetch_closes()
        if len(closes) < s.long_window + 1:
            log.info("Pas assez de donnees (%d bougies)", len(closes))
            return Signal.HOLD

        action = decide(crossover_signal(closes, s.short_window, s.long_window), has_position)
        if action is Signal.BUY:
            self.buy(closes[-1])
        elif action is Signal.SELL:
            self.sell_all("croisement baissier")
        else:
            log.debug("Rien a faire (dernier prix %.2f, position=%s)", closes[-1], has_position)
        return action

    def run(self) -> None:
        log.info(
            "Demarrage sur %s (MM %d/%d, %s, %s)",
            self.symbol, self.settings.short_window, self.settings.long_window,
            "paper" if self.settings.paper else "REEL", "simulation" if self.settings.dry_run else "ordres actifs",
        )
        while True:
            try:
                self.run_once()
            except APIError as err:
                log.error("Erreur API Alpaca : %s", err)
            except Exception:
                log.exception("Erreur inattendue")
            time.sleep(self.settings.interval_seconds)
