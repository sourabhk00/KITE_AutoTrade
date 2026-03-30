"""paper_trading.py — Paper mode (no real money)"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
os.environ["PAPER_TRADING"] = "true"
from main import ask_session, TradingBot, set_session
print("\n  PAPER TRADING — No real money\n")
sess = ask_session(); sess.mode = "PAPER"; set_session(sess)
TradingBot(sess).run()
