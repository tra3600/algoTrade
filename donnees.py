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


# Les 5 scénarios d'origine (ceux des cas illustrés) puis des marchés plus subtils.
SCENARIOS_ETENDUS = {
    **SCENARIOS,
    "regimes": "alternance de tendances et de marchés sans direction (une demi-journée chacun)",
    "rebond": "chute de 40 % du temps, puis remontée en V",
    "vague": "oscillation régulière d'une demi-heure : le terrain du retour à la moyenne",
    "bulle": "accélération de plus en plus folle, puis éclatement",
    "gaps": "tendance haussière, mais chaque matin le marché ouvre sur un écart (gap)",
}


def generer_marche(scenario="haussier", jours=5, prix_initial=100.0, graine=0, periode_vague=30):
    """Barres d'une minute (open/high/low/close/volume) pour un scénario de marché.

    Pour le scénario « regimes », ``df.attrs["regimes"]`` donne le régime de chaque
    barre (« tendance haussière », « sans direction », « tendance baissière »).
    Pour « vague », ``periode_vague`` est la période de l'oscillation en minutes : la même
    oscillation est un retour à la moyenne à l'échelle d'une demi-heure et une tendance
    à l'échelle de quelques heures."""
    if scenario not in SCENARIOS_ETENDUS:
        raise ValueError(f"Scénario inconnu : {scenario}. Choix : {', '.join(SCENARIOS_ETENDUS)}")
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
    elif scenario == "rebond":
        derive = np.where(np.arange(n) < 0.4 * n, -0.0004, 0.0004) + 0.00015 * regimes
    elif scenario == "bulle":
        k = np.arange(n)
        fin_bulle = int(0.8 * n)
        derive = np.where(k < fin_bulle, 0.00002 * np.exp(4.0 * k / fin_bulle), -0.0012)
    elif scenario == "gaps":
        derive = 0.00012 + 0.00015 * regimes
    else:                       # lateral, regimes, vague : prix construit plus bas
        derive = np.zeros(n)

    rendements = derive + vol * rng.standard_normal(n)
    ecart_ouverture = np.zeros(n)        # écart entre la clôture précédente et l'ouverture
    labels = None
    if scenario == "lateral":
        # Processus de retour à la moyenne (Ornstein-Uhlenbeck) sur le log-prix.
        log_p = np.empty(n)
        x = 0.0
        for i in range(n):
            x += -0.02 * x + vol * rng.standard_normal()
            log_p[i] = x
        close = prix_initial * np.exp(log_p)
    elif scenario == "vague":
        # Une oscillation sinusoïdale de ±0,4 % plus un bruit qui revient vite à zéro.
        k = np.arange(n)
        bruit, x = np.empty(n), 0.0
        for i in range(n):
            x += -0.3 * x + 0.0005 * rng.standard_normal()
            bruit[i] = x
        close = prix_initial * np.exp(0.004 * np.sin(2 * np.pi * k / periode_vague) + bruit)
    elif scenario == "regimes":
        # Demi-journées : tendance haussière, sans direction, tendance baissière, sans direction...
        duree = BARRES_PAR_JOUR // 2
        cycle = ["tendance haussière", "sans direction", "tendance baissière", "sans direction"]
        labels = np.array([cycle[(i // duree) % 4] for i in range(n)])
        log_p, x, ancre = np.empty(n), 0.0, 0.0
        for i in range(n):
            if i % duree == 0:
                ancre = x
            if labels[i] == "tendance haussière":
                x += 0.0004 + vol * rng.standard_normal()
            elif labels[i] == "tendance baissière":
                x += -0.0004 + vol * rng.standard_normal()
            else:
                x += -0.05 * (x - ancre) + vol * rng.standard_normal()
            log_p[i] = x
        close = prix_initial * np.exp(log_p)
    else:
        if scenario == "gaps":
            ecart_ouverture[BARRES_PAR_JOUR::BARRES_PAR_JOUR] = rng.normal(0, 0.01, len(
                ecart_ouverture[BARRES_PAR_JOUR::BARRES_PAR_JOUR]))
            rendements = rendements + ecart_ouverture
        close = prix_initial * np.exp(np.cumsum(rendements))

    open_ = np.concatenate([[prix_initial], close[:-1]]) * np.exp(ecart_ouverture)
    amplitude = np.abs(rng.normal(0, vol / 2, n)) * close
    high = np.maximum(open_, close) + amplitude
    low = np.minimum(open_, close) - amplitude
    volume = rng.integers(5_000, 50_000, n)
    index = _index_minutes(jours)
    df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                       "volume": volume}, index=index)
    if labels is not None:
        df.attrs["regimes"] = labels
    return df


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
