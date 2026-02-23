import streamlit as st
import requests
import pandas as pd

st.set_page_config(page_title="Crypto Futures Screener", layout="wide")
st.title("📊 Beta Version")

BASE = "https://fapi.binance.com"

@st.cache_data(ttl=300)
def get_symbols():
    r = requests.get(f"{BASE}/fapi/v1/exchangeInfo")
    return [s["symbol"] for s in r.json()["symbols"] if s["contractType"] == "PERPETUAL"]

@st.cache_data(ttl=300)
def get_24h():
    r = requests.get(f"{BASE}/fapi/v1/ticker/24hr")
    return pd.DataFrame(r.json())

@st.cache_data(ttl=300)
def get_funding():
    r = requests.get(f"{BASE}/fapi/v1/premiumIndex")
    return pd.DataFrame(r.json())

@st.cache_data(ttl=300)
def get_oi(symbol):
    r = requests.get(f"{BASE}/fapi/v1/openInterest", params={"symbol": symbol})
    return float(r.json()["openInterest"])

def classify(price_chg, oi_chg):
    if price_chg > 0 and oi_chg > 0:
        return "Bullish Build-up"
    elif price_chg < 0 and oi_chg > 0:
        return "Bearish Build-up"
    elif price_chg > 0 and oi_chg < 0:
        return "Short Covering"
    elif price_chg < 0 and oi_chg < 0:
        return "Long Closing"
    return "Neutral"

symbols = get_symbols()
ticker = get_24h()
funding = get_funding()

df = ticker[ticker["symbol"].isin(symbols)].copy()

df["priceChangePercent"] = df["priceChangePercent"].astype(float)
df["volume"] = df["quoteVolume"].astype(float)

funding = funding[["symbol", "lastFundingRate"]]
funding["lastFundingRate"] = funding["lastFundingRate"].astype(float)

df = df.merge(funding, on="symbol", how="left")

# Basic Filters
df = df[df["volume"] > 30000000]

# Add Score
def score(row):
    s = 0
    if abs(row["priceChangePercent"]) > 3:
        s += 2
    if row["volume"] > 50000000:
        s += 2
    if 0 <= row["lastFundingRate"] <= 0.03:
        s += 1
    return s

df["Score"] = df.apply(score, axis=1)

df = df.sort_values("Score", ascending=False)

st.dataframe(
    df[[
        "symbol",
        "priceChangePercent",
        "volume",
        "lastFundingRate",
        "Score"
    ]],
    use_container_width=True
)
