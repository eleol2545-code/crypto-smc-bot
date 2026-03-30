import requests
import time
import ccxt
import pandas as pd
import numpy as np
import json
import os
from datetime import datetime

# ==================== НАСТРОЙКА SOCKS5 ПРОКСИ ====================
# ВАШИ ПРОКСИ (проверьте, работают ли)
PROXY1 = "socks5://bqd9tD8A:i6wUJxiU@155.212.48.112:63675"
PROXY2 = "socks5://bqd9tD8A:i6wUJxiU@154.194.89.27:62841"

# Пробуем первый прокси
PROXY_URL = PROXY1
PROXIES = {"http": PROXY1, "https": PROXY1}

# Проверяем прокси
try:
    r = requests.get("https://api.ipify.org", proxies=PROXIES, timeout=10)
    print(f"✅ Прокси работает! Ваш IP: {r.text}")
except Exception as e:
    print(f"❌ Прокси 1 не работает: {e}")
    print("Пробуем прокси 2...")
    PROXY_URL = PROXY2
    PROXIES = {"http": PROXY2, "https": PROXY2}
    try:
        r = requests.get("https://api.ipify.org", proxies=PROXIES, timeout=10)
        print(f"✅ Прокси 2 работает! Ваш IP: {r.text}")
    except:
        print("❌ Оба прокси не работают")
        PROXIES = None

# ==================== ПОДКЛЮЧЕНИЕ К БИРЖЕ ЧЕРЕЗ ПРОКСИ ====================

def create_exchange_with_proxy(exchange_class, params):
    try:
        exchange = exchange_class(params)
        exchange.enableRateLimit = True
        if PROXIES:
            exchange.http_proxy = PROXY_URL
            exchange.https_proxy = PROXY_URL
        return exchange
    except:
        return None

exchange = None
exchange_name = None

# Пробуем Binance (самая крупная)
try:
    ex = create_exchange_with_proxy(ccxt.binance, {'options': {'defaultType': 'future'}})
    if ex:
        ticker = ex.fetch_ticker('BTC/USDT')
        exchange = ex
        exchange_name = 'Binance'
        print(f"✅ Binance подключена! BTC: ${ticker['last']:.2f}")
except Exception as e:
    print(f"Binance ошибка: {e}")

# Если Binance не работает, пробуем Bybit
if not exchange:
    try:
        ex = create_exchange_with_proxy(ccxt.bybit, {'options': {'defaultType': 'linear'}})
        if ex:
            ticker = ex.fetch_ticker('BTCUSDT')
            exchange = ex
            exchange_name = 'Bybit'
            print(f"✅ Bybit подключена! BTC: ${ticker['last']:.2f}")
    except Exception as e:
        print(f"Bybit ошибка: {e}")

# Если Bybit не работает, пробуем KuCoin
if not exchange:
    try:
        ex = create_exchange_with_proxy(ccxt.kucoin, {})
        if ex:
            ticker = ex.fetch_ticker('BTC/USDT')
            exchange = ex
            exchange_name = 'KuCoin'
            print(f"✅ KuCoin подключена! BTC: ${ticker['last']:.2f}")
    except Exception as e:
        print(f"KuCoin ошибка: {e}")

if not exchange:
    print("❌ НИ ОДНА БИРЖА НЕ ПОДКЛЮЧИЛАСЬ! Проверьте прокси.")
    exit(1)

# ==================== ОСТАЛЬНОЙ КОД (SMC, ТЕЛЕГРАМ, СДЕЛКИ) ====================
# ... (весь остальной код из предыдущей версии)
