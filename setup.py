"""
setup.py — One-click installer for Zerodha Trading Bot v4.0
Run this ONCE on your laptop to set everything up.

Usage:
    python setup.py
"""

import subprocess
import sys
import os
import shutil
from pathlib import Path

BASE = Path(__file__).parent

BANNER = """
╔══════════════════════════════════════════════════════════════╗
║   ZERODHA KITE TRADING BOT v4.0 — LAPTOP SETUP              ║
║   sourabhk1967@gmail.com                                     ║
╚══════════════════════════════════════════════════════════════╝
"""

PACKAGES = [
    ("kiteconnect",             "Zerodha official API"),
    ("pandas",                  "Data processing"),
    ("numpy",                   "Math"),
    ("plotly",                  "Interactive charts"),
    ("dash",                    "Live dashboard"),
    ("dash-bootstrap-components","Dashboard UI"),
    ("requests",                "HTTP calls"),
    ("websocket-client",        "Real-time streaming"),
    ("python-dotenv",           "Config from .env file"),
    ("feedparser",              "RSS news feeds"),
    ("vaderSentiment",          "News sentiment scoring"),
    ("schedule",                "Task scheduling"),
    ("colorlog",                "Colored terminal logs"),
    ("tabulate",                "Pretty tables"),
    ("python-dateutil",         "Date handling"),
    ("pytz",                    "Timezone support"),
]

def pip(pkg):
    return subprocess.run(
        [sys.executable, "-m", "pip", "install", pkg, "-q", "--upgrade"],
        capture_output=True
    ).returncode == 0

def main():
    print(BANNER)

    # Python version check
    v = sys.version_info
    if v.major < 3 or v.minor < 9:
        print(f"[ERROR] Python 3.9+ required. You have {v.major}.{v.minor}")
        print("Download Python from: https://www.python.org/downloads/")
        sys.exit(1)
    print(f"✓ Python {v.major}.{v.minor}.{v.micro} detected\n")

    # Install packages
    print("Installing packages (this takes 2-3 minutes)...\n")
    failed = []
    for pkg, desc in PACKAGES:
        print(f"  Installing {pkg:<30} ({desc})... ", end="", flush=True)
        ok = pip(pkg)
        print("✓" if ok else "✗ FAILED")
        if not ok:
            failed.append(pkg)

    if failed:
        print(f"\n[WARNING] Some packages failed: {failed}")
        print("Try manually: pip install " + " ".join(failed))

    # Create directories
    print("\nCreating folders...")
    for d in ["logs", "reports", "config"]:
        Path(d).mkdir(exist_ok=True)
        print(f"  ✓ {d}/")

    # Create .env from template
    env_file = BASE / ".env"
    env_example = BASE / ".env.example"
    if not env_file.exists() and env_example.exists():
        shutil.copy(env_example, env_file)
        print(f"\n  ✓ Created .env (edit this file with your API keys)")
    elif env_file.exists():
        print(f"\n  ✓ .env already exists")

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║   SETUP COMPLETE!                                            ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  NEXT STEPS:                                                 ║
║                                                              ║
║  1. Get Kite Connect API keys (Rs 2,000/month):             ║
║     https://developers.kite.trade                           ║
║                                                              ║
║  2. Edit .env file — add your KITE_API_KEY and              ║
║     KITE_API_SECRET                                          ║
║                                                              ║
║  3. Get FREE news API key (optional):                       ║
║     https://newsapi.org  (100 calls/day free)               ║
║                                                              ║
║  4. Every morning before trading:                           ║
║         python login.py                                      ║
║                                                              ║
║  5. Test with paper trading first (minimum 2 weeks):        ║
║         python paper_trading.py                              ║
║                                                              ║
║  6. Open live dashboard in browser:                         ║
║         http://localhost:8050                                ║
║                                                              ║
║  7. After 2 weeks of good paper results, go live:           ║
║         python main.py                                       ║
║                                                              ║
╠══════════════════════════════════════════════════════════════╣
║  REALISTIC WIN RATE: 50-62% on good strategies              ║
║  Test thoroughly before risking real money!                 ║
╚══════════════════════════════════════════════════════════════╝
""")

if __name__ == "__main__":
    main()
