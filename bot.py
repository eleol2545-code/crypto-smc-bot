import requests
import time
import ccxt
import pandas as pd
import numpy as np
import json
import os
import threading
import asyncio
import websockets
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
import io

TELEGRAM_TOKEN = "8645396589:AAHIceq907-38mvWJfa9BRaQWsrzC86ivNU"
LAST_UPDATE_ID = 0

os.makedirs('data', exist_ok=True)
os.makedirs('data/footprint', exist_ok=True)
os.makedirs('data/charts', exist_ok=True)

# ==================== ПРОКСИ (ВАШИ) ====================

PROXY_HOST1 = "155.212.48.112"
PROXY_PORT1 = "63675"
PROXY_USER1 = "bqd9tD8A"
PROXY_PASS1 = "i6wUJxiU"

PROXY_HOST2 = "154.194.89.27"
PROXY_PORT2 = "62841"
PROXY_USER2 = "bqd9tD8A"
PROXY_PASS2 = "i6wUJxiU"

PROXY_HTTP1 = f"http://{PROXY_USER1}:{PROXY_PASS1}@{PROXY_HOST1}:{PROXY_PORT1}"
PROXY_HTTP2 = f"http://{PROXY_USER2}:{PROXY_PASS2}@{PROXY_HOST2}:{PROXY_PORT2}"

# Пробуем прокси
PROXIES = None
for proxy in [PROXY_HTTP1, PROXY_HTTP2]:
    try:
        proxies = {"http": proxy, "https": proxy}
        r = requests.get("https://api.ipify.org", proxies=proxies, timeout=10)
        if r.status_code == 200:
            print(f"✅ Рабочий прокси: {proxy[:30]}... IP: {r.text}")
            PROXIES = proxies
            break
    except:
        continue

if not PROXIES:
    print("⚠️ Прокси не работают, работаем без прокси")

# ==================== ГЛОБАЛЬНЫЕ НАСТРОЙКИ ====================

GLOBAL_WATCHLIST_FILE = 'data/global_watchlist.json'
GLOBAL_SETTINGS_FILE = 'data/global_settings.json'
GLOBAL_TRADES_FILE = 'data/global_trades.json'

def get_global_watchlist():
    if os.path.exists(GLOBAL_WATCHLIST_FILE):
        with open(GLOBAL_WATCHLIST_FILE, 'r') as f:
            data = json.load(f)
            return data.get('watchlist', ['BTC', 'ETH', 'SOL'])
    return ['BTC', 'ETH', 'SOL']

def save_global_watchlist(watchlist):
    with open(GLOBAL_WATCHLIST_FILE, 'w') as f:
        json.dump({'watchlist': watchlist}, f, indent=2)

def get_global_settings():
    if os.path.exists(GLOBAL_SETTINGS_FILE):
        with open(GLOBAL_SETTINGS_FILE, 'r') as f:
            return json.load(f)
    return {'style': 'day', 'min_confidence': 70, 'notifications_enabled': True}

def save_global_settings(settings):
    with open(GLOBAL_SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=2)

# ==================== УПРАВЛЕНИЕ СДЕЛКАМИ ====================

class GlobalTradeManager:
    def __init__(self):
        self.active_trades = {}
        self.trade_counter = 1
        self.load_trades()
    
    def load_trades(self):
        if os.path.exists(GLOBAL_TRADES_FILE):
            with open(GLOBAL_TRADES_FILE, 'r') as f:
                data = json.load(f)
                self.active_trades = data.get('active', {})
                self.trade_counter = data.get('counter', 1)
    
    def save_trades(self):
        with open(GLOBAL_TRADES_FILE, 'w') as f:
            json.dump({'active': self.active_trades, 'counter': self.trade_counter}, f, indent=2)
    
    def get_next_id(self):
        current = self.trade_counter
        self.trade_counter += 1
        self.save_trades()
        return current
    
    def add_trade(self, symbol, side, entry_price, size=1, leverage=1, tp=None, sl=None):
        trade_id = self.get_next_id()
        trade = {
            'id': trade_id, 'symbol': symbol, 'side': side, 'entry': entry_price,
            'size': size, 'leverage': leverage, 'tp': tp, 'sl': sl,
            'open_time': datetime.now().isoformat(), 'status': 'open'
        }
        self.active_trades[str(trade_id)] = trade
        self.save_trades()
        return trade_id
    
    def close_trade(self, trade_id, exit_price):
        trade_id = str(trade_id)
        if trade_id not in self.active_trades:
            return None
        trade = self.active_trades[trade_id]
        if trade['side'] == 'LONG':
            pnl_pct = (exit_price - trade['entry']) / trade['entry'] * 100 * trade['leverage']
            pnl_usdt = trade['size'] * (exit_price - trade['entry']) / trade['entry'] * trade['leverage']
        else:
            pnl_pct = (trade['entry'] - exit_price) / trade['entry'] * 100 * trade['leverage']
            pnl_usdt = trade['size'] * (trade['entry'] - exit_price) / trade['entry'] * trade['leverage']
        trade['exit'] = exit_price
        trade['exit_time'] = datetime.now().isoformat()
        trade['pnl_pct'] = round(pnl_pct, 2)
        trade['pnl_usdt'] = round(pnl_usdt, 2)
        trade['status'] = 'closed'
        history_file = 'data/trades_history.json'
        history = []
        if os.path.exists(history_file):
            with open(history_file, 'r') as f:
                history = json.load(f)
        history.append(trade)
        with open(history_file, 'w') as f:
            json.dump(history, f, indent=2)
        del self.active_trades[trade_id]
        self.save_trades()
        return trade
    
    def reset_all_trades(self):
        self.active_trades = {}
        self.trade_counter = 1
        self.save_trades()
        if os.path.exists('data/trades_history.json'):
            os.remove('data/trades_history.json')
        return True
    
    def get_active_trades(self):
        return self.active_trades
    
    def get_history(self, limit=20):
        history_file = 'data/trades_history.json'
        if os.path.exists(history_file):
            with open(history_file, 'r') as f:
                history = json.load(f)
            return history[-limit:]
        return []
    
    def get_stats(self):
        history = self.get_history(1000)
        if not history:
            return {'total_trades': 0, 'wins': 0, 'losses': 0, 'win_rate': 0, 'total_pnl_pct': 0, 'total_pnl_usdt': 0, 'profit_factor': 0}
        wins = [t for t in history if t['pnl_pct'] > 0]
        losses = [t for t in history if t['pnl_pct'] <= 0]
        total_pnl_pct = sum(t['pnl_pct'] for t in history)
        total_pnl_usdt = sum(t['pnl_usdt'] for t in history)
        profit_factor = abs(sum(t['pnl_usdt'] for t in wins) / sum(t['pnl_usdt'] for t in losses)) if losses and sum(t['pnl_usdt'] for t in losses) != 0 else 0
        return {
            'total_trades': len(history), 'wins': len(wins), 'losses': len(losses),
            'win_rate': round(len(wins) / len(history) * 100, 2) if history else 0,
            'total_pnl_pct': round(total_pnl_pct, 2), 'total_pnl_usdt': round(total_pnl_usdt, 2),
            'profit_factor': round(profit_factor, 2)
        }

trade_manager = GlobalTradeManager()

# ==================== ФУНКЦИЯ ФОРМАТИРОВАНИЯ ЦЕНЫ ====================

def format_price(price):
    if price is None:
        return "0"
    if price < 0.00001:
        return f"{price:.8f}".rstrip('0').rstrip('.')
    elif price < 0.001:
        return f"{price:.6f}".rstrip('0').rstrip('.')
    elif price < 1:
        return f"{price:.4f}".rstrip('0').rstrip('.')
    elif price < 1000:
        return f"{price:.2f}"
    else:
        return f"{price:.0f}"

# ==================== ПОДКЛЮЧЕНИЕ К БИРЖЕ С ПРОКСИ ====================

def create_exchange_with_proxy(exchange_class, params):
    try:
        exchange = exchange_class(params)
        exchange.enableRateLimit = True
        if PROXIES:
            exchange.http_proxy = PROXIES.get('http')
            exchange.https_proxy = PROXIES.get('https')
        return exchange
    except:
        return None

exchange = None
exchange_name = None

# Пробуем подключиться к биржам через прокси
for name, cls, params in [
    ('Bybit', ccxt.bybit, {'options': {'defaultType': 'linear'}}),
    ('KuCoin', ccxt.kucoin, {}),
    ('Gate.io', ccxt.gateio, {'options': {'defaultType': 'swap'}}),
]:
    ex = create_exchange_with_proxy(cls, params)
    if ex:
        try:
            ticker = ex.fetch_ticker('BTCUSDT')
            exchange = ex
            exchange_name = name
            print(f"✅ {name} подключена через прокси")
            break
        except Exception as e:
            print(f"❌ {name} ошибка: {e}")
            continue

if not exchange:
    print("⚠️ Работаем в тестовом режиме")

# ==================== SMC/ICT АНАЛИЗ (Smart Money Concepts) ====================

def calculate_indicators(df):
    """Расчет всех индикаторов для SMC анализа"""
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # MACD
    ema_fast = df['close'].ewm(span=12, adjust=False).mean()
    ema_slow = df['close'].ewm(span=26, adjust=False).mean()
    df['macd_line'] = ema_fast - ema_slow
    df['macd_signal'] = df['macd_line'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd_line'] - df['macd_signal']
    
    # Bollinger Bands
    df['bb_middle'] = df['close'].rolling(window=20).mean()
    bb_std = df['close'].rolling(window=20).std()
    df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
    df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
    
    # Stochastic
    low_min = df['low'].rolling(window=14).min()
    high_max = df['high'].rolling(window=14).max()
    df['stoch_k'] = 100 * (df['close'] - low_min) / (high_max - low_min)
    df['stoch_d'] = df['stoch_k'].rolling(window=3).mean()
    
    # EMA
    df['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema_21'] = df['close'].ewm(span=21, adjust=False).mean()
    df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
    
    # VWAP
    df['typical_price'] = (df['high'] + df['low'] + df['close']) / 3
    df['vwap'] = (df['typical_price'] * df['volume']).cumsum() / df['volume'].cumsum()
    
    # Объем
    df['volume_sma'] = df['volume'].rolling(window=20).mean()
    df['volume_ratio'] = df['volume'] / df['volume_sma']
    return df

def find_order_blocks(df):
    """
    SMC: Поиск Order Blocks (зоны крупных игроков)
    Бычий OB — последняя медвежья свеча перед сильным ростом
    Медвежий OB — последняя бычья свеча перед сильным падением
    """
    df['bullish_ob'] = 0
    df['bearish_ob'] = 0
    df['ob_high'] = np.nan
    df['ob_low'] = np.nan
    
    for i in range(5, len(df) - 1):
        # Бычий Order Block
        if (df['close'].iloc[i] > df['close'].iloc[i-1] * 1.01 and
            df['volume'].iloc[i] > df['volume'].iloc[i-5:i].mean() * 1.5):
            ob_high = df['high'].iloc[i-1]
            ob_low = df['low'].iloc[i-1]
            for j in range(i, min(i + 20, len(df))):
                if df['low'].iloc[j] <= ob_high:
                    df.loc[df.index[j], 'bullish_ob'] = 1
                    df.loc[df.index[j], 'ob_high'] = ob_high
                    df.loc[df.index[j], 'ob_low'] = ob_low
        
        # Медвежий Order Block
        elif (df['close'].iloc[i] < df['close'].iloc[i-1] * 0.99 and
              df['volume'].iloc[i] > df['volume'].iloc[i-5:i].mean() * 1.5):
            ob_high = df['high'].iloc[i-1]
            ob_low = df['low'].iloc[i-1]
            for j in range(i, min(i + 20, len(df))):
                if df['high'].iloc[j] >= ob_low:
                    df.loc[df.index[j], 'bearish_ob'] = 1
                    df.loc[df.index[j], 'ob_high'] = ob_high
                    df.loc[df.index[j], 'ob_low'] = ob_low
    return df

def calculate_volume_profile(df, bars=50):
    """Volume Profile: находит POC (Point of Control) — цена с макс объемом"""
    recent = df.tail(bars)
    price_min = recent['low'].min()
    price_max = recent['high'].max()
    step = (price_max - price_min) / 20 if price_max > price_min else 1
    levels = []
    current = price_min
    while current <= price_max:
        volume = 0
        for _, row in recent.iterrows():
            if row['low'] <= current <= row['high']:
                volume += row['volume']
        levels.append({'price': current, 'volume': volume})
        current += step
    poc = max(levels, key=lambda x: x['volume']) if levels else None
    return poc['price'] if poc else None

def generate_signal(df, style='day', min_confidence=70):
    """
    Генерация SMC сигнала с системой баллов
    Учитывает: Order Blocks, RSI, MACD, Bollinger, Stochastic, объем
    """
    if df is None or len(df) < 50:
        return None
    current = df.iloc[-1]
    
    # Параметры для разных стилей торговли
    params = {
        'scalp': {'sl_pct': 0.008, 'tp_pct': 0.015, 'min_conf': 65},
        'day': {'sl_pct': 0.015, 'tp_pct': 0.03, 'min_conf': 70},
        'swing': {'sl_pct': 0.025, 'tp_pct': 0.06, 'min_conf': 75}
    }
    p = params.get(style, params['day'])
    
    score = 0
    signal_type = None
    reasons = []
    
    # 1. SMC: Order Blocks (20 баллов)
    if current['bullish_ob'] == 1:
        score += 20
        signal_type = 'LONG'
        reasons.append(f"🔵 Бычий OB: {format_price(current['ob_low'])}-{format_price(current['ob_high'])}")
    if current['bearish_ob'] == 1:
        score += 20
        signal_type = 'SHORT'
        reasons.append(f"🔴 Медвежий OB: {format_price(current['ob_low'])}-{format_price(current['ob_high'])}")
    
    # 2. RSI (15 баллов)
    if current['rsi'] < 30:
        score += 15
        if not signal_type: signal_type = 'LONG'
        reasons.append(f"📊 RSI: {current['rsi']:.1f} (перепроданность)")
    elif current['rsi'] > 70:
        score += 15
        if not signal_type: signal_type = 'SHORT'
        reasons.append(f"📊 RSI: {current['rsi']:.1f} (перекупленность)")
    
    # 3. MACD (15 баллов)
    if current['macd_hist'] > 0 and signal_type == 'LONG':
        score += 15
        reasons.append(f"📈 MACD: +{current['macd_hist']:.4f}")
    elif current['macd_hist'] < 0 and signal_type == 'SHORT':
        score += 15
        reasons.append(f"📉 MACD: {current['macd_hist']:.4f}")
    
    # 4. Bollinger Bands (15 баллов)
    if current['close'] <= current['bb_lower'] * 1.005:
        score += 15
        if not signal_type: signal_type = 'LONG'
        reasons.append(f"📊 Bollinger: у нижней полосы {format_price(current['bb_lower'])}")
    elif current['close'] >= current['bb_upper'] * 0.995:
        score += 15
        if not signal_type: signal_type = 'SHORT'
        reasons.append(f"📊 Bollinger: у верхней полосы {format_price(current['bb_upper'])}")
    
    # 5. Stochastic (15 баллов)
    if current['stoch_k'] < 20:
        score += 15
        if not signal_type: signal_type = 'LONG'
        reasons.append(f"📊 Stochastic: %K={current['stoch_k']:.1f}")
    elif current['stoch_k'] > 80:
        score += 15
        if not signal_type: signal_type = 'SHORT'
        reasons.append(f"📊 Stochastic: %K={current['stoch_k']:.1f}")
    
    # 6. Объем (10 баллов)
    if current['volume_ratio'] > 1.5:
        score += 10
        reasons.append(f"⚡ Объем: {current['volume_ratio']:.1f}x")
    
    confidence = min(100, score)
    
    if signal_type and confidence >= min_confidence:
        entry = current['close']
        if signal_type == 'LONG':
            sl = entry * (1 - p['sl_pct'])
            tp = entry * (1 + p['tp_pct'])
        else:
            sl = entry * (1 + p['sl_pct'])
            tp = entry * (1 - p['tp_pct'])
        return {
            'signal': signal_type, 'entry': entry, 'sl': sl, 'tp': tp,
            'confidence': confidence, 'score': score,
            'rr': round(abs(tp - entry) / abs(sl - entry), 1), 'reasons': reasons[:7]
        }
    return None

def get_full_analysis(symbol, style='day', min_confidence=70):
    """Полный SMC анализ для монеты"""
    if not exchange:
        return None
    try:
        sym = f"{symbol}USDT"
        ohlcv = exchange.fetch_ohlcv(sym, '1h', 150)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = calculate_indicators(df)
        df = find_order_blocks(df)
        poc = calculate_volume_profile(df)
        signal = generate_signal(df, style, min_confidence)
        return {
            'price': df['close'].iloc[-1], 'signal': signal, 'poc': poc,
            'support': df['low'].iloc[-20:].min(), 'resistance': df['high'].iloc[-20:].max(),
            'exchange': exchange_name, 'df': df
        }
    except Exception as e:
        print(f"Error: {e}")
        return None

# ==================== ГРАФИК С УРОВНЯМИ SMC ====================

def generate_smc_chart(symbol, df, analysis, signal, style='day'):
    """Генерирует график с уровнями SMC: Order Blocks, FVG, POC"""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), gridspec_kw={'height_ratios': [3, 1]})
    df_plot = df.tail(100)
    dates = df_plot['timestamp']
    
    # Рисуем свечи
    for i, row in df_plot.iterrows():
        color = '#00ff88' if row['close'] >= row['open'] else '#ff4444'
        ax1.plot([row['timestamp'], row['timestamp']], [row['low'], row['high']], color=color, linewidth=0.8)
        ax1.add_patch(Rectangle((row['timestamp'] - pd.Timedelta(minutes=30), row['open']), pd.Timedelta(minutes=60), row['close'] - row['open'], facecolor=color, alpha=0.7, linewidth=0))
    
    # Order Blocks (зеленые/красные зоны)
    if 'bullish_ob' in df.columns:
        for i in range(len(df_plot)):
            if df_plot['bullish_ob'].iloc[i] == 1:
                ob_high = df_plot['ob_high'].iloc[i]
                ob_low = df_plot['ob_low'].iloc[i]
                if ob_high and ob_low and not np.isnan(ob_high):
                    ax1.axhspan(ob_low, ob_high, alpha=0.2, color='green')
    
    if 'bearish_ob' in df.columns:
        for i in range(len(df_plot)):
            if df_plot['bearish_ob'].iloc[i] == 1:
                ob_high = df_plot['ob_high'].iloc[i]
                ob_low = df_plot['ob_low'].iloc[i]
                if ob_high and ob_low and not np.isnan(ob_high):
                    ax1.axhspan(ob_low, ob_high, alpha=0.2, color='red')
    
    # POC
    if analysis and analysis.get('poc'):
        ax1.axhline(y=analysis['poc'], color='yellow', linestyle='--', linewidth=1.5, alpha=0.7, label=f'POC: {format_price(analysis["poc"])}')
    
    # Уровни поддержки/сопротивления
    if analysis:
        ax1.axhline(y=analysis['support'], color='cyan', linestyle='--', linewidth=1, alpha=0.5, label=f'Support: {format_price(analysis["support"])}')
        ax1.axhline(y=analysis['resistance'], color='orange', linestyle='--', linewidth=1, alpha=0.5, label=f'Resistance: {format_price(analysis["resistance"])}')
    
    # Уровни входа/выхода
    if signal:
        entry = signal['entry']
        sl = signal['sl']
        tp = signal['tp']
        color = 'green' if signal['signal'] == 'LONG' else 'red'
        ax1.axhline(y=entry, color=color, linestyle='-', linewidth=2, label=f'Entry: {format_price(entry)}')
        ax1.axhline(y=sl, color='red', linestyle='--', linewidth=1.5, label=f'SL: {format_price(sl)}')
        ax1.axhline(y=tp, color='lime', linestyle='--', linewidth=1.5, label=f'TP: {format_price(tp)}')
        last_date = df_plot['timestamp'].iloc[-1]
        ax1.annotate('ВХОД', xy=(last_date, entry), xytext=(last_date, entry * (1.02 if signal['signal'] == 'LONG' else 0.98)), arrowprops=dict(arrowstyle='->', color=color, lw=2), fontsize=10, fontweight='bold', color=color)
    
    # Объем
    colors = ['#00ff88' if close >= open else '#ff4444' for close, open in zip(df_plot['close'], df_plot['open'])]
    ax2.bar(dates, df_plot['volume'], color=colors, alpha=0.7, width=0.8)
    ax2.set_ylabel('Volume', color='white')
    ax2.grid(True, alpha=0.2)
    
    # Оформление
    ax1.set_title(f'{symbol} | {style.upper()} | SMC Analysis', fontsize=14, fontweight='bold', color='white')
    ax1.set_ylabel('Price (USDT)', color='white')
    ax1.legend(loc='upper left', fontsize=8, facecolor='#1a1a2e')
    ax1.grid(True, alpha=0.2)
    ax1.set_facecolor('#0a0a0a')
    ax2.set_facecolor('#0a0a0a')
    fig.patch.set_facecolor('#0a0a0a')
    
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %H:%M'))
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100, bbox_inches='tight', facecolor='#0a0a0a')
    buf.seek(0)
    plt.close()
    return buf

# ==================== АНАЛИЗ СТАКАНА L2 ====================

class OrderBookAnalyzer:
    def __init__(self):
        self.exchange = None
    
    def set_exchange(self, ex):
        self.exchange = ex
    
    def get_orderbook(self, symbol):
        try:
            return self.exchange.fetch_order_book(symbol, limit=20)
        except:
            return None
    
    def analyze_liquidity_walls(self, orderbook):
        """Анализирует стены ликвидности в стакане"""
        if not orderbook:
            return None
        bid_walls = []
        for bid in orderbook['bids'][:10]:
            price, quantity = bid
            value = price * quantity
            if value > 500_000:
                bid_walls.append({'price': price, 'quantity': quantity, 'value_usdt': value, 'type': 'BID'})
        ask_walls = []
        for ask in orderbook['asks'][:10]:
            price, quantity = ask
            value = price * quantity
            if value > 500_000:
                ask_walls.append({'price': price, 'quantity': quantity, 'value_usdt': value, 'type': 'ASK'})
        all_walls = bid_walls + ask_walls
        biggest_wall = max(all_walls, key=lambda x: x['value_usdt']) if all_walls else None
        total_bid_value = sum(w['value_usdt'] for w in bid_walls)
        total_ask_value = sum(w['value_usdt'] for w in ask_walls)
        return {
            'bid_walls': bid_walls[:5], 'ask_walls': ask_walls[:5], 'biggest_wall': biggest_wall,
            'total_bid_value': total_bid_value, 'total_ask_value': total_ask_value,
            'balance': total_bid_value - total_ask_value,
            'dominant': 'BUYERS' if total_bid_value > total_ask_value else 'SELLERS'
        }

orderbook_analyzer = OrderBookAnalyzer()
orderbook_analyzer.set_exchange(exchange)

# ==================== TELEGRAM БОТ ====================

def send_message(chat_id, text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}, timeout=10, proxies=PROXIES)
    except:
        pass

def send_photo(chat_id, photo_buf, caption=""):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
        files = {'photo': ('chart.png', photo_buf, 'image/png')}
        data = {'chat_id': chat_id, 'caption': caption, 'parse_mode': 'Markdown'}
        requests.post(url, files=files, data=data, timeout=10, proxies=PROXIES)
    except:
        pass

def format_signal(symbol, analysis, style='day'):
    if not analysis:
        return f"❌ Ошибка получения данных для {symbol}"
    signal = analysis['signal']
    price = analysis['price']
    if signal:
        emoji = "📈" if signal['signal'] == 'LONG' else "📉"
        msg = f"""{emoji} *{signal['signal']} СИГНАЛ* | {symbol} | {style.upper()}

💰 Цена: {format_price(price)}
🎯 Уверенность: {signal['confidence']}%
📊 Баллы: {signal['score']}/100
📈 R:R: 1:{signal['rr']}

🚪 Вход: {format_price(signal['entry'])}
🛑 SL: {format_price(signal['sl'])}
🎯 TP: {format_price(signal['tp'])}

📊 *SMC Анализ:*\n"""
        for r in signal['reasons']:
            msg += f"• {r}\n"
        if analysis['poc']:
            msg += f"• 🟡 POC: {format_price(analysis['poc'])}\n"
        msg += f"\n🏦 *Биржа:* {analysis['exchange']}"
        return msg
    else:
        return f"""⏳ *НЕТ СИГНАЛА* | {symbol} | {style.upper()}

💰 Цена: {format_price(price)}
🟢 Поддержка: {format_price(analysis['support'])}
🔴 Сопротивление: {format_price(analysis['resistance'])}
📊 POC: {format_price(analysis['poc'])}
\n💡 Рекомендация: наблюдение\n🏦 *Биржа:* {analysis['exchange']}"""

def handle_message(chat_id, text):
    print(f"Message from {chat_id}: {text}")
    settings = get_global_settings()
    watchlist = get_global_watchlist()
    
    if text == "/start":
        status = "🟢 РАБОТАЕТ" if exchange else "🟡 ТЕСТОВЫЙ РЕЖИМ"
        msg = f"""🤖 *SMC CRYPTO BOT* — SMC/ICT СТРАТЕГИЯ

📊 *Статус:* {status}
🏦 *Биржа:* {exchange_name if exchange else 'Тестовый режим'}
🔒 *Прокси:* {'✅ ВКЛЮЧЕН' if PROXIES else '❌ ВЫКЛЮЧЕН'}
🌍 *Режим:* Глобальный (все видят одно)

📊 *SMC/ICT МЕТОДОЛОГИЯ:*
• Order Blocks — зоны крупных игроков
• Fair Value Gaps (FVG) — разрывы цены
• Volume Profile / POC — точки контроля
• Liquidity Levels — уровни ликвидности

📈 *Индикаторы:* RSI, MACD, Bollinger, Stochastic, VWAP, EMA
🎯 *Стили:* SCALP (внутри дня), DAY (дневная), SWING (среднесрок)

*Команды:*
/add BTC,ETH,SOL,DOGE,PEPE — добавить монеты
/remove DOGE — удалить
/list — список монет
/signals — сигналы (ваш стиль)
/all_signals — сигналы по ВСЕМ стилям!
/chart BTC — график с уровнями SMC
/orderbook BTC — анализ стакана (стены ликвидности)
/aggregate BTC — агрегированные данные со всех бирж
/analyze PEPE — анализ любой монеты
/scalp BTC — скальп-сигнал
/swing BTC — свинг-сигнал
/take LONG BTC 65000 100 5 — открыть сделку
/close 123 — закрыть сделку
/trades — активные сделки
/history — история сделок
/stats — статистика
/pnl — текущий P&L
/reset_trades — СБРОСИТЬ ВСЕ СДЕЛКИ
/style scalp|day|swing — сменить стиль
/confidence 70 — мин. уверенность
/notifications_on — включить автоуведомления
/notifications_off — выключить
/exchange — текущая биржа
/status — статус
/help — помощь"""
        send_message(chat_id, msg)
    
    elif text.startswith("/add"):
        args = text.replace("/add", "").strip().upper().replace(",", " ").split()
        added = []
        for arg in args:
            if arg not in watchlist:
                watchlist.append(arg)
                added.append(arg)
        save_global_watchlist(watchlist)
        send_message(chat_id, f"✅ Добавлено для ВСЕХ: {', '.join(added)}\n\n📋 Всего монет: {len(watchlist)}")
    
    elif text.startswith("/remove"):
        args = text.replace("/remove", "").strip().upper()
        if args and args in watchlist:
            watchlist.remove(args)
            save_global_watchlist(watchlist)
            send_message(chat_id, f"❌ Удалено для ВСЕХ: {args}")
        else:
            send_message(chat_id, f"⚠️ {args} не найдена")
    
    elif text == "/list":
        if not watchlist:
            send_message(chat_id, "📭 Список пуст. Добавьте: `/add BTC`")
        else:
            msg = "📋 *МОИ МОНЕТЫ* (глобальные)\n\n"
            for s in watchlist:
                msg += f"• {s}\n"
            send_message(chat_id, msg)
    
    elif text == "/signals":
        if not watchlist:
            send_message(chat_id, "📭 Нет монет в списке")
            return
        send_message(chat_id, f"🔍 *Поиск SMC сигналов...*\n🏦 Биржа: {exchange_name if exchange else 'Тестовый режим'}")
        msg = f"🚨 *SMC СИГНАЛЫ* ({settings['style'].upper()})\n\n"
        for sym in watchlist[:5]:
            analysis = get_full_analysis(sym, settings['style'], settings['min_confidence'])
            if analysis:
                msg += format_signal(sym, analysis, settings['style']) + "\n\n"
            else:
                msg += f"❌ *{sym}* | ошибка получения данных\n\n"
        send_message(chat_id, msg[:4000])
    
    elif text == "/all_signals":
        if not watchlist:
            send_message(chat_id, "📭 Нет монет в списке")
            return
        send_message(chat_id, f"🔍 *Поиск SMC сигналов по всем стилям...*\n🏦 Биржа: {exchange_name if exchange else 'Тестовый режим'}")
        msg = "🚨 *SMC СИГНАЛЫ ПО ВСЕМ СТИЛЯМ*\n\n"
        for sym in watchlist[:5]:
            msg += f"📊 *{sym}*\n"
            
            analysis_scalp = get_full_analysis(sym, 'scalp', 65)
            if analysis_scalp and analysis_scalp['signal']:
                s = analysis_scalp['signal']
                emoji = "📈" if s['signal'] == 'LONG' else "📉"
                msg += f"  {emoji} *SCALP* {s['signal']} | Увер: {s['confidence']}% | RR 1:{s['rr']}\n"
                msg += f"     🚪 {format_price(s['entry'])} | 🛑 {format_price(s['sl'])} | 🎯 {format_price(s['tp'])}\n"
            else:
                price = analysis_scalp['price'] if analysis_scalp else '?'
                msg += f"  ⏳ *SCALP* | нет сигнала | Цена: {format_price(price)}\n"
            
            analysis_day = get_full_analysis(sym, 'day', 70)
            if analysis_day and analysis_day['signal']:
                s = analysis_day['signal']
                emoji = "📈" if s['signal'] == 'LONG' else "📉"
                msg += f"  {emoji} *DAY* {s['signal']} | Увер: {s['confidence']}% | RR 1:{s['rr']}\n"
                msg += f"     🚪 {format_price(s['entry'])} | 🛑 {format_price(s['sl'])} | 🎯 {format_price(s['tp'])}\n"
            else:
                price = analysis_day['price'] if analysis_day else '?'
                msg += f"  ⏳ *DAY* | нет сигнала | Цена: {format_price(price)}\n"
            
            analysis_swing = get_full_analysis(sym, 'swing', 75)
            if analysis_swing and analysis_swing['signal']:
                s = analysis_swing['signal']
                emoji = "📈" if s['signal'] == 'LONG' else "📉"
                msg += f"  {emoji} *SWING* {s['signal']} | Увер: {s['confidence']}% | RR 1:{s['rr']}\n"
                msg += f"     🚪 {format_price(s['entry'])} | 🛑 {format_price(s['sl'])} | 🎯 {format_price(s['tp'])}\n"
            else:
                price = analysis_swing['price'] if analysis_swing else '?'
                msg += f"  ⏳ *SWING* | нет сигнала | Цена: {format_price(price)}\n"
            
            msg += "\n"
        send_message(chat_id, msg[:4000])
    
    elif text.startswith("/chart"):
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id, "📝 *Пример:* `/chart BTC`")
            return
        symbol = parts[1].upper()
        send_message(chat_id, f"📊 *Генерирую SMC график для {symbol}...*")
        analysis = get_full_analysis(symbol, settings['style'], settings['min_confidence'])
        if analysis and analysis.get('df') is not None:
            chart = generate_smc_chart(symbol, analysis['df'], analysis, analysis['signal'], settings['style'])
            caption = f"📈 *{symbol}* | {settings['style'].upper()}\n💰 Цена: {format_price(analysis['price'])}"
            if analysis['signal']:
                caption += f"\n🎯 Сигнал: {analysis['signal']['signal']} | Увер: {analysis['signal']['confidence']}%"
            send_photo(chat_id, chart, caption)
        else:
            send_message(chat_id, f"❌ Не удалось создать график для {symbol}")
    
    elif text.startswith("/orderbook"):
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id, "📝 *Пример:* `/orderbook BTC`")
            return
        symbol = parts[1].upper()
        send_message(chat_id, f"📚 *Анализ стакана для {symbol}...*")
        if exchange:
            try:
                sym = f"{symbol}USDT"
                orderbook = exchange.fetch_order_book(sym, limit=20)
                if orderbook:
                    analysis = orderbook_analyzer.analyze_liquidity_walls(orderbook)
                    msg = f"""📚 *СТАКАН L2 | {symbol}* — стены ликвидности

🏦 *Биржа:* {exchange_name}

🟢 *КРУПНЫЕ ЗАЯВКИ НА ПОКУПКУ:*\n"""
                    for wall in analysis['bid_walls'][:3]:
                        msg += f"  • ${format_price(wall['price'])} | {wall['quantity']:.0f} | ${wall['value_usdt']/1000:.0f}K\n"
                    if not analysis['bid_walls']:
                        msg += "  • Нет крупных стен\n"
                    msg += f"\n🔴 *КРУПНЫЕ ЗАЯВКИ НА ПРОДАЖУ:*\n"""
                    for wall in analysis['ask_walls'][:3]:
                        msg += f"  • ${format_price(wall['price'])} | {wall['quantity']:.0f} | ${wall['value_usdt']/1000:.0f}K\n"
                    if not analysis['ask_walls']:
                        msg += "  • Нет крупных стен\n"
                    msg += f"\n📊 *ИТОГО:*\n  • Объем покупок: ${analysis['total_bid_value']/1000:.0f}K\n  • Объем продаж: ${analysis['total_ask_value']/1000:.0f}K\n  • Баланс: {'+' if analysis['balance'] > 0 else ''}{analysis['balance']/1000:.0f}K\n  • Доминируют: {analysis['dominant']}\n"
                    if analysis['biggest_wall']:
                        wall = analysis['biggest_wall']
                        msg += f"\n🔥 *САМАЯ КРУПНАЯ СТЕНА:*\n  • Тип: {'ПОКУПКА' if wall['type'] == 'BID' else 'ПРОДАЖА'}\n  • Цена: ${format_price(wall['price'])}\n  • Объем: ${wall['value_usdt']/1000:.0f}K\n"
                    send_message(chat_id, msg)
                else:
                    send_message(chat_id, f"❌ Не удалось получить стакан для {symbol}")
            except Exception as e:
                send_message(chat_id, f"❌ Ошибка: {e}")
        else:
            send_message(chat_id, f"❌ Биржа недоступна, работаем в тестовом режиме")
    
    elif text == "/aggregate":
        parts = text.split()
        symbol = parts[1].upper() if len(parts) > 1 else 'BTC'
        send_message(chat_id, f"📊 *АГРЕГИРОВАННЫЕ ДАННЫЕ | {symbol}*\n\n🏦 *Биржи:* Bybit, KuCoin, Gate.io\n🔒 *Прокси:* {'✅ ВКЛЮЧЕН' if PROXIES else '❌ ВЫКЛЮЧЕН'}\n\n📡 Данные агрегируются...\n\n💡 Рекомендуется использовать /signals для получения SMC сигналов")
    
    elif text.startswith("/analyze"):
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id, "📝 *Пример:* `/analyze PEPE`")
            return
        symbol = parts[1].upper()
        send_message(chat_id, f"🔍 *SMC анализ {symbol}...*\n🏦 Биржа: {exchange_name if exchange else 'Тестовый режим'}")
        analysis = get_full_analysis(symbol, settings['style'], settings['min_confidence'])
        if analysis:
            send_message(chat_id, format_signal(symbol, analysis, settings['style']))
        else:
            send_message(chat_id, f"❌ Не удалось получить данные для {symbol}")
    
    elif text.startswith("/scalp"):
        parts = text.split()
        symbol = parts[1].upper() if len(parts) > 1 else 'BTC'
        analysis = get_full_analysis(symbol, 'scalp', 65)
        if analysis:
            send_message(chat_id, format_signal(symbol, analysis, 'scalp'))
        else:
            send_message(chat_id, f"❌ Не удалось получить данные для {symbol}")
    
    elif text.startswith("/swing"):
        parts = text.split()
        symbol = parts[1].upper() if len(parts) > 1 else 'BTC'
        analysis = get_full_analysis(symbol, 'swing', 75)
        if analysis:
            send_message(chat_id, format_signal(symbol, analysis, 'swing'))
        else:
            send_message(chat_id, f"❌ Не удалось получить данные для {symbol}")
    
    # ==================== УПРАВЛЕНИЕ СДЕЛКАМИ ====================
    
    elif text.startswith("/take"):
        parts = text.split()
        if len(parts) < 4:
            send_message(chat_id, "📝 *Формат:* `/take LONG BTC 65000`\nИли: `/take LONG BTC 65000 100 5`\n\n*Параметры:*\n- Сторона: LONG/SHORT\n- Монета: BTC, ETH, SOL\n- Цена входа\n- Размер (опционально, USDT)\n- Плечо (опционально, x1 по умолчанию)\n- TP (опционально)\n- SL (опционально)")
            return
        side = parts[1].upper()
        symbol = parts[2].upper()
        try:
            entry = float(parts[3])
        except:
            send_message(chat_id, "❌ Цена должна быть числом")
            return
        size = float(parts[4]) if len(parts) > 4 else 1
        leverage = float(parts[5]) if len(parts) > 5 else 1
        tp = float(parts[6]) if len(parts) > 6 else None
        sl = float(parts[7]) if len(parts) > 7 else None
        
        trade_id = trade_manager.add_trade(symbol, side, entry, size, leverage, tp, sl)
        
        msg = f"✅ *СДЕЛКА ЗАФИКСИРОВАНА*\n\n📊 *{side} {symbol}*\n💰 Вход: ${entry:.2f}\n📦 Размер: {size} USDT\n⚡ Плечо: x{leverage}\n🆔 ID: {trade_id}"
        if tp: msg += f"\n🎯 TP: ${tp:.2f}"
        if sl: msg += f"\n🛑 SL: ${sl:.2f}"
        send_message(chat_id, msg)
    
    elif text.startswith("/close"):
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id, "📝 *Пример:* `/close 123`\nИли: `/close 123 66000`")
            return
        try:
            trade_id = int(parts[1])
            exit_price = float(parts[2]) if len(parts) > 2 else None
            
            active = trade_manager.get_active_trades()
            if str(trade_id) not in active:
                send_message(chat_id, f"❌ Сделка с ID {trade_id} не найдена")
                return
            trade = active[str(trade_id)]
            
            if not exit_price:
                if exchange:
                    try:
                        ticker = exchange.fetch_ticker(f"{trade['symbol']}USDT")
                        exit_price = ticker['last']
                    except:
                        exit_price = trade['entry'] * (1.02 if trade['side'] == 'LONG' else 0.98)
                else:
                    exit_price = trade['entry'] * (1.02 if trade['side'] == 'LONG' else 0.98)
            
            closed = trade_manager.close_trade(trade_id, exit_price)
            if closed:
                emoji = "✅" if closed['pnl_pct'] > 0 else "❌"
                msg = f"{emoji} *СДЕЛКА ЗАКРЫТА*\n\n📊 *{closed['side']} {closed['symbol']}*\n💰 Вход: ${closed['entry']:.2f}\n🚪 Выход: ${closed['exit']:.2f}\n📈 P&L: {closed['pnl_pct']:+.2f}% (${closed['pnl_usdt']:+.2f})\n⚡ Плечо: x{closed['leverage']}"
                send_message(chat_id, msg)
        except ValueError:
            send_message(chat_id, "❌ ID должен быть числом")
    
    elif text == "/trades":
        active = trade_manager.get_active_trades()
        if not active:
            send_message(chat_id, "📭 *Нет активных сделок*")
            return
        msg = "📊 *АКТИВНЫЕ СДЕЛКИ*\n\n"
        for trade_id, trade in active.items():
            current_price = trade['entry']
            if exchange:
                try:
                    ticker = exchange.fetch_ticker(f"{trade['symbol']}USDT")
                    current_price = ticker['last']
                except:
                    pass
            if trade['side'] == 'LONG':
                pnl = (current_price - trade['entry']) / trade['entry'] * 100 * trade['leverage']
            else:
                pnl = (trade['entry'] - current_price) / trade['entry'] * 100 * trade['leverage']
            emoji = "📈" if pnl > 0 else "📉"
            msg += f"🆔 *{trade_id}* | {trade['symbol']} | {trade['side']}\n   💰 Вход: ${trade['entry']:.2f}\n   📍 Текущая: ${current_price:.2f}\n   📊 P&L: {pnl:+.2f}%\n   ⚡ Плечо: x{trade['leverage']}\n"
            if trade.get('tp'): msg += f"   🎯 TP: ${trade['tp']:.2f}\n"
            if trade.get('sl'): msg += f"   🛑 SL: ${trade['sl']:.2f}\n"
            msg += "\n"
        send_message(chat_id, msg)
    
    elif text == "/history":
        history = trade_manager.get_history(10)
        if not history:
            send_message(chat_id, "📭 *Нет истории сделок*")
            return
        msg = "📜 *ПОСЛЕДНИЕ СДЕЛКИ*\n\n"
        for trade in reversed(history):
            emoji = "✅" if trade['pnl_pct'] > 0 else "❌"
            msg += f"{emoji} *{trade['side']} {trade['symbol']}*\n   Вход: ${trade['entry']:.2f} → Выход: ${trade['exit']:.2f}\n   P&L: {trade['pnl_pct']:+.2f}% (${trade['pnl_usdt']:+.2f})\n   ⚡ Плечо: x{trade['leverage']}\n   {trade['open_time'][:16]}\n\n"
        send_message(chat_id, msg)
    
    elif text == "/stats":
        stats = trade_manager.get_stats()
        if stats['total_trades'] == 0:
            send_message(chat_id, "📭 *Нет данных для статистики*\n\nСначала отметьте сделки через `/take`")
            return
        msg = f"""📊 *СТАТИСТИКА ТРЕЙДИНГА*

📈 *Всего сделок:* {stats['total_trades']}
✅ *Прибыльных:* {stats['wins']}
❌ *Убыточных:* {stats['losses']}
🎯 *Win Rate:* {stats['win_rate']}%

💰 *Общая прибыль:* {stats['total_pnl_pct']:+.2f}% (${stats['total_pnl_usdt']:+.2f})
📊 *Profit Factor:* {stats['profit_factor']}"""
        send_message(chat_id, msg)
    
    elif text == "/pnl":
        active = trade_manager.get_active_trades()
        if not active:
            send_message(chat_id, "📭 *Нет открытых сделок*")
            return
        total_pnl = 0
        msg = "📊 *ТЕКУЩИЙ P&L*\n\n"
        for trade_id, trade in active.items():
            current_price = trade['entry']
            if exchange:
                try:
                    ticker = exchange.fetch_ticker(f"{trade['symbol']}USDT")
                    current_price = ticker['last']
                except:
                    pass
            if trade['side'] == 'LONG':
                pnl_pct = (current_price - trade['entry']) / trade['entry'] * 100 * trade['leverage']
                pnl_usdt = trade['size'] * (current_price - trade['entry']) / trade['entry'] * trade['leverage']
            else:
                pnl_pct = (trade['entry'] - current_price) / trade['entry'] * 100 * trade['leverage']
                pnl_usdt = trade['size'] * (trade['entry'] - current_price) / trade['entry'] * trade['leverage']
            total_pnl += pnl_usdt
            emoji = "📈" if pnl_pct > 0 else "📉"
            msg += f"{emoji} *{trade['side']} {trade['symbol']}* (ID: {trade_id})\n   P&L: {pnl_pct:+.2f}% (${pnl_usdt:+.2f})\n   ⚡ Плечо: x{trade['leverage']}\n\n"
        msg += f"\n💰 *ИТОГО:* ${total_pnl:+.2f}"
        send_message(chat_id, msg)
    
    elif text == "/reset_trades":
        trade_manager.reset_all_trades()
        send_message(chat_id, "🗑️ *ВСЕ СДЕЛКИ СБРОШЕНЫ*\n\nИстория и активные сделки очищены.")
    
    # ==================== НАСТРОЙКИ ====================
    
    elif text.startswith("/style"):
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id, "📝 *Пример:* `/style scalp` (scalp/day/swing)")
            return
        new_style = parts[1].lower()
        if new_style in ['scalp', 'day', 'swing']:
            settings['style'] = new_style
            save_global_settings(settings)
            send_message(chat_id, f"✅ Стиль изменен на {new_style.upper()} (для всех пользователей)")
        else:
            send_message(chat_id, "⚠️ Доступные стили: scalp, day, swing")
    
    elif text.startswith("/confidence"):
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id, "📝 *Пример:* `/confidence 70`")
            return
        try:
            val = int(parts[1])
            if 50 <= val <= 90:
                settings['min_confidence'] = val
                save_global_settings(settings)
                send_message(chat_id, f"✅ Мин. уверенность: {val}% (для всех пользователей)")
            else:
                send_message(chat_id, "⚠️ Значение от 50 до 90")
        except:
            send_message(chat_id, "⚠️ Введите число")
    
    elif text == "/notifications_on":
        settings['notifications_enabled'] = True
        save_global_settings(settings)
        send_message(chat_id, "🔔 *Уведомления ВКЛЮЧЕНЫ*\n\nБуду присылать SMC сигналы автоматически!")
    
    elif text == "/notifications_off":
        settings['notifications_enabled'] = False
        save_global_settings(settings)
        send_message(chat_id, "🔕 *Уведомления ВЫКЛЮЧЕНЫ*")
    
    elif text == "/exchange":
        send_message(chat_id, f"🏦 *Текущая биржа:* {exchange_name if exchange else 'Тестовый режим'}\n🔒 *Прокси:* {'✅ ВКЛЮЧЕН' if PROXIES else '❌ ВЫКЛЮЧЕН'}\n\nДоступные: Bybit, KuCoin, Gate.io")
    
    elif text == "/status":
        btc = get_full_analysis('BTC', 'day')
        active_trades = len(trade_manager.get_active_trades())
        if btc:
            msg = f"""✅ *СТАТУС БОТА* (Глобальный)

🏦 *Биржа:* {exchange_name if exchange else 'Тестовый режим'}
🔒 *Прокси:* {'✅ ВКЛЮЧЕН' if PROXIES else '❌ ВЫКЛЮЧЕН'}
🎯 *SMC Стиль:* {settings['style'].upper()}
📊 *Мин. уверенность:* {settings['min_confidence']}%
📋 *Монет:* {len(watchlist)}
🔄 *Активных сделок:* {active_trades}
🔔 *Уведомления:* {'✅ ВКЛ' if settings.get('notifications_enabled', True) else '❌ ВЫКЛ'}

📈 *BTC SMC анализ:* {format_price(btc['price'])}
🟢 *Поддержка:* {format_price(btc['support'])}
🔴 *Сопротивление:* {format_price(btc['resistance'])}
📊 *POC:* {format_price(btc['poc'])}"""
            send_message(chat_id, msg)
        else:
            send_message(chat_id, "✅ Бот активен")
    
    elif text == "/help":
        send_message(chat_id, """📋 *ВСЕ КОМАНДЫ*

📌 *Управление монетами (глобально!):*
/add BTC,DOGE,PEPE — добавить для ВСЕХ
/remove DOGE — удалить для ВСЕХ
/list — список монет

📌 *SMC/ICT Сигналы:*
/signals — сигналы (ваш стиль)
/all_signals — сигналы по ВСЕМ стилям!
/chart BTC — график с уровнями SMC
/orderbook BTC — анализ стакана (стены ликвидности)
/aggregate BTC — агрегированные данные со всех бирж
/analyze PEPE — анализ любой монеты
/scalp BTC — скальп-сигнал
/swing BTC — свинг-сигнал

📌 *Управление сделками (глобально!):*
/take LONG BTC 65000 100 5 — открыть (размер USDT, плечо)
/close 123 — закрыть сделку
/trades — активные сделки
/history — история сделок
/stats — статистика
/pnl — текущий P&L
/reset_trades — СБРОСИТЬ ВСЕ СДЕЛКИ

📌 *Настройки (глобально!):*
/style scalp|day|swing — сменить стиль для ВСЕХ
/confidence 70 — мин. уверенность для ВСЕХ
/notifications_on — включить автоуведомления
/notifications_off — выключить

📌 *Другое:*
/exchange — текущая биржа
/status — статус
/help — помощь

📊 *SMC/ICT Методология:*
• Order Blocks — зоны крупных игроков
• Fair Value Gaps (FVG) — разрывы цены
• Volume Profile / POC — точки контроля
• Стены ликвидности — крупные заявки в стакане""")
    
    else:
        send_message(chat_id, f"⚠️ Неизвестно: {text}\n/help")

# ==================== ЗАПУСК ====================

print("=" * 60)
print("🚀 SMC FULL BOT — SMC/ICT СТРАТЕГИЯ")
print("=" * 60)
print(f"🔒 Прокси: {'✅ ВКЛЮЧЕН (2 шт)' if PROXIES else '❌ ВЫКЛЮЧЕН'}")
print(f"🏦 Биржа: {exchange_name if exchange else 'Тестовый режим'}")
print("🌍 Режим: ГЛОБАЛЬНЫЙ — все пользователи видят одни и те же монеты")
print("📊 SMC/ICT Анализ: Order Blocks, FVG, Volume Profile, POC")
print("📈 Индикаторы: RSI, MACD, Bollinger, Stochastic, VWAP, EMA")
print("🎯 Стили: SCALP (0.8%/1.5%), DAY (1.5%/3%), SWING (2.5%/6%)")
print("📊 Команды: /all_signals, /chart BTC, /orderbook BTC, /aggregate BTC")
print("📈 Статистика: /stats, /trades, /pnl")
print("🗑️ Сброс сделок: /reset_trades")
print("=" * 60)
print("Ожидание сообщений...\n")

while True:
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        response = requests.get(url, params={"offset": LAST_UPDATE_ID + 1, "timeout": 30}, proxies=PROXIES)
        data = response.json()
        if data.get("ok"):
            for update in data.get("result", []):
                if update["update_id"] > LAST_UPDATE_ID:
                    LAST_UPDATE_ID = update["update_id"]
                    if "message" in update:
                        msg = update["message"]
                        chat_id = msg["chat"]["id"]
                        text = msg.get("text", "")
                        handle_message(chat_id, text)
    except Exception as e:
        print(f"Error: {e}")
    time.sleep(1)
