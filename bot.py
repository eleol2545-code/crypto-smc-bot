import requests
import time
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime

TELEGRAM_TOKEN = "8645396589:AAHIceq907-38mvWJfa9BRaQWsrzC86ivNU"
LAST_UPDATE_ID = 0

# Используем KuCoin (стабильно работает)
exchange = ccxt.kucoin({
    'enableRateLimit': True,
})

# ==================== SMC АНАЛИЗАТОР ====================

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

def find_fair_value_gaps(df):
    """Находит Fair Value Gaps"""
    df['bullish_fvg'] = 0
    df['bearish_fvg'] = 0
    
    for i in range(2, len(df) - 1):
        if df['low'].iloc[i] > df['high'].iloc[i-2]:
            for j in range(i, min(i + 10, len(df))):
                if df['low'].iloc[j] <= df['low'].iloc[i]:
                    df.loc[df.index[j], 'bullish_fvg'] = 1
        
        elif df['high'].iloc[i] < df['low'].iloc[i-2]:
            for j in range(i, min(i + 10, len(df))):
                if df['high'].iloc[j] >= df['high'].iloc[i]:
                    df.loc[df.index[j], 'bearish_fvg'] = 1
    
    return df

def calculate_volume_profile(df, bars=50):
    """Volume Profile с POC"""
    recent = df.tail(bars)
    price_min = recent['low'].min()
    price_max = recent['high'].max()
    step = (price_max - price_min) / 20
    
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

def generate_signal(df, style='day'):
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
    
    # 2. FVG (15 баллов)
    if current['bullish_fvg'] == 1:
        score += 15
        if not signal_type:
            signal_type = 'LONG'
        reasons.append("💚 Бычий FVG")
    if current['bearish_fvg'] == 1:
        score += 15
        if not signal_type:
            signal_type = 'SHORT'
        reasons.append("❤️ Медвежий FVG")
    
    # 3. RSI (15 баллов)
    if current['rsi'] < 30:
        score += 15
        if not signal_type:
            signal_type = 'LONG'
        reasons.append(f"📊 RSI: {current['rsi']:.1f} (перепроданность)")
    elif current['rsi'] > 70:
        score += 15
        if not signal_type:
            signal_type = 'SHORT'
        reasons.append(f"📊 RSI: {current['rsi']:.1f} (перекупленность)")
    
    # 4. MACD (15 баллов)
    if current['macd_hist'] > 0:
        if signal_type == 'LONG':
            score += 15
            reasons.append(f"📈 MACD: +{current['macd_hist']:.2f}")
    elif current['macd_hist'] < 0:
        if signal_type == 'SHORT':
            score += 15
            reasons.append(f"📉 MACD: {current['macd_hist']:.2f}")
    
    # 5. Bollinger Bands (15 баллов)
    if current['close'] <= current['bb_lower'] * 1.005:
        score += 15
        if not signal_type:
            signal_type = 'LONG'
        reasons.append(f"📊 Bollinger: у нижней полосы ${current['bb_lower']:.0f}")
    elif current['close'] >= current['bb_upper'] * 0.995:
        score += 15
        if not signal_type:
            signal_type = 'SHORT'
        reasons.append(f"📊 Bollinger: у верхней полосы ${current['bb_upper']:.0f}")
    
    # 6. Stochastic (15 баллов)
    if current['stoch_k'] < 20 and current['stoch_d'] < 20:
        score += 15
        if not signal_type:
            signal_type = 'LONG'
        reasons.append(f"📊 Stochastic: %K={current['stoch_k']:.1f} (перепроданность)")
    elif current['stoch_k'] > 80 and current['stoch_d'] > 80:
        score += 15
        if not signal_type:
            signal_type = 'SHORT'
        reasons.append(f"📊 Stochastic: %K={current['stoch_k']:.1f} (перекупленность)")
    
    # 7. EMA тренд (10 баллов)
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
    
    # 8. Объем (10 баллов)
    if current['volume_ratio'] > 1.5:
        score += 10
        reasons.append(f"⚡ Объем: {current['volume_ratio']:.1f}x от среднего")
    
    # 9. VWAP (10 баллов)
    if current['close'] < current['vwap'] and signal_type == 'LONG':
        score += 10
        reasons.append(f"🎯 VWAP: цена ниже ${current['vwap']:.0f}")
    elif current['close'] > current['vwap'] and signal_type == 'SHORT':
        score += 10
        reasons.append(f"🎯 VWAP: цена выше ${current['vwap']:.0f}")
    
    confidence = min(100, score)
    
    if signal_type and confidence >= p['min_conf']:
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
            'price': entry,
            'entry': entry,
            'sl': sl,
            'tp': tp,
            'confidence': confidence,
            'score': score,
            'rr': rr,
            'reasons': reasons,
            'indicators': {
                'rsi': round(current['rsi'], 1),
                'macd': round(current['macd_hist'], 2),
                'vwap': round(current['vwap'], 2),
                'volume_ratio': round(current['volume_ratio'], 2)
            }
        }
    
    return None

def get_full_analysis(symbol, style='day'):
    """Полный SMC анализ"""
    try:
        df = exchange.fetch_ohlcv(symbol, '1h', limit=150)
        df = pd.DataFrame(df, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        df = calculate_indicators(df)
        df = find_order_blocks(df)
        df = find_fair_value_gaps(df)
        poc = calculate_volume_profile(df)
        
        signal = generate_signal(df, style)
        
        current_price = df['close'].iloc[-1]
        
        return {
            'price': current_price,
            'signal': signal,
            'poc': poc,
            'support': df['low'].iloc[-20:].min(),
            'resistance': df['high'].iloc[-20:].max()
        }
    except Exception as e:
        print(f"Error: {e}")
        return None

# ==================== TELEGRAM БОТ ====================

def send_message(chat_id, text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}, timeout=10)
    except:
        pass

def format_full_signal(symbol, analysis, style='day'):
    """Форматирует полный сигнал"""
    if not analysis:
        return f"❌ Ошибка получения данных для {symbol}"
    
    price = analysis['price']
    signal = analysis['signal']
    
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

📈 *SMC уровни:*
"""
        for r in signal['reasons'][:5]:
            msg += f"• {r}\n"
        
        if analysis['poc']:
            msg += f"• 🟡 POC: ${analysis['poc']:.0f}\n"
        
        return msg
    else:
        return f"""⏳ *НЕТ СИГНАЛА* | {symbol} | {style.upper()}

💰 Цена: ${price:.2f}
📊 POC: ${analysis['poc']:.0f}
🟢 Поддержка: ${analysis['support']:.2f}
🔴 Сопротивление: ${analysis['resistance']:.2f}

💡 *Рекомендация:* наблюдение
"""

def handle_message(chat_id, text):
    print(f"Message from {chat_id}: {text}")
    
    if text == "/start":
        send_message(chat_id, """🤖 *SMC CRYPTO BOT* — ПОЛНАЯ ВЕРСИЯ

📊 *Методология:* SMC/ICT + Order Blocks + FVG + Volume Profile

🎯 *Стили торговли:*
• SCALP (1m-15m) — сделки 5-120 мин
• DAY (15m-4h) — сделки 2-24 часа  
• SWING (4h-1d) — сделки 1-7 дней

📈 *Индикаторы:* RSI, MACD, Bollinger, Stochastic, VWAP, EMA

*Команды:*
/signals — сигналы по BTC, ETH, SOL (стиль DAY)
/scalp BTC — скальп-сигнал для BTC
/swing BTC — свинг-сигнал для BTC
/btc — анализ BTC
/status — статус бота
/help — помощь""")
    
    elif text == "/signals":
        send_message(chat_id, "🔍 *Поиск сигналов (стиль DAY)...*")
        
        btc = get_full_analysis('BTC/USDT', 'day')
        eth = get_full_analysis('ETH/USDT', 'day')
        sol = get_full_analysis('SOL/USDT', 'day')
        
        msg = "🚨 *АКТИВНЫЕ СИГНАЛЫ* (DAY)\n\n"
        msg += format_full_signal('BTC', btc, 'day') + "\n\n"
        msg += format_full_signal('ETH', eth, 'day') + "\n\n"
        msg += format_full_signal('SOL', sol, 'day')
        
        send_message(chat_id, msg[:4000])
    
    elif text.startswith("/scalp"):
        symbol = text.split()[-1].upper() if len(text.split()) > 1 else 'BTC'
        if symbol not in ['BTC', 'ETH', 'SOL']:
            symbol = 'BTC'
        
        send_message(chat_id, f"🔍 *Скальп-анализ {symbol}...*")
        analysis = get_full_analysis(f'{symbol}/USDT', 'scalp')
        send_message(chat_id, format_full_signal(symbol, analysis, 'scalp'))
    
    elif text.startswith("/swing"):
        symbol = text.split()[-1].upper() if len(text.split()) > 1 else 'BTC'
        if symbol not in ['BTC', 'ETH', 'SOL']:
            symbol = 'BTC'
        
        send_message(chat_id, f"🔍 *Свинг-анализ {symbol}...*")
        analysis = get_full_analysis(f'{symbol}/USDT', 'swing')
        send_message(chat_id, format_full_signal(symbol, analysis, 'swing'))
    
    elif text == "/btc":
        send_message(chat_id, "🔍 *Анализ BTC...*")
        analysis = get_full_analysis('BTC/USDT', 'day')
        send_message(chat_id, format_full_signal('BTC', analysis, 'day'))
    
    elif text == "/status":
        btc = get_full_analysis('BTC/USDT', 'day')
        if btc:
            send_message(chat_id, f"""✅ *СТАТУС БОТА*

BTC: ${btc['price']:.2f}
Поддержка: ${btc['support']:.2f}
Сопротивление: ${btc['resistance']:.2f}
POC: ${btc['poc']:.0f}

🎯 Стили: SCALP | DAY | SWING
📊 Индикаторы: RSI, MACD, Bollinger, Stochastic, VWAP
🤖 Версия: SMC Full 2.0
🏦 Биржа: KuCoin""")
        else:
            send_message(chat_id, "✅ Бот активен\nВерсия: SMC Full 2.0")
    
    elif text == "/help":
        send_message(chat_id, """📋 *КОМАНДЫ*

/signals — все сигналы (стиль DAY)
/scalp BTC — скальп-сигнал
/swing BTC — свинг-сигнал
/btc — анализ BTC
/status — статус бота
/help — эта справка

📊 *Что анализирует:*
• Order Blocks (зоны крупных игроков)
• Fair Value Gaps (разрывы цены)
• Volume Profile (POC, HVN, LVN)
• RSI, MACD, Bollinger, Stochastic, VWAP
• Система баллов (0-100)""")
    
    else:
        send_message(chat_id, f"⚠️ Неизвестно: {text}\n/help")

# ==================== ОСНОВНОЙ ЦИКЛ ====================

print("🚀 SMC FULL BOT запущен")
print("📊 Методология: SMC/ICT + Order Blocks + FVG + Volume Profile")
print("📈 Индикаторы: RSI, MACD, Bollinger, Stochastic, VWAP, EMA")
print("🎯 Стили: SCALP, DAY, SWING")
print("Ожидание сообщений...")

while True:
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        response = requests.get(url, params={"offset": LAST_UPDATE_ID + 1, "timeout": 30})
        data = response.json()
        
        if data.get("ok"):
            for update in data.get("result", []):
                LAST_UPDATE_ID = update["update_id"]
                if "message" in update:
                    msg = update["message"]
                    chat_id = msg["chat"]["id"]
                    text = msg.get("text", "")
                    handle_message(chat_id, text)
    except Exception as e:
        print(f"Error: {e}")
    
    time.sleep(1)
