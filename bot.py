import requests
import pandas as pd
import numpy as np
import time
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
IG_USER_ID = "17841449038057212"

coins = ["BTCUSDT", "ETHUSDT"]

def get_price(symbol):
    # Using Binance.US to bypass Render's US server restrictions
    url = f"https://api.binance.us/api/v3/klines?symbol={symbol}&interval=1h&limit=100"
    data = requests.get(url).json()
    
    # Safety Net: If Binance returns an error message instead of price data
    if isinstance(data, dict):
        print(f"Binance API Error for {symbol}: {data}")
        # Return dummy data that WON'T trigger a breakout (last price is lower than max)
        return pd.Series([100.0] * 99 + [50.0]) 
        
    close = [float(x[4]) for x in data]
    return pd.Series(close)

def analyze_trend(series):
    ema20 = series.ewm(span=20).mean()
    ema50 = series.ewm(span=50).mean()
    return 1 if ema20.iloc[-1] > ema50.iloc[-1] else -1

def detect_breakout(series):
    resistance = series.max()
    return series.iloc[-1] > resistance * 0.995

def generate_caption(symbol, bias):
    coin = symbol.replace("USDT","")
    return f"""{coin} Breakout Setup 📈
Multi timeframe alignment
Bias: {bias}

Follow @desicryptopro
#crypto #{coin.lower()} #trading"""

def post(image_url, caption):
    url = f"https://graph.facebook.com/v18.0/{IG_USER_ID}/media"
    payload = {
        "image_url": image_url,
        "caption": caption,
        "access_token": ACCESS_TOKEN
    }
    r = requests.post(url, data=payload)
    
    if "id" not in r.json():
        print("Error creating media container:", r.json())
        return
        
    creation_id = r.json()["id"]

    publish_url = f"https://graph.facebook.com/v18.0/{IG_USER_ID}/media_publish"
    pub_r = requests.post(publish_url, data={
        "creation_id": creation_id,
        "access_token": ACCESS_TOKEN
    })
    print("Publish response:", pub_r.json())

# --- THIS IS YOUR BOT LOOP ---
def run_bot():
    print("Trading bot started in the background!")
    while True:
        try:
            for coin in coins:
                data = get_price(coin)
                trend = analyze_trend(data)
                breakout = detect_breakout(data)

                if breakout:
                    bias = "LONG" if trend == 1 else "SHORT"
                    image = f"https://dummyimage.com/1080x1080/000/fff&text={coin}+{bias}"
                    caption = generate_caption(coin, bias)
                    post(image, caption)
                    print("Posted:", coin)
        except Exception as e:
            print(f"Error in bot loop: {e}")
            
        time.sleep(3600)

# --- THIS IS THE DUMMY SERVER FOR RENDER ---
class DummyServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is awake and running!")

if __name__ == "__main__":
    # Start the bot loop in a separate thread so it doesn't block the server
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.daemon = True 
    bot_thread.start()
    
    # Open the web server port for Render
    port = int(os.environ.get('PORT', 10000))
    server = HTTPServer(('0.0.0.0', port), DummyServer)
    print(f"Dummy web server listening on port {port}...")
    server.serve_forever()
