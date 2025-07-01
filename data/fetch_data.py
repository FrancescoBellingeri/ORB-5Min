from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from datetime import datetime, timedelta, timezone
import os
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv('API_KEY')
SECRET_KEY = os.getenv('API_SECRET')

client = StockHistoricalDataClient(API_KEY, SECRET_KEY)

# Definiamo un periodo storico specifico per il backtesting
end_date = datetime(2025, 6, 26)
start_date = datetime(2016, 1, 1)   # Dall'inizio del 2016

timeframe = TimeFrame(5, TimeFrameUnit.Minute)

request_params = StockBarsRequest(
    symbol_or_symbols="QQQ",
    timeframe=timeframe,
    start=start_date,
    end=end_date
)

try:
    bars = client.get_stock_bars(request_params)
    df = bars.df
    
    # Pulizia e preparazione dei dati
    if isinstance(df.index, pd.MultiIndex):
        df = df.reset_index()
    
    # Mostra le prime righe e alcune informazioni sul dataset
    print("Prime 5 righe del dataset:")
    print(df.head())
    print("\nInformazioni sul dataset:")
    print(f"Periodo: dal {df['timestamp'].min()} al {df['timestamp'].max()}")
    print(f"Numero totale di candele: {len(df)}")
    
    # Opzionale: salva i dati in un file CSV
    df.to_csv('data/qqq_5Min.csv', index=False)
    print("\nDati salvati in 'qqq_5Min.csv'")

except Exception as e:
    print(f"Errore: {e}")