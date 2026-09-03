import os
import time
import math
import requests
import pandas as pd
from binance.client import Client
from binance.enums import *

# ==========================================
# CONFIGURACIÓN DE PRODUCCIÓN
# ==========================================
API_KEY = os.getenv("API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SIMBOLOS = ["PEPEUSDT", "SUIUSDT", "NEARUSDT"]
TIMEFRAME = "15m"
MONTO_INVERSION = 10     # USDT
STOP_LOSS_PCT = 0.015    # 1.5%
TAKE_PROFIT_PCT = 0.025   # 2.5%

# ==========================================
# FUNCIONES AUXILIARES
# ==========================================
def obtener_ip_publica():
    try:
        return requests.get('https://api.ipify.org', timeout=5).text
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
                return valor_en_usdt > 8.0
        return False
    except Exception as e:
        print(f"[X] Error al verificar posición: {e}")
        return False

def dar_formato_precio(symbol, price):
    try:
        info = client.get_symbol_info(symbol)
        for f in info['filters']:
            if f['filterType'] == 'PRICE_FILTER':
                tick_size = float(f['tickSize'])
                if tick_size < 1:
                    precision = int(round(-math.log10(tick_size)))
                else:
                    precision = 0
                return f"{price:.{precision}f}"
        return f"{price:.8f}"
    except Exception:
        return f"{price:.8f}"

def dar_formato_cantidad(symbol, quantity):
    try:
        info = client.get_symbol_info(symbol)
        for f in info['filters']:
            if f['filterType'] == 'LOT_SIZE':
                step_size = float(f['stepSize'])
                if step_size < 1:
                    precision = int(round(-math.log10(step_size)))
                else:
                    precision = 0
                return f"{quantity:.{precision}f}"
        return f"{quantity:.0f}"
    except Exception:
        return f"{quantity:.0f}"

def analizar_y_operar(symbol):
    print(f"--- Analizando {symbol} [{time.strftime('%H:%M:%S')}] ---")
    df = obtener_datos_mercado(symbol, TIMEFRAME)
    df = calcular_indicadores(df)
    
    precio_actual = float(df['close'].iloc[-1])
    rsi_actual = float(df['RSI'].iloc[-1])
    sma_50 = float(df['SMA_50'].iloc[-1])
    sma_200 = float(df['SMA_200'].iloc[-1])
    
    posicion_activa = verificar_posicion_abierta(symbol)
    
    if posicion_activa:
        print(f"[-] Posición activa en {symbol}. Omitiendo...")
        return

    # Condición de estrategia: SMA50 > SMA200 y RSI < 60
    if sma_50 > sma_200 and rsi_actual < 60:
        saldo_usdt = float(client.get_asset_balance(asset="USDT")["free"])
        if saldo_usdt >= MONTO_INVERSION:
            print(f"[+] Ejecutando compra a mercado de {symbol}...")
            
            order = client.create_order(
                symbol=symbol,
                side=SIDE_BUY,
                type=ORDER_TYPE_MARKET,
                quoteOrderQty=MONTO_INVERSION
            )
            
            precio_compra = precio_actual
            stop_loss = precio_compra * (1 - STOP_LOSS_PCT)
            take_profit = precio_compra * (1 + TAKE_PROFIT_PCT)
            
            tp_str = dar_formato_precio(symbol, take_profit)
            sl_str = dar_formato_precio(symbol, stop_loss)
            sl_limit_str = dar_formato_precio(symbol, stop_loss * 0.995)
            
            # Pausa de seguridad
            time.sleep(3.0)
            asset = symbol.replace("USDT", "")
            balance_disponible = float(client.get_asset_balance(asset=asset)["free"])
            
            # Aplicación de margen de seguridad del 0.05% para evitar error de saldo por comisiones
            balance_seguro = balance_disponible * 0.9995
            qty_str = dar_formato_cantidad(symbol, balance_seguro)
            
            print(f"[+] Enviando OCO -> Qty: {qty_str} | TP: {tp_str} | SL Stop: {sl_str} | SL Limit: {sl_limit_str}")
            
            msg_buy = (f"🚀 *ORDEN DE COMPRA EJECUTADA EN {symbol}*\n\n"
                       f"• Precio Entrada: ${dar_formato_precio(symbol, precio_compra)}\n"
                       f"• Take Profit (+2.5%): ${tp_str}\n"
                       f"• Stop Loss (-1.5%): ${sl_str}\n"
                       f"• Inversión: ${MONTO_INVERSION} USDT")
            enviar_telegram(msg_buy)
            
            try:
                params = {
                    'symbol': symbol,
                    'side': 'SELL',
                    'quantity': qty_str,
                    'price': tp_str,
                    'stopPrice': sl_str,
                    'stopLimitPrice': sl_limit_str,
                    'stopLimitTimeInForce': 'GTC'
                }
                res_oco = client._request_api('post', 'order/oco', signed=True, data=params)
                print(f"[+] RESPUESTA OCO BINANCE: {res_oco}")
                enviar_telegram(f"✅ *ORDEN OCO COLOCADA CON ÉXITO EN {symbol}*")
            except Exception as e_oco:
                msg_oco_err = f"⚠️ *COMPRA EN {symbol} OK PERO FALLÓ LA OCO:* `{e_oco}`"
                print(msg_oco_err)
                enviar_telegram(msg_oco_err)
        else:
            print(f"[-] Saldo insuficiente de USDT.")
    else:
        print(f"[i] {symbol}: Sin señal (RSI: {rsi_actual:.1f} | SMA50: {sma_50:.4f} | SMA200: {sma_200:.4f})")

# ==========================================
# BUCLE PRINCIPAL
# ==========================================
if __name__ == "__main__":
    ip_servidor = obtener_ip_publica()
    msg_inicio = f"🤖 *BOT EN PRODUCCIÓN CONTINUA (PEPE / SUI / NEAR)*\n\n📍 *IP de salida:* `{ip_servidor}`"
    print(msg_inicio)
    enviar_telegram(msg_inicio)
    
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
