from ib_insync import *
import pandas as pd
from datetime import datetime, timedelta
import pytz

# Creare una connessione con IB
ib = IB()

# Connessione al TWS o IB Gateway
# Per paper trading usa: port=7497
# Per account reale usa: port=7496
ib.connect('127.0.0.1', port=7497, clientId=1)

contracts = ib.reqContractDetails(Future('MNQ', exchange='CME'))
if contracts:
    contract = contracts[0].contract
    print(f"Userà il contratto: {contract}")
else:
    print("Nessun contratto trovato per NQ")


# Definizione del contratto per il NQ futures
contract = ContFuture(symbol='MNQ', exchange='CME', currency='USD')
ib.qualifyContracts(contract)

# Funzione per scaricare i dati storici
def download_historical_data(contract, duration, barSize):
    bars = ib.reqHistoricalData(
        contract,
        endDateTime='', 
        durationStr=duration,
        barSizeSetting=barSize,
        whatToShow='TRADES',
        useRTH=True,  # True per solo orario di trading regolare, False per includere after-hours
        formatDate=1
    )
    
    if bars:
        df = util.df(bars)
        return df
    return None

# Scarica dati con diverse granularità temporali
try:
    # Dati giornalieri degli ultimi 2 anni
    daily_data = download_historical_data(contract, '2 Y', '30 Mins')
    if daily_data is not None:
        daily_data.to_csv('MNQ_30Min1.csv')
        print("Dati giornalieri salvati")

except Exception as e:
    print(f"Errore durante il download dei dati: {str(e)}")

finally:
    # Disconnessione
    ib.disconnect()
