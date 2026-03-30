import requests
import time
import ccxt
import pandas as pd
import numpy as np
import json
import os
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import io

TELEGRAM_TOKEN = "8645396589:AAHIceq907-38mvWJfa9BRaQWsrzC86ivNU"
LAST_UPDATE_ID = 0

os.makedirs('data', exist_ok=True)

# ==================== КОНФИГУРАЦИЯ ====================
RISK_PER_TRADE = 3

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

# ==================== БИРЖА ====================
print("🔌 Подключение к KuCoin...")
exchange = ccxt.kucoin({'enableRateLimit': True})

try:
    ticker = exchange.fetch_ticker('BTC/USDT')
    print(f"✅ KuCoin подключена! BTC: ${ticker['last']:.2f}")
except Exception as e:
    print(f"❌ Ошибка: {e}")
    exchange = None

# ==================== АНАЛИЗ ====================
def get_analysis(symbol):
    if not exchange:
        return None
    try:
        ohlcv = exchange.fetch_ohlcv(f"{symbol}/USDT", '1h', limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        current_price = df['close'].iloc[-1]
        support = df['low'].iloc[-20:].min()
        resistance = df['high'].iloc[-20:].max()
        
        # Простой сигнал
        signal = None
        if current_price <= support * 1.01:
            signal = {'signal': 'LONG', 'entry': current_price, 'sl': current_price * 0.985, 'tp': current_price * 1.03, 'confidence': 70}
        elif current_price >= resistance * 0.99:
            signal = {'signal': 'SHORT', 'entry': current_price, 'sl': current_price * 1.015, 'tp': current_price * 0.97, 'confidence': 70}
        
        return {
            'price': current_price,
            'signal': signal,
            'support': support,
            'resistance': resistance,
            'df': df,
            'exchange': 'KuCoin'
        }
    except Exception as e:
        print(f"Error: {e}")
        return None

# ==================== ГРАФИК ====================
def make_chart(symbol, analysis):
    if not analysis or analysis.get('df') is None:
        return None
    
    df = analysis['df'].tail(50)
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    # Рисуем линию цены
    ax.plot(df['timestamp'], df['close'], color='white', linewidth=2, label='Price')
    
    # Текущая цена
    current_price = df['close'].iloc[-1]
    ax.axhline(y=current_price, color='yellow', linestyle='-', linewidth=1.5, 
               label=f'Price: ${current_price:.2f}')
    
    # Уровни
    ax.axhline(y=analysis['support'], color='cyan', linestyle='--', linewidth=1, 
               label=f'Support: ${analysis["support"]:.2f}')
    ax.axhline(y=analysis['resistance'], color='orange', linestyle='--', linewidth=1, 
               label=f'Resistance: ${analysis["resistance"]:.2f}')
    
    # Сигнал
    signal = analysis.get('signal')
    if signal:
        color = 'green' if signal['signal'] == 'LONG' else 'red'
        ax.axhline(y=signal['entry'], color=color, linestyle='-', linewidth=2, 
                   label=f'Entry: ${signal["entry"]:.2f}')
        ax.axhline(y=signal['sl'], color='red', linestyle='--', linewidth=1.5, 
                   label=f'SL: ${signal["sl"]:.2f}')
        ax.axhline(y=signal['tp'], color='lime', linestyle='--', linewidth=1.5, 
                   label=f'TP: ${signal["tp"]:.2f}')
    
    # Оформление
    ax.set_title(f'{symbol} | SMC Analysis', fontsize=14, fontweight='bold', color='white')
    ax.set_ylabel('Price (USDT)', color='white')
    ax.legend(loc='upper left')
    ax.grid(True, alpha=0.3)
    ax.set_facecolor('#0a0a0a')
    fig.patch.set_facecolor('#0a0a0a')
    
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100, bbox_inches='tight', facecolor='#0a0a0a')
    buf.seek(0)
    plt.close()
    
    return buf

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

def handle_message(chat_id, text):
    print(f"Message: {text}")
    settings = get_global_settings()
    watchlist = get_global_watchlist()
    
    if text == "/start":
        msg = f"""🤖 *SMC CRYPTO BOT*

📊 *Команды:*
/add BTC,ETH,SOL — добавить монеты
/remove DOGE — удалить
/list — список
/signals — сигналы
/all_signals — сигналы по всем стилям
/chart BTC — график
/analyze PEPE — анализ
/take LONG BTC 65000 100 5 — открыть сделку
/close 123 — закрыть
/trades — активные сделки
/history — история
/stats — статистика
/pnl — P&L
/reset_trades — сброс
/style scalp|day|swing — стиль
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
            if analysis and analysis.get('signal'):
                s = analysis['signal']
                emoji = "📈" if s['signal'] == 'LONG' else "📉"
                msg += f"{emoji} *{sym}* | {s['signal']}\n   💰 Вход: ${s['entry']:.2f}\n   🛑 SL: ${s['sl']:.2f}\n   🎯 TP: ${s['tp']:.2f}\n   🎯 Увер: {s['confidence']}%\n\n"
            else:
                msg += f"⏳ *{sym}* | нет сигнала\n\n"
        send_message(chat_id, msg[:4000])
    
    elif text == "/all_signals":
        settings['style'] = 'day'
        handle_message(chat_id, "/signals")  # Без await!
    
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
                    caption += f"\n🎯 Сигнал: {analysis['signal']['signal']}"
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
            msg = f"📊 *{sym}* | Цена: ${analysis['price']:.2f}\n🟢 Поддержка: ${analysis['support']:.2f}\n🔴 Сопротивление: ${analysis['resistance']:.2f}"
            if analysis.get('signal'):
                s = analysis['signal']
                msg += f"\n\n🔥 *СИГНАЛ {s['signal']}* | Увер: {s['confidence']}%\n🚪 Вход: ${s['entry']:.2f}\n🛑 SL: ${s['sl']:.2f}\n🎯 TP: ${s['tp']:.2f}"
            send_message(chat_id, msg)
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
    
    elif text == "/status":
        msg = f"""✅ *СТАТУС*

🏦 Биржа: KuCoin
🎯 Стиль: {settings['style'].upper()}
📋 Монет: {len(watchlist)}
🔄 Активных сделок: {len(trade_manager.get_active_trades())}
🔔 Уведомления: {'ВКЛ' if settings.get('notifications_enabled') else 'ВЫКЛ'}"""
        send_message(chat_id, msg)
    
    elif text == "/help":
        send_message(chat_id, "📋 *КОМАНДЫ*\n/add BTC\n/remove DOGE\n/list\n/signals\n/all_signals\n/chart BTC\n/analyze PEPE\n/take LONG BTC 65000 100 5\n/close 123\n/trades\n/history\n/stats\n/pnl\n/reset_trades\n/style day\n/status\n/help")
    
    else:
        send_message(chat_id, f"⚠️ Неизвестно: {text}\n/help")

print("=" * 60)
print("🚀 SMC BOT — ПРОСТАЯ ВЕРСИЯ")
print("✅ Бот запущен, ожидание сообщений...")
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
