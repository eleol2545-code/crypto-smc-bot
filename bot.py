import ccxt
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

print("=" * 80)
print("🚀 РАСШИРЕННЫЙ БЭКТЕСТ SMC/ICT СТРАТЕГИИ")
print("   RSI оптимизация | SL/TP 1:2 | Плечо 50x | Все таймфреймы")
print("=" * 80)

# ==================== КОНФИГУРАЦИЯ ====================
INITIAL_BALANCE = 100
COMMISSION = 0.0004
LEVERAGE = 50  # Плечо 50x
DAYS = 180

# 6 монет для тестирования
SYMBOLS = [
    {'symbol': 'BTC/USDT', 'name': 'BTC'},
    {'symbol': 'ETH/USDT', 'name': 'ETH'},
    {'symbol': 'SOL/USDT', 'name': 'SOL'},
    {'symbol': 'SAND/USDT', 'name': 'SAND'},
    {'symbol': 'TIA/USDT', 'name': 'TIA'},
    {'symbol': 'WIF/USDT', 'name': 'WIF'},
]

# Таймфреймы и стили
TIMEFRAMES = [
    {'name': 'SCALP_5m', 'timeframe': '5m', 'limit': 2000, 'risk_pct': 0.008, 'reward_pct': 0.016, 'min_conf': 65},
    {'name': 'SCALP_15m', 'timeframe': '15m', 'limit': 2000, 'risk_pct': 0.008, 'reward_pct': 0.016, 'min_conf': 65},
    {'name': 'DAY_1h', 'timeframe': '1h', 'limit': 1500, 'risk_pct': 0.015, 'reward_pct': 0.03, 'min_conf': 70},
    {'name': 'DAY_4h', 'timeframe': '4h', 'limit': 1000, 'risk_pct': 0.015, 'reward_pct': 0.03, 'min_conf': 70},
    {'name': 'SWING_1d', 'timeframe': '1d', 'limit': 500, 'risk_pct': 0.025, 'reward_pct': 0.05, 'min_conf': 75},
]

# RSI пороги для тестирования
RSI_OPTIONS = [
    {'name': 'RSI_28_72', 'low': 28, 'high': 72},
    {'name': 'RSI_30_70', 'low': 30, 'high': 70},
    {'name': 'RSI_32_68', 'low': 32, 'high': 68},
]

# ==================== ПОДКЛЮЧЕНИЕ К БИРЖЕ ====================
print("\n📡 ПОДКЛЮЧЕНИЕ К KUCOIN...")
exchange = ccxt.kucoin({'enableRateLimit': True})

try:
    ticker = exchange.fetch_ticker('BTC/USDT')
    print(f"   ✅ KuCoin подключена! BTC: ${ticker['last']:.2f}")
except Exception as e:
    print(f"   ❌ Ошибка: {e}")
    exit(1)

# ==================== SMC/ICT ИНДИКАТОРЫ ====================
def calculate_rsi(prices, period=14):
    delta = np.diff(prices)
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_gain = np.zeros(len(prices))
    avg_loss = np.zeros(len(prices))
    avg_gain[period] = np.mean(gain[:period])
    avg_loss[period] = np.mean(loss[:period])
    for i in range(period + 1, len(prices)):
        avg_gain[i] = (avg_gain[i-1] * (period - 1) + gain[i-1]) / period
        avg_loss[i] = (avg_loss[i-1] * (period - 1) + loss[i-1]) / period
    rs = avg_gain / (avg_loss + 0.0001)
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_macd(prices):
    ema_fast = pd.Series(prices).ewm(span=12, adjust=False).mean().values
    ema_slow = pd.Series(prices).ewm(span=26, adjust=False).mean().values
    macd_line = ema_fast - ema_slow
    signal_line = pd.Series(macd_line).ewm(span=9, adjust=False).mean().values
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def calculate_bollinger(prices, period=20, std=2):
    sma = pd.Series(prices).rolling(window=period).mean().values
    std_dev = pd.Series(prices).rolling(window=period).std().values
    upper = sma + (std_dev * std)
    lower = sma - (std_dev * std)
    return upper, sma, lower

def calculate_stochastic(prices, highs, lows, k_period=14, d_period=3):
    low_min = pd.Series(lows).rolling(window=k_period).min().values
    high_max = pd.Series(highs).rolling(window=k_period).max().values
    stoch_k = 100 * (prices - low_min) / (high_max - low_min + 0.0001)
    stoch_d = pd.Series(stoch_k).rolling(window=d_period).mean().values
    return stoch_k, stoch_d

def calculate_ema(prices, period):
    return pd.Series(prices).ewm(span=period, adjust=False).mean().values

def calculate_vwap(prices, volumes):
    typical_price = prices
    cumulative_tp_vol = np.cumsum(typical_price * volumes)
    cumulative_vol = np.cumsum(volumes)
    vwap = cumulative_tp_vol / (cumulative_vol + 0.0001)
    return vwap

def find_order_blocks(prices, volumes, window=5):
    bullish_ob = np.zeros(len(prices))
    bearish_ob = np.zeros(len(prices))
    for i in range(window, len(prices) - 1):
        avg_volume = np.mean(volumes[max(0, i-window):i])
        if prices[i] > prices[i-1] * 1.01 and volumes[i] > avg_volume * 1.5:
            for j in range(i, min(i + 20, len(prices))):
                if j < len(bullish_ob):
                    bullish_ob[j] = 1
        elif prices[i] < prices[i-1] * 0.99 and volumes[i] > avg_volume * 1.5:
            for j in range(i, min(i + 20, len(prices))):
                if j < len(bearish_ob):
                    bearish_ob[j] = 1
    return bullish_ob, bearish_ob

# ==================== ЗАГРУЗКА ДАННЫХ ====================
print("\n📥 ЗАГРУЗКА ДАННЫХ...")

all_data = {}

for sym in SYMBOLS:
    print(f"\n   Загружаем {sym['name']}...")
    sym_data = {}
    
    for tf in TIMEFRAMES:
        try:
            ohlcv = exchange.fetch_ohlcv(sym['symbol'], tf['timeframe'], limit=tf['limit'])
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            sym_data[tf['name']] = {
                'df': df,
                'prices': df['close'].values,
                'volumes': df['volume'].values,
                'highs': df['high'].values,
                'lows': df['low'].values,
                'tf_config': tf
            }
            print(f"      ✅ {tf['name']}: {len(df)} свечей")
        except Exception as e:
            print(f"      ❌ {tf['name']} ошибка: {e}")
    
    all_data[sym['name']] = sym_data

# ==================== СИМУЛЯЦИЯ ====================
print("\n🎯 ЗАПУСК БЭКТЕСТА...")

all_results = []

for rsi_opt in RSI_OPTIONS:
    print(f"\n{'='*80}")
    print(f"📊 ТЕСТИРУЕМ RSI: {rsi_opt['name']} ({rsi_opt['low']}/{rsi_opt['high']})")
    print(f"{'='*80}")
    
    for tf in TIMEFRAMES:
        print(f"\n   📈 {tf['name']} | SL: {tf['risk_pct']*100:.1f}% | TP: {tf['reward_pct']*100:.1f}% | RR 1:{tf['reward_pct']/tf['risk_pct']:.1f}")
        print(f"   {'-'*60}")
        
        for sym_name in ['BTC', 'ETH', 'SOL', 'SAND', 'TIA', 'WIF']:
            if sym_name not in all_data or tf['name'] not in all_data[sym_name]:
                continue
                
            data = all_data[sym_name][tf['name']]
            df = data['df']
            prices = data['prices']
            volumes = data['volumes']
            highs = data['highs']
            lows = data['lows']
            
            # Рассчитываем индикаторы
            rsi = calculate_rsi(prices)
            macd_line, macd_signal, macd_hist = calculate_macd(prices)
            bb_upper, bb_middle, bb_lower = calculate_bollinger(prices)
            stoch_k, stoch_d = calculate_stochastic(prices, highs, lows)
            ema_9 = calculate_ema(prices, 9)
            ema_21 = calculate_ema(prices, 21)
            ema_50 = calculate_ema(prices, 50)
            vwap = calculate_vwap(prices, volumes)
            volume_ratio = volumes / (np.mean(volumes[max(0, len(volumes)-20):]) + 0.0001)
            bullish_ob, bearish_ob = find_order_blocks(prices, volumes)
            
            # Симуляция с плечом 50x
            balance = INITIAL_BALANCE
            position = None
            trades = []
            
            for i in range(100, len(prices) - 1):
                price = prices[i]
                
                # Закрытие позиции
                if position:
                    if position['side'] == 'LONG':
                        if price <= position['sl']:
                            pnl_pct = (position['sl'] - position['entry']) / position['entry'] * 100 * LEVERAGE
                            pnl_usdt = position['size'] * (position['sl'] - position['entry']) / position['entry'] * LEVERAGE
                            pnl_usdt -= position['size'] * COMMISSION * 2
                            balance += pnl_usdt
                            trades.append({'side': 'LONG', 'entry': position['entry'], 'exit': position['sl'],
                                           'pnl_pct': pnl_pct, 'pnl_usdt': pnl_usdt, 'reason': 'SL'})
                            position = None
                        elif price >= position['tp']:
                            pnl_pct = (position['tp'] - position['entry']) / position['entry'] * 100 * LEVERAGE
                            pnl_usdt = position['size'] * (position['tp'] - position['entry']) / position['entry'] * LEVERAGE
                            pnl_usdt -= position['size'] * COMMISSION * 2
                            balance += pnl_usdt
                            trades.append({'side': 'LONG', 'entry': position['entry'], 'exit': position['tp'],
                                           'pnl_pct': pnl_pct, 'pnl_usdt': pnl_usdt, 'reason': 'TP'})
                            position = None
                    else:  # SHORT
                        if price >= position['sl']:
                            pnl_pct = (position['entry'] - position['sl']) / position['entry'] * 100 * LEVERAGE
                            pnl_usdt = position['size'] * (position['entry'] - position['sl']) / position['entry'] * LEVERAGE
                            pnl_usdt -= position['size'] * COMMISSION * 2
                            balance += pnl_usdt
                            trades.append({'side': 'SHORT', 'entry': position['entry'], 'exit': position['sl'],
                                           'pnl_pct': pnl_pct, 'pnl_usdt': pnl_usdt, 'reason': 'SL'})
                            position = None
                        elif price <= position['tp']:
                            pnl_pct = (position['entry'] - position['tp']) / position['entry'] * 100 * LEVERAGE
                            pnl_usdt = position['size'] * (position['entry'] - position['tp']) / position['entry'] * LEVERAGE
                            pnl_usdt -= position['size'] * COMMISSION * 2
                            balance += pnl_usdt
                            trades.append({'side': 'SHORT', 'entry': position['entry'], 'exit': position['tp'],
                                           'pnl_pct': pnl_pct, 'pnl_usdt': pnl_usdt, 'reason': 'TP'})
                            position = None
                
                # Генерация сигнала
                if not position:
                    score = 0
                    signal_type = None
                    
                    if bullish_ob[i] == 1:
                        score += 20
                        signal_type = 'LONG'
                    if bearish_ob[i] == 1:
                        score += 20
                        signal_type = 'SHORT'
                    
                    if rsi[i] < rsi_opt['low']:
                        score += 15
                        if not signal_type: signal_type = 'LONG'
                    elif rsi[i] > rsi_opt['high']:
                        score += 15
                        if not signal_type: signal_type = 'SHORT'
                    
                    if macd_hist[i] > 0 and signal_type == 'LONG':
                        score += 15
                    elif macd_hist[i] < 0 and signal_type == 'SHORT':
                        score += 15
                    
                    if price <= bb_lower[i] * 1.005:
                        score += 15
                        if not signal_type: signal_type = 'LONG'
                    elif price >= bb_upper[i] * 0.995:
                        score += 15
                        if not signal_type: signal_type = 'SHORT'
                    
                    if stoch_k[i] < 20:
                        score += 15
                        if not signal_type: signal_type = 'LONG'
                    elif stoch_k[i] > 80:
                        score += 15
                        if not signal_type: signal_type = 'SHORT'
                    
                    if ema_9[i] > ema_21[i] and ema_21[i] > ema_50[i]:
                        score += 10
                        if signal_type == 'LONG': score += 5
                    elif ema_9[i] < ema_21[i] and ema_21[i] < ema_50[i]:
                        score += 10
                        if signal_type == 'SHORT': score += 5
                    
                    if volume_ratio[i] > 1.5:
                        score += 10
                    
                    if price < vwap[i] and signal_type == 'LONG':
                        score += 10
                    elif price > vwap[i] and signal_type == 'SHORT':
                        score += 10
                    
                    confidence = min(100, score)
                    
                    if signal_type and confidence >= tf['min_conf']:
                        entry = price
                        size = balance * 0.01  # 1% риск
                        
                        if signal_type == 'LONG':
                            sl = entry * (1 - tf['risk_pct'])
                            tp = entry * (1 + tf['reward_pct'])
                        else:
                            sl = entry * (1 + tf['risk_pct'])
                            tp = entry * (1 - tf['reward_pct'])
                        
                        position = {
                            'side': signal_type,
                            'entry': entry,
                            'sl': sl,
                            'tp': tp,
                            'size': size
                        }
                        balance -= size * COMMISSION
            
            # Статистика
            if trades:
                trades_df = pd.DataFrame(trades)
                wins = trades_df[trades_df['pnl_pct'] > 0]
                losses = trades_df[trades_df['pnl_pct'] <= 0]
                
                total_pnl = (balance - INITIAL_BALANCE) / INITIAL_BALANCE * 100
                all_results.append({
                    'rsi': rsi_opt['name'],
                    'timeframe': tf['name'],
                    'symbol': sym_name,
                    'total_trades': len(trades),
                    'wins': len(wins),
                    'losses': len(losses),
                    'win_rate': round(len(wins) / len(trades) * 100, 2),
                    'pnl_pct': round(total_pnl, 2),
                    'pnl_usdt': round(balance - INITIAL_BALANCE, 2),
                    'final_balance': round(balance, 2),
                    'profit_factor': round(abs(wins['pnl_usdt'].sum() / (losses['pnl_usdt'].sum() + 0.0001)), 2),
                    'avg_win': round(wins['pnl_pct'].mean(), 2) if len(wins) > 0 else 0,
                    'avg_loss': round(abs(losses['pnl_pct'].mean()), 2) if len(losses) > 0 else 0
                })
                
                # Вывод по монете
                print(f"      {sym_name:4} | Сделок:{len(trades):3} | Win:{len(wins)/len(trades)*100:5.1f}% | P&L:{total_pnl:+7.2f}% | PF:{abs(wins['pnl_usdt'].sum() / (losses['pnl_usdt'].sum() + 0.0001)):.2f}")
            else:
                all_results.append({
                    'rsi': rsi_opt['name'],
                    'timeframe': tf['name'],
                    'symbol': sym_name,
                    'total_trades': 0, 'wins': 0, 'losses': 0, 'win_rate': 0,
                    'pnl_pct': 0, 'pnl_usdt': 0, 'final_balance': INITIAL_BALANCE,
                    'profit_factor': 0, 'avg_win': 0, 'avg_loss': 0
                })
                print(f"      {sym_name:4} | Сделок:0 | Нет сигналов")

# ==================== ВЫВОД РЕЗУЛЬТАТОВ ====================
print("\n" + "=" * 100)
print("📊 ИТОГОВЫЕ РЕЗУЛЬТАТЫ БЭКТЕСТА (Плечо 50x)")
print("=" * 100)

# Сводная таблица по RSI и таймфреймам
print("\n┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────┐")
print("│ RSI вариант   │ Таймфрейм  │ Сделок │ Win Rate │ Сред. P&L │ Средний PF │ Лучшая монета │ Худшая монета │")
print("├─────────────────────────────────────────────────────────────────────────────────────────────────────────────┤")

for rsi_opt in RSI_OPTIONS:
    for tf in TIMEFRAMES:
        tf_results = [r for r in all_results if r['rsi'] == rsi_opt['name'] and r['timeframe'] == tf['name'] and r['total_trades'] > 0]
        if tf_results:
            avg_pnl = sum(r['pnl_pct'] for r in tf_results) / len(tf_results)
            avg_pf = sum(r['profit_factor'] for r in tf_results) / len(tf_results)
            total_trades = sum(r['total_trades'] for r in tf_results)
            avg_win_rate = sum(r['win_rate'] for r in tf_results) / len(tf_results)
            
            best_symbol = max(tf_results, key=lambda x: x['pnl_pct'])['symbol']
            worst_symbol = min(tf_results, key=lambda x: x['pnl_pct'])['symbol']
            
            print(f"│ {rsi_opt['name']:<12} │ {tf['name']:<10} │ {total_trades:6} │ {avg_win_rate:7.1f}% │ {avg_pnl:+8.2f}% │ {avg_pf:9.2f} │ {best_symbol:11} │ {worst_symbol:12} │")

print("└─────────────────────────────────────────────────────────────────────────────────────────────────────────────┘")

# Лучшие результаты по монетам
print("\n🏆 ТОП-10 ЛУЧШИХ РЕЗУЛЬТАТОВ ПО МОНЕТАМ:")
print("-" * 100)
top_results = sorted([r for r in all_results if r['total_trades'] > 0], key=lambda x: x['pnl_pct'], reverse=True)[:10]
print(f"{'№':<3} {'RSI':<12} {'Таймфрейм':<10} {'Монета':<6} {'Сделок':<7} {'Win Rate':<9} {'P&L':<10} {'Profit Factor':<14}")
print("-" * 100)
for i, r in enumerate(top_results, 1):
    print(f"{i:<3} {r['rsi']:<12} {r['timeframe']:<10} {r['symbol']:<6} {r['total_trades']:<7} {r['win_rate']:<8.1f}% {r['pnl_pct']:+8.2f}% {r['profit_factor']:<14.2f}")

# Худшие результаты
print("\n💀 ТОП-10 ХУДШИХ РЕЗУЛЬТАТОВ:")
print("-" * 100)
worst_results = sorted([r for r in all_results if r['total_trades'] > 0], key=lambda x: x['pnl_pct'])[:10]
print(f"{'№':<3} {'RSI':<12} {'Таймфрейм':<10} {'Монета':<6} {'Сделок':<7} {'Win Rate':<9} {'P&L':<10} {'Profit Factor':<14}")
print("-" * 100)
for i, r in enumerate(worst_results, 1):
    print(f"{i:<3} {r['rsi']:<12} {r['timeframe']:<10} {r['symbol']:<6} {r['total_trades']:<7} {r['win_rate']:<8.1f}% {r['pnl_pct']:+8.2f}% {r['profit_factor']:<14.2f}")

# Статистика по таймфреймам
print("\n📊 СТАТИСТИКА ПО ТАЙМФРЕЙМАМ (средняя по всем RSI и монетам):")
print("-" * 80)
for tf in TIMEFRAMES:
    tf_results = [r for r in all_results if r['timeframe'] == tf['name'] and r['total_trades'] > 0]
    if tf_results:
        avg_pnl = sum(r['pnl_pct'] for r in tf_results) / len(tf_results)
        total_trades = sum(r['total_trades'] for r in tf_results)
        positive_count = len([r for r in tf_results if r['pnl_pct'] > 0])
        print(f"   {tf['name']:<10} | Сделок: {total_trades:5} | Прибыльных монет: {positive_count}/{len(tf_results)} | Средняя P&L: {avg_pnl:+7.2f}%")

# Лучшая комбинация
best = max(all_results, key=lambda x: x['pnl_pct'])
print(f"\n🎯 ЛУЧШАЯ КОМБИНАЦИЯ:")
print(f"   • RSI: {best['rsi']} ({[opt for opt in RSI_OPTIONS if opt['name'] == best['rsi']][0]['low']}/{best['rsi'].split('_')[1]})")
print(f"   • Таймфрейм: {best['timeframe']}")
print(f"   • Монета: {best['symbol']}")
print(f"   • Сделок: {best['total_trades']}")
print(f"   • Win Rate: {best['win_rate']}%")
print(f"   • Прибыль: {best['pnl_pct']:.2f}% (${best['pnl_usdt']:.2f})")
print(f"   • Profit Factor: {best['profit_factor']}")
print(f"   • Средняя прибыль: {best['avg_win']:.2f}%")
print(f"   • Средний убыток: {best['avg_loss']:.2f}%")

print("\n" + "=" * 100)
print("✅ БЭКТЕСТ ЗАВЕРШЕН")
print("=" * 100)
