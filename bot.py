import requests
import time
import ccxt
import pandas as pd

TELEGRAM_TOKEN = "8645396589:AAHIceq907-38mvWJfa9BRaQWsrzC86ivNU"
LAST_UPDATE_ID = 0

exchange = ccxt.binance({'enableRateLimit': True})

def send_message(chat_id, text):
    """Отправляет сообщение"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}, timeout=5)
        print(f"Sent to {chat_id}")
    except Exception as e:
        print(f"Send error: {e}")

def get_btc_signal():
    """Получает сигнал по BTC"""
    try:
        ohlcv = exchange.fetch_ohlcv('BTC/USDT', '1h', limit=50)
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
        
        if price <= low_20 * 1.005 and rsi < 40:
            return f"""📈 *LONG СИГНАЛ* | BTC

💰 Цена: ${price:.2f}
🎯 Уверенность: 75%
📊 RSI: {rsi:.1f}

🚪 Вход: ${price:.2f}
🛑 SL: ${price * 0.985:.2f}
🎯 TP: ${price * 1.04:.2f}

📈 R:R: 1:2.7"""
        
        elif price >= high_20 * 0.995 and rsi > 60:
            return f"""📉 *SHORT СИГНАЛ* | BTC

💰 Цена: ${price:.2f}
🎯 Уверенность: 75%
📊 RSI: {rsi:.1f}

🚪 Вход: ${price:.2f}
🛑 SL: ${price * 1.015:.2f}
🎯 TP: ${price * 0.96:.2f}

📈 R:R: 1:2.7"""
        
        else:
            return f"""⏳ *НЕТ СИГНАЛА* | BTC

💰 Цена: ${price:.2f}
📊 RSI: {rsi:.1f}
🟢 Поддержка: ${low_20:.2f}
🔴 Сопротивление: ${high_20:.2f}"""
            
    except Exception as e:
        return f"❌ Ошибка: {e}"

def get_eth_signal():
    """Сигнал по ETH"""
    try:
        ohlcv = exchange.fetch_ohlcv('ETH/USDT', '1h', limit=50)
        df = pd.DataFrame(ohlcv, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        price = df['c'].iloc[-1]
        high_20 = df['h'].iloc[-20:].max()
        low_20 = df['l'].iloc[-20:].min()
        
        if price <= low_20 * 1.005:
            return f"📈 *LONG* ETH | ${price:.2f}\n🎯 TP: ${price*1.04:.2f}"
        elif price >= high_20 * 0.995:
            return f"📉 *SHORT* ETH | ${price:.2f}\n🎯 TP: ${price*0.96:.2f}"
        else:
            return f"⏳ ETH | ${price:.2f}"
    except:
        return "❌ ETH ошибка"

def get_sol_signal():
    """Сигнал по SOL"""
    try:
        ohlcv = exchange.fetch_ohlcv('SOL/USDT', '1h', limit=50)
        df = pd.DataFrame(ohlcv, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        price = df['c'].iloc[-1]
        high_20 = df['h'].iloc[-20:].max()
        low_20 = df['l'].iloc[-20:].min()
        
        if price <= low_20 * 1.005:
            return f"📈 *LONG* SOL | ${price:.2f}"
        elif price >= high_20 * 0.995:
            return f"📉 *SHORT* SOL | ${price:.2f}"
        else:
            return f"⏳ SOL | ${price:.2f}"
    except:
        return "❌ SOL ошибка"

def handle_message(chat_id, text):
    """Обработка команд"""
    print(f"Message from {chat_id}: {text}")
    
    if text == "/start":
        send_message(chat_id, """🤖 *SMC Crypto Bot*

✅ Бот работает!

*Команды:*
/signals - сигналы BTC, ETH, SOL
/btc - только BTC
/status - статус
/help - помощь""")
    
    elif text == "/signals":
        btc = get_btc_signal()
        eth = get_eth_signal()
        sol = get_sol_signal()
        
        msg = f"🚨 *АКТИВНЫЕ СИГНАЛЫ*\n\n{btc}\n\n{eth}\n\n{sol}"
        send_message(chat_id, msg)
    
    elif text == "/btc":
        send_message(chat_id, get_btc_signal())
    
    elif text == "/status":
        send_message(chat_id, "✅ *Статус*\nБот: активен\nВерсия: 1.0\nМониторинг: BTC, ETH, SOL")
    
    elif text == "/help":
        send_message(chat_id, "📋 *Команды:*\n/start - запуск\n/signals - все сигналы\n/btc - BTC\n/status - статус\n/help - помощь")
    
    else:
        send_message(chat_id, f"⚠️ Неизвестно: {text}\n/help")

# ==================== ОСНОВНОЙ ЦИКЛ ====================

print("🚀 SMC Crypto Bot запущен (polling mode)")
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
