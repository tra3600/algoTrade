"""algoTrade — point d'entrée.

    python main.py cas                          # cas d'origine sur 5 marchés simulés (sans clé API)
    python main.py cas --liste                  # les 14 cas illustrés
    python main.py cas --tout --sauver figures
    python main.py comparer --scenario regimes  # toutes les stratégies sur un marché
    python main.py montecarlo --scenario lateral --graines 100
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
from donnees import SCENARIOS_ETENDUS
from strategies import CATALOGUE

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _params(args):
    """La stratégie choisie par --strategie (par défaut : croisement de moyennes mobiles)."""
    stop, objectif = args.stop / 100, args.objectif / 100
    nom = getattr(args, "strategie", "mm")
    if nom == "mm":
        return ParametresStrategie(court=args.court, long=args.long, stop_loss=stop, take_profit=objectif)
    from strategies import CATALOGUE, creer
    options = {"stop_loss": stop, "take_profit": objectif}
    if nom == "tenir":
        options = {}
    elif nom == "mm_filtre":
        options.update(court=args.court, long=args.long)
    elif args.fenetre:
        options["periode" if nom == "rsi" else "fenetre"] = args.fenetre
    return creer(nom, **options)


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
    import cas
    if args.liste:
        cas.liste()
        return
    ctx = cas.Contexte(base=_params(args), graine=args.graine, frais=args.frais,
                       graines=args.graines, graphique=args.graphique, sauver=args.sauver)
    if args.sauver:
        import matplotlib
        matplotlib.use("Agg")
    noms = list(cas.CAS) if args.tout else (args.nom or ["marches"])
    for nom in noms:
        cas.lancer(nom, ctx)


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


def cmd_comparer(args):
    """Toutes les stratégies du catalogue, avec leurs réglages par défaut, sur un même marché."""
    from backtest import backtester
    from donnees import charger_csv, generer_marche
    from strategies import creer

    if args.csv:
        df, titre = charger_csv(args.csv), args.csv
    else:
        df, titre = generer_marche(args.scenario, jours=args.jours, graine=args.graine), \
            f"marché simulé « {args.scenario} », graine {args.graine}"
    print(f"Comparaison des stratégies — {titre}, capital {args.capital:.0f} $, frais {args.frais}%\n")
    print(f"{'stratégie':<34}{'rendement':>10}{'trades':>8}{'drawdown':>10}{'Sharpe':>8}{'exposition':>12}")
    for nom in CATALOGUE:
        s = creer(nom)
        r = backtester(df, s, capital=args.capital, frais=args.frais / 100)
        print(f"{s.description():<34}{r.rendement_total:>+10.1%}{len(r.transactions):>8}"
              f"{r.drawdown_max:>10.1%}{r.sharpe:>8.1f}{r.exposition:>12.0%}")


def cmd_montecarlo(args):
    import analyses as an

    s = _params(args)
    mc = an.monte_carlo(args.scenario, s, range(args.graines), jours=args.jours,
                        frais=args.frais / 100, capital=args.capital)
    r = an.resume_monte_carlo(mc)
    print(f"{s.description()} sur « {args.scenario} », {args.graines} marchés simulés de {args.jours} jours")
    print(f"   rendement moyen {r['moyenne']:+.2%}, médian {r['mediane']:+.2%}")
    print(f"   90 % des cas entre {r['p5']:+.2%} et {r['p95']:+.2%} (pire {r['pire']:+.2%}, meilleur {r['meilleur']:+.2%})")
    print(f"   probabilité de gagner {r['proba_gain']:.0%} ; de battre « acheter et attendre » {r['proba_battre_bh']:.0%}")
    print(f"   drawdown moyen {r['drawdown_moyen']:.1%} ; {r['transactions']:.0f} transactions par marché")


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


def cas_noms():
    import cas
    return cas.CAS


def main(argv=None):
    parser = argparse.ArgumentParser(description="Scalping par croisement de moyennes mobiles.")
    sous = parser.add_subparsers(dest="commande", required=True)

    def reglages(p):
        p.add_argument("--court", type=int, default=5, help="MM courte (barres)")
        p.add_argument("--long", type=int, default=20, help="MM longue (barres)")
        p.add_argument("--stop", type=float, default=1.0, help="stop-loss en %% (0 = aucun)")
        p.add_argument("--objectif", type=float, default=2.0, help="take-profit en %% (0 = aucun)")
        p.add_argument("--strategie", default="mm", choices=list(CATALOGUE),
                       help="stratégie du catalogue (défaut : mm = croisement de moyennes mobiles)")
        p.add_argument("--fenetre", type=int, help="fenêtre/période de la stratégie (rsi, bollinger, cassure, momentum)")

    def marche(p):
        p.add_argument("--scenario", default="haussier",
                       choices=list(SCENARIOS_ETENDUS))
        p.add_argument("--jours", type=int, default=5)
        p.add_argument("--graine", type=int, default=0)
        p.add_argument("--capital", type=float, default=10_000.0)

    p = sous.add_parser("cas", help="cas illustrés sur marchés simulés")
    reglages(p)
    p.add_argument("--nom", action="append", choices=list(cas_noms()),
                   help="cas à jouer (répétable ; défaut : marches)")
    p.add_argument("--tout", action="store_true", help="tous les cas")
    p.add_argument("--liste", action="store_true", help="liste les cas")
    p.add_argument("--graines", type=int, default=10, help="graines des cas statistiques")
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

    p = sous.add_parser("comparer", help="toutes les stratégies sur un marché")
    marche(p)
    p.add_argument("--csv", help="fichier CSV au lieu d'un marché simulé")
    p.add_argument("--frais", type=float, default=0.05, help="frais par ordre en %%")
    p.set_defaults(f=cmd_comparer)

    p = sous.add_parser("montecarlo", help="distribution des rendements sur de nombreuses graines")
    reglages(p)
    marche(p)
    p.add_argument("--graines", type=int, default=50, help="nombre de marchés simulés")
    p.add_argument("--frais", type=float, default=0.05, help="frais par ordre en %%")
    p.set_defaults(f=cmd_montecarlo)

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
