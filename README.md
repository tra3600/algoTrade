# algoTrade

Algorithme de trading (scalping intraday) sur actions US via l'API [Alpaca](https://alpaca.markets).

## Stratégie

- **Sélection** : action la plus échangée du jour (screener Alpaca), filtrée par bourse et prix (5–500 $).
- **Entrée (achat)** : l'EMA 9 croise au-dessus de l'EMA 21 sur des bougies 1 minute, avec
  RSI(14) < 70, clôture au-dessus de l'EMA 21 et volume supérieur à sa moyenne 20 périodes.
- **Sortie** : ordre *bracket* côté serveur avec stop-loss à 1,5 × ATR et objectif à 3 × ATR,
  ou croisement baissier des EMA, ou RSI > 80.
- **Gestion du risque** : 0,5 % du capital risqué par trade, position max 20 % du capital,
  arrêt après −2 % sur la journée, 20 trades/jour max, aucune entrée dans les 15 dernières
  minutes et clôture de toutes les positions 5 minutes avant la fermeture.
- Positions longues uniquement (pas de vente à découvert).

Tous les paramètres sont réglables dans `config.py`.

## Installation

```bash
pip install -r requirements.txt
cp .env.example .env   # puis renseigner vos clés Alpaca (paper trading par défaut)
```

## Utilisation

```bash
python main.py account                          # infos du compte
python main.py select                           # action retenue aujourd'hui
python main.py backtest --symbol AAPL --days 10 # test sur l'historique
python main.py live --dry-run                   # temps réel, sans passer d'ordres
python main.py live                             # trading (compte paper si ALPACA_PAPER=true)
python main.py live --symbol TSLA               # forcer un symbole
```

`Ctrl+C` arrête le programme et clôture la position ouverte (sauf avec `--keep-position-on-exit`).

## Tests

```bash
python -m pytest
```

## Structure

| Fichier | Rôle |
|---|---|
| `config.py` | Paramètres et lecture des clés API (variables d'environnement / `.env`) |
| `alpaca_connect.py` | Création des clients Alpaca (trading, données, screener) |
| `market_data.py` | Récupération des bougies historiques |
| `trade_volume.py` | Sélection de l'action la plus active |
| `signals.py` | Indicateurs (EMA, RSI, ATR), signaux et dimensionnement des positions |
| `scalp_strategy.py` | Boucle de trading en temps réel |
| `backtest.py` | Backtest de la stratégie |
| `main.py` | Point d'entrée en ligne de commande |

> ⚠️ Testez toujours en paper trading avant tout usage réel. Le scalping sur données IEX
> gratuites (une fraction du volume du marché) peut donner des signaux différents des données SIP.
> Aucune performance n'est garantie.
