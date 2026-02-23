import streamlit as st
import requests
import pandas as pd
import time

st.set_page_config(page_title="Crypto Futures Screener", layout="wide")
st.title("Version 2.0 – Positioning Intelligence")

BASE = "https://www.okx.com"

# --------------------------
# SAFE REQUEST
# --------------------------
def safe_request(url, params=None):
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except:
        return None

# --------------------------
# FETCH DATA
# --------------------------
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

def get_funding(instId):
    data = safe_request(
        f"{BASE}/api/v5/public/funding-rate",
        {"instId": instId}
    )
    if data and "data" in data and len(data["data"]) > 0:
        try:
            return float(data["data"][0]["fundingRate"])
        except:
            return 0
    return 0

# --------------------------
# LOAD DATA
# --------------------------
df = get_tickers()
oi = get_open_interest()

if df.empty or oi.empty:
    st.error("Failed to fetch data")
    st.stop()

# --------------------------
# NUMERIC CONVERSION
# --------------------------
df["last"] = pd.to_numeric(df["last"], errors="coerce")
df["open24h"] = pd.to_numeric(df["open24h"], errors="coerce")
df["vol24h"] = pd.to_numeric(df["volCcy24h"], errors="coerce")

df["change24h"] = ((df["last"] - df["open24h"]) / df["open24h"]) * 100

oi["oi"] = pd.to_numeric(oi["oi"], errors="coerce")

# --------------------------
# OI CHANGE %
# --------------------------
if "oi_prev" not in st.session_state:
    st.session_state.oi_prev = None

oi_current = oi[["instId", "oi"]].copy()

if st.session_state.oi_prev is not None:
    oi_current = oi_current.merge(
        st.session_state.oi_prev,
        on="instId",
        how="left",
        suffixes=("", "_prev")
    )
    oi_current["oi_change_pct"] = (
        (oi_current["oi"] - oi_current["oi_prev"]) /
        oi_current["oi_prev"]
    ) * 100
else:
    oi_current["oi_change_pct"] = 0

st.session_state.oi_prev = oi_current[["instId", "oi"]].copy()

# --------------------------
# MERGE OI
# --------------------------
df = df.merge(
    oi_current[["instId", "oi", "oi_change_pct"]],
    on="instId",
    how="left"
)

# --------------------------
# LIQUIDITY FILTER
# --------------------------
df = df[df["vol24h"] > 30000000]

# --------------------------
# FUNDING (only top 40 volume to avoid API overload)
# --------------------------
top_symbols = df.sort_values("vol24h", ascending=False).head(40)["instId"]
funding_map = {}

for inst in top_symbols:
    funding_map[inst] = get_funding(inst)

df["funding"] = df["instId"].map(funding_map).fillna(0)

# --------------------------
# STRUCTURE CLASSIFICATION
# --------------------------
def classify(row):
    if row["change24h"] > 0 and row["oi_change_pct"] > 0:
        return "Bullish build-up"
    if row["change24h"] < 0 and row["oi_change_pct"] > 0:
        return "Bearish build-up"
    if row["change24h"] > 0 and row["oi_change_pct"] < 0:
        return "Short covering"
    if row["change24h"] < 0 and row["oi_change_pct"] < 0:
        return "Long closing"
    return "Neutral"

df["Structure"] = df.apply(classify, axis=1)

# --------------------------
# SQUEEZE DETECTION
# --------------------------
def detect_squeeze(row):
    if row["change24h"] > 2 and row["oi_change_pct"] > 5 and row["funding"] > 0.01:
        return "Long squeeze risk"
    if row["change24h"] < -2 and row["oi_change_pct"] > 5 and row["funding"] < -0.01:
        return "Short squeeze risk"
    return "None"

df["Squeeze"] = df.apply(detect_squeeze, axis=1)

# --------------------------
# NARRATIVE CLUSTERING
# --------------------------
def narrative(instId):
    if instId.startswith(("SOL", "AVAX", "MATIC")):
        return "Layer1"
    if instId.startswith(("ARB", "OP")):
        return "Layer2"
    if instId.startswith(("DOGE", "SHIB", "PEPE")):
        return "Meme"
    if instId.startswith(("LINK", "BAND")):
        return "Oracle"
    return "Other"

df["Narrative"] = df["instId"].apply(narrative)

sector_flow = (
    df.groupby("Narrative")["oi_change_pct"]
    .mean()
    .sort_values(ascending=False)
)

# --------------------------
# SCORE
# --------------------------
def score(row):
    s = 0
    if abs(row["change24h"]) > 3:
        s += 2
    if row["vol24h"] > 50000000:
        s += 2
    if row["oi_change_pct"] > 5:
        s += 2
    if row["Structure"] in ["Bullish build-up", "Bearish build-up"]:
        s += 2
    return s

df["Score"] = df.apply(score, axis=1)

df = df.sort_values("Score", ascending=False)

# --------------------------
# DISPLAY
# --------------------------
st.subheader("Top Positioning Expansion")
st.dataframe(
    df[[
        "instId",
        "change24h",
        "oi_change_pct",
        "funding",
        "vol24h",
        "Structure",
        "Squeeze",
        "Narrative",
        "Score"
    ]],
    use_container_width=True
)

st.subheader("Sector OI Flow")
st.dataframe(sector_flow)
