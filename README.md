# algoTrade

Bot de trading algorithmique pour les actions US via [Alpaca](https://alpaca.markets),
basé sur le SDK officiel [`alpaca-py`](https://github.com/alpacahq/alpaca-py).

## Fonctionnement

1. **Sélection** : l'action la plus échangée (en volume) du jour, dans une fourchette de prix
   (`MIN_PRICE`–`MAX_PRICE`) pour éviter les penny stocks. On peut aussi fixer `SYMBOL`.
2. **Signal** : croisement de moyennes mobiles sur les bougies 1 minute
   (`SHORT_WINDOW` / `LONG_WINDOW`). On achète au croisement haussier et on vend au croisement baissier.
3. **Gestion du risque** :
   - taille de position = `POSITION_FRACTION` du capital, limitée au pouvoir d'achat ;
   - ordre *bracket* : stop-loss et take-profit sont posés chez le broker dès l'achat
     (ils restent actifs même si le bot s'arrête) ;
   - pas de vente à découvert, une seule position à la fois ;
   - arrêt du trading (et fermeture de la position) si la perte du jour dépasse `MAX_DAILY_LOSS_PCT` ;
   - aucun ordre quand le marché est fermé.

## Installation

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env   # puis renseigner les clés API
pytest
```

## Utilisation

```bash
python -m algotrade account            # état du compte
python -m algotrade select             # action qui serait tradée
python -m algotrade backtest --days 5  # test de la stratégie sur l'historique récent
python -m algotrade run                # lance le bot
```

Par défaut, le bot tourne sur le **compte paper** (`ALPACA_PAPER=true`) et en **simulation** (`DRY_RUN=true`) :
il journalise ses décisions sans envoyer d'ordres. Passez `DRY_RUN=false` pour envoyer des ordres sur le compte paper,
et ne passez `ALPACA_PAPER=false` (argent réel) qu'après un backtest et plusieurs semaines de paper trading concluants.

## Structure

```
algotrade/
  config.py     paramètres (.env)
  strategy.py   signal de croisement de moyennes mobiles (logique pure)
  risk.py       taille de position, stop-loss / take-profit, perte journalière max
  selection.py  choix de l'action
  backtest.py   backtest sur l'historique
  bot.py        boucle de trading
  __main__.py   ligne de commande
tests/          tests unitaires (clients Alpaca simulés, aucun appel réseau)
```

## Changements par rapport à la version initiale

L'ancienne version ne pouvait pas fonctionner :
- les trois scripts ne s'importaient pas entre eux (`api`, `np`, `selected_stock` non définis) ;
- `get_barset` n'existe plus dans l'API Alpaca, et `alpaca-trade-api` est remplacé par `alpaca-py` ;
- la stratégie envoyait un ordre d'achat **chaque minute** tant que la moyenne courte restait au-dessus
  de la longue (position illimitée), et des ventes à découvert sans position ;
- aucun stop-loss, aucune vérification des heures de marché, clés API dans le code.

## Avertissement

Ce code est fourni à titre éducatif. Une stratégie de croisement de moyennes mobiles sur 1 minute est
très sensible aux frais et au slippage, et **n'est pas rentable par défaut** : utilisez le backtest et le compte paper.
Le backtest est simplifié (exécution au prix de clôture, stop vérifié sur les clôtures).
