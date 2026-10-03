"""Stratégie de scalping par croisement de moyennes mobiles.

La logique est une fonction pure (prix + position -> décision) : la même
fonction sert au backtest et au bot en direct, ce qui garantit que l'on
teste exactement ce que l'on exécute.

Corrections par rapport à la version d'origine :
- on n'agit qu'au *croisement* des moyennes, pas tant que court > long
  (l'ancien code rachetait 10 actions chaque minute) ;
- on ne vend que ce que l'on possède (pas de vente à découvert involontaire) ;
- stop-loss et take-profit pour limiter les pertes.
"""

from dataclasses import dataclass

import numpy as np

ACHAT, VENTE = "achat", "vente"


@dataclass
class ParametresStrategie:
    """Réglages du croisement de moyennes mobiles (et interface commune des stratégies :
    ``nom``, ``historique``, ``description()``, ``decider(prix, en_position, prix_entree)``)."""
    court: int = 5            # fenêtre de la moyenne mobile courte (en barres)
    long: int = 20            # fenêtre de la moyenne mobile longue
    stop_loss: float = 0.01   # sortie si le prix baisse de 1 % sous le prix d'entrée
    take_profit: float = 0.02  # sortie si le prix monte de 2 % au-dessus

    def __post_init__(self):
        if not 1 <= self.court < self.long:
            raise ValueError("Il faut 1 ≤ court < long.")
        if self.stop_loss < 0 or self.take_profit < 0:
            raise ValueError("stop_loss et take_profit doivent être positifs (0 = désactivé).")

    nom = "mm"

    @property
    def historique(self):
        return self.long + 1

    def description(self):
        return f"MM {self.court}/{self.long}"

    def decider(self, prix, en_position, prix_entree):
        return decider(prix, en_position, prix_entree, self)


@dataclass
class Decision:
    action: str | None   # ACHAT, VENTE ou None (ne rien faire)
    raison: str


def moyennes_mobiles(prix, fenetre):
    """Moyenne mobile simple ; NaN tant que la fenêtre n'est pas remplie."""
    prix = np.asarray(prix, dtype=float)
    res = np.full(len(prix), np.nan)
    if len(prix) >= fenetre:
        cumul = np.cumsum(np.insert(prix, 0, 0.0))
        res[fenetre - 1:] = (cumul[fenetre:] - cumul[:-fenetre]) / fenetre
    return res


def croisement(prix, p: ParametresStrategie):
    """ACHAT si la MM courte vient de passer au-dessus de la longue, VENTE si l'inverse."""
    if len(prix) < p.long + 1:
        return None
    court = moyennes_mobiles(prix[-(p.long + 1):], p.court)
    long = moyennes_mobiles(prix[-(p.long + 1):], p.long)
    avant, maintenant = court[-2] - long[-2], court[-1] - long[-1]
    if np.isnan(avant):
        return None
    if avant <= 0 < maintenant:
        return ACHAT
    if avant >= 0 > maintenant:
        return VENTE
    return None


def decider(prix, en_position, prix_entree, p: ParametresStrategie):
    """Décision à la clôture de la dernière barre de ``prix``."""
    dernier = float(prix[-1])
    if en_position:
        if p.stop_loss and dernier <= prix_entree * (1 - p.stop_loss):
            return Decision(VENTE, f"stop-loss ({dernier:.2f} ≤ {prix_entree * (1 - p.stop_loss):.2f})")
        if p.take_profit and dernier >= prix_entree * (1 + p.take_profit):
            return Decision(VENTE, f"take-profit ({dernier:.2f} ≥ {prix_entree * (1 + p.take_profit):.2f})")
        if croisement(prix, p) == VENTE:
            return Decision(VENTE, "la MM courte repasse sous la MM longue")
        return Decision(None, "on garde la position")
    if croisement(prix, p) == ACHAT:
        return Decision(ACHAT, "la MM courte croise la MM longue par le haut")
    return Decision(None, "pas de signal")
