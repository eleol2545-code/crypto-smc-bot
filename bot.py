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

TELEGRAM_TOKEN = "8645396589:AAHIceq907-38mvWJfa9BRaQWsrzC86ivNU"
LAST_UPDATE_ID = 0

os.makedirs('data', exist_ok=True)
os.makedirs('data/footprint', exist_ok=True)

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

# ==================== КЛАСТЕРНЫЙ АНАЛИЗ (FOOTPRINT) ====================

class FootprintAnalyzer:
    def __init__(self, symbol='BTCUSDT'):
        self.symbol = symbol
        self.trades = []
        self.delta = 0
        self.delta_history = []
        self.price_clusters = {}
        self.last_poc = None
        self.buy_volume = 0
        self.sell_volume = 0
        self.running = False
        self.ws_thread = None
    
    def start(self):
        self.running = True
        self.ws_thread = threading.Thread(target=self._run_websocket, daemon=True)
        self.ws_thread.start()
        print(f"📡 Footprint WebSocket запущен для {self.symbol}")
    
    def _run_websocket(self):
        asyncio.run(self._connect_websocket())
    
    async def _connect_websocket(self):
        url = "wss://stream.bybit.com/v5/public/linear"
        try:
            async with websockets.connect(url) as ws:
                subscribe_msg = {
                    "op": "subscribe",
                    "args": [f"publicTrade.{self.symbol}"]
                }
                await ws.send(json.dumps(subscribe_msg))
                print(f"✅ WebSocket подключен для {self.symbol}")
                async for message in ws:
                    data = json.loads(message)
                    if 'topic' in data and 'publicTrade' in data['topic']:
                        await self._process_trades(data['data'])
        except Exception as e:
            print(f"❌ WebSocket ошибка для {self.symbol}: {e}")
            time.sleep(5)
            if self.running:
                await self._connect_websocket()
    
    async def _process_trades(self, trades):
        for trade in trades:
            price = float(trade['p'])
            volume = float(trade['v'])
            side = 'BUY' if trade['S'] == 'Buy' else 'SELL'
            
            if side == 'BUY':
                self.delta += volume
                self.buy_volume += volume
            else:
                self.delta -= volume
                self.sell_volume += volume
            
            self.trades.append({'time': trade['T'], 'price': price, 'volume': volume, 'side': side})
            if len(self.trades) > 10000:
                self.trades = self.trades[-5000:]
            
            price_level = round(price, 2) if price > 1 else round(price, 6)
            if price_level not in self.price_clusters:
                self.price_clusters[price_level] = {'buy': 0, 'sell': 0, 'total': 0}
            if side == 'BUY':
                self.price_clusters[price_level]['buy'] += volume
            else:
                self.price_clusters[price_level]['sell'] += volume
            self.price_clusters[price_level]['total'] += volume
            
            if len(self.trades) % 100 == 0:
                self._update_poc()
            
            self.delta_history.append({'time': datetime.now().isoformat(), 'delta': self.delta, 'price': price})
            if len(self.delta_history) > 1000:
                self.delta_history = self.delta_history[-500:]
    
    def _update_poc(self):
        if not self.price_clusters:
            return
        max_volume = 0
        poc_price = None
        for price, data in self.price_clusters.items():
            if data['total'] > max_volume:
                max_volume = data['total']
                poc_price = price
        self.last_poc = poc_price
    
    def get_footprint(self):
        return {
            'delta': self.delta,
            'buy_volume': self.buy_volume,
            'sell_volume': self.sell_volume,
            'poc': self.last_poc,
            'trades_count': len(self.trades),
            'dominant': 'BUYERS' if self.delta > 0 else 'SELLERS' if self.delta < 0 else 'NEUTRAL'
        }
    
    def stop(self):
        self.running = False

# ==================== МЕНЕДЖЕР FOOTPRINT ====================

class FootprintManager:
    def __init__(self):
        self.analyzers = {}
        self.active_symbols = set()
    
    def start_for_symbol(self, symbol):
        symbol_clean = symbol.upper().replace('USDT', '').replace('/', '')
        if symbol_clean in self.active_symbols:
            return
        ws_symbol = f"{symbol_clean}USDT"
        try:
            analyzer = FootprintAnalyzer(ws_symbol)
            analyzer.start()
            self.analyzers[symbol_clean] = analyzer
            self.active_symbols.add(symbol_clean)
            print(f"✅ Footprint запущен для {symbol_clean}")
        except Exception as e:
            print(f"❌ Ошибка запуска Footprint для {symbol_clean}: {e}")
    
    def stop_for_symbol(self, symbol):
        symbol_clean = symbol.upper().replace('USDT', '').replace('/', '')
        if symbol_clean in self.analyzers:
            self.analyzers[symbol_clean].stop()
            del self.analyzers[symbol_clean]
            self.active_symbols.discard(symbol_clean)
            print(f"⏸️ Footprint остановлен для {symbol_clean}")
    
    def get_footprint(self, symbol):
        symbol_clean = symbol.upper().replace('USDT', '').replace('/', '')
        if symbol_clean in self.analyzers:
            return self.analyzers[symbol_clean].get_footprint()
        return None
    
    def update_from_watchlist(self, watchlist):
        watchlist_clean = {s.upper().replace('USDT', '').replace('/', '') for s in watchlist}
        for sym in watchlist_clean:
            if sym not in self.active_symbols and len(self.active_symbols) < 10:
                self.start_for_symbol(sym)
        for sym in list(self.active_symbols):
            if sym not in watchlist_clean:
                self.stop_for_symbol(sym)

footprint_manager = FootprintManager()

# ==================== КОНФИГУРАЦИЯ БИРЖ ====================

EXCHANGES = {
    'bybit': {'name': 'Bybit', 'class': ccxt.bybit, 'params': {'options': {'defaultType': 'linear'}}, 'format': 'BTCUSDT', 'active': True},
    'kucoin': {'name': 'KuCoin', 'class': ccxt.kucoin, 'params': {}, 'format': 'BTC/USDT', 'active': True},
    'gate': {'name': 'Gate.io', 'class': ccxt.gateio, 'params': {'options': {'defaultType': 'swap'}}, 'format': 'BTC_USDT', 'active': True},
}

class SmartExchangeRouter:
    def __init__(self):
        self.exchanges = {}
        self.current_exchange = None
        self.current_name = None
        self.current_format = None
        self.initialize_exchanges()
    
    def initialize_exchanges(self):
        for name, config in EXCHANGES.items():
            if config['active']:
                try:
                    self.exchanges[name] = config['class'](config['params'])
                    self.exchanges[name].enableRateLimit = True
                    print(f"✅ Инициализирована {config['name']}")
                except Exception as e:
                    print(f"❌ Ошибка {config['name']}: {e}")
                    config['active'] = False
        for name, config in EXCHANGES.items():
            if config['active']:
                self.current_exchange = self.exchanges[name]
                self.current_name = config['name']
                self.current_format = config['format']
                break
    
    def format_symbol(self, symbol):
        symbol = symbol.upper().replace('USDT', '').replace('/', '')
        if self.current_format == 'BTCUSDT':
            return f"{symbol}USDT"
        elif self.current_format == 'BTC/USDT':
            return f"{symbol}/USDT"
        elif self.current_format == 'BTC_USDT':
            return f"{symbol}_USDT"
        return f"{symbol}/USDT"
    
    def fetch_ohlcv(self, symbol, timeframe='1h', limit=150):
        try:
            formatted = self.format_symbol(symbol)
            return self.current_exchange.fetch_ohlcv(formatted, timeframe, limit=limit)
        except Exception as e:
            print(f"❌ Ошибка на {self.current_name}: {e}")
            for name, config in EXCHANGES.items():
                if config['active'] and name != self.current_name.lower():
                    try:
                        self.current_exchange = self.exchanges[name]
                        self.current_name = config['name']
                        self.current_format = config['format']
                        print(f"🔄 Переключено на {self.current_name}")
                        return self.fetch_ohlcv(symbol, timeframe, limit)
                    except:
                        continue
            return None

router = SmartExchangeRouter()

# ==================== ХРАНИЛИЩЕ ПОЛЬЗОВАТЕЛЕЙ ====================

def get_user_data(chat_id):
    file_path = f'data/user_{chat_id}.json'
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            return json.load(f)
    else:
        user_data = {'watchlist': ['BTC', 'ETH', 'SOL'], 'style': 'day', 'timeframe': '1h', 'min_confidence': 70}
        with open(file_path, 'w') as f:
            json.dump(user_data, f)
        return user_data

def save_user_data(chat_id, data):
    with open(f'data/user_{chat_id}.json', 'w') as f:
        json.dump(data, f)

# ==================== SMC АНАЛИЗАТОР ====================

def calculate_indicators(df):
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    ema_fast = df['close'].ewm(span=12, adjust=False).mean()
    ema_slow = df['close'].ewm(span=26, adjust=False).mean()
    df['macd_line'] = ema_fast - ema_slow
    df['macd_signal'] = df['macd_line'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd_line'] - df['macd_signal']
    
    df['bb_middle'] = df['close'].rolling(window=20).mean()
    bb_std = df['close'].rolling(window=20).std()
    df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
    df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
    
    low_min = df['low'].rolling(window=14).min()
    high_max = df['high'].rolling(window=14).max()
    df['stoch_k'] = 100 * (df['close'] - low_min) / (high_max - low_min)
    df['stoch_d'] = df['stoch_k'].rolling(window=3).mean()
    
    df['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema_21'] = df['close'].ewm(span=21, adjust=False).mean()
    df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
    
    df['typical_price'] = (df['high'] + df['low'] + df['close']) / 3
    df['vwap'] = (df['typical_price'] * df['volume']).cumsum() / df['volume'].cumsum()
    
    df['volume_sma'] = df['volume'].rolling(window=20).mean()
    df['volume_ratio'] = df['volume'] / df['volume_sma']
    return df

def find_order_blocks(df):
    df['bullish_ob'] = 0
    df['bearish_ob'] = 0
    df['ob_high'] = np.nan
    df['ob_low'] = np.nan
    
    for i in range(5, len(df) - 1):
        if (df['close'].iloc[i] > df['close'].iloc[i-1] * 1.01 and
            df['volume'].iloc[i] > df['volume'].iloc[i-5:i].mean() * 1.5):
            ob_high = df['high'].iloc[i-1]
            ob_low = df['low'].iloc[i-1]
            for j in range(i, min(i + 20, len(df))):
                if df['low'].iloc[j] <= ob_high:
                    df.loc[df.index[j], 'bullish_ob'] = 1
                    df.loc[df.index[j], 'ob_high'] = ob_high
                    df.loc[df.index[j], 'ob_low'] = ob_low
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

def generate_signal(df, style='day', min_confidence=70, footprint_data=None):
    if df is None or len(df) < 50:
        return None
    
    current = df.iloc[-1]
    params = {
        'scalp': {'sl_pct': 0.008, 'tp_pct': 0.015, 'min_conf': 65},
        'day': {'sl_pct': 0.015, 'tp_pct': 0.03, 'min_conf': 70},
        'swing': {'sl_pct': 0.025, 'tp_pct': 0.06, 'min_conf': 75}
    }
    p = params.get(style, params['day'])
    
    score = 0
    signal_type = None
    reasons = []
    
    if current['bullish_ob'] == 1:
        score += 20
        signal_type = 'LONG'
        reasons.append(f"🔵 Бычий OB: {format_price(current['ob_low'])}-{format_price(current['ob_high'])}")
    if current['bearish_ob'] == 1:
        score += 20
        signal_type = 'SHORT'
        reasons.append(f"🔴 Медвежий OB: {format_price(current['ob_low'])}-{format_price(current['ob_high'])}")
    
    if current['rsi'] < 30:
        score += 15
        if not signal_type: signal_type = 'LONG'
        reasons.append(f"📊 RSI: {current['rsi']:.1f} (перепроданность)")
    elif current['rsi'] > 70:
        score += 15
        if not signal_type: signal_type = 'SHORT'
        reasons.append(f"📊 RSI: {current['rsi']:.1f} (перекупленность)")
    
    if current['macd_hist'] > 0 and signal_type == 'LONG':
        score += 15
        reasons.append(f"📈 MACD: +{current['macd_hist']:.4f}")
    elif current['macd_hist'] < 0 and signal_type == 'SHORT':
        score += 15
        reasons.append(f"📉 MACD: {current['macd_hist']:.4f}")
    
    if current['close'] <= current['bb_lower'] * 1.005:
        score += 15
        if not signal_type: signal_type = 'LONG'
        reasons.append(f"📊 Bollinger: у нижней полосы {format_price(current['bb_lower'])}")
    elif current['close'] >= current['bb_upper'] * 0.995:
        score += 15
        if not signal_type: signal_type = 'SHORT'
        reasons.append(f"📊 Bollinger: у верхней полосы {format_price(current['bb_upper'])}")
    
    if current['stoch_k'] < 20:
        score += 15
        if not signal_type: signal_type = 'LONG'
        reasons.append(f"📊 Stochastic: %K={current['stoch_k']:.1f}")
    elif current['stoch_k'] > 80:
        score += 15
        if not signal_type: signal_type = 'SHORT'
        reasons.append(f"📊 Stochastic: %K={current['stoch_k']:.1f}")
    
    if current['volume_ratio'] > 1.5:
        score += 10
        reasons.append(f"⚡ Объем: {current['volume_ratio']:.1f}x")
    
    if footprint_data:
        if footprint_data['delta'] > 500:
            score += 15
            if signal_type == 'LONG': score += 5
            reasons.append(f"📊 Delta: +{footprint_data['delta']:.0f} (покупатели доминируют)")
        elif footprint_data['delta'] < -500:
            score += 15
            if signal_type == 'SHORT': score += 5
            reasons.append(f"📊 Delta: {footprint_data['delta']:.0f} (продавцы доминируют)")
        if footprint_data['poc']:
            poc_distance = abs(current['close'] - footprint_data['poc']) / current['close'] * 100
            if poc_distance < 1:
                score += 10
                reasons.append(f"🎯 POC: {format_price(footprint_data['poc'])} (цена у POC)")
    
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
    try:
        ohlcv = router.fetch_ohlcv(symbol, '1h', 150)
        if not ohlcv: return None
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df = calculate_indicators(df)
        df = find_order_blocks(df)
        poc = calculate_volume_profile(df)
        footprint = footprint_manager.get_footprint(symbol)
        signal = generate_signal(df, style, min_confidence, footprint)
        return {
            'price': df['close'].iloc[-1], 'signal': signal, 'poc': poc,
            'support': df['low'].iloc[-20:].min(), 'resistance': df['high'].iloc[-20:].max(),
            'exchange': router.current_name, 'footprint': footprint
        }
    except Exception as e:
        print(f"Error for {symbol}: {e}")
        return None

# ==================== TELEGRAM БОТ ====================

def send_message(chat_id, text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}, timeout=10)
    except:
        pass

def format_signal(symbol, analysis, style='day'):
    if not analysis: return f"❌ Ошибка получения данных для {symbol}"
    signal = analysis['signal']
    price = analysis['price']
    exchange = analysis.get('exchange', router.current_name)
    footprint = analysis.get('footprint')
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

📊 *Причины:*\n"""
        for r in signal['reasons']: msg += f"• {r}\n"
        if footprint:
            msg += f"\n📡 *FOOTPRINT:*\n• Delta: {'+' if footprint['delta'] > 0 else ''}{footprint['delta']:.0f}\n• Доминируют: {footprint['dominant']}\n• POC: {format_price(footprint['poc']) if footprint['poc'] else 'N/A'}\n• Сделок: {footprint['trades_count']}\n"
        if analysis['poc']: msg += f"• 🟡 POC (свечной): {format_price(analysis['poc'])}\n"
        msg += f"\n🏦 *Биржа:* {exchange}"
        return msg
    else:
        msg = f"""⏳ *НЕТ СИГНАЛА* | {symbol} | {style.upper()}

💰 Цена: {format_price(price)}
🟢 Поддержка: {format_price(analysis['support'])}
🔴 Сопротивление: {format_price(analysis['resistance'])}
📊 POC: {format_price(analysis['poc'])}"""
        if footprint:
            msg += f"\n\n📡 *FOOTPRINT:*\n• Delta: {'+' if footprint['delta'] > 0 else ''}{footprint['delta']:.0f}\n• Доминируют: {footprint['dominant']}\n• Сделок: {footprint['trades_count']}\n"
        msg += f"\n\n💡 Рекомендация: наблюдение\n🏦 *Биржа:* {exchange}"
        return msg

def handle_message(chat_id, text):
    print(f"Message from {chat_id}: {text}")
    user_data = get_user_data(chat_id)
    
    if text == "/start":
        send_message(chat_id, f"""🤖 *SMC CRYPTO BOT* — ПОЛНАЯ ВЕРСИЯ

📊 *Методология:* SMC/ICT + Order Blocks + FVG + Volume Profile
📡 *Footprint:* Delta, POC, кластеры объема (WebSocket)
📈 *Индикаторы:* RSI, MACD, Bollinger, Stochastic, VWAP, EMA
🎯 *Стили:* SCALP, DAY, SWING

🏦 *Биржи:* Bybit, KuCoin, Gate.io (автопереключение)
🔄 *Текущая биржа:* {router.current_name}

*Команды:*
/add BTC,ETH,SOL,DOGE,PEPE — добавить монеты (Footprint автоматически!)
/remove DOGE — удалить
/list — мои монеты
/signals — сигналы + Footprint
/analyze PEPE — анализ любой монеты
/scalp BTC — скальп-сигнал
/swing BTC — свинг-сигнал
/footprint BTC — Footprint данные
/footprint_list — активные Footprint
/exchange — текущая биржа
/status — статус
/help — помощь""")
    
    elif text.startswith("/add"):
        args = text.replace("/add", "").strip().upper().replace(",", " ").split()
        added = []
        for arg in args:
            if arg not in user_data['watchlist']:
                user_data['watchlist'].append(arg)
                added.append(arg)
        save_user_data(chat_id, user_data)
        footprint_manager.update_from_watchlist(user_data['watchlist'])
        send_message(chat_id, f"✅ Добавлено: {', '.join(added)}\n\n📋 Всего монет: {len(user_data['watchlist'])}\n📡 Footprint активен для {len(footprint_manager.active_symbols)} монет")
    
    elif text.startswith("/remove"):
        args = text.replace("/remove", "").strip().upper()
        if args and args in user_data['watchlist']:
            user_data['watchlist'].remove(args)
            save_user_data(chat_id, user_data)
            footprint_manager.update_from_watchlist(user_data['watchlist'])
            send_message(chat_id, f"❌ Удалено: {args}\n📡 Footprint активен для {len(footprint_manager.active_symbols)} монет")
        else:
            send_message(chat_id, f"⚠️ {args} не найдена")
    
    elif text == "/list":
        if not user_data['watchlist']:
            send_message(chat_id, "📭 Список пуст. Добавьте: `/add BTC`")
        else:
            msg = "📋 *МОИ МОНЕТЫ*\n\n"
            for s in user_data['watchlist']: msg += f"• {s}\n"
            send_message(chat_id, msg)
    
    elif text == "/signals":
        if not user_data['watchlist']:
            send_message(chat_id, "📭 Нет монет в списке")
            return
        send_message(chat_id, f"🔍 *Поиск сигналов...*\n🏦 Биржа: {router.current_name}")
        msg = f"🚨 *СИГНАЛЫ* ({user_data['style'].upper()})\n\n"
        for sym in user_data['watchlist'][:5]:
            analysis = get_full_analysis(sym, user_data['style'], user_data['min_confidence'])
            msg += format_signal(sym, analysis, user_data['style']) + "\n\n"
        send_message(chat_id, msg[:4000])
    
    elif text.startswith("/analyze"):
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id, "📝 *Пример:* `/analyze PEPE`")
            return
        symbol = parts[1].upper()
        send_message(chat_id, f"🔍 *Анализ {symbol}...*\n🏦 Биржа: {router.current_name}")
        analysis = get_full_analysis(symbol, user_data['style'], user_data['min_confidence'])
        send_message(chat_id, format_signal(symbol, analysis, user_data['style']))
    
    elif text.startswith("/scalp"):
        parts = text.split()
        symbol = parts[1].upper() if len(parts) > 1 else 'BTC'
        analysis = get_full_analysis(symbol, 'scalp', 65)
        send_message(chat_id, format_signal(symbol, analysis, 'scalp'))
    
    elif text.startswith("/swing"):
        parts = text.split()
        symbol = parts[1].upper() if len(parts) > 1 else 'BTC'
        analysis = get_full_analysis(symbol, 'swing', 75)
        send_message(chat_id, format_signal(symbol, analysis, 'swing'))
    
    elif text.startswith("/footprint"):
        parts = text.split()
        symbol = parts[1].upper() if len(parts) > 1 else 'BTC'
        fp = footprint_manager.get_footprint(symbol)
        if fp:
            try:
                ticker = router.current_exchange.fetch_ticker(router.format_symbol(symbol))
                current_price = ticker['last']
            except:
                current_price = None
            msg = f"""📡 *FOOTPRINT {symbol}*

💰 Цена: {format_price(current_price) if current_price else 'N/A'}
📊 Delta: {'+' if fp['delta'] > 0 else ''}{fp['delta']:.0f}
📈 Buy Volume: {fp['buy_volume']:.0f}
📉 Sell Volume: {fp['sell_volume']:.0f}
🎯 Доминируют: {fp['dominant']}
📍 POC: {format_price(fp['poc']) if fp['poc'] else 'N/A'}
🔄 Сделок: {fp['trades_count']}"""
            send_message(chat_id, msg)
        else:
            send_message(chat_id, f"⚠️ Footprint не активен для {symbol}\n\n💡 Добавьте {symbol} через `/add {symbol}`")
    
    elif text == "/footprint_list":
        active = list(footprint_manager.active_symbols)
        if active:
            msg = "📡 *АКТИВНЫЕ FOOTPRINT МОНЕТЫ*\n\n"
            for sym in active:
                fp = footprint_manager.get_footprint(sym)
                if fp:
                    msg += f"• {sym}: Delta {fp['delta']:+.0f} | {fp['dominant']}\n"
            send_message(chat_id, msg)
        else:
            send_message(chat_id, "📡 Нет активных Footprint монет\nДобавьте монеты через `/add`")
    
    elif text == "/exchange":
        send_message(chat_id, f"🏦 *Текущая биржа:* {router.current_name}\n\nДоступные: Bybit, KuCoin, Gate.io")
    
    elif text == "/status":
        btc = get_full_analysis('BTC', 'day')
        if btc:
            msg = f"""✅ *СТАТУС БОТА*

🏦 *Биржа:* {router.current_name}
🎯 *Ваш стиль:* {user_data['style'].upper()}
📊 *Мин. уверенность:* {user_data['min_confidence']}%
📋 *Монет:* {len(user_data['watchlist'])}
📡 *Footprint активен:* {len(footprint_manager.active_symbols)} монет

📈 *BTC:* {format_price(btc['price'])}
🟢 *Поддержка:* {format_price(btc['support'])}
🔴 *Сопротивление:* {format_price(btc['resistance'])}"""
            send_message(chat_id, msg)
        else:
            send_message(chat_id, "✅ Бот активен")
    
    elif text == "/help":
        send_message(chat_id, """📋 *ВСЕ КОМАНДЫ*

📌 *Управление монетами:*
/add BTC,DOGE,PEPE — добавить (Footprint автоматически!)
/remove DOGE — удалить
/list — мои монеты

📌 *Сигналы:*
/signals — сигналы + Footprint
/analyze PEPE — анализ любой
/scalp BTC — скальп
/swing BTC — свинг
/footprint BTC — Footprint данные
/footprint_list — активные Footprint

📌 *Другое:*
/exchange — текущая биржа
/status — статус
/help — помощь

📊 *Стили:* SCALP (0.8%/1.5%), DAY (1.5%/3%), SWING (2.5%/6%)

📡 *Footprint:* автоматически запускается для любых добавленных монет!""")
    
    else:
        send_message(chat_id, f"⚠️ Неизвестно: {text}\n/help")

# ==================== ОСНОВНОЙ ЦИКЛ ====================

print("=" * 60)
print("🚀 SMC FULL BOT 5.0 — С АВТОМАТИЧЕСКИМ FOOTPRINT")
print("=" * 60)
print(f"🏦 Текущая биржа: {router.current_name}")
print("📡 Footprint: автоматически запускается для любых добавленных монет!")
print("📊 Команды: /add, /remove, /list, /signals, /analyze, /scalp, /swing, /footprint, /footprint_list")
print("=" * 60)
print("Ожидание сообщений...\n")

# Запускаем начальные монеты
for sym in ['BTC', 'ETH', 'SOL']:
    footprint_manager.start_for_symbol(sym)

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
