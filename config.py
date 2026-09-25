"""Configuration centrale de l'algorithme.

Les clés API sont lues depuis les variables d'environnement (ou un fichier .env),
jamais écrites en dur dans le code.
"""
import os
from dataclasses import dataclass, field


def _load_dotenv(path: str = ".env") -> None:
    """Charge un fichier .env minimal (KEY=VALUE) sans dépendance externe."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "oui", "on")


@dataclass
class StrategyConfig:
    # Indicateurs
    ema_fast: int = 9
    ema_slow: int = 21
    rsi_period: int = 14
    rsi_overbought: float = 70.0   # pas d'achat au-dessus
    rsi_exit: float = 80.0         # sortie forcée si le RSI dépasse ce niveau
    atr_period: int = 14
    volume_ma_period: int = 20
    require_volume_confirmation: bool = True

    # Gestion du risque
    stop_loss_atr_mult: float = 1.5
    take_profit_atr_mult: float = 3.0
    risk_per_trade: float = 0.005       # 0.5 % du capital risqué par trade
    max_position_pct: float = 0.20      # position max = 20 % du capital
    max_daily_loss_pct: float = 0.02    # arrêt du trading après -2 % sur la journée
    max_trades_per_day: int = 20

    # Horaires (minutes avant la clôture)
    no_new_entries_before_close_min: int = 15
    flatten_before_close_min: int = 5

    # Boucle
    timeframe_minutes: int = 1
    lookback_bars: int = 100


@dataclass
class SelectionConfig:
    top_n: int = 20             # nombre de titres les plus actifs examinés
    min_price: float = 5.0
    max_price: float = 500.0
    exchanges: tuple = ("NASDAQ", "NYSE", "ARCA", "NYSEARCA", "AMEX", "BATS")


@dataclass
class Config:
    api_key: str = ""
    secret_key: str = ""
    paper: bool = True
    data_feed: str = "iex"
    dry_run: bool = False
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    selection: SelectionConfig = field(default_factory=SelectionConfig)

    @classmethod
    def from_env(cls) -> "Config":
        _load_dotenv()
        return cls(
            api_key=os.getenv("ALPACA_API_KEY", ""),
            secret_key=os.getenv("ALPACA_SECRET_KEY", ""),
            paper=_env_bool("ALPACA_PAPER", True),
            data_feed=os.getenv("ALPACA_DATA_FEED", "iex").lower(),
        )

    def validate(self) -> None:
        if not self.api_key or not self.secret_key or self.api_key == "your_api_key":
            raise ValueError(
                "Clés API manquantes : définissez ALPACA_API_KEY et ALPACA_SECRET_KEY "
                "(voir .env.example)."
            )
