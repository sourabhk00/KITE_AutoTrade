"""
visualization/dashboard.py  v7
================================
Professional Bloomberg-style trading dashboard.
BUG FIX: html/dbc imported at module level, not inside build_app.

New in v7:
  • Session Control Panel — set capital, daily target, SL, positions
  • Start/Stop bot button
  • Auto-order log with timestamps
  • All 18 live index tiles
  • Scrolling ticker tape
http://localhost:8050
"""

import logging
import threading
import pandas as pd
import numpy as np

logger = logging.getLogger("Dashboard")

# ── FIX: Import dash components at module level ──────────────────
try:
    from dash import html, dcc
    import dash_bootstrap_components as dbc
    _DASH_OK = True
except ImportError:
    _DASH_OK = False
    html = None; dcc = None; dbc = None

# ── Colors ───────────────────────────────────────────────────────
BG    = "#050a0e"
CARD  = "#0d1421"
CARD2 = "#0a1628"
BDR   = "#1e3050"
GRN   = "#00e5aa"
RED   = "#ff3d57"
AMB   = "#ffb300"
BLU   = "#2196f3"
PUR   = "#9c27b0"
CYN   = "#00bcd4"
MUT   = "#607d8b"
TXT   = "#eceff1"

FONT  = "JetBrains Mono,Fira Code,Consolas,monospace"

CSS = f"""
*{{ box-sizing: border-box; }}
body {{ background:{BG}; font-family:{FONT}; color:{TXT}; margin:0; padding:0; }}
.Select-control,.Select-menu-outer {{ background:{CARD2} !important; border-color:{BDR} !important; color:{TXT} !important; }}
.Select-value-label,.Select-option {{ color:{TXT} !important; }}
.Select-option:hover {{ background:{CARD} !important; }}
::-webkit-scrollbar {{ width:4px; }}
::-webkit-scrollbar-thumb {{ background:{BDR}; border-radius:2px; }}
.ticker-wrap {{ overflow:hidden; background:{CARD}; border-bottom:1px solid {BDR}; padding:5px 0; }}
.ticker-move {{ display:flex; gap:0; animation:tick 80s linear infinite; white-space:nowrap; }}
@keyframes tick {{ 0%{{transform:translateX(0)}} 100%{{transform:translateX(-50%)}} }}
.t-item {{ display:inline-flex; gap:6px; align-items:center; font-size:11px; padding:0 28px; border-right:1px solid {BDR}; }}
.badge-paper {{ background:rgba(33,150,243,.15); color:{BLU}; border:1px solid {BLU}; border-radius:4px; padding:2px 8px; font-size:11px; font-weight:700; }}
.badge-live  {{ background:rgba(255,61,87,.15); color:{RED}; border:1px solid {RED}; border-radius:4px; padding:2px 8px; font-size:11px; font-weight:700; animation:blink 1.5s infinite; }}
@keyframes blink {{ 0%,100%{{opacity:1}} 50%{{opacity:.4}} }}
.sc {{ background:{CARD}; border:1px solid {BDR}; border-radius:8px; padding:12px 14px; height:100%; }}
.sc-lbl {{ font-size:9px; color:{MUT}; text-transform:uppercase; letter-spacing:1px; margin-bottom:4px; }}
.sc-val {{ font-size:20px; font-weight:700; line-height:1.2; }}
.sc-sub {{ font-size:9px; color:{MUT}; margin-top:3px; }}
.idx-tile {{ background:{CARD}; border:1px solid {BDR}; border-radius:6px; padding:7px 8px; text-align:center; min-height:62px; }}
.idx-name {{ font-size:8px; color:{MUT}; text-transform:uppercase; letter-spacing:.3px; }}
.idx-val  {{ font-size:13px; font-weight:700; margin:2px 0; }}
.idx-chg  {{ font-size:9px; font-weight:600; }}
.panel {{ background:{CARD}; border:1px solid {BDR}; border-radius:8px; padding:10px 12px; }}
.ph {{ font-size:9px; color:{MUT}; text-transform:uppercase; letter-spacing:1px; margin-bottom:7px; border-bottom:1px solid {BDR}; padding-bottom:5px; }}
.pos-row {{ border-bottom:1px solid {BDR}; padding:5px 0; }}
.trade-row td {{ padding:3px 5px; font-size:10px; }}
.ctrl-input {{ background:{CARD2}; border:1px solid {BDR}; border-radius:5px; color:{TXT}; padding:6px 10px; font-size:12px; width:100%; font-family:{FONT}; }}
.ctrl-input:focus {{ border-color:{BLU}; outline:none; }}
.btn-start {{ background:{GRN}; color:#000; border:none; border-radius:5px; padding:8px 20px; font-size:12px; font-weight:700; cursor:pointer; font-family:{FONT}; width:100%; }}
.btn-stop  {{ background:{RED}; color:{TXT}; border:none; border-radius:5px; padding:8px 20px; font-size:12px; font-weight:700; cursor:pointer; font-family:{FONT}; width:100%; }}
.order-row {{ font-size:10px; border-bottom:1px solid {BDR}; padding:3px 0; display:flex; gap:10px; }}
"""


def _safe_float(v, default=0.0):
    try:
        import math; x = float(v)
        return default if (math.isnan(x) or math.isinf(x)) else x
    except Exception:
        return default


# ── Module-level helper components (html imported above) ──────────

def _card(elem_id, label, default, sub):
    if not html:
        return None
    return html.Div([
        html.Div(label, className="sc-lbl"),
        html.Div(default, id=elem_id, className="sc-val"),
        html.Div(sub,    className="sc-sub"),
    ], className="sc")


def _ph(txt):
    if not html: return None
    return html.Div(txt, className="ph")


def _empty_fig(msg="Waiting for data..."):
    try:
        import plotly.graph_objects as go
        fig = go.Figure()
        fig.update_layout(
            template="plotly_dark", paper_bgcolor=BG, plot_bgcolor="#070e1a",
            font=dict(color=TXT, size=11, family=FONT),
            margin=dict(l=50, r=10, t=25, b=10),
            annotations=[dict(text=msg, showarrow=False,
                              font=dict(color=MUT, size=12))],
        )
        return fig
    except Exception:
        return {}


# ── Main app builder ──────────────────────────────────────────────

def build_app(risk_mgr, get_candles_fn, index_tracker, ipo_analyzer,
              session_obj, bot_controller, config):
    """
    Build the Dash app.
    session_obj    — TradingSession (mutable, shared with bot)
    bot_controller — dict with 'running': bool, 'start': callable, 'stop': callable
    """
    if not _DASH_OK:
        logger.error("Dash not installed. Run: pip install dash dash-bootstrap-components plotly")
        return None

    import dash
    from dash import Input, Output, State
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    watchlist = list(getattr(config, "WATCHLIST", ["RELIANCE"]))
    intervals = ["1minute", "3minute", "5minute", "15minute", "60minute", "day"]

    app = dash.Dash(
        __name__,
        external_stylesheets=[dbc.themes.CYBORG],
        suppress_callback_exceptions=True,
        update_title=None,
        title="⚡ Kite Bot v7",
    )
    app.index_string = app.index_string.replace("</head>", f"<style>{CSS}</style></head>")

    # ════════════════════════════════════════════════════════════
    #  LAYOUT
    # ════════════════════════════════════════════════════════════
    app.layout = html.Div(style={"backgroundColor": BG, "minHeight": "100vh"}, children=[

        # Ticker tape
        html.Div(className="ticker-wrap", children=[
            html.Div(id="ticker-tape", className="ticker-move"),
        ]),

        html.Div(style={"padding": "8px 14px"}, children=[

            # Top bar
            dbc.Row([
                dbc.Col(html.Div([
                    html.Span("⚡ KITE BOT v7.0",
                              style={"color": BLU, "fontSize": "15px",
                                     "fontWeight": "700", "letterSpacing": "2px"}),
                    html.Span("  AUTO TRADING TERMINAL",
                              style={"color": MUT, "fontSize": "10px"}),
                ]), width=5),
                dbc.Col(html.Div(id="topbar-right",
                                 style={"textAlign": "right", "fontSize": "11px",
                                        "color": MUT}), width=7),
            ], className="mb-2 align-items-center"),

            # P&L stat row
            dbc.Row([
                dbc.Col(_card("pnl-total",   "Total P&L",    "₹0",    "daily progress"), width=2),
                dbc.Col(_card("pnl-real",    "Realized",     "₹0",    "booked"),          width=2),
                dbc.Col(_card("pnl-unreal",  "Unrealized",   "₹0",    "open pos"),        width=2),
                dbc.Col(_card("winrate-val", "Win Rate",     "0%",    "W / L record"),    width=2),
                dbc.Col(_card("pos-val",     "Positions",    "0/5",   "open / max"),      width=2),
                dbc.Col(_card("regime-val",  "Regime",       "—",     "market + VIX"),    width=2),
            ], className="mb-2"),

            # Main area: chart + control panel
            dbc.Row([
                # Chart
                dbc.Col([
                    html.Div(className="panel", children=[
                        dbc.Row([
                            dbc.Col(dcc.Dropdown(id="sym", value=watchlist[0] if watchlist else "RELIANCE",
                                                  options=[{"label": s, "value": s} for s in watchlist],
                                                  style={"width": "170px"}), width="auto"),
                            dbc.Col(dcc.Dropdown(id="ivl", value="5minute",
                                                  options=[{"label": i, "value": i} for i in intervals],
                                                  style={"width": "118px"}), width="auto"),
                            dbc.Col(html.Span(id="ltp-val",
                                              style={"fontSize": "17px", "fontWeight": "700",
                                                     "color": GRN, "marginLeft": "10px"}), width="auto"),
                            dbc.Col(html.Span(id="chg-val",
                                              style={"fontSize": "12px", "marginLeft": "5px"}), width="auto"),
                            dbc.Col(html.A("↗ Kite Chart", id="kite-link", href="#", target="_blank",
                                           style={"fontSize": "10px", "color": BLU,
                                                  "border": f"1px solid {BDR}",
                                                  "padding": "3px 8px", "borderRadius": "4px",
                                                  "textDecoration": "none", "marginLeft": "8px"}), width="auto"),
                        ], align="center", className="mb-2"),
                        dcc.Graph(id="main-chart", style={"height": "540px"},
                                  config={"displayModeBar": True,
                                          "modeBarButtonsToRemove": ["lasso2d", "select2d"],
                                          "scrollZoom": True}),
                    ]),
                ], width=9),

                # Right panel: controls + positions
                dbc.Col([
                    # ── SESSION CONTROL PANEL ─────────────────
                    html.Div(className="panel", style={"marginBottom": "8px"}, children=[
                        _ph("Trading Parameters"),
                        dbc.Row([
                            dbc.Col([
                                html.Div("Capital (₹)", style={"fontSize": "9px", "color": MUT, "marginBottom": "2px"}),
                                dcc.Input(id="inp-capital", type="number", placeholder="45000",
                                          value=session_obj.capital,
                                          className="ctrl-input", debounce=True),
                            ], width=6, className="mb-2"),
                            dbc.Col([
                                html.Div("Daily Target (₹)", style={"fontSize": "9px", "color": MUT, "marginBottom": "2px"}),
                                dcc.Input(id="inp-target", type="number", placeholder="4000",
                                          value=session_obj.daily_target,
                                          className="ctrl-input", debounce=True),
                            ], width=6, className="mb-2"),
                            dbc.Col([
                                html.Div("Max Loss/Day (₹)", style={"fontSize": "9px", "color": MUT, "marginBottom": "2px"}),
                                dcc.Input(id="inp-loss", type="number", placeholder="2000",
                                          value=session_obj.daily_loss_limit,
                                          className="ctrl-input", debounce=True),
                            ], width=6, className="mb-2"),
                            dbc.Col([
                                html.Div("Stop Loss %", style={"fontSize": "9px", "color": MUT, "marginBottom": "2px"}),
                                dcc.Input(id="inp-sl", type="number", placeholder="1.0",
                                          value=session_obj.stop_loss_pct, step=0.1,
                                          className="ctrl-input", debounce=True),
                            ], width=6, className="mb-2"),
                            dbc.Col([
                                html.Div("Max Positions", style={"fontSize": "9px", "color": MUT, "marginBottom": "2px"}),
                                dcc.Input(id="inp-pos", type="number", placeholder="5",
                                          value=session_obj.max_positions, min=1, max=10,
                                          className="ctrl-input", debounce=True),
                            ], width=6, className="mb-2"),
                            dbc.Col([
                                html.Div("Target Multiplier", style={"fontSize": "9px", "color": MUT, "marginBottom": "2px"}),
                                dcc.Input(id="inp-mult", type="number", placeholder="2.5",
                                          value=session_obj.target_multiplier, step=0.1,
                                          className="ctrl-input", debounce=True),
                            ], width=6, className="mb-2"),
                        ]),
                        html.Div(id="session-summary",
                                 style={"fontSize": "9px", "color": MUT,
                                        "background": CARD2, "borderRadius": "4px",
                                        "padding": "6px", "marginBottom": "8px",
                                        "fontFamily": FONT}),
                        dbc.Row([
                            dbc.Col(html.Button("▶ START AUTO TRADING",
                                                id="btn-start", n_clicks=0,
                                                className="btn-start"), width=6),
                            dbc.Col(html.Button("⏹ STOP",
                                                id="btn-stop", n_clicks=0,
                                                className="btn-stop"), width=6),
                        ]),
                        html.Div(id="bot-status-msg",
                                 style={"fontSize": "10px", "color": GRN,
                                        "marginTop": "6px", "textAlign": "center"}),
                    ]),

                    # Open positions
                    html.Div(className="panel", style={"marginBottom": "8px"}, children=[
                        _ph("Open Positions"),
                        html.Div(id="pos-list"),
                    ]),

                    # Strategy stats
                    html.Div(className="panel", children=[
                        _ph("Strategy Performance"),
                        html.Div(id="strat-list"),
                    ]),
                ], width=3),
            ], className="mb-2"),

            # Bottom row
            dbc.Row([
                dbc.Col(html.Div(className="panel", children=[
                    _ph("Auto Order Log"),
                    html.Div(id="order-log", style={"maxHeight": "200px", "overflowY": "auto"}),
                ]), width=4),
                dbc.Col(html.Div(className="panel", children=[
                    _ph("Closed Trades"),
                    html.Div(id="trades-panel"),
                ]), width=5),
                dbc.Col(html.Div(className="panel", children=[
                    _ph("IPO Tracker"),
                    html.Div(id="ipo-panel"),
                ]), width=3),
            ], className="mb-2"),

            # Index grid
            html.Div(className="panel", children=[
                _ph("Live Indices — All Segments"),
                dbc.Row(id="idx-grid", className="g-1"),
            ]),
        ]),

        # Timers
        dcc.Interval(id="t3",  interval=3_000,  n_intervals=0),
        dcc.Interval(id="t15", interval=15_000, n_intervals=0),
        dcc.Interval(id="t30", interval=30_000, n_intervals=0),
    ])

    # ════════════════════════════════════════════════════════════
    #  CALLBACK — Session parameter update
    # ════════════════════════════════════════════════════════════
    @app.callback(
        Output("session-summary", "children"),
        [Input("inp-capital","value"), Input("inp-target","value"),
         Input("inp-loss","value"),    Input("inp-sl","value"),
         Input("inp-pos","value"),     Input("inp-mult","value")],
    )
    def update_session(capital, target, loss, sl, pos, mult):
        try:
            updates = {}
            if capital and float(capital) > 0: updates["capital"]           = float(capital)
            if target  and float(target)  > 0: updates["daily_target"]      = float(target)
            if loss    and float(loss)    > 0: updates["daily_loss_limit"]  = float(loss)
            if sl      and float(sl)      > 0: updates["stop_loss_pct"]     = float(sl)
            if pos     and int(pos)       > 0: updates["max_positions"]     = int(pos)
            if mult    and float(mult)    > 0: updates["target_multiplier"] = float(mult)
            if updates:
                session_obj.update(**updates)
                session_obj.apply_to_config(config)
            return session_obj.summary()
        except Exception as e:
            return f"Error: {e}"

    # ════════════════════════════════════════════════════════════
    #  CALLBACK — Start / Stop buttons
    # ════════════════════════════════════════════════════════════
    @app.callback(
        Output("bot-status-msg", "children"),
        [Input("btn-start", "n_clicks"), Input("btn-stop", "n_clicks")],
        prevent_initial_call=True,
    )
    def handle_bot_buttons(n_start, n_stop):
        from dash import callback_context
        ctx = callback_context
        if not ctx.triggered:
            return ""
        triggered = ctx.triggered[0]["prop_id"]
        if "btn-start" in triggered:
            try:
                bot_controller["start"]()
                return "▶ Bot started — auto-trading active"
            except Exception as e:
                return f"Start error: {e}"
        elif "btn-stop" in triggered:
            try:
                bot_controller["stop"]()
                return "⏹ Bot stopped"
            except Exception as e:
                return f"Stop error: {e}"
        return ""

    # ════════════════════════════════════════════════════════════
    #  CALLBACK 1 — 3s: P&L + positions + order log
    # ════════════════════════════════════════════════════════════
    @app.callback(
        [Output("pnl-total","children"), Output("pnl-real","children"),
         Output("pnl-unreal","children"), Output("winrate-val","children"),
         Output("pos-val","children"),   Output("regime-val","children"),
         Output("topbar-right","children"), Output("pos-list","children"),
         Output("strat-list","children"), Output("order-log","children"),
         Output("trades-panel","children")],
        Input("t3", "n_intervals"),
    )
    def cb_fast(_):
        from datetime import datetime
        rm = risk_mgr
        pnl = rm.total_pnl; rea = rm.daily_realized_pnl; unr = rm.unrealized_pnl
        wr  = rm.win_rate;   prog = rm.target_progress()
        mode   = "PAPER" if config.PAPER_TRADING else "LIVE"
        regime = index_tracker.market_regime() if index_tracker else "—"
        vix    = index_tracker.get_ltp("INDIA VIX") if index_tracker else 0

        def fmt(n): return f"{'+'if n>=0 else ''}₹{abs(n):,.0f}"
        def clr(n): return GRN if n >= 0 else RED

        bar_w = max(0, min(100, prog))
        pnl_el = html.Div([
            html.Div(fmt(pnl), className="sc-val", style={"color": clr(pnl)}),
            html.Div(style={"height": "3px", "background": BDR, "borderRadius": "2px", "marginTop": "4px"},
                     children=[html.Div(style={"height": "100%", "width": f"{bar_w}%",
                                               "background": clr(pnl), "borderRadius": "2px"})]),
            html.Div(f"{prog:.1f}% of ₹{config.DAILY_TARGET:,}", className="sc-sub"),
        ])
        rea_el = html.Div([html.Div(fmt(rea), className="sc-val", style={"color": clr(rea)}),
                            html.Div("booked today", className="sc-sub")])
        unr_el = html.Div([html.Div(fmt(unr), className="sc-val", style={"color": clr(unr)}),
                            html.Div(f"{len(rm.positions)} open", className="sc-sub")])
        wr_el  = html.Div([html.Div(f"{wr:.1f}%", className="sc-val", style={"color": BLU}),
                            html.Div(f"{rm.win_count}W/{rm.loss_count}L/{rm.trade_count}T", className="sc-sub")])
        pos_el = html.Div([html.Div(f"{len(rm.positions)}/{config.MAX_POSITIONS}", className="sc-val",
                                     style={"color": AMB}),
                            html.Div(f"Heat ₹{rm.portfolio_heat:.0f}", className="sc-sub")])
        rg_clr = GRN if regime=="BULLISH" else (RED if regime=="BEARISH" else AMB)
        reg_el = html.Div([html.Div(regime[:7], className="sc-val",
                                     style={"color": rg_clr, "fontSize": "14px"}),
                            html.Div(f"VIX {vix:.1f}" if vix else "VIX —", className="sc-sub")])

        mode_badge = html.Span(mode, className=f"badge-{'paper' if config.PAPER_TRADING else 'live'}")
        topbar = html.Span([
            mode_badge, "  ",
            html.Span(datetime.now().strftime("%H:%M:%S  %d-%b-%Y"), style={"color": MUT}), "  ",
            html.Span("● RUNNING", style={"color": GRN}),
            f"  Streak: {rm.consecutive_wins}W/{rm.consecutive_losses}L",
        ])

        # Positions
        pos_rows = []
        for sym, pos in rm.positions.items():
            pc = GRN if pos.pnl >= 0 else RED
            pos_rows.append(html.Div([
                html.Div([
                    html.Span(sym, style={"fontWeight":"700","color":CYN,"fontSize":"12px"}),
                    html.Span(f" {pos.action}", style={"color":GRN if pos.action=="BUY" else RED,"fontSize":"10px"}),
                    html.Span(fmt(pos.pnl), style={"color":pc,"fontWeight":"700","float":"right","fontSize":"12px"}),
                ]),
                html.Div(f"₹{pos.entry_price:.2f}→₹{pos.current_price:.2f} "
                         f"SL=₹{pos.trailing_sl:.2f} TGT=₹{pos.target:.2f}",
                         style={"fontSize":"9px","color":MUT}),
                html.Div(pos.strategy[:38], style={"fontSize":"9px","color":PUR}),
            ], className="pos-row"))
        if not pos_rows:
            pos_rows = [html.Div("No open positions", style={"color":MUT,"fontSize":"11px","padding":"6px 0"})]

        # Strategy stats
        strat_rows = []
        for name, st in getattr(rm, "_strat_stats", {}).items():
            tot = st.get("wins",0)+st.get("losses",0)
            wr_ = st["wins"]/tot*100 if tot else 0
            strat_rows.append(html.Div([
                html.Span(name[:18], style={"fontSize":"10px","color":TXT}),
                html.Span(f" {st.get('wins',0)}W/{st.get('losses',0)}L {wr_:.0f}%",
                          style={"fontSize":"10px","color":BLU,"float":"right"}),
            ], style={"borderBottom":f"1px solid {BDR}","padding":"2px 0"}))

        # Order log
        order_rows = []
        for t in reversed(getattr(rm, "order_log", [])[-20:]):
            oc = GRN if t.get("action")=="BUY" else RED
            order_rows.append(html.Div([
                html.Span(str(t.get("ts",""))[-8:], style={"color":MUT,"minWidth":"42px"}),
                html.Span(t.get("symbol",""), style={"color":CYN,"fontWeight":"700","minWidth":"80px"}),
                html.Span(t.get("action",""), style={"color":oc,"minWidth":"36px"}),
                html.Span(f"₹{_safe_float(t.get('price',0)):.2f}", style={"color":TXT,"minWidth":"70px"}),
                html.Span(f"Qty={t.get('qty',0)}", style={"color":MUT}),
                html.Span(t.get("type",""), style={"color":AMB,"fontSize":"9px"}),
            ], className="order-row"))
        if not order_rows:
            order_rows = [html.Div("No orders yet", style={"color":MUT,"fontSize":"10px","padding":"4px 0"})]

        # Trades table
        rows = []
        for t in reversed(rm.closed_trades[-15:]):
            p = t.get("pnl",0)
            rows.append(html.Tr([
                html.Td(str(t.get("exit_time",""))[-8:-3], style={"color":MUT}),
                html.Td(t.get("symbol",""), style={"color":CYN,"fontWeight":"700"}),
                html.Td(html.Span(t.get("action",""),
                                  style={"color":GRN if t.get("action")=="BUY" else RED,"fontWeight":"700"})),
                html.Td(f"₹{_safe_float(t.get('entry_price',0)):.1f}", style={"color":MUT}),
                html.Td(f"₹{_safe_float(t.get('exit_price',0)):.1f}", style={"color":MUT}),
                html.Td(f"{'+'if p>=0 else ''}₹{abs(p):.0f}",
                        style={"color":GRN if p>=0 else RED,"fontWeight":"700"}),
                html.Td(t.get("reason","").replace("CLOSED_","").replace("_"," "),
                        style={"color":MUT,"fontSize":"9px"}),
            ], className="trade-row"))
        trades_el = html.Table(
            [html.Thead(html.Tr([
                html.Th(h, style={"color":MUT,"fontSize":"9px","textTransform":"uppercase",
                                   "padding":"3px 5px","borderBottom":f"1px solid {BDR}"})
                for h in ["Time","Symbol","Dir","Entry","Exit","P&L","Reason"]
            ])),
             html.Tbody(rows if rows else [html.Tr([
                 html.Td("No trades yet", colSpan=7,
                         style={"color":MUT,"padding":"10px","textAlign":"center"})])])],
            style={"width":"100%","borderCollapse":"collapse"},
        )

        return (pnl_el, rea_el, unr_el, wr_el, pos_el, reg_el,
                topbar, pos_rows, strat_rows, order_rows, trades_el)

    # ════════════════════════════════════════════════════════════
    #  CALLBACK 2 — 15s: Live chart
    # ════════════════════════════════════════════════════════════
    @app.callback(
        [Output("main-chart","figure"), Output("ltp-val","children"),
         Output("chg-val","children"),  Output("kite-link","href")],
        [Input("t15","n_intervals"), Input("sym","value"), Input("ivl","value")],
    )
    def cb_chart(_, symbol, interval):
        kite_url = f"https://kite.zerodha.com/chart/web/ciq/NSE/{symbol}/EQ"
        if not symbol:
            return _empty_fig(), "—", "", kite_url
        try:
            df = get_candles_fn(symbol, interval)
        except Exception as e:
            return _empty_fig(f"Error: {e}"), "—", "", kite_url
        if df is None or len(df) < 10:
            return _empty_fig(f"No data for {symbol}"), "—", "", kite_url

        try:
            c=df["close"].astype(float); h=df["high"].astype(float)
            l=df["low"].astype(float);   v=df["volume"].astype(float)
            o=df["open"].astype(float)
            dt=df["datetime"] if "datetime" in df.columns else pd.RangeIndex(len(df))
            ltp = _safe_float(c.iloc[-1]); prev = _safe_float(c.iloc[-2]) if len(c)>1 else ltp
            chg = ltp-prev; chg_pct = chg/prev*100 if prev else 0
            ltp_c = GRN if ltp >= prev else RED

            def ema(s,n): return s.ewm(span=n,adjust=False).mean()
            e9=ema(c,9); e21=ema(c,21); e50=ema(c,min(50,len(c)-1))
            bm=c.rolling(min(20,len(c))).mean(); bs=c.rolling(min(20,len(c))).std().fillna(0)
            bbu=bm+2*bs; bbl=bm-2*bs
            vwap_s=((h+l+c)/3*v).cumsum()/v.cumsum().replace(0,1e-9)
            tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
            atr=tr.ewm(span=14,adjust=False).mean()
            st_u=(h+l)/2+3*atr; st_l=(h+l)/2-3*atr

            delta=c.diff(); gain=delta.clip(lower=0).ewm(alpha=1/14,adjust=False).mean()
            loss=(-delta.clip(upper=0)).ewm(alpha=1/14,adjust=False).mean()
            rsi=100-100/(1+gain/loss.replace(0,1e-9))
            mac=ema(c,12)-ema(c,26); sig_=ema(mac,9); hist=mac-sig_
            lo14=l.rolling(min(14,len(l))).min(); hi14=h.rolling(min(14,len(h))).max()
            sk=(100*(c-lo14)/(hi14-lo14+1e-9)).rolling(3).mean(); sd=sk.rolling(3).mean()
            up_=h.diff(); dn_=-l.diff()
            pdm=pd.Series(np.where((up_>dn_)&(up_>0),up_,0.),index=h.index)
            ndm=pd.Series(np.where((dn_>up_)&(dn_>0),dn_,0.),index=l.index)
            pdi=100*pdm.ewm(span=14,adjust=False).mean()/atr.replace(0,1e-9)
            ndi=100*ndm.ewm(span=14,adjust=False).mean()/atr.replace(0,1e-9)
            dx_=100*(pdi-ndi).abs()/(pdi+ndi+1e-9); adx=dx_.ewm(span=14,adjust=False).mean()

            vc=[GRN if c.iloc[i]>=o.iloc[i] else RED for i in range(len(c))]
            hc=[GRN if x>=0 else RED for x in hist.fillna(0)]

            fig = make_subplots(rows=6,cols=1,shared_xaxes=True,
                                row_heights=[0.42,0.11,0.12,0.12,0.12,0.11],
                                vertical_spacing=0.01)

            fig.add_trace(go.Candlestick(x=dt,open=o,high=h,low=l,close=c,name="OHLC",
                increasing_line_color=GRN,increasing_fillcolor=GRN+"28",
                decreasing_line_color=RED,decreasing_fillcolor=RED+"28",line_width=1),row=1,col=1)
            for ser,col,nm,lw in [(e9,AMB,"EMA9",1),(e21,BLU,"EMA21",1.2),(e50,PUR,"EMA50",1.5)]:
                fig.add_trace(go.Scatter(x=dt,y=ser,name=nm,line=dict(color=col,width=lw)),row=1,col=1)
            fig.add_trace(go.Scatter(x=dt,y=bbu,line=dict(color="#546e7a",width=1,dash="dot"),showlegend=False),row=1,col=1)
            fig.add_trace(go.Scatter(x=dt,y=bbl,line=dict(color="#546e7a",width=1,dash="dot"),
                fill="tonexty",fillcolor="rgba(84,110,122,0.06)",showlegend=False),row=1,col=1)
            fig.add_trace(go.Scatter(x=dt,y=vwap_s,name="VWAP",line=dict(color="#e91e63",width=1.5,dash="dash")),row=1,col=1)
            fig.add_trace(go.Scatter(x=dt,y=st_u,line=dict(color=RED,width=1),showlegend=False),row=1,col=1)
            fig.add_trace(go.Scatter(x=dt,y=st_l,line=dict(color=GRN,width=1),showlegend=False),row=1,col=1)

            for sym_,pos in risk_mgr.positions.items():
                if sym_==symbol:
                    for y_,cc,lb in [(pos.entry_price,AMB,f"Entry ₹{pos.entry_price:.2f}"),
                                      (pos.trailing_sl,RED,f"SL ₹{pos.trailing_sl:.2f}"),
                                      (pos.target,GRN,f"TGT ₹{pos.target:.2f}")]:
                        fig.add_hline(y=y_,line_color=cc,line_dash="dot",line_width=1.5,
                                       annotation_text=lb,annotation_font_size=9,
                                       annotation_font_color=cc,row=1,col=1)

            fig.add_trace(go.Bar(x=dt,y=v,marker_color=vc,showlegend=False),row=2,col=1)
            fig.add_trace(go.Scatter(x=dt,y=v.rolling(20).mean(),line=dict(color=AMB,width=1),showlegend=False),row=2,col=1)
            fig.add_trace(go.Scatter(x=dt,y=rsi,line=dict(color=PUR,width=1.5),showlegend=False),row=3,col=1)
            for lvl,cc in [(70,RED),(50,MUT),(30,GRN)]:
                fig.add_hline(y=lvl,line_color=cc,line_dash="dot",line_width=0.6,row=3,col=1)
            fig.add_trace(go.Bar(x=dt,y=hist,marker_color=hc,showlegend=False),row=4,col=1)
            fig.add_trace(go.Scatter(x=dt,y=mac,line=dict(color=BLU,width=1.5),showlegend=False),row=4,col=1)
            fig.add_trace(go.Scatter(x=dt,y=sig_,line=dict(color=AMB,width=1.5),showlegend=False),row=4,col=1)
            fig.add_hline(y=0,line_color=MUT,line_width=0.5,row=4,col=1)
            fig.add_trace(go.Scatter(x=dt,y=sk,line=dict(color=GRN,width=1.5),showlegend=False),row=5,col=1)
            fig.add_trace(go.Scatter(x=dt,y=sd,line=dict(color=AMB,width=1.5),showlegend=False),row=5,col=1)
            for lvl,cc in [(80,RED),(20,GRN)]:
                fig.add_hline(y=lvl,line_color=cc,line_dash="dot",line_width=0.6,row=5,col=1)
            fig.add_trace(go.Scatter(x=dt,y=adx,line=dict(color=AMB,width=1.5),showlegend=False),row=6,col=1)
            fig.add_trace(go.Scatter(x=dt,y=pdi,line=dict(color=GRN,width=1),showlegend=False),row=6,col=1)
            fig.add_trace(go.Scatter(x=dt,y=ndi,line=dict(color=RED,width=1),showlegend=False),row=6,col=1)
            fig.add_hline(y=20,line_color=MUT,line_dash="dot",line_width=0.6,row=6,col=1)

            row_lbls = {1:"Price",2:"Vol",3:"RSI(14)",4:"MACD",5:"Stoch",6:"ADX"}
            for r,lb in row_lbls.items():
                fig.update_yaxes(title_text=lb,title_font=dict(size=8,color=MUT),row=r,col=1)

            fig.update_layout(
                template="plotly_dark", paper_bgcolor=BG, plot_bgcolor="#06101a",
                font=dict(color=TXT,size=9,family=FONT),
                margin=dict(l=52,r=8,t=12,b=8),
                xaxis_rangeslider_visible=False,
                hovermode="x unified",
                legend=dict(bgcolor="rgba(0,0,0,0)",font=dict(size=9),
                            orientation="h",y=1.02,x=0),
                hoverlabel=dict(bgcolor=CARD2,font_size=9,font_family=FONT),
            )
            fig.update_yaxes(gridcolor="#0d1f30",gridwidth=0.5,zeroline=False,tickfont=dict(size=8))
            fig.update_xaxes(gridcolor="#0d1f30",gridwidth=0.5,tickfont=dict(size=8))

            sgn = "+" if chg>=0 else ""
            chg_el = html.Span(f"{sgn}{chg:.2f} ({sgn}{chg_pct:.2f}%)",
                                style={"color":ltp_c,"fontSize":"12px"})
        except Exception as e:
            logger.error(f"Chart {symbol}: {e}", exc_info=True)
            return _empty_fig(f"Render error"), "—", "", kite_url

        return fig, f"₹{ltp:,.2f}", chg_el, kite_url

    # ════════════════════════════════════════════════════════════
    #  CALLBACK 3 — 30s: Indices + news + IPO + ticker
    # ════════════════════════════════════════════════════════════
    @app.callback(
        [Output("idx-grid","children"), Output("ticker-tape","children"),
         Output("ipo-panel","children")],
        Input("t30","n_intervals"),
    )
    def cb_slow(_):
        idx_data = index_tracker.get_all() if index_tracker else {}

        # Index tiles
        idx_names = [
            "NIFTY 50","SENSEX","NIFTY BANK","NIFTY MIDCAP 100","BANKEX",
            "NIFTY IT","NIFTY PHARMA","NIFTY AUTO","NIFTY FMCG","NIFTY METAL",
            "NIFTY ENERGY","NIFTY FIN SERVICE","NIFTY REALTY",
            "NIFTY COMMODITIES","NIFTY CONSUMPTION","NIFTY DIV OPPS 50","INDIA VIX",
        ]
        tiles = []
        for name in idx_names:
            d = idx_data.get(name,{})
            ltp_ = d.get("ltp",0); chg_ = d.get("chg_pct",0)
            col_ = GRN if chg_>=0 else RED; sgn_ = "+"if chg_>=0 else ""
            tiles.append(dbc.Col(html.Div([
                html.Div(name[:13], className="idx-name"),
                html.Div(f"{ltp_:,.1f}" if ltp_ else "—", className="idx-val",
                         style={"color":col_}),
                html.Div(f"{sgn_}{chg_:.2f}%", className="idx-chg", style={"color":col_}),
            ], className="idx-tile"), xs=6,sm=4,md=3,lg=2,xl=1))

        # Ticker tape
        tick = []
        for name,d in idx_data.items():
            ltp_=d.get("ltp",0); chg_=d.get("chg_pct",0)
            col_=GRN if chg_>=0 else RED; sgn_="+"if chg_>=0 else ""
            tick.append(html.Span([
                html.Span(name, style={"color":MUT,"fontSize":"11px"}),
                html.Span(f" {ltp_:,.1f}", style={"color":col_,"fontWeight":"700","fontSize":"11px"}),
                html.Span(f" {sgn_}{chg_:.2f}%", style={"color":col_,"fontSize":"10px"}),
            ], className="t-item"))
        ticker = tick * 3

        # IPO
        ipo_items = []
        try:
            for r in (ipo_analyzer.get_recommendations() if ipo_analyzer else [])[:5]:
                col_=GRN if r["recommendation"]=="APPLY" else(AMB if r["recommendation"]=="WATCH" else RED)
                ipo_items.append(html.Div([
                    html.Span(r["name"][:22],style={"color":CYN,"fontWeight":"700","fontSize":"11px"}),
                    html.Span(f" {r['recommendation']}",style={"color":col_,"fontWeight":"700","fontSize":"10px","marginLeft":"5px"}),
                    html.Div(r["reason"][:55],style={"fontSize":"9px","color":MUT,"marginTop":"1px"}),
                    html.Div(f"Score:{r['score']:.2f} Sub:{r['subscription']:.1f}x GMP:₹{r['gmp']}",
                             style={"fontSize":"9px","color":MUT}),
                ], style={"borderBottom":f"1px solid {BDR}","padding":"4px 0"}))
        except Exception:
            pass
        if not ipo_items:
            ipo_items=[html.Div("IPO data loading...",style={"color":MUT,"fontSize":"10px","padding":"6px 0"})]

        return tiles, ticker, ipo_items

    return app


def start_dashboard(risk_mgr, get_candles_fn, index_tracker, ipo_analyzer,
                    session_obj, bot_controller, config):
    if not _DASH_OK:
        logger.error("Install dash: pip install dash dash-bootstrap-components plotly")
        return
    app = build_app(risk_mgr, get_candles_fn, index_tracker, ipo_analyzer,
                    session_obj, bot_controller, config)
    if not app:
        return

    def run():
        import logging as _l
        _l.getLogger("werkzeug").setLevel(_l.ERROR)
        app.run(host=getattr(config,"DASHBOARD_HOST","127.0.0.1"),
                port=getattr(config,"DASHBOARD_PORT",8050),
                debug=False, use_reloader=False,
                dev_tools_silence_routes_logging=True)

    threading.Thread(target=run, daemon=True, name="Dashboard").start()
    logger.info(f"Dashboard: http://127.0.0.1:{getattr(config,'DASHBOARD_PORT',8050)}")
