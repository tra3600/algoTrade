import pytest

from algotrade.strategy import Signal, crossover_signal, decide, sma


def test_sma():
    assert sma([1, 2, 3, 4], 2) == 3.5
    with pytest.raises(ValueError):
        sma([1], 2)


def test_signal_achat_sur_croisement_haussier():
    closes = [10, 10, 10, 10, 9, 12]
    assert crossover_signal(closes, 2, 4) is Signal.BUY


def test_signal_vente_sur_croisement_baissier():
    closes = [10, 10, 10, 10, 11, 8]
    assert crossover_signal(closes, 2, 4) is Signal.SELL


def test_pas_de_signal_repete_si_deja_au_dessus():
    # la moyenne courte reste au-dessus : pas de nouvel achat a chaque bougie
    closes = [10, 10, 10, 10, 9, 12, 13]
    assert crossover_signal(closes, 2, 4) is Signal.HOLD


def test_pas_assez_de_donnees():
    assert crossover_signal([1, 2, 3], 2, 4) is Signal.HOLD


@pytest.mark.parametrize(
    "signal,has_position,expected",
    [
        (Signal.BUY, False, Signal.BUY),
        (Signal.BUY, True, Signal.HOLD),
        (Signal.SELL, True, Signal.SELL),
        (Signal.SELL, False, Signal.HOLD),  # pas de vente a decouvert
        (Signal.HOLD, True, Signal.HOLD),
    ],
)
def test_decide(signal, has_position, expected):
    assert decide(signal, has_position) is expected
