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

SIMBOLOS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TIMEFRAME = "1h"
MONTO_INVERSION = 20
STOP_LOSS_PCT = 0.05
TAKE_PROFIT_PCT = 0.10

# ==========================================
# FUNCIONES AUXILIARES Y OBTENCIÓN DE IP
# ==========================================
def obtener_ip_publica():
    """Consulta la IP pública exacta desde la que opera el servidor"""
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

# (Conserva las funciones obtener_datos_mercado, verificar_posicion_abierta y analizar_y_operar sin cambios)

# ==========================================
# BUCLE PRINCIPAL
# ==========================================
if __name__ == "__main__":
    ip_servidor = obtener_ip_publica()
    msg_inicio = f"🤖 *BOT INICIADO EN RAILWAY*\n\n📍 *IP de salida:* `{ip_servidor}`\n\nCopia esta IP y agrégala a las restricciones de tu API Key en Binance."
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
