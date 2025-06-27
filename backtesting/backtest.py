import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

# Carichiamo il dataset pulito
df = pd.read_csv('./data/qqq_data.csv')

# Convertiamo la colonna trading_day in datetime
df['trading_day'] = pd.to_datetime(df['trading_day'])

# Filtriamo solo i dati del 2024
#df = df[df['trading_day'].dt.year > 2016]

def calculate_drawdown_statistics(equity):
    # Calcolo del drawdown
    running_max = equity.expanding().max()
    drawdown = (equity - running_max) / running_max * 100
    
    # Statistiche base
    avg_drawdown = drawdown[drawdown < 0].mean() if len(drawdown[drawdown < 0]) > 0 else 0
    
    # Periodi di drawdown
    in_drawdown = False
    drawdown_periods = []
    current_drawdown_start = None
    
    for i in range(len(drawdown)):
        if drawdown.iloc[i] < 0 and not in_drawdown:
            in_drawdown = True
            current_drawdown_start = i
        elif drawdown.iloc[i] >= 0 and in_drawdown:
            in_drawdown = False
            drawdown_periods.append((current_drawdown_start, i))
    
    if in_drawdown:
        drawdown_periods.append((current_drawdown_start, len(drawdown) - 1))
    
    # Calcolo durate
    drawdown_durations = [end - start for start, end in drawdown_periods]
    max_drawdown_duration = max(drawdown_durations) if drawdown_durations else 0
    avg_drawdown_duration = np.mean(drawdown_durations) if drawdown_durations else 0
    
    # Tempo in drawdown
    total_drawdown_days = sum(drawdown_durations)
    total_days = len(equity)
    time_in_drawdown_pct = (total_drawdown_days / total_days) * 100 if total_days > 0 else 0
    
    return {
        'avg_drawdown': avg_drawdown,
        'max_drawdown_duration': max_drawdown_duration,
        'avg_drawdown_duration': avg_drawdown_duration,
        'num_drawdown_periods': len(drawdown_periods),
        'time_in_drawdown_pct': time_in_drawdown_pct
    }

def calculate_position_size(entry_price, stop_loss, account_size):
    # Calcolo del rischio in dollari
    R = abs(entry_price - stop_loss)
    
    # Calcolo delle due limitazioni
    position_size = int(account_size * 0.01 / R)  # Rischio massimo del 1% del capitale per trade
    #leverage_based_size = int((4 * account_size) / entry_price)  # Limitazione basata sulla leva 4x
    
    # Prendiamo il minore dei due valori
    #position_size = min(position_size, leverage_based_size)
    
    return position_size if position_size > 0 else 0

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

def calculate_relative_volume(first_candle, df):
    # Filtra i 14 giorni precedenti
    previous_days = df[df['trading_day'] < first_candle['trading_day']]
    previous_first_candles = previous_days.groupby('trading_day').head(1).tail(14)

    avg_5m_volume_14gg = previous_first_candles['volume'].mean()

    if avg_5m_volume_14gg == 0 or np.isnan(avg_5m_volume_14gg):
        return 0

    return first_candle['volume'] / avg_5m_volume_14gg

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
    
    # Calcola relative volume
    rel_vol = calculate_relative_volume(first_candle, df)

    if rel_vol < 1.0:
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
        trade_result['relative_volume'] = rel_vol
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

# Calcolo dei giorni massimi consecutivi in perdita
consecutive_losses = 0
max_consecutive_losses = 0
current_streak = 0
consecutive_wins = 0
max_consecutive_wins = 0
current_win_streak = 0

for pnl in trading_results['pnl']:
    if pnl < 0:
        current_streak += 1
        max_consecutive_losses = max(max_consecutive_losses, current_streak)
    else:
        current_streak = 0

    if pnl > 0:
        current_win_streak += 1
        max_consecutive_wins = max(max_consecutive_wins, current_win_streak)
    else:
        current_win_streak = 0

if len(trading_results) > 0:
    # Calcoliamo l'equity curve
    trading_results['cumulative_pnl'] = trading_results['pnl'].cumsum()
    trading_results['equity'] = STARTING_CAPITAL + trading_results['cumulative_pnl']
    
    # Assicuriamoci che la colonna date sia in formato datetime
    trading_results['date'] = pd.to_datetime(trading_results['date'])
    
    # Ordiniamo i risultati per data
    trading_results = trading_results.sort_values('date')
    
    # Calcolo del buy and hold
    first_price = df.iloc[0]['close']
    last_price = df.iloc[-1]['close']
    shares_buy_hold = STARTING_CAPITAL / first_price
    buy_hold_equity = []
    
    # Calcola il valore del portafoglio buy & hold per ogni giorno
    for day in trading_results['date']:
        # Trova il prezzo di chiusura per quel giorno
        day_data = df[df['trading_day'] == day.date()]
        if len(day_data) > 0:
            day_price = day_data.iloc[-1]['close']  # Prezzo di chiusura del giorno
        else:
            # Se non troviamo dati per quel giorno, usa il prezzo precedente
            day_price = buy_hold_equity[-1] / shares_buy_hold if buy_hold_equity else first_price
        equity_value = shares_buy_hold * day_price
        buy_hold_equity.append(equity_value)
    
    # Creiamo il grafico
    plt.figure(figsize=(20, 10))
    sns.set_style("whitegrid")
    
    plt.plot(trading_results['date'], trading_results['equity'], 
        color='blue', linewidth=1.5, label='Strategia ORB + RelVol')
    
    plt.plot(trading_results['date'], buy_hold_equity,
             color='green', linewidth=1.5, label='Buy & Hold')
    
    plt.axhline(y=STARTING_CAPITAL, color='r', linestyle='--', label='Capitale Iniziale')
    
    plt.title('Confronto Strategia ORB + RelVol vs Buy & Hold', fontsize=14, pad=20)
    plt.xlabel('Data', fontsize=12)
    plt.ylabel('Capitale ($)', fontsize=12)
    plt.legend(fontsize=10)
    
    plt.gca().yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
    plt.gcf().autofmt_xdate()
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.tight_layout()
    
    plt.savefig('backtesting/equity__ORB_5min.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    # Stampiamo le statistiche
    print("\nStatistiche della Strategia ORB + RelVol:")
    print(f"Capitale Iniziale: ${STARTING_CAPITAL:,.2f}")
    print(f"Capitale Finale: ${trading_results['equity'].iloc[-1]:,.2f}")
    print(f"Profitto Totale: ${trading_results['cumulative_pnl'].iloc[-1]:,.2f}")
    print(f"Rendimento Totale: {((trading_results['equity'].iloc[-1] / STARTING_CAPITAL - 1) * 100):,.2f}%")
    print(f"Numero di Trade: {len(trading_results)}")
    
    wins = trading_results[trading_results['pnl'] > 0]
    losses = trading_results[trading_results['pnl'] <= 0]
    
    print(f"Trade Vincenti: {len(wins)}")
    print(f"Trade Perdenti: {len(losses)}")
    print(f"Win Rate: {(len(wins) / len(trading_results) * 100):,.2f}%")
    
    # Statistiche aggiuntive
    if len(wins) > 0:
        print(f"Media Trade Vincenti: ${wins['pnl'].mean():,.2f}")
        print(f"Massimo Trade Vincente: ${wins['pnl'].max():,.2f}")
    
    if len(losses) > 0:
        print(f"Media Trade Perdenti: ${losses['pnl'].mean():,.2f}")
        print(f"Massima Perdita: ${losses['pnl'].min():,.2f}")
    
    # Profit Factor
    if len(losses) > 0 and losses['pnl'].sum() < 0:
        profit_factor = wins['pnl'].sum() / abs(losses['pnl'].sum())
        print(f"Profit Factor: {profit_factor:.2f}")
    print(f"\nGiorni massimi consecutivi in perdita: {max_consecutive_losses}")
    print(f"Giorni massimi consecutivi in profitto: {max_consecutive_wins}")
    # Statistiche sulle uscite
    exit_stats = trading_results['exit_reason'].value_counts()
    print(f"\nStatistiche sulle uscite:")
    for reason, count in exit_stats.items():
        percentage = (count / len(trading_results)) * 100
        print(f"{reason}: {count} ({percentage:.1f}%)")
    
    # Statistiche direzionali
    long_trades = trading_results[trading_results['direction'] == 'LONG']
    short_trades = trading_results[trading_results['direction'] == 'SHORT']
    
    print(f"\nTrade LONG: {len(long_trades)} ({(len(long_trades) / len(trading_results) * 100):.1f}%)")
    print(f"Trade SHORT: {len(short_trades)} ({(len(short_trades) / len(trading_results) * 100):.1f}%)")

    # R-multiple medio
    print(f"\nR:R: {trading_results['R:R'].mean():.2f}")
    
    # Commissioni totali
    print(f"Commissioni Totali: ${trading_results['commission'].sum():,.2f}")
    
    # Drawdown massimo
    running_max = trading_results['equity'].expanding().max()
    drawdown = (trading_results['equity'] - running_max) / running_max * 100
    max_drawdown = drawdown.min()
    print(f"Drawdown Massimo: {max_drawdown:.2f}%")

    # Calcola le statistiche del drawdown
    #drawdown_stats = calculate_drawdown_statistics(trading_results['equity'])

    # print("\n=== Statistiche Drawdown ===")
    # print(f"Drawdown Medio: {drawdown_stats['avg_drawdown']:.2f}%")
    # print(f"Durata Massima Drawdown: {drawdown_stats['max_drawdown_duration']} giorni")
    # print(f"Durata Media Drawdown: {drawdown_stats['avg_drawdown_duration']:.1f} giorni")
    # print(f"Numero Periodi Drawdown: {drawdown_stats['num_drawdown_periods']}")
    # print(f"Percentuale Tempo in Drawdown: {drawdown_stats['time_in_drawdown_pct']:.1f}%")

    # print("\nDrawdown Medio Mensile:")
    # for month, drawdown in drawdown_stats['monthly_avg_drawdown'].items():
    #     print(f"{month}: {drawdown:.2f}%")

    # print("\nDrawdown Medio Trimestrale:")
    # for quarter, drawdown in drawdown_stats['quarterly_avg_drawdown'].items():
    #     print(f"Q{quarter}: {drawdown:.2f}%")
    
    # Sharpe Ratio (approssimato)
    if len(trading_results) > 1:
        daily_returns = trading_results['pnl'] / (STARTING_CAPITAL + trading_results['cumulative_pnl'].shift(1).fillna(0))
        sharpe_ratio = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)  # Annualizzato
        print(f"Sharpe Ratio (annualizzato): {sharpe_ratio:.2f}")
    
    # Buy & Hold statistics
    buy_hold_return = ((last_price - first_price) / first_price) * 100
    print(f"\n--- Buy & Hold ---")
    print(f"Rendimento Buy & Hold: {buy_hold_return:.2f}%")
    print(f"Capitale finale Buy & Hold: ${buy_hold_equity[-1]:,.2f}")
    
    # Confronto con Buy & Hold
    strategy_return = ((trading_results['equity'].iloc[-1] / STARTING_CAPITAL - 1) * 100)
    excess_return = strategy_return - buy_hold_return
    print(f"\nExcess Return vs Buy & Hold: {excess_return:.2f}%")
    
    # Salviamo i risultati
    trading_results.to_csv('backtesting/trading_results_ORB_5min.csv', index=False)
    print(f"\nRisultati salvati in 'trading_results_dr_idr.csv'")
    
else:
    print("Nessun trade eseguito con la strategia ORB + RelVol")
    print("Verifica che ci siano segnali di trading validi nei dati")