#!/usr/bin/env python3
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import telegram
import requests
import asyncio
import os
from typing import Optional, Dict
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import time
import json

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Secure token loading with fallback
def get_bot_token():
    token = os.getenv('BOT_TOKEN')
    if token:
        return token
    try:
        with open('.env', 'r') as f:
            for line in f:
                if line.startswith('BOT_TOKEN='):
                    return line.split('=', 1)[1].strip().strip('"\'')
    except FileNotFoundError:
        pass
    return None

TOKEN = get_bot_token()

# Supported coins
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
        for key in ["KGS", "kgs"]:
            if key in rates:
                return float(rates[key])
        raise KeyError("Rate for KGS not found")
    except Exception as e:
        logging.error(f"Error fetching USDT→KGS rate: {e}")
        return None

def get_coin_price(coin: str) -> Optional[float]:
    try:
        pair = SUPPORTED_COINS[coin]
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={pair}"
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        return float(r.json()["price"])
    except Exception as e:
        logging.error(f"Error fetching {coin} price: {e}")
        return None

# --- Handlers (обязательно ДО main) ---
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
            await update.message.reply_text("⚠️ Количество должно быть положительным числом.")
            return
    except ValueError:
        await update.message.reply_text("⚠️ Неверный формат суммы.")
        return

    loading_msg = await update.message.reply_text("🔄 Получаю актуальные курсы...")
    coin_price = get_coin_price(coin)
    if coin_price is None:
        await loading_msg.edit_text("🚫 Не удалось получить курс монеты.")
        return

    kgs_rate = get_usdt_to_kgs()
    if kgs_rate is None:
        await loading_msg.edit_text("🚫 Не удалось получить курс доллара к сому.")
        return

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
    loading_msg = await update.message.reply_text("🔄 Загружаю курсы...")
    rates_text = "📈 **Актуальные курсы криптовалют**\n\n"
    for coin_symbol in SUPPORTED_COINS.keys():
        price = get_coin_price(coin_symbol)
        if price:
            rates_text += f"{coin_symbol.upper()}: `${price:,.2f}`\n"
        else:
            rates_text += f"{coin_symbol.upper()}: ❌ недоступно\n"

    kgs_rate = get_usdt_to_kgs()
    if kgs_rate:
        rates_text += f"\n💵 USD/KGS: `{kgs_rate:.2f}`"

    await loading_msg.edit_text(rates_text, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    await update.message.reply_text(
        "👋 Привет! Я помогу рассчитать стоимость криптовалют в сомах.\n\n"
        "Используй /help для получения списка команд."
    )

# ---------- lightweight health HTTP server ----------
START_TIME = time.time()
_FAKE_REQUESTS = 0
_FAKE_LOCK = threading.Lock()

class HealthHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        logging.info("%s - - [%s] %s", self.client_address[0], self.log_date_time_string(), format % args)

    def do_GET(self):
        global _FAKE_REQUESTS
        if self.path in ("/", "/health"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"OK")
        elif self.path == "/metrics":
            uptime = time.time() - START_TIME
            with _FAKE_LOCK:
                fake = _FAKE_REQUESTS
            payload = {"uptime_seconds": int(uptime), "fake_requests": fake}
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

def start_health_server():
    port = int(os.getenv("PORT", "8000"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logging.info("Health server started on 0.0.0.0:%d", port)
    return server

def start_fake_traffic(interval_seconds: int = 25):
    port = int(os.getenv("PORT", "8000"))
    def loop():
        global _FAKE_REQUESTS
        url = f"http://127.0.0.1:{port}/"
        while True:
            try:
                requests.get(url, timeout=5)
                with _FAKE_LOCK:
                    _FAKE_REQUESTS += 1
            except Exception as e:
                logging.debug("Fake traffic request failed: %s", e)
            time.sleep(interval_seconds)
    t = threading.Thread(target=loop, daemon=True)
    t.start()
    logging.info("Started fake traffic thread (every %ds) to localhost:%d", interval_seconds, port)

# ---------- main ----------
def main():
    if not TOKEN:
        print("❌ Error: BOT_TOKEN not found!")
        print("1) export BOT_TOKEN='your_bot_token'")
        print("2) or create .env with BOT_TOKEN=your_bot_token")
        return

    # Start health server BEFORE starting the bot
    start_health_server()
    # start fake requests (optional)
    start_fake_traffic(interval_seconds=30)

    app = Application.builder().token(TOKEN).build()

    # Now handlers can be added because they are defined above
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("calc", calc))
    app.add_handler(CommandHandler("rates", rates))
    app.add_handler(CommandHandler("help", help_command))

    logging.info("python-telegram-bot version: %s", telegram.__version__)
    print("🚀 Bot starting...")

    try:
        app.run_polling()
    except Exception as e:
        logging.error(f"Failed to start bot: {e}")
        print(f"❌ Failed to start bot: {e}")

if __name__ == "__main__":
    main()
