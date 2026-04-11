import requests
import pandas as pd
import numpy as np
import time
import os
import threading
import google.generativeai as genai
from http.server import BaseHTTPRequestHandler, HTTPServer

# --- CREDENTIALS ---
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
IG_USER_ID = "17841449038057212"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
ai_model = genai.GenerativeModel('gemini-2.5-flash')

coins = ["BTCUSDT", "ETHUSDT"]

# 1. THE SENSORS: Now accepts a specific timeframe interval
def get_market_data(symbol, interval):
    url = f"https://api.binance.us/api/v3/klines?symbol={symbol}&interval={interval}&limit=100"
    data = requests.get(url).json()
    
    if isinstance(data, dict):
        print(f"API Error on {interval}: {data}")
        return None
        
    df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'tbv', 'tqv', 'ignore'])
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
    return df

# 2. THE MATH ENGINE
def analyze_technicals(df):
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=9, adjust=False).mean()
    
    ema20 = df['close'].ewm(span=20, adjust=False).mean()
    ema50 = df['close'].ewm(span=50, adjust=False).mean()
    
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    pattern = "None"
    if prev['close'] < prev['open'] and latest['close'] > latest['open'] and latest['close'] > prev['open'] and latest['open'] < prev['close']:
        pattern = "Bullish Engulfing"
    elif prev['close'] > prev['open'] and latest['close'] < latest['open'] and latest['close'] < prev['open'] and latest['open'] > prev['close']:
        pattern = "Bearish Engulfing"

    return {
        "current_price": latest['close'],
        "rsi_14": rsi.iloc[-1],
        "macd_status": "Bullish" if macd.iloc[-1] > signal.iloc[-1] else "Bearish",
        "trend_status": "Uptrend" if ema20.iloc[-1] > ema50.iloc[-1] else "Downtrend",
        "candlestick_pattern": pattern,
        "support_level": df['low'].tail(20).min(),
        "resistance_level": df['high'].tail(20).max()
    }

# 3. THE AGENT'S BRAIN: Now processes HTF and LTF simultaneously
def generate_agentic_caption(symbol, htf_data, ltf_data):
    coin = symbol.replace("USDT", "")
    
    prompt = f"""
    You are an elite cryptocurrency technical analyst managing the Instagram account @desicryptopro.
    Analyze the following Multi-Timeframe Data for {coin} and write an engaging, professional Instagram caption.
    
    Macro Environment (Daily Chart - HTF):
    - Trend: {htf_data['trend_status']}
    - RSI: {htf_data['rsi_14']:.2f}
    - Pattern Formed: {htf_data['candlestick_pattern']}
    
    Micro Execution (1-Hour Chart - LTF):
    - Current Price: ${ltf_data['current_price']:.2f}
    - Trend: {ltf_data['trend_status']}
    - MACD: {ltf_data['macd_status']}
    - Pattern Formed: {ltf_data['candlestick_pattern']}
    - Local Support: ${ltf_data['support_level']:.2f}
    - Local Resistance: ${ltf_data['resistance_level']:.2f}
    
    Rules for the caption:
    1. Hook the reader with the Multi-Timeframe Alignment (e.g., "The daily trend is bullish, and we just got a trigger on the 1H chart!").
    2. Explain how the LTF pattern (if any) interacts with the HTF trend. Give higher weight to the HTF trend.
    3. State the exact current price, and the key support/resistance levels to watch.
    4. Give a clear overall bias (Bullish, Bearish, or Neutral).
    5. Use emojis and formatting for readability.
    6. End with: "Follow @desicryptopro for real-time market analysis!" and relevant hashtags.
    """
    
    response = ai_model.generate_content(prompt)
    return response.text

# --- INSTAGRAM PUBLISHING ---
def post(image_url, caption):
    url = f"https://graph.facebook.com/v18.0/{IG_USER_ID}/media"
    payload = {"image_url": image_url, "caption": caption, "access_token": ACCESS_TOKEN}
    r = requests.post(url, data=payload)
    
    if "id" not in r.json():
        print("Error creating media:", r.json())
        return
        
    creation_id = r.json()["id"]
    publish_url = f"https://graph.facebook.com/v18.0/{IG_USER_ID}/media_publish"
    pub_r = requests.post(publish_url, data={"creation_id": creation_id, "access_token": ACCESS_TOKEN})
    print("Publish status:", pub_r.json())

# --- BOT LOOP ---
def run_bot():
    print("Multi-Timeframe Agentic AI Bot started!")
    while True:
        try:
            for coin in coins:
                # 1. Sense BOTH timeframes
                df_htf = get_market_data(coin, '1d')  # 1-Day Macro Chart
                df_ltf = get_market_data(coin, '1h')  # 1-Hour Micro Chart
                
                if df_htf is not None and df_ltf is not None:
                    # 2. Analyze Both
                    htf_tech = analyze_technicals(df_htf)
                    ltf_tech = analyze_technicals(df_ltf)
                    
                    # 3. Reason & Synthesize Text
                    caption = generate_agentic_caption(coin, htf_tech, ltf_tech)
                    
                    # 4. Act (Post)
                    # Note: We still pass the LTF bias to the placeholder image generator
                    bias = "LONG" if ltf_tech['trend_status'] == "Uptrend" else "SHORT"
                    image = f"https://dummyimage.com/1080x1080/1a1a1a/ffcc00&text={coin}+MTFA+{bias}"
                    
                    post(image, caption)
                    print(f"Agent successfully posted MTFA for: {coin}")
                    
                time.sleep(15) 
        except Exception as e:
            print(f"Error in bot loop: {e}")
            
        time.sleep(7200) # Run every 2 hours

# --- RENDER DUMMY SERVER ---
class DummyServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"MTFA Agentic AI is running!")

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get('PORT', 10000))
    server = HTTPServer(('0.0.0.0', port), DummyServer)
    print(f"Server listening on port {port}...")
    server.serve_forever()
