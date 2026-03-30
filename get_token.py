"""
get_token.py  —  Emergency token extractor
==========================================
Use this if login.py still fails to get the access token.

INSTRUCTIONS:
1. Open this URL in your browser manually:
   (Run: python login.py  to see the URL, then copy it)

2. Log in with User ID + Password + TPIN

3. After TPIN, your browser shows "can't be reached" page.
   COPY THE FULL URL from the address bar.

4. Run: python get_token.py
   Paste the full URL when asked.

5. The access token will be saved automatically.
"""

import sys, re, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

def main():
    print("""
╔══════════════════════════════════════════════════════════╗
║  ZERODHA TOKEN EXTRACTOR — Emergency Fallback           ║
╚══════════════════════════════════════════════════════════╝

After entering your TPIN in the browser, copy the FULL URL
from the browser address bar and paste it below.

The URL looks like:
  http://127.0.0.1:8787/?request_token=XXXXX&status=success

""")

    try:
        from kiteconnect import KiteConnect
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "kiteconnect", "-q"])
        from kiteconnect import KiteConnect

    # Load env
    env = {}
    for path in [ROOT/".env", ROOT/".env.example"]:
        if path.exists():
            for line in path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                v = re.split(r'\s+#', v.strip())[0].strip().strip('"').strip("'")
                env[k.strip()] = v

    api_key    = env.get("KITE_API_KEY","").strip()
    api_secret = env.get("KITE_API_SECRET","").strip()

    bad = {"", "your_api_key_here", None}
    if api_key in bad:
        api_key    = input("Enter API KEY    : ").strip()
        api_secret = input("Enter API SECRET : ").strip()

    print(f"  Using key: {api_key[:4]}...{api_key[-4:]}\n")

    # Get URL or token from user
    raw = input("Paste the browser URL (or just the request_token): ").strip()

    # Extract token
    m = re.search(r'request_token=([^&\s]+)', raw)
    if m:
        token = m.group(1).strip()
    elif re.match(r'^[A-Za-z0-9+/=_-]{10,}$', raw):
        token = raw
    else:
        print(f"\n[ERROR] Cannot find request_token in: {raw[:100]}")
        print("Make sure you copied the full URL from the browser address bar.")
        sys.exit(1)

    print(f"\n  Token found: {token[:6]}...{token[-4:]}  (length={len(token)})")
    print("  Generating session...")

    kite = KiteConnect(api_key=api_key)
    try:
        session      = kite.generate_session(token, api_secret=api_secret)
        access_token = session["access_token"]
    except Exception as e:
        print(f"\n[ERROR] {e}")
        if "token" in str(e).lower():
            print("\n  The token expired (valid for ~2 min).")
            print("  Log in again in browser, copy the new URL immediately, run this again.")
        sys.exit(1)

    # Save
    try:
        from config.settings import ACCESS_TOKEN_FILE
        path = Path(ACCESS_TOKEN_FILE)
    except Exception:
        path = ROOT / "config" / "access_token.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(access_token.strip())

    kite.set_access_token(access_token)
    try:
        p = kite.profile()
        print(f"\n  Logged in as: {p['user_name']} ({p['user_id']})")
    except Exception:
        pass

    print(f"\n  Access token saved to: {path}")
    print(f"\n  Now run: python paper_trading.py\n")

if __name__ == "__main__":
    main()
