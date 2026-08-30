import time
import requests
import pandas as pd
from binance.client import Client
from binance.enums import *

# ==========================================
# CONFIGURACIÓN Y PARÁMETROS DEL BOT
# ==========================================
API_KEY = "YOUR_API_KEY"
SECRET_KEY = "YOUR_SECRET_KEY"

TELEGRAM_TOKEN = "YOUR_TELEGRAM_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_TELEGRAM_CHAT_ID"

# Lista de pares a monitorear
SIMBOLOS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TIMEFRAME = "1h"
MONTO_INVERSION = 20     # USDT por cada operación
STOP_LOSS_PCT = 0.05     # 5%
TAKE_PROFIT_PCT = 0.10   # 10%

# Conexión con Binance (Sincroniza el reloj del servidor automáticamente)
client = Client(API_KEY, SECRET_KEY, requests_params={"timeout": 20})
client.TIME_OFFSET = client.get_server_time()["serverTime"] - int(time.time() * 1000)

# ==========================================
# FUNCIONES AUXILIARES
# ==========================================

def enviar_telegram(mensaje):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "Markdown"}
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"[X] Error Telegram: {e}")

def obtener_datos_mercado(symbol, interval, limit=100):
    klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
    df = pd.DataFrame(klines, columns=[
        'time', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'
    ])
    df['close'] = df['close'].astype(float)

    df['ema9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema21'] = df['close'].ewm(span=21, adjust=False).mean()

    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))

    return df

def verificar_posicion_abierta(symbol):
    asset = symbol.replace("USDT", "")
    balance = float(client.get_asset_balance(asset=asset)['free'])
    ticker = float(client.get_symbol_ticker(symbol=symbol)['price'])
    return (balance * ticker) > 5.0

def analizar_y_operar(symbol):
    hora_actual = time.strftime('%H:%M:%S')
    print(f"\n--- Analizando {symbol} [{hora_actual}] ---")

    if verificar_posicion_abierta(symbol):
        print(f"[-] Posición activa en {symbol}. Omitiendo...")
        return

    df = obtener_datos_mercado(symbol, TIMEFRAME)
    
    prev_ema9 = df['ema9'].iloc[-2]
    prev_ema21 = df['ema21'].iloc[-2]
    curr_ema9 = df['ema9'].iloc[-1]
    curr_ema21 = df['ema21'].iloc[-1]
    curr_rsi = df['rsi'].iloc[-1]
    precio_actual = df['close'].iloc[-1]

    print(f"{symbol} Precio: ${precio_actual:.2f} | EMA9: {curr_ema9:.2f} | EMA21: {curr_ema21:.2f} | RSI: {curr_rsi:.2f}")

    cruce_alcista = (prev_ema9 <= prev_ema21) and (curr_ema9 > curr_ema21)
    rsi_valido = 50 <= curr_rsi <= 70

    if cruce_alcista and rsi_valido:
        # Verificar si hay saldo libre en USDT suficiente
        saldo_usdt = float(client.get_asset_balance(asset="USDT")['free'])
        if saldo_usdt < MONTO_INVERSION:
            msg_sin_saldo = f"⚠️ *SEÑAL EN {symbol} PERO SIN SALDO SUFICIENTE*\nSaldo libre: ${saldo_usdt:.2f} USDT | Requerido: ${MONTO_INVERSION} USDT"
            print(msg_sin_saldo)
            enviar_telegram(msg_sin_saldo)
            return

        msg_senal = f"🚨 *SEÑAL DE COMPRA EN {symbol}*\nPrecio: ${precio_actual:.2f}"
        print(msg_senal)
        enviar_telegram(msg_senal)
        
        info_simbolo = client.get_symbol_info(symbol)
        precision = info_simbolo['baseAssetPrecision']
        cantidad = round(MONTO_INVERSION / precio_actual, precision)

        orden_compra = client.order_market_buy(symbol=symbol, quantity=cantidad)
        precio_ejecutado = float(orden_compra['fills'][0]['price']) if orden_compra['fills'] else precio_actual

        precio_tp = round(precio_ejecutado * (1 + TAKE_PROFIT_PCT), 2)
        precio_sl = round(precio_ejecutado * (1 - STOP_LOSS_PCT), 2)
        precio_stop_limit = round(precio_sl * 0.995, 2)

        client.create_oco_order(
            symbol=symbol,
            side=SIDE_SELL,
            stopLimitPrice=precio_stop_limit,
            stopPrice=precio_sl,
            price=precio_tp,
            quantity=cantidad,
            stopLimitTimeInForce=TIME_IN_FORCE_GTC
        )

        msg_exito = (
            f"✅ *COMPRA EJECUTADA ({symbol})*\n\n"
            f"• *Entrada:* ${precio_ejecutado:.2f}\n"
            f"• *Inversión:* ${MONTO_INVERSION} USDT\n"
            f"• *Take Profit (+10%):* ${precio_tp}\n"
            f"• *Stop Loss (-5%):* ${precio_sl}"
        )
        print(msg_exito)
        enviar_telegram(msg_exito)

# ==========================================
# BUCLE PRINCIPAL MULTIMONEDA
# ==========================================
if __name__ == "__main__":
    msg_inicio = "🤖 *BOT MULTIMONEDA INICIADO (BTC, ETH, SOL)*"
    print(msg_inicio)
    enviar_telegram(msg_inicio)
    
    while True:
        for simbolo in SIMBOLOS:
            try:
                analizar_y_operar(simbolo)
            except Exception as e:
                msg_error = f"⚠️ *ERROR EN {simbolo}:* {e}"
                print(msg_error)
                enviar_telegram(msg_error)
        
        # Espera 5 minutos entre cada ronda de análisis
        time.sleep(300)