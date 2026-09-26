# algoTrade

Algorithme de scalping par **croisement de moyennes mobiles**, connecté au courtier
[Alpaca](https://alpaca.markets). Avant de trader, on peut **backtester** la stratégie sur
des marchés simulés ou réels, et **simuler le bot** en accéléré, sans clé API.

> ⚠️ Projet éducatif. Le trading comporte un risque de perte en capital. Par défaut,
> le programme utilise le **compte de démonstration** d'Alpaca et **n'envoie aucun ordre**.

## Installation

```sh
pip install -r requirements.txt
cp .env.example .env      # puis renseigner ALPACA_API_KEY et ALPACA_SECRET_KEY (facultatif)
```

## Utilisation

```sh
# Sans clé API
python main.py cas                               # cas illustrés sur 5 marchés simulés
python main.py cas --graphique                   # ... avec les graphiques
python main.py backtest --scenario krach --transactions --graphique
python main.py backtest --csv mes_prix.csv       # vos propres données (open,high,low,close,volume)
python main.py simulation --scenario lateral     # le bot en accéléré, avec coupe-circuit

# Avec clés API (compte de démonstration par défaut)
python main.py compte                            # capital, liquidités, pouvoir d'achat
python main.py selection                         # action la plus échangée du jour (> 5 $)
python main.py backtest --symbole AAPL --jours 5 # backtest sur l'historique réel
python main.py bot --symbole AAPL                # bot en direct, À BLANC (journal seulement)
python main.py bot --symbole AAPL --envoyer-ordres
```

Réglages communs : `--court 5 --long 20` (moyennes mobiles), `--stop 1` (stop-loss en %),
`--objectif 2` (take-profit en %). Pour le bot : `--budget`, `--quantite`, `--perte-max`.

## La stratégie

- **Achat** quand la moyenne mobile courte **croise** la longue par le haut.
- **Vente** quand elle repasse dessous, ou au **stop-loss** / **take-profit**.
- Une seule position à la fois et jamais de vente à découvert.

## Cas illustrés : que vaut vraiment ce scalping ?

`python main.py cas` joue la stratégie sur 5 jours de barres d'une minute
(capital 10 000 $, frais 0,05 % par ordre, glissement 0,02 %) :

| Marché | Buy & hold | Scalping MM 5/20 | Sans frais | Plus lent (MM 15/60) | Trades |
|---|---:|---:|---:|---:|---:|
| haussier | +5.4 % | −4.5 % | +3.5 % | +2.4 % | 58 |
| baissier | −22.8 % | −14.1 % | −7.3 % | −7.2 % | 54 |
| latéral | +0.8 % | −13.2 % | −4.3 % | −10.3 % | 70 |
| volatil | −20.3 % | −15.7 % | −8.7 % | +1.9 % | 57 |
| krach | −24.9 % | −5.5 % | +0.3 % | −0.7 % | 43 |

Ce qu'on en retient :

- **Protection dans les baisses** : pendant le krach, la stratégie sort vite du marché et
  perd 5,5 % au lieu de 25 %.
- **Le marché latéral est le pire cas** : les moyennes se croisent sans arrêt, et chaque faux
  signal coûte des frais.
- **Les frais pèsent lourd** : 50 à 70 allers-retours par semaine, c'est ce qui sépare la
  colonne « Scalping » de la colonne « Sans frais ».
- **Aucun réglage ne gagne partout.** Testez sur vos données (`--csv`, `--symbole`) et
  plusieurs graines (`--graine`) avant de risquer de l'argent.

### Krach : la stratégie reste à l'abri

![Krach](figures/cas_krach.png)

### Marché latéral : les faux signaux s'accumulent

![Latéral](figures/cas_lateral.png)

## Garde-fous du bot

| Garde-fou | Comportement |
|---|---|
| Mode à blanc | Sans `--envoyer-ordres`, le bot écrit ce qu'il ferait, sans rien envoyer |
| Compte de démonstration | Actif tant que `ALPACA_PAPER` n'est pas à `false` ; le compte réel demande de taper « JE CONFIRME » |
| Budget | La quantité est calculée pour ne pas dépasser `--budget` |
| Coupe-circuit | Arrêt si le capital baisse de plus de `--perte-max` % (3 % par défaut) |
| Robustesse | Une erreur réseau est journalisée et le bot continue ; Ctrl-C l'arrête proprement |
| Marché fermé | Le bot attend l'ouverture au lieu d'envoyer des ordres |

## Organisation du code

| Fichier | Rôle |
|---|---|
| `main.py` | ligne de commande (`cas`, `backtest`, `simulation`, `compte`, `selection`, `bot`) |
| `scalp_strategy.py` | la stratégie, une fonction pure utilisée à l'identique en backtest et en direct |
| `backtest.py` | rejeu avec frais et glissement, sans lecture de l'avenir ; métriques et graphiques |
| `donnees.py` | marchés simulés (5 scénarios), CSV, historique Alpaca |
| `alpaca_connect.py` | courtier Alpaca (SDK `alpaca-py`) et courtier simulé, avec la même interface |
| `trade_volume.py` | choix de l'action la plus active (screener Alpaca), hors penny stocks |
| `bot.py` | boucle de trading et garde-fous |
| `config.py` | clés lues dans l'environnement ou `.env`, jamais dans le code |
| `test_algotrade.py` | 21 tests hors ligne (`python -m pytest -q`) |

## Ce qui a changé par rapport à la première version

- Les trois scripts ne pouvaient pas s'exécuter : ils utilisaient des variables définies
  dans d'autres fichiers (`api`, `np`, `time`, `selected_stock`).
- `get_barset` n'existe plus dans l'API Alpaca. Le code utilise maintenant le SDK officiel `alpaca-py`.
- L'ancien code rachetait 10 actions **chaque minute** tant que la MM courte restait
  au-dessus de la longue, et pouvait vendre à découvert sans le vouloir. Il n'agit plus
  qu'aux croisements, et ne vend que ce qu'il détient.
- Les ordres au marché étaient en `gtc`. Ils sont maintenant valables pour la journée (`day`).
- Les clés API ne sont plus écrites dans le code.
- La sélection d'action ne demande plus les barres de milliers de symboles du NASDAQ.
  Elle utilise le screener d'Alpaca et écarte les actions à moins de 5 $.
