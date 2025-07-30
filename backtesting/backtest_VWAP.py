import pandas as pd
from datetime import time

# Carichiamo il dataset pulito
df = pd.read_csv('./data/qqq_1Min_cleared.csv')

df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)


# Convertiamo la colonna trading_day in datetime
df['trading_day'] = pd.to_datetime(df['trading_day'])

df['timestamp'] = df['timestamp'].dt.tz_convert('America/New_York')
df['time'] = df['timestamp'].dt.time

# Filtriamo solo i dati del 2024
#df = df[df['trading_day'].dt.year > 2024]

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

def execute_trade(day_data, bias, last_dr_candle, entry_price, stop_loss, position_size):
    # Trova le candele dopo il segnale
    candles_after_signal = day_data[day_data['timestamp'] > last_dr_candle['timestamp']]
    
    if len(candles_after_signal) == 0:
        return None
    
    # Calcola il rischio (sempre positivo)
    risk = abs(entry_price - stop_loss)
    take_profit = entry_price + (risk * 6) if bias == 'LONG' else entry_price - (risk * 6)

    entry_candle = None
    exit_candle = None
    exit_price = None
    exit_reason = 'EOD'
    current_stop = stop_loss
    stop_moved_to_profit = False
    
    for _, candle in candles_after_signal.iterrows():
        if entry_candle is None:
            if bias == 'LONG' and candle['high'] >= entry_price:
                entry_candle = candle
            elif bias == 'SHORT' and candle['low'] <= entry_price:
                entry_candle = candle
            continue
        
        if bias == 'LONG':
            # Se il prezzo corrente è sopra entry price e il VWAP è sopra lo stop loss originale
            if candle['close'] > entry_price  and candle['vwap'] > stop_loss:
                old_stop = current_stop
                current_stop = max(candle['vwap'], current_stop)
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
                current_stop = min(candle['vwap'], current_stop)
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
        exit_price = candles_after_signal.iloc[-1]['close']
        exit_candle = candles_after_signal.iloc[-1]

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
        'exit_time': exit_candle['timestamp'] if exit_candle is not None else None,
        'vwap': entry_candle['vwap']
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

    first_dr_candle = day_data[day_data['time'] == time(9, 30)].iloc[0]
    last_dr_candle = day_data[day_data['time'] == time(10, 0)].iloc[0]

    if first_dr_candle['open'] < last_dr_candle['close']:
        bias = 'LONG'
    else:
        bias = 'SHORT'

    # Determina il tipo di trade basato sulla direzione della candela
    if bias == 'LONG':
        entry_price = dr['high']
        stop_loss = entry_price - (atr_value * 0.1)
    else:  # short
        entry_price = dr['low']
        stop_loss = entry_price + (atr_value * 0.1)
    
    position_size = calculate_position_size(entry_price, stop_loss, current_equity)
    
    if position_size == 0:
        return None
    
    # Esegui il trade
    trade_result = execute_trade(day_data, bias, last_dr_candle, entry_price, stop_loss, position_size)
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

trading_results.to_csv('outputs/trading_results_1Min_VWAP.csv', index=False)
print(f"\nRisultati salvati in 'trading_results_TP.csv'")