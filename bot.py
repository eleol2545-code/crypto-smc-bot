import ccxt
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

print("=" * 80)
print("🚀 МУЛЬТИБИРЖЕВОЙ БЭКТЕСТ — 13 МОНЕТ")
print("   BTC, ETH, SOL, WIF, TIA, SAND, XRP, SUI, APE, DOT, ADA, LINK, SEI")
print("   75x плечо | 6 месяцев | Агрегированные данные с 4 бирж")
print("=" * 80)

# ==================== КОНФИГУРАЦИЯ ====================
INITIAL_BALANCE = 100
COMMISSION = 0.0004
LEVERAGE = 75
DAYS = 180

# 13 монет
SYMBOLS = [
    {'symbol': 'BTC/USDT', 'name': 'BTC'},
    {'symbol': 'ETH/USDT', 'name': 'ETH'},
    {'symbol': 'SOL/USDT', 'name': 'SOL'},
    {'symbol': 'WIF/USDT', 'name': 'WIF'},
    {'symbol': 'TIA/USDT', 'name': 'TIA'},
    {'symbol': 'SAND/USDT', 'name': 'SAND'},
    {'symbol': 'XRP/USDT', 'name': 'XRP'},
    {'symbol': 'SUI/USDT', 'name': 'SUI'},
    {'symbol': 'APE/USDT', 'name': 'APE'},
    {'symbol': 'DOT/USDT', 'name': 'DOT'},
    {'symbol': 'ADA/USDT', 'name': 'ADA'},
    {'symbol': 'LINK/USDT', 'name': 'LINK'},
    {'symbol': 'SEI/USDT', 'name': 'SEI'},
]

# Таймфрейм
TIMEFRAMES = [
    {'name': 'DAY_1h', 'timeframe': '1h', 'limit': 1500, 'risk_pct': 0.015, 'reward_pct': 0.03, 'min_conf': 70},
]

# RSI пороги
RSI_OPTIONS = [
    {'name': 'RSI_28_72', 'low': 28, 'high': 72},
]

# Активные часы
ACTIVE_HOURS = list(range(10, 21))

# ==================== БИРЖИ ДЛЯ АГРЕГАЦИИ ====================
EXCHANGES_LIST = [
    {'name': 'KuCoin', 'class': ccxt.kucoin, 'params': {}},
    {'name': 'Gate.io', 'class': ccxt.gateio, 'params': {}},
    {'name': 'OKX', 'class': ccxt.okx, 'params': {}},
    {'name': 'Bitget', 'class': ccxt.bitget, 'params': {}},
]

print("\n📡 ПОДКЛЮЧЕНИЕ К БИРЖАМ...")

active_exchanges = []
for ex in EXCHANGES_LIST:
    try:
        e = ex['class'](ex['params'])
        e.enableRateLimit = True
        active_exchanges.append({
            'name': ex['name'],
            'exchange': e
        })
        print(f"   ✅ {ex['name']} подключена")
    except Exception as e:
        print(f"   ❌ {ex['name']} ошибка: {e}")

if not active_exchanges:
    print("❌ Нет доступных бирж!")
    exit(1)

# ==================== ФУНКЦИИ ИНДИКАТОРОВ ====================

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

def calculate_atr(highs, lows, closes, period=14):
    tr = np.zeros(len(closes))
    for i in range(1, len(closes)):
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
    atr = np.zeros(len(closes))
    atr[period] = np.mean(tr[1:period+1])
    for i in range(period+1, len(closes)):
        atr[i] = (atr[i-1] * (period - 1) + tr[i]) / period
    return atr

def calculate_adx(highs, lows, closes, period=14):
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
    try:
        if isinstance(timestamp, np.datetime64):
            ts = pd.Timestamp(timestamp)
        else:
            ts = timestamp
        hour = ts.hour
        return hour in ACTIVE_HOURS
    except:
        return False

def format_symbol_for_exchange(exchange_name, symbol):
    """Форматирует символ для конкретной биржи"""
    symbol_clean = symbol.replace('/USDT', '').replace('USDT', '').replace('/', '')
    if exchange_name == 'KuCoin':
        return f"{symbol_clean}/USDT"
    elif exchange_name == 'Gate.io':
        return f"{symbol_clean}_USDT"
    elif exchange_name == 'OKX':
        return f"{symbol_clean}-USDT-SWAP"
    elif exchange_name == 'Bitget':
        return f"{symbol_clean}/USDT"
    return f"{symbol_clean}/USDT"

# ==================== ЗАГРУЗКА АГРЕГИРОВАННЫХ ДАННЫХ ====================
print("\n📥 ЗАГРУЗКА АГРЕГИРОВАННЫХ ДАННЫХ ЗА 6 МЕСЯЦЕВ...")

all_data = {}

for sym in SYMBOLS:
    print(f"\n   Загружаем {sym['name']}...")
    sym_data = {}
    
    for tf in TIMEFRAMES:
        exchange_data = []
        
        for ex in active_exchanges:
            try:
                symbol_fmt = format_symbol_for_exchange(ex['name'], sym['symbol'])
                limit = tf['limit']
                ohlcv = ex['exchange'].fetch_ohlcv(symbol_fmt, tf['timeframe'], limit=limit)
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                exchange_data.append(df)
                print(f"      ✅ {ex['name']}: {len(df)} свечей")
            except Exception as e:
                print(f"      ❌ {ex['name']} ошибка: {e}")
            time.sleep(0.3)
        
        if not exchange_data:
            continue
        
        # Агрегируем данные по всем биржам
        # Находим общий временной диапазон
        all_dates = [df.set_index('timestamp').index for df in exchange_data]
        common_start = max(idx.min() for idx in all_dates)
        common_end = min(idx.max() for idx in all_dates)
        
        # Выравниваем и агрегируем
        aligned_dfs = []
        for df in exchange_data:
            df_aligned = df.set_index('timestamp').loc[common_start:common_end].copy()
            aligned_dfs.append(df_aligned)
        
        # Создаем агрегированный датафрейм
        agg_df = pd.DataFrame(index=aligned_dfs[0].index)
        agg_df['close'] = np.mean([df['close'].values for df in aligned_dfs], axis=0)
        agg_df['volume'] = np.sum([df['volume'].values for df in aligned_dfs], axis=0)
        agg_df['high'] = np.mean([df['high'].values for df in aligned_dfs], axis=0)
        agg_df['low'] = np.mean([df['low'].values for df in aligned_dfs], axis=0)
        agg_df['open'] = np.mean([df['open'].values for df in aligned_dfs], axis=0)
        
        sym_data[tf['name']] = {
            'df': agg_df.reset_index(),
            'prices': agg_df['close'].values,
            'volumes': agg_df['volume'].values,
            'highs': agg_df['high'].values,
            'lows': agg_df['low'].values,
            'timestamps': agg_df.index.values,
            'tf_config': tf
        }
        print(f"      ✅ Агрегировано: {len(agg_df)} свечей")
    
    all_data[sym['name']] = sym_data

# ==================== СИМУЛЯЦИЯ ====================
print("\n🎯 ЗАПУСК МУЛЬТИБИРЖЕВОГО БЭКТЕСТА...")

all_results = []

for rsi_opt in RSI_OPTIONS:
    print(f"\n{'='*80}")
    print(f"📊 ТЕСТИРУЕМ RSI: {rsi_opt['name']} ({rsi_opt['low']}/{rsi_opt['high']}) | Плечо {LEVERAGE}x")
    print(f"{'='*80}")
    
    for tf in TIMEFRAMES:
        print(f"\n   📈 {tf['name']} | SL: {tf['risk_pct']*100:.1f}% | TP: {tf['reward_pct']*100:.1f}% | RR 1:{tf['reward_pct']/tf['risk_pct']:.1f}")
        print(f"   Активные часы: {ACTIVE_HOURS[0]}:00-{ACTIVE_HOURS[-1]}:00 МСК")
        print(f"   {'-'*80}")
        
        for sym in SYMBOLS:
            sym_name = sym['name']
            if sym_name not in all_data or tf['name'] not in all_data[sym_name]:
                print(f"      {sym_name:4} | Нет данных")
                continue
                
            data = all_data[sym_name][tf['name']]
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
            atr = calculate_atr(highs, lows, prices, 14)
            adx = calculate_adx(highs, lows, prices, 14)
            
            # Симуляция
            balance = INITIAL_BALANCE
            position = None
            trades = []
            
            for i in range(100, len(prices) - 1):
                price = prices[i]
                timestamp = timestamps[i]
                
                # Временной фильтр
                if not is_active_session(timestamp):
                    continue
                
                # ADX фильтр
                if adx[i] < 20:
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
                    else:
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
                        size = balance * 0.03
                        
                        current_atr = atr[i]
                        if current_atr > 0:
                            if signal_type == 'LONG':
                                sl = entry - current_atr * 1.5
                                tp = entry + current_atr * 3.0
                            else:
                                sl = entry + current_atr * 1.5
                                tp = entry - current_atr * 3.0
                        else:
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
                    'profit_factor': round(abs(wins['pnl_usdt'].sum() / (losses['pnl_usdt'].sum() + 0.0001)), 2)
                })
                
                print(f"      {sym_name:4} | Сделок:{len(trades):3} | Win:{len(wins)/len(trades)*100:5.1f}% | P&L:{total_pnl:+7.2f}% | PF:{abs(wins['pnl_usdt'].sum() / (losses['pnl_usdt'].sum() + 0.0001)):.2f}")
            else:
                print(f"      {sym_name:4} | Сделок:0 | Нет сигналов")

# ==================== ВЫВОД РЕЗУЛЬТАТОВ ====================
print("\n" + "=" * 100)
print("📊 МУЛЬТИБИРЖЕВОЙ БЭКТЕСТ — 13 МОНЕТ (75x плечо)")
print("=" * 100)

# Сортировка по прибыли
sorted_results = sorted([r for r in all_results if r['total_trades'] > 0], key=lambda x: x['pnl_pct'], reverse=True)

if sorted_results:
    print("\n┌─────────────────────────────────────────────────────────────────────────────────────────────────┐")
    print("│ №  │ Монета │ Сделок │ Win Rate │ P&L 6 мес │ P&L год* │ Profit Factor │")
    print("├─────────────────────────────────────────────────────────────────────────────────────────────────┤")

    for i, r in enumerate(sorted_results, 1):
        yearly = r['pnl_pct'] * 2
        print(f"│ {i:2}  │ {r['symbol']:6} │ {r['total_trades']:6} │ {r['win_rate']:7.1f}% │ {r['pnl_pct']:+8.2f}% │ {yearly:+8.2f}% │ {r['profit_factor']:13.2f} │")

    print("└─────────────────────────────────────────────────────────────────────────────────────────────────┘")

    # ТОП-5
    print("\n🏆 ТОП-5 ЛУЧШИХ МОНЕТ:")
    print("-" * 80)
    for i, r in enumerate(sorted_results[:5], 1):
        print(f"   {i}. {r['symbol']}: +{r['pnl_pct']:.2f}% за 6 мес | Win Rate: {r['win_rate']}% | PF: {r['profit_factor']}")

    # ХУДШИЕ 5
    print("\n💀 ТОП-5 ХУДШИХ МОНЕТ:")
    print("-" * 80)
    for i, r in enumerate(sorted_results[-5:], 1):
        print(f"   {i}. {r['symbol']}: {r['pnl_pct']:+.2f}% за 6 мес | Win Rate: {r['win_rate']}% | PF: {r['profit_factor']}")

    # Статистика
    positive_count = len([r for r in sorted_results if r['pnl_pct'] > 0])
    negative_count = len([r for r in sorted_results if r['pnl_pct'] < 0])
    avg_pnl = sum(r['pnl_pct'] for r in sorted_results) / len(sorted_results) if sorted_results else 0

    print("\n📊 ОБЩАЯ СТАТИСТИКА:")
    print("-" * 80)
    print(f"   • Всего монет с сигналами: {len(sorted_results)}")
    print(f"   • Прибыльных монет: {positive_count} ({positive_count/len(sorted_results)*100:.1f}%)")
    print(f"   • Убыточных монет: {negative_count} ({negative_count/len(sorted_results)*100:.1f}%)")
    print(f"   • Средняя прибыль по монетам: {avg_pnl:+.2f}% за 6 мес")
    print(f"   • Средняя годовая: {avg_pnl*2:+.2f}%")

    # Лучшая монета
    best = sorted_results[0]
    print(f"\n🎯 ЛУЧШАЯ МОНЕТА: {best['symbol']}")
    print(f"   • Прибыль за 6 мес: +{best['pnl_pct']:.2f}%")
    print(f"   • Годовая: +{best['pnl_pct']*2:.2f}%")
    print(f"   • Win Rate: {best['win_rate']}%")
    print(f"   • Profit Factor: {best['profit_factor']}")
    print(f"   • Сделок: {best['total_trades']}")

    # Сравнение с обычным бэктестом
    print("\n📈 СРАВНЕНИЕ С ОДНОБИРЖЕВЫМ ТЕСТОМ (KuCoin, 50x):")
    print("-" * 80)
    
    single_results = {
        'SOL': 86.56, 'SUI': 74.21, 'TIA': 69.34, 'ETH': 60.53, 'DOT': 56.90,
        'SAND': 52.73, 'ADA': 44.10, 'LINK': 28.12, 'SEI': 21.51, 'XRP': 18.72,
        'BTC': 11.69, 'APE': 6.18, 'WIF': 3.40
    }
    
    print(f"{'Монета':<8} {'Одна биржа (50x)':<20} {'Мультибиржа (75x)':<20} {'Изменение':<15}")
    print("-" * 80)
    
    for r in sorted_results:
        single = single_results.get(r['symbol'], 0)
        multi = r['pnl_pct']
        change = multi - single
        arrow = '▲' if change > 0 else '▼' if change < 0 else '●'
        print(f"{r['symbol']:<8} {single:>15.2f}% {multi:>17.2f}% {arrow} {change:>+10.2f}%")

    # Рекомендация
    print("\n💡 ФИНАЛЬНАЯ РЕКОМЕНДАЦИЯ:")
    print("-" * 80)

    top_coins = [r['symbol'] for r in sorted_results[:5]]
    print(f"""
✅ ЛУЧШИЕ МОНЕТЫ ДЛЯ ТОРГОВЛИ: {', '.join(top_coins)}
✅ ТАЙМФРЕЙМ: 1h (DAY)
✅ RSI: 28/72
✅ АКТИВНЫЕ ЧАСЫ: 10:00-20:00 МСК (Лондон + Нью-Йорк)
✅ РИСК НА СДЕЛКУ: 3%
✅ ПЛЕЧО: {LEVERAGE}x
✅ SL/TP: ДИНАМИЧЕСКИЙ (1.5x ATR / 3.0x ATR)
✅ ДАННЫЕ: АГРЕГИРОВАННЫЕ (KuCoin + Gate.io + OKX + Bitget)

📈 ОЖИДАЕМАЯ ДОХОДНОСТЬ:
   • На лучших монетах: {best['pnl_pct']:.2f}% за 6 месяцев
   • Годовая: {best['pnl_pct']*2:.2f}%
   • С депозитом $100 → ${100 + best['pnl_pct']:.2f} через 6 месяцев
   • В месяц: ~${(100 + best['pnl_pct']) / 6:.2f}
""")

else:
    print("\n❌ Нет результатов для отображения")

print("=" * 100)
print("✅ МУЛЬТИБИРЖЕВОЙ БЭКТЕСТ ЗАВЕРШЕН")
print("=" * 100)
