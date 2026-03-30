import ccxt
import requests
import time

# ==================== ПРОКСИ ====================
PROXIES_LIST = [
    {
        'host': '155.212.48.112',
        'port': '63674',
        'user': 'bqd9tD8A',
        'pass': 'i6wUJxiU',
        'type': 'http'
    },
    {
        'host': '92.61.111.34',
        'port': '51225',
        'user': 'izupU25r3SLfpho',
        'pass': 'EV4nseGTeBlpY17',
        'type': 'socks5'
    },
]

print("=" * 60)
print("🔍 ТЕСТ ВСЕХ ПРОКСИ")
print("=" * 60)

def test_proxy(proxy_info):
    if proxy_info['type'] == 'http':
        proxy_url = f"http://{proxy_info['user']}:{proxy_info['pass']}@{proxy_info['host']}:{proxy_info['port']}"
    else:
        proxy_url = f"socks5://{proxy_info['user']}:{proxy_info['pass']}@{proxy_info['host']}:{proxy_info['port']}"
    
    try:
        proxies = {"http": proxy_url, "https": proxy_url}
        r = requests.get("https://api.ipify.org", proxies=proxies, timeout=10)
        print(f"✅ {proxy_info['type'].upper()} прокси РАБОТАЕТ! IP: {r.text}")
        return True
    except Exception as e:
        print(f"❌ {proxy_info['type'].upper()} прокси {proxy_info['host']}:{proxy_info['port']} не работает: {e}")
        return False

def test_exchange(name, exchange_class, symbol, proxy_info, params=None):
    if params is None:
        params = {}
    try:
        ex = exchange_class(params)
        ex.enableRateLimit = True
        
        if proxy_info['type'] == 'http':
            ex.http_proxy = f"http://{proxy_info['user']}:{proxy_info['pass']}@{proxy_info['host']}:{proxy_info['port']}"
            ex.https_proxy = f"http://{proxy_info['user']}:{proxy_info['pass']}@{proxy_info['host']}:{proxy_info['port']}"
        else:
            ex.proxy = f"socks5://{proxy_info['host']}:{proxy_info['port']}"
            ex.proxy_login = proxy_info['user']
            ex.proxy_password = proxy_info['pass']
            ex.proxy_type = 'socks5'
        
        ticker = ex.fetch_ticker(symbol)
        print(f"   ✅ {name} - РАБОТАЕТ! Цена: ${ticker['last']:.2f}")
        return True
    except Exception as e:
        print(f"   ❌ {name} - {str(e)[:60]}")
        return False

# ==================== ТЕСТИРУЕМ КАЖДЫЙ ПРОКСИ ====================
working_proxy = None

for proxy_info in PROXIES_LIST:
    print("\n" + "=" * 60)
    print(f"📡 ТЕСТИРУЕМ {proxy_info['type'].upper()} ПРОКСИ: {proxy_info['host']}:{proxy_info['port']}")
    print("=" * 60)
    
    # Проверяем прокси
    if not test_proxy(proxy_info):
        continue
    
    # Проверяем биржи
    exchanges = [
        ("Bybit", ccxt.bybit, "BTCUSDT", {'options': {'defaultType': 'linear'}}),
        ("KuCoin", ccxt.kucoin, "BTC/USDT", {}),
        ("Gate.io", ccxt.gateio, "BTC_USDT", {'options': {'defaultType': 'swap'}}),
        ("Binance", ccxt.binance, "BTC/USDT", {'options': {'defaultType': 'future'}}),
    ]
    
    working = []
    for name, cls, symbol, params in exchanges:
        if test_exchange(name, cls, symbol, proxy_info, params):
            working.append(name)
        time.sleep(0.5)
    
    if working:
        print(f"\n✅ С ЭТИМ ПРОКСИ РАБОТАЮТ: {', '.join(working)}")
        print(f"\n🎉 УСПЕХ! {proxy_info['type'].upper()} прокси {proxy_info['host']}:{proxy_info['port']} ГОДЕН!")
        working_proxy = proxy_info
        break

if not working_proxy:
    print("\n❌ НИ ОДИН ПРОКСИ НЕ РАБОТАЕТ!")
else:
    print("\n" + "=" * 60)
    print(f"🏆 РЕКОМЕНДУЕМЫЙ ПРОКСИ: {working_proxy['type'].upper()}://{working_proxy['host']}:{working_proxy['port']}")
    print("=" * 60)

print("\n" + "=" * 60)
