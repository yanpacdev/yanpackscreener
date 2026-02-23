import streamlit as st
import requests
import pandas as pd

st.set_page_config(page_title="Crypto OI Screener", layout="wide")

st.title("📊 Crypto Futures Screener")

API_URL = "https://api.coinanalyze.net/public/v1/markets"

def get_data():
    r = requests.get(API_URL)
    return r.json()

def classify(price_chg, oi_chg):
    if price_chg > 0 and oi_chg > 0:
        return "Bullish Build-up"
    elif price_chg < 0 and oi_chg > 0:
        return "Bearish Build-up"
    elif price_chg > 0 and oi_chg < 0:
        return "Short Covering"
    elif price_chg < 0 and oi_chg < 0:
        return "Long Closing"
    else:
        return "Neutral"

def score(row):
    s = 0

    # OI Change
    if row["oiChange24h"] > 10:
        s += 3

    # Volume filter
    if row["volume24h"] > 30000000:
        s += 2

    # Funding
    if 0 <= row["fundingRate"] <= 0.03:
        s += 1

    # OI/Volume ratio
    if row["volume24h"] != 0:
        ratio = row["openInterest"] / row["volume24h"]
        if 0.2 <= ratio <= 0.8:
            s += 2

    return s

data = get_data()
df = pd.DataFrame(data)

# Filter Futures Only
df = df[df["contractType"] == "perpetual"]

# Add Classification
df["Structure"] = df.apply(lambda x: classify(x["priceChange24h"], x["oiChange24h"]), axis=1)

# Add Score
df["Score"] = df.apply(score, axis=1)

# Filter OI > 10%
df = df[df["oiChange24h"] > 10]

df = df.sort_values("Score", ascending=False)

st.dataframe(
    df[[
        "symbol",
        "priceChange24h",
        "oiChange24h",
        "fundingRate",
        "volume24h",
        "openInterest",
        "Structure",
        "Score"
    ]],
    use_container_width=True
)
