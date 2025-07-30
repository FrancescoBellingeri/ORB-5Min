import pandas as pd
import numpy as np
from pandas.tseries.holiday import USFederalHolidayCalendar
import pytz
from datetime import datetime, time

# Importiamo il dataset
df = pd.read_csv('data/MNQ_30Min.csv')

# Rimuoviamo le colonne temporanee se non servono
df['timestamp'] = df['timestamp'].str[:-6]

# Salviamo il dataset pulito
df.to_csv('data/MNQ_30Min.csv', index=False)