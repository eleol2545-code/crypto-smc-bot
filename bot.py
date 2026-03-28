import requests
import time
import ccxt
import pandas as pd
import numpy as np
import json
import os
from datetime import datetime

TELEGRAM_TOKEN = "8645396589:AAHIceq907-38mvWJfa9BRaQWsrzC86ivNU"
LAST_UPDATE_ID = 0

os.makedirs('data', exist_ok=True)

# ==================== КОНФИГУРАЦИЯ БИРЖ ====================

EXCHANGES = {
    'bybit': {
        'name': 'Bybit',
        'class': ccxt.bybit,
        'params': {'options': {'defaultType': 'linear'}},
        'format': 'BTCUSDT',  # формат без /
        'active': True,
        'last_error': None
    },
    'kucoin': {
        'name': 'KuCoin',
        'class': ccxt.kucoin,
        'params': {},
        'format': 'BTC/USDT',  # формат с /
        'active': True,
        'last_error': None
    },
    'gate': {
        'name': 'Gate.io',
        'class': ccxt.gateio,
        'params': {'options': {'defaultType': 'swap'}},
        'format': 'BTC_USDT',  # формат с _
        'active': True,
        'last_error': None
    },
    'okx': {
        'name': 'OKX',
        'class': ccxt.okx,
        'params': {'options': {'defaultType': 'swap'}},
        'format': 'BTC-USDT-SWAP',
        'active': True,
        'last_error': None
    }
}

# ==================== SMART EXCHANGE ROUTER ====================

class SmartExchangeRouter:
    """Автоматически выбирает работающую биржу"""
    
    def __init__(self):
        self.exchanges = {}
        self.current_exchange = None
        self.current_name = None
        self.initialize_exchanges()
    
    def initialize_exchanges(self):
        """Инициализирует все биржи"""
        for name, config in EXCHANGES.items():
            if config['active']:
                try:
                    self.exchanges[name] = config['class'](config['params'])
                    self.exchanges[name].enableRateLimit = True
                    print(f"✅ Инициализирована {config['name']}")
                except Exception as e:
                    print(f"❌ Ошибка инициализации {config['name']}: {e}")
                    config['active'] = False
        
        # Выбираем первую активную биржу
        for name, config in EXCHANGES.items():
            if config['active']:
                self.current_exchange = self.exchanges[name]
                self.current_name = config['name']
                self.current_format = config['format']
                break
    
    def test_connection(self):
        """Тестирует подключение к текущей бирже"""
        try:
            ticker = self.current_exchange.fetch_ticker('BTC/USDT' if '/' in self.current_format else 'BTCUSDT')
            return True
        except Exception as e:
            print(f"⚠️ {self.current_name} не отвечает: {e}")
            return False
    
    def switch_to_next_exchange(self):
        """Переключается на следующую работающую биржу"""
        for name, config in EXCHANGES.items():
            if config['active'] and name != self.current_name.lower():
                try:
                    self.current_exchange = self.exchanges[name]
                    self.current_name = config['name']
                    self.current_format = config['format']
                    print(f"🔄 Переключено на {self.current_name}")
                    return True
                except:
                    continue
        return False
    
    def format_symbol(self, symbol):
        """Форматирует символ под текущую биржу"""
        symbol = symbol.upper().replace('USDT', '').replace('/', '')
        
        if self.current_format == 'BTCUSDT':
            return f"{symbol}USDT"
        elif self.current_format == 'BTC/USDT':
            return f"{symbol}/USDT"
        elif self.current_format == 'BTC_USDT':
            return f"{symbol}_USDT"
        elif self.current_format == 'BTC-USDT-SWAP':
            return f"{symbol}-USDT-SWAP"
        return f"{symbol}/USDT"
    
    def fetch_ohlcv(self, symbol, timeframe='1h', limit=150):
        """Получает свечи с текущей биржи, при ошибке переключается"""
        try:
            formatted = self.format_symbol(symbol)
            return self.current_exchange.fetch_ohlcv(formatted, timeframe, limit=limit)
        except Exception as e:
            print(f"❌ Ошибка на {self.current_name}: {e}")
            if self.switch_to_next_exchange():
                return self.fetch_ohlcv(symbol, timeframe, limit)
            return None

# Инициализируем роутер
router = SmartExchangeRouter()

# ==================== ХРАНИЛИЩЕ ПОЛЬЗОВАТЕЛЕЙ ====================

def get_user_data(chat_id):
    file_path = f'data/user_{chat_id}.json'
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            return json.load(f)
    else:
        user_data = {
            'watchlist': ['BTC', 'ETH', 'SOL'],
            'style': 'day',
            'timeframe': '1h',
            'min_confidence': 70
        }
        with open(file_path, 'w') as f:
            json.dump(user_data, f)
        return user_data

def save_user_data(chat_id, data):
    with open(f'data/user_{chat_id}.json', 'w') as f:
        json.dump(data, f)

# ==================== SMC АНАЛИЗАТОР (полный) ====================

def calculate_indicators(df):
    """Рассчитывает все индикаторы"""
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
    """Находит Order Blocks"""
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
    """Volume Profile с POC"""
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
    """Генерирует сигнал с системой баллов"""
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
    
    # 1. Order Blocks (20 баллов)
    if current['bullish_ob'] == 1:
        score += 20
        signal_type = 'LONG'
        reasons.append(f"🔵 Бычий OB: ${current['ob_low']:.0f}-${current['ob_high']:.0f}")
    if current['bearish_ob'] == 1:
        score += 20
        signal_type = 'SHORT'
        reasons.append(f"🔴 Медвежий OB: ${current['ob_low']:.0f}-${current['ob_high']:.0f}")
    
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
        reasons.append(f"📈 MACD: +{current['macd_hist']:.2f}")
    elif current['macd_hist'] < 0 and signal_type == 'SHORT':
        score += 15
        reasons.append(f"📉 MACD: {current['macd_hist']:.2f}")
    
    # 4. Bollinger Bands (15 баллов)
    if current['close'] <= current['bb_lower'] * 1.005:
        score += 15
        if not signal_type: signal_type = 'LONG'
        reasons.append(f"📊 Bollinger: у нижней полосы ${current['bb_lower']:.0f}")
    elif current['close'] >= current['bb_upper'] * 0.995:
        score += 15
        if not signal_type: signal_type = 'SHORT'
        reasons.append(f"📊 Bollinger: у верхней полосы ${current['bb_upper']:.0f}")
    
    # 5. Stochastic (15 баллов)
    if current['stoch_k'] < 20 and current['stoch_d'] < 20:
        score += 15
        if not signal_type: signal_type = 'LONG'
        reasons.append(f"📊 Stochastic: %K={current['stoch_k']:.1f} (перепроданность)")
    elif current['stoch_k'] > 80 and current['stoch_d'] > 80:
        score += 15
        if not signal_type: signal_type = 'SHORT'
        reasons.append(f"📊 Stochastic: %K={current['stoch_k']:.1f} (перекупленность)")
    
    # 6. EMA тренд (10 баллов)
    if current['ema_9'] > current['ema_21'] and current['ema_21'] > current['ema_50']:
        score += 10
        if signal_type == 'LONG':
            score += 5
        reasons.append("📈 EMA: золотой крест")
    elif current['ema_9'] < current['ema_21'] and current['ema_21'] < current['ema_50']:
        score += 10
        if signal_type == 'SHORT':
            score += 5
        reasons.append("📉 EMA: мертвый крест")
    
    # 7. Объем (10 баллов)
    if current['volume_ratio'] > 1.5:
        score += 10
        reasons.append(f"⚡ Объем: {current['volume_ratio']:.1f}x от среднего")
    
    # 8. VWAP (10 баллов)
    if current['close'] < current['vwap'] and signal_type == 'LONG':
        score += 10
        reasons.append(f"🎯 VWAP: цена ниже ${current['vwap']:.0f}")
    elif current['close'] > current['vwap'] and signal_type == 'SHORT':
        score += 10
        reasons.append(f"🎯 VWAP: цена выше ${current['vwap']:.0f}")
    
    confidence = min(100, score)
    
    if signal_type and confidence >= min_confidence:
        entry = current['close']
        if signal_type == 'LONG':
            sl = entry * (1 - p['sl_pct'])
            tp = entry * (1 + p['tp_pct'])
        else:
            sl = entry * (1 + p['sl_pct'])
            tp = entry * (1 - p['tp_pct'])
        
        rr = round(abs(tp - entry) / abs(sl - entry), 1)
        
        return {
            'signal': signal_type,
            'entry': round(entry, 2),
            'sl': round(sl, 2),
            'tp': round(tp, 2),
            'confidence': confidence,
            'score': score,
            'rr': rr,
            'reasons': reasons[:6],
            'indicators': {
                'rsi': round(current['rsi'], 1),
                'macd': round(current['macd_hist'], 2),
                'vwap': round(current['vwap'], 2),
                'volume_ratio': round(current['volume_ratio'], 2)
            }
        }
    
    return None

def get_full_analysis(symbol, style='day', min_confidence=70):
    """Полный SMC анализ с автоматическим выбором биржи"""
    try:
        # Получаем свечи через Smart Router
        ohlcv = router.fetch_ohlcv(symbol, '1h', 150)
        if not ohlcv:
            return None
        
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        df = calculate_indicators(df)
        df = find_order_blocks(df)
        poc = calculate_volume_profile(df)
        
        signal = generate_signal(df, style, min_confidence)
        
        current_price = df['close'].iloc[-1]
        
        return {
            'price': current_price,
            'signal': signal,
            'poc': poc,
            'support': df['low'].iloc[-20:].min(),
            'resistance': df['high'].iloc[-20:].max(),
            'exchange': router.current_name
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
    if not analysis:
        return f"❌ Ошибка получения данных для {symbol}\nБиржа: {router.current_name}"
    
    signal = analysis['signal']
    price = analysis['price']
    exchange = analysis.get('exchange', router.current_name)
    
    if signal:
        emoji = "📈" if signal['signal'] == 'LONG' else "📉"
        msg = f"""{emoji} *{signal['signal']} СИГНАЛ* | {symbol} | {style.upper()}

💰 Цена: ${price:.2f}
🎯 Уверенность: {signal['confidence']}%
📊 Баллы: {signal['score']}/100
📈 R:R: 1:{signal['rr']}

🚪 Вход: ${signal['entry']:.2f}
🛑 SL: ${signal['sl']:.2f}
🎯 TP: ${signal['tp']:.2f}

📊 *Индикаторы:*
• RSI: {signal['indicators']['rsi']}
• MACD: {signal['indicators']['macd']:+.2f}
• VWAP: ${signal['indicators']['vwap']:.0f}
• Объем: {signal['indicators']['volume_ratio']:.1f}x

📈 *SMC уровни:*\n"""
        for r in signal['reasons']:
            msg += f"• {r}\n"
        
        if analysis['poc']:
            msg += f"• 🟡 POC: ${analysis['poc']:.0f}\n"
        
        msg += f"\n🏦 *Биржа:* {exchange}"
        return msg
    else:
        return f"""⏳ *НЕТ СИГНАЛА* | {symbol} | {style.upper()}

💰 Цена: ${price:.2f}
🟢 Поддержка: ${analysis['support']:.2f}
🔴 Сопротивление: ${analysis['resistance']:.2f}
📊 POC: ${analysis['poc']:.0f}

💡 Рекомендация: наблюдение
🏦 *Биржа:* {exchange}"""

def handle_message(chat_id, text):
    print(f"Message from {chat_id}: {text}")
    user_data = get_user_data(chat_id)
    
    if text == "/start":
        send_message(chat_id, f"""🤖 *SMC CRYPTO BOT* — МУЛЬТИБИРЖЕВАЯ ВЕРСИЯ

📊 *Методология:* SMC/ICT + Order Blocks + FVG + Volume Profile
📈 *Индикаторы:* RSI, MACD, Bollinger, Stochastic, VWAP, EMA
🎯 *Стили:* SCALP (внутри дня), DAY (дневная), SWING (среднесрок)

🏦 *Активные биржи:* Bybit, KuCoin, Gate.io, OKX (автопереключение)
🔄 *Текущая биржа:* {router.current_name}

*Команды:*
/add BTC,ETH,SOL,DOGE,PEPE — добавить монеты
/remove DOGE — удалить монету
/list — мои монеты
/signals — сигналы по моим монетам
/analyze PEPE — анализ любой монеты
/scalp BTC — скальп-сигнал
/swing BTC — свинг-сигнал
/settings — настройки
/status — статус
/exchange — текущая биржа
/help — помощь""")
    
    elif text.startswith("/add"):
        args = text.replace("/add", "").strip().upper().replace(",", " ").split()
        added = []
        for arg in args:
            sym = arg.upper()
            if sym not in user_data['watchlist']:
                user_data['watchlist'].append(sym)
                added.append(sym)
        save_user_data(chat_id, user_data)
        send_message(chat_id, f"✅ Добавлено: {', '.join(added)}\n\n📋 Всего монет: {len(user_data['watchlist'])}")
    
    elif text.startswith("/remove"):
        args = text.replace("/remove", "").strip().upper()
        if args:
            sym = args
            if sym in user_data['watchlist']:
                user_data['watchlist'].remove(sym)
                save_user_data(chat_id, user_data)
                send_message(chat_id, f"❌ Удалено: {sym}")
            else:
                send_message(chat_id, f"⚠️ {sym} не найдена в вашем списке")
    
    elif text == "/list":
        if not user_data['watchlist']:
            send_message(chat_id, "📭 Список пуст. Добавьте: `/add BTC`")
        else:
            msg = "📋 *МОИ МОНЕТЫ*\n\n"
            for s in user_data['watchlist']:
                msg += f"• {s}\n"
            send_message(chat_id, msg)
    
    elif text == "/signals":
        if not user_data['watchlist']:
            send_message(chat_id, "📭 Нет монет в списке. Добавьте: `/add BTC`")
            return
        
        send_message(chat_id, f"🔍 *Поиск сигналов ({user_data['style'].upper()})...*\n🏦 Биржа: {router.current_name}")
        
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
        send_message(chat_id, f"🔍 *Скальп-анализ {symbol}...*\n🏦 Биржа: {router.current_name}")
        analysis = get_full_analysis(symbol, 'scalp', 65)
        send_message(chat_id, format_signal(symbol, analysis, 'scalp'))
    
    elif text.startswith("/swing"):
        parts = text.split()
        symbol = parts[1].upper() if len(parts) > 1 else 'BTC'
        send_message(chat_id, f"🔍 *Свинг-анализ {symbol}...*\n🏦 Биржа: {router.current_name}")
        analysis = get_full_analysis(symbol, 'swing', 75)
        send_message(chat_id, format_signal(symbol, analysis, 'swing'))
    
    elif text == "/settings":
        send_message(chat_id, f"""⚙️ *НАСТРОЙКИ*

🎯 Стиль: {user_data['style'].upper()}
📊 Мин. уверенность: {user_data['min_confidence']}%
⏱️ Таймфрейм: {user_data['timeframe']}
📋 Монет: {len(user_data['watchlist'])}

*Изменить:*
/style scalp|day|swing
/confidence 70""")
    
    elif text.startswith("/style"):
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id, "📝 *Пример:* `/style scalp` (scalp/day/swing)")
            return
        new_style = parts[1].lower()
        if new_style in ['scalp', 'day', 'swing']:
            user_data['style'] = new_style
            save_user_data(chat_id, user_data)
            send_message(chat_id, f"✅ Стиль изменен на {new_style.upper()}")
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
                user_data['min_confidence'] = val
                save_user_data(chat_id, user_data)
                send_message(chat_id, f"✅ Мин. уверенность: {val}%")
            else:
                send_message(chat_id, "⚠️ Значение от 50 до 90")
        except:
            send_message(chat_id, "⚠️ Введите число")
    
    elif text == "/exchange":
        send_message(chat_id, f"🏦 *Текущая биржа:* {router.current_name}\n\nДоступные биржи:\n• Bybit ✅\n• KuCoin ✅\n• Gate.io ✅\n• OKX ⚠️\n\n*Автоматическое переключение при ошибках*")
    
    elif text == "/status":
        btc = get_full_analysis('BTC', 'day')
        if btc:
            send_message(chat_id, f"""✅ *СТАТУС БОТА*

🏦 *Биржа:* {router.current_name}
🎯 *Ваш стиль:* {user_data['style'].upper()}
📊 *Мин. уверенность:* {user_data['min_confidence']}%
📋 *Монет в списке:* {len(user_data['watchlist'])}

📈 *BTC:* ${btc['price']:.2f}
🟢 *Поддержка:* ${btc['support']:.2f}
🔴 *Сопротивление:* ${btc['resistance']:.2f}
📊 *POC:* ${btc['poc']:.0f}

🤖 *Версия:* SMC Multi-Exchange 3.0""")
        else:
            send_message(chat_id, "✅ Бот активен\n🏦 Мультибиржевой режим")
    
    elif text == "/help":
        send_message(chat_id, """📋 *ВСЕ КОМАНДЫ*

📌 *Управление монетами:*
/add BTC,ETH,SOL,DOGE,PEPE — добавить
/remove DOGE — удалить
/list — мои монеты

📌 *Сигналы:*
/signals — по моим монетам
/analyze PEPE — анализ любой
/scalp BTC — скальп-сигнал
/swing BTC — свинг-сигнал

📌 *Настройки:*
/settings — текущие настройки
/style scalp|day|swing — сменить стиль
/confidence 70 — мин. уверенность

📌 *Другое:*
/exchange — текущая биржа
/status — статус бота
/help — эта справка

📊 *Стили:*
• SCALP — сделки 5-120 мин (SL 0.8%, TP 1.5%)
• DAY — сделки 2-24 часа (SL 1.5%, TP 3.0%)
• SWING — сделки 1-7 дней (SL 2.5%, TP 6.0%)

🏦 *Биржи:* Bybit, KuCoin, Gate.io, OKX (автопереключение)""")
    
    else:
        send_message(chat_id, f"⚠️ Неизвестно: {text}\n/help")

# ==================== ОСНОВНОЙ ЦИКЛ ====================

print("=" * 60)
print("🚀 SMC MULTI-EXCHANGE BOT 3.0")
print("=" * 60)
print(f"🏦 Активные биржи:")
for name, config in EXCHANGES.items():
    if config['active']:
        print(f"   ✅ {config['name']}")
print(f"\n🔄 Текущая биржа: {router.current_name}")
print("📊 Команды: /add, /remove, /list, /signals, /analyze, /scalp, /swing")
print("🎯 Каждый пользователь имеет свой список монет и настройки")
print("=" * 60)
print("Ожидание сообщений...\n")

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
