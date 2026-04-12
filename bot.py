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

# --- 1. SENSORS ---
def get_market_data(symbol, interval):
    url = f"https://api.binance.us/api/v3/klines?symbol={symbol}&interval={interval}&limit=100"
    data = requests.get(url).json()

    if isinstance(data, dict):
        print(f"API Error on {interval}: {data}")
        return None

    df = pd.DataFrame(
        data,
        columns=[
            'timestamp','open','high','low','close','volume',
            'close_time','qav','num_trades','tbv','tqv','ignore'
        ]
    )

    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)

    for col in ['open','high','low','close','volume']:
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
    You are an elite cryptocurrency technical analyst managing @desicryptopro.
    Analyze Multi-Timeframe data for {coin} and create Instagram caption.

    Daily Trend: {htf_data['trend_status']}
    Daily RSI: {htf_data['rsi_14']:.2f}

    1H Price: {ltf_data['current_price']:.2f}
    1H Trend: {ltf_data['trend_status']}
    Support: {ltf_data['support_level']:.2f}
    Resistance: {ltf_data['resistance_level']:.2f}

    Add emojis, bias and end with follow CTA.
    """

    response = ai_model.generate_content(prompt)
    return response.text

# --- 4. UPDATED PRO CHART ENGINE ---
def create_and_upload_chart(df, symbol, tech_data):
    df_chart = df.tail(60)
    coin_name = symbol.replace("USDT", "")
    latest = df_chart.iloc[-1]
    latest_price = latest['close']

    current_ist = datetime.utcnow() + timedelta(hours=5, minutes=30)
    timestamp_str = current_ist.strftime('%d %b %Y • %I:%M %p IST')

    support = tech_data['support_level']
    resistance = tech_data['resistance_level']
    is_bullish = tech_data['trend_status'] == 'Uptrend'

    arrow_data = [np.nan] * len(df_chart)

    if is_bullish:
        sl = support * 0.998
        risk = latest_price - sl
        tp = latest_price + risk * 1.5
        arrow_data[-1] = latest['low'] * 0.995
        marker = '^'
        color = '#00ff00'
        bias = "LONG"
    else:
        sl = resistance * 1.002
        risk = sl - latest_price
        tp = latest_price - risk * 1.5
        arrow_data[-1] = latest['high'] * 1.005
        marker = 'v'
        color = '#ff3333'
        bias = "SHORT"

    ema20 = df_chart['close'].ewm(span=20).mean()
    ema50 = df_chart['close'].ewm(span=50).mean()

    apds = [
        mpf.make_addplot(ema20, color='#00ffcc'),
        mpf.make_addplot(ema50, color='#ff00ff'),
        mpf.make_addplot(arrow_data, type='scatter',
                         marker=marker, markersize=350,
                         color=color)
    ]

    buf = io.BytesIO()

    fig, axlist = mpf.plot(
        df_chart,
        type='candle',
        style='nightclouds',
        addplot=apds,
        volume=True,
        returnfig=True,
        figsize=(12,12),
        title=f"{coin_name} / USDT\n{timestamp_str}\n@desicryptopro"
    )

    ax = axlist[0]

    ax.text(
        0.01,0.97,
        f"{coin_name} | {bias}",
        transform=ax.transAxes,
        fontsize=14,
        color="white",
        bbox=dict(facecolor=color)
    )

    ax.text(df_chart.index[2], tp, " TAKE PROFIT", color="green")
    ax.text(df_chart.index[2], sl, " STOP LOSS", color="red")
    ax.text(df_chart.index[2], latest_price, " ENTRY", color="white")

    fig.savefig(buf, dpi=300, bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)

    payload = {
        "key": IMGBB_API_KEY,
        "image": base64.b64encode(buf.read())
    }

    res = requests.post("https://api.imgbb.com/1/upload", data=payload)
    return res.json()['data']['url']

# --- 5. INSTAGRAM POST ---
def post(image_url, caption):
    url = f"https://graph.facebook.com/v18.0/{IG_USER_ID}/media"
    payload = {
        "image_url": image_url,
        "caption": caption,
        "access_token": ACCESS_TOKEN
    }

    r = requests.post(url, data=payload)
    creation_id = r.json()["id"]

    publish_url = f"https://graph.facebook.com/v18.0/{IG_USER_ID}/media_publish"
    requests.post(publish_url, data={
        "creation_id": creation_id,
        "access_token": ACCESS_TOKEN
    })

# --- BOT LOOP ---
def run_bot():
    print("Ultimate AI Agent Running...")
    while True:
        try:
            for coin in coins:
                df_htf = get_market_data(coin, '1d')
                df_ltf = get_market_data(coin, '1h')

                if df_htf is not None and df_ltf is not None:
                    htf = analyze_technicals(df_htf)
                    ltf = analyze_technicals(df_ltf)

                    chart = create_and_upload_chart(df_ltf, coin, ltf)
                    caption = generate_agentic_caption(coin, htf, ltf)

                    post(chart, caption)
                    print(f"Posted {coin}")

                time.sleep(15)

        except Exception as e:
            print(e)

        time.sleep(7200)

# --- SERVER ---
class DummyServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"AI Running")

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get("PORT",10000))
    server = HTTPServer(("0.0.0.0", port), DummyServer)
    server.serve_forever()