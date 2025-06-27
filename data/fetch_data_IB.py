from ib_insync import *
import pandas as pd
import datetime

def fetch_mnq_5min(start_date, end_date, contract_month='202306'):
    ib = IB()
    ib.connect('127.0.0.1', 7497, clientId=1)
    
    contract = Future(
        symbol='MNQ',
        lastTradeDateOrContractMonth=contract_month,
        exchange='GLOBEX',
        currency='USD'
    )
    ib.qualifyContracts(contract)
    
    data = ib.reqHistoricalData(
        contract,
        endDateTime=end_date.strftime("%Y%m%d %H:%M:%S"),
        durationStr=f"{(end_date - start_date).days + 1} D",
        barSizeSetting='5 mins',
        whatToShow='TRADES',
        useRTH=False,
        formatDate=1,
        keepUpToDate=False
    )
    
    ib.disconnect()
    df = util.df(data)
    return df

# ⚠️ Ricorda: per maggio 2023 il contratto scambiato era molto probabilmente quello con scadenza giugno 2023
df = fetch_mnq_5min(datetime.datetime(2023,5,1), datetime.datetime(2023,5,31), contract_month='202309')
print(df)
