import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

def getPlot(df):
    df['cumulative_pnl'] = df['pnl'].cumsum()
    df['equity'] = STARTING_CAPITAL + df['cumulative_pnl']

    df['date'] = pd.to_datetime(df['date'])

    return df['date'], df['equity']

df = pd.read_csv('./data/qqq_15Min.csv')

# Convertiamo la colonna trading_day in datetime
df['trading_day'] = pd.to_datetime(df['trading_day'])

trading_results_5Min = pd.read_csv('outputs/trading_results_5Min.csv')
trading_results_15Min = pd.read_csv('outputs/trading_results_15Min.csv')
trading_results_30Min = pd.read_csv('outputs/trading_results_30Min.csv')
trading_results_30Min_VWAP = pd.read_csv('outputs/trading_results_30Min_VWAP.csv')
trading_results_60Min = pd.read_csv('outputs/trading_results_60Min.csv')

STARTING_CAPITAL = 50000

# Calcola il numero di azioni acquistate all'inizio
initial_price = df.iloc[0]['close']
final_price = df.iloc[-1]['close']
shares = STARTING_CAPITAL / initial_price

# Calcola l'equity curve del buy & hold
buy_hold_df = pd.DataFrame({
    'date': df['trading_day'],
    'equity': df['close'] * shares
})

# Creiamo il grafico
plt.figure(figsize=(20, 10))
sns.set_style("whitegrid")

date, equity = getPlot(trading_results_5Min)

plt.plot(date, equity, 
    color='blue', linewidth=1.5, label='Strategia ORB 5 Minuti')

date, equity = getPlot(trading_results_15Min)

plt.plot(date, equity, 
    color='red', linewidth=1.5, label='Strategia ORB 15 Minuti')

date, equity = getPlot(trading_results_30Min)

plt.plot(date, equity, 
    color='orange', linewidth=1.5, label='Strategia ORB 30 Minuti')

date, equity = getPlot(trading_results_30Min_VWAP)
plt.plot(date, equity, 
    color='purple', linewidth=1.5, label='Strategia ORB 30 Minuti + VWAP')

date, equity = getPlot(trading_results_60Min)

plt.plot(date, equity, 
    color='black', linewidth=1.5, label='Strategia ORB 60 Minuti')

plt.plot(df['trading_day'],  buy_hold_df['equity'],
            color='green', linewidth=1.5, label='Buy & Hold')

plt.axhline(y=STARTING_CAPITAL, color='r', linestyle='--', label='Capitale Iniziale')

plt.title('Confronto Strategia ORB Multi Frame vs Buy & Hold', fontsize=14, pad=20)
plt.xlabel('Data', fontsize=12)
plt.ylabel('Capitale ($)', fontsize=12)
plt.legend(fontsize=10)

plt.gca().yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
plt.gcf().autofmt_xdate()
plt.grid(True, linestyle='--', alpha=0.7)
plt.tight_layout()

plt.savefig('outputs/equity_comparison.png', dpi=300, bbox_inches='tight')
plt.close()