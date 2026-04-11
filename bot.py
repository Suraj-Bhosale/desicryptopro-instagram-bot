import requests
import pandas as pd
import numpy as np
import time
import os
import threading
import io
import base64
from datetime import datetime, timedelta
import google.generativeai as genai
import mplfinance as mpf
import matplotlib.pyplot as plt
from http.server import BaseHTTPRequestHandler, HTTPServer

# --- CREDENTIALS ---
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
IG_USER_ID = "17841449038057212"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
IMGBB_API_KEY = os.getenv("IMGBB_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
ai_model = genai.GenerativeModel('gemini-2.5-flash')

coins = ["BTCUSDT", "ETHUSDT"]

# --- 1. SENSORS (Data Fetching) ---
def get_market_data(symbol, interval):
    url = f"https://api.binance.us/api/v3/klines?symbol={symbol}&interval={interval}&limit=100"
    data = requests.get(url).json()
    
    if isinstance(data, dict):
        print(f"API Error on {interval}: {data}")
        return None
        
    df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'tbv', 'tqv', 'ignore'])
    
    # Convert timestamp to proper datetime for charting
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
    return df

# --- 2. MATH ENGINE ---
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

# --- 3. AI AGENT ---
def generate_agentic_caption(symbol, htf_data, ltf_data):
    coin = symbol.replace("USDT", "")
    
    prompt = f"""
    You are an elite cryptocurrency technical analyst managing the Instagram account @desicryptopro.
    Analyze the following Multi-Timeframe Data for {coin} and write an engaging, professional Instagram caption.
    
    Macro Environment (Daily Chart):
    - Trend: {htf_data['trend_status']}
    - RSI: {htf_data['rsi_14']:.2f}
    - Pattern: {htf_data['candlestick_pattern']}
    
    Micro Execution (1-Hour Chart):
    - Current Price: ${ltf_data['current_price']:.2f}
    - Trend: {ltf_data['trend_status']}
    - MACD: {ltf_data['macd_status']}
    - Pattern: {ltf_data['candlestick_pattern']}
    - Local Support: ${ltf_data['support_level']:.2f}
    - Local Resistance: ${ltf_data['resistance_level']:.2f}
    
    Rules for the caption:
    1. Hook the reader with the Multi-Timeframe Alignment.
    2. Explain how the LTF pattern interacts with the HTF trend. Give higher weight to the HTF trend.
    3. State the exact current price, and the key support/resistance levels.
    4. Give a clear overall bias (Bullish, Bearish, or Neutral).
    5. Use emojis and formatting for readability.
    6. End with: "Follow @desicryptopro for real-time market analysis!" and relevant hashtags.
    """
    
    response = ai_model.generate_content(prompt)
    return response.text

# --- 4. ULTIMATE CHART GENERATION (S/R Zones, SL/TP, Arrows) ---
def create_and_upload_chart(df, symbol, tech_data):
    df_chart = df.tail(60) 
    coin_name = symbol.replace("USDT", "")
    latest_data = df_chart.iloc[-1]
    latest_price = latest_data['close']

    # Generate IST Timestamp (UTC + 5:30)
    current_ist = datetime.utcnow() + timedelta(hours=5, minutes=30)
    timestamp_str = current_ist.strftime('%d %b %Y • %I:%M %p IST')

    # Fetch Support/Resistance from the Math Engine
    support = tech_data['support_level']
    resistance = tech_data['resistance_level']
    is_bullish = tech_data['trend_status'] == 'Uptrend'

    # Auto-Calculate Stop Loss (SL) and Take Profit (TP) with 1:1.5 Risk/Reward
    arrow_data = [np.nan] * len(df_chart)
    if is_bullish:
        sl = support * 0.998 # SL slightly below support zone
        risk = latest_price - sl
        tp = latest_price + (risk * 1.5)
        arrow_data[-1] = latest_data['low'] * 0.995 # Arrow points up from below candle
        marker_shape = '^'
        trade_color = '#00ff00' # Green for Long
    else:
        sl = resistance * 1.002 # SL slightly above resistance zone
        risk = sl - latest_price
        tp = latest_price - (risk * 1.5)
        arrow_data[-1] = latest_data['high'] * 1.005 # Arrow points down from above candle
        marker_shape = 'v'
        trade_color = '#ff3333' # Red for Short

    # 1. Overlay indicators and Breakout Arrow
    ema20 = df_chart['close'].ewm(span=20, adjust=False).mean()
    ema50 = df_chart['close'].ewm(span=50, adjust=False).mean()
    
    added_plots = [
        mpf.make_addplot(ema20, color='#00ffcc', width=1.5), 
        mpf.make_addplot(ema50, color='#ff00ff', width=1.5), 
        mpf.make_addplot(pd.Series([latest_price]*len(df_chart), index=df_chart.index), color='#ffffff', linestyle=':', width=0.8),
        mpf.make_addplot(arrow_data, type='scatter', marker=marker_shape, markersize=250, color=trade_color) # The Arrow
    ]
    
    # 2. Support and Resistance Shaded Boxes
    shaded_zones = [
        dict(y1=support, y2=support*0.995, color='#00ffcc', alpha=0.15), # Greenish Support Box
        dict(y1=resistance, y2=resistance*1.005, color='#ff00ff', alpha=0.15) # Pinkish Resistance Box
    ]

    # 3. SL and TP Horizontal Lines
    target_lines = dict(hlines=[tp, sl], colors=['#00ff00', '#ff3333'], linestyle='-.', linewidths=[1.5, 1.5])

    # Professional Dark Theme
    custom_colors = mpf.make_marketcolors(
        up='#00ff00', down='#ff3333', edge={'up': '#00ff00', 'down': '#ff3333'},
        wick={'up': '#00ff00', 'down': '#ff3333'}, volume='in', inherit=True
        )

    custom_style = mpf.make_mpf_style(
        marketcolors=custom_colors, facecolor='#080808', gridcolor='#1a1a1a', 
        gridstyle='dotted', y_on_right=True,     
        rc={'font.size': 10, 'axes.labelsize': 12, 'axes.titlesize': 16, 'xtick.color': '#888888', 'ytick.color': '#888888', 'axes.edgecolor': '#333333'}
        )
    
    buf = io.BytesIO()
    
    # Draw chart with Zones and Lines
    fig, axlist = mpf.plot(df_chart, type='candle', style=custom_style, addplot=added_plots, volume=True,
             title=f"{coin_name} / USDT - 1H Setup\n{timestamp_str}\n@desicryptopro",
             figsize=(10, 10), returnfig=True, volume_panel=1, main_panel=0,
             fill_between=shaded_zones, hlines=target_lines)
    
    ax_main = axlist[0] 
    
    # Text Labels for TP and SL
    ax_main.text(df_chart.index[2], tp, '  TAKE PROFIT', color='#00ff00', fontsize=11, fontweight='bold', va='bottom')
    ax_main.text(df_chart.index[2], sl, '  STOP LOSS', color='#ff3333', fontsize=11, fontweight='bold', va='bottom')

    # Price Tag Annotation
    ax_main.annotate(f'${latest_price:.2f}', xy=(df_chart.index[-1], latest_price), xytext=(8, 0), textcoords="offset points",
                color='#ffffff', fontsize=11, fontweight='bold',
                bbox=dict(boxstyle="round,pad=0.3", fc=trade_color, ec=trade_color, lw=1))

    # Save and clean up memory
    fig.savefig(buf, dpi=150, bbox_inches='tight')
    plt.close(fig) 
    buf.seek(0)
    
    # Upload to ImgBB
    print("Uploading ultimate chart to ImgBB...")
    payload = {
        "key": IMGBB_API_KEY,
        "image": base64.b64encode(buf.read()).decode('utf-8')
    }
    res = requests.post("https://api.imgbb.com/1/upload", data=payload)
    return res.json()['data']['url']

# --- 5. INSTAGRAM PUBLISHING ---
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

# --- BOT MAIN LOOP ---
def run_bot():
    print("Agentic AI Bot with Ultimate Charting started!")
    while True:
        try:
            for coin in coins:
                df_htf = get_market_data(coin, '1d') 
                df_ltf = get_market_data(coin, '1h')  
                
                if df_htf is not None and df_ltf is not None:
                    htf_tech = analyze_technicals(df_htf)
                    ltf_tech = analyze_technicals(df_ltf)
                    
                    # Pass the technical data to the chart function to draw SL/TP and Zones
                    chart_url = create_and_upload_chart(df_ltf, coin, ltf_tech)
                    print(f"Chart generated: {chart_url}")
                    
                    caption = generate_agentic_caption(coin, htf_tech, ltf_tech)
                    
                    post(chart_url, caption)
                    print(f"Agent successfully posted Setup for: {coin}")
                    
                time.sleep(15) 
        except Exception as e:
            print(f"Error in bot loop: {e}")
            
        time.sleep(7200) # Sleep for exactly 2 hours

# --- RENDER DUMMY SERVER ---
class DummyServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Ultimate Agentic AI is running!")
    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get('PORT', 10000))
    server = HTTPServer(('0.0.0.0', port), DummyServer)
    print(f"Server listening on port {port}...")
    server.serve_forever()
