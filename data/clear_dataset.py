import pandas as pd
import numpy as np
from pandas.tseries.holiday import USFederalHolidayCalendar
import pytz
from datetime import datetime, time

# Importiamo il dataset
df = pd.read_csv('data/QQQ_1Min.csv')

# Convertiamo la colonna timestamp in datetime e la convertiamo in ET (Eastern Time)
df['timestamp'] = pd.to_datetime(df['timestamp'])
et_tz = pytz.timezone('America/New_York')
df['timestamp'] = df['timestamp'].dt.tz_convert(et_tz)

# Rimuoviamo i weekend
df = df[df['timestamp'].dt.dayofweek < 5]

# Rimuoviamo i giorni festivi
cal = USFederalHolidayCalendar()
holidays = cal.holidays(start=datetime(2016, 1, 1), end=datetime(2025, 6, 1))
df = df[~df['timestamp'].dt.date.isin(holidays)]

# Filtriamo solo per l'orario di mercato (9:30-16:00 ET)
df = df[
    (df['timestamp'].dt.time >= time(9, 30)) & 
    (df['timestamp'].dt.time <= time(16, 0))
]

# Ordiniamo per timestamp
df = df.sort_values('timestamp')

# Aggiungiamo una colonna per identificare il giorno di trading
df['trading_day'] = df['timestamp'].dt.date

# Verifichiamo che ogni giorno abbia la prima candela alle 9:30 e l'ultima alle 16:00
valid_days = df.groupby('trading_day').agg({
    'timestamp': [
        lambda x: x.dt.time.min() == time(9, 30),
        lambda x: x.dt.time.max() == time(16, 0)
    ]
}).all(axis=1)

valid_days = valid_days[valid_days].index
df = df[df['trading_day'].isin(valid_days)]

# Salviamo il dataset pulito
df.to_csv('data/QQQ_1Min_cleared2.csv', index=False)

print(f"Righe nel dataset originale: {len(df)}")
print(f"Giorni di trading validi: {len(valid_days)}")
print(f"Prima data: {df['trading_day'].min()}")
print(f"Ultima data: {df['trading_day'].max()}")