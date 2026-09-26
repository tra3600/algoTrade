"""Sources de données : marchés simulés (sans clé API), fichiers CSV, ou Alpaca."""

import numpy as np
import pandas as pd

BARRES_PAR_JOUR = 390  # une séance américaine = 6h30 de barres d'une minute

SCENARIOS = {
    "haussier": "tendance de fond à la hausse, par vagues",
    "baissier": "tendance de fond à la baisse, par vagues",
    "lateral": "prix qui oscille autour d'une valeur sans tendance",
    "volatil": "pas de tendance, mais de fortes secousses",
    "krach": "montée tranquille puis chute brutale",
}


def generer_marche(scenario="haussier", jours=5, prix_initial=100.0, graine=0):
    """Barres d'une minute (open/high/low/close/volume) pour un scénario de marché."""
    if scenario not in SCENARIOS:
        raise ValueError(f"Scénario inconnu : {scenario}. Choix : {', '.join(SCENARIOS)}")
    rng = np.random.default_rng(graine)
    n = jours * BARRES_PAR_JOUR
    vol = 0.0012
    # Tendances par « vagues » : la dérive change de régime toutes les ~90 minutes.
    regimes = np.repeat(rng.normal(0, 1, n // 90 + 1), 90)[:n]
    if scenario == "haussier":
        derive = 0.00008 + 0.00015 * regimes
    elif scenario == "baissier":
        derive = -0.00008 + 0.00015 * regimes
    elif scenario == "volatil":
        derive, vol = 0.00015 * regimes, 0.0035
    elif scenario == "krach":
        derive = np.where(np.arange(n) < 0.7 * n, 0.00008, -0.0005) + 0.00015 * regimes
    else:
        derive = np.zeros(n)

    rendements = derive + vol * rng.standard_normal(n)
    if scenario == "lateral":
        # Processus de retour à la moyenne (Ornstein-Uhlenbeck) sur le log-prix.
        log_p = np.empty(n)
        x = 0.0
        for i in range(n):
            x += -0.02 * x + vol * rng.standard_normal()
            log_p[i] = x
        close = prix_initial * np.exp(log_p)
    else:
        close = prix_initial * np.exp(np.cumsum(rendements))

    open_ = np.concatenate([[prix_initial], close[:-1]])
    amplitude = np.abs(rng.normal(0, vol / 2, n)) * close
    high = np.maximum(open_, close) + amplitude
    low = np.minimum(open_, close) - amplitude
    volume = rng.integers(5_000, 50_000, n)
    index = _index_minutes(jours)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                         "volume": volume}, index=index)


def _index_minutes(jours):
    jours_ouvres = pd.bdate_range("2026-01-05", periods=jours)
    return pd.DatetimeIndex([j + pd.Timedelta(hours=9, minutes=30 + m)
                             for j in jours_ouvres for m in range(BARRES_PAR_JOUR)])


def charger_csv(chemin):
    """CSV avec au moins une colonne 'close' (et idéalement open/high/low/volume, un index date)."""
    df = pd.read_csv(chemin, index_col=0, parse_dates=True)
    df.columns = [c.lower() for c in df.columns]
    if "close" not in df:
        raise ValueError("Le CSV doit contenir une colonne 'close'.")
    for col in ("open", "high", "low"):
        if col not in df:
            df[col] = df["close"]
    if "volume" not in df:
        df["volume"] = 0
    return df[["open", "high", "low", "close", "volume"]].dropna()


def charger_alpaca(config, symbole, jours=5, minutes_par_barre=1):
    """Historique réel via l'API de données Alpaca (flux IEX, gratuit)."""
    from alpaca.data.enums import DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    client = StockHistoricalDataClient(config.api_key, config.secret_key)
    fin = pd.Timestamp.now(tz="America/New_York")
    requete = StockBarsRequest(
        symbol_or_symbols=symbole,
        timeframe=TimeFrame(minutes_par_barre, TimeFrameUnit.Minute),
        start=fin - pd.Timedelta(days=jours), end=fin, feed=DataFeed.IEX)
    df = client.get_stock_bars(requete).df
    if df.empty:
        raise ValueError(f"Aucune donnée pour {symbole}.")
    if isinstance(df.index, pd.MultiIndex):
        df = df.xs(symbole, level="symbol")
    return df[["open", "high", "low", "close", "volume"]]
