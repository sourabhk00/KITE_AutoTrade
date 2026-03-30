"""config/settings.py v7"""
import os, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def _env(key, default=""):
    for p in [ROOT/".env", ROOT/".env.example"]:
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                if not line.strip() or line.strip().startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                v = re.split(r'\s+#', v.strip())[0].strip().strip('"').strip("'")
                if k.strip() == key:
                    return v
    return os.getenv(key, default)

# ── API ──────────────────────────────────────────────────────────
KITE_API_KEY      = _env("KITE_API_KEY")
KITE_API_SECRET   = _env("KITE_API_SECRET")
ACCESS_TOKEN_FILE = ROOT / "config" / "access_token.txt"
NEWSAPI_KEY       = _env("NEWSAPI_KEY")
TELEGRAM_TOKEN    = _env("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID  = _env("TELEGRAM_CHAT_ID")

# ── Mode ─────────────────────────────────────────────────────────
PAPER_TRADING = _env("PAPER_TRADING", "true").lower() == "true"

# ── SESSION CONFIG (set by user at startup or via dashboard) ─────
# These are defaults — overridden when user enters values
TOTAL_CAPITAL      = 45_000
DAILY_TARGET       = 4_000
DAILY_LOSS_LIMIT   = 2_000
MAX_POSITIONS      = 5

# Derived
CAPITAL_PER_TRADE  = TOTAL_CAPITAL / MAX_POSITIONS
MAX_RISK_PER_TRADE = 0.01

# ── Trade parameters ─────────────────────────────────────────────
STOP_LOSS_PCT      = 0.010
TARGET_PCT         = 0.025
TRAILING_SL_PCT    = 0.005
BREAKEVEN_TRIGGER  = 0.012

# ── Timing ───────────────────────────────────────────────────────
MARKET_OPEN   = "09:15"
ENTRY_START   = "09:25"
ENTRY_CUTOFF  = "14:00"
SQUARE_OFF    = "15:10"
MARKET_CLOSE  = "15:30"
AVOID_LUNCH   = True
LUNCH_START   = "12:30"
LUNCH_END     = "13:15"
SCAN_INTERVAL = 55

# ── Indicators ───────────────────────────────────────────────────
CANDLE_INTERVAL   = "5minute"
EMA_FAST          = 9
EMA_SLOW          = 21
EMA_TREND         = 50
EMA_200           = 200
MACD_FAST         = 12
MACD_SLOW         = 26
MACD_SIG          = 9
RSI_PERIOD        = 14
RSI_OVERSOLD      = 35
RSI_OVERBOUGHT    = 65
BB_PERIOD         = 20
ATR_PERIOD        = 14
ADX_MIN           = 20
VOLUME_MULT       = 1.5
SUPERTREND_MULT   = 3.0
VWAP_DEV_PCT      = 0.5

# ── Strategies ───────────────────────────────────────────────────
ACTIVE_STRATEGIES = [
    "EMA_CROSSOVER","MACD_RSI","VWAP_REVERSAL",
    "SUPERTREND","BOLLINGER_SQUEEZE","ICHIMOKU",
    "OPENING_RANGE","VOLUME_PRICE","MEAN_REVERSION",
]
MIN_CONFIDENCE = 0.62

# ── Orders ───────────────────────────────────────────────────────
USE_GTT = True

# ── Dashboard ────────────────────────────────────────────────────
DASHBOARD_HOST = "127.0.0.1"
DASHBOARD_PORT = int(_env("DASHBOARD_PORT", "8050"))

# ── News ─────────────────────────────────────────────────────────
NEWS_ENABLED         = True
NEWS_BLOCK_THRESHOLD = -0.35
NEWS_BOOST_THRESHOLD = 0.20

# ── IPO ──────────────────────────────────────────────────────────
IPO_ENABLED          = True
IPO_MIN_SUBSCRIPTION = 2.0

# ── Scanner ──────────────────────────────────────────────────────
MIN_PRICE   = 50
MAX_PRICE   = 10_000
MIN_ATR_PCT = 0.5
MAX_ATR_PCT = 7.0

# ── All Indices ──────────────────────────────────────────────────
INDEX_INSTRUMENTS = {
    "NIFTY 50":          "NSE:NIFTY 50",
    "NIFTY BANK":        "NSE:NIFTY BANK",
    "NIFTY 100":         "NSE:NIFTY 100",
    "NIFTY MIDCAP 100":  "NSE:NIFTY MIDCAP 100",
    "NIFTY IT":          "NSE:NIFTY IT",
    "NIFTY PHARMA":      "NSE:NIFTY PHARMA",
    "NIFTY AUTO":        "NSE:NIFTY AUTO",
    "NIFTY FIN SERVICE": "NSE:NIFTY FIN SERVICE",
    "NIFTY ENERGY":      "NSE:NIFTY ENERGY",
    "NIFTY FMCG":        "NSE:NIFTY FMCG",
    "NIFTY METAL":       "NSE:NIFTY METAL",
    "NIFTY REALTY":      "NSE:NIFTY REALTY",
    "NIFTY COMMODITIES": "NSE:NIFTY COMMODITIES",
    "NIFTY CONSUMPTION": "NSE:NIFTY CONSUMPTION",
    "NIFTY DIV OPPS 50": "NSE:NIFTY DIV OPPS 50",
    "INDIA VIX":         "NSE:INDIA VIX",
    "SENSEX":            "BSE:SENSEX",
    "BANKEX":            "BSE:BANKEX",
}

# ── Stock Universe ────────────────────────────────────────────────
NIFTY_50 = [
    "ADANIENT","ADANIPORTS","APOLLOHOSP","ASIANPAINT","AXISBANK",
    "BAJAJ_AUTO","BAJAJFINSV","BAJFINANCE","BHARTIARTL","BPCL",
    "BRITANNIA","CIPLA","COALINDIA","DIVISLAB","DRREDDY",
    "EICHERMOT","GRASIM","HCLTECH","HDFCBANK","HDFCLIFE",
    "HEROMOTOCO","HINDALCO","HINDUNILVR","ICICIBANK","INDUSINDBK",
    "INFY","ITC","JSWSTEEL","KOTAKBANK","LT",
    "LTIM","M_M","MARUTI","NESTLEIND","NTPC",
    "ONGC","POWERGRID","RELIANCE","SBILIFE","SBIN",
    "SHRIRAMFIN","SUNPHARMA","TATACONSUM","TATAMOTORS","TATASTEEL",
    "TCS","TECHM","TITAN","TRENT","ULTRACEMCO","WIPRO",
]
NIFTY_BANK    = ["HDFCBANK","ICICIBANK","KOTAKBANK","SBIN","AXISBANK","INDUSINDBK","BANDHANBNK","FEDERALBNK","IDFCFIRSTB","AUBANK","PNB","BANKBARODA"]
SENSEX_30     = ["RELIANCE","TCS","HDFCBANK","ICICIBANK","INFY","HINDUNILVR","ITC","SBIN","BHARTIARTL","BAJFINANCE","KOTAKBANK","LT","AXISBANK","ASIANPAINT","MARUTI","TITAN","NTPC","ULTRACEMCO","POWERGRID","WIPRO","HCLTECH","TATAMOTORS","NESTLEIND","BAJAJ_AUTO","SUNPHARMA","TATASTEEL","M_M","ADANIENT","DRREDDY","ONGC"]
NIFTY_IT      = ["TCS","INFY","WIPRO","HCLTECH","TECHM","LTIM","MPHASIS","COFORGE","PERSISTENT","OFSS"]
NIFTY_PHARMA  = ["SUNPHARMA","DRREDDY","CIPLA","DIVISLAB","APOLLOHOSP","AUROPHARMA","LUPIN","TORNTPHARM","ALKEM","IPCALAB"]
NIFTY_AUTO    = ["MARUTI","TATAMOTORS","BAJAJ_AUTO","HEROMOTOCO","EICHERMOT","M_M","TVSMOTORS","ASHOKLEY","BALKRISIND","BOSCHLTD"]
NIFTY_METAL   = ["TATASTEEL","JSWSTEEL","HINDALCO","COALINDIA","VEDL","SAIL","NMDC","HINDCOPPER","NATIONALUM","RATNAMANI"]
NIFTY_ENERGY  = ["RELIANCE","ONGC","BPCL","NTPC","POWERGRID","TATAPOWER","ADANIGREEN","TORNTPOWER","IEX","CESC"]
NIFTY_FMCG    = ["HINDUNILVR","ITC","NESTLEIND","BRITANNIA","TATACONSUM","DABUR","MARICO","GODREJCP","EMAMILTD","COLPAL"]
NIFTY_FIN_SVC = ["HDFCBANK","ICICIBANK","KOTAKBANK","BAJFINANCE","BAJAJFINSV","SBIN","AXISBANK","SBILIFE","HDFCLIFE","CHOLAFIN"]
NIFTY_MIDCAP  = ["ZOMATO","IRCTC","ABCAPITAL","CHOLAFIN","SBICARD","PIDILITIND","ASTRAL","POLYCAB","HAVELLS","VOLTAS","CUMMINSIND","THERMAX","BHEL","HAL","BEL","RVNL","IRFC","NAUKRI","PERSISTENT","DIXON"]
NIFTY_REALTY  = ["DLF","GODREJPROP","LODHA","OBEROIRLTY","PRESTIGE","SOBHA","BRIGADE","PHOENIXLTD","SUNTECK","MAHINDCIE"]

_all = (NIFTY_50 + NIFTY_BANK + SENSEX_30 + NIFTY_IT + NIFTY_PHARMA + NIFTY_AUTO +
        NIFTY_METAL + NIFTY_ENERGY + NIFTY_FMCG + NIFTY_FIN_SVC + NIFTY_MIDCAP + NIFTY_REALTY)
WATCHLIST       = list(dict.fromkeys(_all))
WATCHLIST_TIER1 = NIFTY_50[:25]
