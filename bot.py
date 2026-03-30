import ccxt
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

print("=" * 70)
print("🚀 БЭКТЕСТ SMC/ICT СТРАТЕГИИ НА 6 МОНЕТАХ")
print("=" * 70)

# ==================== КОНФИГУРАЦИЯ ====================
INITIAL_BALANCE = 100
COMMISSION = 0.0004
TIMEFRAME = '1h'
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

# ==================== ОПТИМИЗИРУЕМЫЕ ПАРАМЕТРЫ ====================
OPTIMIZATIONS = [
    {'name': 'OPT1_стандарт', 'rsi_low': 30, 'rsi_high': 70, 'sl_pct': 0.015, 'tp_pct': 0.03, 'volume_mult': 1.5},
    {'name': 'OPT2_агрессивный', 'rsi_low': 25, 'rsi_high': 75, 'sl_pct': 0.01, 'tp_pct': 0.02, 'volume_mult': 1.3},
    {'name': 'OPT3_консервативный', 'rsi_low': 35, 'rsi_high': 65, 'sl_pct': 0.02, 'tp_pct': 0.04, 'volume_mult': 1.8},
    {'name': 'OPT4_широкий_стоп', 'rsi_low': 28, 'rsi_high': 72, 'sl_pct': 0.025, 'tp_pct': 0.05, 'volume_mult': 1.5},
    {'name': 'OPT5_узкий_стоп', 'rsi_low': 32, 'rsi_high': 68, 'sl_pct': 0.012, 'tp_pct': 0.025, 'volume_mult': 1.4},
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
print("\n📥 ЗАГРУЗКА ДАННЫХ ДЛЯ 6 МОНЕТ...")

symbols_data = {}

for sym in SYMBOLS:
    print(f"\n   Загружаем {sym['name']}...")
    try:
        limit = int(DAYS * 24) + 200
        ohlcv = exchange.fetch_ohlcv(sym['symbol'], TIMEFRAME, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        symbols_data[sym['name']] = {
            'df': df,
            'prices': df['close'].values,
            'volumes': df['volume'].values,
            'highs': df['high'].values,
            'lows': df['low'].values
        }
        print(f"      ✅ Загружено {len(df)} свечей")
    except Exception as e:
        print(f"      ❌ Ошибка: {e}")

# ==================== ТЕСТИРОВАНИЕ ====================
print("\n🎯 ЗАПУСК БЭКТЕСТА С ОПТИМИЗАЦИЕЙ ПАРАМЕТРОВ...")

all_results = {}

for opt in OPTIMIZATIONS:
    print(f"\n{'='*70}")
    print(f"📊 ТЕСТИРУЕМ: {opt['name']}")
    print(f"   RSI: {opt['rsi_low']}/{opt['rsi_high']} | SL: {opt['sl_pct']*100:.1f}% | TP: {opt['tp_pct']*100:.1f}% | Объем: {opt['volume_mult']}x")
    print(f"{'='*70}")
    
    results_by_symbol = {}
    total_trades_all = 0
    total_pnl_all = 0
    
    for sym_name, data in symbols_data.items():
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
        
        # Симуляция
        balance = INITIAL_BALANCE
        position = None
        trades = []
        
        for i in range(100, len(prices) - 1):
            price = prices[i]
            
            # Закрытие позиции
            if position:
                if position['side'] == 'LONG':
                    if price <= position['sl']:
                        pnl_pct = (position['sl'] - position['entry']) / position['entry'] * 100
                        pnl_usdt = position['size'] * (position['sl'] - position['entry']) / position['entry']
                        pnl_usdt -= position['size'] * COMMISSION * 2
                        balance += pnl_usdt
                        trades.append({'side': 'LONG', 'entry': position['entry'], 'exit': position['sl'],
                                       'pnl_pct': pnl_pct, 'pnl_usdt': pnl_usdt, 'reason': 'SL'})
                        position = None
                    elif price >= position['tp']:
                        pnl_pct = (position['tp'] - position['entry']) / position['entry'] * 100
                        pnl_usdt = position['size'] * (position['tp'] - position['entry']) / position['entry']
                        pnl_usdt -= position['size'] * COMMISSION * 2
                        balance += pnl_usdt
                        trades.append({'side': 'LONG', 'entry': position['entry'], 'exit': position['tp'],
                                       'pnl_pct': pnl_pct, 'pnl_usdt': pnl_usdt, 'reason': 'TP'})
                        position = None
                else:
                    if price >= position['sl']:
                        pnl_pct = (position['entry'] - position['sl']) / position['entry'] * 100
                        pnl_usdt = position['size'] * (position['entry'] - position['sl']) / position['entry']
                        pnl_usdt -= position['size'] * COMMISSION * 2
                        balance += pnl_usdt
                        trades.append({'side': 'SHORT', 'entry': position['entry'], 'exit': position['sl'],
                                       'pnl_pct': pnl_pct, 'pnl_usdt': pnl_usdt, 'reason': 'SL'})
                        position = None
                    elif price <= position['tp']:
                        pnl_pct = (position['entry'] - position['tp']) / position['entry'] * 100
                        pnl_usdt = position['size'] * (position['entry'] - position['tp']) / position['entry']
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
                
                if rsi[i] < opt['rsi_low']:
                    score += 15
                    if not signal_type: signal_type = 'LONG'
                elif rsi[i] > opt['rsi_high']:
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
                
                if volume_ratio[i] > opt['volume_mult']:
                    score += 10
                
                if price < vwap[i] and signal_type == 'LONG':
                    score += 10
                elif price > vwap[i] and signal_type == 'SHORT':
                    score += 10
                
                confidence = min(100, score)
                
                if signal_type and confidence >= 65:
                    entry = price
                    size = balance * 0.01
                    
                    if signal_type == 'LONG':
                        sl = entry * (1 - opt['sl_pct'])
                        tp = entry * (1 + opt['tp_pct'])
                    else:
                        sl = entry * (1 + opt['sl_pct'])
                        tp = entry * (1 - opt['tp_pct'])
                    
                    position = {
                        'side': signal_type,
                        'entry': entry,
                        'sl': sl,
                        'tp': tp,
                        'size': size
                    }
                    balance -= size * COMMISSION
        
        # Статистика по монете
        if trades:
            trades_df = pd.DataFrame(trades)
            wins = trades_df[trades_df['pnl_pct'] > 0]
            losses = trades_df[trades_df['pnl_pct'] <= 0]
            
            total_pnl = (balance - INITIAL_BALANCE) / INITIAL_BALANCE * 100
            results_by_symbol[sym_name] = {
                'total_trades': len(trades),
                'wins': len(wins),
                'win_rate': round(len(wins) / len(trades) * 100, 2),
                'pnl_pct': round(total_pnl, 2),
                'profit_factor': round(abs(wins['pnl_usdt'].sum() / (losses['pnl_usdt'].sum() + 0.0001)), 2)
            }
            total_trades_all += len(trades)
            total_pnl_all += total_pnl
        else:
            results_by_symbol[sym_name] = {
                'total_trades': 0, 'wins': 0, 'win_rate': 0,
                'pnl_pct': 0, 'profit_factor': 0
            }
    
    all_results[opt['name']] = {
        'by_symbol': results_by_symbol,
        'total_trades': total_trades_all,
        'total_pnl': round(total_pnl_all / len(symbols_data), 2)
    }

# ==================== ВЫВОД РЕЗУЛЬТАТОВ ====================
print("\n" + "=" * 80)
print("📊 РЕЗУЛЬТАТЫ БЭКТЕСТА ПО 6 МОНЕТАМ")
print("=" * 80)

print("\n┌─────────────────────────────────────────────────────────────────────────────────────────────────────┐")
print("│ Оптимизация     │ BTC    │ ETH    │ SOL    │ SAND   │ TIA    │ WIF    │ Всего  │ Средняя P&L │")
print("├─────────────────────────────────────────────────────────────────────────────────────────────────────┤")

for opt_name, data in all_results.items():
    by_sym = data['by_symbol']
    row = f"│ {opt_name:<15} │ "
    for sym in ['BTC', 'ETH', 'SOL', 'SAND', 'TIA', 'WIF']:
        pnl = by_sym.get(sym, {}).get('pnl_pct', 0)
        color = '+' if pnl > 0 else ''
        row += f"{color}{pnl:>6.2f}% │ "
    row += f"{data['total_trades']:>6} │ {data['total_pnl']:>10.2f}% │"
    print(row)

print("└─────────────────────────────────────────────────────────────────────────────────────────────────────┘")

# Находим лучшую оптимизацию
best_opt = max(all_results.items(), key=lambda x: x[1]['total_pnl'])
print(f"\n🏆 ЛУЧШАЯ ОПТИМИЗАЦИЯ: {best_opt[0]}")
print(f"   • Средняя прибыль по 6 монетам: {best_opt[1]['total_pnl']:.2f}%")
print(f"   • Всего сделок: {best_opt[1]['total_trades']}")

# Детализация по монетам для лучшей оптимизации
print(f"\n📈 ДЕТАЛИЗАЦИЯ ПО МОНЕТАМ ({best_opt[0]}):")
print("-" * 70)
print(f"{'Монета':<8} {'Сделок':<8} {'Win Rate':<10} {'P&L':<12} {'Profit Factor':<15}")
print("-" * 70)

best_data = best_opt[1]['by_symbol']
for sym in ['BTC', 'ETH', 'SOL', 'SAND', 'TIA', 'WIF']:
    data = best_data.get(sym, {})
    pnl = data.get('pnl_pct', 0)
    pnl_str = f"+{pnl}%" if pnl > 0 else f"{pnl}%"
    print(f"{sym:<8} {data.get('total_trades', 0):<8} {data.get('win_rate', 0):<9}% {pnl_str:<12} {data.get('profit_factor', 0):<15}")

print("\n" + "=" * 80)
print("✅ БЭКТЕСТ ЗАВЕРШЕН")
print("=" * 80)
