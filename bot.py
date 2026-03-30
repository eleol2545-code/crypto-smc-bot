import ccxt
import requests
import time
import os

TELEGRAM_TOKEN = "8645396589:AAHIceq907-38mvWJfa9BRaQWsrzC86ivNU"

# ==================== ВАШИ ПРОКСИ ====================
PROXY1 = "socks5://bqd9tD8A:i6wUJxiU@155.212.48.112:63675"
PROXY2 = "socks5://bqd9tD8A:i6wUJxiU@154.194.89.27:62841"

print("=" * 60)
print("🔍 ПРОВЕРКА ПРОКСИ И БИРЖ")
print("=" * 60)

# ==================== ПРОВЕРКА ПРОКСИ ====================
def test_proxy(proxy_url):
    try:
        proxies = {"http": proxy_url, "https": proxy_url}
        r = requests.get("https://api.ipify.org", proxies=proxies, timeout=10)
        print(f"✅ ПРОКСИ РАБОТАЕТ! IP: {r.text}")
        return True
    except Exception as e:
        print(f"❌ Прокси не работает: {e}")
        return False

print("\n📡 Проверяем прокси 1...")
proxy1_works = test_proxy(PROXY1)

print("\n📡 Проверяем прокси 2...")
proxy2_works = test_proxy(PROXY2)

if not proxy1_works and not proxy2_works:
    print("\n❌ НИ ОДИН ПРОКСИ НЕ РАБОТАЕТ!")
    print("💡 Нужны новые прокси")
    exit(1)

WORKING_PROXY = PROXY1 if proxy1_works else PROXY2
print(f"\n✅ Используем прокси: {WORKING_PROXY[:50]}...")

# ==================== ПРОВЕРКА БИРЖ (БЕЗ КОНФЛИКТА) ====================
print("\n" + "=" * 60)
print("🏦 ПРОВЕРКА БИРЖ ЧЕРЕЗ ПРОКСИ")
print("=" * 60)

def test_exchange(name, exchange_class, symbol, params=None):
    if params is None:
        params = {}
    try:
        # ВАЖНО: не используем http_proxy/https_proxy отдельно
        # Вместо этого используем aiohttp_proxy или настраиваем через session
        ex = exchange_class(params)
        ex.enableRateLimit = True
        
        # Правильный способ установки прокси для ccxt
        ex.proxy = WORKING_PROXY
        ex.proxy_type = 'socks5'  # socks5 или http
        
        ticker = ex.fetch_ticker(symbol)
        print(f"✅ {name} - РАБОТАЕТ! Цена: ${ticker['last']:.2f}")
        return True, ex
    except Exception as e:
        print(f"❌ {name} - НЕ РАБОТАЕТ: {str(e)[:80]}")
        return False, None

exchanges = [
    ("Binance", ccxt.binance, "BTC/USDT", {'options': {'defaultType': 'future'}}),
    ("Bybit", ccxt.bybit, "BTCUSDT", {'options': {'defaultType': 'linear'}}),
    ("KuCoin", ccxt.kucoin, "BTC/USDT", {}),
    ("Gate.io", ccxt.gateio, "BTC_USDT", {'options': {'defaultType': 'swap'}}),
]

print("\n")
working_exchanges = []
selected_exchange = None
selected_name = None

for name, cls, symbol, params in exchanges:
    ok, ex = test_exchange(name, cls, symbol, params)
    if ok:
        working_exchanges.append(name)
        if not selected_exchange:
            selected_exchange = ex
            selected_name = name
    time.sleep(1)

# ==================== РЕЗУЛЬТАТ ====================
print("\n" + "=" * 60)
print("📊 РЕЗУЛЬТАТЫ ПРОВЕРКИ")
print("=" * 60)

if working_exchanges:
    print(f"\n✅ РАБОТАЮТ: {', '.join(working_exchanges)}")
    print(f"\n🎯 РЕКОМЕНДАЦИЯ: Используйте {working_exchanges[0]}")
    print(f"\n📡 ТЕСТОВЫЙ ЗАПРОС К {working_exchanges[0]}...")
    
    # Делаем тестовый запрос к первой рабочей бирже
    try:
        if working_exchanges[0] == "Binance":
            ticker = selected_exchange.fetch_ticker("BTC/USDT")
        elif working_exchanges[0] == "Bybit":
            ticker = selected_exchange.fetch_ticker("BTCUSDT")
        elif working_exchanges[0] == "KuCoin":
            ticker = selected_exchange.fetch_ticker("BTC/USDT")
        else:
            ticker = selected_exchange.fetch_ticker("BTC/USDT")
        
        print(f"\n✅ УСПЕШНО! BTC: ${ticker['last']:.2f}")
        print(f"📈 24h объем: ${ticker.get('quoteVolume', 0):.0f}")
        print(f"📊 Изменение: {ticker.get('percentage', 0):+.2f}%")
        
        print("\n" + "=" * 60)
        print("🎉 ПРОКСИ И БИРЖА РАБОТАЮТ!")
        print("💡 МОЖНО ЗАПУСКАТЬ ПОЛНОГО БОТА")
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ Ошибка при тестовом запросе: {e}")
else:
    print("\n❌ НИ ОДНА БИРЖА НЕ РАБОТАЕТ!")
    print("💡 Возможные причины:")
    print("   1. Прокси не работают")
    print("   2. Биржи блокируют прокси")
    print("   3. Нужны новые прокси")
    print("\n❌ БОТ НЕ МОЖЕТ РАБОТАТЬ БЕЗ БИРЖИ!")

print("\n" + "=" * 60)
