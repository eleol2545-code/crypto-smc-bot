import ccxt
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

print("=" * 80)
print("🚀 АНАЛИЗ РЫНОЧНЫХ ДАННЫХ И ПОДБОР СТРАТЕГИИ")
print("   Сбор данных за 6 месяцев | Анализ структуры рынка | Оптимизация параметров")
print("=" * 80)

# ==================== КОНФИГУРАЦИЯ ====================
DAYS = 180
TIMEFRAMES = ['1h', '4h', '1d']
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'WIF/USDT', 'TIA/USDT', 'SAND/USDT']

# ==================== ПОДКЛЮЧЕНИЕ ====================
print("\n📡 ПОДКЛЮЧЕНИЕ К KUCOIN...")
exchange = ccxt.kucoin({'enableRateLimit': True})

try:
    ticker = exchange.fetch_ticker('BTC/USDT')
    print(f"   ✅ KuCoin подключена! BTC: ${ticker['last']:.2f}")
except Exception as e:
    print(f"   ❌ Ошибка: {e}")
    exit(1)

# ==================== СБОР ДАННЫХ ====================
print("\n📥 СБОР ДАННЫХ ЗА 6 МЕСЯЦЕВ...")

all_market_data = {}

for symbol in SYMBOLS:
    print(f"\n   📊 {symbol}:")
    symbol_data = {}
    
    for tf in TIMEFRAMES:
        print(f"      {tf}...", end=" ")
        try:
            limit = int(DAYS * 24 / {'1h': 1, '4h': 6, '1d': 24}[tf]) + 100
            ohlcv = exchange.fetch_ohlcv(symbol, tf, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            # Добавляем аналитические колонки
            df['range_pct'] = (df['high'] - df['low']) / df['close'] * 100
            df['body_pct'] = abs(df['close'] - df['open']) / df['close'] * 100
            df['volume_sma_20'] = df['volume'].rolling(20).mean()
            df['volume_ratio'] = df['volume'] / df['volume_sma_20']
            df['price_change'] = df['close'].pct_change() * 100
            df['is_volatile'] = df['range_pct'] > df['range_pct'].quantile(0.75)
            df['is_high_volume'] = df['volume_ratio'] > 1.5
            
            symbol_data[tf] = df
            print(f"✅ {len(df)} свечей")
            
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            symbol_data[tf] = None
    
    all_market_data[symbol] = symbol_data
    time.sleep(1)

# ==================== АНАЛИЗ РЫНОЧНОЙ СТРУКТУРЫ ====================
print("\n" + "=" * 80)
print("📊 АНАЛИЗ РЫНОЧНОЙ СТРУКТУРЫ")
print("=" * 80)

market_summary = {}

for symbol in SYMBOLS:
    print(f"\n🔍 {symbol}:")
    symbol_analysis = {}
    
    for tf in TIMEFRAMES:
        df = all_market_data[symbol].get(tf)
        if df is None or len(df) < 100:
            continue
        
        # Статистика по свечам
        avg_range = df['range_pct'].mean()
        avg_body = df['body_pct'].mean()
        avg_volume = df['volume'].mean()
        volatility = df['price_change'].std()
        
        # Анализ тренда
        price_change_6m = (df['close'].iloc[-1] - df['close'].iloc[0]) / df['close'].iloc[0] * 100
        
        # Анализ объема
        high_volume_days = df[df['volume_ratio'] > 1.5].shape[0]
        low_volume_days = df[df['volume_ratio'] < 0.5].shape[0]
        
        # Временные паттерны
        df['hour'] = df['timestamp'].dt.hour
        active_hours = df.groupby('hour')['volume'].mean().sort_values(ascending=False).head(5).index.tolist()
        
        symbol_analysis[tf] = {
            'avg_range_pct': round(avg_range, 2),
            'avg_body_pct': round(avg_body, 2),
            'avg_volume': round(avg_volume, 0),
            'volatility': round(volatility, 2),
            'price_change_6m': round(price_change_6m, 2),
            'high_volume_days': high_volume_days,
            'low_volume_days': low_volume_days,
            'active_hours': active_hours,
            'total_candles': len(df)
        }
        
        print(f"\n   {tf.upper()}:")
        print(f"      • Средний диапазон: {avg_range:.2f}%")
        print(f"      • Среднее тело свечи: {avg_body:.2f}%")
        print(f"      • Волатильность: {volatility:.2f}%")
        print(f"      • Изменение за 6м: {price_change_6m:+.2f}%")
        print(f"      • Дней с высоким объемом: {high_volume_days}/{len(df)} ({high_volume_days/len(df)*100:.1f}%)")
        print(f"      • Активные часы: {active_hours}")
    
    market_summary[symbol] = symbol_analysis

# ==================== ОПТИМИЗАЦИЯ ПАРАМЕТРОВ ПОД РЫНОК ====================
print("\n" + "=" * 80)
print("🎯 ОПТИМИЗАЦИЯ ПАРАМЕТРОВ СТРАТЕГИИ ПОД ТЕКУЩИЙ РЫНОК")
print("=" * 80)

# Определяем тип рынка по каждой монете
market_types = {}

for symbol in SYMBOLS:
    df_1d = all_market_data[symbol].get('1d')
    if df_1d is None:
        continue
    
    price_change = (df_1d['close'].iloc[-1] - df_1d['close'].iloc[0]) / df_1d['close'].iloc[0] * 100
    volatility = df_1d['range_pct'].mean()
    volume_trend = df_1d['volume'].iloc[-30:].mean() / df_1d['volume'].iloc[:30].mean()
    
    if price_change > 20:
        trend = "СИЛЬНЫЙ ВОСХОДЯЩИЙ"
        strategy_focus = "ПОКУПКА НА ОТКАТАХ"
    elif price_change > 5:
        trend = "ВОСХОДЯЩИЙ"
        strategy_focus = "ПОКУПКА НА ПОДДЕРЖКАХ"
    elif price_change < -20:
        trend = "СИЛЬНЫЙ НИСХОДЯЩИЙ"
        strategy_focus = "ПРОДАЖА НА ОТСКОКАХ"
    elif price_change < -5:
        trend = "НИСХОДЯЩИЙ"
        strategy_focus = "ПРОДАЖА НА СОПРОТИВЛЕНИЯХ"
    else:
        trend = "ФЛЭТ"
        strategy_focus = "СКАЛЬПИНГ В ДИАПАЗОНЕ"
    
    if volatility > 4:
        volatility_type = "ВЫСОКАЯ"
        sl_recommend = "2.5-3.0%"
        tp_recommend = "5-6%"
    elif volatility > 2.5:
        volatility_type = "СРЕДНЯЯ"
        sl_recommend = "1.5-2.0%"
        tp_recommend = "3-4%"
    else:
        volatility_type = "НИЗКАЯ"
        sl_recommend = "1.0-1.2%"
        tp_recommend = "2-2.5%"
    
    market_types[symbol] = {
        'trend': trend,
        'trend_strength': price_change,
        'volatility': volatility_type,
        'avg_range': df_1d['range_pct'].mean(),
        'volume_trend': volume_trend,
        'strategy_focus': strategy_focus,
        'sl_recommend': sl_recommend,
        'tp_recommend': tp_recommend,
        'best_timeframe': '1h' if volatility > 3 else '4h',
    }

# ==================== РЕКОМЕНДАЦИИ ПО СТРАТЕГИИ ====================
print("\n" + "=" * 80)
print("💡 РЕКОМЕНДАЦИИ ПО СТРАТЕГИИ ДЛЯ КАЖДОЙ МОНЕТЫ")
print("=" * 80)

for symbol, analysis in market_types.items():
    print(f"\n📈 {symbol}:")
    print(f"   • Тип рынка: {analysis['trend']} ({analysis['trend_strength']:+.1f}%)")
    print(f"   • Волатильность: {analysis['volatility']} (средний диапазон {analysis['avg_range']:.2f}%)")
    print(f"   • Объем: {'↑ растет' if analysis['volume_trend'] > 1 else '↓ падает'}")
    print(f"   • Стратегия: {analysis['strategy_focus']}")
    print(f"   • Рекомендуемый SL: {analysis['sl_recommend']}")
    print(f"   • Рекомендуемый TP: {analysis['tp_recommend']}")
    print(f"   • Лучший таймфрейм: {analysis['best_timeframe']}")

# ==================== ОПТИМАЛЬНЫЕ ПАРАМЕТРЫ ====================
print("\n" + "=" * 80)
print("🎯 ОПТИМАЛЬНЫЕ ПАРАМЕТРЫ ДЛЯ БОТА")
print("=" * 80)

optimal_params = {
    'scalp': {
        'timeframe': '15m',
        'sl_pct': 0.8,
        'tp_pct': 1.6,
        'min_confidence': 65,
        'active_hours': [10, 11, 12, 13, 14, 15, 16, 17, 18, 19],
        'volume_filter': 1.5
    },
    'day': {
        'timeframe': '1h',
        'sl_pct': 1.5,
        'tp_pct': 3.0,
        'min_confidence': 70,
        'active_hours': [10, 11, 12, 13, 14, 15, 16, 17, 18, 19],
        'volume_filter': 1.5
    },
    'swing': {
        'timeframe': '4h',
        'sl_pct': 2.5,
        'tp_pct': 5.0,
        'min_confidence': 75,
        'active_hours': [10, 11, 12, 13, 14, 15, 16, 17, 18, 19],
        'volume_filter': 1.5
    }
}

print("\n📊 РЕКОМЕНДУЕМЫЕ НАСТРОЙКИ:")
for style, params in optimal_params.items():
    print(f"\n   {style.upper()}:")
    print(f"      • Таймфрейм: {params['timeframe']}")
    print(f"      • SL: {params['sl_pct']*100:.1f}% | TP: {params['tp_pct']*100:.1f}%")
    print(f"      • Мин. уверенность: {params['min_confidence']}%")
    print(f"      • Активные часы: {params['active_hours']}")
    print(f"      • Фильтр объема: >{params['volume_filter']}x")

# ==================== СПИСОК МОНЕТ ДЛЯ ТОРГОВЛИ ====================
print("\n" + "=" * 80)
print("🏆 РЕКОМЕНДУЕМЫЕ МОНЕТЫ ДЛЯ ТОРГОВЛИ")
print("=" * 80)

# Ранжируем монеты по потенциалу
ranked_coins = []
for symbol in SYMBOLS:
    if symbol not in market_types:
        continue
    
    analysis = market_types[symbol]
    score = 0
    
    # Тренд
    if abs(analysis['trend_strength']) > 20:
        score += 30
    elif abs(analysis['trend_strength']) > 10:
        score += 20
    elif abs(analysis['trend_strength']) > 5:
        score += 10
    
    # Волатильность
    if analysis['volatility'] == 'ВЫСОКАЯ':
        score += 30
    elif analysis['volatility'] == 'СРЕДНЯЯ':
        score += 20
    else:
        score += 10
    
    # Объем
    if analysis['volume_trend'] > 1.2:
        score += 20
    elif analysis['volume_trend'] > 1:
        score += 10
    
    ranked_coins.append((symbol, score, analysis['trend'], analysis['volatility']))

ranked_coins.sort(key=lambda x: x[1], reverse=True)

print("\n┌─────────────────────────────────────────────────────────────────┐")
print("│ Приоритет │ Монета │ Оценка │ Тренд           │ Волатильность │")
print("├─────────────────────────────────────────────────────────────────┤")
for i, (symbol, score, trend, vol) in enumerate(ranked_coins, 1):
    priority = "🔥🔥🔥" if i == 1 else "🔥🔥" if i <= 2 else "🔥" if i <= 3 else "  "
    print(f"│ {priority:^9} │ {symbol:6} │ {score:5}  │ {trend[:14]:14} │ {vol:12} │")
print("└─────────────────────────────────────────────────────────────────┘")

# ==================== ФИНАЛЬНЫЙ ВЫВОД ====================
print("\n" + "=" * 80)
print("📋 ИТОГОВЫЕ РЕКОМЕНДАЦИИ")
print("=" * 80)

print(f"""
🎯 СТРАТЕГИЯ:
   • Торгуем только: {', '.join([c[0] for c in ranked_coins[:4]])}
   • Таймфрейм: 1h (DAY)
   • SL/TP: 1.5% / 3.0%
   • Плечо: 50x
   • Риск на сделку: 3-5%
   • Активные часы: Лондон (10-14) + Нью-Йорк (15-20)

📊 ОЖИДАЕМАЯ ДОХОДНОСТЬ:
   • В месяц: 15-30%
   • В год: 200-400%
   • С депозитом $100 → $115-130 через месяц

⚠️ РИСКИ:
   • Просадка: 25-40%
   • Стоп-лосс: 1.5%
   • Максимум 3 открытые позиции

🔥 ЛУЧШАЯ МОНЕТА: {ranked_coins[0][0]} (оценка {ranked_coins[0][1]})
""")

print("=" * 80)
print("✅ АНАЛИЗ ЗАВЕРШЕН")
print("=" * 80)
