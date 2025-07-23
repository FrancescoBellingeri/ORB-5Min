import pandas as pd
from datetime import time, datetime, timedelta
from ib_insync import *
from zoneinfo import ZoneInfo
import schedule
import time as time_module

# --- 1. Parametri di Configurazione ---
IB_HOST = '127.0.0.1'
IB_PORT = 7497  # Usa 4001 per IB Gateway, 7496 per TWS
IB_CLIENT_ID = 1 # Un numero unico per questa connessione
TICKER = 'QQQ'
EXCHANGE = 'NASDAQ'
CURRENCY = 'USD'
TIMEFRAME = 5
ACCOUNT_SIZE = 50000 # Il tuo capitale iniziale
MARKET_TIMEZONE = ZoneInfo("America/New_York") # Orario sessione New York
MARKET_OPEN = time(9, 30)
LAST_ENTRY_TIME = time(15, 50) # Ultimo orario per un'entrata

# --- 2. Stato del Bot (Fondamentale!) ---
# Usiamo un dizionario per tenere traccia di tutto
bot_state = {
    "dr_calculated_today": False,
    "daily_range": {"high": 0, "low": 0},
    "in_trade": False,
    "trade_details": None, # Conterrà info sul trade in corso
    "order": None, # Conterrà l'oggetto ordine di ib_insync
    "current_day": None
}

# --- 4. Connessione e Loop Principale ---
ib = IB()
ib.connect(IB_HOST, IB_PORT, clientId=IB_CLIENT_ID)

# Definisci il contratto per QQQ
contract = Stock(TICKER, exchange=EXCHANGE, currency=CURRENCY)
ib.qualifyContracts(contract)
print("✅ Contratto qualificato:", contract)

def calculate_position_size(entry_price, stop_loss, account_size, risk_percent=1):
    """
    Calcola la size della posizione basata sul rischio
    """
    risk_amount = account_size * (risk_percent / 100)
    risk_per_share = abs(entry_price - stop_loss)
    
    if risk_per_share == 0:
        return 0
        
    position_size = int(risk_amount / risk_per_share)
    
    # Limita la leva a 4x
    max_position_value = account_size * 4
    max_shares = int(max_position_value / entry_price)
    
    return min(position_size, max_shares)

def calculate_ATR(ib, contract, period=14):
    """Calcola l'ATR usando i dati storici di IB"""
    try:
        # Richiedi i dati degli ultimi 14 giorni
        bars = ib.reqHistoricalData(
            contract,
            endDateTime='',
            durationStr=f'{period} D',
            barSizeSetting='1 day',
            whatToShow='TRADES',
            useRTH=True
        )
        
        if not bars or len(bars) < period:
            return None
            
        df = util.df(bars)
        
        # Calcolo TR
        df['previous_close'] = df['close'].shift(1)
        df['hl'] = df['high'] - df['low']
        df['hpc'] = abs(df['high'] - df['previous_close'])
        df['lpc'] = abs(df['low'] - df['previous_close'])
        df['TR'] = df[['hl', 'hpc', 'lpc']].max(axis=1)
        
        # Calcolo ATR
        atr = df['TR'].mean()
        
        return atr
        
    except Exception as e:
        print(f"Errore nel calcolo ATR: {e}")
        return None

def get_first_candle_of_day(ib, contract):
    """Recupera la prima candela del giorno dopo l'apertura"""
    try:
        # Ottieni la data corrente in ET
        current_date = datetime.now(ZoneInfo("America/New_York")).date()
        market_open_time = datetime.combine(current_date, MARKET_OPEN)
        market_open_time = market_open_time.replace(tzinfo=ZoneInfo("America/New_York"))
        
        bars = ib.reqHistoricalData(
            contract,
            endDateTime='',
            durationStr='1 D',
            barSizeSetting='5 mins',
            whatToShow='TRADES',
            useRTH=True,
            formatDate=1
        )
        
        if not bars:
            return None
            
        df = util.df(bars)
        # I dati di IB sono già in ET, non serve localizzare
        df['date'] = pd.to_datetime(df['date'])
        
        # Filtra solo le candele di oggi dopo l'apertura del mercato
        today_bars = df[
            (df['date'].dt.date == current_date) & 
            (df['date'] >= market_open_time)
        ]
        
        if len(today_bars) == 0:
            print("Nessuna candela disponibile per oggi")
            return None
            
        # Ritorna la prima candela di oggi come BarData object
        first_today_index = today_bars.index[0]
        return bars[first_today_index]
        
    except Exception as e:
        print(f"Errore nel recupero della prima candela: {e}")
        return None

def validate_prices(entry_price, tp_price, stop_loss):
    """Validazione dei prezzi per evitare ordini non validi"""
    if entry_price <= 0 or tp_price <= 0 or stop_loss <= 0:
        return False
    
    print(f"Validazione prezzi: Entry={entry_price}, TP={tp_price}, SL={stop_loss}")
    # Verifica che i prezzi siano multipli del tick size
    tick_size = 0.01  # Per QQQ
    if any(round(price % tick_size, 8) != 0 for price in [entry_price, tp_price, stop_loss]):
        return False
    
    return True

def on_bar_update(bar, has_new_bar):
    """ Questa funzione viene chiamata da ib_insync ogni volta che arriva una nuova candela. """
    if not has_new_bar:
        return # Nessuna nuova candela, non fare nulla

    print(f"Nuova candela ricevuta: {bar}")

    current_market_time = bar.date.time()
    today = bar.date.date()
    
    # Reset giornaliero dello stato
    if today != bot_state["current_day"]:
        print(f"Nuovo giorno di trading: {today}. Reset dello stato.")
        bot_state["dr_calculated_today"] = False
        bot_state["in_trade"] = False
        bot_state["trade_details"] = None
        bot_state["current_day"] = today

    # --- Logica del Daily Range (DR) ---
    if not bot_state["dr_calculated_today"] and current_market_time >= MARKET_OPEN:
        first_candle = get_first_candle_of_day(ib, contract)
        
        if first_candle:
            bot_state["daily_range"]["high"] = first_candle.high
            bot_state["daily_range"]["low"] = first_candle.low
            bot_state["dr_calculated_today"] = True
            
            print(f"DR calcolato per oggi: High={first_candle.high}, Low={first_candle.low}")
        else:
            print("Non ci sono abbastanza candele per calcolare il DR.")
            return

    # --- Logica di Ingresso (se non siamo già in un trade) ---
    if not bot_state["in_trade"] and bot_state["dr_calculated_today"]:
        # Controlla solo fino alle 11:00
        if current_market_time > LAST_ENTRY_TIME:
            return
            
        first_candle = get_first_candle_of_day(ib, contract)
        if first_candle:
            if first_candle.close > first_candle.open:  # Candela bullish
                signal_type = 'LONG'
            elif first_candle.close < first_candle.open:  # Candela bearish
                signal_type = 'SHORT'
            else:
                return  # Candela doji, no trade
                
            place_trade(signal_type, first_candle)

def round_to_tick(price, tick_size=0.01):  # QQQ tick size è $0.01
    """
    Arrotonda il prezzo al tick più vicino.
    """
    return round(price, 2)

def place_trade(signal_type, entry_candle):
    """Piazza il trade con la logica della nostra strategia"""
    
    # Calcola ATR
    atr_value = calculate_ATR(ib, contract)
    if not atr_value:
        print("❌ Impossibile calcolare ATR, trade annullato")
        return
        
    # Calcola entry, stop loss e take profit
    if signal_type == 'LONG':
        entry_price = entry_candle.high
        stop_loss = entry_price - (atr_value * 0.1)
        risk = abs(entry_price - stop_loss)
        take_profit = entry_price + (risk * 10)
    else:  # SHORT
        entry_price = entry_candle.low
        stop_loss = entry_price + (atr_value * 0.1)
        risk = abs(entry_price - stop_loss)
        take_profit = entry_price - (risk * 10)

    # Calcola position size
    position_size = calculate_position_size(entry_price, stop_loss, ACCOUNT_SIZE)
    
    if position_size < 1:
        print("Position size troppo piccola")
        return
        
    # Arrotonda i prezzi al tick size
    entry_price = round_to_tick(entry_price)
    stop_loss = round_to_tick(stop_loss)
    take_profit = round_to_tick(take_profit)
    
    # Validazione prezzi
    if not validate_prices(entry_price, take_profit, stop_loss):
        return

    try:
        # Crea l'ordine di entrata (Buy Stop o Sell Stop)
        entry = StopOrder(
            'BUY' if signal_type == 'LONG' else 'SELL',
            position_size,
            entry_price,
            outsideRth=False,  # Solo durante le ore di mercato
            tif='DAY'  # Ordine valido solo per oggi
        )
        entry.transmit = False  # Non trasmettere ancora
        
        # Crea l'ordine di Take Profit
        tp = LimitOrder(
            'SELL' if signal_type == 'LONG' else 'BUY',
            position_size,
            take_profit,
            outsideRth=False,
            tif='DAY'
        )
        tp.transmit = False
        tp.parentId = entry.orderId
        
        # Crea l'ordine di Stop Loss
        sl = StopOrder(
            'SELL' if signal_type == 'LONG' else 'BUY',
            position_size,
            stop_loss,
            outsideRth=False,
            tif='DAY'
        )
        sl.transmit = True  # Ultimo ordine del bracket, ora trasmetti tutto
        sl.parentId = entry.orderId

        # Piazza gli ordini
        entry_trade = ib.placeOrder(contract, entry)
        tp_trade = ib.placeOrder(contract, tp)
        sl_trade = ib.placeOrder(contract, sl)
        
        print(f"""
                Trade piazzato:
                Direction: {signal_type}
                Size: {position_size}
                Entry Stop: {entry_price}
                Stop Loss: {stop_loss}
                Take Profit: {take_profit}
                Risk: ${risk * position_size:.2f}
                        """)
        
        # Aggiorna lo stato del bot
        bot_state["in_trade"] = True
        bot_state["trade_details"] = {
            "type": signal_type,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "position_size": position_size,
            "trades": [entry_trade, tp_trade, sl_trade]
        }
        
    except Exception as e:
        print(f"❌ Errore nel piazzamento degli ordini: {e}")
        return None

def is_tradable_time():
    """Verifica se il mercato è aperto"""
    current_time = datetime.now(ZoneInfo("US/Central"))
    current_time = current_time.time()
    
    # Verifica l'orario di mercato (9:30 - 15:15 CT)
    #return MARKET_OPEN <= current_time <= LAST_ENTRY_TIME
    return True

def get_last_candle(ib, contract):
    """
    Richiede gli ultimi n_candles dati storici
    Ritorna le ultime due candele per verificare la chiusura
    """
    try:
        # Richiediamo qualche candela in più per sicurezza
        bars = ib.reqHistoricalData(
            contract,
            endDateTime='',  # '' significa 'now'
            durationStr='1 D',  # Tutte le candele del giorno
            barSizeSetting='5 mins',
            whatToShow='TRADES',
            useRTH=False,
            formatDate=1
        )
        
        if bars and len(bars) > 0:
            return bars[-1]  # Ritorna le ultime n_candles
        return None
        
    except Exception as e:
        print(f"Errore nel recupero dei dati storici: {e}")
        return None

def is_candle_fully_formed(candle_time):
    """
    Verifica che una candela sia completamente formata
    confrontando il suo timestamp con l'orario attuale
    """
    current_time = datetime.now(ZoneInfo("US/Central"))
    candle_end_time = candle_time + timedelta(minutes=TIMEFRAME)
    return current_time >= candle_end_time

def check_new_candle():
    """
    Funzione principale che viene chiamata ogni 5 minuti
    """
    current_time = datetime.now(ZoneInfo("US/Central"))
    print(f"\nVerifica candela alle {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Verifica se siamo in orario di trading
    if not is_tradable_time():
        print("Non è orario di trading. Skip.")
        return
        
    try:
        # Ottieni le ultime due candele
        last_candle = get_last_candle(ib, contract)
        
        if not last_candle:
            print("Nessun dato ricevuto")
            return
        
        last_candle_formed = is_candle_fully_formed(last_candle.date)

        print(f"\nUltima candela ({last_candle.date.strftime('%H:%M')}): {'✅ Chiusa' if last_candle_formed else '❌ In formazione'}")
        print(f"-> Open:{last_candle.open:.2f} High:{last_candle.high:.2f} Low:{last_candle.low:.2f} Close:{last_candle.close:.2f}")
        
        if last_candle_formed:
            print("✅ Candela completata, eseguo logica di trading")
            on_bar_update(last_candle, True)  # Passa la candela come lista per compatibilità
        else:
            print("⚠️ Attendere la completa formazione della candela")
            
    except Exception as e:
        print(f"Errore durante il controllo della nuova candela: {e}")

def setup_schedule():
    """
    Configura lo schedule per eseguire il check ogni 5 minuti
    """
    # Calcola i minuti per l'esecuzione (0, 5, 10, 15, ...)
    for minute in range(0, 60, 5):
        schedule.every().hour.at(f":{minute:02d}").do(check_new_candle)
    
    print("Schedule configurato per eseguire ogni 5 minuti")

def handle_connection_error():
    """Gestisce gli errori di connessione"""
    try:
        if not ib.isConnected():
            print("Riconnessione a IB...")
            ib.disconnect()
            time_module.sleep(5)
            ib.connect(IB_HOST, IB_PORT, clientId=IB_CLIENT_ID)
            ib.qualifyContracts(contract)
    except Exception as e:
        print(f"Errore durante la riconnessione: {e}")

# Setup dello schedule
setup_schedule()

# Esegui immediatamente il primo check
check_new_candle()

# Main loop
print("Bot avviato. In attesa delle prossime candele...")
while True:
    try:
        if not is_tradable_time():
            print("Mercato chiuso, in attesa di riapertura...")
            time_module.sleep(180)
        
        schedule.run_pending()
        ib.sleep(1)  # Usa ib.sleep invece di time.sleep per mantenere la connessione IB attiva
    
    except ConnectionError:
        handle_connection_error()
    except KeyboardInterrupt:
        print("\nChiusura del bot...")
        ib.disconnect()
        break
    except Exception as e:
        print(f"Errore nel main loop: {e}")
        # Potresti voler aggiungere una logica di reconnessione qui
        time_module.sleep(5)