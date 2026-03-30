import ccxt
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

print("=" * 80)
print("🚀 УЛУЧШЕННЫЙ БЭКТЕСТ SMC/ICT СТРАТЕГИИ")
print("   ATR динамический SL/TP | ADX фильтр | Временные фильтры | Объемный анализ")
print("   6 монет: BTC, ETH, SOL, SAND, TIA, WIF")
print("=" * 80)

# ==================== КОНФИГУРАЦИЯ ====================
INITIAL_BALANCE = 100
COMMISSION = 0.0004
LEVERAGE = 50
DAYS = 180

# 6 монет
SYMBOLS = [
    {'symbol': 'BTC/USDT', 'name': 'BTC'},
    {'symbol': 'ETH/USDT', 'name': 'ETH'},
    {'symbol': 'SOL/USDT', 'name': 'SOL'},
    {'symbol': 'SAND/USDT', 'name': 'SAND'},
    {'symbol': 'TIA/USDT', 'name': 'TIA'},
    {'symbol': 'WIF/USDT', 'name': 'WIF'},
]

# Таймфреймы (DAY_1h показал лучшие результаты)
TIMEFRAMES = [
    {'name': 'DAY_1h', 'timeframe': '1h', 'limit': 1500, 'min_conf': 70},
]

# RSI пороги (лучший из прошлого теста)
RSI_OPTIONS = [
    {'name': 'RSI_28_72', 'low': 28, 'high': 72},
]

# ==================== НОВЫЕ ИНДИКАТОРЫ ====================

def calculate_atr(highs, lows, closes, period=14):
    """Average True Range - волатильность"""
    tr = np.zeros(len(closes))
    for i in range(1, len(closes)):
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
    
    atr = np.zeros(len(closes))
    atr[period] = np.mean(tr[1:period+1])
    for i in range(period+1, len(closes)):
        atr[i] = (atr[i-1] * (period - 1) + tr[i]) / period
    return atr

def calculate_adx(highs, lows, closes, period=14):
    """Average Directional Index - сила тренда"""
    tr = np.zeros(len(closes))
    for i in range(1, len(closes)):
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
    
    up_move = np.zeros(len(closes))
    down_move = np.zeros(len(closes))
    for i in range(1, len(closes)):
        up_move[i] = highs[i] - highs[i-1]
        down_move[i] = lows[i-1] - lows[i]
    
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
    
    atr = calculate_atr(highs, lows, closes, period)
    
    plus_di = 100 * np.where(atr > 0, np.convolve(plus_dm, np.ones(period)/period, mode='same'), 0)
    minus_di = 100 * np.where(atr > 0, np.convolve(minus_dm, np.ones(period)/period, mode='same'), 0)
    
    dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di + 0.0001)
    adx = np.convolve(dx, np.ones(period)/period, mode='same')
    return adx

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

def is_active_session(timestamp):
    """Проверка, активная ли торговая сессия (Лондон + Нью-Йорк)"""
    hour = timestamp.hour
    # Лондон: 10:00-14:00, Нью-Йорк: 15:00-20:00 (МСК)
    return (10 <= hour <= 14) or (15 <= hour <= 20)

# ==================== ПОДКЛЮЧЕНИЕ К БИРЖЕ ====================
print("\n📡 ПОДКЛЮЧЕНИЕ К KUCOIN...")
exchange = ccxt.kucoin({'enableRateLimit': True})

try:
    ticker = exchange.fetch_ticker('BTC/USDT')
    print(f"   ✅ KuCoin подключена! BTC: ${ticker['last']:.2f}")
except Exception as e:
    print(f"   ❌ Ошибка: {e}")
    exit(1)

# ==================== ЗАГРУЗКА ДАННЫХ ====================
print("\n📥 ЗАГРУЗКА ДАННЫХ ДЛЯ 6 МОНЕТ...")

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
                'timestamps': df['timestamp'].values,
                'tf_config': tf
            }
            print(f"      ✅ {tf['name']}: {len(df)} свечей")
        except Exception as e:
            print(f"      ❌ {tf['name']} ошибка: {e}")
    
    all_data[sym['name']] = sym_data

# ==================== СИМУЛЯЦИЯ ====================
print("\n🎯 ЗАПУСК БЭКТЕСТА С УЛУЧШЕННЫМИ ФИЛЬТРАМИ...")

all_results = []

for rsi_opt in RSI_OPTIONS:
    print(f"\n{'='*80}")
    print(f"📊 ТЕСТИРУЕМ RSI: {rsi_opt['name']} ({rsi_opt['low']}/{rsi_opt['high']})")
    print(f"{'='*80}")
    
    for tf in TIMEFRAMES:
        print(f"\n   📈 {tf['name']} | ATR динамический SL/TP | ADX фильтр | Временной фильтр")
        print(f"   {'-'*70}")
        
        for sym_name in SYMBOLS:
            sym = sym_name['name'] if isinstance(sym_name, dict) else sym_name
            if sym not in all_data or tf['name'] not in all_data[sym]:
                continue
                
            data = all_data[sym][tf['name']]
            df = data['df']
            prices = data['prices']
            volumes = data['volumes']
            highs = data['highs']
            lows = data['lows']
            timestamps = data['timestamps']
            
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
            
            # НОВЫЕ ИНДИКАТОРЫ
            atr = calculate_atr(highs, lows, prices, 14)
            adx = calculate_adx(highs, lows, prices, 14)
            
            # Симуляция
            balance = INITIAL_BALANCE
            position = None
            trades = []
            
            for i in range(100, len(prices) - 1):
                price = prices[i]
                timestamp = timestamps[i]
                
                # ========== ВРЕМЕННОЙ ФИЛЬТР ==========
                if not is_active_session(timestamp):
                    continue
                
                # ========== ADX ФИЛЬТР (сильный тренд) ==========
                if adx[i] < 25:  # слабый тренд или флэт
                    continue
                
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
                    
                    # SMC Order Blocks
                    if bullish_ob[i] == 1:
                        score += 20
                        signal_type = 'LONG'
                    if bearish_ob[i] == 1:
                        score += 20
                        signal_type = 'SHORT'
                    
                    # RSI
                    if rsi[i] < rsi_opt['low']:
                        score += 15
                        if not signal_type: signal_type = 'LONG'
                    elif rsi[i] > rsi_opt['high']:
                        score += 15
                        if not signal_type: signal_type = 'SHORT'
                    
                    # MACD
                    if macd_hist[i] > 0 and signal_type == 'LONG':
                        score += 15
                    elif macd_hist[i] < 0 and signal_type == 'SHORT':
                        score += 15
                    
                    # Bollinger
                    if price <= bb_lower[i] * 1.005:
                        score += 15
                        if not signal_type: signal_type = 'LONG'
                    elif price >= bb_upper[i] * 0.995:
                        score += 15
                        if not signal_type: signal_type = 'SHORT'
                    
                    # Stochastic
                    if stoch_k[i] < 20:
                        score += 15
                        if not signal_type: signal_type = 'LONG'
                    elif stoch_k[i] > 80:
                        score += 15
                        if not signal_type: signal_type = 'SHORT'
                    
                    # EMA тренд
                    if ema_9[i] > ema_21[i] and ema_21[i] > ema_50[i]:
                        score += 10
                        if signal_type == 'LONG': score += 5
                    elif ema_9[i] < ema_21[i] and ema_21[i] < ema_50[i]:
                        score += 10
                        if signal_type == 'SHORT': score += 5
                    
                    # Объем
                    if volume_ratio[i] > 1.5:
                        score += 10
                    
                    # VWAP
                    if price < vwap[i] and signal_type == 'LONG':
                        score += 10
                    elif price > vwap[i] and signal_type == 'SHORT':
                        score += 10
                    
                    confidence = min(100, score)
                    
                    if signal_type and confidence >= tf['min_conf']:
                        entry = price
                        size = balance * 0.03  # риск 3%
                        
                        # ========== ДИНАМИЧЕСКИЙ SL/TP через ATR ==========
                        current_atr = atr[i]
                        if current_atr > 0:
                            if signal_type == 'LONG':
                                sl = entry - current_atr * 1.5
                                tp = entry + current_atr * 3.0
                            else:
                                sl = entry + current_atr * 1.5
                                tp = entry - current_atr * 3.0
                        else:
                            # fallback на фиксированные
                            if signal_type == 'LONG':
                                sl = entry * 0.985
                                tp = entry * 1.03
                            else:
                                sl = entry * 1.015
                                tp = entry * 0.97
                        
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
                    'symbol': sym,
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
                
                print(f"      {sym:4} | Сделок:{len(trades):3} | Win:{len(wins)/len(trades)*100:5.1f}% | P&L:{total_pnl:+7.2f}% | PF:{abs(wins['pnl_usdt'].sum() / (losses['pnl_usdt'].sum() + 0.0001)):.2f} | ADX:{adx[-1]:.1f}")
            else:
                all_results.append({
                    'rsi': rsi_opt['name'],
                    'timeframe': tf['name'],
                    'symbol': sym,
                    'total_trades': 0, 'wins': 0, 'losses': 0, 'win_rate': 0,
                    'pnl_pct': 0, 'pnl_usdt': 0, 'final_balance': INITIAL_BALANCE,
                    'profit_factor': 0, 'avg_win': 0, 'avg_loss': 0
                })
                print(f"      {sym:4} | Сделок:0 | Нет сигналов")

# ==================== ВЫВОД РЕЗУЛЬТАТОВ ====================
print("\n" + "=" * 100)
print("📊 ИТОГОВЫЕ РЕЗУЛЬТАТЫ УЛУЧШЕННОГО БЭКТЕСТА")
print("=" * 100)

print("\n┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────┐")
print("│ Монета    │ Сделок │ Win Rate │ P&L 6 мес │ P&L год │ Profit Factor │ ATR SL/TP │ ADX фильтр │ Время     │")
print("├─────────────────────────────────────────────────────────────────────────────────────────────────────────────┤")

for sym in ['BTC', 'ETH', 'SOL', 'SAND', 'TIA', 'WIF']:
    sym_results = [r for r in all_results if r['symbol'] == sym and r['total_trades'] > 0]
    if sym_results:
        r = sym_results[0]
        yearly = r['pnl_pct'] * 2  # простая экстраполяция
        print(f"│ {sym:6} │ {r['total_trades']:6} │ {r['win_rate']:7.1f}% │ {r['pnl_pct']:+8.2f}% │ {yearly:+8.2f}% │ {r['profit_factor']:13.2f} │ {'✅' if r['total_trades'] > 0 else '❌':8} │ {'✅' if r['total_trades'] > 0 else '❌':8} │ {'✅' if r['total_trades'] > 0 else '❌':8} │")
    else:
        print(f"│ {sym:6} │ {'0':6} │ {'0.0':7}% │ {'0.00':+8}% │ {'0.00':+8}% │ {'0.00':13} │ {'❌':8} │ {'❌':8} │ {'❌':8} │")

print("└─────────────────────────────────────────────────────────────────────────────────────────────────────────────┘")

# Сравнение с прошлым тестом
print("\n📈 СРАВНЕНИЕ С ПРЕДЫДУЩИМ ТЕСТОМ (DAY_1h, RSI 28/72):")
print("-" * 80)
print(f"{'Монета':<8} {'Было (без фильтров)':<25} {'Стало (с фильтрами)':<25} {'Изменение':<15}")
print("-" * 80)

# Данные из прошлого теста
previous_results = {
    'BTC': 14.82, 'ETH': 14.61, 'SOL': 29.14, 'SAND': 17.06, 'TIA': 23.33, 'WIF': 39.77
}

for sym in ['BTC', 'ETH', 'SOL', 'SAND', 'TIA', 'WIF']:
    current = [r for r in all_results if r['symbol'] == sym and r['total_trades'] > 0]
    current_pnl = current[0]['pnl_pct'] if current else 0
    previous = previous_results.get(sym, 0)
    change = current_pnl - previous
    arrow = '▲' if change > 0 else '▼' if change < 0 else '●'
    print(f"{sym:<8} {previous:+.2f}%{'':<20} {current_pnl:+.2f}%{'':<20} {arrow} {change:+.2f}%")

# Лучшая монета
best = max(all_results, key=lambda x: x['pnl_pct'])
print(f"\n🏆 ЛУЧШАЯ МОНЕТА: {best['symbol']} | P&L: +{best['pnl_pct']:.2f}% | Win Rate: {best['win_rate']}% | PF: {best['profit_factor']}")

print("\n" + "=" * 100)
print("✅ УЛУЧШЕННЫЙ БЭКТЕСТ ЗАВЕРШЕН")
print("=" * 100)
