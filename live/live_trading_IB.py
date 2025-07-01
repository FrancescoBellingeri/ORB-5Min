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
TICKER = 'MNQ'
EXCHANGE = 'CME'
CURRENCY = 'USD'
TIMEFRAME = 5
ACCOUNT_SIZE = 50000 # Il tuo capitale iniziale
MARKET_TIMEZONE = ZoneInfo("US/Central") # Orario sessione New York
MARKET_OPEN = time(8, 30)
DR_CALC_TIME = time(8, 45) # Orario dopo il quale calcoli il DR
LAST_ENTRY_TIME = time(10, 0) # Ultimo orario per un'entrata

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
contract = ContFuture(TICKER, exchange=EXCHANGE, currency=CURRENCY)
ib.qualifyContracts(contract)
print("✅ Contratto qualificato:", contract)

def get_dr_candles(ib, contract):
    """
    Recupera le prime 3 candele dopo l'apertura del mercato per calcolare il DR
    """
    try:
        # Richiediamo i dati della giornata
        bars = ib.reqHistoricalData(
            contract,
            endDateTime='',
            durationStr='1 D',
            barSizeSetting='5 mins',
            whatToShow='TRADES',
            useRTH=True,  # Usa solo orario di mercato
            formatDate=1
        )
        
        if not bars:
            return None
            
        # Converti in DataFrame per facilitare la manipolazione
        df = util.df(bars)
        
        # Trova le prime 3 candele dopo l'apertura del mercato (9:30 CT)
        df['time'] = df['date'].apply(lambda x: x.time())
        opening_candles = df[df['time'] >= MARKET_OPEN].head(3)
        
        if len(opening_candles) >= 3:
            return bars[:3]  # Ritorna le prime 3 candele come BarDataList
        return None
        
    except Exception as e:
        print(f"Errore nel recupero delle candele per il DR: {e}")
        return None

def validate_prices(entry_price, tp_price, stop_loss):
    """Validazione dei prezzi per evitare ordini non validi"""
    if entry_price <= 0 or tp_price <= 0 or stop_loss <= 0:
        return False
    
    print(f"Validazione prezzi: Entry={entry_price}, TP={tp_price}, SL={stop_loss}")
    # Verifica che i prezzi siano multipli del tick size
    tick_size = 0.25  # Per MNQ
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
    if not bot_state["dr_calculated_today"] and current_market_time >= DR_CALC_TIME:
        dr_candles = get_dr_candles(ib, contract)
        
        if dr_candles and len(dr_candles) == 3:
            dr_high = max(candle.high for candle in dr_candles)
            dr_low = min(candle.low for candle in dr_candles)
            
            bot_state["daily_range"]["high"] = dr_high
            bot_state["daily_range"]["low"] = dr_low
            bot_state["dr_calculated_today"] = True
            
            print(f"DR calcolato per oggi: High={dr_high}, Low={dr_low}")
        else:
            print("Non ci sono abbastanza candele per calcolare il DR.")
            return

    # --- Logica di Ingresso (se non siamo già in un trade) ---
    if not bot_state["in_trade"] and bot_state["dr_calculated_today"]:
        # Controlla solo fino alle 11:00
        if current_market_time > LAST_ENTRY_TIME:
            return
            
        signal_type = None
        if bar.close > bot_state["daily_range"]["high"]:
            signal_type = 'LONG'
        elif bar.close < bot_state["daily_range"]["low"]:
            signal_type = 'SHORT'
        
        if signal_type:
            print(f"Segnale di ingresso {signal_type} rilevato!")
            place_trade(signal_type, bar)

def place_trade(signal_type, entry_candle):
    """
    Funzione per calcolare i dettagli del trade e inviare l'ordine a IB.
    """
    dr = bot_state["daily_range"]
    
    if signal_type == 'LONG':
        entry_price = dr['high']
        stop_loss = dr['low']
    else: # SHORT
        entry_price = dr['low']
        stop_loss = dr['high']

    def round_to_tick(price):
        tick_size = 0.25
        return round(price / tick_size) * tick_size
    
    stop_loss = round_to_tick(stop_loss)

    # Qui va la tua logica di position sizing
    # position_size = calculate_position_size(entry_price, stop_loss, ACCOUNT_SIZE)
    # Per sicurezza, iniziamo con una size fissa e piccola!
    position_size = 2 # **USARE SEMPRE UNA SIZE PICCOLA ALL'INIZIO!**
    
    if position_size == 0:
        print("Position size è zero, nessun trade piazzato.")
        return

    # Usiamo un "Bracket Order": un ordine che include Entry, Take Profit e Stop Loss
    # Questo è il modo più sicuro per fare trading algoritmico
    R = abs(entry_price - stop_loss)
    
    if signal_type == 'LONG':
        action_entry = 'BUY'
        tp_price = entry_price + (1.5 * R) # TP1
    else:
        action_entry = 'SELL'
        tp_price = entry_price - (1.5 * R) # TP1

    if not validate_prices(entry_price, tp_price, stop_loss):
        print("Prezzi non validi per l'ordine")
        return
        
    # Definiamo il contratto
    contract = ContFuture(TICKER, EXCHANGE, CURRENCY)
    
    # Creiamo gli ordini
    # Useremo un ordine Stop per entrare quando il prezzo rompe il DR
    entry_order = StopOrder(action_entry, position_size, entry_price)
    entry_order.transmit = False # Non inviare ancora

    take_profit_order = LimitOrder('SELL' if signal_type == 'LONG' else 'BUY', position_size, tp_price)
    take_profit_order.transmit = False

    stop_loss_order = StopOrder('SELL' if signal_type == 'LONG' else 'BUY', position_size, stop_loss)
    stop_loss_order.transmit = True # L'ultimo ordine del bracket trasmette tutto il gruppo

    bracket_orders = [entry_order, take_profit_order, stop_loss_order]
    
    print(f"Invio Bracket Order: {action_entry} {position_size} @ {entry_price}, TP: {tp_price}, SL: {stop_loss}")
    
    # Invia gli ordini
    for order in bracket_orders:
        ib.placeOrder(contract, order)
    
    # Aggiorna lo stato del bot
    bot_state["in_trade"] = True
    bot_state["trade_details"] = {
        "type": signal_type,
        "entry_price": entry_price,
        "sl": stop_loss,
        "tp": tp_price
    }

def is_tradable_time():
    """Verifica se il mercato è aperto"""
    current_time = datetime.now(ZoneInfo("US/Central"))
    current_time = current_time.time()
    
    # Verifica l'orario di mercato (9:30 - 15:15 CT)
    return MARKET_OPEN <= current_time <= LAST_ENTRY_TIME
    #return True

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