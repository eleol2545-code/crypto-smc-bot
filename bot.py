import ccxt
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

print("=" * 70)
print("🚀 БЭКТЕСТ SMC/ICT СТРАТЕГИИ НА АГРЕГИРОВАННЫХ ДАННЫХ")
print("=" * 70)

# ==================== КОНФИГУРАЦИЯ ====================
INITIAL_BALANCE = 100
TIMEFRAME = '1h'
DAYS = 180
COMMISSION = 0.0004

# ==================== РАБОТАЮЩИЕ БИРЖИ ====================
EXCHANGES = [
    {'name': 'KuCoin', 'class': ccxt.kucoin, 'symbol': 'BTC/USDT', 'params': {}},
    {'name': 'Gate.io', 'class': ccxt.gateio, 'symbol': 'BTC/USDT', 'params': {}},
    {'name': 'OKX', 'class': ccxt.okx, 'symbol': 'BTC/USDT', 'params': {}},
    {'name': 'Huobi', 'class': ccxt.huobi, 'symbol': 'BTC/USDT', 'params': {}},
    {'name': 'Bitget', 'class': ccxt.bitget, 'symbol': 'BTC/USDT', 'params': {}},
]

print("\n📡 ПОДКЛЮЧЕНИЕ К БИРЖАМ...")
active_exchanges = []

for ex in EXCHANGES:
    try:
        e = ex['class'](ex['params'])
        e.enableRateLimit = True
        active_exchanges.append({
            'name': ex['name'],
            'exchange': e,
            'symbol': ex['symbol']
        })
        print(f"   ✅ {ex['name']} подключена")
    except Exception as e:
        print(f"   ❌ {ex['name']} ошибка: {e}")

if not active_exchanges:
    print("\n❌ Нет доступных бирж!")
    exit(1)

# ==================== ЗАГРУЗКА ДАННЫХ ====================
print(f"\n📥 ЗАГРУЗКА ДАННЫХ ЗА {DAYS} ДНЕЙ...")

all_dfs = []
limit = int(DAYS * 24) + 200

for ex in active_exchanges:
    try:
        print(f"   Загружаем {ex['name']}...")
        ohlcv = ex['exchange'].fetch_ohlcv(ex['symbol'], TIMEFRAME, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df.set_index('timestamp')
        all_dfs.append(df)
        print(f"      ✅ {len(df)} свечей")
    except Exception as e:
        print(f"   ⚠️ {ex['name']} ошибка: {e}")

if not all_dfs:
    print("\n❌ Не удалось загрузить данные!")
    exit(1)

# ==================== АГРЕГАЦИЯ ДАННЫХ ====================
print("\n📊 АГРЕГАЦИЯ ДАННЫХ...")

# Находим общий временной диапазон
all_indexes = [df.index for df in all_dfs]
common_start = max(idx.min() for idx in all_indexes)
common_end = min(idx.max() for idx in all_indexes)

print(f"   Общий диапазон: {common_start.date()} - {common_end.date()}")

# Выравниваем все датафреймы
aligned_dfs = []
for df in all_dfs:
    aligned = df.loc[common_start:common_end].copy()
    aligned_dfs.append(aligned)

# Создаем агрегированный датафрейм
agg_df = pd.DataFrame(index=aligned_dfs[0].index)
agg_df['close'] = np.mean([df['close'].values for df in aligned_dfs], axis=0)
agg_df['volume'] = np.sum([df['volume'].values for df in aligned_dfs], axis=0)
agg_df['high'] = np.mean([df['high'].values for df in aligned_dfs], axis=0)
agg_df['low'] = np.mean([df['low'].values for df in aligned_dfs], axis=0)
agg_df['open'] = np.mean([df['open'].values for df in aligned_dfs], axis=0)

print(f"✅ Агрегировано {len(agg_df)} свечей")

# ==================== SMC/ICT ИНДИКАТОРЫ ====================
print("\n📊 РАСЧЕТ ИНДИКАТОРОВ...")

prices = agg_df['close'].values
volumes = agg_df['volume'].values
highs = agg_df['high'].values
lows = agg_df['low'].values

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

# Рассчитываем
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

print("✅ Индикаторы рассчитаны")

# ==================== СИМУЛЯЦИЯ ТОРГОВЛИ ====================
print("\n🎯 ЗАПУСК СИМУЛЯЦИИ...")

STYLES = {
    'scalp': {'sl_pct': 0.008, 'tp_pct': 0.015, 'min_conf': 65},
    'day': {'sl_pct': 0.015, 'tp_pct': 0.03, 'min_conf': 70},
    'swing': {'sl_pct': 0.025, 'tp_pct': 0.06, 'min_conf': 75}
}

results_by_style = {}

for style_name, style_params in STYLES.items():
    print(f"\n   Тестируем стиль: {style_name.upper()}...")
    
    balance = INITIAL_BALANCE
    position = None
    trades = []
    
    for i in range(100, len(prices) - 1):
        price = prices[i]
        
        # Закрытие позиции
        if position:
            if position['side'] == 'LONG':
                if price <= position['sl']:
                    pnl_pct = (position['sl'] - position['entry']) / position['entry'] * 100 * position['leverage']
                    pnl_usdt = position['size'] * (position['sl'] - position['entry']) / position['entry'] * position['leverage']
                    pnl_usdt -= position['size'] * COMMISSION * 2
                    balance += pnl_usdt
                    trades.append({'side': 'LONG', 'entry': position['entry'], 'exit': position['sl'],
                                   'pnl_pct': pnl_pct, 'pnl_usdt': pnl_usdt, 'reason': 'SL'})
                    position = None
                elif price >= position['tp']:
                    pnl_pct = (position['tp'] - position['entry']) / position['entry'] * 100 * position['leverage']
                    pnl_usdt = position['size'] * (position['tp'] - position['entry']) / position['entry'] * position['leverage']
                    pnl_usdt -= position['size'] * COMMISSION * 2
                    balance += pnl_usdt
                    trades.append({'side': 'LONG', 'entry': position['entry'], 'exit': position['tp'],
                                   'pnl_pct': pnl_pct, 'pnl_usdt': pnl_usdt, 'reason': 'TP'})
                    position = None
            else:
                if price >= position['sl']:
                    pnl_pct = (position['entry'] - position['sl']) / position['entry'] * 100 * position['leverage']
                    pnl_usdt = position['size'] * (position['entry'] - position['sl']) / position['entry'] * position['leverage']
                    pnl_usdt -= position['size'] * COMMISSION * 2
                    balance += pnl_usdt
                    trades.append({'side': 'SHORT', 'entry': position['entry'], 'exit': position['sl'],
                                   'pnl_pct': pnl_pct, 'pnl_usdt': pnl_usdt, 'reason': 'SL'})
                    position = None
                elif price <= position['tp']:
                    pnl_pct = (position['entry'] - position['tp']) / position['entry'] * 100 * position['leverage']
                    pnl_usdt = position['size'] * (position['entry'] - position['tp']) / position['entry'] * position['leverage']
                    pnl_usdt -= position['size'] * COMMISSION * 2
                    balance += pnl_usdt
                    trades.append({'side': 'SHORT', 'entry': position['entry'], 'exit': position['tp'],
                                   'pnl_pct': pnl_pct, 'pnl_usdt': pnl_usdt, 'reason': 'TP'})
                    position = None
        
        # Генерация нового сигнала
        if not position:
            score = 0
            signal_type = None
            
            if bullish_ob[i] == 1:
                score += 20
                signal_type = 'LONG'
            if bearish_ob[i] == 1:
                score += 20
                signal_type = 'SHORT'
            
            if rsi[i] < 30:
                score += 15
                if not signal_type: signal_type = 'LONG'
            elif rsi[i] > 70:
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
            
            if signal_type and confidence >= style_params['min_conf']:
                entry = price
                size = balance * 0.01
                
                if signal_type == 'LONG':
                    sl = entry * (1 - style_params['sl_pct'])
                    tp = entry * (1 + style_params['tp_pct'])
                else:
                    sl = entry * (1 + style_params['sl_pct'])
                    tp = entry * (1 - style_params['tp_pct'])
                
                position = {
                    'side': signal_type,
                    'entry': entry,
                    'sl': sl,
                    'tp': tp,
                    'size': size,
                    'leverage': 1
                }
                balance -= size * COMMISSION
    
    # Статистика
    if trades:
        trades_df = pd.DataFrame(trades)
        wins = trades_df[trades_df['pnl_pct'] > 0]
        losses = trades_df[trades_df['pnl_pct'] <= 0]
        
        results_by_style[style_name] = {
            'total_trades': len(trades),
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': round(len(wins) / len(trades) * 100, 2) if trades else 0,
            'total_pnl_pct': round((balance - INITIAL_BALANCE) / INITIAL_BALANCE * 100, 2),
            'total_pnl_usdt': round(balance - INITIAL_BALANCE, 2),
            'final_balance': round(balance, 2),
            'profit_factor': round(abs(wins['pnl_usdt'].sum() / (losses['pnl_usdt'].sum() + 0.0001)), 2) if len(losses) > 0 else 0,
            'trades_list': trades[-10:]
        }
    else:
        results_by_style[style_name] = {
            'total_trades': 0, 'wins': 0, 'losses': 0, 'win_rate': 0,
            'total_pnl_pct': 0, 'total_pnl_usdt': 0, 'final_balance': INITIAL_BALANCE,
            'profit_factor': 0, 'trades_list': []
        }

# ==================== ВЫВОД РЕЗУЛЬТАТОВ ====================
print("\n" + "=" * 70)
print("📊 РЕЗУЛЬТАТЫ БЭКТЕСТА")
print("=" * 70)

print("\n┌────────────────────────────────────────────────────────────────────┐")
print("│                      ОБЩАЯ СТАТИСТИКА                              │")
print("├────────────────────────────────────────────────────────────────────┤")
for style, res in results_by_style.items():
    print(f"│ {style.upper():<10} │ Сделок: {res['total_trades']:<4} │ Win: {res['win_rate']}% │ P&L: +{res['total_pnl_pct']}% │")
print("└────────────────────────────────────────────────────────────────────┘")

# Находим лучший стиль
best_style = max(results_by_style.items(), key=lambda x: x[1]['total_pnl_pct'])
print(f"\n🏆 ЛУЧШИЙ СТИЛЬ: {best_style[0].upper()} (прибыль {best_style[1]['total_pnl_pct']}%, Win Rate {best_style[1]['win_rate']}%)")

# Последние сделки
if best_style[1]['trades_list']:
    print(f"\n📜 ПОСЛЕДНИЕ 10 СДЕЛОК (стиль {best_style[0].upper()}):")
    print("-" * 65)
    print(f"{'№':<4} {'Тип':<6} {'Вход':<12} {'Выход':<12} {'P&L':<10} {'Причина':<10}")
    print("-" * 65)
    for i, trade in enumerate(best_style[1]['trades_list'][-10:], 1):
        pnl = f"{trade['pnl_pct']:+.2f}%"
        print(f"{i:<4} {trade['side']:<6} ${trade['entry']:<11.2f} ${trade['exit']:<11.2f} {pnl:<10} {trade['reason']:<10}")

print("\n" + "=" * 70)
print("🎯 ИТОГОВАЯ ОЦЕНКА")
print("=" * 70)

best = best_style[1]
if best['total_trades'] > 20 and best['win_rate'] > 55 and best['profit_factor'] > 1.5:
    print("\n✅ СТРАТЕГИЯ ПОКАЗЫВАЕТ СТАБИЛЬНУЮ ПРИБЫЛЬ!")
    print(f"   • Win Rate {best['win_rate']}% > 55%")
    print(f"   • Profit Factor {best['profit_factor']} > 1.5")
    print(f"   • Прибыль {best['total_pnl_pct']}% за 6 месяцев")
elif best['win_rate'] > 45 and best['profit_factor'] > 1:
    print("\n⚠️ СТРАТЕГИЯ ТРЕБУЕТ ДОРАБОТКИ")
else:
    print("\n❌ СТРАТЕГИЯ НЕ ПРИБЫЛЬНА")

print("\n" + "=" * 70)
print("✅ БЭКТЕСТ ЗАВЕРШЕН")
print("=" * 70)
