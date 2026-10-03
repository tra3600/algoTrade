"""Backtest : rejouer la stratégie sur un historique, avec frais et glissement.

Pour éviter de « lire l'avenir », une décision prise à la clôture d'une barre
est exécutée à l'ouverture de la barre suivante.
"""

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from scalp_strategy import ACHAT, VENTE, ParametresStrategie, moyennes_mobiles


@dataclass
class Transaction:
    entree_date: pd.Timestamp
    entree_prix: float
    quantite: int
    sortie_date: pd.Timestamp | None = None
    sortie_prix: float | None = None
    raison_sortie: str = ""

    @property
    def gain(self):
        return (self.sortie_prix - self.entree_prix) * self.quantite

    @property
    def rendement(self):
        return self.sortie_prix / self.entree_prix - 1


@dataclass
class Resultat:
    capital_initial: float
    equity: pd.Series
    transactions: list = field(default_factory=list)
    frais_payes: float = 0.0
    buy_and_hold: pd.Series | None = None
    barres_par_an: float = 252 * 390
    positions: np.ndarray | None = None   # vrai quand une position est détenue à la clôture de la barre

    @property
    def rendement_total(self):
        return self.equity.iloc[-1] / self.capital_initial - 1

    @property
    def rendement_buy_and_hold(self):
        return self.buy_and_hold.iloc[-1] / self.buy_and_hold.iloc[0] - 1

    @property
    def drawdown_max(self):
        return float((self.equity / self.equity.cummax() - 1).min())

    @property
    def sharpe(self):
        r = self.equity.pct_change().dropna()
        if r.std() == 0 or len(r) < 2:
            return 0.0
        return float(r.mean() / r.std() * math.sqrt(self.barres_par_an))

    @property
    def sortino(self):
        """Comme Sharpe, mais seules les baisses comptent comme du risque."""
        r = self.equity.pct_change().dropna()
        baisse = np.sqrt(np.mean(np.minimum(r.to_numpy(), 0.0) ** 2)) if len(r) else 0.0
        if baisse == 0:
            return 0.0
        return float(r.mean() / baisse * math.sqrt(self.barres_par_an))

    @property
    def calmar(self):
        """Rendement total rapporté au pire drawdown (non annualisé : l'horizon est court)."""
        dd = self.drawdown_max
        return float(self.rendement_total / -dd) if dd < 0 else 0.0

    @property
    def exposition(self):
        """Part du temps passée en position (0 à 1)."""
        return float(np.mean(self.positions)) if self.positions is not None else float("nan")

    @property
    def esperance(self):
        """Gain moyen par transaction ($)."""
        return float(np.mean([t.gain for t in self.transactions])) if self.transactions else 0.0

    @property
    def gain_moyen(self):
        g = [t.gain for t in self.transactions if t.gain > 0]
        return float(np.mean(g)) if g else 0.0

    @property
    def perte_moyenne(self):
        p = [t.gain for t in self.transactions if t.gain < 0]
        return float(np.mean(p)) if p else 0.0

    @property
    def duree_moyenne(self):
        """Durée moyenne d'une transaction, en minutes."""
        if not self.transactions:
            return 0.0
        return float(np.mean([(t.sortie_date - t.entree_date).total_seconds() / 60
                              for t in self.transactions]))

    @property
    def taux_reussite(self):
        if not self.transactions:
            return 0.0
        return sum(t.gain > 0 for t in self.transactions) / len(self.transactions)

    @property
    def facteur_profit(self):
        gains = sum(t.gain for t in self.transactions if t.gain > 0)
        pertes = -sum(t.gain for t in self.transactions if t.gain < 0)
        return math.inf if pertes == 0 and gains > 0 else (gains / pertes if pertes else 0.0)

    def resume(self):
        pf = self.facteur_profit
        return {
            "Rendement stratégie": f"{self.rendement_total:+.2%}",
            "Rendement buy & hold": f"{self.rendement_buy_and_hold:+.2%}",
            "Transactions": len(self.transactions),
            "Taux de réussite": f"{self.taux_reussite:.0%}",
            "Facteur de profit": "∞" if pf == math.inf else f"{pf:.2f}",
            "Drawdown max": f"{self.drawdown_max:.2%}",
            "Sharpe (annualisé)": f"{self.sharpe:.2f}",
            "Frais payés": f"{self.frais_payes:.2f} $",
        }


    def resume_etendu(self):
        """``resume()`` plus les mesures de risque et de qualité des transactions."""
        r = self.resume()
        r.update({
            "Sortino (annualisé)": f"{self.sortino:.2f}",
            "Calmar": f"{self.calmar:.2f}",
            "Exposition": f"{self.exposition:.0%}",
            "Espérance par trade": f"{self.esperance:+.2f} $",
            "Gain moyen / perte moyenne": f"{self.gain_moyen:+.2f} / {self.perte_moyenne:+.2f} $",
            "Durée moyenne d'un trade": f"{self.duree_moyenne:.0f} min",
        })
        return r


def backtester(df, params=None, capital=10_000.0, frais=0.0005, glissement=0.0002,
               barres_par_an=252 * 390, fraction=1.0):
    """Rejoue la stratégie sur ``df`` (colonnes open/close).

    params : toute stratégie (``decider(prix, en_position, prix_entree)``) ; par défaut
        le croisement de moyennes mobiles 5/20
    frais : commission proportionnelle par ordre (0,05 % par défaut)
    glissement : écart défavorable entre prix attendu et prix obtenu (0,02 %)
    fraction : part des liquidités engagée à chaque achat (1 = tout, 0,5 = la moitié)
    """
    if not 0 < fraction <= 1:
        raise ValueError("fraction doit être dans ]0, 1].")
    params = params or ParametresStrategie()
    closes = df["close"].to_numpy(dtype=float)
    opens = df["open"].to_numpy(dtype=float)
    dates = df.index
    cash, quantite, prix_entree = capital, 0, 0.0
    transactions, frais_payes = [], 0.0
    equity = np.empty(len(df))
    positions = np.zeros(len(df), dtype=bool)
    en_attente = None  # décision prise à la clôture, exécutée à l'ouverture suivante

    for i in range(len(df)):
        if en_attente is not None:
            action, raison = en_attente
            en_attente = None
            if action == ACHAT and quantite == 0:
                prix = opens[i] * (1 + glissement)
                q = int(cash * fraction // (prix * (1 + frais)))
                if q > 0:
                    cout = q * prix
                    frais_payes += cout * frais
                    cash -= cout * (1 + frais)
                    quantite, prix_entree = q, prix
                    transactions.append(Transaction(dates[i], prix, q))
            elif action == VENTE and quantite > 0:
                prix = opens[i] * (1 - glissement)
                produit = quantite * prix
                frais_payes += produit * frais
                cash += produit * (1 - frais)
                t = transactions[-1]
                t.sortie_date, t.sortie_prix, t.raison_sortie = dates[i], prix, raison
                quantite = 0

        equity[i] = cash + quantite * closes[i]
        positions[i] = quantite > 0
        d = params.decider(closes[: i + 1], quantite > 0, prix_entree)
        if d.action:
            en_attente = (d.action, d.raison)

    # Position encore ouverte : on la valorise au dernier cours (sans la clôturer).
    fermees = [t for t in transactions if t.sortie_prix is not None]
    bh = df["close"] / df["close"].iloc[0] * capital
    return Resultat(capital, pd.Series(equity, index=dates), fermees, frais_payes, bh,
                    barres_par_an, positions)


def tracer(df, res, params, titre=""):
    """Prix + moyennes + achats/ventes, puis capital comparé au buy & hold."""
    import matplotlib.pyplot as plt

    bleu, orange, vert, rouge, gris, encre = "#2a78d6", "#eb6834", "#008300", "#e34948", "#8a8983", "#0b0b0b"
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7), sharex=True,
                                   gridspec_kw={"height_ratios": [3, 2]})
    x = np.arange(len(df))
    closes = df["close"].to_numpy()
    ax1.plot(x, closes, color=gris, lw=1, label="prix")
    ax1.plot(x, moyennes_mobiles(closes, params.court), color=bleu, lw=1.5,
             label=f"MM {params.court}")
    ax1.plot(x, moyennes_mobiles(closes, params.long), color=orange, lw=1.5,
             label=f"MM {params.long}")
    pos = {d: i for i, d in enumerate(df.index)}
    for t in res.transactions:
        ax1.scatter(pos[t.entree_date], t.entree_prix, marker="^", s=60, color=encre, zorder=3)
        ax1.scatter(pos[t.sortie_date], t.sortie_prix, marker="v", s=60,
                    color=vert if t.gain > 0 else rouge, zorder=3)
    ax1.scatter([], [], marker="^", color=encre, label="achat")
    ax1.scatter([], [], marker="v", color=rouge, label="vente (perte)")
    ax1.scatter([], [], marker="v", color=vert, label="vente (gain)")
    ax1.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=6, frameon=False, fontsize=9)
    ax1.set_ylabel("prix ($)")
    ax2.plot(x, res.equity.to_numpy(), color=bleu, lw=2,
             label=f"stratégie {res.rendement_total:+.1%}")
    ax2.plot(x, res.buy_and_hold.to_numpy(), color=gris, lw=1.5, ls="--",
             label=f"buy & hold {res.rendement_buy_and_hold:+.1%}")
    ax2.axhline(res.capital_initial, color="#d9d8d3", lw=1)
    ax2.legend(loc="lower left", frameon=False, fontsize=9)
    ax2.set_ylabel("capital ($)")
    ax2.set_xlabel("barre (minutes)")
    for ax in (ax1, ax2):
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", color="#eeeeea")
    fig.suptitle(titre or "Backtest", fontweight="bold", y=0.99)
    fig.tight_layout()
    return fig
