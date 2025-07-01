import alpaca_trade_api as tradeapi
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetAssetsRequest
from alpaca.trading.enums import AssetClass
import pandas as pd
import numpy as np
from datetime import datetime, time, timedelta
import pytz, os
import logging
from dotenv import load_dotenv

# Carica le variabili dal file .env
load_dotenv()

# Configurazione del logging
logging.basicConfig(
    filename='live_trading.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Configurazione delle API Alpaca
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
ALPACA_BASE_URL = os.getenv("ALPACA_BASE_URL")

# Inizializzazione dell'API
api = tradeapi.REST(API_KEY, API_SECRET, ALPACA_BASE_URL, api_version='v2')

# Simbolo da tradare
SYMBOL = 'QQQ'

def is_market_open():
    """ Verifica se il mercato è aperto """
    clock = api.get_clock()
    return clock.is_open

def wait_for_market_open():
    """ Attende l'apertura del mercato """
    clock = api.get_clock()
    if not clock.is_open:
        time_to_open = clock.next_open - clock.timestamp
        logging.info(f'Mercato chiuso. Apertura tra {time_to_open.total_seconds()/60:.2f} minuti')
        time.sleep(time_to_open.total_seconds())

def get_current_position():
    """ Ottiene la posizione corrente per il simbolo """
    try:
        position = api.get_position(SYMBOL)
        return float(position.qty)
    except:
        return 0
    
def get_account_equity():
    """ Ottiene il capitale corrente del conto """
    account = api.get_account()
    return float(account.equity)

def get_current_bars():
    """ Ottiene le candele più recenti per calcolare il DR """
    now = datetime.now(pytz.timezone('America/New_York'))
    start = now.replace(hour=9, minute=30, second=0, microsecond=0)
    
    try:
        bars = api.get_bars(
            SYMBOL,
            tradeapi.TimeFrame(5, tradeapi.TimeFrameUnit.Minute),
            start.isoformat(),
            now.isoformat(),
            adjustment='raw'
        ).df
        
        return bars
    except Exception as e:
        logging.error(f"Errore nel recupero delle barre: {e}")
        return None
    
print(get_current_bars())