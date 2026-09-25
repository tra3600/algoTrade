"""Configuration lue depuis les variables d'environnement (fichier .env accepte)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


def _bool(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "oui", "on"}


@dataclass(frozen=True)
class Settings:
    api_key: str
    secret_key: str
    paper: bool = True
    dry_run: bool = True
    symbol: str | None = None
    short_window: int = 9
    long_window: int = 21
    position_fraction: float = 0.10
    stop_loss_pct: float = 0.01
    take_profit_pct: float = 0.02
    max_daily_loss_pct: float = 0.03
    interval_seconds: int = 60
    min_price: float = 5.0
    max_price: float = 500.0
    data_feed: str = "iex"

    def __post_init__(self) -> None:
        if self.short_window < 1 or self.long_window <= self.short_window:
            raise ValueError("Il faut 1 <= SHORT_WINDOW < LONG_WINDOW")
        if not 0 < self.position_fraction <= 1:
            raise ValueError("POSITION_FRACTION doit etre dans ]0, 1]")
        if self.stop_loss_pct <= 0 or self.take_profit_pct <= 0:
            raise ValueError("STOP_LOSS_PCT et TAKE_PROFIT_PCT doivent etre > 0")

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        api_key = os.getenv("ALPACA_API_KEY", "")
        secret_key = os.getenv("ALPACA_SECRET_KEY", "")
        if not api_key or not secret_key:
            raise RuntimeError("ALPACA_API_KEY et ALPACA_SECRET_KEY sont requis (voir .env.example)")
        env = os.getenv
        return cls(
            api_key=api_key,
            secret_key=secret_key,
            paper=_bool(env("ALPACA_PAPER"), True),
            dry_run=_bool(env("DRY_RUN"), True),
            symbol=env("SYMBOL") or None,
            short_window=int(env("SHORT_WINDOW", "9")),
            long_window=int(env("LONG_WINDOW", "21")),
            position_fraction=float(env("POSITION_FRACTION", "0.10")),
            stop_loss_pct=float(env("STOP_LOSS_PCT", "0.01")),
            take_profit_pct=float(env("TAKE_PROFIT_PCT", "0.02")),
            max_daily_loss_pct=float(env("MAX_DAILY_LOSS_PCT", "0.03")),
            interval_seconds=int(env("INTERVAL_SECONDS", "60")),
            min_price=float(env("MIN_PRICE", "5")),
            max_price=float(env("MAX_PRICE", "500")),
            data_feed=env("DATA_FEED", "iex"),
        )
