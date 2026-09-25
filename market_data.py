"""Récupération des bougies historiques Alpaca sous forme de DataFrame."""
from datetime import datetime, timedelta, timezone

import pandas as pd
from alpaca.data.enums import DataFeed
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

COLUMNS = ["open", "high", "low", "close", "volume"]


def get_bars(data_client, symbols, timeframe_minutes: int, start: datetime,
             end: datetime | None = None, feed: str = "iex") -> dict[str, pd.DataFrame]:
    """Renvoie {symbole: DataFrame(open, high, low, close, volume)} indexé par timestamp."""
    if isinstance(symbols, str):
        symbols = [symbols]
    tf = TimeFrame(timeframe_minutes, TimeFrameUnit.Minute) if timeframe_minutes < 1440 else TimeFrame.Day
    request = StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=tf,
        start=start,
        end=end,
        feed=DataFeed(feed),
    )
    df = data_client.get_stock_bars(request).df
    result: dict[str, pd.DataFrame] = {}
    if df is None or df.empty:
        return result
    for symbol in symbols:
        if symbol in df.index.get_level_values(0):
            result[symbol] = df.xs(symbol, level=0)[COLUMNS].sort_index()
    return result


def get_recent_bars(data_client, symbol: str, timeframe_minutes: int, lookback_bars: int,
                    feed: str = "iex") -> pd.DataFrame:
    """Dernières bougies *clôturées* d'un symbole (la bougie en cours est exclue)."""
    now = datetime.now(timezone.utc)
    # Marge large pour couvrir les périodes sans cotation (nuit, week-end)
    start = now - timedelta(minutes=timeframe_minutes * lookback_bars * 3) - timedelta(days=4)
    bars = get_bars(data_client, symbol, timeframe_minutes, start, feed=feed).get(symbol)
    if bars is None:
        return pd.DataFrame(columns=COLUMNS)
    current_bar_start = pd.Timestamp(now).floor(f"{timeframe_minutes}min")
    bars = bars[bars.index < current_bar_start]
    return bars.tail(lookback_bars)
