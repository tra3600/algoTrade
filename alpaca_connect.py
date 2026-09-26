"""Connexion au courtier.

Deux courtiers avec la même interface :
- ``CourtierAlpaca`` : le vrai (SDK officiel alpaca-py ; compte de démonstration par défaut) ;
- ``CourtierSimule`` : rejoue des barres (simulées ou historiques) sans rien envoyer.
Le bot ne voit que cette interface : on peut le tester entièrement hors ligne.
"""

from dataclasses import dataclass

import pandas as pd


@dataclass
class Position:
    quantite: int = 0
    prix_moyen: float = 0.0


class CourtierAlpaca:
    def __init__(self, config):
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.trading.client import TradingClient

        self.config = config
        self.trading = TradingClient(config.api_key, config.secret_key, paper=config.paper)
        self.donnees = StockHistoricalDataClient(config.api_key, config.secret_key)

    def compte(self):
        c = self.trading.get_account()
        return {"statut": str(c.status), "capital": float(c.equity), "liquidites": float(c.cash),
                "pouvoir_achat": float(c.buying_power),
                "mode": "démonstration (paper)" if self.config.paper else "RÉEL"}

    def marche_ouvert(self):
        return bool(self.trading.get_clock().is_open)

    def position(self, symbole):
        from alpaca.common.exceptions import APIError
        try:
            p = self.trading.get_open_position(symbole)
        except APIError:
            return Position()  # l'API répond 404 quand on ne détient rien
        return Position(int(float(p.qty)), float(p.avg_entry_price))

    def dernieres_barres(self, symbole, n):
        from alpaca.data.enums import DataFeed
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        fin = pd.Timestamp.now(tz="America/New_York")
        req = StockBarsRequest(symbol_or_symbols=symbole, timeframe=TimeFrame.Minute,
                               start=fin - pd.Timedelta(days=3), end=fin, feed=DataFeed.IEX)
        df = self.donnees.get_stock_bars(req).df
        if df.empty:
            return df
        if isinstance(df.index, pd.MultiIndex):
            df = df.xs(symbole, level="symbol")
        return df.tail(n)

    def acheter(self, symbole, quantite):
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import MarketOrderRequest

        return self.trading.submit_order(MarketOrderRequest(
            symbol=symbole, qty=quantite, side=OrderSide.BUY, time_in_force=TimeInForce.DAY))

    def vendre(self, symbole, quantite):
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import MarketOrderRequest

        return self.trading.submit_order(MarketOrderRequest(
            symbol=symbole, qty=quantite, side=OrderSide.SELL, time_in_force=TimeInForce.DAY))


class CourtierSimule:
    """Avance d'une barre à chaque appel de ``dernieres_barres`` ; exécute au dernier cours."""

    def __init__(self, df, capital=10_000.0, depart=30, frais=0.0005, glissement=0.0002):
        self.df = df
        self.frais, self.glissement = frais, glissement
        self.i = depart
        self.liquidites = capital
        self.pos = Position()
        self.ordres = []

    def compte(self):
        prix = float(self.df["close"].iloc[min(self.i, len(self.df)) - 1])
        return {"statut": "SIMULÉ", "capital": self.liquidites + self.pos.quantite * prix,
                "liquidites": self.liquidites, "pouvoir_achat": self.liquidites,
                "mode": "simulation locale"}

    def marche_ouvert(self):
        return self.i < len(self.df)

    def position(self, symbole):
        return Position(self.pos.quantite, self.pos.prix_moyen)

    def dernieres_barres(self, symbole, n):
        self.i += 1
        return self.df.iloc[max(0, self.i - n): self.i]

    def _prix(self):
        return float(self.df["close"].iloc[self.i - 1])

    def acheter(self, symbole, quantite):
        prix = self._prix() * (1 + self.glissement)
        self.liquidites -= quantite * prix * (1 + self.frais)
        total = self.pos.quantite + quantite
        self.pos = Position(total, (self.pos.prix_moyen * self.pos.quantite + prix * quantite) / total)
        self.ordres.append(("achat", symbole, quantite, prix))

    def vendre(self, symbole, quantite):
        prix = self._prix() * (1 - self.glissement)
        self.liquidites += quantite * prix * (1 - self.frais)
        self.pos = Position(self.pos.quantite - quantite, self.pos.prix_moyen if self.pos.quantite > quantite else 0.0)
        self.ordres.append(("vente", symbole, quantite, prix))
