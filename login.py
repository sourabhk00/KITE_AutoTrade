"""
login.py — Complete Zerodha Login v3  (Fully Automated)
=========================================================
Solves the TPIN/redirect problem permanently.

HOW IT WORKS:
  Method A (Automatic): Opens browser, you log in manually,
    a local server on port 8787 catches the redirect token
    automatically — you never have to copy anything.

  Method B (URL extract): If the page shows "can't be reached",
    this script reads the URL from your clipboard OR asks you
    to paste the full browser URL — it extracts the token itself.

  Method C (Manual): Paste just the token directly.

Run:  python login.py
=========================================================
"""

import os, sys, re, time, json, socket, webbrowser, threading, subprocess
import urllib.parse, urllib.request, urllib.error
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# ── Terminal colours ───────────────────────────────────────
G = lambda s: f"\033[92m{s}\033[0m"   # green
R = lambda s: f"\033[91m{s}\033[0m"   # red
Y = lambda s: f"\033[93m{s}\033[0m"   # yellow
C = lambda s: f"\033[96m{s}\033[0m"   # cyan
B = lambda s: f"\033[1m{s}\033[0m"    # bold
W = lambda s: f"\033[97m{s}\033[0m"   # white

SEP = "─" * 60


def banner(msg, colour=G):
    print(colour(f"\n{'═'*60}"))
    print(colour(f"  {msg}"))
    print(colour(f"{'═'*60}\n"))


# ═══════════════════════════════════════════════════════════
#  INSTALL CHECK
# ═══════════════════════════════════════════════════════════
def ensure_kiteconnect():
    try:
        from kiteconnect import KiteConnect
        return KiteConnect
    except ImportError:
        print(Y("\nInstalling kiteconnect..."))
        subprocess.check_call([sys.executable, "-m", "pip", "install",
                                "kiteconnect", "-q"])
        from kiteconnect import KiteConnect
        return KiteConnect


# ═══════════════════════════════════════════════════════════
#  LOAD CREDENTIALS FROM .env
# ═══════════════════════════════════════════════════════════
def load_env():
    """Parse .env file robustly — handles comments, quotes, spaces."""
    env = {}
    for path in [ROOT / ".env", ROOT / ".env.example"]:
        if path.exists():
            for raw in path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip()
                # Strip inline comment
                v = re.split(r'\s+#', v)[0].strip()
                # Strip surrounding quotes
                v = v.strip('"').strip("'")
                if k:
                    env[k] = v
            if env.get("KITE_API_KEY","").replace("your_api_key_here",""):
                break
    return env


def get_credentials():
    env = load_env()
    key    = env.get("KITE_API_KEY", "").strip()
    secret = env.get("KITE_API_SECRET", "").strip()

    bad = {"", "your_api_key_here", "your_api_secret_here",
           "get_from_developers", None}

    if key in bad or secret in bad:
        banner("API Key Not Found in .env", R)
        print(B("  Your .env file needs your real Kite API credentials.\n"))
        print("  Get them from:  https://developers.kite.trade")
        print("  Log in → My Apps → Create App → Copy API Key + Secret\n")
        print(SEP)
        key    = input("  Paste your API KEY    : ").strip()
        secret = input("  Paste your API SECRET : ").strip()
        if not key or not secret:
            print(R("\n[ERROR] Both API Key and Secret are required.")); sys.exit(1)
        # Save to .env
        _write_env(key, secret)

    print(G(f"  Credentials loaded: {key[:4]}...{key[-4:]}"))
    return key, secret


def _write_env(key, secret):
    env_path = ROOT / ".env"
    template = (ROOT / ".env.example").read_text() if (ROOT / ".env.example").exists() else \
        "KITE_API_KEY=\nKITE_API_SECRET=\nPAPER_TRADING=true\nDASHBOARD_PORT=8050\n"
    template = re.sub(r"(?m)^KITE_API_KEY=.*$",    f"KITE_API_KEY={key}",    template)
    template = re.sub(r"(?m)^KITE_API_SECRET=.*$", f"KITE_API_SECRET={secret}", template)
    env_path.write_text(template)
    print(G(f"  Saved to .env"))


# ═══════════════════════════════════════════════════════════
#  LOCAL REDIRECT SERVER — catches the token automatically
# ═══════════════════════════════════════════════════════════
_token_store = {"token": None, "done": False}

SUCCESS_HTML = b"""<!DOCTYPE html><html><head><meta charset=utf-8>
<style>body{background:#0d1117;color:#e8f0fe;font-family:sans-serif;
text-align:center;padding:80px 20px}
h1{color:#00d4aa;font-size:28px;margin-bottom:16px}
p{color:#8892a4;font-size:15px}
.tick{font-size:60px;color:#00d4aa}</style></head><body>
<div class=tick>&#10003;</div>
<h1>Login Successful!</h1>
<p>Token captured automatically.</p>
<p>You can <strong>close this tab</strong> and return to your terminal.</p>
</body></html>"""

FAIL_HTML = b"""<!DOCTYPE html><html><head><meta charset=utf-8>
<style>body{background:#0d1117;color:#e8f0fe;font-family:sans-serif;
text-align:center;padding:80px 20px}
h1{color:#ff4757;font-size:24px}p{color:#8892a4}</style></head><body>
<h1>Login cancelled</h1><p>Please run <code>python login.py</code> again.</p>
</body></html>"""


class TokenHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        qs     = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        token  = qs.get("request_token", [None])[0]
        status = qs.get("status", [""])[0]

        if token and status == "success":
            _token_store["token"] = token
            _token_store["done"]  = True
            self._respond(200, SUCCESS_HTML)
        else:
            _token_store["done"] = True
            self._respond(200, FAIL_HTML)

    def _respond(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass   # silence


def _port_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def start_server(port=8787):
    if not _port_free(port):
        # Try alternate port
        port = 8788
        if not _port_free(port):
            return None, None
    try:
        srv = HTTPServer(("127.0.0.1", port), TokenHandler)
        t   = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        return srv, port
    except Exception:
        return None, None


# ═══════════════════════════════════════════════════════════
#  EXTRACT TOKEN FROM A FULL URL
# ═══════════════════════════════════════════════════════════
def extract_token_from_url(url: str):
    """Works on any of these formats:
       http://127.0.0.1:8787/?request_token=XYZ&status=success
       https://127.0.0.1/?request_token=XYZ&action=login&status=success
       request_token=XYZ&status=success    (partial paste)
       XYZ                                 (just the token)
    """
    url = url.strip()
    # Already looks like a plain token (no = or & or /)
    if re.match(r'^[A-Za-z0-9+/=_-]{10,}$', url) and '=' not in url:
        return url
    # Extract from URL
    m = re.search(r'[?&]?request_token=([^&\s]+)', url)
    if m:
        return m.group(1).strip()
    return None


# ═══════════════════════════════════════════════════════════
#  TRY CLIPBOARD (Windows + Mac)
# ═══════════════════════════════════════════════════════════
def try_clipboard():
    try:
        if sys.platform == "win32":
            import subprocess
            result = subprocess.run(
                ["powershell", "-command", "Get-Clipboard"],
                capture_output=True, text=True, timeout=3
            )
            return result.stdout.strip()
        elif sys.platform == "darwin":
            import subprocess
            result = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=3)
            return result.stdout.strip()
    except Exception:
        pass
    return ""


# ═══════════════════════════════════════════════════════════
#  GENERATE SESSION WITH RETRY
# ═══════════════════════════════════════════════════════════
def generate_session(kite, token: str, secret: str):
    token = token.strip()
    # Clean up if user pasted the full URL
    extracted = extract_token_from_url(token)
    if extracted:
        token = extracted

    if not token:
        raise ValueError("Empty token")

    print(f"\n  Using token: {B(token[:6])}...{token[-4:]}  (length: {len(token)})")

    try:
        session = kite.generate_session(token, api_secret=secret)
        return session["access_token"]
    except Exception as e:
        err = str(e).lower()
        if "token" in err or "expired" in err or "invalid" in err:
            raise RuntimeError(
                f"Token rejected by Zerodha: {e}\n\n"
                "  COMMON CAUSE: Each request_token is valid for ~2 minutes\n"
                "  and can only be used ONCE. You may have:\n"
                "    • Waited too long before pasting\n"
                "    • Reused a token from a previous attempt\n"
                "  FIX: Run login.py again and paste the token immediately."
            )
        raise


# ═══════════════════════════════════════════════════════════
#  SAVE ACCESS TOKEN
# ═══════════════════════════════════════════════════════════
def save_token(access_token: str):
    # Try to get path from settings
    try:
        from config.settings import ACCESS_TOKEN_FILE
        path = Path(ACCESS_TOKEN_FILE)
    except Exception:
        path = ROOT / "config" / "access_token.txt"

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(access_token.strip())
    return path


# ═══════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════
def main():
    banner("ZERODHA KITE BOT v4.0 — DAILY LOGIN", C)

    KiteConnect = ensure_kiteconnect()
    api_key, api_secret = get_credentials()
    kite = KiteConnect(api_key=api_key)
    login_url = kite.login_url()

    # Start local redirect server
    server, port = start_server()
    server_ok = server is not None

    print(f"\n{B('STEP 1')} — Open this URL in your browser:")
    print(f"\n  {C(login_url)}\n")
    print(f"  (Browser will open automatically in 2 seconds...)\n")
    time.sleep(2)
    try:
        webbrowser.open(login_url)
    except Exception:
        pass

    print(SEP)
    print(B("STEP 2") + " — Complete login in the browser:")
    print("   Enter User ID  (e.g. AB1234)")
    print("   Enter Password")
    print("   Enter TPIN / PIN  (6-digit number)")
    if server_ok:
        print(f"\n  {G('Auto-capture is ON')} — when you finish the TPIN step,")
        print(f"  the token will be captured automatically.")
        print(f"  Local server listening on port {port}")
    print(SEP)

    # ── Wait for auto-capture ──────────────────────────────
    request_token = None

    if server_ok:
        print(f"\n  Waiting for you to complete login (up to 3 minutes)...")
        print(f"  {Y('After entering TPIN, wait 5 seconds then check here.')}\n")

        for tick in range(180):
            if _token_store["done"]:
                request_token = _token_store["token"]
                break
            if tick % 30 == 29:
                print(f"  Still waiting... ({tick+1}s elapsed) "
                      f"— complete the TPIN step in your browser")
            time.sleep(1)

        if server:
            try: server.shutdown()
            except: pass

    # ── Token captured automatically ──────────────────────
    if request_token:
        print(G("\n  Token auto-captured! No need to copy anything."))

    # ── Auto-capture failed — try clipboard then manual ───
    else:
        print(Y("\n  Auto-capture did not work. Let's get the token manually.\n"))
        print(B("WHAT TO DO:"))
        print("""
  After you entered your TPIN, your browser redirected to a URL.
  The page may say "This site can't be reached" — THAT IS NORMAL.

  Look at the ADDRESS BAR of your browser. The URL looks like:

  """ + C("  http://127.0.0.1:8787/?request_token=AbCd1234XyZ&status=success") + """
  """ + C("  https://127.0.0.1/?request_token=AbCd1234XyZ&action=login&status=success") + """

  You need the value after  request_token=  and before  &

  """)
        print(SEP)

        # Try clipboard first
        clip = try_clipboard()
        if clip and ("request_token" in clip or len(clip) > 15):
            extracted = extract_token_from_url(clip)
            if extracted:
                print(Y(f"  Found in clipboard: {extracted[:6]}...{extracted[-4:]}"))
                confirm = input("  Use this token? [Y/n]: ").strip().lower()
                if confirm != "n":
                    request_token = extracted

        # Manual input
        if not request_token:
            print(B("\n  Option 1: Paste the FULL URL from your browser address bar"))
            print(B("  Option 2: Paste just the request_token value"))
            print(B("  Option 3: Type  RETRY  to open the login page again\n"))

            while not request_token:
                raw = input("  Paste here: ").strip()

                if raw.upper() == "RETRY":
                    webbrowser.open(login_url)
                    print(Y("\n  Browser reopened. Complete login, then paste the URL here."))
                    continue

                if not raw:
                    print(Y("  Nothing entered. Try again or type RETRY."))
                    continue

                extracted = extract_token_from_url(raw)
                if extracted:
                    request_token = extracted
                    print(G(f"  Token extracted: {extracted[:6]}...{extracted[-4:]}"))
                else:
                    print(R(f"  Could not find a token in: {raw[:80]}"))
                    print(Y("  Make sure you copy the full URL from the address bar."))

    # ── Generate session ───────────────────────────────────
    print(f"\n  Connecting to Zerodha...")
    try:
        access_token = generate_session(kite, request_token, api_secret)
    except RuntimeError as e:
        print(R(f"\n[ERROR] {e}"))
        sys.exit(1)
    except Exception as e:
        print(R(f"\n[ERROR] Unexpected error: {e}"))
        err = str(e).lower()
        if "api_key" in err:
            print(Y("  Check your KITE_API_KEY in .env"))
        sys.exit(1)

    # ── Save token ─────────────────────────────────────────
    saved_path = save_token(access_token)

    # ── Verify with profile ────────────────────────────────
    try:
        kite.set_access_token(access_token)
        p = kite.profile()
        name, uid, email = p["user_name"], p["user_id"], p["email"]
    except Exception:
        name = uid = email = "(could not fetch)"

    banner("LOGIN SUCCESSFUL", G)
    print(G(f"  Name    : {name}"))
    print(G(f"  User ID : {uid}"))
    print(G(f"  Email   : {email}"))
    print(G(f"  Token   : saved to {saved_path}"))
    print(f"\n  {B('Next step:')}  python paper_trading.py")
    print(f"  {B('Dashboard:')} http://localhost:8050\n")


# ═══════════════════════════════════════════════════════════
#  TROUBLESHOOT REFERENCE
# ═══════════════════════════════════════════════════════════
TROUBLESHOOT = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMMON PROBLEMS AND FIXES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Problem: "This site can't be reached" after TPIN
  Fix: NORMAL. Look at the address bar URL, copy it, paste
       into the terminal when it asks. The token is in the URL.

Problem: request_token not in the URL
  Fix: You are not fully logged in yet. Go back and complete
       the TPIN step, then the redirect URL will have the token.

Problem: "Token rejected" or "expired token"
  Fix: Each token expires in ~2 minutes. Run login.py again
       and paste the token immediately after getting it.

Problem: "Invalid api_key"
  Fix: Open .env file, check KITE_API_KEY is correct.
       Get keys from: https://developers.kite.trade

Problem: TPIN vs TOTP confusion
  TPIN: 6-digit number you set on Zerodha website (like a PIN)
  TOTP: 6-digit code from Google Authenticator / Zerodha app
  Use whichever your account has enabled.

Problem: Screen stays blank after TPIN
  Fix: Wait 5 seconds. If nothing happens, check the browser
       address bar — the token should be in the URL already.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(Y("\n\nLogin cancelled."))
        sys.exit(0)
    except SystemExit:
        raise
    except Exception as e:
        print(R(f"\n[UNEXPECTED ERROR] {e}"))
        print(TROUBLESHOOT)
        sys.exit(1)
