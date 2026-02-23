import streamlit as st
import requests
import pandas as pd

st.set_page_config(page_title="OKX Advanced Screener", layout="wide")
st.title("📊 OKX Advanced Futures Screener")

BASE = "https://www.okx.com"

def safe_request(url, params=None):
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except:
        return None

@st.cache_data(ttl=300)
def get_tickers():
    data = safe_request(
        f"{BASE}/api/v5/market/tickers",
        {"instType": "SWAP"}
    )
    if not data or "data" not in data:
        return pd.DataFrame()
    return pd.DataFrame(data["data"])

@st.cache_data(ttl=300)
def get_open_interest():
    data = safe_request(
        f"{BASE}/api/v5/public/open-interest",
        {"instType": "SWAP"}
    )
    if not data or "data" not in data:
        return pd.DataFrame()
    return pd.DataFrame(data["data"])

df = get_tickers()
oi = get_open_interest()

if df.empty or oi.empty:
    st.stop()

# numeric conversion
df["last"] = pd.to_numeric(df["last"], errors="coerce")
df["open24h"] = pd.to_numeric(df["open24h"], errors="coerce")
df["vol24h"] = pd.to_numeric(df["volCcy24h"], errors="coerce")

df["change24h"] = ((df["last"] - df["open24h"]) / df["open24h"]) * 100

oi["oi"] = pd.to_numeric(oi["oi"], errors="coerce")

df = df.merge(oi[["instId", "oi"]], on="instId", how="left")

# Basic liquidity filter
df = df[df["vol24h"] > 30000000]

def classify(row):
    if row["change24h"] > 0 and row["oi"] > 0:
        return "Bullish build-up"
    if row["change24h"] < 0 and row["oi"] > 0:
        return "Bearish build-up"
    if row["change24h"] > 0 and row["oi"] <= 0:
        return "Short covering"
    if row["change24h"] < 0 and row["oi"] <= 0:
        return "Long closing"
    return "Neutral"

df["Structure"] = df.apply(classify, axis=1)

def score(row):
    s = 0
    if abs(row["change24h"]) > 3:
        s += 2
    if row["vol24h"] > 50000000:
        s += 2
    if row["Structure"] in ["Bullish build-up", "Bearish build-up"]:
        s += 2
    return s

df["Score"] = df.apply(score, axis=1)

df = df.sort_values("Score", ascending=False)

st.dataframe(
    df[[
        "instId",
        "change24h",
        "vol24h",
        "oi",
        "Structure",
        "Score"
    ]],
    use_container_width=True
)
