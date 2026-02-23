import streamlit as st
import requests
import pandas as pd
import time
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="Crypto Futures Screener", layout="wide")
st.title("Version 2.0.1 – Flow Engine")

BASE = "https://www.okx.com"

# ----------------------
# AUTO REFRESH
# ----------------------
refresh = st.sidebar.checkbox("Auto Refresh (60s)", value=True)

if refresh:
    st_autorefresh(interval=60 * 1000, key="datarefresh")

# ----------------------
# SAFE REQUEST
# ----------------------
def safe_request(url, params=None):
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except:
        return None

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

# ----------------------
# LOAD DATA
# ----------------------
df = get_tickers()
oi = get_open_interest()

if df.empty or oi.empty:
    st.stop()

# ----------------------
# NUMERIC
# ----------------------
df["last"] = pd.to_numeric(df["last"], errors="coerce")
df["open24h"] = pd.to_numeric(df["open24h"], errors="coerce")
df["vol24h"] = pd.to_numeric(df["volCcy24h"], errors="coerce")
df["change24h"] = ((df["last"] - df["open24h"]) / df["open24h"]) * 100

oi["oi"] = pd.to_numeric(oi["oi"], errors="coerce")

# ----------------------
# OI SNAPSHOT (5 MIN WINDOW)
# ----------------------
now = time.time()

if "oi_history" not in st.session_state:
    st.session_state.oi_history = {}

oi_change_map = {}

for _, row in oi.iterrows():
    inst = row["instId"]
    current_oi = row["oi"]

    if inst not in st.session_state.oi_history:
        st.session_state.oi_history[inst] = {"time": now, "oi": current_oi}
        oi_change_map[inst] = 0
    else:
        prev = st.session_state.oi_history[inst]
        time_diff = now - prev["time"]

        # 5 minute window
        if time_diff >= 300:
            if prev["oi"] > 0:
                delta = ((current_oi - prev["oi"]) / prev["oi"]) * 100
            else:
                delta = 0

            oi_change_map[inst] = delta
            st.session_state.oi_history[inst] = {"time": now, "oi": current_oi}
        else:
            oi_change_map[inst] = 0

df["oi"] = df["instId"].map(dict(zip(oi["instId"], oi["oi"])))
df["oi_5m_delta"] = df["instId"].map(oi_change_map).fillna(0)

# ----------------------
# LIQUIDITY FILTER
# ----------------------
df = df[df["vol24h"] > 30000000]

# ----------------------
# STRUCTURE
# ----------------------
def structure(row):
    if row["change24h"] > 0 and row["oi_5m_delta"] > 0:
        return "Bull build"
    if row["change24h"] < 0 and row["oi_5m_delta"] > 0:
        return "Bear build"
    if row["change24h"] > 0 and row["oi_5m_delta"] < 0:
        return "Short cover"
    if row["change24h"] < 0 and row["oi_5m_delta"] < 0:
        return "Long close"
    return "-"

df["Structure"] = df.apply(structure, axis=1)

# ----------------------
# ALERT SYSTEM
# ----------------------
threshold = st.sidebar.slider("OI 5m Alert Threshold %", 1, 20, 5)

alerts = df[df["oi_5m_delta"].abs() > threshold]

if not alerts.empty:
    st.warning("OI Expansion Alert")
    st.dataframe(alerts[["instId", "oi_5m_delta"]], use_container_width=True)

if telegram_enable and not alerts.empty:
    message = "🚨 OI Expansion Alert\n"
    for _, r in alerts.iterrows():
        message += f"{r['instId']} | {r['oi_5m_delta']:.2f}%\n"
    send_telegram(message)

# ----------------------
# NARRATIVE
# ----------------------
def narrative(instId):
    if instId.startswith(("SOL", "AVAX", "MATIC")):
        return "Layer1"
    if instId.startswith(("ARB", "OP")):
        return "Layer2"
    if instId.startswith(("DOGE", "SHIB", "PEPE", "WIF")):
        return "Meme"
    return "Other"

df["Narrative"] = df["instId"].apply(narrative)

sector_flow = (
    df.groupby("Narrative")["oi_5m_delta"]
    .mean()
    .sort_values(ascending=False)
)

# ----------------------
# RANK BY REAL FLOW
# ----------------------
df["FlowScore"] = (
    df["oi_5m_delta"].abs() * 0.6 +
    df["change24h"].abs() * 0.2 +
    (df["vol24h"] / 1e9) * 0.2
)

df = df.sort_values("FlowScore", ascending=False)

# ----------------------
# DISPLAY MINIMAL
# ----------------------
telegram_enable = st.sidebar.checkbox("Enable Telegram Alert")
telegram_token = st.sidebar.text_input("Bot Token")
telegram_chat_id = st.sidebar.text_input("Chat ID")
top5_mode = st.sidebar.checkbox("Top 5 Only Mode")

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    requests.post(url, data={
        "chat_id": telegram_chat_id,
        "text": msg
    })

display_df = df.copy()

if top5_mode:
    display_df = display_df.head(5)
else:
    display_df = display_df.head(25)

def oi_color(val):
    if val > 0:
        return "background-color: rgba(0,255,0,0.3)"
    if val < 0:
        return "background-color: rgba(255,0,0,0.3)"
    return ""

styled = (
    display_df[[
        "instId",
        "oi_5m_delta",
        "change24h",
        "Structure",
        "Narrative",
        "FlowScore"
    ]]
    .style
    .format({
        "oi_5m_delta": "{:.2f}",
        "change24h": "{:.2f}",
        "FlowScore": "{:.2f}"
    })
    .applymap(oi_color, subset=["oi_5m_delta"])
)

st.dataframe(styled, use_container_width=True, height=400)
st.subheader("Sector OI Flow (5m)")
st.dataframe(sector_flow, use_container_width=True)
