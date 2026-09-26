"""Tests hors ligne (aucune clé API nécessaire) : python -m pytest -q"""

import numpy as np
import pandas as pd
import pytest

from alpaca_connect import CourtierSimule
from backtest import backtester
from bot import executer_bot
from config import Config
from donnees import SCENARIOS, charger_csv, generer_marche
from scalp_strategy import ACHAT, VENTE, ParametresStrategie, croisement, decider, moyennes_mobiles
from trade_volume import choisir

P = ParametresStrategie(court=2, long=4, stop_loss=0.05, take_profit=0.10)


def _df(closes):
    closes = np.asarray(closes, dtype=float)
    idx = pd.date_range("2026-01-05 09:30", periods=len(closes), freq="min")
    return pd.DataFrame({"open": closes, "high": closes, "low": closes, "close": closes,
                         "volume": 1000}, index=idx)


# --- Stratégie ----------------------------------------------------------
def test_moyennes_mobiles():
    mm = moyennes_mobiles([1, 2, 3, 4, 5], 3)
    assert np.isnan(mm[:2]).all()
    assert mm[2:].tolist() == [2, 3, 4]


def test_parametres_invalides():
    with pytest.raises(ValueError):
        ParametresStrategie(court=20, long=5)


def test_croisement_haussier_puis_baissier():
    assert croisement([10, 10, 10, 10, 12], P) == ACHAT
    assert croisement([10, 10, 10, 10, 8], P) == VENTE
    assert croisement([10, 11, 12, 13, 14], P) is None  # déjà au-dessus : pas de nouveau signal
    assert croisement([10, 10], P) is None               # pas assez de données


def test_pas_de_rachat_ni_vente_a_decouvert():
    # Déjà en position : un croisement haussier ne déclenche pas un 2e achat.
    assert decider([10, 10, 10, 10, 10.5], True, 10.0, P).action is None
    # Sans position : un croisement baissier ne déclenche pas de vente.
    assert decider([10, 10, 10, 10, 9.9], False, 0.0, P).action is None


def test_stop_loss_et_take_profit():
    d = decider([100] * 5 + [94], True, 100.0, P)
    assert d.action == VENTE and "stop-loss" in d.raison
    d = decider([100] * 5 + [111], True, 100.0, P)
    assert d.action == VENTE and "take-profit" in d.raison


# --- Backtest -----------------------------------------------------------
def test_backtest_sans_lecture_de_l_avenir():
    # Le signal apparaît à la clôture de la barre 4 ; on achète à l'ouverture de la barre 5.
    closes = [10, 10, 10, 10, 12, 13, 14, 15, 16, 17]
    df = _df(closes)
    df["open"] = df["close"].shift(1).fillna(10) + 0.5
    sans_sortie = ParametresStrategie(court=2, long=4, stop_loss=0, take_profit=0)
    res = backtester(df, sans_sortie, capital=1000, frais=0, glissement=0)
    assert res.equity.iloc[:5].eq(1000).all()
    # Position encore ouverte : elle n'apparaît pas dans les transactions clôturées...
    assert res.transactions == []
    # ...mais elle est valorisée : 80 actions achetées à l'ouverture de la barre 5 (12,5 $).
    assert res.equity.iloc[-1] == pytest.approx(1000 - 80 * 12.5 + 80 * 17)


def test_backtest_aller_retour_et_frais():
    closes = [10, 10, 10, 10, 12, 12, 12, 9, 9, 9]
    res = backtester(_df(closes), ParametresStrategie(2, 4, 0, 0), capital=1200,
                     frais=0.01, glissement=0)
    assert len(res.transactions) == 1
    t = res.transactions[0]
    assert t.entree_prix == 12 and t.sortie_prix == 9 and t.gain < 0
    assert res.frais_payes == pytest.approx(t.quantite * (12 + 9) * 0.01)
    assert res.equity.iloc[-1] == pytest.approx(1200 - t.quantite * 12 * 1.01 + t.quantite * 9 * 0.99)


def test_frais_toujours_penalisants():
    df = generer_marche("lateral", jours=2)
    assert backtester(df, frais=0.001).rendement_total < backtester(df, frais=0).rendement_total


@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_scenarios_generes(scenario):
    df = generer_marche(scenario, jours=2, graine=3)
    assert len(df) == 780
    assert (df["high"] >= df[["open", "close"]].max(axis=1)).all()
    assert (df["low"] <= df[["open", "close"]].min(axis=1)).all()
    assert (df["close"] > 0).all()
    res = backtester(df)
    assert set(res.resume()) >= {"Rendement stratégie", "Drawdown max"}
    assert -1 < res.drawdown_max <= 0


def test_scenarios_ont_la_bonne_direction():
    for g in range(3):
        assert generer_marche("haussier", graine=g)["close"].iloc[-1] > 100
        assert generer_marche("baissier", graine=g)["close"].iloc[-1] < 100
        assert generer_marche("krach", graine=g)["close"].iloc[-1] < 95


def test_charger_csv(tmp_path):
    chemin = tmp_path / "prix.csv"
    chemin.write_text("date,Close\n2026-01-05,10\n2026-01-06,11\n")
    df = charger_csv(chemin)
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df["open"].tolist() == [10, 11]


# --- Sélection ----------------------------------------------------------
def test_selection_ignore_les_penny_stocks():
    candidats = [("PENNY", 9e8), ("AAPL", 5e7), ("TSLA", 8e7)]
    prix = {"PENNY": 0.5, "AAPL": 230.0, "TSLA": 250.0}
    assert choisir(candidats, prix) == "TSLA"
    assert choisir(candidats, prix, exclure={"TSLA"}) == "AAPL"
    assert choisir(candidats, prix, prix_min=1000) is None


# --- Bot ----------------------------------------------------------------
def test_bot_simule_coherent_avec_backtest():
    df = generer_marche("haussier", jours=2)
    courtier = CourtierSimule(df, capital=10_000)
    final = executer_bot(courtier, "SIMU", ParametresStrategie(), budget=10_000, envoyer=True,
                         pause=0, perte_max=0.5, arret_si_ferme=True, journal=lambda m: None,
                         dormir=lambda s: None)
    assert courtier.ordres, "le bot aurait dû passer des ordres"
    # Achats et ventes alternent : jamais deux achats de suite.
    sens = [o[0] for o in courtier.ordres]
    assert all(a != b for a, b in zip(sens, sens[1:]))
    assert courtier.pos.quantite >= 0
    assert final == pytest.approx(courtier.compte()["capital"])


def test_bot_a_blanc_n_envoie_rien():
    courtier = CourtierSimule(generer_marche("volatil", jours=1))
    executer_bot(courtier, "SIMU", ParametresStrategie(), envoyer=False, pause=0,
                 arret_si_ferme=True, journal=lambda m: None, dormir=lambda s: None)
    assert courtier.ordres == []


def test_coupe_circuit():
    closes = [100] * 40 + [101] * 3 + [60] * 20  # achat puis effondrement
    courtier = CourtierSimule(_df(closes), capital=10_000, frais=0, glissement=0)
    journal = []
    executer_bot(courtier, "SIMU", ParametresStrategie(2, 4, 0, 0), budget=10_000, envoyer=True,
                 pause=0, perte_max=0.05, arret_si_ferme=True, journal=journal.append,
                 dormir=lambda s: None)
    assert any("Coupe-circuit" in m for m in journal)


# --- Configuration ------------------------------------------------------
def test_config_paper_par_defaut(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "s")
    monkeypatch.delenv("ALPACA_PAPER", raising=False)
    assert Config.depuis_env().paper is True
    monkeypatch.setenv("ALPACA_PAPER", "false")
    assert Config.depuis_env().paper is False


def test_config_sans_cles(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    with pytest.raises(SystemExit):
        Config.depuis_env()
