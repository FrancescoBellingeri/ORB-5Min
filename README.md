# QQQ 5-Minute Opening Range Breakout (ORB) Strategy Backtester

## 📈 Descrizione

Questo progetto implementa e backtesta una strategia Opening Range Breakout (ORB) su QQQ utilizzando dati intraday a 5 minuti.  
La strategia entra tramite ordini stop (buy o sell) in direzione della prima candela della giornata e applica uno stop loss dinamico basato sulla volatilità (ATR).  
Il backtest include gestione del rischio, volumi relativi e uscita a fine giornata.

---

## 🧠 Strategia

### Entry

1. **Opening Range (OR):**

   - Definita dalla prima candela 5 minuti della giornata (9:30 - 9:35 ET)
   - Si prende l’high e il low di questa candela

2. **Filtri di Volume:**

   - Calcolo del Relative Volume: volume della candela OR / media dei volumi delle prime candele dei 14 giorni precedenti
   - Si entra solo se il relative volume ≥ 100%

3. **Filtro Direzione:**

   - Solo long se candela OR è bullish (close > open)
   - Solo short se candela OR è bearish (close < open)
   - Nessun trade su doji (close = open)

4. **Esecuzione Ordine:**
   - **Long:** ordine stop sopra l’high della OR
   - **Short:** ordine stop sotto il low della OR

### Gestione del Rischio

- **Stop Loss:** 10% del valore dell’ATR a 14 giorni, calcolato in punti dal prezzo di ingresso
- **Chiusura:** a fine giornata (16:00 ET) se SL/TP non sono stati raggiunti
- **Position Size:** calcolata per rischiare il 1% del capitale

---

## 🗂️ Struttura della repo

- `fetch_data.py`: script per scaricare i dati 5-min OHLCV da Alpaca API
- `clear_dataset.py`: script per pulire e preparare il dataset scaricato
- `backtest.py`: esegue il backtest della strategia
- `analyze_backtest.py`: genera statistiche e grafici dai risultati del backtest
- `data/`: cartella dove vengono salvati i file CSV dei dati
- `backtesting/`: cartella dove vengono salvati i risultati e report del backtest

---

## Requisiti

- Python 3.8+
- Librerie: `pandas`, `numpy`, `matplotlib`, `seaborn`, `python-dotenv` (per leggere .env)

Puoi installare le dipendenze con:

````bash
pip install -r requirements.txt

---

## Configurazione API

Crea un file `.env` nella root del progetto con le tue credenziali Alpaca:

```ini
API_KEY=
API_SECRET=
ALPACA_BASE_URL=https://paper-api.alpaca.markets/v2

---

## 🚀 Come usare la repo

1. **Scaricare i Dati**
   - Lancia nel terminale: python data/fetch_data.py
   - Scarica i dati a 5 minuti per QQQ da Alpaca.
   - Salva il file CSV in data/qqq_5Min.csv.

2. **Pulire i Dati**
   - Lancia nel terminale: python data/clear_dataset.py
   - Pulisce il dataset rimuovendo anomalie e righe mancanti.
   - Crea un file pronto per il backtest.

3. **Eseguire il Backtest**
   - Lancia nel terminale: python backtesting/backtest.py
   - Applica la strategia ORB su QQQ.
   - I trade vengono salvati in outputs/trading_results_5Min.csv.

4. **Analizzare i risultati**
   - Genera:
      - Grafico Equity curve
      - Statistiche di performance salvate in outputs/stats_strategy_5Min.csv

🔧 Miglioramenti Futuri
Supporto multi-timeframe (es. 15min OR con conferma H1)

Posizionamento adattivo con trailing stop

Aggiunta di TP dinamici basati su range giornaliero

Filtro regime di mercato (es. trend SPY, VIX, ecc.)

👨‍💻 Autore
Francesco Bellingeri
GitHub – Feel free to open issues or pull requests.

🛑 Disclaimer
Questo progetto è a scopo puramente educativo.
Non rappresenta un consiglio finanziario né una strategia da usare su mercati reali senza verifica.
````
