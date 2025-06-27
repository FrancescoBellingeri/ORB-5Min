import pandas as pd
import numpy as np
from pandas.tseries.holiday import USFederalHolidayCalendar
import pytz
from datetime import datetime

# Importiamo il dataset
df = pd.read_csv('qqq_1MIN.csv')

# Convertiamo la colonna timestamp in datetime se non lo è già
df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
# Group by date and check if last candle is at 15:55
# Convertiamo in fuso orario New York
ny_tz = pytz.timezone('America/New_York')
df['timestamp'] = df['timestamp'].dt.tz_convert(ny_tz)


# Rimuoviamo i giorni festivi
cal = USFederalHolidayCalendar()
holidays = cal.holidays(start=datetime(2016, 1, 1), end=datetime(2025, 6, 1))
df = df[~df['timestamp'].dt.date.isin(holidays)]

# Rimuovere i weekend
df = df[df['timestamp'].dt.dayofweek < 5]

# Creiamo colonne per ora e minuti per facilitare il filtraggio
df['time'] = df['timestamp'].dt.time

# Creiamo i tempi limite del mercato
market_open = pd.Timestamp('09:30').time()
market_close = pd.Timestamp('15:55').time()

# Filtriamo solo le ore di mercato
df = df[
    (df['time'] >= market_open) & 
    (df['time'] <= market_close)
]

# Ordiniamo per timestamp
df = df.sort_values('timestamp')

# Aggiungiamo una colonna per identificare le candele positive/negative
df['candle_direction'] = np.where(df['close'] > df['open'], 'bullish', 'bearish')

# Aggiungiamo una colonna per identificare il giorno di trading
df['trading_day'] = df['timestamp'].dt.date

valid_days = df.groupby(df['timestamp'].dt.date)['timestamp'].max().dt.time == pd.Timestamp('15:55').time()
valid_days = valid_days[valid_days].index
df = df[df['timestamp'].dt.date.isin(valid_days)]

df.to_csv('QQQ_1MIN_cleared.csv', index=False)
