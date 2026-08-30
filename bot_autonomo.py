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
            
            # Obtención segura del precio de compra
            precio_compra = precio_actual
            if isinstance(order, dict) and 'fills' in order and len(order['fills']) > 0:
                precio_compra = float(order['fills'][0]['price'])
                
            stop_loss = precio_compra * (1 - STOP_LOSS_PCT)
            take_profit = precio_compra * (1 + TAKE_PROFIT_PCT)
            
            tp_str = dar_formato_precio(symbol, take_profit)
            sl_str = dar_formato_precio(symbol, stop_loss)
            sl_limit_str = dar_formato_precio(symbol, stop_loss * 0.995)
            
            # Pausa para asiento de comisión
            time.sleep(1.5)
            asset = symbol.replace("USDT", "")
            balance_disponible = float(client.get_asset_balance(asset=asset)["free"])
            qty_str = dar_formato_cantidad(symbol, balance_disponible)
            
            # Creación de Orden OCO con parámetros de tipo explícitos
            try:
                client.create_oco_order(
                    symbol=symbol,
                    side=SIDE_SELL,
                    quantity=qty_str,
                    price=tp_str,
                    stopPrice=sl_str,
                    stopLimitPrice=sl_limit_str,
                    stopLimitTimeInForce=TIME_IN_FORCE_GTC,
                    aboveType='LIMIT_MAKER',
                    belowType='STOP_LOSS_LIMIT'
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
