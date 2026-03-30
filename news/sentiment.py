"""
news/sentiment.py
Market sentiment from free RSS feeds + NewsAPI.
Analyzes Economic Times, Moneycontrol, LiveMint headlines.
Used as a signal filter — blocks trades with strong bad news.
"""

import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from urllib.request import urlopen, Request
from urllib.parse import quote
from urllib.error import URLError

logger = logging.getLogger("Sentiment")

BULLISH = {"surge","rally","gains","jumps","soars","beats","record","upgrade","buy",
           "profit","growth","acquisition","order","strong","dividend","buyback",
           "beat","exceeds","high","bullish","positive","win","expansion"}
BEARISH = {"fall","drops","crash","decline","loss","miss","downgrade","sell",
           "negative","weak","cut","debt","fine","fraud","probe","investigation",
           "recall","default","bearish","below","disappoints","concern","warning"}

RSS = [
    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "https://www.moneycontrol.com/rss/marketsnews.xml",
]

NAME_MAP = {
    "RELIANCE":"Reliance","TCS":"Tata Consultancy","HDFCBANK":"HDFC Bank",
    "ICICIBANK":"ICICI Bank","SBIN":"State Bank","INFY":"Infosys",
    "WIPRO":"Wipro","TATAMOTORS":"Tata Motors","BAJFINANCE":"Bajaj Finance",
    "SUNPHARMA":"Sun Pharma","ZOMATO":"Zomato","AXISBANK":"Axis Bank",
    "KOTAKBANK":"Kotak","LT":"Larsen","NTPC":"NTPC","ONGC":"ONGC",
    "BHARTIARTL":"Airtel","ITC":"ITC","HINDUNILVR":"Hindustan Unilever",
    "MARUTI":"Maruti","TATASTEEL":"Tata Steel","HINDALCO":"Hindalco",
}


class SentimentEngine:
    def __init__(self, config):
        self.cfg   = config
        self._cache: dict = {}

    def get_stock_sentiment(self, symbol: str) -> dict:
        cached = self._cache.get(symbol)
        if cached and time.time() - cached["ts"] < 1800:
            return cached

        headlines = self._fetch(symbol)
        score, detail = self._score(headlines)
        signal = "NEUTRAL"
        if score >=  0.20: signal = "BULLISH"
        if score <= -0.20: signal = "BEARISH"

        result = {"score": round(score, 3), "signal": signal,
                  "headlines": headlines[:4], "detail": detail, "ts": time.time()}
        self._cache[symbol] = result
        return result

    def should_avoid(self, symbol: str, action: str) -> tuple[bool, str]:
        if not getattr(self.cfg, "NEWS_ENABLED", True):
            return False, "disabled"
        s = self.get_stock_sentiment(symbol)
        if action == "BUY"  and s["score"] < -0.35:
            return True, f"Negative news ({s['score']:.2f})"
        if action == "SELL" and s["score"] >  0.35:
            return True, f"Positive news ({s['score']:.2f})"
        return False, "OK"

    def news_boost(self, symbol: str, action: str) -> float:
        s = self.get_stock_sentiment(symbol)
        sc = s["score"]
        if action == "BUY"  and sc > 0.2: return min(sc * 0.15, 0.12)
        if action == "SELL" and sc < -0.2: return min(abs(sc) * 0.15, 0.12)
        return 0.0

    def _fetch(self, symbol: str) -> list:
        name = NAME_MAP.get(symbol, symbol)
        headlines = []
        for url in RSS:
            try:
                req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urlopen(req, timeout=5) as r:
                    xml = r.read().decode("utf-8", errors="ignore")
                root = ET.fromstring(xml)
                for item in root.iter("item"):
                    el = item.find("title")
                    if el is not None and el.text:
                        t = el.text.strip()
                        if symbol.lower() in t.lower() or name.lower() in t.lower():
                            headlines.append(t)
            except Exception:
                continue
        # NewsAPI fallback
        api_key = getattr(self.cfg, "NEWSAPI_KEY", "")
        if api_key and api_key != "get_free_key_at_newsapi_org" and len(headlines) < 3:
            headlines += self._newsapi(symbol, api_key)
        return headlines[:15]

    def _newsapi(self, symbol: str, key: str) -> list:
        try:
            url = (f"https://newsapi.org/v2/everything?q={quote(symbol)}+NSE"
                   f"&language=en&sortBy=publishedAt&pageSize=5&apiKey={key}")
            with urlopen(Request(url), timeout=5) as r:
                data = json.loads(r.read())
            return [a["title"] for a in data.get("articles", []) if a.get("title")]
        except Exception:
            return []

    def _score(self, headlines: list) -> tuple[float, str]:
        if not headlines:
            return 0.0, "No headlines"
        bull = bear = 0
        for h in headlines:
            words = set(re.findall(r'\w+', h.lower()))
            bull += len(words & BULLISH)
            bear += len(words & BEARISH)
        total = bull + bear
        if total == 0:
            return 0.0, "No sentiment keywords"
        score = (bull - bear) / total
        return score, f"{bull} bullish / {bear} bearish in {len(headlines)} headlines"
