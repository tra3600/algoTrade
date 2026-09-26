"""Boucle de trading en direct (ou simulée).

Garde-fous :
- par défaut, aucun ordre n'est envoyé (mode « à blanc ») : il faut --envoyer-ordres ;
- le compte de démonstration Alpaca est utilisé tant que ALPACA_PAPER n'est pas à false ;
- la taille de position est plafonnée par un budget ;
- coupe-circuit : le bot s'arrête si le capital perd plus de ``perte_max`` depuis le lancement.
"""

import time
from datetime import datetime

from scalp_strategy import ACHAT, VENTE, decider


def executer_bot(courtier, symbole, params, budget=1_000.0, quantite_fixe=None,
                 envoyer=False, pause=60, iterations=None, perte_max=0.03,
                 arret_si_ferme=False, journal=print, dormir=time.sleep):
    capital_depart = courtier.compte()["capital"]
    mode = "ORDRES ENVOYÉS" if envoyer else "à blanc (aucun ordre envoyé)"
    journal(f"▶ Bot sur {symbole} — {mode} — budget {budget:.0f} $, "
            f"MM {params.court}/{params.long}, stop {params.stop_loss:.1%}, "
            f"objectif {params.take_profit:.1%}, coupe-circuit à -{perte_max:.0%}")
    n = 0
    try:
        while iterations is None or n < iterations:
            n += 1
            if not courtier.marche_ouvert():
                if arret_si_ferme:
                    journal("Marché fermé / données épuisées : arrêt.")
                    break
                journal("Marché fermé, nouvelle vérification dans 5 minutes.")
                dormir(300)
                continue

            capital = courtier.compte()["capital"]
            if capital < capital_depart * (1 - perte_max):
                journal(f"⛔ Coupe-circuit : capital {capital:.2f} $ < "
                        f"{capital_depart * (1 - perte_max):.2f} $. Arrêt du bot.")
                break

            try:
                barres = courtier.dernieres_barres(symbole, params.long + 5)
                if len(barres) < params.long + 1:
                    journal("Pas encore assez de barres, on attend.")
                    dormir(pause)
                    continue
                closes = barres["close"].to_numpy(dtype=float)
                pos = courtier.position(symbole)
                d = decider(closes, pos.quantite > 0, pos.prix_moyen, params)
                prix = closes[-1]
                heure = datetime.now().strftime("%H:%M:%S")
                if d.action == ACHAT:
                    q = quantite_fixe or int(budget // prix)
                    if q <= 0:
                        journal(f"{heure} Budget insuffisant pour 1 action à {prix:.2f} $.")
                    else:
                        journal(f"{heure} 🟢 ACHAT {q} {symbole} à ~{prix:.2f} $ — {d.raison}")
                        if envoyer:
                            courtier.acheter(symbole, q)
                elif d.action == VENTE:
                    journal(f"{heure} 🔴 VENTE {pos.quantite} {symbole} à ~{prix:.2f} $ — {d.raison}")
                    if envoyer:
                        courtier.vendre(symbole, pos.quantite)
            except Exception as e:  # une erreur réseau ne doit pas tuer le bot
                journal(f"⚠ Erreur : {e!r}. Nouvelle tentative au prochain tour.")
            dormir(pause)
    except KeyboardInterrupt:
        journal("Arrêt demandé (Ctrl-C).")
    final = courtier.compte()["capital"]
    journal(f"■ Fin : capital {final:.2f} $ ({final / capital_depart - 1:+.2%} depuis le lancement).")
    return final
