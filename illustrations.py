"""Figures des cas illustrés (matplotlib). Chaque fonction retourne une figure."""

import matplotlib.pyplot as plt
import numpy as np

import analyses as an
from backtest import backtester
from donnees import SCENARIOS_ETENDUS, generer_marche
from scalp_strategy import ParametresStrategie
from strategies import MMFiltre, RSI, Bollinger, bandes_bollinger, rsi

BLEU, ORANGE, VERT, ROUGE = "#2a78d6", "#eb6834", "#008300", "#e34948"
GRIS, ENCRE, VIOLET, TURQUOISE = "#8a8983", "#0b0b0b", "#7a4fd1", "#1a9aa0"
COULEURS = [BLEU, ORANGE, VERT, ROUGE, VIOLET, TURQUOISE, GRIS]


def _style(ax, grille="y"):
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis=grille, color="#eeeeea")


def fig_marches():
    """Les 10 scénarios de marché (une même graine)."""
    fig, axes = plt.subplots(2, 5, figsize=(14, 5), sharex=True)
    for ax, (nom, desc) in zip(axes.ravel(), SCENARIOS_ETENDUS.items()):
        df = generer_marche(nom, graine=1)
        ax.plot(df["close"].to_numpy(), color=BLEU, lw=1)
        ax.set_title(nom, fontsize=10, fontweight="bold")
        _style(ax)
        ax.tick_params(labelsize=8)
    for ax in axes[1]:
        ax.set_xlabel("minutes", fontsize=8)
    fig.suptitle("Dix marchés simulés (5 jours de barres d'une minute)", fontweight="bold")
    fig.tight_layout()
    return fig


def fig_matrice(matrice, bh, scenarios, noms_strategies):
    """Rendement moyen de chaque stratégie dans chaque marché (carte de chaleur)."""
    fig, ax = plt.subplots(figsize=(10, 6))
    donnees = np.column_stack([matrice, bh])
    lim = max(abs(donnees).max(), 0.05)
    im = ax.imshow(donnees, cmap="RdBu", vmin=-lim, vmax=lim, aspect="auto")
    ax.set_xticks(range(donnees.shape[1]))
    ax.set_xticklabels(list(noms_strategies) + ["acheter et attendre"], rotation=30, ha="right")
    ax.set_yticks(range(len(scenarios)))
    ax.set_yticklabels(scenarios)
    for i in range(donnees.shape[0]):
        for j in range(donnees.shape[1]):
            ax.text(j, i, f"{donnees[i, j]:+.0%}", ha="center", va="center", fontsize=9,
                    color="white" if abs(donnees[i, j]) > 0.6 * lim else ENCRE)
    fig.colorbar(im, ax=ax, label="rendement moyen sur 5 jours")
    ax.set_title("Aucune stratégie ne gagne partout", fontweight="bold")
    fig.tight_layout()
    return fig


def fig_echelle(periodes, resultats):
    """Rendement selon la période de l'oscillation : tendance ou retour à la moyenne ?"""
    fig, ax = plt.subplots(figsize=(9, 5))
    for (nom, valeurs), c in zip(resultats.items(), COULEURS):
        ax.plot(periodes, valeurs, "o-", color=c, label=nom, lw=2)
    ax.axhline(0, color=GRIS, lw=1)
    ax.set_xscale("log")
    ax.set_xlabel("période de l'oscillation (minutes, échelle log)")
    ax.set_ylabel("rendement moyen sur 5 jours")
    ax.set_title("La même oscillation : retour à la moyenne ou tendance, selon l'échelle",
                 fontweight="bold", fontsize=11)
    ax.legend(frameon=False)
    _style(ax)
    fig.tight_layout()
    return fig


def fig_frais(frais, courbes, equilibres):
    """Rendement en fonction des frais par ordre, avec le point d'équilibre."""
    fig, ax = plt.subplots(figsize=(9, 5))
    for (nom, valeurs), c in zip(courbes.items(), COULEURS):
        ax.plot(np.array(frais) * 100, np.array(valeurs) * 100, color=c, lw=2, label=nom)
        eq = equilibres[nom]
        if 0 < eq < frais[-1]:
            ax.scatter([eq * 100], [0], color=c, zorder=3, s=50)
    ax.axhline(0, color=GRIS, lw=1)
    ax.set_xlabel("frais par ordre (%)")
    ax.set_ylabel("rendement sur 5 jours (%)")
    ax.set_title("Les frais font disparaître le gain (points : seuil de rentabilité)",
                 fontweight="bold", fontsize=11)
    ax.legend(frameon=False)
    _style(ax)
    fig.tight_layout()
    return fig


def fig_grille(grilles, courts, longs):
    """Cartes de chaleur court × long pour plusieurs marchés (dict nom -> grille)."""
    fig, axes = plt.subplots(1, len(grilles), figsize=(5.5 * len(grilles), 4.6))
    axes = np.atleast_1d(axes)
    for ax, (nom, g) in zip(axes, grilles.items()):
        lim = max(np.nanmax(abs(g)), 0.02)
        im = ax.imshow(g, cmap="RdBu", vmin=-lim, vmax=lim, aspect="auto")
        ax.set_xticks(range(len(longs)), longs)
        ax.set_yticks(range(len(courts)), courts)
        ax.set_xlabel("MM longue")
        ax.set_ylabel("MM courte")
        c, l, _ = an.meilleur_couple(g, courts, longs)
        ax.scatter([longs.index(l)], [courts.index(c)], marker="*", s=220, color="gold",
                   edgecolor=ENCRE, zorder=3)
        ax.set_title(f"{nom} (★ = meilleur réglage {c}/{l})", fontsize=10, fontweight="bold")
        fig.colorbar(im, ax=ax, shrink=0.8)
    fig.suptitle("Rendement selon les réglages : le meilleur change avec le marché", fontweight="bold")
    fig.tight_layout()
    return fig


def fig_surapprentissage(lignes):
    """Rendement d'un réglage optimisé : dans l'échantillon d'apprentissage vs sur des données neuves."""
    dans = np.array([l["dans_echantillon"] for l in lignes]) * 100
    hors = np.array([l["hors_echantillon"] for l in lignes]) * 100
    defaut = np.array([l["defaut_hors_echantillon"] for l in lignes]) * 100
    fig, (a, b) = plt.subplots(1, 2, figsize=(12, 5))
    lim = [min(dans.min(), hors.min()) - 1, max(dans.max(), hors.max()) + 1]
    a.plot(lim, lim, color=GRIS, ls="--", lw=1, label="même résultat")
    a.scatter(dans, hors, color=BLEU, s=40, zorder=3)
    a.set_xlabel("rendement du réglage optimisé, sur les données d'apprentissage (%)")
    a.set_ylabel("rendement du même réglage sur des données neuves (%)")
    a.axhline(0, color=GRIS, lw=0.8)
    a.legend(frameon=False)
    a.set_title("Optimisé sur le passé, déçu sur l'avenir", fontweight="bold", fontsize=11)
    b.bar([0, 1, 2], [dans.mean(), hors.mean(), defaut.mean()], color=[BLEU, ROUGE, GRIS])
    b.set_xticks([0, 1, 2], ["optimisé\n(apprentissage)", "optimisé\n(données neuves)",
                             "réglage 5/20\n(données neuves)"])
    b.axhline(0, color=ENCRE, lw=0.8)
    b.set_ylabel("rendement moyen (%)")
    b.set_title("Moyenne sur toutes les graines", fontweight="bold", fontsize=11)
    for ax in (a, b):
        _style(ax, "both" if ax is a else "y")
    fig.tight_layout()
    return fig


def fig_monte_carlo(mcs, titre):
    """Histogrammes des rendements sur de nombreuses graines (dict nom -> monte_carlo)."""
    fig, ax = plt.subplots(figsize=(10, 5))
    tous = np.concatenate([m["rendement"] for m in mcs.values()] + [list(mcs.values())[0]["buy_and_hold"]]) * 100
    bins = np.linspace(tous.min(), tous.max(), 36)
    for (nom, mc), c in zip(mcs.items(), COULEURS):
        ax.hist(mc["rendement"] * 100, bins=bins, alpha=0.6, color=c, label=f"{nom} (moy. {mc['rendement'].mean():+.1%})")
    bh = list(mcs.values())[0]["buy_and_hold"]
    ax.hist(bh * 100, bins=bins, histtype="step", color=ENCRE, lw=1.8,
            label=f"acheter et attendre (moy. {bh.mean():+.1%})")
    ax.axvline(0, color=GRIS, lw=1)
    ax.set_xlabel("rendement sur 5 jours (%)")
    ax.set_ylabel("nombre de marchés simulés")
    ax.set_title(titre, fontweight="bold", fontsize=11)
    ax.legend(frameon=False, fontsize=9)
    _style(ax)
    fig.tight_layout()
    return fig


def fig_risque(stops, rend_stop, objectifs, rend_obj, titre):
    fig, (a, b) = plt.subplots(1, 2, figsize=(12, 4.6))
    for ax, x, courbes, lab in ((a, stops, rend_stop, "stop-loss (%)"), (b, objectifs, rend_obj, "take-profit (%)")):
        for (nom, v), c in zip(courbes.items(), COULEURS):
            ax.plot(x, np.array(v) * 100, "o-", color=c, label=nom, lw=2)
        ax.axhline(0, color=GRIS, lw=1)
        ax.set_xlabel(lab)
        ax.set_ylabel("rendement moyen (%)")
        ax.legend(frameon=False, fontsize=9)
        _style(ax)
    fig.suptitle(titre, fontweight="bold")
    fig.tight_layout()
    return fig


def fig_taille(lignes, equities):
    """Rendement et drawdown selon la part du capital engagée, puis les courbes de capital."""
    fig, (a, b) = plt.subplots(1, 2, figsize=(12, 4.8))
    x = [l[0] * 100 for l in lignes]
    a.plot(x, [l[1] * 100 for l in lignes], "o-", color=BLEU, lw=2, label="rendement moyen")
    a.plot(x, [l[2] * 100 for l in lignes], "o-", color=ROUGE, lw=2, label="drawdown moyen")
    a.plot(x, [l[3] * 100 for l in lignes], "o--", color=ROUGE, lw=1.4, alpha=0.6, label="pire drawdown")
    a.axhline(0, color=GRIS, lw=1)
    a.set_xlabel("part du capital engagée à chaque achat (%)")
    a.set_ylabel("%")
    a.legend(frameon=False)
    a.set_title("Gain et risque croissent ensemble", fontweight="bold", fontsize=11)
    for (nom, eq), c in zip(equities.items(), COULEURS):
        b.plot(eq.to_numpy(), color=c, lw=1.6, label=nom)
    b.set_xlabel("barre (minutes)")
    b.set_ylabel("capital ($)")
    b.legend(frameon=False, fontsize=9)
    b.set_title("Même stratégie, tailles de position différentes", fontweight="bold", fontsize=11)
    for ax in (a, b):
        _style(ax)
    fig.tight_layout()
    return fig


def fig_regimes(df, res_mm, res_filtre):
    labels = df.attrs["regimes"]
    couleurs = {"tendance haussière": "#dcefdc", "tendance baissière": "#f8dcdc", "sans direction": "#eeeeea"}
    fig, (a, b) = plt.subplots(2, 1, figsize=(12, 7), sharex=True,
                               gridspec_kw={"height_ratios": [2, 2]})
    debut = 0
    for i in range(1, len(labels) + 1):
        if i == len(labels) or labels[i] != labels[debut]:
            for ax in (a, b):
                ax.axvspan(debut, i, color=couleurs[labels[debut]], lw=0)
            debut = i
    a.plot(df["close"].to_numpy(), color=ENCRE, lw=1)
    a.set_ylabel("prix ($)")
    b.plot(res_mm.equity.to_numpy(), color=ORANGE, lw=2, label=f"MM 5/20 ({res_mm.rendement_total:+.1%})")
    b.plot(res_filtre.equity.to_numpy(), color=BLEU, lw=2, label=f"MM filtrée ({res_filtre.rendement_total:+.1%})")
    b.plot(res_mm.buy_and_hold.to_numpy(), color=GRIS, lw=1.4, ls="--",
           label=f"acheter et attendre ({res_mm.rendement_buy_and_hold:+.1%})")
    b.set_ylabel("capital ($)")
    b.set_xlabel("barre (minutes)")
    b.legend(frameon=False, loc="lower left")
    a.set_title("Vert : tendance haussière — rouge : tendance baissière — gris : sans direction",
                fontsize=10)
    for ax in (a, b):
        _style(ax)
    fig.tight_layout()
    return fig


def fig_anatomie(df, strategie, titre, debut=0, fin=400):
    """Prix, indicateur de la stratégie, achats et ventes sur une portion du marché."""
    res = backtester(df, strategie)
    closes = df["close"].to_numpy()
    x = np.arange(len(df))
    fig, (a, b) = plt.subplots(2, 1, figsize=(12, 6.5), sharex=True,
                               gridspec_kw={"height_ratios": [3, 1.4]})
    a.plot(x, closes, color=GRIS, lw=1, label="prix")
    if isinstance(strategie, Bollinger):
        mu, bas, haut = bandes_bollinger(closes, strategie.fenetre, strategie.k)
        a.plot(x, mu, color=BLEU, lw=1.2, label="moyenne")
        a.fill_between(x, bas, haut, color=BLEU, alpha=0.12, label=f"±{strategie.k:g}σ")
        b.plot(x, (closes - mu) / np.where(haut - mu > 0, (haut - mu) / strategie.k, np.nan), color=VIOLET, lw=1)
        b.axhline(-strategie.k, color=ROUGE, ls="--", lw=1)
        b.axhline(0, color=GRIS, lw=1)
        b.set_ylabel("écart (σ)")
    elif isinstance(strategie, RSI):
        valeurs = [np.nan] * strategie.periode + [rsi(closes[:i + 1], strategie.periode)
                                                 for i in range(strategie.periode, len(closes))]
        b.plot(x, valeurs, color=VIOLET, lw=1)
        b.axhline(strategie.survente, color=ROUGE, ls="--", lw=1)
        b.axhline(strategie.sortie_rsi, color=VERT, ls="--", lw=1)
        b.set_ylabel("RSI")
        b.set_ylim(0, 100)
    else:
        b.plot(x, res.equity.to_numpy(), color=BLEU, lw=1.6)
        b.set_ylabel("capital ($)")
    pos = {d: i for i, d in enumerate(df.index)}
    for t in res.transactions:
        a.scatter(pos[t.entree_date], t.entree_prix, marker="^", s=55, color=ENCRE, zorder=3)
        a.scatter(pos[t.sortie_date], t.sortie_prix, marker="v", s=55,
                  color=VERT if t.gain > 0 else ROUGE, zorder=3)
    a.set_xlim(debut, fin)
    sous = closes[debut:fin]
    a.set_ylim(sous.min() * 0.998, sous.max() * 1.002)
    a.legend(frameon=False, ncol=4, loc="upper left")
    a.set_title(titre, fontweight="bold")
    b.set_xlabel("barre (minutes)")
    for ax in (a, b):
        _style(ax)
    fig.tight_layout()
    return fig


def fig_equity(df, resultats, titre):
    """Capital de chaque stratégie sur un même marché (dict nom -> Resultat)."""
    fig, (a, b) = plt.subplots(2, 1, figsize=(12, 7), sharex=True,
                               gridspec_kw={"height_ratios": [1, 2]})
    a.plot(df["close"].to_numpy(), color=ENCRE, lw=1)
    a.set_ylabel("prix ($)")
    for (nom, r), c in zip(resultats.items(), COULEURS):
        b.plot(r.equity.to_numpy(), color=c, lw=1.8, label=f"{nom} ({r.rendement_total:+.1%})")
    b.set_ylabel("capital ($)")
    b.set_xlabel("barre (minutes)")
    b.legend(frameon=False, ncol=2, fontsize=9, loc="best")
    a.set_title(titre, fontweight="bold")
    for ax in (a, b):
        _style(ax)
    fig.tight_layout()
    return fig


def fig_drawdown(df, res, titre):
    """Capital, « sous l'eau » (distance au sommet) et position détenue."""
    fig, (a, b, c) = plt.subplots(3, 1, figsize=(12, 7.5), sharex=True,
                                  gridspec_kw={"height_ratios": [3, 2, 0.8]})
    eq = res.equity
    a.plot(eq.to_numpy(), color=BLEU, lw=1.8, label=f"stratégie {res.rendement_total:+.1%}")
    a.plot(res.buy_and_hold.to_numpy(), color=GRIS, lw=1.3, ls="--",
           label=f"acheter et attendre {res.rendement_buy_and_hold:+.1%}")
    a.set_ylabel("capital ($)")
    a.legend(frameon=False, loc="upper left")
    a.set_title(titre, fontweight="bold")
    sous_eau = (eq / eq.cummax() - 1).to_numpy() * 100
    b.fill_between(range(len(sous_eau)), sous_eau, 0, color=ROUGE, alpha=0.35)
    b.axhline(res.drawdown_max * 100, color=ROUGE, ls=":", lw=1)
    b.set_ylabel("drawdown (%)")
    b.text(len(sous_eau) * 0.01, res.drawdown_max * 100 * 0.9, f"pire : {res.drawdown_max:.1%}",
           color=ROUGE, fontsize=9, va="top")
    c.fill_between(range(len(res.positions)), res.positions.astype(float), step="mid", color=VERT, alpha=0.5)
    c.set_yticks([0, 1], ["hors", "en"])
    c.set_xlabel(f"barre (minutes) — exposition {res.exposition:.0%}")
    for ax in (a, b, c):
        _style(ax)
    fig.tight_layout()
    return fig


def fig_bot(df, traces):
    """Capital du bot selon le seuil du coupe-circuit, sur un krach."""
    fig, (a, b) = plt.subplots(2, 1, figsize=(12, 6.5), sharex=True,
                               gridspec_kw={"height_ratios": [1, 2]})
    a.plot(df["close"].to_numpy(), color=ENCRE, lw=1)
    a.set_ylabel("prix ($)")
    for (nom, cap), c in zip(traces.items(), COULEURS):
        b.plot(np.arange(len(cap)) + 30, cap, color=c, lw=1.8, label=nom)
        b.scatter([len(cap) + 29], [cap[-1]], color=c, zorder=3)
    b.set_ylabel("capital ($)")
    b.set_xlabel("barre (minutes)")
    b.legend(frameon=False)
    a.set_title("Le bot sur un krach : le coupe-circuit arrête les frais", fontweight="bold")
    for ax in (a, b):
        _style(ax)
    fig.tight_layout()
    return fig
