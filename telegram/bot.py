from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes
import matplotlib.pyplot as plt
import io

class TelegramBot:
    def __init__(self, token, chat_id, analyzer, trader, config):
        self.token = token
        self.chat_id = chat_id
        self.analyzer = analyzer
        self.trader = trader
        self.config = config
        self.application = None
        self.watchlist = config.get('watchlist', ['BTC/USDT', 'ETH/USDT', 'SOL/USDT'])
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = f"""
🤖 *SMC CRYPTO BOT*

📊 *Статус:* 🟢 Активен
🎯 *Стиль:* {self.config['strategy']['style'].upper()}
📈 *Режим:* {"🟢 Торговля" if self.config['trading']['enabled'] else "🔴 Только сигналы"}

*Команды:*
/signals - активные сигналы
/status - статус бота
/positions - открытые позиции
/trades - история сделок
/chart BTC - график с уровнями
/dashboard - мобильный дашборд
/start_trading - включить торговлю
/stop_trading - выключить торговлю
/help - помощь
"""
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def signals_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🔍 *Поиск сигналов...*", parse_mode='Markdown')
        signals = []
        for symbol in self.watchlist:
            df = self.analyzer.fetch_data(symbol, '1h')
            if df is not None:
                df = self.analyzer.calculate_indicators(df)
                df = self.analyzer.find_order_blocks(df)
                signal = self.analyzer.generate_signal(df, style=self.config['strategy']['style'])
                if signal:
                    signals.append((symbol, signal))
        
        if not signals:
            await update.message.reply_text("⏳ *Нет активных сигналов*", parse_mode='Markdown')
            return
        
        message = "🚨 *АКТИВНЫЕ СИГНАЛЫ*\n\n"
        for symbol, signal in signals:
            emoji = "📈" if signal['type'] == 'LONG' else "📉"
            message += f"{emoji} *{symbol}* | {signal['type']}\n"
            message += f"   🎯 Уверенность: {signal['confidence']}%\n"
            message += f"   💰 Вход: ${signal['entry']}\n"
            message += f"   🛑 SL: ${signal['stop_loss']}\n"
            message += f"   🎯 TP: ${signal['take_profit']}\n\n"
        await update.message.reply_text(message[:4096], parse_mode='Markdown')
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        balance = self.trader.get_balance()
        if balance:
            message = f"""
📊 *СТАТУС БОТА*

💰 *Баланс:* ${balance['total']:,.2f}
📈 *Режим:* {"Торговля" if self.config['trading']['enabled'] else "Только сигналы"}
🎯 *Стиль:* {self.config['strategy']['style'].upper()}
📊 *Сегодня:* {self.trader.daily_pnl:+.2f}%
🔄 *Позиций:* {len(self.trader.positions)}
"""
        else:
            message = "❌ Не удалось получить баланс"
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def positions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.trader.positions:
            await update.message.reply_text("📭 *Нет открытых позиций*", parse_mode='Markdown')
            return
        message = "📊 *ОТКРЫТЫЕ ПОЗИЦИИ*\n\n"
        for symbol, pos in self.trader.positions.items():
            emoji = "📈" if pos['type'] == 'LONG' else "📉"
            message += f"{emoji} *{symbol}* | {pos['type']}\n"
            message += f"   💰 Вход: ${pos['entry']}\n"
            message += f"   🛑 SL: ${pos['stop_loss']}\n"
            message += f"   🎯 TP: ${pos['take_profit']}\n\n"
        await update.message.reply_text(message[:4096], parse_mode='Markdown')
    
    async def trades_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.trader.trades_history:
            await update.message.reply_text("📭 *Нет истории сделок*", parse_mode='Markdown')
            return
        recent = self.trader.trades_history[-10:]
        message = "📜 *ПОСЛЕДНИЕ СДЕЛКИ*\n\n"
        for trade in reversed(recent):
            emoji = "✅" if trade['pnl_pct'] > 0 else "❌"
            message += f"{emoji} *{trade['symbol']}* | {trade['type']}\n"
            message += f"   💰 P&L: {trade['pnl_pct']:+.2f}%\n\n"
        await update.message.reply_text(message[:4096], parse_mode='Markdown')
    
    async def chart_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("📝 *Пример:* `/chart BTC`", parse_mode='Markdown')
            return
        symbol = context.args[0].upper()
        if not symbol.endswith('/USDT'):
            symbol = f"{symbol}/USDT"
        
        await update.message.reply_text(f"📊 *Генерирую график для {symbol}...*", parse_mode='Markdown')
        
        df = self.analyzer.fetch_data(symbol, '1h')
        if df is not None:
            df = self.analyzer.calculate_indicators(df)
            df = self.analyzer.find_order_blocks(df)
            signal = self.analyzer.generate_signal(df, style=self.config['strategy']['style'])
            
            fig, ax = plt.subplots(figsize=(12, 8))
            dates = df.index[-100:]
            closes = df['close'].iloc[-100:]
            ax.plot(dates, closes, color='white', linewidth=1)
            ax.fill_between(dates, df['low'].iloc[-100:], df['high'].iloc[-100:], alpha=0.2, color='gray')
            
            if signal:
                ax.axhline(y=signal['entry'], color='green', linestyle='-', linewidth=2, label=f'Entry: ${signal["entry"]}')
                ax.axhline(y=signal['stop_loss'], color='red', linestyle='--', label=f'SL: ${signal["stop_loss"]}')
                ax.axhline(y=signal['take_profit'], color='blue', linestyle='--', label=f'TP: ${signal["take_profit"]}')
            
            ax.legend()
            ax.set_title(f"{symbol} - SMC Analysis")
            ax.set_ylabel('Price (USDT)')
            ax.grid(True, alpha=0.3)
            ax.set_facecolor('#0f0f1a')
            fig.patch.set_facecolor('#0a0a0a')
            
            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=100, bbox_inches='tight', facecolor='#0a0a0a')
            buf.seek(0)
            plt.close()
            await update.message.reply_photo(photo=buf)
        else:
            await update.message.reply_text(f"❌ Не удалось загрузить данные для {symbol}")
    
    async def dashboard_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        import requests
        try:
            external_ip = requests.get('https://api.ipify.org', timeout=5).text
        except:
            external_ip = "localhost"
        message = f"📱 *МОБИЛЬНЫЙ ДАШБОРД*\n\nОткройте в браузере:\n`http://{external_ip}:8000`"
        keyboard = [[InlineKeyboardButton("🌐 Открыть дашборд", url=f"http://{external_ip}:8000")]]
        await update.message.reply_text(message, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    
    async def start_trading_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.config['trading']['enabled'] = True
        await update.message.reply_text("✅ *Автоматическая торговля ВКЛЮЧЕНА*", parse_mode='Markdown')
    
    async def stop_trading_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.config['trading']['enabled'] = False
        await update.message.reply_text("⏸️ *Автоматическая торговля ВЫКЛЮЧЕНА*", parse_mode='Markdown')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.start_command(update, context)
    
    def run(self):
        self.application = Application.builder().token(self.token).build()
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("signals", self.signals_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("positions", self.positions_command))
        self.application.add_handler(CommandHandler("trades", self.trades_command))
        self.application.add_handler(CommandHandler("chart", self.chart_command))
        self.application.add_handler(CommandHandler("dashboard", self.dashboard_command))
        self.application.add_handler(CommandHandler("start_trading", self.start_trading_command))
        self.application.add_handler(CommandHandler("stop_trading", self.stop_trading_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.run_polling()
