"""Tests du laboratoire : stratégies, marchés étendus, analyses, cas illustrés, ligne de commande."""

import re

import numpy as np
import pandas as pd
import pytest

import analyses as an
import cas
import main as principal
from alpaca_connect import CourtierSimule
from backtest import backtester
from bot import executer_bot
from donnees import SCENARIOS, SCENARIOS_ETENDUS, generer_marche
from scalp_strategy import ACHAT, VENTE, Decision, ParametresStrategie, decider
from strategies import (CATALOGUE, Bollinger, Cassure, MMFiltre, Momentum, RSI, TenirPosition,
                        bandes_bollinger, creer, ratio_efficacite, rsi)


def _df(closes):
    closes = np.asarray(closes, dtype=float)
    idx = pd.date_range("2026-01-05 09:30", periods=len(closes), freq="min")
    return pd.DataFrame({"open": closes, "high": closes, "low": closes, "close": closes,
                         "volume": 1000}, index=idx)


# --- Indicateurs ----------------------------------------------------------
def test_rsi_bornes():
    assert rsi(np.arange(1, 30), 14) == 100.0
    assert rsi(np.arange(30, 1, -1), 14) == pytest.approx(0.0)
    assert rsi([5.0] * 20, 14) == 50.0
    assert rsi([1, 2] * 8, 14) == pytest.approx(50.0, abs=5)     # autant de hausses que de baisses


def test_ratio_efficacite():
    assert ratio_efficacite(np.arange(30), 20) == pytest.approx(1.0)
    assert ratio_efficacite([1, 2] * 20, 20) == pytest.approx(0.0)
    assert ratio_efficacite([3.0] * 30, 20) == 0.0
    assert 0 <= ratio_efficacite(np.random.default_rng(0).normal(size=100).cumsum(), 20) <= 1


def test_bandes_bollinger():
    prix = np.random.default_rng(1).normal(100, 1, 60)
    mu, bas, haut = bandes_bollinger(prix, 20, 2)
    assert np.isnan(mu[:19]).all() and np.isnan(bas[:19]).all()
    assert np.allclose(mu[19:] - bas[19:], haut[19:] - mu[19:])
    assert mu[30] == pytest.approx(prix[11:31].mean())
    assert (haut[19:] - mu[19:])[0] == pytest.approx(2 * prix[:20].std())


# --- Stratégies -----------------------------------------------------------
def test_catalogue_complet():
    assert set(CATALOGUE) == {"mm", "mm_filtre", "cassure", "momentum", "rsi", "bollinger", "tenir"}
    for nom in CATALOGUE:
        s = creer(nom)
        assert s.nom == nom and s.historique >= 1 and s.description()
        d = s.decider(np.full(s.historique, 100.0), False, 0.0)
        assert isinstance(d, Decision)
    with pytest.raises(ValueError):
        creer("inconnue")


def test_interface_mm_identique():
    p = ParametresStrategie(2, 4, 0.05, 0.10)
    for prix, pos, entree in [([10, 10, 10, 10, 12], False, 0), ([100] * 5 + [94], True, 100.0),
                              ([10, 10, 10, 10, 8], True, 10.0)]:
        assert p.decider(prix, pos, entree) == decider(prix, pos, entree, p)
    assert p.historique == 5 and p.nom == "mm"


def test_rsi_strategie():
    s = RSI(periode=5, survente=30, sortie_rsi=55, stop_loss=0, take_profit=0)
    chute = [100, 99, 98, 97, 96, 95]
    assert s.decider(chute, False, 0).action == ACHAT
    assert s.decider(chute, True, 95).action is None
    hausse = [95, 96, 97, 98, 99, 100]
    assert s.decider(hausse, True, 95).action == VENTE
    assert s.decider(hausse, False, 0).action is None
    assert s.decider([100, 99], False, 0).raison == "pas assez de barres"


def test_bollinger_strategie():
    s = Bollinger(fenetre=10, k=2, stop_loss=0, take_profit=0)
    prix = [100.0] * 9 + [99.0, 90.0]
    assert s.decider(prix, False, 0).action == ACHAT
    assert s.decider([100.0] * 10, False, 0).action is None       # écart-type nul : pas de signal
    assert s.decider([100.0] * 9 + [101.0], True, 90).action == VENTE


def test_cassure_strategie():
    s = Cassure(fenetre=5, sortie_fenetre=3, stop_loss=0, take_profit=0)
    assert s.decider([10, 11, 10, 11, 10, 12], False, 0).action == ACHAT
    assert s.decider([10, 11, 10, 11, 10, 11], False, 0).action is None
    assert s.decider([10, 11, 12, 13, 14, 11.5], True, 10).action == VENTE


def test_momentum_strategie():
    s = Momentum(fenetre=4, seuil=0.01, stop_loss=0, take_profit=0)
    assert s.decider([100, 100, 100, 100, 102], False, 0).action == ACHAT
    assert s.decider([100, 100, 100, 100, 100.5], False, 0).action is None
    assert s.decider([100, 101, 102, 101, 99], True, 100).action == VENTE


def test_mm_filtre_refuse_le_zigzag():
    from scalp_strategy import croisement
    s = MMFiltre(court=2, long=4, fenetre_er=6, seuil_er=0.5, stop_loss=0, take_profit=0)
    zigzag = [10, 12, 10, 12, 10, 12, 10, 10, 10, 11.5]    # croisement haussier dans un zigzag
    tendance = [10.0] * 9 + [11.0]                          # croisement haussier, en ligne droite
    assert croisement(zigzag, s._mm) == ACHAT and croisement(tendance, s._mm) == ACHAT
    assert ratio_efficacite(zigzag, 6) < 0.5 <= ratio_efficacite(tendance, 6)
    assert s.decider(zigzag, False, 0).action is None
    d = s.decider(tendance, False, 0)
    assert d.action == ACHAT and "ER" in d.raison


def test_stop_et_objectif_communs():
    for s in (RSI(stop_loss=0.02, take_profit=0.05), Cassure(stop_loss=0.02, take_profit=0.05)):
        assert s.decider([100] * 40 + [97], True, 100.0).action == VENTE
        assert "stop-loss" in s.decider([100] * 40 + [97], True, 100.0).raison
        assert "take-profit" in s.decider([100] * 40 + [106], True, 100.0).raison
    with pytest.raises(ValueError):
        Momentum(stop_loss=-1)


def test_tenir_position():
    t = TenirPosition()
    assert t.decider([100.0], False, 0).action == ACHAT
    assert t.decider([100.0, 50.0], True, 100.0).action is None
    r = backtester(_df([10, 11, 12, 13]), t, capital=1000, frais=0, glissement=0)
    assert r.equity.iloc[-1] == pytest.approx(1000 * 13 / 11, rel=0.1)
    assert r.positions.tolist() == [False, True, True, True]


# --- Backtest : extensions ------------------------------------------------
def test_backtest_avec_toutes_les_strategies():
    df = generer_marche("regimes", jours=2, graine=2)
    for nom in CATALOGUE:
        r = backtester(df, creer(nom))
        assert np.isfinite(r.rendement_total) and -1 < r.drawdown_max <= 0
        assert 0 <= r.exposition <= 1
        assert set(r.resume_etendu()) > set(r.resume())


def test_fraction_engagee():
    df = _df([10, 10, 10, 10, 12, 13, 14, 15, 16, 17])
    s = ParametresStrategie(2, 4, 0, 0)
    plein = backtester(df, s, capital=1000, frais=0, glissement=0)
    moitie = backtester(df, s, capital=1000, frais=0, glissement=0, fraction=0.5)
    assert plein.equity.iloc[-1] > moitie.equity.iloc[-1] > 1000
    assert moitie.equity.iloc[-1] - 1000 == pytest.approx((plein.equity.iloc[-1] - 1000) / 2, rel=0.05)
    for f in (0, -1, 1.5):
        with pytest.raises(ValueError):
            backtester(df, s, fraction=f)


def test_metriques_etendues_a_la_main():
    closes = [10, 10, 10, 10, 12, 12, 12, 9, 9, 9, 9, 9, 9]
    r = backtester(_df(closes), ParametresStrategie(2, 4, 0, 0), capital=1200, frais=0, glissement=0)
    assert len(r.transactions) == 1
    t = r.transactions[0]
    assert r.esperance == pytest.approx(t.gain) and r.gain_moyen == 0 and r.perte_moyenne == pytest.approx(t.gain)
    assert r.duree_moyenne == 3.0                     # achat à l'ouverture de la barre 5, vente à celle de la barre 8
    assert r.exposition == pytest.approx(r.positions.mean())
    assert r.calmar == pytest.approx(r.rendement_total / -r.drawdown_max)
    assert r.sortino <= 0 and r.sharpe <= 0


def test_metriques_sans_transaction():
    r = backtester(_df([10.0] * 30), ParametresStrategie(), capital=1000)
    assert r.esperance == 0 and r.duree_moyenne == 0 and r.sortino == 0 and r.calmar == 0
    assert r.exposition == 0


# --- Marchés étendus -------------------------------------------------------
def test_scenarios_classiques_inchanges():
    attendu = {"haussier": 105.34405974763888, "baissier": 77.10990584385135,
               "lateral": 100.78730806404327, "volatil": 79.56430330107193,
               "krach": 75.03328032506307}
    for nom, valeur in attendu.items():
        assert generer_marche(nom, graine=0)["close"].iloc[-1] == pytest.approx(valeur, rel=1e-12)
    assert list(SCENARIOS) == list(SCENARIOS_ETENDUS)[:5]


@pytest.mark.parametrize("scenario", list(SCENARIOS_ETENDUS))
def test_scenarios_etendus_valides(scenario):
    df = generer_marche(scenario, jours=3, graine=4)
    assert len(df) == 1170
    assert (df["high"] >= df[["open", "close"]].max(axis=1)).all()
    assert (df["low"] <= df[["open", "close"]].min(axis=1)).all()
    assert (df["close"] > 0).all()
    pd.testing.assert_frame_equal(df, generer_marche(scenario, jours=3, graine=4))


def test_regimes_etiquettes():
    df = generer_marche("regimes", graine=1)
    lab = df.attrs["regimes"]
    assert len(lab) == len(df) and set(lab) == {"tendance haussière", "tendance baissière", "sans direction"}
    c = df["close"].to_numpy()
    haut = [c[i * 195 + 194] / c[i * 195] for i in range(0, 10, 4)]
    assert np.mean(haut) > 1                                    # les demi-journées haussières montent


def test_formes_des_scenarios():
    for g in range(3):
        rebond = generer_marche("rebond", graine=g)["close"].to_numpy()
        assert rebond.argmin() < 0.6 * len(rebond) and rebond[-1] > rebond.min() * 1.1
        bulle = generer_marche("bulle", graine=g)["close"].to_numpy()
        assert bulle.max() > 110 and bulle[-1] < bulle.max() * 0.85
        assert generer_marche("gaps", graine=g)["close"].iloc[-1] > 100


def test_gaps_a_l_ouverture():
    df = generer_marche("gaps", graine=2)
    prev = df["close"].shift(1)
    ecarts = (df["open"] / prev - 1).abs()
    matin = ecarts.iloc[390::390]
    reste = ecarts.drop(matin.index).dropna()
    assert matin.mean() > 10 * reste.mean() + 1e-3
    assert generer_marche("gaps", graine=2).equals(df)


def test_vague_periode():
    for p in (20, 60):
        c = generer_marche("vague", graine=0, periode_vague=p)["close"].to_numpy()
        z = np.log(c) - np.log(c).mean()
        spectre = np.abs(np.fft.rfft(z))
        assert abs(len(c) / (spectre[1:].argmax() + 1) - p) < 0.15 * p


def test_scenario_inconnu():
    with pytest.raises(ValueError):
        generer_marche("licorne")


# --- Analyses ----------------------------------------------------------------
def test_monte_carlo():
    mc = an.monte_carlo("lateral", ParametresStrategie(), range(4), jours=2)
    assert set(mc) == {"rendement", "buy_and_hold", "drawdown", "transactions"}
    assert all(len(v) == 4 for v in mc.values())
    mc2 = an.monte_carlo("lateral", ParametresStrategie(), range(4), jours=2)
    assert np.array_equal(mc["rendement"], mc2["rendement"])
    r = an.resume_monte_carlo(mc)
    assert r["p5"] <= r["mediane"] <= r["p95"] and 0 <= r["proba_gain"] <= 1
    assert r["pire"] <= r["moyenne"] <= r["meilleur"]


def test_matrice_strategies():
    strats = {"mm": ParametresStrategie(), "tenir": TenirPosition()}
    m, bh = an.matrice_strategies(["haussier", "krach"], strats, range(2), jours=2)
    assert m.shape == (2, 2) and bh.shape == (2,)
    assert bh[0] > bh[1]                                       # un marché monte, l'autre s'effondre


def test_frais_equilibre():
    df = generer_marche("regimes", graine=0)
    s = Momentum()
    eq = an.frais_equilibre(df, s)
    assert 0 < eq < 0.01
    assert backtester(df, s, frais=eq * 0.9).rendement_total > 0 > backtester(df, s, frais=eq * 1.1).rendement_total
    assert an.frais_equilibre(generer_marche("lateral", graine=0), ParametresStrategie()) == 0.0
    courbe = an.balayage_frais(df, s, [0, 0.001, 0.002])
    assert courbe[0] > courbe[1] > courbe[2]


def test_grille_et_meilleur_couple():
    df = generer_marche("haussier", jours=2, graine=1)
    courts, longs = [2, 5, 10], [5, 10, 20]
    g = an.grille_mm(df, courts, longs)
    assert g.shape == (3, 3)
    for i, c in enumerate(courts):
        for j, l in enumerate(longs):
            assert np.isnan(g[i, j]) == (c >= l)
    c, l, v = an.meilleur_couple(g, courts, longs)
    assert v == np.nanmax(g) and c < l


def test_optimiser_puis_tester():
    r = an.optimiser_puis_tester("lateral", 0, [3, 5], [10, 20], jours=2)
    assert set(r) == {"court", "long", "dans_echantillon", "hors_echantillon",
                      "defaut_hors_echantillon", "buy_and_hold_test"}
    assert r["court"] < r["long"]


def test_surapprentissage_moyen():
    lignes = [an.optimiser_puis_tester("lateral", g, [3, 5, 8], [15, 30, 45], jours=4) for g in range(5)]
    assert np.mean([l["dans_echantillon"] for l in lignes]) > np.mean([l["hors_echantillon"] for l in lignes])


def test_kelly():
    assert an.kelly(0.5, 0.01, 0.01) == pytest.approx(0.0)
    assert an.kelly(0.6, 1.0, 1.0) == pytest.approx(0.2)          # formule classique p − q/b
    assert an.kelly(0.3, 0.01, 0.01) < 0
    assert an.kelly(0.4, 0.03, 0.01) == pytest.approx(0.4 / 0.01 - 0.6 / 0.03)
    with pytest.raises(ValueError):
        an.kelly(0.5, 0.0, 0.01)


def test_rendement_par_regime():
    df = generer_marche("regimes", graine=1)
    r = backtester(df, ParametresStrategie())
    par = an.rendement_par_regime(r, df)
    assert set(par) == set(df.attrs["regimes"])
    assert sum(v["gain"] for v in par.values()) == pytest.approx(r.equity.iloc[-1] - r.equity.iloc[0])
    assert sum(v["barres"] for v in par.values()) == len(df)


# --- Bot avec d'autres stratégies --------------------------------------------
@pytest.mark.parametrize("nom", ["cassure", "rsi", "bollinger", "momentum", "mm_filtre"])
def test_bot_avec_chaque_strategie(nom):
    courtier = CourtierSimule(generer_marche("vague", jours=2, graine=1), capital=10_000)
    final = executer_bot(courtier, "SIMU", creer(nom), budget=10_000, envoyer=True, pause=0,
                         perte_max=0.9, arret_si_ferme=True, journal=lambda m: None,
                         dormir=lambda s: None)
    sens = [o[0] for o in courtier.ordres]
    assert all(a != b for a, b in zip(sens, sens[1:]))
    assert courtier.pos.quantite >= 0
    assert final == pytest.approx(courtier.compte()["capital"])


# --- Cas illustrés ---------------------------------------------------------------
@pytest.mark.parametrize("nom", list(cas.CAS))
def test_chaque_cas(nom, capsys, tmp_path):
    import matplotlib
    matplotlib.use("Agg")
    ctx = cas.Contexte(graines=2, sauver=str(tmp_path))
    cas.lancer(nom, ctx)
    sortie = capsys.readouterr().out
    assert sortie.strip()
    assert not re.search(r"\bnan\b", sortie.lower())
    assert list(tmp_path.glob("*.png")), f"le cas {nom} n'a produit aucune figure"


def test_cas_marches_identique_a_l_original(capsys):
    principal.main(["cas"])
    sortie = capsys.readouterr().out
    assert "CAS ILLUSTRÉS" in sortie and "krach" in sortie
    lignes = [l for l in sortie.splitlines() if l.startswith(("haussier", "krach"))]
    assert lignes[1].split()[1] == "-24.9%"                      # buy & hold du krach (README)


def test_liste_des_cas(capsys):
    cas.liste()
    sortie = capsys.readouterr().out
    assert all(n in sortie for n in cas.CAS)
    assert len(cas.CAS) == 14


# --- Ligne de commande --------------------------------------------------------------
def test_cli_cas_liste_et_nom(capsys):
    principal.main(["cas", "--liste"])
    assert "monte_carlo" in capsys.readouterr().out
    principal.main(["cas", "--nom", "metriques"])
    assert "Recalcul à la main" in capsys.readouterr().out


def test_cli_comparer(capsys):
    principal.main(["comparer", "--scenario", "vague", "--jours", "2"])
    sortie = capsys.readouterr().out
    assert sortie.count("%") > 20 and "Bollinger" in sortie and "acheter et garder" in sortie


def test_cli_montecarlo(capsys):
    principal.main(["montecarlo", "--scenario", "lateral", "--graines", "3", "--jours", "2",
                    "--strategie", "rsi", "--fenetre", "10"])
    sortie = capsys.readouterr().out
    assert "RSI 10" in sortie and "probabilité de gagner" in sortie


@pytest.mark.parametrize("nom", ["mm", "mm_filtre", "cassure", "momentum", "rsi", "bollinger", "tenir"])
def test_cli_backtest_strategie(nom, capsys):
    principal.main(["backtest", "--scenario", "regimes", "--jours", "2", "--strategie", nom])
    assert "Rendement stratégie" in capsys.readouterr().out


def test_cli_simulation_strategie(capsys):
    principal.main(["simulation", "--scenario", "vague", "--jours", "2", "--strategie", "bollinger"])
    assert "ordres exécutés" in capsys.readouterr().out


def test_cli_scenario_etendu_refuse_inconnu():
    with pytest.raises(SystemExit):
        principal.main(["backtest", "--scenario", "licorne"])
