import pandas as pd

# === STEP 1: carica i dati ===
df = pd.read_csv('MNQ_30Min.csv')

# Assicurati che 'date' sia datetime
df['date'] = pd.to_datetime(df['date'], utc=True)

# Estrai solo la data (senza ora) per raggruppare per giorno
df['day'] = df['date'].dt.date

# === STEP 2: funzione per calcolare il VWAP per un singolo giorno ===
def calcola_vwap_per_giorno(giorno_df):
    # Calcola prezzo * volume per ogni barra
    giorno_df['pv'] = giorno_df['average'] * giorno_df['volume']
    
    # Calcola cumulativi
    giorno_df['cum_pv'] = giorno_df['pv'].cumsum()
    giorno_df['cum_vol'] = giorno_df['volume'].cumsum()
    
    # VWAP = somma(p*v) / somma(v)
    giorno_df['vwap'] = giorno_df['cum_pv'] / giorno_df['cum_vol']
    
    return giorno_df

# === STEP 3: applica la funzione a ogni giorno ===
df = df.groupby('day', group_keys=False).apply(calcola_vwap_per_giorno)

# === STEP 4: salva o mostra i risultati ===
df.to_csv('data/MNQ_vwap.csv', index=False)
print(df[['date', 'average', 'volume', 'vwap']].head(15))

# Optional: puoi rimuovere le colonne temporanee se non ti servono
df = df.drop(['pv', 'cum_pv', 'cum_vol'], axis=1)