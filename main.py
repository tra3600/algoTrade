"""algoTrade — point d'entrée.

    python main.py cas                          # cas illustrés sur 5 marchés simulés (sans clé API)
    python main.py backtest --scenario krach --graphique
    python main.py backtest --csv mes_donnees.csv
    python main.py simulation --scenario haussier   # le bot en accéléré sur un marché simulé
    python main.py compte                       # état du compte Alpaca (clés requises)
    python main.py selection                    # action la plus active du jour
    python main.py bot --symbole AAPL           # bot en direct, à blanc
    python main.py bot --symbole AAPL --envoyer-ordres
"""

import argparse
import os
import re
import sys

from scalp_strategy import ParametresStrategie

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _params(args):
    return ParametresStrategie(court=args.court, long=args.long,
                               stop_loss=args.stop / 100, take_profit=args.objectif / 100)


def _afficher_resultat(titre, res):
    print(f"\n── {titre}")
    for cle, val in res.resume().items():
        print(f"   {cle:<22}{val}")


def _montrer(fig, sauver, nom):
    import matplotlib.pyplot as plt
    if sauver:
        os.makedirs(sauver, exist_ok=True)
        chemin = os.path.join(sauver, f"{nom}.png")
        fig.savefig(chemin, dpi=110)
        print(f"   🖼  {chemin}")
        plt.close(fig)
    else:
        plt.show()


# ----------------------------------------------------------------------
def cmd_cas(args):
    """Les cas illustrés : que vaut la stratégie selon le marché, les frais, les réglages ?"""
    import matplotlib
    if args.sauver:
        matplotlib.use("Agg")
    from backtest import backtester, tracer
    from donnees import SCENARIOS, generer_marche

    base = _params(args)
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
        df = generer_marche(s, graine=args.graine)
        r = backtester(df, base, frais=args.frais / 100)
        r0 = backtester(df, base, frais=0, glissement=0)
        rl = backtester(df, lent, frais=args.frais / 100)
        print(f"{s:<10}{r.rendement_buy_and_hold:>+12.1%}{r.rendement_total:>+12.1%}"
              f"{r0.rendement_total:>+12.1%}{rl.rendement_total:>+12.1%}"
              f"{len(r.transactions):>9}{r.drawdown_max:>11.1%}")
        if args.graphique or args.sauver:
            _montrer(tracer(df, r, base, f"Marché {s} : {description}"), args.sauver, f"cas_{s}")
    print(f"""
Colonnes : « Scalping » = MM {base.court}/{base.long} avec frais {args.frais}% et glissement ;
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


def cmd_backtest(args):
    from backtest import backtester, tracer
    from donnees import charger_alpaca, charger_csv, generer_marche

    if args.csv:
        df, titre = charger_csv(args.csv), f"Backtest sur {args.csv}"
    elif args.symbole:
        from config import Config
        df = charger_alpaca(Config.depuis_env(), args.symbole, jours=args.jours)
        titre = f"Backtest sur {args.symbole} ({args.jours} jours)"
    else:
        df = generer_marche(args.scenario, jours=args.jours, graine=args.graine)
        titre = f"Backtest sur un marché simulé « {args.scenario} »"
    p = _params(args)
    res = backtester(df, p, capital=args.capital, frais=args.frais / 100)
    _afficher_resultat(titre, res)
    if args.transactions:
        print("\n   Entrée                 Sortie                 Qté    Gain     Raison")
        for t in res.transactions:
            print(f"   {t.entree_date:%Y-%m-%d %H:%M} {t.entree_prix:>8.2f}   "
                  f"{t.sortie_date:%Y-%m-%d %H:%M} {t.sortie_prix:>8.2f}   {t.quantite:>4} "
                  f"{t.gain:>+8.2f}   {t.raison_sortie}")
    if args.graphique or args.sauver:
        if args.sauver:
            import matplotlib
            matplotlib.use("Agg")
        _montrer(tracer(df, res, p, titre), args.sauver, "backtest")


def cmd_simulation(args):
    from alpaca_connect import CourtierSimule
    from bot import executer_bot
    from donnees import generer_marche

    df = generer_marche(args.scenario, jours=args.jours, graine=args.graine)
    courtier = CourtierSimule(df, capital=args.capital)
    executer_bot(courtier, "SIMU", _params(args), budget=args.budget, envoyer=True, pause=0,
                 perte_max=args.perte_max / 100, arret_si_ferme=True, dormir=lambda s: None,
                 journal=print if args.bavard else _journal_resume)
    print(f"{len(courtier.ordres)} ordres exécutés sur {len(df)} minutes simulées.")


def _journal_resume(msg):
    """N'affiche pas les ordres un par un (lignes horodatées), seulement le bilan."""
    if not re.match(r"\d\d:\d\d:\d\d ", msg):
        print(msg)


def cmd_compte(args):
    from alpaca_connect import CourtierAlpaca
    from config import Config

    for cle, val in CourtierAlpaca(Config.depuis_env()).compte().items():
        print(f"{cle:<15}{val}")


def cmd_selection(args):
    from config import Config
    from trade_volume import select_stock

    s = select_stock(Config.depuis_env(), prix_min=args.prix_min)
    print(f"Action sélectionnée : {s}" if s else "Aucune action ne passe le filtre.")


def cmd_bot(args):
    from alpaca_connect import CourtierAlpaca
    from bot import executer_bot
    from config import Config

    config = Config.depuis_env()
    if not config.paper and args.envoyer_ordres:
        rep = input("⚠ COMPTE RÉEL : des ordres avec de l'argent réel vont être envoyés. "
                    "Tapez « JE CONFIRME » : ")
        if rep.strip() != "JE CONFIRME":
            sys.exit("Annulé.")
    symbole = args.symbole
    if not symbole:
        from trade_volume import select_stock
        symbole = select_stock(config)
        print(f"Action sélectionnée automatiquement : {symbole}")
    executer_bot(CourtierAlpaca(config), symbole, _params(args), budget=args.budget,
                 quantite_fixe=args.quantite, envoyer=args.envoyer_ordres,
                 perte_max=args.perte_max / 100)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Scalping par croisement de moyennes mobiles.")
    sous = parser.add_subparsers(dest="commande", required=True)

    def reglages(p):
        p.add_argument("--court", type=int, default=5, help="MM courte (barres)")
        p.add_argument("--long", type=int, default=20, help="MM longue (barres)")
        p.add_argument("--stop", type=float, default=1.0, help="stop-loss en %% (0 = aucun)")
        p.add_argument("--objectif", type=float, default=2.0, help="take-profit en %% (0 = aucun)")

    def marche(p):
        p.add_argument("--scenario", default="haussier",
                       choices=["haussier", "baissier", "lateral", "volatil", "krach"])
        p.add_argument("--jours", type=int, default=5)
        p.add_argument("--graine", type=int, default=0)
        p.add_argument("--capital", type=float, default=10_000.0)

    p = sous.add_parser("cas", help="cas illustrés sur marchés simulés")
    reglages(p)
    p.add_argument("--graine", type=int, default=0)
    p.add_argument("--frais", type=float, default=0.05, help="frais par ordre en %%")
    p.add_argument("--graphique", action="store_true")
    p.add_argument("--sauver", metavar="DOSSIER")
    p.set_defaults(f=cmd_cas)

    p = sous.add_parser("backtest", help="rejouer la stratégie sur un historique")
    reglages(p)
    marche(p)
    p.add_argument("--csv", help="fichier CSV (colonnes open,high,low,close,volume)")
    p.add_argument("--symbole", help="historique réel Alpaca (clés requises)")
    p.add_argument("--frais", type=float, default=0.05, help="frais par ordre en %%")
    p.add_argument("--transactions", action="store_true", help="lister chaque transaction")
    p.add_argument("--graphique", action="store_true")
    p.add_argument("--sauver", metavar="DOSSIER")
    p.set_defaults(f=cmd_backtest)

    p = sous.add_parser("simulation", help="le bot en accéléré sur un marché simulé")
    reglages(p)
    marche(p)
    p.add_argument("--budget", type=float, default=10_000.0)
    p.add_argument("--perte-max", type=float, default=10.0, help="coupe-circuit en %%")
    p.add_argument("--bavard", action="store_true", help="afficher chaque ordre")
    p.set_defaults(f=cmd_simulation)

    p = sous.add_parser("compte", help="état du compte Alpaca")
    p.set_defaults(f=cmd_compte)

    p = sous.add_parser("selection", help="action la plus active du jour")
    p.add_argument("--prix-min", type=float, default=5.0)
    p.set_defaults(f=cmd_selection)

    p = sous.add_parser("bot", help="trading en direct (à blanc par défaut)")
    reglages(p)
    p.add_argument("--symbole", help="action à trader (sinon : la plus active)")
    p.add_argument("--budget", type=float, default=1_000.0, help="montant max par position ($)")
    p.add_argument("--quantite", type=int, help="quantité fixe (sinon calculée sur le budget)")
    p.add_argument("--perte-max", type=float, default=3.0, help="coupe-circuit en %%")
    p.add_argument("--envoyer-ordres", action="store_true",
                   help="envoyer réellement les ordres (sinon : à blanc)")
    p.set_defaults(f=cmd_bot)

    args = parser.parse_args(argv)
    args.f(args)


if __name__ == "__main__":
    main()
