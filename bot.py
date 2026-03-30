import ccxt
import requests
import time

# ==================== ВАШИ ПРОКСИ ====================
PROXY1 = "socks5://bqd9tD8A:i6wUJxiU@155.212.48.112:63675"
PROXY2 = "socks5://bqd9tD8A:i6wUJxiU@154.194.89.27:62841"

# ==================== ПРОВЕРКА ПРОКСИ ====================
print("=" * 60)
print("🔍 ПРОВЕРКА ПРОКСИ")
print("=" * 60)

def test_proxy(proxy_url):
    try:
        proxies = {"http": proxy_url, "https": proxy_url}
        r = requests.get("https://api.ipify.org", proxies=proxies, timeout=10)
        print(f"✅ ПРОКСИ РАБОТАЕТ! Ваш IP: {r.text}")
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

# Выбираем рабочий прокси
WORKING_PROXY = PROXY1 if proxy1_works else PROXY2
print(f"\n✅ Используем прокси: {WORKING_PROXY[:50]}...")

# ==================== ПРОВЕРКА БИРЖ ====================
print("\n" + "=" * 60)
print("🏦 ПРОВЕРКА БИРЖ ЧЕРЕЗ ПРОКСИ")
print("=" * 60)

def test_exchange(name, exchange_class, symbol, params=None):
    if params is None:
        params = {}
    try:
        ex = exchange_class(params)
        ex.enableRateLimit = True
        ex.http_proxy = WORKING_PROXY
        ex.https_proxy = WORKING_PROXY
        
        ticker = ex.fetch_ticker(symbol)
        print(f"✅ {name} - РАБОТАЕТ! Цена: ${ticker['last']:.2f}")
        return True
    except Exception as e:
        print(f"❌ {name} - НЕ РАБОТАЕТ: {str(e)[:80]}")
        return False

# Тестируем биржи
exchanges = [
    ("Binance", ccxt.binance, "BTC/USDT", {'options': {'defaultType': 'future'}}),
    ("Bybit", ccxt.bybit, "BTCUSDT", {'options': {'defaultType': 'linear'}}),
    ("KuCoin", ccxt.kucoin, "BTC/USDT", {}),
    ("Gate.io", ccxt.gateio, "BTC_USDT", {'options': {'defaultType': 'swap'}}),
    ("OKX", ccxt.okx, "BTC-USDT-SWAP", {'options': {'defaultType': 'swap'}}),
]

print("\n")
working_exchanges = []
for name, cls, symbol, params in exchanges:
    if test_exchange(name, cls, symbol, params):
        working_exchanges.append(name)
    time.sleep(1)  # пауза чтобы не забанили

# ==================== РЕЗУЛЬТАТ ====================
print("\n" + "=" * 60)
print("📊 РЕЗУЛЬТАТЫ ПРОВЕРКИ")
print("=" * 60)

if working_exchanges:
    print(f"\n✅ РАБОТАЮТ: {', '.join(working_exchanges)}")
    print(f"\n🎯 РЕКОМЕНДАЦИЯ: Используйте {working_exchanges[0]}")
else:
    print("\n❌ НИ ОДНА БИРЖА НЕ РАБОТАЕТ!")
    print("💡 Возможные причины:")
    print("   1. Прокси не работают")
    print("   2. Биржи блокируют прокси")
    print("   3. Нужны новые прокси")

print("\n" + "=" * 60)
