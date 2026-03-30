import requests
import time
import ccxt
import pandas as pd
import numpy as np
import json
import os
import threading
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
import io

TELEGRAM_TOKEN = "8645396589:AAHIceq907-38mvWJfa9BRaQWsrzC86ivNU"
LAST_UPDATE_ID = 0

os.makedirs('data', exist_ok=True)
os.makedirs('data/charts', exist_ok=True)

# ==================== КОНФИГУРАЦИЯ ====================
RISK_PER_TRADE = 3
RSI_LOW = 28
RSI_HIGH = 72
CHECK_INTERVAL = 60

# ==================== ТОРГОВЫЕ СЕССИИ ====================
SESSIONS = {
    'asia': {'name': '🇯🇵 АЗИАТСКАЯ', 'start': 2, 'end': 10, 'volatility': 'Низкая', 'color': '🟡'},
    'london': {'name': '🇬🇧 ЛОНДОНСКАЯ', 'start': 10, 'end': 16, 'volatility': 'Высокая', 'color': '🟢'},
    'newyork': {'name': '🇺🇸 НЬЮ-ЙОРКСКАЯ', 'start': 16, 'end': 22, 'volatility': 'Очень высокая', 'color': '🔴'},
    'calm': {'name': '😴 ТИХАЯ', 'start': 22, 'end': 2, 'volatility': 'Низкая', 'color': '⚪'}
}

def get_current_session():
    now = datetime.now()
    current_hour = now.hour
    if 10 <= current_hour < 16:
        return 'london'
    elif 16 <= current_hour < 22:
        return 'newyork'
    elif 2 <= current_hour < 10:
        return 'asia'
    else:
        return 'calm'

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
    
    def add_trade(self, symbol, side, entry_price, leverage, size=1, tp=None, sl=None):
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

# ==================== МУЛЬТИБИРЖЕВОЙ АГРЕГАТОР ====================
class MultiExchangeAggregator:
    def __init__(self):
        self.exchanges = []
        self.init_exchanges()
    
    def init_exchanges(self):
        exchanges_config = [
            {'name': 'KuCoin', 'class': ccxt.kucoin, 'params': {}},
            {'name': 'Gate.io', 'class': ccxt.gateio, 'params': {}},
            {'name': 'OKX', 'class': ccxt.okx, 'params': {}},
            {'name': 'Bitget', 'class': ccxt.bitget, 'params': {}},
        ]
        for config in exchanges_config:
            try:
                ex = config['class'](config['params'])
                ex.enableRateLimit = True
                self.exchanges.append({'name': config['name'], 'exchange': ex})
                print(f"✅ {config['name']} подключена")
            except Exception as e:
                print(f"❌ {config['name']} ошибка: {e}")
    
    def format_symbol(self, exchange_name, symbol):
        symbol_clean = symbol.upper().replace('/USDT', '').replace('USDT', '').replace('/', '')
        if exchange_name == 'KuCoin':
            return f"{symbol_clean}/USDT"
        elif exchange_name == 'Gate.io':
            return f"{symbol_clean}_USDT"
        elif exchange_name == 'OKX':
            return f"{symbol_clean}-USDT-SWAP"
        elif exchange_name == 'Bitget':
            return f"{symbol_clean}/USDT"
        return f"{symbol_clean}/USDT"
    
    def get_aggregated_price(self, symbol):
        prices = []
        volumes = []
        for ex in self.exchanges:
            try:
                sym = self.format_symbol(ex['name'], symbol)
                ticker = ex['exchange'].fetch_ticker(sym)
                prices.append(ticker['last'])
                volumes.append(ticker.get('quoteVolume', 0))
            except:
                continue
        if not prices:
            return None
        total_volume = sum(volumes)
        if total_volume > 0:
            return sum(p * v for p, v in zip(prices, volumes)) / total_volume
        return sum(prices) / len(prices)
    
    def get_aggregated_ohlcv(self, symbol, timeframe='1h', limit=150):
        all_dfs = []
        for ex in self.exchanges:
            try:
                sym = self.format_symbol(ex['name'], symbol)
                ohlcv = ex['exchange'].fetch_ohlcv(sym, timeframe, limit=limit)
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                all_dfs.append(df)
            except:
                continue
        if not all_dfs:
            return None
        for df in all_dfs:
            df.set_index('timestamp', inplace=True)
        common_index = all_dfs[0].index
        for df in all_dfs[1:]:
            common_index = common_index.intersection(df.index)
        agg_df = pd.DataFrame(index=common_index)
        agg_df['close'] = np.mean([df.loc[common_index, 'close'].values for df in all_dfs], axis=0)
        agg_df['volume'] = np.sum([df.loc[common_index, 'volume'].values for df in all_dfs], axis=0)
        agg_df['high'] = np.mean([df.loc[common_index, 'high'].values for df in all_dfs], axis=0)
        agg_df['low'] = np.mean([df.loc[common_index, 'low'].values for df in all_dfs], axis=0)
        agg_df['open'] = np.mean([df.loc[common_index, 'open'].values for df in all_dfs], axis=0)
        agg_df.reset_index(inplace=True)
        return agg_df

aggregator = MultiExchangeAggregator()

# ==================== FOOTPRINT (DELTA) ====================
def get_delta(symbol, minutes=5):
    try:
        exchange = ccxt.bybit({'enableRateLimit': True})
        sym = f"{symbol}USDT"
        trades = exchange.fetch_trades(sym, limit=200)
        
        now = datetime.now().timestamp() * 1000
        cutoff = now - (minutes * 60 * 1000)
        
        buy_volume = 0
        sell_volume = 0
        
        for trade in trades:
            if trade['timestamp'] >= cutoff:
                if trade['side'] == 'buy':
                    buy_volume += trade['amount']
                else:
                    sell_volume += trade['amount']
        
        delta = buy_volume - sell_volume
        total = buy_volume + sell_volume
        buy_pct = (buy_volume / total * 100) if total > 0 else 50
        
        return {
            'delta': delta,
            'buy_volume': buy_volume,
            'sell_volume': sell_volume,
            'buy_pct': round(buy_pct, 1),
            'dominant': 'BUYERS' if delta > 0 else 'SELLERS' if delta < 0 else 'NEUTRAL'
        }
    except Exception as e:
        return None

# ==================== SMC ИНДИКАТОРЫ ====================
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

def find_order_blocks(df):
    bullish_ob = np.zeros(len(df))
    bearish_ob = np.zeros(len(df))
    ob_high = np.zeros(len(df))
    ob_low = np.zeros(len(df))
    
    for i in range(5, len(df) - 1):
        avg_volume = df['volume'].iloc[i-5:i].mean()
        if df['close'].iloc[i] > df['close'].iloc[i-1] * 1.01 and df['volume'].iloc[i] > avg_volume * 1.5:
            ob_high_val = df['high'].iloc[i-1]
            ob_low_val = df['low'].iloc[i-1]
            for j in range(i, min(i + 20, len(df))):
                bullish_ob[j] = 1
                ob_high[j] = ob_high_val
                ob_low[j] = ob_low_val
        elif df['close'].iloc[i] < df['close'].iloc[i-1] * 0.99 and df['volume'].iloc[i] > avg_volume * 1.5:
            ob_high_val = df['high'].iloc[i-1]
            ob_low_val = df['low'].iloc[i-1]
            for j in range(i, min(i + 20, len(df))):
                bearish_ob[j] = 1
                ob_high[j] = ob_high_val
                ob_low[j] = ob_low_val
    return bullish_ob, bearish_ob, ob_high, ob_low

def calculate_volume_profile(df, bars=50):
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

# ==================== ГЕНЕРАЦИЯ СИГНАЛА ====================
def get_analysis(symbol, timeframe='1h'):
    try:
        df = aggregator.get_aggregated_ohlcv(symbol, timeframe, 150)
        if df is None:
            return None
        
        current_price = df['close'].iloc[-1]
        support = df['low'].iloc[-20:].min()
        resistance = df['high'].iloc[-20:].max()
        poc = calculate_volume_profile(df)
        
        rsi = calculate_rsi(df['close'].values)
        current_rsi = rsi[-1] if len(rsi) > 0 else 50
        
        bullish_ob, bearish_ob, ob_high, ob_low = find_order_blocks(df)
        
        score = 0
        signal_type = None
        reasons = []
        
        if bullish_ob[-1] == 1:
            score += 30
            signal_type = 'LONG'
            reasons.append(f"🔵 Бычий OB: ${ob_low[-1]:.0f}-${ob_high[-1]:.0f}")
        if bearish_ob[-1] == 1:
            score += 30
            signal_type = 'SHORT'
            reasons.append(f"🔴 Медвежий OB: ${ob_low[-1]:.0f}-${ob_high[-1]:.0f}")
        
        if current_rsi < RSI_LOW:
            score += 15
            if not signal_type: signal_type = 'LONG'
            reasons.append(f"📊 RSI: {current_rsi:.1f} (перепроданность)")
        elif current_rsi > RSI_HIGH:
            score += 15
            if not signal_type: signal_type = 'SHORT'
            reasons.append(f"📊 RSI: {current_rsi:.1f} (перекупленность)")
        
        if current_price <= support * 1.01 and not signal_type:
            signal_type = 'LONG'
            score += 10
            reasons.append("📊 Цена у поддержки")
        elif current_price >= resistance * 0.99 and not signal_type:
            signal_type = 'SHORT'
            score += 10
            reasons.append("📊 Цена у сопротивления")
        
        confidence = min(100, score)
        
        signal = None
        if signal_type and confidence >= 60:
            entry = current_price
            if signal_type == 'LONG':
                sl = entry * 0.985
                tp = entry * 1.03
            else:
                sl = entry * 1.015
                tp = entry * 0.97
            
            signal = {
                'signal': signal_type,
                'entry': entry,
                'sl': sl,
                'tp': tp,
                'confidence': confidence,
                'reasons': reasons
            }
        
        return {
            'price': current_price,
            'signal': signal,
            'support': support,
            'resistance': resistance,
            'poc': poc,
            'rsi': current_rsi,
            'df': df,
            'exchange': 'Multi-Exchange (4 биржи)',
            'bullish_ob': bullish_ob,
            'bearish_ob': bearish_ob,
            'ob_high': ob_high,
            'ob_low': ob_low
        }
    except Exception as e:
        print(f"Error for {symbol}: {e}")
        return None

# ==================== МУЛЬТИТАЙМФРЕЙМ ====================
def get_mtf_confirmation(symbol):
    timeframes = ['15m', '1h', '4h']
    results = {}
    
    for tf in timeframes:
        analysis = get_analysis(symbol, tf)
        if analysis and analysis.get('signal'):
            results[tf] = analysis['signal']['signal']
        else:
            results[tf] = 'NEUTRAL'
    
    signals = [v for v in results.values() if v != 'NEUTRAL']
    if len(signals) >= 2 and all(s == signals[0] for s in signals):
        return {
            'consensus': signals[0],
            'strength': 'STRONG',
            'details': results
        }
    elif len(signals) >= 1:
        return {
            'consensus': signals[0],
            'strength': 'WEAK',
            'details': results
        }
    else:
        return {
            'consensus': 'NEUTRAL',
            'strength': 'NONE',
            'details': results
        }

# ==================== ГРАФИК ====================
def make_chart(symbol, analysis):
    if not analysis or analysis.get('df') is None:
        return None
    
    df = analysis['df'].tail(60)
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), gridspec_kw={'height_ratios': [3, 1]})
    dates = df['timestamp']
    
    for i, row in df.iterrows():
        color = '#00ff88' if row['close'] >= row['open'] else '#ff4444'
        ax1.plot([row['timestamp'], row['timestamp']], [row['low'], row['high']], color=color, linewidth=1)
        ax1.add_patch(Rectangle(
            (row['timestamp'] - pd.Timedelta(minutes=30), min(row['open'], row['close'])),
            pd.Timedelta(minutes=60), abs(row['close'] - row['open']),
            facecolor=color, alpha=0.7, linewidth=0
        ))
    
    for i in range(len(df)):
        idx = len(analysis['df']) - 60 + i
        if idx < len(analysis.get('bullish_ob', [])) and analysis['bullish_ob'][idx] == 1:
            ob_h = analysis['ob_high'][idx]
            ob_l = analysis['ob_low'][idx]
            if ob_h > 0 and ob_l > 0:
                ax1.axhspan(ob_l, ob_h, alpha=0.2, color='green')
                ax1.text(dates.iloc[i], ob_h, 'BUY OB', color='green', fontsize=8, ha='right')
        if idx < len(analysis.get('bearish_ob', [])) and analysis['bearish_ob'][idx] == 1:
            ob_h = analysis['ob_high'][idx]
            ob_l = analysis['ob_low'][idx]
            if ob_h > 0 and ob_l > 0:
                ax1.axhspan(ob_l, ob_h, alpha=0.2, color='red')
                ax1.text(dates.iloc[i], ob_h, 'SELL OB', color='red', fontsize=8, ha='right')
    
    current_price = df['close'].iloc[-1]
    ax1.axhline(y=current_price, color='yellow', linestyle='-', linewidth=1.5, label=f'Price: ${current_price:.2f}')
    ax1.axhline(y=analysis['support'], color='cyan', linestyle='--', linewidth=1, label=f'Support: ${analysis["support"]:.2f}')
    ax1.axhline(y=analysis['resistance'], color='orange', linestyle='--', linewidth=1, label=f'Resistance: ${analysis["resistance"]:.2f}')
    if analysis.get('poc'):
        ax1.axhline(y=analysis['poc'], color='yellow', linestyle=':', linewidth=1, alpha=0.5, label=f'POC: ${analysis["poc"]:.2f}')
    
    signal = analysis.get('signal')
    if signal:
        color = 'green' if signal['signal'] == 'LONG' else 'red'
        ax1.axhline(y=signal['entry'], color=color, linestyle='-', linewidth=2, label=f'Entry: ${signal["entry"]:.2f}')
        ax1.axhline(y=signal['sl'], color='red', linestyle='--', linewidth=1.5, label=f'SL: ${signal["sl"]:.2f}')
        ax1.axhline(y=signal['tp'], color='lime', linestyle='--', linewidth=1.5, label=f'TP: ${signal["tp"]:.2f}')
        last_date = dates.iloc[-1]
        ax1.annotate('ВХОД', xy=(last_date, signal['entry']), xytext=(last_date, signal['entry'] * 1.02),
                    arrowprops=dict(arrowstyle='->', color=color, lw=2), fontsize=10, fontweight='bold', color=color)
    
    colors_vol = ['#00ff88' if close >= open else '#ff4444' for close, open in zip(df['close'], df['open'])]
    ax2.bar(dates, df['volume'], color=colors_vol, alpha=0.7, width=0.8)
    ax2.set_ylabel('Volume', color='white')
    ax2.grid(True, alpha=0.2)
    
    title = f'{symbol} | SMC Analysis'
    if signal:
        title += f' | {signal["signal"]} СИГНАЛ ({signal["confidence"]}%)'
    ax1.set_title(title, fontsize=14, fontweight='bold', color='white')
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

# ==================== АВТОУВЕДОМЛЕНИЯ ====================
last_signals = {}

def check_and_notify():
    settings = get_global_settings()
    if not settings.get('notifications_enabled', True):
        return
    
    watchlist = get_global_watchlist()
    chat_ids = get_all_chat_ids()
    
    for sym in watchlist:
        analysis = get_analysis(sym)
        if analysis and analysis.get('signal'):
            signal = analysis['signal']
            signal_key = f"{sym}_{signal['signal']}_{int(signal['entry'])}"
            
            if signal_key not in last_signals:
                last_signals[signal_key] = time.time()
                
                msg = format_signal(sym, analysis)
                for chat_id in chat_ids:
                    send_message(chat_id, msg)
    
    current_time = time.time()
    for key in list(last_signals.keys()):
        if current_time - last_signals[key] > 3600:
            del last_signals[key]

def get_all_chat_ids():
    chat_ids = []
    for filename in os.listdir('data'):
        if filename.startswith('user_') and filename.endswith('.json'):
            chat_id = int(filename.replace('user_', '').replace('.json', ''))
            chat_ids.append(chat_id)
    return chat_ids if chat_ids else []

def start_auto_notifications():
    def notification_loop():
        print("🔄 Фоновые уведомления запущены")
        while True:
            try:
                check_and_notify()
                time.sleep(60)
            except Exception as e:
                print(f"Ошибка: {e}")
                time.sleep(60)
    
    thread = threading.Thread(target=notification_loop, daemon=True)
    thread.start()

# ==================== TELEGRAM ====================
def send_message(chat_id, text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}, timeout=10)
    except:
        pass

def send_photo(chat_id, photo_buf, caption=""):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
        files = {'photo': ('chart.png', photo_buf, 'image/png')}
        data = {'chat_id': chat_id, 'caption': caption, 'parse_mode': 'Markdown'}
        requests.post(url, files=files, data=data, timeout=10)
    except:
        pass

def format_signal(symbol, analysis):
    if not analysis:
        return f"❌ Ошибка данных для {symbol}"
    
    signal = analysis.get('signal')
    price = analysis['price']
    
    if signal:
        emoji = "📈" if signal['signal'] == 'LONG' else "📉"
        msg = f"""{emoji} *{signal['signal']} СИГНАЛ* | {symbol}

💰 Цена: ${price:.2f}
🎯 Уверенность: {signal['confidence']}%

🚪 Вход: ${signal['entry']:.2f}
🛑 SL: ${signal['sl']:.2f}
🎯 TP: ${signal['tp']:.2f}

📊 *Причины:*\n"""
        for r in signal['reasons']:
            msg += f"• {r}\n"
        msg += f"\n📊 RSI: {analysis['rsi']:.1f}"
        if analysis.get('poc'):
            msg += f"\n🟡 POC: ${analysis['poc']:.2f}"
        msg += f"\n🏦 *Биржа:* {analysis['exchange']}"
        return msg
    else:
        return f"""⏳ *НЕТ СИГНАЛА* | {symbol}

💰 Цена: ${price:.2f}
🟢 Поддержка: ${analysis['support']:.2f}
🔴 Сопротивление: ${analysis['resistance']:.2f}
📊 RSI: {analysis['rsi']:.1f}
{f"🟡 POC: ${analysis['poc']:.2f}" if analysis.get('poc') else ""}

💡 Рекомендация: наблюдение
🏦 *Биржа:* {analysis['exchange']}"""

def save_chat_id(chat_id):
    file_path = f'data/user_{chat_id}.json'
    if not os.path.exists(file_path):
        with open(file_path, 'w') as f:
            json.dump({'chat_id': chat_id, 'first_seen': datetime.now().isoformat()}, f)

def handle_message(chat_id, text):
    print(f"Message: {text}")
    save_chat_id(chat_id)
    settings = get_global_settings()
    watchlist = get_global_watchlist()
    
    if text == "/start":
        msg = f"""🤖 *SMC CRYPTO BOT* — ПОЛНАЯ ВЕРСИЯ

📊 *Методология:* SMC/ICT + Order Blocks + RSI + POC
🏦 *Биржи:* KuCoin + Gate.io + OKX + Bitget
🎯 *Стили:* SCALP, DAY, SWING
🔔 *Уведомления:* {'ВКЛ' if settings.get('notifications_enabled') else 'ВЫКЛ'}

*Команды:*
/add BTC,ETH,SOL — добавить монеты
/remove DOGE — удалить
/list — список
/signals — сигналы
/all_signals — сигналы по всем стилям
/chart BTC — график
/analyze PEPE — анализ
/footprint BTC — дельта покупок/продаж
/confirm BTC — мультитаймфрейм
/session — текущая сессия
/take LONG BTC 65000 100 5 — открыть сделку
/close 123 — закрыть
/trades — активные сделки
/history — история
/stats — статистика
/pnl — P&L
/reset_trades — сброс
/style scalp|day|swing — стиль
/notifications_on — уведомления вкл
/notifications_off — уведомления выкл
/status — статус
/help — помощь"""
        send_message(chat_id, msg)
    
    elif text == "/session":
        session = get_current_session()
        session_info = SESSIONS[session]
        
        msg = f"""🕐 *ТОРГОВЫЕ СЕССИИ*

{session_info['color']} *СЕЙЧАС:* {session_info['name']}
📊 *Волатильность:* {session_info['volatility']}

📅 *Расписание (МСК):*
• 🟡 Азиатская: 02:00-10:00
• 🟢 Лондонская: 10:00-16:00 🔥
• 🔴 Нью-Йоркская: 16:00-22:00 🔥🔥
• ⚪ Тихая: 22:00-02:00

💡 *Лучшее время:* 10:00-22:00"""
        send_message(chat_id, msg)
    
    elif text.startswith("/footprint"):
        parts = text.split()
        sym = parts[1].upper() if len(parts) > 1 else 'BTC'
        
        fp = get_delta(sym)
        if fp:
            emoji = "📈" if fp['dominant'] == 'BUYERS' else "📉" if fp['dominant'] == 'SELLERS' else "⚪"
            msg = f"""📡 *FOOTPRINT {sym}* {emoji}

💰 Delta: {fp['delta']:+.0f}
📊 Buy Volume: {fp['buy_volume']:.0f}
📉 Sell Volume: {fp['sell_volume']:.0f}
🎯 Buy %: {fp['buy_pct']}%
👑 Доминируют: {fp['dominant']}

💡 *Интерпретация:*
• Delta > 0 → покупатели активнее
• Delta < 0 → продавцы активнее
• |Delta| > 1000 → сильный дисбаланс"""
            send_message(chat_id, msg)
        else:
            send_message(chat_id, f"❌ Нет данных для {sym}")
    
    elif text.startswith("/confirm"):
        parts = text.split()
        sym = parts[1].upper() if len(parts) > 1 else 'BTC'
        
        send_message(chat_id, f"🔄 *Мультитаймфрейм анализ {sym}...*")
        
        mtf = get_mtf_confirmation(sym)
        
        msg = f"""🔄 *МУЛЬТИТАЙМФРЕЙМ | {sym}*

📊 *15m:* {mtf['details']['15m']}
📊 *1h:* {mtf['details']['1h']}
📊 *4h:* {mtf['details']['4h']}

🎯 *Консенсус:* {mtf['consensus']}
💪 *Сила:* {mtf['strength']}

"""
        if mtf['strength'] == 'STRONG':
            msg += "✅ *СИЛЬНЫЙ СИГНАЛ* — все таймфреймы согласны!"
        elif mtf['strength'] == 'WEAK':
            msg += "⚠️ *СЛАБЫЙ СИГНАЛ* — таймфреймы расходятся"
        else:
            msg += "⏳ *НЕТ СИГНАЛА* — ждите"
        
        send_message(chat_id, msg)
    
    elif text.startswith("/add"):
        args = text.replace("/add", "").strip().upper().replace(",", " ").split()
        added = []
        for arg in args:
            if arg not in watchlist:
                watchlist.append(arg)
                added.append(arg)
        save_global_watchlist(watchlist)
        send_message(chat_id, f"✅ Добавлено: {', '.join(added)}\n📋 Всего: {len(watchlist)}")
    
    elif text.startswith("/remove"):
        args = text.replace("/remove", "").strip().upper()
        if args and args in watchlist:
            watchlist.remove(args)
            save_global_watchlist(watchlist)
            send_message(chat_id, f"❌ Удалено: {args}")
        else:
            send_message(chat_id, f"⚠️ {args} не найдена")
    
    elif text == "/list":
        if not watchlist:
            send_message(chat_id, "📭 Список пуст")
        else:
            msg = "📋 *МОИ МОНЕТЫ*\n\n"
            for s in watchlist:
                msg += f"• {s}\n"
            send_message(chat_id, msg)
    
    elif text == "/signals":
        if not watchlist:
            send_message(chat_id, "📭 Нет монет")
            return
        msg = f"🚨 *СИГНАЛЫ* ({settings['style'].upper()})\n\n"
        for sym in watchlist:
            analysis = get_analysis(sym)
            msg += format_signal(sym, analysis) + "\n\n"
        send_message(chat_id, msg[:4000])
    
    elif text == "/all_signals":
        settings['style'] = 'day'
        handle_message(chat_id, "/signals")
    
    elif text.startswith("/chart"):
        parts = text.split()
        sym = parts[1].upper() if len(parts) > 1 else 'BTC'
        send_message(chat_id, f"📊 *График {sym}...*")
        analysis = get_analysis(sym)
        if analysis:
            chart = make_chart(sym, analysis)
            if chart:
                caption = f"📈 *{sym}* | Цена: ${analysis['price']:.2f}"
                if analysis.get('signal'):
                    caption += f"\n🎯 Сигнал: {analysis['signal']['signal']} | Увер: {analysis['signal']['confidence']}%"
                send_photo(chat_id, chart, caption)
            else:
                send_message(chat_id, "❌ Ошибка графика")
        else:
            send_message(chat_id, f"❌ Нет данных для {sym}")
    
    elif text.startswith("/analyze"):
        parts = text.split()
        sym = parts[1].upper() if len(parts) > 1 else 'BTC'
        analysis = get_analysis(sym)
        if analysis:
            send_message(chat_id, format_signal(sym, analysis))
        else:
            send_message(chat_id, f"❌ Нет данных для {sym}")
    
    elif text.startswith("/take"):
        parts = text.split()
        if len(parts) < 5:
            send_message(chat_id, "📝 `/take LONG BTC 65000 100 5`")
            return
        side = parts[1].upper()
        symbol = parts[2].upper()
        try:
            entry = float(parts[3])
            size = float(parts[4])
            leverage = float(parts[5])
        except:
            send_message(chat_id, "❌ Ошибка в параметрах")
            return
        trade_id = trade_manager.add_trade(symbol, side, entry, leverage, size)
        send_message(chat_id, f"✅ Сделка #{trade_id}: {side} {symbol} @ ${entry:.2f}, {size} USDT, x{leverage}")
    
    elif text.startswith("/close"):
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id, "📝 `/close 123`")
            return
        try:
            trade_id = int(parts[1])
            exit_price = float(parts[2]) if len(parts) > 2 else None
            active = trade_manager.get_active_trades()
            if str(trade_id) not in active:
                send_message(chat_id, f"❌ Сделка #{trade_id} не найдена")
                return
            trade = active[str(trade_id)]
            if not exit_price:
                exit_price = trade['entry'] * 1.02 if trade['side'] == 'LONG' else trade['entry'] * 0.98
            closed = trade_manager.close_trade(trade_id, exit_price)
            if closed:
                emoji = "✅" if closed['pnl_pct'] > 0 else "❌"
                send_message(chat_id, f"{emoji} Сделка #{trade_id} закрыта: P&L {closed['pnl_pct']:+.2f}%")
        except:
            send_message(chat_id, "❌ Ошибка")
    
    elif text == "/trades":
        active = trade_manager.get_active_trades()
        if not active:
            send_message(chat_id, "📭 Нет активных сделок")
            return
        msg = "📊 *АКТИВНЫЕ СДЕЛКИ*\n\n"
        for tid, trade in active.items():
            msg += f"🆔 *{tid}* | {trade['symbol']} | {trade['side']}\n   💰 Вход: ${trade['entry']:.2f}\n   ⚡ Плечо: x{trade['leverage']}\n\n"
        send_message(chat_id, msg)
    
    elif text == "/history":
        history = trade_manager.get_history(10)
        if not history:
            send_message(chat_id, "📭 Нет истории")
            return
        msg = "📜 *ПОСЛЕДНИЕ СДЕЛКИ*\n\n"
        for trade in reversed(history):
            emoji = "✅" if trade['pnl_pct'] > 0 else "❌"
            msg += f"{emoji} *{trade['side']} {trade['symbol']}* | P&L: {trade['pnl_pct']:+.2f}%\n"
        send_message(chat_id, msg)
    
    elif text == "/stats":
        stats = trade_manager.get_stats()
        if stats['total_trades'] == 0:
            send_message(chat_id, "📭 Нет данных")
            return
        msg = f"""📊 *СТАТИСТИКА*

📈 Сделок: {stats['total_trades']}
✅ Прибыльных: {stats['wins']}
❌ Убыточных: {stats['losses']}
🎯 Win Rate: {stats['win_rate']}%
💰 Общая прибыль: {stats['total_pnl_pct']:+.2f}%
📊 Profit Factor: {stats['profit_factor']}"""
        send_message(chat_id, msg)
    
    elif text == "/pnl":
        active = trade_manager.get_active_trades()
        if not active:
            send_message(chat_id, "📭 Нет открытых сделок")
            return
        total = 0
        msg = "📊 *ТЕКУЩИЙ P&L*\n\n"
        for tid, trade in active.items():
            current = get_analysis(trade['symbol'])['price'] if get_analysis(trade['symbol']) else trade['entry']
            if trade['side'] == 'LONG':
                pnl = (current - trade['entry']) / trade['entry'] * 100 * trade['leverage']
            else:
                pnl = (trade['entry'] - current) / trade['entry'] * 100 * trade['leverage']
            total += pnl
            emoji = "📈" if pnl > 0 else "📉"
            msg += f"{emoji} *{trade['symbol']}* (ID: {tid}) | P&L: {pnl:+.2f}%\n"
        msg += f"\n💰 *ИТОГО:* {total:+.2f}%"
        send_message(chat_id, msg)
    
    elif text == "/reset_trades":
        trade_manager.reset_all_trades()
        send_message(chat_id, "🗑️ Все сделки сброшены")
    
    elif text.startswith("/style"):
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id, "📝 `/style day`")
            return
        new_style = parts[1].lower()
        if new_style in ['scalp', 'day', 'swing']:
            settings['style'] = new_style
            save_global_settings(settings)
            send_message(chat_id, f"✅ Стиль: {new_style.upper()}")
    
    elif text == "/notifications_on":
        settings['notifications_enabled'] = True
        save_global_settings(settings)
        send_message(chat_id, "🔔 Уведомления ВКЛЮЧЕНЫ")
    
    elif text == "/notifications_off":
        settings['notifications_enabled'] = False
        save_global_settings(settings)
        send_message(chat_id, "🔕 Уведомления ВЫКЛЮЧЕНЫ")
    
    elif text == "/status":
        msg = f"""✅ *СТАТУС*

🏦 Биржи: KuCoin + Gate.io + OKX + Bitget
🎯 Стиль: {settings['style'].upper()}
📋 Монет: {len(watchlist)}
🔄 Активных сделок: {len(trade_manager.get_active_trades())}
🔔 Уведомления: {'ВКЛ' if settings.get('notifications_enabled') else 'ВЫКЛ'}"""
        send_message(chat_id, msg)
    
    elif text == "/help":
        msg = """📋 *ВСЕ КОМАНДЫ*

📌 *Основные:*
/add BTC — добавить
/remove DOGE — удалить
/list — список
/signals — сигналы
/all_signals — сигналы по всем стилям
/chart BTC — график
/analyze PEPE — анализ

📌 *Новые функции:*
/footprint BTC — дельта (покупки/продажи)
/confirm BTC — мультитаймфрейм
/session — сессии

📌 *Сделки:*
/take LONG BTC 65000 100 5 — открыть
/close 123 — закрыть
/trades — активные сделки
/history — история
/stats — статистика
/pnl — P&L
/reset_trades — сброс

📌 *Настройки:*
/style day — стиль
/notifications_on — уведомления вкл
/notifications_off — уведомления выкл
/status — статус
/help — помощь"""
        send_message(chat_id, msg)
    
    else:
        send_message(chat_id, f"⚠️ Неизвестно: {text}\n/help")

# ==================== ЗАПУСК ====================
print("=" * 60)
print("🚀 SMC FULL BOT — РАСШИРЕННАЯ ВЕРСИЯ")
print("📊 Новые функции: Footprint, Мультитаймфрейм")
print("=" * 60)

start_auto_notifications()

print("✅ Бот запущен")
print("=" * 60)

while True:
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        response = requests.get(url, params={"offset": LAST_UPDATE_ID + 1, "timeout": 30})
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
