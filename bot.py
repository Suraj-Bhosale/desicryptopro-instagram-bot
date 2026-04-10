import requests
import pandas as pd
import numpy as np
import time
import os

ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
IG_USER_ID = "17841449038057212"

coins = ["BTCUSDT", "ETHUSDT"]

def get_price(symbol):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1h&limit=100"
    data = requests.get(url).json()
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
    creation_id = r.json()["id"]

    publish_url = f"https://graph.facebook.com/v18.0/{IG_USER_ID}/media_publish"
    requests.post(publish_url, data={
        "creation_id": creation_id,
        "access_token": ACCESS_TOKEN
    })

while True:
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

    time.sleep(3600)
