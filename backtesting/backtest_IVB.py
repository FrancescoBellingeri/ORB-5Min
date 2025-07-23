import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

# Carichiamo il dataset pulito
df = pd.read_csv('./data/qqq_5Min.csv')

# Convertiamo la colonna trading_day in datetime
df['trading_day'] = pd.to_datetime(df['trading_day'])
df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_localize(None)

# Filtriamo solo i dati del 2024
#df = df[df['trading_day'].dt.year > 2016]

def calculate_position_size(entry_price, stop_loss, account_size, leverage=4):
    # Calcolo del rischio in dollari
    R = abs(entry_price - stop_loss)
    
    # Calcolo size basato sul rischio (1% del capitale)
    risk_based_size = int(account_size * 0.01 / R)
    
    # Calcolo size massimo con leva piena
    max_shares_with_leverage = int((account_size * leverage) / entry_price)
    
    # Usa il risk_based_size direttamente
    position_size = risk_based_size
    
    # Debug info
    position_value = position_size * entry_price
    actual_leverage = position_value / account_size
    
    # Se superiamo la leva massima, allora limitiamo
    if actual_leverage > leverage:
        position_size = max_shares_with_leverage
    
    #return position_size if position_size > 0 else 0
    return risk_based_size

def ibkr_commission(shares):

    # Totale commissioni
    total_fees = shares * 0.0035

    # Output
    return total_fees

def calculate_dr_for_day(day_data):
    """
    Calcola il Daily Range per le candele tra le 9:30 e le 10:00.
    Returns: {'high': float, 'low': float, 'size': float}
    """
    
    # Filtra le candele tra le 9:30 e le 10:00
    start_time = day_data.iloc[0]['timestamp'].replace(hour=9, minute=30)
    end_time = day_data.iloc[0]['timestamp'].replace(hour=10, minute=0)
    
    dr_candles = day_data[
        (day_data['timestamp'] >= start_time) & 
        (day_data['timestamp'] <= end_time)
    ]
    
    if dr_candles.empty:
        return None
        
    return {
        'high': dr_candles['high'].max(),
        'low': dr_candles['low'].min(),
        'size': dr_candles['high'].max() - dr_candles['low'].min()
    }

def calculate_ATR(df, period=14):
    """
    Calcola l'ATR usando la formula: ATR = (1/n) * Σ(TR_i)
    Il DataFrame in input deve già contenere esattamente i 14 giorni di trading precedenti
    """
    # Verifichiamo di avere il numero corretto di giorni
    num_days = len(df['trading_day'].unique())
    if num_days != period:
        print(f"Numero errato di giorni: {num_days} invece di {period}")
        return None
    
    # Raggruppiamo i dati per giorno per ottenere OHLC giornalieri
    daily_data = df.groupby('trading_day').agg({
        'high': 'max',
        'low': 'min',
        'close': 'last'
    }).reset_index()
    
    # Calcoliamo il True Range per ogni giorno
    daily_data['previous_close'] = daily_data['close'].shift(1)
    
    # Calcoliamo le tre componenti del TR
    daily_data['hl'] = daily_data['high'] - daily_data['low']  # High - Low
    daily_data['hpc'] = abs(daily_data['high'] - daily_data['previous_close'])  # |High - Previous Close|
    daily_data['lpc'] = abs(daily_data['low'] - daily_data['previous_close'])   # |Low - Previous Close|
    
    # TR è il massimo dei tre valori
    daily_data['TR'] = daily_data[['hl', 'hpc', 'lpc']].max(axis=1)
    
    # Calcoliamo l'ATR come media dei TR
    atr = daily_data['TR'].mean()
    
    return atr

def execute_trade(candles, bias, entry_price, stop_loss, take_profit, position_size):

    # Calcola il rischio (sempre positivo)
    risk = abs(entry_price - stop_loss)

    entry_candle = None
    exit_price = None
    exit_reason = 'EOD'
    
    # Un solo ciclo per controllare entry e stop loss
    for _, candle in candles.iterrows():
        # Se non siamo ancora entrati, controlliamo l'entry
        if entry_candle is None:
            if bias == 'LONG' and candle['high'] >= entry_price:
                entry_candle = candle
            elif bias == 'SHORT' and candle['low'] <= entry_price:
                entry_candle = candle
            continue  # Passiamo alla prossima candela se non siamo entrati
        
        # Se siamo entrati, controlliamo stop loss e take profit
        if bias == 'LONG':
            if candle['low'] <= stop_loss:
                exit_price = stop_loss
                exit_reason = 'SL'
                break
            elif candle['high'] >= take_profit:
                exit_price = take_profit
                exit_reason = 'TP'
                break
        else:  # SHORT
            if candle['high'] >= stop_loss:
                exit_price = stop_loss
                exit_reason = 'SL'
                break
            elif candle['low'] <= take_profit:
                exit_price = take_profit
                exit_reason = 'TP'
                break
    
    # Se non siamo mai entrati, nessun trade
    if entry_candle is None:
        return None
    
    # Se non abbiamo hittato stop loss, usiamo chiusura fine giornata
    if exit_reason == 'EOD':
        exit_price = candles.iloc[-1]['close']

    reward = abs(exit_price - entry_price)
    rr_ratio = reward / risk if risk > 0 else 0

    total_commission = ibkr_commission(position_size)

    # Calcolo PnL
    if bias == 'LONG':
        pnl = (exit_price - entry_price) * position_size - total_commission
    else:  # SHORT
        pnl = (entry_price - exit_price) * position_size - total_commission
    
    return {
        'entry_price': entry_price,
        'exit_price': exit_price,
        'stop_loss': stop_loss,
        'direction': bias,
        'exit_reason': exit_reason,
        'position_size': position_size,
        'pnl': pnl,
        'R:R': rr_ratio,
        'commission': total_commission,
        'entry_time': entry_candle['timestamp'] if entry_candle is not None else None,
    }

def analyze_trading_day(day_data, current_equity):
    """
    Analizza una giornata di trading
    """
    current_date = day_data.iloc[0]['trading_day']
    
    # Troviamo i 14 giorni di trading precedenti
    previous_dates = df[df['trading_day'] < current_date]['trading_day'].unique()
    if len(previous_dates) < 14:
        return None
        
    # Prendiamo esattamente gli ultimi 14 giorni
    previous_dates = sorted(previous_dates)[-14:]
    previous_data = df[df['trading_day'].isin(previous_dates)]
    
    # Calcola l'ATR
    atr_value = calculate_ATR(previous_data)
        
    # Calcola il DR (9:30-10:00) ET
    dr = calculate_dr_for_day(day_data)
    if not dr:
        return None
    
    # Trova le candele dopo le 10:30
    target_time = pd.Timestamp(current_date.date()).replace(hour=10, minute=00)
    candles_after_dr = day_data[day_data['timestamp'] > target_time]
    
    if len(candles_after_dr) == 0:
        return None
    
    # Cerca la prima rottura del DR
    breakout_candle = None
    confirmation_candle = None
    bias = None
    
    for idx, candle in candles_after_dr.iterrows():
        # Aggiorna il DR se necessario
        if candle['high'] > dr['high'] and candle['close'] < dr['high'] and breakout_candle is None:
            dr['high'] = candle['high']
            dr['size'] = dr['high'] - dr['low']
            continue
            
        if candle['low'] < dr['low'] and candle['close'] > dr['low'] and breakout_candle is None:
            dr['low'] = candle['low']
            dr['size'] = dr['high'] - dr['low']
            continue

        # Controlla rottura sopra
        if candle['close'] > dr['high']:
            breakout_candle = candle
            bias = 'LONG'
            break
        # Controlla rottura sotto
        elif candle['close'] < dr['low']:
            breakout_candle = candle
            bias = 'SHORT'
            break

    if breakout_candle is None:
        print(f"Nessuna candela trovata che ha rotto il dr {day_data.iloc[0]['trading_day']}")
        return None
    
    # Trova la candela di conferma
    breakout_index = day_data.index.get_loc(breakout_candle.name)
    remaining_candles = day_data.iloc[breakout_index + 1:]
    
    for idx, candle in remaining_candles.iterrows():
        if bias == 'LONG':
            if candle['close'] > breakout_candle['high']:
                confirmation_candle = candle
                break
        else:  # SHORT
            if candle['close'] < breakout_candle['low']:
                confirmation_candle = candle
                break
    
    if confirmation_candle is None:
        print(f"Nessuna candela di conferma trovata per {current_date.strftime('%Y-%m-%d')}")
        return None
    
    # Calcola entry, stop loss e gestisci il take profit in base al R:R
    if bias == 'LONG':
        entry_price = confirmation_candle['high']
        stop_loss = entry_price - (atr_value * 0.1)
        take_profit = dr['high'] + dr['size']

    else:  # SHORT
        entry_price = confirmation_candle['low']
        stop_loss = entry_price + (atr_value * 0.1)
        take_profit = dr['low'] - dr['size']
    
    position_size = calculate_position_size(entry_price, stop_loss, current_equity)
    
    if position_size == 0:
        return None
    
    # Trova le candele dopo la candela di breakout
    breakout_index = day_data.index.get_loc(confirmation_candle.name)
    candles_after_confirmation = day_data.iloc[breakout_index + 1:]
    
    # Esegui il trade
    trade_result = execute_trade(candles_after_confirmation, bias, entry_price, stop_loss, take_profit, position_size)
    if trade_result is not None:
        trade_result['date'] = day_data.iloc[0]['timestamp']
        trade_result['ATR'] = atr_value
        #trade_result['relative_volume'] = rel_vol
        return pd.Series(trade_result)

# Capitale iniziale
STARTING_CAPITAL = 50000
current_equity = STARTING_CAPITAL

# Lista per raccogliere i risultati
results = []

# Loop principale
for day, day_data in df.groupby('trading_day'):
    result = analyze_trading_day(day_data, current_equity)
    if result is not None:
        results.append(result)
        #current_equity += result['pnl']

# Creiamo un DataFrame con i risultati
trading_results = pd.DataFrame(results)

trading_results.to_csv('outputs/trading_results_5min_IVB.csv', index=False)
print(f"\nRisultati salvati in 'trading_results_TP.csv'")