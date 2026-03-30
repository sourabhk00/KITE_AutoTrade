"""live_trading.py — LIVE trading with real money"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
os.environ["PAPER_TRADING"] = "false"
print("""
╔══════════════════════════════════════════════════════╗
║  ⚠️  LIVE TRADING — REAL MONEY                      ║
╚══════════════════════════════════════════════════════╝""")
c = input("  Type YES to confirm: ").strip()
if c != "YES": print("  Cancelled"); sys.exit(0)
uid = input("  Zerodha User ID: ").strip()
if not uid: sys.exit(0)
from main import ask_session, TradingBot, set_session
sess = ask_session(); sess.mode = "LIVE"; set_session(sess)
TradingBot(sess).run()
