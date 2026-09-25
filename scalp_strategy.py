"""Boucle de trading en temps réel (scalping EMA/RSI/ATR, positions longues uniquement).

Améliorations par rapport à la version initiale :
- n'achète que si aucune position n'est ouverte (plus d'achats répétés chaque minute) ;
- ne vend que la position détenue (plus de vente à découvert involontaire) ;
- ordres « bracket » avec stop-loss et take-profit côté serveur ;
- taille de position calculée selon le risque et le capital ;
- respect des horaires de marché, clôture des positions avant la fin de séance ;
- limite de perte journalière et de nombre de trades ;
- mode simulation (dry-run) et journalisation.
"""
import logging
import time
from datetime import datetime, timezone

from alpaca.common.exceptions import APIError
from alpaca.trading.enums import OrderClass, OrderSide, QueryOrderStatus, TimeInForce
from alpaca.trading.requests import (
    GetOrdersRequest,
    MarketOrderRequest,
    StopLossRequest,
    TakeProfitRequest,
)

from config import Config
from market_data import get_recent_bars
from signals import Signal, compute_indicators, generate_signal, plan_trade
from trade_volume import select_stock

log = logging.getLogger(__name__)


class ScalpTrader:
    def __init__(self, clients, cfg: Config, symbol: str | None = None):
        self.clients = clients
        self.cfg = cfg
        self.s = cfg.strategy
        self.fixed_symbol = symbol
        self.symbol = symbol
        self.trading_day = None
        self.trades_today = 0
        self.halted_today = False

    # ------------------------------------------------------------------ utilitaires
    def _position(self):
        try:
            return self.clients.trading.get_open_position(self.symbol)
        except APIError:
            return None

    def _open_orders(self):
        return self.clients.trading.get_orders(
            GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[self.symbol])
        )

    def _cancel_symbol_orders(self) -> None:
        for order in self._open_orders():
            try:
                self.clients.trading.cancel_order_by_id(order.id)
            except APIError as e:
                log.warning("Annulation impossible de l'ordre %s : %s", order.id, e)

    def flatten(self, reason: str) -> None:
        """Annule les ordres en attente et clôture la position sur le symbole."""
        if not self.symbol:
            return
        position = self._position()
        if position is None:
            return
        log.info("Clôture de %s (%s) : %s", self.symbol, position.qty, reason)
        if self.cfg.dry_run:
            return
        self._cancel_symbol_orders()
        time.sleep(1)  # laisser Alpaca libérer la quantité bloquée par les ordres stop/limit
        try:
            self.clients.trading.close_position(self.symbol)
        except APIError as e:
            log.error("Échec de la clôture de %s : %s", self.symbol, e)

    # ------------------------------------------------------------------ gestion journalière
    def _new_day(self, today) -> None:
        self.trading_day = today
        self.trades_today = 0
        self.halted_today = False
        if not self.fixed_symbol and (self.symbol is None or self._position() is None):
            self.symbol = select_stock(self.clients, self.cfg)
        log.info("Nouvelle séance %s — symbole : %s", today, self.symbol)

    def _daily_loss_exceeded(self, account) -> bool:
        last_equity = float(account.last_equity)
        pnl = float(account.equity) - last_equity
        return last_equity > 0 and pnl <= -self.s.max_daily_loss_pct * last_equity

    # ------------------------------------------------------------------ une itération
    def step(self) -> None:
        clock = self.clients.trading.get_clock()
        if not clock.is_open:
            return

        today = clock.timestamp.date()
        if today != self.trading_day:
            self._new_day(today)
        if not self.symbol:
            log.warning("Aucun symbole éligible.")
            return

        minutes_to_close = (clock.next_close - clock.timestamp).total_seconds() / 60
        if minutes_to_close <= self.s.flatten_before_close_min:
            self.flatten("fin de séance")
            return

        account = self.clients.trading.get_account()
        if not self.halted_today and self._daily_loss_exceeded(account):
            self.halted_today = True
            log.warning("Perte journalière maximale atteinte : arrêt du trading pour aujourd'hui.")
            self.flatten("limite de perte journalière")
        if self.halted_today:
            return

        bars = get_recent_bars(self.clients.data, self.symbol, self.s.timeframe_minutes,
                               self.s.lookback_bars, feed=self.cfg.data_feed)
        ind = compute_indicators(bars, self.s)
        position = self._position()
        signal = generate_signal(ind, self.s, in_position=position is not None)
        last = ind.iloc[-1] if len(ind) else None
        if last is not None:
            log.info("%s close=%.2f ema%d=%.2f ema%d=%.2f rsi=%.1f -> %s", self.symbol, last["close"],
                     self.s.ema_fast, last["ema_fast"], self.s.ema_slow, last["ema_slow"],
                     last["rsi"], signal.value)

        if signal == Signal.SELL and position is not None:
            self.flatten("signal de sortie")
        elif signal == Signal.BUY and position is None:
            self._enter(ind, account, minutes_to_close)

    def _enter(self, ind, account, minutes_to_close: float) -> None:
        if minutes_to_close <= self.s.no_new_entries_before_close_min:
            log.info("Trop proche de la clôture : pas de nouvelle entrée.")
            return
        if self.trades_today >= self.s.max_trades_per_day:
            log.info("Nombre maximal de trades atteint pour aujourd'hui.")
            return
        if self._open_orders():
            log.info("Ordres déjà en attente sur %s : entrée ignorée.", self.symbol)
            return

        last = ind.iloc[-1]
        plan = plan_trade(float(last["close"]), float(last["atr"]), float(account.equity), self.s)
        if plan is None:
            log.info("Trade non viable (taille ou stop invalide).")
            return
        buying_power = float(account.buying_power)
        if plan.qty * plan.entry > buying_power:
            plan.qty = int(buying_power // plan.entry)
            if plan.qty < 1:
                log.info("Pouvoir d'achat insuffisant.")
                return

        log.info("ACHAT %d %s ~%.2f | stop %.2f | objectif %.2f", plan.qty, self.symbol,
                 plan.entry, plan.stop_loss, plan.take_profit)
        self.trades_today += 1
        if self.cfg.dry_run:
            return
        try:
            self.clients.trading.submit_order(MarketOrderRequest(
                symbol=self.symbol,
                qty=plan.qty,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
                order_class=OrderClass.BRACKET,
                take_profit=TakeProfitRequest(limit_price=plan.take_profit),
                stop_loss=StopLossRequest(stop_price=plan.stop_loss),
            ))
        except APIError as e:
            log.error("Ordre refusé : %s", e)

    # ------------------------------------------------------------------ boucle principale
    def _sleep_until_next_bar(self) -> None:
        period = self.s.timeframe_minutes * 60
        now = datetime.now(timezone.utc).timestamp()
        # Se réveiller 3 s après la clôture de la bougie pour que les données soient disponibles
        delay = period - (now % period) + 3
        time.sleep(max(delay, 1))

    def run(self, flatten_on_exit: bool = True) -> None:
        log.info("Démarrage (%s%s)", "paper" if self.cfg.paper else "RÉEL",
                 ", dry-run" if self.cfg.dry_run else "")
        try:
            while True:
                try:
                    clock = self.clients.trading.get_clock()
                    if not clock.is_open:
                        wait = (clock.next_open - clock.timestamp).total_seconds()
                        log.info("Marché fermé. Réouverture : %s", clock.next_open)
                        time.sleep(min(max(wait, 30), 30 * 60))
                        continue
                    self.step()
                except APIError as e:
                    log.error("Erreur API : %s", e)
                except Exception:  # ne jamais laisser la boucle mourir sur une erreur réseau
                    log.exception("Erreur inattendue")
                self._sleep_until_next_bar()
        except KeyboardInterrupt:
            log.info("Arrêt demandé.")
            if flatten_on_exit:
                self.flatten("arrêt du programme")


def scalping_strategy(clients, cfg: Config, symbol: str | None = None) -> None:
    ScalpTrader(clients, cfg, symbol).run()
