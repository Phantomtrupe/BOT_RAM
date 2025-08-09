from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import logging
import threading
import requests
import os
from typing import Optional

# ---------- Logging ----------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------- Token loader ----------
def get_bot_token() -> Optional[str]:
    token = os.getenv("BOT_TOKEN")
    if token:
        return token
    # try .env fallback
    try:
        with open(".env", "r") as f:
            for line in f:
                if line.strip().startswith("BOT_TOKEN="):
                    return line.split("=", 1)[1].strip().strip('"\'')
    except FileNotFoundError:
        pass
    return None

TOKEN = get_bot_token()
PORT = int(os.getenv("PORT", 5000))

# ---------- Business logic (your handlers) ----------
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
    try:
        url = "https://open.er-api.com/v6/latest/USD"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        rates = data.get("rates", {})
        # prefer uppercase "KGS"
        for key in ("KGS", "kgs"):
            if key in rates:
                return float(rates[key])
        raise KeyError("KGS not found in rates")
    except Exception as e:
        logger.error("Error fetching USD->KGS: %s", e)
        return None

def get_coin_price(coin: str) -> Optional[float]:
    try:
        pair = SUPPORTED_COINS[coin]
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={pair}"
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        return float(r.json()["price"])
    except Exception as e:
        logger.error("Error fetching %s price: %s", coin, e)
        return None

# Handlers (async as required by PTB)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я работаю на Render и запущен как веб-сервис.\n"
        "Используй /help для списка команд."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🤖 **Криптовалютный калькулятор**\n\n"
        "**Команды:**\n"
        "/calc <монета> <количество> - рассчитать в сомах\n"
        "/rates - показать текущие курсы\n"
        "/help - показать эту справку\n\n"
        f"Поддерживаемые монеты: {', '.join([c.upper() for c in SUPPORTED_COINS.keys()])}\n\n"
        "Примеры:\n"
        "`/calc btc 0.001`\n"
        "`/calc eth 0.5`"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def calc(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            raise ValueError()
    except ValueError:
        await update.message.reply_text("⚠️ Неверный формат суммы.")
        return

    loading = await update.message.reply_text("🔄 Получаю актуальные курсы...")

    coin_price = get_coin_price(coin)
    if coin_price is None:
        await loading.edit_text("🚫 Не удалось получить курс монеты.")
        return

    kgs_rate = get_usdt_to_kgs()
    if kgs_rate is None:
        await loading.edit_text("🚫 Не удалось получить курс доллара к сому.")
        return

    usdt_value = amount * coin_price
    total_kgs = usdt_value * kgs_rate

    await loading.edit_text(
        f"💰 **Обмен {amount} {coin.upper()}**\n\n"
        f"📊 Курс {coin.upper()}/USDT: `${coin_price:,.2f}`\n"
        f"💵 Стоимость в USDT: `${usdt_value:,.2f}`\n"
        f"🇰🇬 Курс USD/KGS: `{kgs_rate:.2f}`\n\n"
        f"💸 **Итого: {total_kgs:,.2f} сом**",
        parse_mode="Markdown"
    )

async def rates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    loading = await update.message.reply_text("🔄 Загружаю курсы...")
    lines = ["📈 **Актуальные курсы криптовалют**", ""]
    for coin_symbol in SUPPORTED_COINS.keys():
        price = get_coin_price(coin_symbol)
        if price is not None:
            lines.append(f"{coin_symbol.upper()}: `${price:,.2f}`")
        else:
            lines.append(f"{coin_symbol.upper()}: ❌ недоступно")

    kgs_rate = get_usdt_to_kgs()
    if kgs_rate:
        lines.append("")
        lines.append(f"💵 USD/KGS: `{kgs_rate:.2f}`")

    await loading.edit_text("\n".join(lines), parse_mode="Markdown")

# ---------- Create Telegram app ----------
def build_tg_app(token: str) -> Application:
    tg_app = Application.builder().token(token).build()
    tg_app.add_handler(CommandHandler("start", start))
    tg_app.add_handler(CommandHandler("help", help_command))
    tg_app.add_handler(CommandHandler("calc", calc))
    tg_app.add_handler(CommandHandler("rates", rates))
    return tg_app

# ---------- Flask web app (keeps Render happy) ----------
flask_app = Flask(__name__)

@flask_app.route("/", methods=["GET"])
def index():
    return "OK - bot is running (web service + polling).", 200

@flask_app.route("/health", methods=["GET"])
def health():
    return "healthy", 200

# ---------- Entrypoint ----------
def main():
    if not TOKEN:
        logger.error("BOT_TOKEN not found. Set BOT_TOKEN env variable or .env file.")
        print("❌ BOT_TOKEN not found. Set BOT_TOKEN env variable or .env file.")
        return

    tg_app = build_tg_app(TOKEN)

    def run_telegram_polling():
        try:
            logger.info("Starting telegram polling in background thread...")
            tg_app.run_polling(poll_interval=3.0)
        except Exception as e:
            logger.exception("Telegram polling stopped: %s", e)

    # Start telegram polling in a daemon thread
    t = threading.Thread(target=run_telegram_polling, daemon=True)
    t.start()

    # Run flask (blocking) — Render expects the process to listen on PORT
    logger.info("Starting Flask on 0.0.0.0:%s", PORT)
    flask_app.run(host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    main()
