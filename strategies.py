"""Un catalogue de stratégies, toutes sous la même forme que ``scalp_strategy``.

Chaque stratégie est une fonction pure du passé des prix : ``decider(prix,
en_position, prix_entree) -> Decision``. Le backtest et le bot peuvent donc les
échanger sans rien changer, et l'on teste exactement ce que l'on exécute.

Deux familles s'opposent :
- **suivi de tendance** (MM croisées, cassure de canal, momentum) : on achète ce
  qui monte, on gagne gros dans les tendances et on perd dans les marchés sans direction ;
- **retour à la moyenne** (RSI, bandes de Bollinger) : on achète ce qui a trop
  baissé, on gagne dans les marchés qui oscillent et on se fait écraser par les tendances.
"""

from dataclasses import dataclass

import numpy as np

from scalp_strategy import ACHAT, Decision, ParametresStrategie, VENTE, croisement, moyennes_mobiles


@dataclass(kw_only=True)
class StrategieBase:
    """Gère stop-loss et take-profit ; les sous-classes donnent entrée et sortie."""
    stop_loss: float = 0.01
    take_profit: float = 0.02
    nom = "base"

    def __post_init__(self):
        if self.stop_loss < 0 or self.take_profit < 0:
            raise ValueError("stop_loss et take_profit doivent être positifs (0 = désactivé).")

    @property
    def historique(self) -> int:
        """Nombre minimal de barres nécessaires pour décider."""
        raise NotImplementedError

    def entree(self, prix):
        """Raison de l'achat (texte) ou None."""
        raise NotImplementedError

    def sortie(self, prix):
        """Raison de la vente (texte) ou None."""
        raise NotImplementedError

    def description(self) -> str:
        return self.nom

    def decider(self, prix, en_position, prix_entree):
        prix = np.asarray(prix, dtype=float)
        dernier = float(prix[-1])
        if en_position:
            if self.stop_loss and dernier <= prix_entree * (1 - self.stop_loss):
                return Decision(VENTE, f"stop-loss ({dernier:.2f} ≤ {prix_entree * (1 - self.stop_loss):.2f})")
            if self.take_profit and dernier >= prix_entree * (1 + self.take_profit):
                return Decision(VENTE, f"take-profit ({dernier:.2f} ≥ {prix_entree * (1 + self.take_profit):.2f})")
        if len(prix) < self.historique:
            return Decision(None, "pas assez de barres")
        if en_position:
            raison = self.sortie(prix)
            return Decision(VENTE, raison) if raison else Decision(None, "on garde la position")
        raison = self.entree(prix)
        return Decision(ACHAT, raison) if raison else Decision(None, "pas de signal")


# ----------------------------------------------------------------------
# Suivi de tendance
# ----------------------------------------------------------------------
@dataclass(kw_only=True)
class MMFiltre(StrategieBase):
    """Croisement de moyennes mobiles, mais on n'achète que si le marché *a une
    direction* : ratio d'efficacité de Kaufman = |variation nette| / chemin parcouru.
    Il vaut 1 pour une tendance parfaite et ~0 pour un marché qui tourne en rond."""
    court: int = 5
    long: int = 20
    fenetre_er: int = 20
    seuil_er: float = 0.2
    nom = "mm_filtre"

    def __post_init__(self):
        super().__post_init__()
        self._mm = ParametresStrategie(self.court, self.long, 0, 0)

    @property
    def historique(self):
        return max(self.long, self.fenetre_er) + 1

    def description(self):
        return f"MM {self.court}/{self.long} filtrée (ER > {self.seuil_er})"

    def entree(self, prix):
        if croisement(prix, self._mm) != ACHAT:
            return None
        er = ratio_efficacite(prix, self.fenetre_er)
        if er >= self.seuil_er:
            return f"croisement haussier, marché directionnel (ER {er:.2f})"
        return None

    def sortie(self, prix):
        return "la MM courte repasse sous la MM longue" if croisement(prix, self._mm) == VENTE else None


@dataclass(kw_only=True)
class Cassure(StrategieBase):
    """Canal de Donchian : achat quand le prix dépasse son plus haut des
    ``fenetre`` dernières barres, vente quand il passe sous son plus bas des ``sortie_fenetre``."""
    fenetre: int = 20
    sortie_fenetre: int = 10
    nom = "cassure"

    @property
    def historique(self):
        return self.fenetre + 1

    def description(self):
        return f"cassure du plus haut sur {self.fenetre} barres"

    def entree(self, prix):
        haut = prix[-self.fenetre - 1:-1].max()
        return f"cassure : {prix[-1]:.2f} > plus haut {haut:.2f}" if prix[-1] > haut else None

    def sortie(self, prix):
        bas = prix[-self.sortie_fenetre - 1:-1].min()
        return f"cassure basse : {prix[-1]:.2f} < plus bas {bas:.2f}" if prix[-1] < bas else None


@dataclass(kw_only=True)
class Momentum(StrategieBase):
    """On achète ce qui a monté de plus de ``seuil`` sur ``fenetre`` barres, on
    vend quand cette variation redevient négative."""
    fenetre: int = 30
    seuil: float = 0.003
    nom = "momentum"

    @property
    def historique(self):
        return self.fenetre + 1

    def description(self):
        return f"momentum {self.fenetre} barres > {self.seuil:.1%}"

    def _variation(self, prix):
        return prix[-1] / prix[-self.fenetre - 1] - 1

    def entree(self, prix):
        v = self._variation(prix)
        return f"momentum {v:+.2%} sur {self.fenetre} barres" if v > self.seuil else None

    def sortie(self, prix):
        v = self._variation(prix)
        return f"le momentum devient négatif ({v:+.2%})" if v < 0 else None


# ----------------------------------------------------------------------
# Retour à la moyenne
# ----------------------------------------------------------------------
@dataclass(kw_only=True)
class RSI(StrategieBase):
    """Indice de force relative : on achète les survendus (RSI bas), on vend au retour à la normale."""
    periode: int = 14
    survente: float = 30.0
    sortie_rsi: float = 55.0
    nom = "rsi"

    @property
    def historique(self):
        return self.periode + 1

    def description(self):
        return f"RSI {self.periode} (achat < {self.survente:g}, vente > {self.sortie_rsi:g})"

    def entree(self, prix):
        r = rsi(prix, self.periode)
        return f"RSI {r:.0f} < {self.survente:g} : survendu" if r < self.survente else None

    def sortie(self, prix):
        r = rsi(prix, self.periode)
        return f"RSI revenu à {r:.0f}" if r > self.sortie_rsi else None


@dataclass(kw_only=True)
class Bollinger(StrategieBase):
    """Bandes de Bollinger : on achète sous la bande basse (moyenne − k·écart-type),
    on vend au retour sur la moyenne."""
    fenetre: int = 20
    k: float = 2.0
    nom = "bollinger"

    @property
    def historique(self):
        return self.fenetre

    def description(self):
        return f"Bollinger {self.fenetre} ± {self.k:g}σ"

    def entree(self, prix):
        w = prix[-self.fenetre:]
        mu, sigma = w.mean(), w.std()
        if sigma > 0 and prix[-1] < mu - self.k * sigma:
            return f"{prix[-1]:.2f} sous la bande basse ({mu - self.k * sigma:.2f})"
        return None

    def sortie(self, prix):
        mu = prix[-self.fenetre:].mean()
        return f"retour sur la moyenne ({mu:.2f})" if prix[-1] >= mu else None


@dataclass(kw_only=True)
class TenirPosition(StrategieBase):
    """Référence : acheter tout de suite et ne plus rien faire (avec les mêmes frais)."""
    stop_loss: float = 0.0
    take_profit: float = 0.0
    nom = "tenir"

    @property
    def historique(self):
        return 1

    def description(self):
        return "acheter et garder"

    def entree(self, prix):
        return "achat initial"

    def sortie(self, prix):
        return None


# ----------------------------------------------------------------------
# Indicateurs
# ----------------------------------------------------------------------
def rsi(prix, periode: int = 14) -> float:
    """RSI de Cutler sur les ``periode`` dernières variations (0 à 100)."""
    d = np.diff(np.asarray(prix, dtype=float)[-periode - 1:])
    gains, pertes = d[d > 0].sum(), -d[d < 0].sum()
    if gains + pertes == 0:
        return 50.0
    if pertes == 0:
        return 100.0
    return float(100 - 100 / (1 + gains / pertes))


def ratio_efficacite(prix, fenetre: int = 20) -> float:
    """Ratio d'efficacité de Kaufman sur ``fenetre`` barres, entre 0 et 1."""
    w = np.asarray(prix, dtype=float)[-fenetre - 1:]
    chemin = np.abs(np.diff(w)).sum()
    return float(abs(w[-1] - w[0]) / chemin) if chemin > 0 else 0.0


def bandes_bollinger(prix, fenetre: int = 20, k: float = 2.0):
    """(moyenne, bande basse, bande haute) ; NaN tant que la fenêtre n'est pas remplie."""
    prix = np.asarray(prix, dtype=float)
    mu = moyennes_mobiles(prix, fenetre)
    sigma = np.full(len(prix), np.nan)
    for i in range(fenetre - 1, len(prix)):
        sigma[i] = prix[i - fenetre + 1:i + 1].std()
    return mu, mu - k * sigma, mu + k * sigma


# ----------------------------------------------------------------------
# Catalogue
# ----------------------------------------------------------------------
CATALOGUE = {
    "mm": (ParametresStrategie, "croisement de moyennes mobiles 5/20 (la stratégie d'origine)"),
    "mm_filtre": (MMFiltre, "idem, mais seulement si le marché a une direction"),
    "cassure": (Cassure, "cassure du plus haut des 20 dernières barres"),
    "momentum": (Momentum, "on suit ce qui a monté"),
    "rsi": (RSI, "retour à la moyenne : on achète les survendus"),
    "bollinger": (Bollinger, "retour à la moyenne : on achète sous la bande basse"),
    "tenir": (TenirPosition, "référence : acheter et attendre"),
}


def creer(nom: str, **options):
    """Instancie une stratégie du catalogue ; `options` = champs de la stratégie."""
    if nom not in CATALOGUE:
        raise ValueError(f"Stratégie inconnue : {nom}. Choix : {', '.join(CATALOGUE)}")
    return CATALOGUE[nom][0](**options)
