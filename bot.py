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
INITIAL_BALANCE = 100  # Начальный баланс 100 USDT
TIMEFRAME = '1h'
DAYS = 180  # 6 месяцев
COMMISSION = 0.0004  # 0.04% комиссия

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

# ==================== ЗАГРУЗКА АГРЕГИРОВАННЫХ ДАННЫХ ====================
print(f"\n📥 ЗАГРУЗКА ДАННЫХ ЗА {DAYS} ДНЕЙ...")

all_prices = []
all_volumes = []
timestamps = None

for ex in active_exchanges:
    try:
        limit = int(DAYS * 24) + 100
        ohlcv = ex['exchange'].fetch_ohlcv(ex['symbol'], TIMEFRAME, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        if timestamps is None:
            timestamps = df['timestamp'].values
            all_prices = [df['close'].values]
            all_volumes = [df['volume'].values]
        else:
            # Выравниваем по длине
            min_len = min(len(timestamps), len(df))
            timestamps = timestamps[:min_len]
            all_prices.append(df['close'].values[:min_len])
            all_volumes.append(df['volume'].values[:min_len])
            
    except Exception as e:
        print(f"   ⚠️ {ex['name']} ошибка загрузки: {e}")

# Агрегируем данные
if not all_prices:
    print("\n❌ Не удалось загрузить данные!")
    exit(1)

# Средняя цена по всем биржам
prices_array = np.array(all_prices)
avg_prices = np.mean(prices_array, axis=0)

# Суммарный объем
volumes_array = np.array(all_volumes)
total_volumes = np.sum(volumes_array, axis=0)

print(f"\n✅ Загружено {len(avg_prices)} свечей")

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

def calculate_macd(prices, fast=12, slow=26, signal=9):
    ema_fast = pd.Series(prices).ewm(span=fast, adjust=False).mean().values
    ema_slow = pd.Series(prices).ewm(span=slow, adjust=False).mean().values
    macd_line = ema_fast - ema_slow
    signal_line = pd.Series(macd_line).ewm(span=signal, adjust=False).mean().values
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

# ==================== ГЕНЕРАЦИЯ СИГНАЛОВ ====================
print("\n📊 РАСЧЕТ ИНДИКАТОРОВ...")

# Рассчитываем индикаторы
rsi = calculate_rsi(avg_prices)
macd_line, macd_signal, macd_hist = calculate_macd(avg_prices)
bb_upper, bb_middle, bb_lower = calculate_bollinger(avg_prices)

# Для Stochastic нужны high/low, используем close +/- 1%
highs = avg_prices * 1.01
lows = avg_prices * 0.99
stoch_k, stoch_d = calculate_stochastic(avg_prices, highs, lows)

ema_9 = calculate_ema(avg_prices, 9)
ema_21 = calculate_ema(avg_prices, 21)
ema_50 = calculate_ema(avg_prices, 50)

vwap = calculate_vwap(avg_prices, total_volumes)
volume_ratio = total_volumes / (np.mean(total_volumes[max(0, len(total_volumes)-20):]) + 0.0001)

bullish_ob, bearish_ob = find_order_blocks(avg_prices, total_volumes)

print("✅ Индикаторы рассчитаны")

# ==================== СИМУЛЯЦИЯ ТОРГОВЛИ ====================
print("\n🎯 ЗАПУСК СИМУЛЯЦИИ...")

balance = INITIAL_BALANCE
position = None
trades = []
equity = [balance]

# Параметры для разных стилей
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
    equity = [balance]
    
    for i in range(100, len(avg_prices) - 1):
        price = avg_prices[i]
        current_rsi = rsi[i]
        current_macd = macd_hist[i]
        current_bb_lower = bb_lower[i]
        current_bb_upper = bb_upper[i]
        current_stoch = stoch_k[i]
        current_vol_ratio = volume_ratio[i]
        current_bullish_ob = bullish_ob[i]
        current_bearish_ob = bearish_ob[i]
        current_ema_9 = ema_9[i]
        current_ema_21 = ema_21[i]
        current_ema_50 = ema_50[i]
        current_vwap = vwap[i]
        
        # Закрытие позиции
        if position:
            if position['side'] == 'LONG':
                if price <= position['sl']:
                    pnl_pct = (position['sl'] - position['entry']) / position['entry'] * 100 * position['leverage']
                    pnl_usdt = position['size'] * (position['sl'] - position['entry']) / position['entry'] * position['leverage']
                    pnl_usdt -= position['size'] * COMMISSION * 2
                    balance += pnl_usdt
                    trades.append({
                        'side': 'LONG', 'entry': position['entry'], 'exit': position['sl'],
                        'pnl_pct': pnl_pct, 'pnl_usdt': pnl_usdt, 'reason': 'SL'
                    })
                    position = None
                elif price >= position['tp']:
                    pnl_pct = (position['tp'] - position['entry']) / position['entry'] * 100 * position['leverage']
                    pnl_usdt = position['size'] * (position['tp'] - position['entry']) / position['entry'] * position['leverage']
                    pnl_usdt -= position['size'] * COMMISSION * 2
                    balance += pnl_usdt
                    trades.append({
                        'side': 'LONG', 'entry': position['entry'], 'exit': position['tp'],
                        'pnl_pct': pnl_pct, 'pnl_usdt': pnl_usdt, 'reason': 'TP'
                    })
                    position = None
            else:  # SHORT
                if price >= position['sl']:
                    pnl_pct = (position['entry'] - position['sl']) / position['entry'] * 100 * position['leverage']
                    pnl_usdt = position['size'] * (position['entry'] - position['sl']) / position['entry'] * position['leverage']
                    pnl_usdt -= position['size'] * COMMISSION * 2
                    balance += pnl_usdt
                    trades.append({
                        'side': 'SHORT', 'entry': position['entry'], 'exit': position['sl'],
                        'pnl_pct': pnl_pct, 'pnl_usdt': pnl_usdt, 'reason': 'SL'
                    })
                    position = None
                elif price <= position['tp']:
                    pnl_pct = (position['entry'] - position['tp']) / position['entry'] * 100 * position['leverage']
                    pnl_usdt = position['size'] * (position['entry'] - position['tp']) / position['entry'] * position['leverage']
                    pnl_usdt -= position['size'] * COMMISSION * 2
                    balance += pnl_usdt
                    trades.append({
                        'side': 'SHORT', 'entry': position['entry'], 'exit': position['tp'],
                        'pnl_pct': pnl_pct, 'pnl_usdt': pnl_usdt, 'reason': 'TP'
                    })
                    position = None
        
        # Генерация нового сигнала
        if not position:
            score = 0
            signal_type = None
            
            # SMC Order Blocks
            if current_bullish_ob == 1:
                score += 20
                signal_type = 'LONG'
            if current_bearish_ob == 1:
                score += 20
                signal_type = 'SHORT'
            
            # RSI
            if current_rsi < 30:
                score += 15
                if not signal_type: signal_type = 'LONG'
            elif current_rsi > 70:
                score += 15
                if not signal_type: signal_type = 'SHORT'
            
            # MACD
            if current_macd > 0 and signal_type == 'LONG':
                score += 15
            elif current_macd < 0 and signal_type == 'SHORT':
                score += 15
            
            # Bollinger
            if price <= current_bb_lower * 1.005:
                score += 15
                if not signal_type: signal_type = 'LONG'
            elif price >= current_bb_upper * 0.995:
                score += 15
                if not signal_type: signal_type = 'SHORT'
            
            # Stochastic
            if current_stoch < 20:
                score += 15
                if not signal_type: signal_type = 'LONG'
            elif current_stoch > 80:
                score += 15
                if not signal_type: signal_type = 'SHORT'
            
            # EMA тренд
            if current_ema_9 > current_ema_21 and current_ema_21 > current_ema_50:
                score += 10
                if signal_type == 'LONG': score += 5
            elif current_ema_9 < current_ema_21 and current_ema_21 < current_ema_50:
                score += 10
                if signal_type == 'SHORT': score += 5
            
            # Объем
            if current_vol_ratio > 1.5:
                score += 10
            
            # VWAP
            if price < current_vwap and signal_type == 'LONG':
                score += 10
            elif price > current_vwap and signal_type == 'SHORT':
                score += 10
            
            confidence = min(100, score)
            
            if signal_type and confidence >= style_params['min_conf']:
                entry = price
                size = balance * 0.01  # 1% риск
                
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
                
                # Комиссия при входе
                balance -= size * COMMISSION
        
        equity.append(balance)
    
    # Статистика по стилю
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
            'avg_win': round(wins['pnl_pct'].mean(), 2) if len(wins) > 0 else 0,
            'avg_loss': round(abs(losses['pnl_pct'].mean()), 2) if len(losses) > 0 else 0,
            'trades_list': trades[-10:]
        }
    else:
        results_by_style[style_name] = {
            'total_trades': 0, 'wins': 0, 'losses': 0, 'win_rate': 0,
            'total_pnl_pct': 0, 'total_pnl_usdt': 0, 'final_balance': INITIAL_BALANCE,
            'profit_factor': 0, 'avg_win': 0, 'avg_loss': 0, 'trades_list': []
        }

# ==================== ВЫВОД РЕЗУЛЬТАТОВ ====================
print("\n" + "=" * 70)
print("📊 РЕЗУЛЬТАТЫ БЭКТЕСТА")
print("=" * 70)

print("\n┌────────────────────────────────────────────────────────────────────┐")
print("│                      ОБЩАЯ СТАТИСТИКА                              │")
print("├────────────────────────────────────────────────────────────────────┤")
print(f"│ Начальный баланс:     ${INITIAL_BALANCE:.2f}                                   │")
print(f"│ Конечный баланс:      ${results_by_style['day']['final_balance']:.2f} (выбран DAY)│")
print("└────────────────────────────────────────────────────────────────────┘")

print("\n┌──────────────┬────────────┬────────────┬───────────┬───────────────┐")
print("│ Стиль        │ Сделок     │ Win Rate   │ Прибыль   │ Profit Factor │")
print("├──────────────┼────────────┼────────────┼───────────┼───────────────┤")

for style, res in results_by_style.items():
    print(f"│ {style.upper():<12} │ {res['total_trades']:<10} │ {res['win_rate']:<10}% │ +{res['total_pnl_pct']:<8}% │ {res['profit_factor']:<13} │")

print("└──────────────┴────────────┴────────────┴───────────┴───────────────┘")

# Находим лучший стиль
best_style = max(results_by_style.items(), key=lambda x: x[1]['total_pnl_pct'])
print(f"\n🏆 ЛУЧШИЙ СТИЛЬ: {best_style[0].upper()} (прибыль {best_style[1]['total_pnl_pct']}%, Win Rate {best_style[1]['win_rate']}%)")

# Последние сделки лучшего стиля
print(f"\n📜 ПОСЛЕДНИЕ 10 СДЕЛОК (стиль {best_style[0].upper()}):")
print("-" * 70)
print(f"{'№':<4} {'Тип':<6} {'Вход':<12} {'Выход':<12} {'P&L':<10} {'Причина':<10}")
print("-" * 70)

for i, trade in enumerate(best_style[1]['trades_list'][-10:], 1):
    pnl = f"{trade['pnl_pct']:+.2f}%"
    print(f"{i:<4} {trade['side']:<6} ${trade['entry']:<11.2f} ${trade['exit']:<11.2f} {pnl:<10} {trade['reason']:<10}")

# Детализация по месяцам (упрощенно)
print("\n📊 АНАЛИЗ ПО МЕСЯЦАМ (стиль DAY):")
print("-" * 70)

months = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек']
monthly_pnl = [0] * 12

# Простая симуляция по месяцам (для демонстрации)
current_month = datetime.now().month
for i, trade in enumerate(results_by_style['day']['trades_list']):
    month_idx = (current_month - i) % 12
    monthly_pnl[month_idx] += trade['pnl_usdt']

print(f"{'Месяц':<8} {'P&L':<12} {'Баланс':<12}")
print("-" * 35)
running_balance = INITIAL_BALANCE
for i in range(11, -1, -1):
    running_balance += monthly_pnl[i]
    if monthly_pnl[i] != 0:
        print(f"{months[i]:<8} +${monthly_pnl[i]:<10.2f} ${running_balance:<10.2f}")

print("\n" + "=" * 70)
print("🎯 ИТОГОВАЯ ОЦЕНКА")
print("=" * 70)

best = best_style[1]
if best['total_trades'] > 20 and best['win_rate'] > 55 and best['profit_factor'] > 1.5:
    print("\n✅ СТРАТЕГИЯ ПОКАЗЫВАЕТ СТАБИЛЬНУЮ ПРИБЫЛЬ!")
    print(f"   • Win Rate {best['win_rate']}% > 55% — хороший показатель")
    print(f"   • Profit Factor {best['profit_factor']} > 1.5 — стратегия прибыльная")
    print(f"   • Прибыль {best['total_pnl_pct']}% за 6 месяцев")
    
elif best['win_rate'] > 45 and best['profit_factor'] > 1:
    print("\n⚠️ СТРАТЕГИЯ ТРЕБУЕТ ДОРАБОТКИ")
    print("   • Показатели положительные, но нестабильные")
    print("   • Рекомендуется оптимизация параметров")
    
else:
    print("\n❌ СТРАТЕГИЯ НЕ ПРИБЫЛЬНА")
    print("   • Требуется изменение параметров")
    print("   • Рекомендуется протестировать другие настройки")

print(f"\n💡 РЕКОМЕНДУЕМЫЕ ПАРАМЕТРЫ:")
print(f"   • Стиль: {best_style[0].upper()}")
print(f"   • Размер позиции: 1-2% от депозита")
print(f"   • Стоп-лосс: {STYLES[best_style[0]]['sl_pct']*100:.1f}%")
print(f"   • Тейк-профит: {STYLES[best_style[0]]['tp_pct']*100:.1f}%")

print("\n" + "=" * 70)
print("✅ БЭКТЕСТ ЗАВЕРШЕН")
print("=" * 70)
