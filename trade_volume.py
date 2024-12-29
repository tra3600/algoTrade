def select_stock(api):
    # Récupérer les données de marché pour les actions les plus actives
    active_stocks = api.get_assets(status='active')
    
    # Filtrer les actions éligibles (par exemple, uniquement les actions du NASDAQ)
    nasdaq_stocks = [stock.symbol for stock in active_stocks if stock.exchange == 'NASDAQ']

    # Récupérer les données historiques des actions éligibles
    end_date = pd.Timestamp.now(tz='America/New_York')
    start_date = end_date - pd.Timedelta(days=1)
    barset = api.get_barset(nasdaq_stocks, 'day', start=start_date, end=end_date)

    # Choisir l'action avec le plus grand volume de trading
    max_volume = 0
    selected_stock = None
    for symbol in nasdaq_stocks:
        if symbol in barset and len(barset[symbol]) > 0:
            volume = barset[symbol][0].v
            if volume > max_volume:
                max_volume = volume
                selected_stock = symbol

    return selected_stock

selected_stock = select_stock(api)
print(f"Selected stock: {selected_stock}")