from backtesting import Backtest, Strategy
import pandas as pd
import numpy as np
from datetime import time, datetime, timedelta

def prepare_data(filepath):
    # Leggi il CSV
    df = pd.read_csv(filepath)
    
    # Converti timestamp in datetime con UTC=True per evitare il warning
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    
    # Converti trading_day in datetime
    df['trading_day'] = pd.to_datetime(df['trading_day']).dt.date
    
    # Imposta timestamp come index
    df.set_index('timestamp', inplace=True)
    
    # Seleziona solo le colonne necessarie per il backtesting
    df_backtest = df[['open', 'high', 'low', 'close', 'volume']]
    
    # Rinomina le colonne per rispettare il formato di backtesting.py
    df_backtest.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
    
    return df_backtest, df

def calculate_ATR(df, period=14):
    """
    Calcola l'ATR usando la formula: ATR = (1/n) * Σ(TR_i)
    """
    daily_data = df.groupby('trading_day').agg({
        'high': 'max',
        'low': 'min',
        'close': 'last'
    }).reset_index()
    
    daily_data['previous_close'] = daily_data['close'].shift(1)
    daily_data['hl'] = daily_data['high'] - daily_data['low']
    daily_data['hpc'] = abs(daily_data['high'] - daily_data['previous_close'])
    daily_data['lpc'] = abs(daily_data['low'] - daily_data['previous_close'])
    daily_data['TR'] = daily_data[['hl', 'hpc', 'lpc']].max(axis=1)
    
    return daily_data['TR'].mean()

class ORB5Min(Strategy):
    def init(self):
        self.atr_value = None
        self.current_trading_day = None
        self.first_candle = None
        self.entry_price = None
        self.stop_loss = None
        self.signal_type = None
        self.trade_executed = False
        
        self.first_candle_map = {}

        for ts, row in zip(self.data.index, self.data.df.itertuples()):
            ny_time = ts.tz_convert('America/New_York')
            if ny_time.time() == time(9, 30):
                self.first_candle_map[ny_time.date()] = {
                    'open': row.Open,
                    'high': row.High,
                    'low': row.Low,
                    'close': row.Close,
                    'timestamp': ts
                }
        
    def next(self):
        current_time = self.data.index[-1]
        current_ny_time = current_time.tz_convert('America/New_York')
        current_date = current_ny_time.date()
        
        # Reset giornaliero
        if self.current_trading_day != current_date:
            self.current_trading_day = current_date
            self.trade_executed = False
            self.first_candle = None
            
            # Calcolo ATR sui 14 giorni precedenti
            end_timestamp = pd.Timestamp(current_date, tz='UTC')
            start_timestamp = end_timestamp - timedelta(days=30)
            
            mask = (df_complete.index >= start_timestamp) & (df_complete.index < end_timestamp)
            previous_data = df_complete.loc[mask].copy()
            
            if len(previous_data) > 0:
                unique_days = sorted(previous_data['trading_day'].unique())[-14:]
                previous_data_14d = previous_data[previous_data['trading_day'].isin(unique_days)]
                
                if len(unique_days) == 14:
                    self.atr_value = calculate_ATR(previous_data_14d)
            
            self.first_candle = self.first_candle_map.get(current_date)
            if self.first_candle and self.atr_value:
                if self.first_candle['close'] > self.first_candle['open']:
                    self.signal_type = 'LONG'
                    self.entry_price = self.first_candle['high']
                    self.stop_loss = self.entry_price - (self.atr_value * 0.1)
                elif self.first_candle['close'] < self.first_candle['open']:
                    self.signal_type = 'SHORT'
                    self.entry_price = self.first_candle['low']
                    self.stop_loss = self.entry_price + (self.atr_value * 0.1)
        
        # Esecuzione del trade
        if (not self.trade_executed and 
            self.first_candle and 
            self.atr_value is not None and
            time(9, 35) <= current_ny_time.time() < time(16, 0)):  # Modificato per iniziare dopo la prima candela
            
            risk = abs(self.entry_price - self.stop_loss)
            risk_amount = self.equity * 0.01
            position_size = int(risk_amount / risk)
            
            if risk > 0:
                if self.signal_type == 'LONG':
                    take_profit = self.entry_price + (risk * 10)
                    candle_high = self.data.High[-1]
                    
                    if candle_high > self.entry_price:
                        print(f"\nEsecuzione LONG a {current_ny_time.time()}")
                        print(f"Entry={self.entry_price}, SL={self.stop_loss}, TP={take_profit}")
                        
                        self.buy(size=position_size, 
                            sl=self.stop_loss,
                            tp=take_profit,
                            )

                        self.trade_executed = True
                        
                elif self.signal_type == 'SHORT':
                    take_profit = self.entry_price - (risk * 10)
                    candle_low = self.data.Low[-1]
                    
                    if candle_low <= self.entry_price:
                        print(f"\nEsecuzione SHORT a {current_ny_time.time()}")
                        print(f"Entry={self.entry_price}, SL={self.stop_loss}, TP={take_profit}")
                        
                        self.sell(size=position_size,
                                sl=self.stop_loss,
                                tp=take_profit)

                        self.trade_executed = True
        
        # Chiusura forzata a fine giornata
        if current_ny_time.time() >= time(15, 55) and self.position:
            self.position.close()

# Carica e prepara i dati
df_backtest, df_complete = prepare_data('./data/qqq_data.csv')

# Configura e esegui il backtest
bt = Backtest(
    df_backtest,
    ORB5Min,
    cash=50000,
    commission=.0035,
    exclusive_orders=True,
    trade_on_close=False,
)

# Esegui il backtest
results = bt.run()

# Stampa i risultati dettagliati
print("\nRisultati del Backtest:")
print(f"Rendimento totale: {results['Return [%]']:.2f}%")
print(f"Rendimento annuale: {results['Return (Ann.) [%]']:.2f}%")
print(f"Numero di trade: {results['# Trades']}")
print(f"Win Rate: {results['Win Rate [%]']:.2f}%")
print(f"Profit Factor: {results['Profit Factor']:.2f}")
print(f"Max Drawdown: {results['Max. Drawdown [%]']:.2f}%")
print(f"Sharpe Ratio: {results['Sharpe Ratio']:.2f}")

# Plot dei risultati
bt.plot()