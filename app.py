import streamlit as st
import requests
import pandas as pd

st.set_page_config(page_title="Crypto Futures Screener", layout="wide")
st.title("📊 OKX Futures Screener")

BASE = "https://www.okx.com"

def safe_request(url, params=None):
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"API Error: {e}")
        return None

@st.cache_data(ttl=300)
def get_tickers():
    data = safe_request(f"{BASE}/api/v5/market/tickers", {"instType": "SWAP"})
    if not data:
        return pd.DataFrame()
    return pd.DataFrame(data["data"])

df = get_tickers()

if df.empty:
    st.stop()

df["vol24h"] = pd.to_numeric(df["volCcy24h"], errors="coerce")
df["change24h"] = pd.to_numeric(df["chgPct"], errors="coerce")

df = df[df["vol24h"] > 30000000]

def score(row):
    s = 0
    if abs(row["change24h"]) > 0.03:
        s += 2
    if row["vol24h"] > 50000000:
        s += 2
    return s

df["Score"] = df.apply(score, axis=1)

df = df.sort_values("Score", ascending=False)

st.dataframe(
    df[[
        "instId",
        "change24h",
        "vol24h",
        "Score"
    ]],
    use_container_width=True
)
