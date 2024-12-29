import alpaca_trade_api as tradeapi
import pandas as pd
import numpy as np
import time

# Configuration de l'API Alpaca
API_KEY = 'your_api_key'
SECRET_KEY = 'your_secret_key'
BASE_URL = 'https://paper-api.alpaca.markets'  # Utilisation de l'API de test

api = tradeapi.REST(API_KEY, SECRET_KEY, BASE_URL, api_version='v2')
account = api.get_account()

print(f"Account equity: {account.equity}")