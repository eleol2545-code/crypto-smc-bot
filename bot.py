import ccxt
import time

print("=" * 60)
print("🔍 ТЕСТ ПОДКЛЮЧЕНИЯ КО ВСЕМ БИРЖАМ (ВКЛЮЧАЯ BINANCE)")
print("=" * 60)

# Список бирж для тестирования
exchanges = [
    ("Binance", ccxt.binance, "BTC/USDT", {'options': {'defaultType': 'spot'}}),
    ("Bybit", ccxt.bybit, "BTC/USDT", {'options': {'defaultType': 'spot'}}),
    ("KuCoin", ccxt.kucoin, "BTC/USDT", {}),
    ("Gate.io", ccxt.gateio, "BTC/USDT", {}),
    ("OKX", ccxt.okx, "BTC/USDT", {}),
    ("Huobi", ccxt.huobi, "BTC/USDT", {}),
    ("Bitget", ccxt.bitget, "BTC/USDT", {}),
]

print("\n📡 ПРОВЕРКА...\n")

working_exchanges = []
failed_exchanges = []

for name, cls, symbol, params in exchanges:
    try:
        print(f"   Пробуем {name}...", end=" ")
        
        ex = cls(params)
        ex.enableRateLimit = True
        
        ticker = ex.fetch_ticker(symbol)
        price = ticker['last']
        volume = ticker.get('quoteVolume', 0)
        
        print(f"✅ РАБОТАЕТ! Цена: ${price:.2f}, Объем: ${volume/1_000_000:.2f}M")
        working_exchanges.append({
            'name': name,
            'exchange': ex,
            'symbol': symbol,
            'price': price,
            'volume': volume
        })
        
    except Exception as e:
        error = str(e)[:60]
        print(f"❌ НЕ РАБОТАЕТ: {error}")
        failed_exchanges.append(name)
    
    time.sleep(1)

# ==================== РЕЗУЛЬТАТЫ ====================
print("\n" + "=" * 60)
print("📊 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ")
print("=" * 60)

if working_exchanges:
    print(f"\n✅ РАБОТАЮТ ({len(working_exchanges)} бирж):")
    for ex in working_exchanges:
        print(f"   • {ex['name']}: ${ex['price']:.2f} | Объем: ${ex['volume']/1_000_000:.2f}M")
    
    # Агрегированные данные
    prices = [ex['price'] for ex in working_exchanges]
    volumes = [ex['volume'] for ex in working_exchanges]
    
    avg_price = sum(prices) / len(prices)
    total_volume = sum(volumes)
    
    if total_volume > 0:
        weighted_price = sum(p * v for p, v in zip(prices, volumes)) / total_volume
    else:
        weighted_price = avg_price
    
    price_spread = max(prices) - min(prices)
    price_spread_pct = (price_spread / avg_price) * 100 if avg_price > 0 else 0
    
    print(f"\n📊 АГРЕГИРОВАННЫЕ ДАННЫЕ:")
    print(f"   • Средняя цена: ${avg_price:.2f}")
    print(f"   • Взвешенная цена: ${weighted_price:.2f}")
    print(f"   • Разброс цен: ${price_spread:.2f} ({price_spread_pct:.2f}%)")
    print(f"   • Общий объем 24h: ${total_volume/1_000_000:.2f}M")
    
    # Какая биржа самая активная
    most_active = max(working_exchanges, key=lambda x: x['volume'])
    print(f"\n🏆 САМАЯ АКТИВНАЯ БИРЖА: {most_active['name']} (${most_active['volume']/1_000_000:.2f}M)")
    
else:
    print("\n❌ НИ ОДНА БИРЖА НЕ РАБОТАЕТ!")

print("\n" + "=" * 60)

if failed_exchanges:
    print(f"\n❌ НЕ РАБОТАЮТ: {', '.join(failed_exchanges)}")
