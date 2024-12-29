def scalping_strategy(api, stock, quantity):
    while True:
        # Récupérer les données de marché en temps réel
        barset = api.get_barset(stock, 'minute', limit=5)
        bars = barset[stock]

        # Calculer les moyennes mobiles
        close_prices = np.array([bar.c for bar in bars])
        short_ma = np.mean(close_prices[-3:])
        long_ma = np.mean(close_prices)

        # Critères d'achat et de vente
        if short_ma > long_ma:
            # Acheter l'action
            api.submit_order(
                symbol=stock,
                qty=quantity,
                side='buy',
                type='market',
                time_in_force='gtc'
            )
            print(f"Bought {quantity} shares of {stock}")
        elif short_ma < long_ma:
            # Vendre l'action
            api.submit_order(
                symbol=stock,
                qty=quantity,
                side='sell',
                type='market',
                time_in_force='gtc'
            )
            print(f"Sold {quantity} shares of {stock}")

        # Attendre une minute avant la prochaine itération
        time.sleep(60)

# Exécuter la stratégie de scalping
quantity = 10  # Quantité d'actions à acheter/vendre
scalping_strategy(api, selected_stock, quantity)