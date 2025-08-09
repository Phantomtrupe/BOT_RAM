from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import requests
import os
from typing import Optional, Dict
import logging

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Secure token loading with fallback
def get_bot_token():
    """Get bot token from environment variable or .env file"""
    # Try environment variable first
    token = os.getenv('BOT_TOKEN')
    if token:
        return token
    
    # Try loading from .env file
    try:
        with open('.env', 'r') as f:
            for line in f:
                if line.startswith('BOT_TOKEN='):
                    return line.split('=', 1)[1].strip().strip('"\'')
    except FileNotFoundError:
        pass
    
    # Fallback to hardcoded token (not recommended for production)
    print("⚠️ Warning: Using hardcoded token. Please set BOT_TOKEN environment variable or create .env file for better security!")
    return "7961938964:AAHGGc0uGTMde2DpQ6tDKeI031UXpY6HG0s"

TOKEN = get_bot_token()

# Expanded coin support
SUPPORTED_COINS = {
    "btc": "BTCUSDT",
    "eth": "ETHUSDT", 
    "ltc": "LTCUSDT",
    "ada": "ADAUSDT",
    "dot": "DOTUSDT",
    "bnb": "BNBUSDT",
    "xrp": "XRPUSDT",
    "sol": "SOLUSDT"
}

def get_usdt_to_kgs() -> Optional[float]:
    """
    Get USD → KGS exchange rate from Open ER-API.
    """
    try:
        url = "https://open.er-api.com/v6/latest/USD"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        rates = data.get("rates", {})

        # Try to get KGS rate (case variations)
        for key in ["KGS", "kgs"]:
            if key in rates:
                return float(rates[key])
        
        raise KeyError("Rate for KGS not found")

    except Exception as e:
        logging.error(f"Error fetching USDT→KGS rate: {e}")
        return None

def get_coin_price(coin: str) -> Optional[float]:
    """
    Get cryptocurrency price in USDT from Binance API.
    """
    try:
        pair = SUPPORTED_COINS[coin]
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={pair}"
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        return float(r.json()["price"])
    except Exception as e:
        logging.error(f"Error fetching {coin} price: {e}")
        return None

async def calc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Calculate cryptocurrency to KGS conversion."""
    if len(context.args) != 2:
        await update.message.reply_text(
            "⚠️ Используй: /calc <монета> <количество>\n"
            f"Поддерживаемые монеты: {', '.join(SUPPORTED_COINS.keys())}"
        )
        return

    coin, amount_str = context.args[0].lower(), context.args[1]
    
    if coin not in SUPPORTED_COINS:
        await update.message.reply_text(
            f"⚠️ Поддерживаются только: {', '.join(SUPPORTED_COINS.keys())}"
        )
        return

    try:
        amount = float(amount_str)
        if amount <= 0:
            await update.message.reply_text("⚠️ Количество должно быть положительным числом.")
            return
    except ValueError:
        await update.message.reply_text("⚠️ Неверный формат суммы.")
        return

    # Show loading message
    loading_msg = await update.message.reply_text("🔄 Получаю актуальные курсы...")

    # 1) Get coin price in USDT
    coin_price = get_coin_price(coin)
    if coin_price is None:
        await loading_msg.edit_text("🚫 Не удалось получить курс монеты.")
        return

    # 2) Get USDT → KGS rate
    kgs_rate = get_usdt_to_kgs()
    if kgs_rate is None:
        await loading_msg.edit_text("🚫 Не удалось получить курс доллара к сому.")
        return

    # 3) Calculate total
    usdt_value = amount * coin_price
    total_kgs = usdt_value * kgs_rate

    await loading_msg.edit_text(
        f"💰 **Обмен {amount} {coin.upper()}**\n\n"
        f"📊 Курс {coin.upper()}/USDT: `${coin_price:,.2f}`\n"
        f"💵 Стоимость в USDT: `${usdt_value:,.2f}`\n"
        f"🇰🇬 Курс USD/KGS: `{kgs_rate:.2f}`\n\n"
        f"💸 **Итого: {total_kgs:,.2f} сом**",
        parse_mode='Markdown'
    )

async def rates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current rates for all supported coins."""
    loading_msg = await update.message.reply_text("🔄 Загружаю курсы...")
    
    rates_text = "📈 **Актуальные курсы криптовалют**\n\n"
    
    for coin_symbol in SUPPORTED_COINS.keys():
        price = get_coin_price(coin_symbol)
        if price:
            rates_text += f"{coin_symbol.upper()}: `${price:,.2f}`\n"
        else:
            rates_text += f"{coin_symbol.upper()}: ❌ недоступно\n"
    
    # Add KGS rate
    kgs_rate = get_usdt_to_kgs()
    if kgs_rate:
        rates_text += f"\n💵 USD/KGS: `{kgs_rate:.2f}`"
    
    await loading_msg.edit_text(rates_text, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help information."""
    help_text = (
        "🤖 **Криптовалютный калькулятор**\n\n"
        "**Команды:**\n"
        "/calc <монета> <количество> - рассчитать в сомах\n"
        "/rates - показать текущие курсы\n"
        "/help - показать эту справку\n\n"
        "**Поддерживаемые монеты:**\n"
        f"{', '.join([coin.upper() for coin in SUPPORTED_COINS.keys()])}\n\n"
        "**Примеры:**\n"
        "`/calc btc 0.001`\n"
        "`/calc eth 0.5`\n"
        "`/calc ltc 2`"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler."""
    await update.message.reply_text(
        "👋 Привет! Я помогу рассчитать стоимость криптовалют в сомах.\n\n"
        "Используй /help для получения списка команд."
    )

def main():
    """Start the bot."""
    if not TOKEN:
        print("❌ Error: BOT_TOKEN not found!")
        return
        
    app = Application.builder().token(TOKEN).build()
    
    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("calc", calc))
    app.add_handler(CommandHandler("rates", rates))
    app.add_handler(CommandHandler("help", help_command))
    
    print("🚀 Bot starting...")
    app.run_polling()

if __name__ == "__main__":
    main()
