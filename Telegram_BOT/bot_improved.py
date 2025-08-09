from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import telegram
import requests
import asyncio
import os
from typing import Optional, Dict
import logging

# new imports
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
    """Get bot token from environment variable or .env file"""
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

TOKEN = get_bot_token()

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

# ... (оставьте функции get_usdt_to_kgs, get_coin_price, calc, rates, help_command, start без изменений) ...
# For brevity I'm assuming the rest of your handler functions stay exactly as you provided.

# ---------- lightweight health HTTP server (no extra deps) ----------
START_TIME = time.time()
_FAKE_REQUESTS = 0
_FAKE_LOCK = threading.Lock()

class HealthHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # отключаем лишний вывод в stdout (можно убрать если нужно)
        logging.info("%s - - [%s] %s\n" %
                     (self.client_address[0],
                      self.log_date_time_string(),
                      format%args))

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
    """Start a small HTTP server on PORT (Render requires binding to $PORT)."""
    port = int(os.getenv("PORT", "8000"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logging.info("Health server started on 0.0.0.0:%d", port)
    return server

def start_fake_traffic(interval_seconds: int = 25):
    """Optionally send periodic requests to our own server to create 'pseudo' traffic."""
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
    """Start the bot and the health server (required by Render free web service)."""
    if not TOKEN:
        print("❌ Error: BOT_TOKEN not found!")
        print("\n📋 To fix this issue, you can:")
        print("1. Set environment variable: export BOT_TOKEN='your_bot_token_here'")
        print("2. Create a .env file in the same directory with: BOT_TOKEN=your_bot_token_here")
        return

    # Start minimal HTTP server so Render sees a bound port
    health_server = start_health_server()

    # Optionally start fake traffic to simulate incoming connections (so the server shows activity)
    # You can reduce frequency or disable if not needed.
    start_fake_traffic(interval_seconds=30)

    app = Application.builder().token(TOKEN).build()

    # Add handlers (same as before)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("calc", calc))
    app.add_handler(CommandHandler("rates", rates))
    app.add_handler(CommandHandler("help", help_command))

    logging.info("python-telegram-bot version: %s", telegram.__version__)
    print("🚀 Bot starting...")

    try:
        # This will run forever (polling) while health server runs in background thread
        app.run_polling()
    except Exception as e:
        logging.error(f"Failed to start bot: {e}")
        print(f"❌ Failed to start bot: {e}")

if __name__ == "__main__":
    main()
