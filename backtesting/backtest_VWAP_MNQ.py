import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import math

# Carichiamo il dataset pulito
df = pd.read_csv('./data/MNQ_30Min.csv')

# Convertiamo la colonna date in datetime
df['timestamp'] = pd.to_datetime(df['timestamp'])

# Estrai solo la data (senza ora) per raggruppare per giorno
df['day'] = df['timestamp'].dt.date

# Filtriamo solo i dati del 2024
#df = df[df['day'].dt.year > 2024]

def round_to_quarter_up(number):
    """Approssima sempre per eccesso a multipli di 0.25"""
    return math.ceil(number * 4) / 4

def round_to_quarter_down(number):
    """Approssima sempre per difetto a multipli di 0.25"""
    return math.floor(number * 4) / 4

def calculate_position_size(entry_price, stop_loss, account_size, risk_pct=0.01):
    # rischio in $, es. 1% del capitale
    max_risk = account_size * risk_pct

    # specifico MNQ
    POINT_VALUE = 2.0  # $ per punto

    distance_points = abs(entry_price - stop_loss)
    risk_per_contract = distance_points * POINT_VALUE
    if risk_per_contract <= 0:
        return 0

    # arrotonda per difetto per essere conservativo
    return math.floor(max_risk / risk_per_contract)

def ibkr_commission(shares):

    # Totale commissioni
    total_fees = shares * 0.0035

    # Output
    return total_fees

def calculate_dr_for_day(candle):
    """
    Calcola il Daily Range per le prime 3 candele della giornata.
    Returns: {'high': float, 'low': float, 'size': float}
    """

    if candle.empty:
        return None
        
    return {
        'high': candle['high'],
        'low': candle['low'],
        'size': candle['high'] - candle['low']
    }

def calculate_ATR(df, period=14):
    """
    Calcola l'ATR usando la formula: ATR = (1/n) * Σ(TR_i)
    Il DataFrame in input deve già contenere esattamente i 14 giorni di trading precedenti
    """
    # Verifichiamo di avere il numero corretto di giorni
    num_days = len(df['day'].unique())
    if num_days != period:
        print(f"Numero errato di giorni: {num_days} invece di {period}")
        return None
    
    # Raggruppiamo i dati per giorno per ottenere OHLC giornalieri
    daily_data = df.groupby('day').agg({
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

def execute_trade(day_data, signal_type, first_candle, entry_price, stop_loss, position_size):
    # Trova le candele dopo il segnale
    candles_after_signal = day_data[day_data['timestamp'] > first_candle['timestamp']]
    
    # Calcola il rischio (sempre positivo)
    risk = abs(entry_price - stop_loss)
    take_profit = entry_price + (risk * 10) if signal_type == 'LONG' else entry_price - (risk * 10)
    
    if len(candles_after_signal) == 0:
        return None

    entry_candle = None
    exit_price = None
    exit_candle = None
    exit_reason = 'EOD'
    current_stop = stop_loss
    stop_moved_to_profit = False
    
    for _, candle in candles_after_signal.iterrows():
        if entry_candle is None:
            if signal_type == 'LONG' and candle['high'] >= entry_price:
                entry_candle = candle
            elif signal_type == 'SHORT' and candle['low'] <= entry_price:
                entry_candle = candle
            continue
        
        if signal_type == 'LONG':
            # Se il prezzo corrente è sopra entry price e il VWAP è sopra lo stop loss originale
            if candle['close'] > entry_price  and candle['vwap'] > stop_loss:
                old_stop = current_stop
                current_stop = max(round_to_quarter_down(candle['vwap']), current_stop)
                # Aggiorniamo il flag se lo stop è stato effettivamente spostato
                if current_stop > old_stop:
                    stop_moved_to_profit = True
            
            if candle['low'] <= current_stop:
                exit_price = current_stop
                exit_reason = 'TRAILING' if stop_moved_to_profit else 'SL'
                exit_candle = candle
                break
            elif candle['high'] >= take_profit:
                exit_price = take_profit
                exit_reason = 'TP'
                exit_candle = candle
                break
                
        else:  # SHORT
            if candle['close'] < entry_price  and candle['vwap'] < stop_loss:
                old_stop = current_stop
                current_stop = min(round_to_quarter_up(candle['vwap']), current_stop)
                # Aggiorniamo il flag se lo stop è stato effettivamente spostato
                if current_stop < old_stop:
                    stop_moved_to_profit = True
            
            if candle['high'] >= current_stop:
                exit_price = current_stop
                exit_reason = 'TRAILING' if stop_moved_to_profit else 'SL'
                exit_candle = candle
                break
            elif candle['low'] <= take_profit:
                exit_price = take_profit
                exit_reason = 'TP'
                exit_candle = candle
                break
    
    # Se non siamo mai entrati, nessun trade
    if entry_candle is None:
        return None
    
    # Se non abbiamo hittato stop loss, usiamo chiusura fine giornata
    if exit_reason == 'EOD':
        exit_price = candles_after_signal.iloc[-2]['close']
        exit_candle = candles_after_signal.iloc[-2]

    reward = abs(exit_price - entry_price)
    rr_ratio = reward / risk if risk > 0 else 0

    total_commission = ibkr_commission(position_size)

    # Calcolo PnL
    if signal_type == 'LONG':
        pnl = (exit_price - entry_price) * position_size * 2 - total_commission
    else:  # SHORT
        pnl = (entry_price - exit_price) * position_size * 2 - total_commission
    
    return {
        'entry_price': entry_price,
        'exit_price': exit_price,
        'stop_loss': stop_loss,
        'direction': signal_type,
        'exit_reason': exit_reason,
        'position_size': position_size,
        'pnl': pnl,
        'R:R': rr_ratio,
        'commission': total_commission,
        'entry_time': entry_candle['timestamp'] if entry_candle is not None else None,
        'exit_time': exit_candle['timestamp'] if exit_candle is not None else None,
        'vwap': entry_candle['vwap']
    }

def analyze_trading_day(day_data, current_equity):
    """
    Analizza una giornata di trading
    """
    current_date = day_data.iloc[0]['day']
    
    # Troviamo i 14 giorni di trading precedenti
    previous_dates = df[df['day'] < current_date]['day'].unique()
    if len(previous_dates) < 14:
        return None
        
    # Prendiamo esattamente gli ultimi 14 giorni
    previous_dates = sorted(previous_dates)[-14:]
    previous_data = df[df['day'].isin(previous_dates)]
    
    # Calcola l'ATR
    atr_value = calculate_ATR(previous_data)

    first_candle = day_data.iloc[0]
    # No trade se candela Doji
    if first_candle['open'] == first_candle['close']:
        return None
    
    # Determina la direzione della candela
    candle_direction = 'bullish' if first_candle['close'] > first_candle['open'] else 'bearish'
    
    # Calcola il DR (9:30-9:35) ET
    dr = calculate_dr_for_day(first_candle)
    if not dr:
        return None
    
    # Trova le candele dopo il DR
    candles_after_dr = day_data.iloc[2:]
    
    if len(candles_after_dr) == 0:
        return None
    
    # Determina il tipo di trade basato sulla direzione della candela
    if candle_direction == 'bullish':
        signal_type = 'LONG'
        entry_price = dr['high']
        stop_loss = round_to_quarter_down(entry_price - (atr_value * 0.1))
    else:  # bearish
        signal_type = 'SHORT'
        entry_price = dr['low']
        stop_loss = round_to_quarter_up(entry_price + (atr_value * 0.1))
    
    position_size = calculate_position_size(entry_price, stop_loss, current_equity)
    
    if position_size == 0:
        return None
    
    # Esegui il trade
    trade_result = execute_trade(day_data, signal_type, first_candle, entry_price, stop_loss, position_size)
    if trade_result is not None:
        trade_result['timestamp'] = day_data.iloc[0]['timestamp']
        trade_result['ATR'] = atr_value
        #trade_result['relative_volume'] = rel_vol
        return pd.Series(trade_result)

# Capitale iniziale
STARTING_CAPITAL = 50000
current_equity = STARTING_CAPITAL

# Lista per raccogliere i risultati
results = []

# Loop principale
for day, day_data in df.groupby('day'):
    result = analyze_trading_day(day_data, current_equity)
    if result is not None:
        results.append(result)
        #current_equity += result['pnl']

# Creiamo un DataFrame con i risultati
trading_results = pd.DataFrame(results)

trading_results.to_csv('outputs/trading_results_MNQ_VWAP.csv', index=False)
print(f"\nRisultati salvati in 'trading_results_TP.csv'")