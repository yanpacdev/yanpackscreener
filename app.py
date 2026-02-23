import streamlit as st
import requests
import pandas as pd
import numpy as np
import time
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="Futures Flow Engine", layout="wide")
st.title("Flow Engine – Multi TF Monitoring")

BASE = "https://www.okx.com"

# =========================================================
# SIDEBAR CONFIG (DEFINE FIRST – FIX NAMEERROR)
# =========================================================
st.sidebar.header("System Settings")

auto_refresh = st.sidebar.checkbox("Auto Refresh (60s)", value=True)
top5_mode = st.sidebar.checkbox("Top 5 Only Mode")
threshold = st.sidebar.slider("OI 5m Alert Threshold %", 1, 20, 5)
telegram_enable = st.sidebar.checkbox("Enable Telegram Alert")

telegram_token = ""
telegram_chat_id = ""

if telegram_enable:
    telegram_token = st.sidebar.text_input("Bot Token")
    telegram_chat_id = st.sidebar.text_input("Chat ID")

if auto_refresh:
    st_autorefresh(interval=60 * 1000, key="refresh")

# =========================================================
# SAFE REQUEST
# =========================================================
def safe_request(url, params=None):
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except:
        return None

def send_telegram(message):
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    payload = {"chat_id": telegram_chat_id, "text": message}
    try:
        requests.post(url, data=payload)
    except:
        pass

# =========================================================
# DATA FETCH
# =========================================================
@st.cache_data(ttl=60)
def get_tickers():
    data = safe_request(f"{BASE}/api/v5/market/tickers", {"instType": "SWAP"})
    if not data or "data" not in data:
        return pd.DataFrame()
    return pd.DataFrame(data["data"])

@st.cache_data(ttl=60)
def get_open_interest():
    data = safe_request(f"{BASE}/api/v5/public/open-interest", {"instType": "SWAP"})
    if not data or "data" not in data:
        return pd.DataFrame()
    return pd.DataFrame(data["data"])

@st.cache_data(ttl=60)
def get_funding():
    data = safe_request(f"{BASE}/api/v5/public/funding-rate", {"instType": "SWAP"})
    if not data or "data" not in data:
        return pd.DataFrame()
    return pd.DataFrame(data["data"])

df = get_tickers()
oi = get_open_interest()
funding = get_funding()

if df.empty or oi.empty:
    st.stop()

# =========================================================
# NUMERIC CLEANING
# =========================================================
df["last"] = pd.to_numeric(df["last"], errors="coerce")
df["open24h"] = pd.to_numeric(df["open24h"], errors="coerce")
df["vol24h"] = pd.to_numeric(df["volCcy24h"], errors="coerce")
df["change24h"] = ((df["last"] - df["open24h"]) / df["open24h"]) * 100

oi["oi"] = pd.to_numeric(oi["oi"], errors="coerce")

if not funding.empty:
    funding["fundingRate"] = pd.to_numeric(funding["fundingRate"], errors="coerce")
    funding_map = dict(zip(funding["instId"], funding["fundingRate"]))
    df["fundingRate"] = df["instId"].map(funding_map)
else:
    df["fundingRate"] = 0

# =========================================================
# OI DELTA ENGINE (SAFE + MEMORY LIMITED)
# =========================================================
now = time.time()

if "oi_history" not in st.session_state:
    st.session_state.oi_history = {}

oi_delta_5m = {}
oi_delta_15m = {}
oi_delta_1h = {}

for _, row in oi.iterrows():
    inst = row["instId"]
    current_oi = row["oi"]

    # ---- HARD RESET if legacy format detected ----
    if inst in st.session_state.oi_history:
        if not isinstance(st.session_state.oi_history[inst], list):
            st.session_state.oi_history[inst] = []

    # ---- Initialize list ----
    if inst not in st.session_state.oi_history:
        st.session_state.oi_history[inst] = []

    history = st.session_state.oi_history[inst]

    # ---- Append new snapshot ----
    history.append((now, current_oi))

    # ---- Keep only last 2 hours data (memory protection) ----
    history[:] = [h for h in history if now - h[0] <= 7200]

    def calc_delta(seconds):
        past_points = [h for h in history if now - h[0] >= seconds]
        if not past_points:
            return 0
        prev_oi = past_points[-1][1]
        if prev_oi == 0:
            return 0
        return ((current_oi - prev_oi) / prev_oi) * 100

    oi_delta_5m[inst] = calc_delta(300)
    oi_delta_15m[inst] = calc_delta(900)
    oi_delta_1h[inst] = calc_delta(3600)

# =========================================================
# CUMULATIVE DELTA SIMULATION
# =========================================================
df["cumDeltaSim"] = df["oi_5m"] * df["change24h"]

# =========================================================
# LIQUIDITY VACUUM DETECTOR
# =========================================================
df["vacuum"] = np.where(
    (df["change24h"].abs() > 2) & (df["oi_5m"].abs() < 0.5),
    "Vacuum",
    "-"
)

# =========================================================
# TRAP PROBABILITY (LOGISTIC MODEL)
# =========================================================
def logistic(x):
    return 1 / (1 + np.exp(-x))

df["trapScore"] = logistic(
    (df["fundingRate"] * -500) +
    (df["oi_5m"] * 0.3) -
    (df["change24h"] * 0.2)
)

# =========================================================
# FLOW SCORE
# =========================================================
df["FlowScore"] = (
    df["oi_5m"].abs() * 0.4 +
    df["oi_15m"].abs() * 0.2 +
    df["oi_1h"].abs() * 0.1 +
    df["change24h"].abs() * 0.2 +
    df["trapScore"] * 10 * 0.1
)

df = df[df["vol24h"] > 30000000]
df = df.sort_values("FlowScore", ascending=False)

# =========================================================
# ALERT SYSTEM
# =========================================================
alerts = df[df["oi_5m"].abs() > threshold]

if not alerts.empty:
    st.warning("OI Expansion Alert")
    st.dataframe(alerts[["instId", "oi_5m"]], use_container_width=True)

    if telegram_enable and telegram_token and telegram_chat_id:
        message = "🚨 OI Expansion Alert\n"
        for _, r in alerts.iterrows():
            message += f"{r['instId']} | {r['oi_5m']:.2f}%\n"
        send_telegram(message)

# =========================================================
# HEATMAP DASHBOARD
# =========================================================
st.subheader("Flow Heatmap (5m / 15m / 1h)")

heatmap = df.set_index("instId")[["oi_5m", "oi_15m", "oi_1h"]].head(20)

st.dataframe(
    heatmap.style.background_gradient(cmap="RdYlGn"),
    use_container_width=True
)

# =========================================================
# MAIN TABLE
# =========================================================
display = df.head(5) if top5_mode else df.head(25)

st.subheader("Flow Ranking")

st.dataframe(
    display[[
        "instId",
        "oi_5m",
        "oi_15m",
        "oi_1h",
        "fundingRate",
        "vacuum",
        "trapScore",
        "FlowScore"
    ]],
    use_container_width=True,
    height=500
)
