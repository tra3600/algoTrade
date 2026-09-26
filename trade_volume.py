"""Sélection de l'action à trader : la plus échangée du jour, hors « penny stocks ».

L'ancienne version demandait les barres de *toutes* les actions du NASDAQ en une
requête (plusieurs milliers de symboles, avec l'API ``get_barset`` supprimée depuis).
On utilise désormais le « screener » d'Alpaca, qui renvoie directement les plus actives.
"""


def choisir(candidats, prix, prix_min=5.0, exclure=()):
    """Premier symbole (candidats triés par volume décroissant) dont le prix ≥ prix_min.

    candidats : liste de (symbole, volume) ; prix : dict symbole -> dernier prix.
    """
    for symbole, _volume in sorted(candidats, key=lambda c: -c[1]):
        if symbole in exclure:
            continue
        if prix.get(symbole, 0.0) >= prix_min:
            return symbole
    return None


def plus_actives(config, top=20):
    """[(symbole, volume), ...] selon le screener Alpaca."""
    from alpaca.data.historical.screener import ScreenerClient
    from alpaca.data.requests import MostActivesRequest

    client = ScreenerClient(config.api_key, config.secret_key)
    res = client.get_most_actives(MostActivesRequest(top=top))
    return [(a.symbol, a.volume) for a in res.most_actives]


def derniers_prix(config, symboles):
    from alpaca.data.enums import DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockLatestTradeRequest

    client = StockHistoricalDataClient(config.api_key, config.secret_key)
    trades = client.get_stock_latest_trade(
        StockLatestTradeRequest(symbol_or_symbols=list(symboles), feed=DataFeed.IEX))
    return {s: float(t.price) for s, t in trades.items()}


def select_stock(config, prix_min=5.0, top=20):
    """Point d'entrée conservé : renvoie le symbole retenu (ou None)."""
    candidats = plus_actives(config, top)
    return choisir(candidats, derniers_prix(config, [s for s, _ in candidats]), prix_min)
