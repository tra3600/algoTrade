"""Analyses : que vaut une stratégie quand on change les frais, les réglages, la graine, le marché ?

Un seul backtest ne prouve rien : le hasard peut faire gagner une mauvaise stratégie
ou perdre une bonne. Ces outils répètent l'expérience (Monte-Carlo), séparent
l'apprentissage du test (surapprentissage) et mesurent la sensibilité aux coûts.
"""

import numpy as np

from backtest import backtester
from donnees import generer_marche
from scalp_strategy import ParametresStrategie


def monte_carlo(scenario, strategie, graines, jours=5, frais=0.0005, glissement=0.0002,
                fraction=1.0, capital=10_000.0):
    """Rejoue la stratégie sur autant de marchés simulés que de graines.

    Retourne un dict de tableaux numpy : rendement, buy_and_hold, drawdown, transactions."""
    rend, bh, dd, nt = [], [], [], []
    for g in graines:
        df = generer_marche(scenario, jours=jours, graine=g)
        r = backtester(df, strategie, capital=capital, frais=frais, glissement=glissement,
                       fraction=fraction)
        rend.append(r.rendement_total)
        bh.append(r.rendement_buy_and_hold)
        dd.append(r.drawdown_max)
        nt.append(len(r.transactions))
    return {"rendement": np.array(rend), "buy_and_hold": np.array(bh),
            "drawdown": np.array(dd), "transactions": np.array(nt)}


def resume_monte_carlo(mc):
    """Moyenne, médiane, quantiles et probabilités à partir de ``monte_carlo``."""
    r = mc["rendement"]
    return {
        "moyenne": float(r.mean()), "mediane": float(np.median(r)),
        "p5": float(np.percentile(r, 5)), "p95": float(np.percentile(r, 95)),
        "pire": float(r.min()), "meilleur": float(r.max()),
        "proba_gain": float(np.mean(r > 0)),
        "proba_battre_bh": float(np.mean(r > mc["buy_and_hold"])),
        "drawdown_moyen": float(mc["drawdown"].mean()),
        "transactions": float(mc["transactions"].mean()),
    }


def matrice_strategies(scenarios, strategies, graines, jours=5, **kw):
    """Rendement moyen de chaque stratégie (dict nom -> stratégie) dans chaque scénario.

    Retourne (matrice [scénarios × stratégies], buy_and_hold moyen par scénario)."""
    m = np.zeros((len(scenarios), len(strategies)))
    bh = np.zeros(len(scenarios))
    for i, s in enumerate(scenarios):
        for j, strat in enumerate(strategies.values()):
            mc = monte_carlo(s, strat, graines, jours, **kw)
            m[i, j] = mc["rendement"].mean()
            bh[i] = mc["buy_and_hold"].mean()
    return m, bh


def balayage_frais(df, strategie, frais_liste, glissement=0.0002):
    """Rendement total pour chaque niveau de frais (fraction par ordre)."""
    return [backtester(df, strategie, frais=f, glissement=glissement).rendement_total
            for f in frais_liste]


def frais_equilibre(df, strategie, glissement=0.0002, frais_max=0.01, iterations=30):
    """Frais par ordre pour lesquels la stratégie passe de gagnante à perdante.

    Retourne 0.0 si elle perd même sans frais, ``inf`` si elle gagne encore à ``frais_max``."""
    if backtester(df, strategie, frais=0, glissement=glissement).rendement_total <= 0:
        return 0.0
    if backtester(df, strategie, frais=frais_max, glissement=glissement).rendement_total > 0:
        return float("inf")
    bas, haut = 0.0, frais_max
    for _ in range(iterations):
        milieu = (bas + haut) / 2
        if backtester(df, strategie, frais=milieu, glissement=glissement).rendement_total > 0:
            bas = milieu
        else:
            haut = milieu
    return (bas + haut) / 2


def grille_mm(df, courts, longs, stop_loss=0.01, take_profit=0.02, **kw):
    """Rendement du croisement MM pour chaque couple (court, long) ; NaN si court ≥ long."""
    g = np.full((len(courts), len(longs)), np.nan)
    for i, c in enumerate(courts):
        for j, l in enumerate(longs):
            if c < l:
                g[i, j] = backtester(df, ParametresStrategie(c, l, stop_loss, take_profit),
                                     **kw).rendement_total
    return g


def meilleur_couple(grille, courts, longs):
    i, j = np.unravel_index(np.nanargmax(grille), grille.shape)
    return courts[i], longs[j], float(grille[i, j])


def optimiser_puis_tester(scenario, graine, courts, longs, jours=6, **kw):
    """Surapprentissage : on choisit le meilleur réglage sur la 1re moitié du marché,
    puis on le juge sur la 2e (jamais vue) et on le compare au réglage par défaut 5/20."""
    df = generer_marche(scenario, jours=jours, graine=graine)
    milieu = len(df) // 2
    apprentissage, test = df.iloc[:milieu], df.iloc[milieu:]
    g = grille_mm(apprentissage, courts, longs, **kw)
    c, l, dans_echantillon = meilleur_couple(g, courts, longs)
    hors = backtester(test, ParametresStrategie(c, l), **kw).rendement_total
    defaut = backtester(test, ParametresStrategie(), **kw).rendement_total
    return {"court": c, "long": l, "dans_echantillon": dans_echantillon,
            "hors_echantillon": hors, "defaut_hors_echantillon": defaut,
            "buy_and_hold_test": backtester(test, ParametresStrategie(), **kw).rendement_buy_and_hold}


def kelly(taux_reussite, gain_moyen, perte_moyenne):
    """Fraction de Kelly : part du capital à engager pour maximiser la croissance.

    Pour un trade qui gagne ``gain_moyen`` (en rendement, ex. 0,014) avec probabilité p et
    perd ``perte_moyenne`` sinon : f* = p / perte − (1 − p) / gain. Si la perte est de 100 %
    de la mise, on retrouve la formule classique p − (1 − p)/b. Négative : espérance
    négative, il ne faut pas jouer ; supérieure à 1 : l'avantage mesuré dépasse le risque
    par trade (ce qui doit rendre prudent sur son estimation)."""
    perte_moyenne, gain_moyen = abs(perte_moyenne), abs(gain_moyen)
    if gain_moyen == 0 or perte_moyenne == 0:
        raise ValueError("gain_moyen et perte_moyenne doivent être non nuls")
    return float(taux_reussite / perte_moyenne - (1 - taux_reussite) / gain_moyen)


def rendement_par_regime(res, df):
    """Gain de la stratégie (en $) et du marché dans chaque régime d'un scénario « regimes »."""
    labels = df.attrs["regimes"]
    eq = res.equity.to_numpy()
    px = df["close"].to_numpy()
    sortie = {}
    for nom in dict.fromkeys(labels):
        idx = np.where(labels == nom)[0]
        gain = sum(eq[i] - eq[i - 1] for i in idx if i > 0)
        marche = sum(px[i] / px[i - 1] - 1 for i in idx if i > 0)
        sortie[nom] = {"gain": float(gain), "marche": float(marche), "barres": len(idx)}
    return sortie
