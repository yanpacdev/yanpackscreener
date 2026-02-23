import streamlit as st
import requests
import pandas as pd

st.set_page_config(page_title="Crypto Futures Screener", layout="wide")
st.title("Ver 1.0.0")

BASE = "https://fapi.binance.com"

def safe_request(url, params=None):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, params=params, headers=headers, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"API Error: {e}")
        return None


@st.cache_data(ttl=300)
def get_symbols():
    data = safe_request(f"{BASE}/fapi/v1/exchangeInfo")
    if not data or "symbols" not in data:
        return []
    return [
        s["symbol"]
        for s in data["symbols"]
        if s["contractType"] == "PERPETUAL"
    ]


@st.cache_data(ttl=300)
def get_24h():
    data = safe_request(f"{BASE}/fapi/v1/ticker/24hr")
    if not data:
        return pd.DataFrame()
    return pd.DataFrame(data)


@st.cache_data(ttl=300)
def get_funding():
    data = safe_request(f"{BASE}/fapi/v1/premiumIndex")
    if not data:
        return pd.DataFrame()
    return pd.DataFrame(data)


symbols = get_symbols()

if not symbols:
    st.stop()

ticker = get_24h()
funding = get_funding()

if ticker.empty or funding.empty:
    st.stop()

df = ticker[ticker["symbol"].isin(symbols)].copy()

df["priceChangePercent"] = pd.to_numeric(df["priceChangePercent"], errors="coerce")
df["volume"] = pd.to_numeric(df["quoteVolume"], errors="coerce")

funding = funding[["symbol", "lastFundingRate"]]
funding["lastFundingRate"] = pd.to_numeric(funding["lastFundingRate"], errors="coerce")

df = df.merge(funding, on="symbol", how="left")

# Basic liquidity filter
df = df[df["volume"] > 30000000]

def score(row):
    s = 0
    if abs(row["priceChangePercent"]) > 3:
        s += 2
    if row["volume"] > 50000000:
        s += 2
    if 0 <= row["lastFundingRate"] <= 0.0003:
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
