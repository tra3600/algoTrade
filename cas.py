"""Les cas illustrés : chaque chiffre affiché est calculé par un backtest, jamais recopié.

    python main.py cas --liste
    python main.py cas --nom strategies --nom frais
    python main.py cas --tout --sauver figures
"""

import os
import re
from dataclasses import dataclass, field

import numpy as np

import analyses as an
from alpaca_connect import CourtierSimule
from backtest import backtester, tracer
from bot import executer_bot
from donnees import SCENARIOS, SCENARIOS_ETENDUS, generer_marche
from scalp_strategy import ParametresStrategie
from strategies import Bollinger, Cassure, MMFiltre, Momentum, RSI, TenirPosition

ETENDUS = [s for s in SCENARIOS_ETENDUS if s not in SCENARIOS]


@dataclass
class Contexte:
    """Réglages communs des cas : graine, frais (en %), nombre de graines, figures."""
    base: ParametresStrategie = field(default_factory=ParametresStrategie)
    graine: int = 0
    frais: float = 0.05
    graines: int = 10
    graphique: bool = False
    sauver: str | None = None

    @property
    def figures(self):
        return self.graphique or bool(self.sauver)


def montrer(fig, ctx, nom):
    """Affiche ou enregistre une figure (rien si aucune sortie graphique n'est demandée)."""
    if not ctx.figures:
        import matplotlib.pyplot as plt
        plt.close(fig)
        return
    import matplotlib.pyplot as plt
    if ctx.sauver:
        os.makedirs(ctx.sauver, exist_ok=True)
        chemin = os.path.join(ctx.sauver, f"{nom}.png")
        fig.savefig(chemin, dpi=110)
        print(f"   🖼  {chemin}")
        plt.close(fig)
    else:
        plt.show()


def titre(texte):
    print("\n" + "═" * 86)
    print(f"  {texte}")
    print("═" * 86)


def para(texte):
    print(texte.strip("\n"))


def strategies_standard():
    return {"MM 5/20": ParametresStrategie(), "MM filtrée": MMFiltre(), "Cassure": Cassure(),
            "Momentum": Momentum(), "RSI": RSI(), "Bollinger": Bollinger()}


def _fig(nom):
    import illustrations
    return getattr(illustrations, f"fig_{nom}")


# ----------------------------------------------------------------------
def cas_marches(ctx):
    """Le cas d'origine : le croisement de moyennes mobiles sur les 5 premiers marchés."""
    if ctx.sauver:
        import matplotlib
        matplotlib.use("Agg")
    base = ctx.base
    lent = ParametresStrategie(court=15, long=60, stop_loss=base.stop_loss,
                               take_profit=base.take_profit)
    print("═" * 86)
    print("  CAS ILLUSTRÉS — 5 jours de barres d'une minute, capital 10 000 $")
    print("═" * 86)
    entete = f"{'Marché':<10}{'Buy & hold':>12}{'Scalping':>12}{'Sans frais':>12}" \
             f"{'Plus lent':>12}{'Trades':>9}{'Drawdown':>11}"
    print(entete)
    print("─" * len(entete))
    for s, description in SCENARIOS.items():
        df = generer_marche(s, graine=ctx.graine)
        r = backtester(df, base, frais=ctx.frais / 100)
        r0 = backtester(df, base, frais=0, glissement=0)
        rl = backtester(df, lent, frais=ctx.frais / 100)
        print(f"{s:<10}{r.rendement_buy_and_hold:>+12.1%}{r.rendement_total:>+12.1%}"
              f"{r0.rendement_total:>+12.1%}{rl.rendement_total:>+12.1%}"
              f"{len(r.transactions):>9}{r.drawdown_max:>11.1%}")
        if ctx.figures:
            montrer(tracer(df, r, base, f"Marché {s} : {description}"), ctx, f"cas_{s}")
    print(f"""
Colonnes : « Scalping » = MM {base.court}/{base.long} avec frais {ctx.frais}% et glissement ;
« Sans frais » = même stratégie sans frais ni glissement ; « Plus lent » = MM 15/60.

Ce qu'il faut retenir :
  • En marché baissier ou en krach, la stratégie sort vite du marché : elle perd
    beaucoup moins que « acheter et attendre ».
  • En marché latéral, les moyennes se croisent sans arrêt : chaque faux signal
    coûte des frais et du glissement. C'est le pire cas du scalping.
  • La colonne « Sans frais » montre combien les coûts de transaction pèsent :
    une stratégie qui trade des dizaines de fois par semaine doit battre ses frais.
  • Aucun réglage ne gagne partout : testez sur vos propres données (--csv ou --symbole)
    et sur plusieurs graines (--graine) avant de risquer le moindre dollar.""")


def cas_nouveaux_marches(ctx):
    titre("1. CINQ NOUVEAUX MARCHÉS : régimes, rebond, vague, bulle, gaps")
    para("""
Les cinq marchés d'origine ne suffisent pas. Voici cinq situations de plus,
dont une où la tendance change de nature toutes les demi-journées.""")
    print(f"\n{'Marché':<10}{'Buy & hold':>12}{'MM 5/20':>10}{'Trades':>8}{'Drawdown':>10}   description")
    for s in ETENDUS:
        df = generer_marche(s, graine=ctx.graine)
        r = backtester(df, ctx.base, frais=ctx.frais / 100)
        print(f"{s:<10}{r.rendement_buy_and_hold:>+12.1%}{r.rendement_total:>+10.1%}"
              f"{len(r.transactions):>8}{r.drawdown_max:>10.1%}   {SCENARIOS_ETENDUS[s]}")
    montrer(_fig("marches")(), ctx, "marches_etendus")


def cas_strategies(ctx):
    titre("2. SIX STRATÉGIES, DIX MARCHÉS : qui gagne où ?")
    strats = strategies_standard()
    para(f"""
Suivi de tendance (MM, cassure, momentum) contre retour à la moyenne (RSI,
Bollinger). Rendement moyen sur {ctx.graines} graines, frais {ctx.frais}% par ordre.
La MM filtrée n'achète que si le marché a une direction (ratio d'efficacité de Kaufman).""")
    scenarios = list(SCENARIOS_ETENDUS)
    m, bh = an.matrice_strategies(scenarios, strats, range(ctx.graines), frais=ctx.frais / 100)
    print(f"\n{'Marché':<10}" + "".join(f"{n:>13}" for n in strats) + f"{'Acheter+garder':>16}")
    for i, s in enumerate(scenarios):
        print(f"{s:<10}" + "".join(f"{v:>+13.1%}" for v in m[i]) + f"{bh[i]:>+16.1%}")
    noms = list(strats)
    print("\nMeilleure stratégie par marché :")
    for i, s in enumerate(scenarios):
        j = int(np.argmax(m[i]))
        print(f"   {s:<10} {noms[j]:<12} ({m[i, j]:+.1%})")
    gagnants = {noms[int(np.argmax(m[i]))] for i in range(len(scenarios))}
    print(f"\n{len(gagnants)} stratégies différentes gagnent quelque part : aucune ne gagne partout.")
    montrer(_fig("matrice")(m, bh, scenarios, noms), ctx, "strategies_matrice")
    df = generer_marche("regimes", graine=ctx.graine)
    res = {n: backtester(df, s, frais=ctx.frais / 100) for n, s in strats.items()}
    montrer(_fig("equity")(df, res, "Marché « regimes » : le capital de chaque stratégie"), ctx,
            "strategies_regimes")


def cas_echelle(ctx):
    titre("3. L'ÉCHELLE DE TEMPS : la même oscillation est-elle une tendance ?")
    para("""
Un marché qui oscille sans fin est le terrain rêvé du retour à la moyenne... si
l'oscillation est rapide par rapport à la stratégie. Quand la période dépasse la
fenêtre des indicateurs, chaque vague *est* une tendance et le sens s'inverse.""")
    periodes = [10, 15, 20, 30, 45, 60, 90, 150, 300]
    strats = {"MM 5/20": ParametresStrategie(), "Cassure": Cassure(), "RSI": RSI(),
              "Bollinger": Bollinger()}
    n = max(2, ctx.graines // 2)
    res = {nom: [] for nom in strats}
    print(f"\n{'période (min)':>14}" + "".join(f"{n_:>12}" for n_ in strats))
    for p in periodes:
        ligne = []
        for nom, s in strats.items():
            r = np.mean([backtester(generer_marche("vague", graine=g, periode_vague=p), s,
                                    frais=ctx.frais / 100).rendement_total for g in range(n)])
            res[nom].append(r)
            ligne.append(r)
        print(f"{p:>14}" + "".join(f"{v:>+12.1%}" for v in ligne))
    mr = [p for i, p in enumerate(periodes) if max(res["RSI"][i], res["Bollinger"][i]) > 0.005]
    tendance = [p for i, p in enumerate(periodes) if max(res["MM 5/20"][i], res["Cassure"][i]) > 0.005]
    print(f"\nRetour à la moyenne rentable (> +0,5 %) pour les périodes {mr} minutes ;")
    print(f"suivi de tendance rentable pour les périodes {tendance} minutes.")
    print("Les fenêtres des indicateurs (5 à 20 barres) fixent l'échelle : trop rapide, tout est du bruit ;")
    print("plus lent, chaque vague est une tendance. Aucun des deux camps n'a « raison » en soi.")
    montrer(_fig("echelle")(periodes, res), ctx, "echelle")


def cas_frais(ctx):
    titre("4. LES FRAIS : à partir de quand la stratégie cesse-t-elle de gagner ?")
    para("""
On cherche, par dichotomie, les frais par ordre qui annulent exactement le rendement.
Plus une stratégie trade souvent, plus ce seuil est bas : le scalping est une
course contre les coûts.""")
    cas = [("Momentum / regimes", "regimes", Momentum()), ("Cassure / gaps", "gaps", Cassure()),
           ("MM 5/20 / haussier", "haussier", ParametresStrategie())]
    frais = list(np.linspace(0, 0.002, 9))
    courbes, equilibres = {}, {}
    print(f"\n{'':<22}{'trades':>8}{'rend. sans frais':>18}{'seuil de rentabilité':>24}")
    for nom, sc, strat in cas:
        df = generer_marche(sc, graine=ctx.graine)
        courbes[nom] = an.balayage_frais(df, strat, frais)
        equilibres[nom] = an.frais_equilibre(df, strat)
        r0 = backtester(df, strat, frais=0)
        eq = equilibres[nom]
        seuil = "jamais rentable" if eq == 0 else ("> 1 %" if eq == float("inf") else f"{eq:.3%} par ordre")
        print(f"{nom:<22}{len(r0.transactions):>8}{r0.rendement_total:>+18.1%}{seuil:>24}")
    print("\nRendement selon les frais (par ordre) :")
    print(f"{'frais':>8}" + "".join(f"{n[:18]:>20}" for n in courbes))
    for i, f in enumerate(frais):
        print(f"{f:>8.3%}" + "".join(f"{courbes[n][i]:>+20.1%}" for n in courbes))
    df = generer_marche("lateral", graine=ctx.graine)
    print("\nEt le glissement (écart entre prix vu et prix obtenu) ? Même effet, sur chaque ordre :")
    for g in (0, 0.0002, 0.0005, 0.001):
        r = backtester(df, ctx.base, frais=0.0005, glissement=g)
        print(f"   glissement {g:.2%} → {r.rendement_total:+.1%}  ({len(r.transactions)} trades)")
    montrer(_fig("frais")(frais, courbes, equilibres), ctx, "frais")


def cas_reglages(ctx):
    titre("5. LES RÉGLAGES : le meilleur couple de moyennes change avec le marché")
    para("""
Rendement du croisement de MM pour chaque couple (courte, longue) sur le même
marché ; ★ marque le meilleur. Un réglage « optimal » ici ne l'est pas ailleurs.""")
    courts, longs = [2, 3, 5, 8, 12], [10, 15, 20, 30, 45, 60]
    grilles = {}
    for sc in ("haussier", "lateral", "vague"):
        df = generer_marche(sc, graine=ctx.graine)
        g = an.grille_mm(df, courts, longs, frais=ctx.frais / 100)
        grilles[sc] = g
        c, l, v = an.meilleur_couple(g, courts, longs)
        print(f"\n   {sc} : meilleur réglage MM {c}/{l} ({v:+.1%}) ; "
              f"pire {np.nanmin(g):+.1%} ; réglage 5/20 : {g[courts.index(5), longs.index(20)]:+.1%}")
        print("   court\\long " + "".join(f"{l_:>8}" for l_ in longs))
        for i, c_ in enumerate(courts):
            print(f"   {c_:>10} " + "".join("        " if np.isnan(x) else f"{x:>+8.1%}" for x in g[i]))
    montrer(_fig("grille")(grilles, courts, longs), ctx, "reglages")


def cas_surapprentissage(ctx):
    titre("6. LE SURAPPRENTISSAGE : optimiser sur le passé, perdre sur l'avenir")
    para("""
On choisit le meilleur couple de MM sur la première moitié d'un marché latéral
(où rien n'est prévisible), puis on le juge sur la seconde. Pour isoler l'effet,
on travaille sans frais : le réglage choisi « marchait » sur le passé uniquement
parce qu'on l'a choisi pour cela.""")
    courts, longs = [2, 3, 5, 8, 12], [10, 15, 20, 30, 45, 60]
    n = max(4, ctx.graines)
    lignes = [an.optimiser_puis_tester("lateral", g, courts, longs, frais=0, glissement=0)
              for g in range(n)]
    print(f"\n{'graine':>7}{'réglage':>10}{'apprentissage':>15}{'données neuves':>16}{'MM 5/20 neuf':>14}")
    for g, l in enumerate(lignes[:8]):
        print(f"{g:>7}{str(l['court']) + '/' + str(l['long']):>10}{l['dans_echantillon']:>+15.1%}"
              f"{l['hors_echantillon']:>+16.1%}{l['defaut_hors_echantillon']:>+14.1%}")
    dans = np.mean([l["dans_echantillon"] for l in lignes])
    hors = np.mean([l["hors_echantillon"] for l in lignes])
    defaut = np.mean([l["defaut_hors_echantillon"] for l in lignes])
    decus = sum(l["hors_echantillon"] < l["dans_echantillon"] for l in lignes)
    print(f"\nMoyenne sur {n} marchés : apprentissage {dans:+.1%}, données neuves {hors:+.1%} "
          f"(réglage 5/20, non optimisé : {defaut:+.1%}).")
    print(f"Le réglage optimisé déçoit sur données neuves dans {decus} cas sur {n} : l'écart est le prix de")
    print("l'optimisation. Jugez toujours sur des données que le réglage n'a jamais vues.")
    montrer(_fig("surapprentissage")(lignes), ctx, "surapprentissage")


def cas_monte_carlo(ctx):
    titre("7. MONTE-CARLO : un seul backtest ne prouve rien")
    n = max(10, ctx.graines * 5)
    para(f"""
La même stratégie, sur {n} marchés simulés qui ne diffèrent que par la graine.
Le hasard seul peut faire gagner ou perdre ; seule la distribution compte.""")
    for sc in ("lateral", "regimes"):
        mcs = {"MM 5/20": an.monte_carlo(sc, ParametresStrategie(), range(n), frais=ctx.frais / 100),
               "Momentum": an.monte_carlo(sc, Momentum(), range(n), frais=ctx.frais / 100)}
        print(f"\n   Marché « {sc} » ({n} graines)")
        print(f"   {'':<10}{'moyenne':>9}{'médiane':>9}{'5 %':>8}{'95 %':>8}{'P(gain)':>9}{'P(>B&H)':>9}{'trades':>8}")
        for nom, mc in mcs.items():
            r = an.resume_monte_carlo(mc)
            print(f"   {nom:<10}{r['moyenne']:>+9.1%}{r['mediane']:>+9.1%}{r['p5']:>+8.1%}"
                  f"{r['p95']:>+8.1%}{r['proba_gain']:>9.0%}{r['proba_battre_bh']:>9.0%}"
                  f"{r['transactions']:>8.0f}")
        montrer(_fig("monte_carlo")(mcs, f"Marché « {sc} » : rendements sur {n} graines"), ctx,
                f"monte_carlo_{sc}")


def cas_risque(ctx):
    titre("8. STOP-LOSS ET TAKE-PROFIT : combien et quelle garantie ?")
    para("""
Un stop-loss serré coupe les pertes mais aussi les gains en devenir ; un take-profit
serré coupe les gains. La stratégie décide à la clôture et s'exécute à l'ouverture
suivante : le prix de sortie n'est donc jamais exactement le niveau du stop.""")
    n = max(3, ctx.graines // 2)
    frais = ctx.frais / 100
    stops, objectifs = [0.0, 0.005, 0.01, 0.02, 0.05], [0.0, 0.005, 0.01, 0.02, 0.04, 0.08]
    fabriques = {"RSI": lambda s, o: RSI(stop_loss=s, take_profit=o),
                 "Cassure": lambda s, o: Cassure(stop_loss=s, take_profit=o),
                 "MM 5/20": lambda s, o: ParametresStrategie(stop_loss=s, take_profit=o)}

    def moyenne(sc, strat):
        return np.mean([backtester(generer_marche(sc, graine=g), strat, frais=frais).rendement_total
                        for g in range(n)])

    print(f"\n   Rendement moyen ({n} graines) selon le stop-loss (0 % = aucun), sans take-profit")
    print(f"   {'stratégie / marché':<22}" + "".join(f"{s:>9.1%}" for s in stops))
    rend_stop = {}
    for nom, mk in fabriques.items():
        for sc in ("krach", "bulle", "volatil"):
            ligne = [moyenne(sc, mk(s, 0.0)) for s in stops]
            if sc == "krach":
                rend_stop[nom] = ligne
            ecart = max(ligne) - min(ligne)
            note = "stop sans effet visible" if ecart < 0.005 else (
                f"meilleur stop {stops[int(np.argmax(ligne))]:.1%}" if np.argmax(ligne) else "mieux sans stop")
            print(f"   {nom + ' / ' + sc:<22}" + "".join(f"{v:>+9.1%}" for v in ligne) + f"   {note}")
    print(f"\n   Rendement moyen selon le take-profit sur « haussier » (0 % = aucun)")
    print(f"   {'stratégie':<22}" + "".join(f"{o:>9.1%}" for o in objectifs))
    rend_obj = {}
    for nom, mk in {"MM 5/20": fabriques["MM 5/20"], "Cassure": fabriques["Cassure"],
                    "Momentum": lambda s, o: Momentum(stop_loss=s, take_profit=o)}.items():
        ligne = [moyenne("haussier", mk(0.0, o)) for o in objectifs]
        rend_obj[nom] = ligne
        print(f"   {nom:<22}" + "".join(f"{v:>+9.1%}" for v in ligne))
    print("   → un take-profit serré coupe les gains : il vaut mieux laisser courir une tendance.")
    sorties = []
    for sc in ("krach", "volatil", "gaps"):
        for g in range(n):
            r = backtester(generer_marche(sc, graine=g), RSI(stop_loss=0.01, take_profit=0.0),
                           frais=0, glissement=0)
            sorties += [(sc, t.rendement) for t in r.transactions if "stop-loss" in t.raison_sortie]
    print(f"\n   Stop-loss fixé à −1 % : {len(sorties)} sorties observées ; perte réelle moyenne "
          f"{np.mean([x for _, x in sorties]):+.2%}, pire {min(x for _, x in sorties):+.2%}.")
    for sc in ("krach", "volatil", "gaps"):
        xs = [x for s_, x in sorties if s_ == sc]
        if xs:
            print(f"      {sc:<8} perte moyenne au stop {np.mean(xs):+.2%} ({len(xs)} sorties)")
    print("   Le stop n'est pas une garantie : le marché peut sauter par-dessus (gap, volatilité).")
    montrer(_fig("risque")(stops_pct(stops), rend_stop, stops_pct(objectifs), rend_obj,
                           "Rendement moyen selon le stop-loss (krach) et le take-profit (haussier)"),
            ctx, "risque")


def stops_pct(x):
    return [v * 100 for v in x]


def cas_taille(ctx):
    titre("9. COMBIEN ENGAGER ? Taille de position et risque")
    para("""
La taille d'une position ne change pas la qualité d'une stratégie, seulement
l'échelle : gains et pertes sont multipliés dans la même proportion, et le risque
de grosse chute aussi. Règle usuelle : fixer le risque par trade (ex. 0,5 % du
capital) et en déduire la taille : fraction = risque / stop-loss.""")
    n = max(6, ctx.graines)
    fractions = [0.1, 0.25, 0.5, 0.75, 1.0]
    frais = ctx.frais / 100
    strat = Momentum()
    print(f"\n   Momentum sur « regimes », {n} graines, selon la part du capital engagée :")
    print(f"   {'part':>6}{'rendement':>11}{'drawdown moyen':>16}{'pire drawdown':>15}{'rendement/drawdown':>20}")
    lignes = []
    for fr in fractions:
        rs, dds = [], []
        for g in range(n):
            r = backtester(generer_marche("regimes", graine=g), strat, frais=frais, fraction=fr)
            rs.append(r.rendement_total)
            dds.append(r.drawdown_max)
        lignes.append((fr, np.mean(rs), np.mean(dds), np.min(dds)))
        print(f"   {fr:>6.0%}{np.mean(rs):>+11.1%}{np.mean(dds):>16.1%}{np.min(dds):>15.1%}"
              f"{np.mean(rs) / -np.mean(dds):>20.2f}")
    print("   → le rapport rendement/drawdown reste presque constant : la taille règle le niveau de risque, pas la qualité.")
    risque, stop = 0.005, 0.01
    print(f"\n   Risque de 0,5 % du capital par trade avec un stop à 1 % → on engage {risque / stop:.0%} du capital.")
    print("\n   Fraction de Kelly f* = p/l − q/g (g, l = gain et perte moyens par trade, en rendement) :")
    for nom, s_, sc in (("Momentum", Momentum(), "regimes"), ("MM 5/20", ParametresStrategie(), "lateral")):
        rend = np.array([t.rendement for g in range(n)
                         for t in backtester(generer_marche(sc, graine=g), s_, frais=frais).transactions])
        gains, pertes = rend[rend > 0], -rend[rend < 0]
        p = len(gains) / len(rend)
        g_moy, l_moy = gains.mean(), pertes.mean()
        f = an.kelly(p, g_moy, l_moy)
        verdict = ("aucun avantage : ne pas jouer" if f <= 0 else
                   "avantage mesuré énorme face au risque par trade : à ne pas croire tel quel" if f > 1 else "")
        print(f"      {nom:<9} « {sc} » : {len(rend)} trades, réussite {p:.0%}, gain {g_moy:+.2%}, "
              f"perte {-l_moy:+.2%} → Kelly {f:+.1f}× le capital" + (f"  ({verdict})" if verdict else ""))
    print("   Un Kelly aussi élevé vient de petits gains/pertes par trade : il suppose que le passé se")
    print("   répète exactement. En pratique on engage une fraction du Kelly, jamais de levier aveugle.")
    df = generer_marche("regimes", graine=ctx.graine)
    equities = {f"{int(fr * 100)} % du capital":
                backtester(df, strat, frais=frais, fraction=fr).equity for fr in (0.25, 0.5, 1.0)}
    montrer(_fig("taille")(lignes, equities), ctx, "taille_position")


def cas_regimes(ctx):
    titre("10. LES RÉGIMES : le filtre de tendance évite les faux signaux")
    para("""
Un marché qui alterne tendance et absence de direction piège le suivi de tendance :
tout va bien pendant la tendance, puis les faux signaux rongent les gains. Le
filtre (ratio d'efficacité de Kaufman) n'autorise l'achat que si le prix avance
en ligne droite plutôt qu'en zigzag.""")
    df = generer_marche("regimes", graine=ctx.graine)
    r_mm = backtester(df, ParametresStrategie(), frais=ctx.frais / 100)
    r_f = backtester(df, MMFiltre(), frais=ctx.frais / 100)
    print(f"\n   graine {ctx.graine} : MM 5/20 {r_mm.rendement_total:+.1%} ({len(r_mm.transactions)} trades) ; "
          f"MM filtrée {r_f.rendement_total:+.1%} ({len(r_f.transactions)} trades) ; "
          f"acheter et attendre {r_mm.rendement_buy_and_hold:+.1%}")
    print(f"\n   Gain moyen par régime (en $, sur {max(4, ctx.graines)} graines) :")
    print(f"   {'régime':<22}{'marché':>9}{'MM 5/20':>11}{'MM filtrée':>12}")
    cumul = {}
    n = max(4, ctx.graines)
    for g in range(n):
        d = generer_marche("regimes", graine=g)
        a = an.rendement_par_regime(backtester(d, ParametresStrategie(), frais=ctx.frais / 100), d)
        b = an.rendement_par_regime(backtester(d, MMFiltre(), frais=ctx.frais / 100), d)
        for reg in a:
            c = cumul.setdefault(reg, [0.0, 0.0, 0.0])
            c[0] += a[reg]["marche"] / n
            c[1] += a[reg]["gain"] / n
            c[2] += b[reg]["gain"] / n
    for reg, (m, a_, b_) in cumul.items():
        print(f"   {reg:<22}{m:>+9.1%}{a_:>+11.0f}{b_:>+12.0f}")
    montrer(_fig("regimes")(df, r_mm, r_f), ctx, "regimes")


def cas_metriques(ctx):
    titre("11. LES MÉTRIQUES : comment lire un backtest")
    para("""
Le rendement seul ne dit pas le risque pris. On recalcule ici chaque mesure « à la
main » pour vérifier ce que le programme affiche.""")
    df = generer_marche("regimes", graine=ctx.graine)
    r = backtester(df, Momentum(), frais=ctx.frais / 100)
    for cle, val in r.resume_etendu().items():
        print(f"   {cle:<28}{val}")
    eq = r.equity
    rendements = eq.pct_change().dropna()
    sharpe = rendements.mean() / rendements.std() * np.sqrt(r.barres_par_an)
    dd = (eq / eq.cummax() - 1).min()
    gains = sum(t.gain for t in r.transactions if t.gain > 0)
    pertes = -sum(t.gain for t in r.transactions if t.gain < 0)
    print("\nRecalcul à la main :")
    print(f"   Sharpe = moyenne/écart-type des rendements par barre × √({r.barres_par_an:.0f}) = {sharpe:.2f}")
    print(f"   Drawdown max = plus forte baisse depuis un sommet = {dd:.2%}")
    print(f"   Facteur de profit = gains {gains:.0f} $ / pertes {pertes:.0f} $ = {gains / pertes if pertes else float('inf'):.2f}")
    print(f"   Espérance = gain total / nombre de trades = {sum(t.gain for t in r.transactions) / len(r.transactions):+.2f} $")
    assert abs(sharpe - r.sharpe) < 1e-9 and abs(dd - r.drawdown_max) < 1e-12
    print("\nLecture : un rendement positif avec un Sharpe faible ou un drawdown énorme n'est pas")
    print("une bonne stratégie, c'est un hasard heureux. Le Sortino ne pénalise que les baisses ;")
    print("l'exposition dit combien de temps le capital a réellement travaillé.")
    montrer(_fig("drawdown")(df, r, "Momentum sur « regimes » : capital, drawdown et position"), ctx, "metriques")


class CourtierTrace(CourtierSimule):
    """Courtier simulé qui retient le capital à chaque barre (pour tracer le bot)."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.capitaux = []

    def dernieres_barres(self, symbole, n):
        self.capitaux.append(self.compte()["capital"])
        return super().dernieres_barres(symbole, n)


def cas_bot(ctx):
    titre("12. LE BOT SIMULÉ : le coupe-circuit à l'œuvre")
    para("""
Le bot tourne ici sur un courtier simulé, sans rien envoyer. Il utilise la même
fonction de décision que le backtest. On le lance sur un krach avec trois seuils de
coupe-circuit : un seuil serré arrête le bot, un seuil large le laisse subir.""")
    df = generer_marche("krach", graine=ctx.graine)
    traces = {}
    for perte_max in (0.02, 0.10, 0.50):
        courtier = CourtierTrace(df, capital=10_000.0)
        journal = []
        final = executer_bot(courtier, "SIMU", ParametresStrategie(stop_loss=0.0, take_profit=0.0),
                             budget=10_000.0, envoyer=True, pause=0, perte_max=perte_max,
                             arret_si_ferme=True, journal=journal.append, dormir=lambda s: None)
        coupe = any("Coupe-circuit" in m for m in journal)
        traces[f"coupe-circuit à {perte_max:.0%}" + (" (déclenché)" if coupe else "")] = courtier.capitaux
        print(f"   perte max {perte_max:>4.0%} : {len(courtier.ordres):>3} ordres, "
              f"capital final {final:>9.2f} $ ({final / 10_000 - 1:+.1%})"
              + ("  ⛔ coupe-circuit déclenché" if coupe else ""))
    print("\nEt à blanc (--envoyer-ordres absent) : le bot décide mais n'envoie rien.")
    courtier = CourtierSimule(df)
    journal = []
    executer_bot(courtier, "SIMU", ParametresStrategie(), envoyer=False, pause=0, arret_si_ferme=True,
                 journal=journal.append, dormir=lambda s: None)
    ordres_vus = sum(1 for m in journal if re.search(r"ACHAT|VENTE", m))
    print(f"   {ordres_vus} ordres journalisés, {len(courtier.ordres)} réellement envoyés.")
    print("\nToutes les stratégies sont interchangeables dans le bot (même interface) :")
    for nom, s in strategies_standard().items():
        courtier = CourtierSimule(generer_marche("regimes", graine=ctx.graine), capital=10_000.0)
        final = executer_bot(courtier, "SIMU", s, budget=10_000.0, envoyer=True, pause=0,
                             perte_max=0.5, arret_si_ferme=True, journal=lambda m: None,
                             dormir=lambda s_: None)
        print(f"   {nom:<12} {len(courtier.ordres):>3} ordres, capital final {final:>9.2f} $")
    montrer(_fig("bot")(df, traces), ctx, "bot_coupe_circuit")


def cas_anatomie(ctx):
    titre("13. ANATOMIE D'UN TRADE : pourquoi la stratégie a-t-elle agi ?")
    para("""
Chaque décision a une raison écrite. Voici les premières décisions de chaque
stratégie sur le marché « vague », puis le tracé de deux d'entre elles.""")
    df = generer_marche("vague", graine=ctx.graine)
    closes = df["close"].to_numpy()
    for nom, s in (("RSI", RSI()), ("Bollinger", Bollinger()), ("Cassure", Cassure())):
        print(f"\n   {nom} — {s.description()}")
        pos, entree, vues = False, 0.0, 0
        for i in range(len(closes)):
            d = s.decider(closes[: i + 1], pos, entree)
            if d.action:
                heure = df.index[i].strftime("%H:%M")
                print(f"      {heure}  {d.action.upper():<6} à {closes[i]:7.2f}  {d.raison}")
                pos, entree = (d.action == "achat"), (closes[i] if d.action == "achat" else 0.0)
                vues += 1
                if vues >= 4:
                    break
    for s, nom in ((Bollinger(), "bollinger"), (RSI(), "rsi")):
        montrer(_fig("anatomie")(df, s, f"{s.description()} sur le marché « vague »", 0, 300), ctx,
                f"anatomie_{nom}")


CAS = {
    "marches": (cas_marches, "le cas d'origine : MM 5/20 sur les 5 marchés classiques"),
    "nouveaux_marches": (cas_nouveaux_marches, "cinq marchés de plus : régimes, rebond, vague, bulle, gaps"),
    "strategies": (cas_strategies, "6 stratégies × 10 marchés : qui gagne où ?"),
    "echelle": (cas_echelle, "tendance ou retour à la moyenne selon l'échelle de temps"),
    "frais": (cas_frais, "seuil de rentabilité en frais, effet du glissement"),
    "reglages": (cas_reglages, "grille des réglages court × long"),
    "surapprentissage": (cas_surapprentissage, "optimiser sur le passé, juger sur l'avenir"),
    "monte_carlo": (cas_monte_carlo, "distribution des rendements sur de nombreuses graines"),
    "risque": (cas_risque, "stop-loss, take-profit et leur garantie"),
    "taille": (cas_taille, "fraction de Kelly et taille de position"),
    "regimes": (cas_regimes, "filtre de tendance dans un marché à régimes"),
    "metriques": (cas_metriques, "Sharpe, Sortino, drawdown, espérance, recalculés à la main"),
    "bot": (cas_bot, "le bot simulé et son coupe-circuit"),
    "anatomie": (cas_anatomie, "la raison de chaque décision, tracée"),
}


def lancer(nom, ctx):
    CAS[nom][0](ctx)


def liste():
    print("Cas disponibles :")
    for nom, (_, desc) in CAS.items():
        print(f"   {nom:<18} {desc}")
