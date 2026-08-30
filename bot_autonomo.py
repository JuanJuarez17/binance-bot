import os
import time
import requests
import pandas as pd
from binance.client import Client
from binance.enums import *

# ==========================================
# CONFIGURACIÓN Y PARÁMETROS DEL BOT
# ==========================================
API_KEY = os.getenv("API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SIMBOLOS = ["PEPEUSDT", "SUIUSDT", "NEARUSDT"]
TIMEFRAME = "15m"         # Velas de 15 minutos
MONTO_INVERSION = 10     # Mínimo permitido por Binance (MIN_NOTIONAL)
STOP_LOSS_PCT = 0.015    # 1.5%
TAKE_PROFIT_PCT = 0.025   # 2.5%

# ==========================================
# FUNCIONES AUXILIARES
# ==========================================
def obtener_ip_publica():
    try:
        ip = requests.get('https://api.ipify.org', timeout=5).text
        return ip
    except Exception:
        return "No disponible"

def enviar_telegram(mensaje):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "Markdown"}
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"[X] Error Telegram: {e}")

def obtener_datos_mercado(symbol, interval, limit=300):
    klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
    df = pd.DataFrame(klines, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_asset_volume', 'number_of_trades',
        'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
    ])
    df['close'] = df['close'].astype(float)
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    return df

def calcular_indicadores(df):
    df['SMA_50'] = df['close'].rolling(window=50).mean()
    df['SMA_200'] = df['close'].rolling(window=200).mean()
    
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    return df

def verificar_posicion_abierta(symbol):
    try:
        asset = symbol.replace("USDT", "")
        account_info = client.get_account()
        for b in account_info['balances']:
            if b['asset'] == asset:
                balance_total = float(b['free']) + float(b['locked'])
                ticker_precio = float(client.get_symbol_ticker(symbol=symbol)["price"])
                valor_en_usdt = balance_total * ticker_precio
                return valor_en_usdt > 3.0
        return False
    except Exception as e:
        print(f"[X] Error al verificar posición: {e}")
        return False

def dar_formato_precio(symbol, price):
    info = client.get_symbol_info(symbol)
    precision = 2
    for f in info['filters']:
        if f['filterType'] == 'PRICE_FILTER':
            tick_size = float(f['tickSize'])
            if tick_size < 1:
                precision = len(str(tick_size).split('.')[1].rstrip('0'))
            else:
                precision = 0
            break
    return f"{price:.{precision}f}"

def dar_formato_cantidad(symbol, quantity):
    info = client.get_symbol_info(symbol)
    precision = 0
    for f in info['filters']:
        if f['filterType'] == 'LOT_SIZE':
            step_size = float(f['stepSize'])
            if step_size < 1:
                precision = len(str(step_size).split('.')[1].rstrip('0'))
            else:
                precision = 0
            break
    return f"{quantity:.{precision}f}"

def analizar_y_operar(symbol):
    print(f"--- Analizando {symbol} [{time.strftime('%H:%M:%S')}] ---")
    df = obtener_datos_mercado(symbol, TIMEFRAME)
    df = calcular_indicadores(df)
    
    ultima_vela = df.iloc[-1]
    precio_actual = ultima_vela['close']
    rsi_actual = ultima_vela['RSI']
    sma_50 = ultima_vela['SMA_50']
    sma_200 = ultima_vela['SMA_200']
    
    posicion_activa = verificar_posicion_abierta(symbol)
    
    if posicion_activa:
        print(f"[-] Posición activa en {symbol} (Libre/Bloqueada). Omitiendo...")
        return

    # Condición de Compra Intradía: SMA50 > SMA200 y RSI < 60
    if sma_50 > sma_200 and rsi_actual < 60:
        saldo_usdt = float(client.get_asset_balance(asset="USDT")["free"])
        if saldo_usdt >= MONTO_INVERSION:
            order = client.create_order(
                symbol=symbol,
                side=SIDE_BUY,
                type=ORDER_TYPE_MARKET,
                quoteOrderQty=MONTO_INVERSION
            )
            
            # Obtención segura del precio de compra (Protección contra 'list index out of range')
            precio_compra = precio_actual
            if isinstance(order, dict) and 'fills' in order and len(order['fills']) > 0:
                precio_compra = float(order['fills'][0]['price'])
                
            stop_loss = precio_compra * (1 - STOP_LOSS_PCT)
            take_profit = precio_compra * (1 + TAKE_PROFIT_PCT)
            
            tp_str = dar_formato_precio(symbol, take_profit)
            sl_str = dar_formato_precio(symbol, stop_loss)
            sl_limit_str = dar_formato_precio(symbol, stop_loss * 0.995)
            
            # Pausa breve para asegurar asentamiento del balance en Binance tras la comisión
            time.sleep(1.5)
            asset = symbol.replace("USDT", "")
            balance_disponible = float(client.get_asset_balance(asset=asset)["free"])
            qty_str = dar_formato_cantidad(symbol, balance_disponible)
            
            # Creación de Orden OCO protegida
            try:
                client.create_oco_order(
                    symbol=symbol,
                    side=SIDE_SELL,
                    quantity=qty_str,
                    price=tp_str,
                    stopPrice=sl_str,
                    stopLimitPrice=sl_limit_str,
                    stopLimitTimeInForce=TIME_IN_FORCE_GTC
                )
                print(f"[+] Orden OCO creada exitosamente para {symbol}")
            except Exception as e_oco:
                msg_oco_err = f"⚠️ *COMPRA EN {symbol} REALIZADA PERO FALLÓ OCO:* {e_oco}"
                print(msg_oco_err)
                enviar_telegram(msg_oco_err)
            
            msg = (f"🚀 *ORDEN DE COMPRA EJECUTADA EN {symbol}*\n\n"
                   f"• Precio Entrada: ${dar_formato_precio(symbol, precio_compra)}\n"
                   f"• Take Profit (+2.5%): ${tp_str}\n"
                   f"• Stop Loss (-1.5%): ${sl_str}\n"
                   f"• Inversión: ${MONTO_INVERSION} USDT")
            enviar_telegram(msg)
        else:
            print(f"[-] Saldo insuficiente de USDT para operar en {symbol}.")
    else:
        print(f"[i] {symbol}: Sin señal de compra (RSI: {rsi_actual:.1f} | SMA50: {sma_50:.8f} | SMA200: {sma_200:.8f})")

# ==========================================
# BUCLE PRINCIPAL
# ==========================================
if __name__ == "__main__":
    ip_servidor = obtener_ip_publica()
    msg_inicio = f"🤖 *BOT REINICIADO (SINTAXIS OCO Y PRECIO SEGURO)*\n\n📍 *IP de salida:* `{ip_servidor}`"
    print(msg_inicio)
    enviar_telegram(msg_inicio)
    
    # Conexión con Binance
    client = Client(API_KEY, SECRET_KEY, requests_params={"timeout": 20})
    client.TIME_OFFSET = client.get_server_time()["serverTime"] - int(time.time() * 1000)

    while True:
        for simbolo in SIMBOLOS:
            try:
                analizar_y_operar(simbolo)
            except Exception as e:
                msg_error = f"⚠️ *ERROR EN {simbolo}:* {e}"
                print(msg_error)
                enviar_telegram(msg_error)
        
        time.sleep(300)
