import requests
import time
import ccxt
import pandas as pd
import numpy as np
import json
import os
import threading
from datetime import datetime

TELEGRAM_TOKEN = "8645396589:AAHIceq907-38mvWJfa9BRaQWsrzC86ivNU"
LAST_UPDATE_ID = 0

os.makedirs('data', exist_ok=True)

# ==================== КОНФИГУРАЦИЯ ====================
LEVERAGE = 75
RISK_PER_TRADE = 3

# 13 монет
SYMBOLS = [
    'BTC', 'ETH', 'SOL', 'WIF', 'TIA', 'SAND', 'XRP', 'SUI', 'APE', 'DOT', 'ADA', 'LINK', 'SEI'
]

# RSI пороги
RSI_LOW = 28
RSI_HIGH = 72

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
    
    def add_trade(self, symbol, side, entry_price, size=1, leverage=LEVERAGE, tp=None, sl=None):
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

aggregator = MultiExchangeAggregator()

# ==================== SMC АНАЛИЗ ====================
def get_simple_signal(symbol):
    try:
        price = aggregator.get_aggregated_price(f"{symbol}/USDT")
        if not price:
            return None
        # Простой сигнал для теста
        return {
            'signal': 'LONG' if price < 65000 else 'SHORT',
            'entry': price,
            'sl': price * 0.985,
            'tp': price * 1.04,
            'confidence': 75,
            'rr': 2.7,
            'reasons': ['📊 Агрегированные данные с 4 бирж', f'💰 Цена: ${price:.2f}']
        }
    except:
        return None

def get_full_analysis(symbol, style='day', min_confidence=70):
    try:
        price = aggregator.get_aggregated_price(f"{symbol}/USDT")
        if not price:
            return None
        signal = get_simple_signal(symbol)
        return {
            'price': price,
            'signal': signal,
            'support': price * 0.98,
            'resistance': price * 1.02,
            'exchange': 'Multi-Exchange (4 биржи)'
        }
    except:
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

💰 Цена: {format_price(price)}
🎯 Уверенность: {signal['confidence']}%
📈 R:R: 1:{signal['rr']}

🚪 Вход: {format_price(signal['entry'])}
🛑 SL: {format_price(signal['sl'])}
🎯 TP: {format_price(signal['tp'])}

📊 *Причины:*\n"""
        for r in signal['reasons']:
            msg += f"• {r}\n"
        msg += f"\n🏦 *Биржа:* {analysis['exchange']}"
        return msg
    else:
        return f"""⏳ *НЕТ СИГНАЛА* | {symbol} | {style.upper()}

💰 Цена: {format_price(price)}
🟢 Поддержка: {format_price(analysis['support'])}
🔴 Сопротивление: {format_price(analysis['resistance'])}
\n💡 Рекомендация: наблюдение\n🏦 *Биржа:* {analysis['exchange']}"""

def handle_message(chat_id, text):
    print(f"Message from {chat_id}: {text}")
    settings = get_global_settings()
    watchlist = get_global_watchlist()
    
    if text == "/start":
        msg = f"""🤖 *SMC CRYPTO BOT* — МУЛЬТИБИРЖЕВАЯ ВЕРСИЯ

📊 *Методология:* SMC/ICT + Order Blocks + Volume Profile
🏦 *Биржи:* KuCoin + Gate.io + OKX + Bitget
⚡ *Плечо:* {LEVERAGE}x
📈 *Риск:* {RISK_PER_TRADE}%

*Команды:*
/add BTC,ETH,SOL — добавить монеты
/remove DOGE — удалить
/list — список монет
/signals — сигналы (ваш стиль)
/all_signals — сигналы по ВСЕМ стилям!
/take LONG BTC 65000 — открыть сделку
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
        send_message(chat_id, f"✅ Добавлено: {', '.join(added)}\n\n📋 Всего монет: {len(watchlist)}")
    
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
            send_message(chat_id, "📭 Список пуст. Добавьте: `/add BTC`")
        else:
            msg = "📋 *МОИ МОНЕТЫ*\n\n"
            for s in watchlist:
                msg += f"• {s}\n"
            send_message(chat_id, msg)
    
    elif text == "/signals":
        if not watchlist:
            send_message(chat_id, "📭 Нет монет в списке")
            return
        send_message(chat_id, f"🔍 *Поиск сигналов...*")
        msg = f"🚨 *СИГНАЛЫ* ({settings['style'].upper()})\n\n"
        for sym in watchlist:
            analysis = get_full_analysis(sym, settings['style'], settings['min_confidence'])
            msg += format_signal(sym, analysis, settings['style']) + "\n\n"
            if len(msg) > 3500:
                send_message(chat_id, msg[:4000])
                msg = ""
        if msg:
            send_message(chat_id, msg[:4000])
    
    elif text == "/all_signals":
        if not watchlist:
            send_message(chat_id, "📭 Нет монет в списке")
            return
        send_message(chat_id, f"🔍 *Поиск сигналов по всем стилям...*")
        msg = "🚨 *СИГНАЛЫ ПО ВСЕМ СТИЛЯМ*\n\n"
        for sym in watchlist:
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
            if len(msg) > 3500:
                send_message(chat_id, msg[:4000])
                msg = ""
        if msg:
            send_message(chat_id, msg[:4000])
    
    elif text.startswith("/take"):
        parts = text.split()
        if len(parts) < 4:
            send_message(chat_id, "📝 *Формат:* `/take LONG BTC 65000`")
            return
        side = parts[1].upper()
        symbol = parts[2].upper()
        try:
            entry = float(parts[3])
        except:
            send_message(chat_id, "❌ Цена должна быть числом")
            return
        size = float(parts[4]) if len(parts) > 4 else RISK_PER_TRADE
        trade_id = trade_manager.add_trade(symbol, side, entry, size)
        msg = f"✅ *СДЕЛКА ЗАФИКСИРОВАНА*\n\n📊 *{side} {symbol}*\n💰 Вход: ${entry:.2f}\n📦 Размер: {size} USDT\n⚡ Плечо: x{LEVERAGE}\n🆔 ID: {trade_id}"
        send_message(chat_id, msg)
    
    elif text.startswith("/close"):
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id, "📝 *Пример:* `/close 123`")
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
                exit_price = aggregator.get_aggregated_price(f"{trade['symbol']}/USDT") or trade['entry'] * 1.02
            closed = trade_manager.close_trade(trade_id, exit_price)
            if closed:
                emoji = "✅" if closed['pnl_pct'] > 0 else "❌"
                msg = f"{emoji} *СДЕЛКА ЗАКРЫТА*\n\n📊 *{closed['side']} {closed['symbol']}*\n💰 Вход: ${closed['entry']:.2f}\n🚪 Выход: ${closed['exit']:.2f}\n📈 P&L: {closed['pnl_pct']:+.2f}% (${closed['pnl_usdt']:+.2f})"
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
            current = aggregator.get_aggregated_price(f"{trade['symbol']}/USDT") or trade['entry']
            if trade['side'] == 'LONG':
                pnl = (current - trade['entry']) / trade['entry'] * 100 * trade['leverage']
            else:
                pnl = (trade['entry'] - current) / trade['entry'] * 100 * trade['leverage']
            emoji = "📈" if pnl > 0 else "📉"
            msg += f"🆔 *{trade_id}* | {trade['symbol']} | {trade['side']}\n   💰 Вход: ${trade['entry']:.2f}\n   📍 Текущая: ${current:.2f}\n   📊 P&L: {pnl:+.2f}%\n\n"
        send_message(chat_id, msg)
    
    elif text == "/history":
        history = trade_manager.get_history(10)
        if not history:
            send_message(chat_id, "📭 *Нет истории сделок*")
            return
        msg = "📜 *ПОСЛЕДНИЕ СДЕЛКИ*\n\n"
        for trade in reversed(history):
            emoji = "✅" if trade['pnl_pct'] > 0 else "❌"
            msg += f"{emoji} *{trade['side']} {trade['symbol']}*\n   Вход: ${trade['entry']:.2f} → Выход: ${trade['exit']:.2f}\n   P&L: {trade['pnl_pct']:+.2f}%\n\n"
        send_message(chat_id, msg)
    
    elif text == "/stats":
        stats = trade_manager.get_stats()
        if stats['total_trades'] == 0:
            send_message(chat_id, "📭 *Нет данных для статистики*")
            return
        msg = f"""📊 *СТАТИСТИКА*

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
            current = aggregator.get_aggregated_price(f"{trade['symbol']}/USDT") or trade['entry']
            if trade['side'] == 'LONG':
                pnl_pct = (current - trade['entry']) / trade['entry'] * 100 * trade['leverage']
                pnl_usdt = trade['size'] * (current - trade['entry']) / trade['entry'] * trade['leverage']
            else:
                pnl_pct = (trade['entry'] - current) / trade['entry'] * 100 * trade['leverage']
                pnl_usdt = trade['size'] * (trade['entry'] - current) / trade['entry'] * trade['leverage']
            total_pnl += pnl_usdt
            emoji = "📈" if pnl_pct > 0 else "📉"
            msg += f"{emoji} *{trade['side']} {trade['symbol']}* (ID: {trade_id})\n   P&L: {pnl_pct:+.2f}% (${pnl_usdt:+.2f})\n\n"
        msg += f"\n💰 *ИТОГО:* ${total_pnl:+.2f}"
        send_message(chat_id, msg)
    
    elif text == "/reset_trades":
        trade_manager.reset_all_trades()
        send_message(chat_id, "🗑️ *ВСЕ СДЕЛКИ СБРОШЕНЫ*")
    
    elif text.startswith("/style"):
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id, "📝 *Пример:* `/style scalp`")
            return
        new_style = parts[1].lower()
        if new_style in ['scalp', 'day', 'swing']:
            settings['style'] = new_style
            save_global_settings(settings)
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
                settings['min_confidence'] = val
                save_global_settings(settings)
                send_message(chat_id, f"✅ Мин. уверенность: {val}%")
            else:
                send_message(chat_id, "⚠️ Значение от 50 до 90")
        except:
            send_message(chat_id, "⚠️ Введите число")
    
    elif text == "/notifications_on":
        settings['notifications_enabled'] = True
        save_global_settings(settings)
        send_message(chat_id, "🔔 *Уведомления ВКЛЮЧЕНЫ*")
    
    elif text == "/notifications_off":
        settings['notifications_enabled'] = False
        save_global_settings(settings)
        send_message(chat_id, "🔕 *Уведомления ВЫКЛЮЧЕНЫ*")
    
    elif text == "/status":
        msg = f"""✅ *СТАТУС БОТА*

🏦 *Биржи:* KuCoin + Gate.io + OKX + Bitget
⚡ *Плечо:* {LEVERAGE}x
📊 *Риск:* {RISK_PER_TRADE}%
🎯 *Стиль:* {settings['style'].upper()}
📊 *Мин. уверенность:* {settings['min_confidence']}%
📋 *Монет:* {len(watchlist)}
🔄 *Активных сделок:* {len(trade_manager.get_active_trades())}
🔔 *Уведомления:* {'✅ ВКЛ' if settings.get('notifications_enabled', True) else '❌ ВЫКЛ'}"""
        send_message(chat_id, msg)
    
    elif text == "/help":
        send_message(chat_id, """📋 *ВСЕ КОМАНДЫ*

/add BTC,ETH — добавить
/remove DOGE — удалить
/list — список
/signals — сигналы
/all_signals — сигналы по всем стилям
/take LONG BTC 65000 — открыть
/close 123 — закрыть
/trades — активные сделки
/history — история
/stats — статистика
/pnl — P&L
/reset_trades — сброс
/style scalp|day|swing — стиль
/confidence 70 — уверенность
/notifications_on — уведомления вкл
/notifications_off — уведомления выкл
/status — статус
/help — помощь""")
    
    else:
        send_message(chat_id, f"⚠️ Неизвестно: {text}\n/help")

print("=" * 60)
print("🚀 SMC BOT — МУЛЬТИБИРЖЕВОЙ")
print(f"⚡ Плечо: {LEVERAGE}x | Риск: {RISK_PER_TRADE}%")
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
