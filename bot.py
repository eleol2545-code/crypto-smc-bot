import requests
import time
import ccxt
import pandas as pd

TELEGRAM_TOKEN = "8645396589:AAHIceq907-38mvWJfa9BRaQWsrzC86ivNU"
LAST_UPDATE_ID = 0

# ИСПОЛЬЗУЕМ KUCOIN (работает стабильно)
exchange = ccxt.kucoin({
    'enableRateLimit': True,
})

def send_message(chat_id, text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}, timeout=10)
        print(f"Sent to {chat_id}")
    except Exception as e:
        print(f"Send error: {e}")

def get_signal(symbol='BTC/USDT'):
    """Получает сигнал по паре (KuCoin использует BTC/USDT с /)"""
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, '1h', limit=50)
        df = pd.DataFrame(ohlcv, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        
        price = df['c'].iloc[-1]
        high_20 = df['h'].iloc[-20:].max()
        low_20 = df['l'].iloc[-20:].min()
        
        # RSI
        delta = df['c'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs)).iloc[-1]
        
        symbol_name = symbol.replace('/USDT', '')
        
        if price <= low_20 * 1.005 and rsi < 40:
            return {
                'signal': 'LONG',
                'symbol': symbol_name,
                'price': price,
                'rsi': rsi,
                'entry': price,
                'sl': price * 0.985,
                'tp': price * 1.04,
                'confidence': 75,
                'support': low_20,
                'resistance': high_20
            }
        elif price >= high_20 * 0.995 and rsi > 60:
            return {
                'signal': 'SHORT',
                'symbol': symbol_name,
                'price': price,
                'rsi': rsi,
                'entry': price,
                'sl': price * 1.015,
                'tp': price * 0.96,
                'confidence': 75,
                'support': low_20,
                'resistance': high_20
            }
        else:
            return {
                'signal': None,
                'symbol': symbol_name,
                'price': price,
                'rsi': rsi,
                'support': low_20,
                'resistance': high_20
            }
    except Exception as e:
        print(f"Error for {symbol}: {e}")
        return None

def format_signal(signal):
    """Форматирует сигнал для отправки"""
    if not signal:
        return "❌ Ошибка получения данных"
    
    if signal.get('signal'):
        emoji = "📈" if signal['signal'] == 'LONG' else "📉"
        rr = round((signal['tp'] - signal['entry']) / (signal['entry'] - signal['sl']), 1) if signal['signal'] == 'LONG' else round((signal['entry'] - signal['tp']) / (signal['sl'] - signal['entry']), 1)
        
        return f"""{emoji} *{signal['signal']} СИГНАЛ* | {signal['symbol']}

💰 Цена: ${signal['price']:.2f}
🎯 Уверенность: {signal['confidence']}%
📊 RSI: {signal['rsi']:.1f}

🚪 Вход: ${signal['entry']:.2f}
🛑 SL: ${signal['sl']:.2f}
🎯 TP: ${signal['tp']:.2f}
📊 R:R: 1:{rr}"""
    else:
        return f"""⏳ *НЕТ СИГНАЛА* | {signal['symbol']}

💰 Цена: ${signal['price']:.2f}
📊 RSI: {signal['rsi']:.1f}
🟢 Поддержка: ${signal['support']:.2f}
🔴 Сопротивление: ${signal['resistance']:.2f}"""

def handle_message(chat_id, text):
    """Обработка команд"""
    print(f"Message from {chat_id}: {text}")
    
    if text == "/start":
        send_message(chat_id, """🤖 *SMC Crypto Bot*

✅ Бот работает на KuCoin

*Команды:*
/signals - сигналы BTC, ETH, SOL
/btc - только BTC
/status - статус
/help - помощь""")
    
    elif text == "/signals":
        send_message(chat_id, "🔍 *Поиск сигналов...*")
        
        btc = get_signal('BTC/USDT')
        eth = get_signal('ETH/USDT')
        sol = get_signal('SOL/USDT')
        
        msg = "🚨 *АКТИВНЫЕ СИГНАЛЫ*\n\n"
        msg += format_signal(btc) + "\n\n"
        msg += format_signal(eth) + "\n\n"
        msg += format_signal(sol)
        
        send_message(chat_id, msg)
    
    elif text == "/btc":
        send_message(chat_id, "🔍 *Анализ BTC...*")
        btc = get_signal('BTC/USDT')
        send_message(chat_id, format_signal(btc))
    
    elif text == "/status":
        btc = get_signal('BTC/USDT')
        if btc:
            send_message(chat_id, f"""✅ *Статус*

BTC: ${btc['price']:.2f}
RSI: {btc['rsi']:.1f}
Поддержка: ${btc['support']:.2f}
Сопротивление: ${btc['resistance']:.2f}

Бот: активен
Биржа: KuCoin
Версия: 2.0""")
        else:
            send_message(chat_id, "✅ Бот активен\nБиржа: KuCoin")
    
    elif text == "/help":
        send_message(chat_id, """📋 *Команды:*
/start - запуск
/signals - все сигналы
/btc - только BTC
/status - статус
/help - помощь""")
    
    else:
        send_message(chat_id, f"⚠️ Неизвестно: {text}\n/help")

# ==================== ОСНОВНОЙ ЦИКЛ ====================

print("🚀 SMC Crypto Bot запущен (KuCoin)")
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
