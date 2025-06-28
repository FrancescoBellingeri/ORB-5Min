import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

# Carichiamo il dataset pulito
df = pd.read_csv('./data/qqq_data.csv')

# Convertiamo la colonna trading_day in datetime
df['trading_day'] = pd.to_datetime(df['trading_day'])

# Filtriamo solo i dati del 2024
#df = df[df['trading_day'].dt.year > 2024]

def calculate_position_size(entry_price, stop_loss, account_size, leverage=4):
    # Calcolo del rischio in dollari
    R = abs(entry_price - stop_loss)
    
    # Calcolo size basato sul rischio (1% del capitale)
    risk_based_size = int(account_size * 0.01 / R)
    
    # Calcolo size massimo con leva (usando 70% del margine disponibile per sicurezza)
    max_shares_with_leverage = int((account_size * leverage * 0.7) / entry_price)
    
    # Prendiamo il minore dei due valori
    position_size = min(risk_based_size, max_shares_with_leverage)
    
    return risk_based_size

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

def execute_trade(day_data, signal_type, first_candle, entry_price, stop_loss, position_size):
    # Trova le candele dopo il segnale
    candles_after_signal = day_data[day_data['timestamp'] > first_candle['timestamp']]
    
    if len(candles_after_signal) == 0:
        return None

    entry_candle = None
    exit_price = None
    exit_reason = 'EOD'
    
    # Un solo ciclo per controllare entry e stop loss
    for _, candle in candles_after_signal.iterrows():
        # Se non siamo ancora entrati, controlliamo l'entry
        if entry_candle is None:
            if signal_type == 'LONG' and candle['high'] >= entry_price:
                entry_candle = candle
            elif signal_type == 'SHORT' and candle['low'] <= entry_price:
                entry_candle = candle
            continue  # Passiamo alla prossima candela se non siamo entrati
        
        # Se siamo entrati, controlliamo lo stop loss
        if signal_type == 'LONG' and candle['low'] <= stop_loss:
            exit_price = stop_loss
            exit_reason = 'SL'
            break
        elif signal_type == 'SHORT' and candle['high'] >= stop_loss:
            exit_price = stop_loss
            exit_reason = 'SL'
            break
    
    # Se non siamo mai entrati, nessun trade
    if entry_candle is None:
        return None
    
    # Calcola il rischio (sempre positivo)
    risk = abs(entry_price - stop_loss)

    # Se non abbiamo hittato stop loss, usiamo chiusura fine giornata
    if exit_reason == 'EOD':
        exit_price = candles_after_signal.iloc[-1]['close']
        reward = abs(exit_price - entry_price)
        rr_ratio = reward / risk if risk > 0 else 0
    else:
        rr_ratio = -1

    total_commission = ibkr_commission(position_size)
    
    # Calcolo PnL
    if signal_type == 'LONG':
        pnl = (exit_price - entry_price) * position_size - total_commission
    else:  # SHORT
        pnl = (entry_price - exit_price) * position_size - total_commission
    
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
    candles_after_dr = day_data.iloc[1:]
    
    if len(candles_after_dr) == 0:
        return None
    
    # Determina il tipo di trade basato sulla direzione della candela
    if candle_direction == 'bullish':
        signal_type = 'LONG'
        entry_price = dr['high']
        stop_loss = entry_price - (atr_value * 0.1)
    else:  # bearish
        signal_type = 'SHORT'
        entry_price = dr['low']
        stop_loss = entry_price + (atr_value * 0.1)
    
    position_size = calculate_position_size(entry_price, stop_loss, current_equity)
    
    if position_size == 0:
        return None
    
    # Esegui il trade
    trade_result = execute_trade(day_data, signal_type, first_candle, entry_price, stop_loss, position_size)
    if trade_result is not None:
        trade_result['date'] = day_data.iloc[0]['timestamp']
        trade_result['ATR'] = atr_value
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

trading_results.to_csv('backtesting/trading_results.csv', index=False)
print(f"\nRisultati salvati in 'trading_results.csv'")