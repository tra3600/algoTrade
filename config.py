"""Configuration : clés API lues dans l'environnement (ou un fichier .env), jamais dans le code."""

import os
from dataclasses import dataclass


def charger_env(chemin=".env"):
    """Charge un fichier .env simple (CLE=valeur) sans écraser l'environnement existant."""
    if not os.path.exists(chemin):
        return
    with open(chemin, encoding="utf-8") as f:
        for ligne in f:
            ligne = ligne.strip()
            if not ligne or ligne.startswith("#") or "=" not in ligne:
                continue
            cle, valeur = ligne.split("=", 1)
            os.environ.setdefault(cle.strip(), valeur.strip().strip("'\""))


@dataclass
class Config:
    api_key: str
    secret_key: str
    paper: bool = True

    @classmethod
    def depuis_env(cls):
        charger_env()
        api_key = os.environ.get("ALPACA_API_KEY", "")
        secret_key = os.environ.get("ALPACA_SECRET_KEY", "")
        if not api_key or not secret_key:
            raise SystemExit(
                "Clés Alpaca manquantes : définis ALPACA_API_KEY et ALPACA_SECRET_KEY "
                "(voir .env.example). Le mode « backtest » fonctionne sans clés.")
        # Compte de démonstration par défaut : il faut le désactiver explicitement.
        paper = os.environ.get("ALPACA_PAPER", "true").lower() not in ("false", "0", "non", "no")
        return cls(api_key, secret_key, paper)
