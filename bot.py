import requests
import time
import ccxt
import pandas as pd
import numpy as np
import json
import os

TELEGRAM_TOKEN = "8645396589:AAHIceq907-38mvWJfa9BRaQWsrzC86ivNU"
LAST_UPDATE_ID = 0

# Папка для хранения данных пользователей
os.makedirs('data', exist_ok=True)

exchange = ccxt.kucoin({'enableRateLimit': True})

# ==================== ХРАНИЛИЩЕ ПОЛЬЗОВАТЕЛЕЙ ====================

def get_user_data(chat_id):
    """Получает данные пользователя, создает если нет"""
    file_path = f'data/user_{chat_id}.json'
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            return json.load(f)
    else:
        # Новый пользователь с настройками по умолчанию
        user_data = {
            'watchlist': ['BTC/USDT', 'ETH/USDT', 'SOL/USDT'],
            'style': 'day',
            'timeframe': '1h',
            'min_confidence': 70
        }
        with open(file_path, 'w') as f:
            json.dump(user_data, f)
        return user_data

def save_user_data(chat_id, data):
    """Сохраняет данные пользователя"""
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
    
    # Order Blocks
    if current['bullish_ob'] == 1:
        score += 20
        signal_type = 'LONG'
        reasons.append(f"🔵 Бычий OB: ${current['ob_low']:.0f}-${current['ob_high']:.0f}")
    if current['bearish_ob'] == 1:
        score += 20
        signal_type = 'SHORT'
        reasons.append(f"🔴 Медвежий OB: ${current['ob_low']:.0f}-${current['ob_high']:.0f}")
    
    # RSI
    if current['rsi'] < 30:
        score += 15
        if not signal_type: signal_type = 'LONG'
        reasons.append(f"📊 RSI: {current['rsi']:.1f} (перепроданность)")
    elif current['rsi'] > 70:
        score += 15
        if not signal_type: signal_type = 'SHORT'
        reasons.append(f"📊 RSI: {current['rsi']:.1f} (перекупленность)")
    
    # MACD
    if current['macd_hist'] > 0 and signal_type == 'LONG':
        score += 15
        reasons.append(f"📈 MACD: +{current['macd_hist']:.2f}")
    elif current['macd_hist'] < 0 and signal_type == 'SHORT':
        score += 15
        reasons.append(f"📉 MACD: {current['macd_hist']:.2f}")
    
    # Bollinger
    if current['close'] <= current['bb_lower'] * 1.005:
        score += 15
        if not signal_type: signal_type = 'LONG'
        reasons.append(f"📊 Bollinger: у нижней полосы")
    elif current['close'] >= current['bb_upper'] * 0.995:
        score += 15
        if not signal_type: signal_type = 'SHORT'
        reasons.append(f"📊 Bollinger: у верхней полосы")
    
    # Stochastic
    if current['stoch_k'] < 20:
        score += 15
        if not signal_type: signal_type = 'LONG'
        reasons.append(f"📊 Stochastic: %K={current['stoch_k']:.1f}")
    elif current['stoch_k'] > 80:
        score += 15
        if not signal_type: signal_type = 'SHORT'
        reasons.append(f"📊 Stochastic: %K={current['stoch_k']:.1f}")
    
    # EMA тренд
    if current['ema_9'] > current['ema_21'] and current['ema_21'] > current['ema_50']:
        score += 10
        if signal_type == 'LONG': score += 5
        reasons.append("📈 EMA: золотой крест")
    elif current['ema_9'] < current['ema_21'] and current['ema_21'] < current['ema_50']:
        score += 10
        if signal_type == 'SHORT': score += 5
        reasons.append("📉 EMA: мертвый крест")
    
    # Объем
    if current['volume_ratio'] > 1.5:
        score += 10
        reasons.append(f"⚡ Объем: {current['volume_ratio']:.1f}x")
    
    # VWAP
    if current['close'] < current['vwap'] and signal_type == 'LONG':
        score += 10
        reasons.append(f"🎯 VWAP: цена ниже")
    elif current['close'] > current['vwap'] and signal_type == 'SHORT':
        score += 10
        reasons.append(f"🎯 VWAP: цена выше")
    
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
            'signal': signal_type,
            'entry': entry,
            'sl': sl,
            'tp': tp,
            'confidence': confidence,
            'score': score,
            'rr': round(abs(tp - entry) / abs(sl - entry), 1),
            'reasons': reasons[:5]
        }
    
    return None

def get_full_analysis(symbol, style='day', min_confidence=70):
    """Полный SMC анализ для ЛЮБОЙ монеты"""
    try:
        df = exchange.fetch_ohlcv(symbol, '1h', limit=150)
        df = pd.DataFrame(df, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
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
            'resistance': df['high'].iloc[-20:].max()
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
        return f"❌ Ошибка получения данных для {symbol}"
    
    signal = analysis['signal']
    price = analysis['price']
    
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

📊 *Причины:*\n"""
        for r in signal['reasons']:
            msg += f"• {r}\n"
        
        if analysis['poc']:
            msg += f"• 🟡 POC: ${analysis['poc']:.0f}\n"
        
        return msg
    else:
        return f"""⏳ *НЕТ СИГНАЛА* | {symbol} | {style.upper()}

💰 Цена: ${price:.2f}
🟢 Поддержка: ${analysis['support']:.2f}
🔴 Сопротивление: ${analysis['resistance']:.2f}
📊 POC: ${analysis['poc']:.0f}

💡 Рекомендация: наблюдение"""

def handle_message(chat_id, text):
    print(f"Message from {chat_id}: {text}")
    user_data = get_user_data(chat_id)
    
    if text == "/start":
        send_message(chat_id, """🤖 *SMC CRYPTO BOT* — ПОЛНАЯ ВЕРСИЯ

📊 *Методология:* SMC/ICT + Order Blocks + FVG + Volume Profile
📈 *Индикаторы:* RSI, MACD, Bollinger, Stochastic, VWAP, EMA
🎯 *Стили:* SCALP (внутри дня), DAY (дневная), SWING (среднесрок)

*Команды:*
/add BTC,ETH,SOL — добавить монеты
/remove DOGE — удалить монету
/list — мои монеты
/signals — сигналы по моим монетам
/analyze PEPE — анализ любой монеты
/scalp BTC — скальп-сигнал
/swing BTC — свинг-сигнал
/settings — настройки
/status — статус
/help — помощь""")
    
    elif text.startswith("/add"):
        args = text.replace("/add", "").strip().upper().replace(",", " ").split()
        added = []
        for arg in args:
            if not arg.endswith('/USDT'):
                sym = f"{arg}/USDT"
            else:
                sym = arg
            if sym not in user_data['watchlist']:
                user_data['watchlist'].append(sym)
                added.append(sym)
        save_user_data(chat_id, user_data)
        send_message(chat_id, f"✅ Добавлено: {', '.join(added)}\n\n📋 Всего монет: {len(user_data['watchlist'])}")
    
    elif text.startswith("/remove"):
        args = text.replace("/remove", "").strip().upper()
        if args:
            if not args.endswith('/USDT'):
                sym = f"{args}/USDT"
            else:
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
        
        send_message(chat_id, f"🔍 *Поиск сигналов ({user_data['style'].upper()})...*")
        
        msg = f"🚨 *СИГНАЛЫ* ({user_data['style'].upper()})\n\n"
        for sym in user_data['watchlist'][:5]:  # Ограничим 5 монетами
            name = sym.replace('/USDT', '')
            analysis = get_full_analysis(sym, user_data['style'], user_data['min_confidence'])
            msg += format_signal(name, analysis, user_data['style']) + "\n\n"
        
        send_message(chat_id, msg[:4000])
    
    elif text.startswith("/analyze"):
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id, "📝 *Пример:* `/analyze PEPE`")
            return
        
        symbol = parts[1].upper()
        if not symbol.endswith('/USDT'):
            sym = f"{symbol}/USDT"
        else:
            sym = symbol
            symbol = symbol.replace('/USDT', '')
        
        send_message(chat_id, f"🔍 *Анализ {symbol}...*")
        analysis = get_full_analysis(sym, user_data['style'], user_data['min_confidence'])
        send_message(chat_id, format_signal(symbol, analysis, user_data['style']))
    
    elif text.startswith("/scalp"):
        parts = text.split()
        symbol = parts[1].upper() if len(parts) > 1 else 'BTC'
        if not symbol.endswith('/USDT'):
            sym = f"{symbol}/USDT"
        else:
            sym = symbol
            symbol = symbol.replace('/USDT', '')
        
        send_message(chat_id, f"🔍 *Скальп-анализ {symbol}...*")
        analysis = get_full_analysis(sym, 'scalp', 65)
        send_message(chat_id, format_signal(symbol, analysis, 'scalp'))
    
    elif text.startswith("/swing"):
        parts = text.split()
        symbol = parts[1].upper() if len(parts) > 1 else 'BTC'
        if not symbol.endswith('/USDT'):
            sym = f"{symbol}/USDT"
        else:
            sym = symbol
            symbol = symbol.replace('/USDT', '')
        
        send_message(chat_id, f"🔍 *Свинг-анализ {symbol}...*")
        analysis = get_full_analysis(sym, 'swing', 75)
        send_message(chat_id, format_signal(symbol, analysis, 'swing'))
    
    elif text == "/settings":
        send_message(chat_id, f"""⚙️ *НАСТРОЙКИ*

🎯 Стиль: {user_data['style'].upper()}
📊 Мин. уверенность: {user_data['min_confidence']}%
⏱️ Таймфрейм: {user_data['timeframe']}
📋 Монет: {len(user_data['watchlist'])}

*Изменить стиль:* /style scalp|day|swing
*Изменить уверенность:* /confidence 70""")
    
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
    
    elif text == "/status":
        btc = get_full_analysis('BTC/USDT', 'day')
        if btc:
            send_message(chat_id, f"""✅ *СТАТУС БОТА*

🎯 Ваш стиль: {user_data['style'].upper()}
📊 Мин. уверенность: {user_data['min_confidence']}%
📋 Монет в списке: {len(user_data['watchlist'])}

📈 *BTC:* ${btc['price']:.2f}
🟢 Поддержка: ${btc['support']:.2f}
🔴 Сопротивление: ${btc['resistance']:.2f}

🤖 Версия: SMC Full 3.0
🏦 Биржа: KuCoin""")
        else:
            send_message(chat_id, "✅ Бот активен")
    
    elif text == "/help":
        send_message(chat_id, """📋 *ВСЕ КОМАНДЫ*

📌 *Управление монетами:*
/add BTC,ETH,SOL — добавить монеты
/remove DOGE — удалить монету
/list — мои монеты

📌 *Сигналы:*
/signals — сигналы по моим монетам
/analyze PEPE — анализ любой монеты
/scalp BTC — скальп-сигнал
/swing BTC — свинг-сигнал

📌 *Настройки:*
/settings — текущие настройки
/style scalp|day|swing — сменить стиль
/confidence 70 — мин. уверенность

📌 *Другое:*
/status — статус бота
/help — эта справка

📊 *Стили:*
• SCALP — сделки 5-120 мин (SL 0.8%, TP 1.5%)
• DAY — сделки 2-24 часа (SL 1.5%, TP 3.0%)
• SWING — сделки 1-7 дней (SL 2.5%, TP 6.0%)""")
    
    else:
        send_message(chat_id, f"⚠️ Неизвестно: {text}\n/help")

# ==================== ОСНОВНОЙ ЦИКЛ ====================

print("🚀 SMC FULL BOT 3.0 — МУЛЬТИВАЛЮТНЫЙ")
print("📊 Команды: /add, /remove, /list, /signals, /analyze, /scalp, /swing")
print("🎯 Каждый пользователь имеет свой список монет и настройки")
print("Ожидание сообщений...")

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
