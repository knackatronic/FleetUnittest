import ast

FLEET_BUILD = "2026.11.22.4"

import os



FLEET_UPDATE_URL = (

    os.getenv("FLEET_UPDATE_URL")

    or "https://fleetunit-support.fleetunitsupport.workers.dev/version"

).strip()



import os

import sys

import traceback

import subprocess

from datetime import datetime, timezone, time as dtime, timedelta, timezone

import ctypes

from ctypes import wintypes

import re

import webbrowser

import hashlib

from groq_diagnostics import audit_rejected_proposals, run_async_task, synthesize_post_mortems

import smtplib

import urllib.parse

from email.message import EmailMessage

import urllib.error



try:

    from zoneinfo import ZoneInfo

except ImportError:

    ZoneInfo = None



# --- DYNAMIC PATH RESOLUTION ---

if getattr(sys, 'frozen', False):

    # If running as a compiled .exe (e.g., PyInstaller)

    BASE_DIR = os.path.dirname(sys.executable)

else:

    # If running as a .py script

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))



_BOOTSTRAP_LOG_DIR = os.path.join(BASE_DIR, "logs")

DB_FILE = os.path.join(BASE_DIR, "trade_memory.db")

LOG_DIR = _BOOTSTRAP_LOG_DIR

ARCHIVE_LOG_DIR = os.path.join(LOG_DIR, "archive")

# -------------------------------



def _bootstrap_error(msg):

    try:

        os.makedirs(_BOOTSTRAP_LOG_DIR, exist_ok=True)

        with open(os.path.join(_BOOTSTRAP_LOG_DIR, "gui_diag.log"), "a", encoding="utf-8") as f:

            f.write(f"\n[{__import__('datetime').datetime.now()}] [STARTUP] {msg}\n")

    except Exception:

        pass



# Patch 1: Timezone Foundation

try:

    MARKET_TZ = ZoneInfo("America/New_York")

except Exception:

    MARKET_TZ = timezone(timedelta(hours=-5))

    _bootstrap_error("tzdata missing — market scheduling falling back to fixed UTC-5")



def get_est_now():

    """Naive NY time. DST handled automatically. Use for ALL scheduling logic."""

    return datetime.now(MARKET_TZ).replace(tzinfo=None)



def get_user_tz():

    return datetime.now().astimezone().tzinfo



def get_user_tz_abbr():

    return datetime.now().astimezone().strftime("%Z") or "LOCAL"



def market_hm_to_local_str(hour, minute):

    """15, 30 → '12:30 PST' (winter) or '13:30 PDT' (summer) for an LA user."""

    now = datetime.now(MARKET_TZ)

    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    return target.astimezone(get_user_tz()).strftime("%H:%M %Z")



try:

    import customtkinter as ctk

    import tkinter as tk

    import sqlite3

    import threading

    import time

    import math

    from PIL import Image, ImageTk

    import urllib.request

    import json

    import xml.etree.ElementTree as ET

    import requests

except Exception as e:

    _bootstrap_error(traceback.format_exc())

    raise



try:

    from groq_helper import get_groq_api_key as _external_get_groq_key, save_groq_api_key as _external_save_groq_key

except ImportError:

    _external_get_groq_key = None

    _external_save_groq_key = None





def load_persisted_groq_key(db_path=DB_FILE):

    if _external_get_groq_key is not None:

        return _external_get_groq_key(db_path)

    env_key = (os.environ.get("GROQ_API_KEY") or "").strip()

    if env_key:

        return env_key

    if db_path and os.path.exists(db_path):

        try:

            conn = sqlite3.connect(db_path, timeout=5.0)

            row = conn.execute("SELECT value FROM bot_config WHERE key='groq_api_key' LIMIT 1").fetchone()

            conn.close()

            if row and row[0]:

                return str(row[0]).strip()

        except Exception:

            return None

    return None





def persist_groq_key(api_key, db_path=DB_FILE):

    cleaned = (api_key or "").strip()

    if cleaned:

        os.environ["GROQ_API_KEY"] = cleaned

    else:

        os.environ.pop("GROQ_API_KEY", None)

    if _external_save_groq_key is not None:

        return _external_save_groq_key(cleaned, db_path)

    try:

        parent = os.path.dirname(os.path.abspath(db_path))

        if parent:

            os.makedirs(parent, exist_ok=True)

        conn = sqlite3.connect(db_path, timeout=10.0)

        c = conn.cursor()

        c.execute("CREATE TABLE IF NOT EXISTS bot_config (key TEXT PRIMARY KEY, value TEXT);")

        if cleaned:

            c.execute("INSERT OR REPLACE INTO bot_config (key, value) VALUES ('groq_api_key', ?);", (cleaned,))

        else:

            c.execute("DELETE FROM bot_config WHERE key = 'groq_api_key';")

        conn.commit()

        conn.close()

        return True

    except Exception:

        return False



def get_groq_api_key(db_path=DB_FILE):

    return load_persisted_groq_key(db_path)





def save_groq_api_key(api_key, db_path=DB_FILE):

    return persist_groq_key(api_key, db_path)







try:

    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('fleetunit.forex.terminal.v1')

except Exception:

    pass



try:

    import MetaTrader5 as mt5

    MT5_AVAILABLE = True

except ImportError:

    MT5_AVAILABLE = False



ctk.set_appearance_mode("Dark")

ctk.set_default_color_theme("blue")



HISTORY_PAGE_SIZE = 10

LIVE_LOG_MAX_LINES = 400

LIVE_LOG_ARCHIVE_BATCH = 300

ARCHIVE_RETENTION_DAYS = 2



MAX_OPEN_CHARTS = 3

CHART_DEFAULT_TF = "30m"

CHART_REFRESH_MS = 5000



# Chart zoom / pan constants

BASE_VISIBLE_BARS = {

    "1m": 60,

    "5m": 72,

    "15m": 192,

    "30m": 96,

    "1h": 48,

}

# Extended history to 3.5 days at every timeframe

MAX_BARS_FOR_TF = {

    "1m": 5040,

    "5m": 1008,

    "15m": 336,

    "30m": 168,

    "1h": 84,

}

MIN_VISIBLE_BARS = 10

ZOOM_STEP = 1.5

ZOOM_SNAP_FRACTION = 0.20  # snap to min/max when the next step is within 20%



# Rollover defense thresholds (EST)

ROLLOVER_HARVEST_DECAY = 0.60

ROLLOVER_MAX_SWAP_LOSS = -0.25

ROLLOVER_STAGNANT_SECS = 7200



# Worker script names (used for orphan cleanup on startup)

WORKER_SCRIPTS = [

    "macro_calendar_sync.py", "macro_sentinel.py", "spread_sentinel.py",

    "strength_sentinel.py", "risk_engine.py", "trend_guard.py",

    "master_router.py", "confluence_validator.py", "dispatch_orders.py",

    "worker_harmonic_fib.py", "worker_liquidity_sweep.py", "worker_atr_expansion.py",

    "worker_trend_scalper.py", "worker_impulse_scalper.py", "worker_swing_follower.py",

    "worker_range_reversion.py", "worker_news_retest.py", "worker_chart_patterns.py",

    "worker_risk_architect.py", "worker_meta_supervisor.py", "external_telemetry_fetcher.py",

    "worker_trade_memory.py", "worker_recovery_sentinel.py", "worker_composio_bridge.py",

    "worker_wyckoff_phases.py",

]



# Consistent UI wording & labels

UI_LABELS = {

    "app_title": "FleetUnit",

    "connect_idle": "Connect & Scan MT5",

    "connect_busy": "Connecting to MT5",

    "connect_ready": "Connected to MT5",

    "fleet_resume": "▶ Resume Fleet",

    "fleet_pause": "⏸ Pause Fleet",

    "profit_target": "Profit Target ($):",

    "save_btn": "Set",

    "status_disconnected": "🔴 DISCONNECTED",

    "status_paused_manual": "⚪ SYSTEM PAUSED (Manual)",

    "status_news_freeze": "🟠 NEWS FREEZE - PAUSED",

    "status_active": "🟢 SYSTEM ACTIVE",

    "status_ready_query": "Status: Ready to Query Live MT5 Terminal",

    "refresh_history": "Refresh History",

    "fetch_news": "Fetch Live Headlines",

    "archive_clear": "Archive & Clear",

    "open_archive": "Open Archive Folder",

    "test_conn": "Test Connection",

    "clear_key": "Clear Key",

    "send_ai": "Send",

}





def get_resource_path(relative_path):

    try:

        base_path = sys._MEIPASS

    except Exception:

        base_path = BASE_DIR

    return os.path.join(base_path, relative_path)





ICON_FILE = get_resource_path("icon.ico")





def _init_copilot_history_table(db_path=DB_FILE):

    try:

        parent = os.path.dirname(os.path.abspath(db_path))

        if parent:

            os.makedirs(parent, exist_ok=True)

        conn = sqlite3.connect(db_path, timeout=10.0)

        conn.execute(

            """

            CREATE TABLE IF NOT EXISTS copilot_chat_history (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                role TEXT NOT NULL,

                content TEXT NOT NULL,

                created_at TEXT NOT NULL

            );

            """

        )

        conn.commit()

        conn.close()

    except Exception:

        pass





def load_copilot_history(limit=50, db_path=DB_FILE):

    _init_copilot_history_table(db_path)

    try:

        conn = sqlite3.connect(db_path, timeout=10.0)

        rows = conn.execute(

            "SELECT role, content, created_at FROM copilot_chat_history ORDER BY id DESC LIMIT ?;",

            (int(limit),),

        ).fetchall()

        conn.close()

        rows.reverse()

        return [{"role": r[0], "content": r[1], "created_at": r[2]} for r in rows]

    except Exception:

        return []





def append_copilot_history(role, content, db_path=DB_FILE):

    if not content:

        return

    _init_copilot_history_table(db_path)

    try:

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = sqlite3.connect(db_path, timeout=10.0)

        conn.execute(

            "INSERT INTO copilot_chat_history (role, content, created_at) VALUES (?, ?, ?);",

            (str(role), str(content), ts),

        )

        conn.commit()

        conn.close()

    except Exception:

        pass





def clear_copilot_history(db_path=DB_FILE):

    _init_copilot_history_table(db_path)

    try:

        conn = sqlite3.connect(db_path, timeout=10.0)

        conn.execute("DELETE FROM copilot_chat_history;")

        conn.commit()

        conn.close()

        return True

    except Exception:

        return False







def run_readonly_sql(sql, db_path=DB_FILE, max_rows=30):

    """Executes only SELECT/WITH/EXPLAIN queries in read-only mode."""

    cleaned = (sql or "").strip().rstrip(";")

    upper = cleaned.upper()

    forbidden = ("INSERT ", "UPDATE ", "DELETE ", "DROP ", "ALTER ", "CREATE ", "REPLACE ", "ATTACH ", "DETACH ", "VACUUM", "PRAGMA ")

    if not cleaned or any(upper.startswith(f) or f" {f}" in upper for f in forbidden):

        return None, "Blocked non-read-only SQL."

    if not (upper.startswith("SELECT") or upper.startswith("WITH") or upper.startswith("EXPLAIN")):

        return None, "Only SELECT/WITH/EXPLAIN read-only queries are allowed."

    if not db_path or not os.path.exists(db_path):

        return None, "Database not found."

    try:

        uri = f"file:{os.path.abspath(db_path)}?mode=ro"

        conn = sqlite3.connect(uri, uri=True, timeout=10.0)

        cur = conn.cursor()

        cur.execute(cleaned)

        cols = [d[0] for d in cur.description] if cur.description else []

        rows = cur.fetchmany(max_rows)

        conn.close()

        return (cols, rows), None

    except Exception as exc:

        return None, str(exc)





def build_full_system_snapshot(db_path=DB_FILE, base_dir=None, max_chars=9000):

    """Collects a read-only overview of all DB tables, Python fleet files, and recent logs."""

    root_dir = base_dir or os.path.dirname(os.path.abspath(__file__))

    sections = []



    # 1. All SQLite tables & sample/latest rows

    if db_path and os.path.exists(db_path):

        try:

            uri = f"file:{os.path.abspath(db_path)}?mode=ro"

            conn = sqlite3.connect(uri, uri=True, timeout=10.0)

            tables = [

                r[0]

                for r in conn.execute(

                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;"

                ).fetchall()

            ]

            db_lines = [f"SQLite DB ({os.path.basename(db_path)}) tables ({len(tables)}): {', '.join(tables)}"]

            for tbl in tables:

                try:

                    cnt = conn.execute(f'SELECT COUNT(*) FROM "{tbl}";').fetchone()[0]

                    cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{tbl}");').fetchall()]

                    latest = conn.execute(f'SELECT * FROM "{tbl}" ORDER BY rowid DESC LIMIT 3;').fetchall()

                    db_lines.append(f"- {tbl} (rows={cnt}, cols={cols}): latest={latest}")

                except Exception as te:

                    db_lines.append(f"- {tbl}: error reading ({te})")

            conn.close()

            sections.append("\n".join(db_lines))

        except Exception as e:

            sections.append(f"SQLite DB error: {e}")



    # 2. All Python modules in the fleet directory

    try:

        py_files = sorted(f for f in os.listdir(root_dir) if f.endswith(".py"))

        mod_lines = [f"Fleet Python modules ({len(py_files)}):"]

        for fname in py_files:

            fpath = os.path.join(root_dir, fname)

            try:

                with open(fpath, "r", encoding="utf-8-sig", errors="replace") as pf:

                    content = pf.read()

                defs = []

                for ln in content.splitlines():

                    s = ln.strip()

                    if s.startswith("def ") or s.startswith("class "):

                        defs.append(s.split(":")[0][:60])

                preview_defs = ", ".join(defs[:8]) + (" ..." if len(defs) > 8 else "")

                mod_lines.append(f"- {fname} ({len(content.splitlines())} lines): {preview_defs}")

            except Exception as fe:

                mod_lines.append(f"- {fname}: read error ({fe})")

        sections.append("\n".join(mod_lines))

    except Exception as e:

        sections.append(f"Modules scan error: {e}")



    # 3. Recent log tail across logs/*.log

    logs_dir = os.path.join(root_dir, "logs")

    if os.path.isdir(logs_dir):

        try:

            log_files = sorted(f for f in os.listdir(logs_dir) if f.endswith(".log"))

            log_lines = [f"Recent logs ({len(log_files)} files):"]

            for lf in log_files[-8:]:

                lpath = os.path.join(logs_dir, lf)

                try:

                    with open(lpath, "r", encoding="utf-8-sig", errors="replace") as f_log:

                        tail = f_log.readlines()[-4:]

                    joined_tail = " | ".join(x.strip() for x in tail if x.strip())

                    if joined_tail:

                        log_lines.append(f"- {lf}: {joined_tail[:240]}")

                except Exception:

                    pass

            sections.append("\n".join(log_lines))

        except Exception:

            pass



    full_text = "\n\n".join(sections)

    if len(full_text) > max_chars:

        full_text = full_text[:max_chars] + "\n...[truncated for prompt budget]..."

    return full_text







class FleetApp(ctk.CTk):

    def __init__(self):

        super().__init__()

        self._connected = False

        self._fleet_workers = {}



        self.title(UI_LABELS["app_title"])
        try:
            self._build_badge = ctk.CTkLabel(
                self,
                text=f"Build {FLEET_BUILD}",
                font=ctk.CTkFont(size=11),
                text_color=("#6b7280", "#9ca3af"),
            )
            self._build_badge.place(relx=1.0, rely=0.0, x=-14, y=8, anchor="ne")
        except Exception:
            pass

        self.minsize(640, 420)

        self._apply_default_window_geometry()

        self.after(150, self._apply_default_window_geometry)

        self.after(600, self._apply_default_window_geometry)



        if os.path.exists(ICON_FILE):

            try:

                self.wm_iconbitmap(ICON_FILE)

            except Exception:

                pass

            try:

                img_ico = Image.open(ICON_FILE)

                self.icon_photo = ImageTk.PhotoImage(img_ico)

                self.iconphoto(True, self.icon_photo)

            except Exception:

                pass



        self.protocol("WM_DELETE_WINDOW", self._on_close)



        self._setup_win32_api()

        self._restore_mt5_on_startup()



        # FORCE RESET PROFIT TARGET TO 0.00 ON EVERY STARTUP

        try:

            os.makedirs(BASE_DIR, exist_ok=True)

            conn = sqlite3.connect(DB_FILE, timeout=30.0)

            c = conn.cursor()

            c.execute("CREATE TABLE IF NOT EXISTS bot_config (key TEXT PRIMARY KEY, value TEXT);")

            c.execute("INSERT OR REPLACE INTO bot_config (key, value) VALUES ('max_profit_radius', '0.0');")

            c.execute("INSERT OR REPLACE INTO bot_config (key, value) VALUES ('market_phase', 'ACTIVE');")

            conn.commit()

            try:

                c.execute("PRAGMA wal_checkpoint(PASSIVE);")

            except Exception:

                pass

            conn.close()

        except Exception:

            pass



        self.tabview = ctk.CTkTabview(self, width=1280, height=800, command=self.on_tab_changed)

        self.tabview.pack(padx=15, pady=15, fill="both", expand=True)



        self.tab_orders = self.tabview.add("Live Orders & Account")

        self.tab_live = self.tabview.add("Activity & Chat")

        self.tab_ai = self.tabview.add("AI Copilot")

        self.tab_security = self.tabview.add("Trust & Support")

        _support_msg_btn = self._apply_3d_button_feel(

            ctk.CTkButton(

                self.tab_security,

                text="Send a Message",

                width=145,

                height=30,

                fg_color="#2980b9",

                hover_color="#1f618d",

                command=self.open_support_message_window,

            )

        )

        _support_msg_btn.pack(anchor="nw", padx=12, pady=(8, 4))



        self._current_tab = "Live Orders & Account"

        self._current_inner_tab = "Active Orders"



        self._history_deals_cache = []

        self._open_order_chart_modes = {}

        self._watchlist_chart_mode = "candlestick"

        self._history_page = 0

        self._live_log_line_count = 1



        # Subtle animation state

        self._pulse_step = 0

        self._pulse_job = None



        self.setup_orders_tab()

        self.setup_live_tab()

        self.setup_ai_tab()

        self.setup_security_tab()



        self.cached_positions = []

        self.order_ui_rows = {}

        self.history_ui_rows = {}

        self.file_positions = {}

        self.last_mtimes = {}

        self._closing = set()

        self._closed_tickets = set()

        self._expanded_tickets = []

        self._focused_chart_ticket = None  # Tracks which chart has focus for zooming

        self._scanning = False

        self._account_line = UI_LABELS["status_ready_query"]

        self._cached_radius = 0.0

        self._account_balance = 0.0

        self.auto_paused = False

        self.market_phase = "ACTIVE"

        self.news_freeze_active = False



        self.dynamic_slots = 2

        self.manual_lot_size = 0.01

        self.dollar_stop_loss = 0.0

        self._last_persisted_scaling = None



        self._hist_cache = {"daily": 0.0, "daily_ts": 0.0, "total": 0.0, "total_ts": 0.0}



        self.is_running = True



        # FLEET STARTUP POLICY: Always start paused. User must click Resume.

        self.fleet_active = False

        self._persist_fleet_active()



        self._cleanup_old_archived_logs()



        _initial_phase = self._compute_market_phase(get_est_now())

        self.market_phase = _initial_phase

        self._set_market_phase(_initial_phase)

        self.auto_paused = _initial_phase in ("DEAD_ZONE_LOCKDOWN", "WEEKEND_LOCKDOWN", "SPREAD_RECOVERY")

        self.news_freeze_active = False

        self._sync_system_paused()



        # Best-effort kill of orphan workers from a previous crashed session

        threading.Thread(target=self._kill_orphaned_workers, daemon=True).start()



        self.update_system_status_ui()

        self._start_subtle_pulse()



        self.poll_thread = threading.Thread(target=self.background_event_listener, daemon=True)

        self.poll_thread.start()



        self.ticker_thread = threading.Thread(target=self.live_ticker_loop, daemon=True)

        self.ticker_thread.start()



        # Strict chart-focus: capture every click in the app so we can defocus

        # when the click lands outside any expanded chart's bounding box.

        # bind_all is used (instead of bind) because CustomTkinter buttons route

        # their click events through internal canvases that don't reliably bubble

        # up the widget hierarchy the way plain Tk widgets do.

        try:

            self.bind_all("<Button-1>", self._on_global_click, add="+")

        except Exception:

            pass



        self.after(CHART_REFRESH_MS, self._chart_refresh_loop)

        self.after(1500, lambda: self._check_for_gui_update(show_if_current=False))

    def _on_global_click(self, event):

        """Strict chart focus: only the chart you click is focused; clicking

        anywhere outside its bounding box immediately unfocuses it.



        Uses screen-coordinate hit-testing rather than widget-hierarchy walking

        because CustomTkinter widgets expose internal canvases as event.widget,

        which makes `.master` chains unreliable.

        """

        try:

            if not getattr(self, "is_running", False):

                return

            expanded = getattr(self, "_expanded_tickets", None)

            if not expanded:

                return

            if getattr(self, "_current_tab", "") != "Live Orders & Account":

                return

            try:

                x = int(event.x_root)

                y = int(event.y_root)

            except Exception:

                return



            for t in list(expanded):

                rw = self.order_ui_rows.get(t)

                if not rw:

                    continue

                cf = rw.get("chart_frame")

                if not cf:

                    continue

                try:

                    if not cf.winfo_exists() or not cf.winfo_ismapped():

                        continue

                    fx = cf.winfo_rootx()

                    fy = cf.winfo_rooty()

                    fw = cf.winfo_width()

                    fh = cf.winfo_height()

                except Exception:

                    continue



                if fx <= x <= fx + fw and fy <= y <= fy + fh:

                    if self._focused_chart_ticket != t:

                        self._focused_chart_ticket = t

                        self._update_chart_borders()

                    return



            # Click landed outside every expanded chart

            if self._focused_chart_ticket is not None:

                self._focused_chart_ticket = None

                self._update_chart_borders()

        except Exception as e:

            self._log_exc("_on_global_click", e)



    def _apply_3d_button_feel(self, btn, normal_border="#64748b", pressed_border="#cbd5e1", hover_border="#94a3b8"):

        try:

            btn.configure(border_width=2, border_color=normal_border)



            def _on_enter(_event):

                if str(btn.cget("state")) != "disabled":

                    btn.configure(border_color=hover_border)



            def _on_leave(_event):

                btn.configure(border_color=normal_border)



            def _on_press(_event):

                if str(btn.cget("state")) != "disabled":

                    btn.configure(border_color=pressed_border, border_width=1)



            def _on_release(_event):

                if str(btn.cget("state")) != "disabled":

                    btn.configure(border_color=hover_border, border_width=2)



            btn.bind("<Enter>", _on_enter, add="+")

            btn.bind("<Leave>", _on_leave, add="+")

            btn.bind("<ButtonPress-1>", _on_press, add="+")

            btn.bind("<ButtonRelease-1>", _on_release, add="+")

        except Exception:

            pass

        return btn



    def _start_subtle_pulse(self):

        if self._pulse_job is not None:

            try:

                self.after_cancel(self._pulse_job)

            except Exception:

                pass

            self._pulse_job = None



        def _tick():

            if not getattr(self, "is_running", False):

                return

            self._pulse_step = (self._pulse_step + 1) % 4

            dots = ["", " ·", " ··", " ···"][self._pulse_step]

            try:

                if self._scanning and hasattr(self, "connect_btn") and self.connect_btn.winfo_exists():

                    self.connect_btn.configure(text=f"{UI_LABELS['connect_busy']}{dots}")

                elif hasattr(self, "system_status_lbl") and self.system_status_lbl.winfo_exists():

                    base_txt = getattr(self, "_base_status_text", UI_LABELS["status_paused_manual"])

                    if self.fleet_active and not self.auto_paused and not self.news_freeze_active:

                        self.system_status_lbl.configure(text=f"{base_txt}{dots}")

                    else:

                        self.system_status_lbl.configure(text=base_txt)

            except Exception:

                pass

            try:

                self._pulse_job = self.after(550, _tick)

            except Exception:

                pass



        try:

            self._pulse_job = self.after(550, _tick)

        except Exception:

            pass



    def _setup_win32_api(self):

        try:

            user32 = ctypes.windll.user32

            user32.FindWindowW.restype = wintypes.HWND

            user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]

            user32.EnumWindows.restype = wintypes.BOOL

            user32.GetWindowTextW.restype = ctypes.c_int

            user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]

            user32.GetWindowTextLengthW.restype = ctypes.c_int

            user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]

            user32.IsWindowVisible.restype = wintypes.BOOL

            user32.IsWindowVisible.argtypes = [wintypes.HWND]

            user32.ShowWindow.restype = wintypes.BOOL

            user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]

        except Exception as e:

            self._log_exc("_setup_win32_api", e)



    def _restore_mt5_on_startup(self):

        try:

            hwnd = self._find_mt5_window()

            if hwnd:

                if not ctypes.windll.user32.IsWindowVisible(hwnd):

                    ctypes.windll.user32.ShowWindow(hwnd, 9)

                    print("[MT5] Detected hidden MT5 terminal from previous session. Restored.")

        except Exception as e:

            self._log_exc("_restore_mt5_on_startup", e)



    def _chart_refresh_loop(self):

        if not self.is_running:

            return

        # Do the (blocking) MT5 fetch on a background thread so the UI thread

        # never stalls on copy_rates_from_pos. Rendering is dispatched back

        # to the main thread inside _fetch_and_render_charts.

        try:

            if self._expanded_tickets:

                threading.Thread(target=self._fetch_and_render_charts, daemon=True).start()

        except Exception:

            pass

        try:

            self.after(CHART_REFRESH_MS, self._chart_refresh_loop)

        except Exception:

            pass



    def _fetch_and_render_charts(self):

        """Background worker: fetch MT5 rates for every expanded chart, then

        schedule the actual render on the main thread."""

        try:

            if not MT5_AVAILABLE:

                return

            tf_map = {

                "1m": mt5.TIMEFRAME_M1,

                "5m": mt5.TIMEFRAME_M5,

                "15m": mt5.TIMEFRAME_M15,

                "30m": mt5.TIMEFRAME_M30,

                "1h": mt5.TIMEFRAME_H1,

            }

            for t in list(self._expanded_tickets):

                if not self.is_running:

                    return

                rw = self.order_ui_rows.get(t)

                if not rw:

                    continue

                symbol = rw.get("symbol_text", "")

                if not symbol:

                    continue

                tf_at_fetch = rw.get("timeframe", CHART_DEFAULT_TF)

                zoom = rw.get("chart_zoom", 1.0)

                _, max_bars = self._get_chart_bars(tf_at_fetch, zoom)

                mt5_tf = tf_map.get(tf_at_fetch, mt5.TIMEFRAME_M30)

                try:

                    rates_all = mt5.copy_rates_from_pos(symbol, mt5_tf, 0, max_bars)

                except Exception:

                    rates_all = None

                self._ui(self._draw_candle_chart_with_cache, t, rates_all, tf_at_fetch)

        except Exception as e:

            self._log_exc("_fetch_and_render_charts", e)



    def _draw_candle_chart_with_cache(self, ticket, rates_all, expected_tf):

        """Main-thread entrypoint for background-fetched chart data.

        Discards the payload if the chart closed or its timeframe changed

        while the fetch was in flight."""

        rw = self.order_ui_rows.get(ticket)

        if not rw:

            return

        if ticket not in self._expanded_tickets:

            return

        if rw.get("timeframe") != expected_tf:

            return

        self._draw_candle_chart(ticket, rates_all)



    def _set_system_paused(self, value):

        try:

            conn = sqlite3.connect(DB_FILE, timeout=30.0)

            c = conn.cursor()

            c.execute("CREATE TABLE IF NOT EXISTS bot_config (key TEXT PRIMARY KEY, value TEXT);")

            c.execute("INSERT OR REPLACE INTO bot_config (key, value) VALUES ('system_paused', ?);", (str(value),))

            conn.commit()

            try:

                c.execute("PRAGMA wal_checkpoint(PASSIVE);")

            except Exception:

                pass

            conn.close()

        except Exception as e:

            self._log_exc("_set_system_paused", e)



    def _set_market_phase(self, phase):

        try:

            conn = sqlite3.connect(DB_FILE, timeout=30.0)

            c = conn.cursor()

            c.execute("CREATE TABLE IF NOT EXISTS bot_config (key TEXT PRIMARY KEY, value TEXT);")

            c.execute("INSERT OR REPLACE INTO bot_config (key, value) VALUES ('market_phase', ?);", (str(phase),))

            conn.commit()

            try:

                c.execute("PRAGMA wal_checkpoint(PASSIVE);")

            except Exception:

                pass

            conn.close()

        except Exception as e:

            self._log_exc("_set_market_phase", e)



    def _persist_fleet_active(self):

        try:

            conn = sqlite3.connect(DB_FILE, timeout=30.0)

            c = conn.cursor()

            c.execute("CREATE TABLE IF NOT EXISTS bot_config (key TEXT PRIMARY KEY, value TEXT);")

            c.execute(

                "INSERT OR REPLACE INTO bot_config (key, value) VALUES ('fleet_active', ?);",

                ("1" if self.fleet_active else "0",),

            )

            conn.commit()

            try:

                c.execute("PRAGMA wal_checkpoint(PASSIVE);")

            except Exception:

                pass

            conn.close()

        except Exception as e:

            self._log_exc("_persist_fleet_active", e)



    def _sync_system_paused(self):

        """Single source of truth: system_paused=1 iff fleet is off OR auto-paused OR news freeze."""

        should_pause = (not self.fleet_active) or self.auto_paused or self.news_freeze_active

        new_val = 1 if should_pause else 0

        if getattr(self, "_last_system_paused", None) == new_val:

            return

        self._set_system_paused(new_val)

        self._last_system_paused = new_val



    def _kill_orphaned_workers(self):

        """Best-effort kill of any worker processes left over from a previous session."""

        names_pattern = "|".join(re.escape(n) for n in WORKER_SCRIPTS)

        own_pid = os.getpid()

        ps_cmd = (

            "Get-CimInstance Win32_Process | "

            f"Where-Object {{ $_.CommandLine -match '{names_pattern}' -and $_.ProcessId -ne {own_pid} }} | "

            "Select-Object -ExpandProperty ProcessId"

        )

        try:

            r = subprocess.run(

                ["powershell", "-NoProfile", "-Command", ps_cmd],

                capture_output=True, text=True, timeout=15,

                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),

            )

            pids = [p.strip() for p in r.stdout.splitlines() if p.strip().isdigit()]

            for pid in pids:

                try:

                    subprocess.run(

                        ["taskkill", "/PID", pid, "/F"],

                        capture_output=True, timeout=5,

                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),

                    )

                except Exception:

                    pass

            if pids:

                print(f"[ORPHAN] Cleaned up {len(pids)} orphaned worker processes")

        except Exception as e:

            self._log_exc("_kill_orphaned_workers", e)



    def _compute_market_phase(self, now):

        wd = now.weekday()

        mins = now.hour * 60 + now.minute



        if wd == 4 and mins >= (16 * 60 + 45):

            return "WEEKEND_LOCKDOWN"

        if wd == 5:

            return "WEEKEND_LOCKDOWN"

        if wd == 6 and mins < (18 * 60):

            return "WEEKEND_LOCKDOWN"



        if wd < 5:

            if (15 * 60 + 30) <= mins < (16 * 60 + 15):

                return "ENTRY_CURFEW"

            if (16 * 60 + 15) <= mins < (16 * 60 + 40):

                return "HARVEST_MODE"

            if (16 * 60 + 40) <= mins < (16 * 60 + 55):

                return "TRIAGE_WINDOW"

            if (16 * 60 + 55) <= mins < (17 * 60 + 30):

                return "DEAD_ZONE_LOCKDOWN"

            if (17 * 60 + 30) <= mins < (18 * 60):

                return "SPREAD_RECOVERY"



        return "ACTIVE"



    def _estimate_overnight_swap_cost(self, pos):

        if not MT5_AVAILABLE:

            return 0.0

        try:

            info = mt5.symbol_info(pos.symbol)

            if not info:

                return 0.0

            swap_pts = info.swap_long if pos.type == 0 else info.swap_short

            tick_size = info.trade_tick_size or info.point or 0.0001

            tick_value = info.trade_tick_value or 1.0

            per_lot_per_day = (swap_pts / tick_size) * tick_value

            now_est = get_est_now()

            multiplier = 3.0 if now_est.weekday() == 2 else 1.0

            return float(per_lot_per_day * pos.volume * multiplier)

        except Exception:

            return 0.0



    def _should_triage_close(self, pos):

        now_ts = int(time.time())

        elapsed_secs = max(0, now_ts - int(pos.time))

        profit = float(pos.profit)

        swap_cost = self._estimate_overnight_swap_cost(pos)



        swap_limit = ROLLOVER_MAX_SWAP_LOSS

        if self._cached_radius > 0:

            swap_limit = min(swap_limit, -0.25 * self._cached_radius)

        if swap_cost < swap_limit and profit < max(0.25, self._cached_radius * 0.75):

            return True, f"SwapRisk({swap_cost:.2f})"



        if elapsed_secs >= ROLLOVER_STAGNANT_SECS and -1.50 <= profit <= 0.15:

            return True, f"Stagnant({profit:.2f})"



        return False, ""



    def update_connect_button_ui(self):

        try:

            if self._scanning:

                self._ui(self.connect_btn.configure, text=UI_LABELS["connect_busy"], fg_color="#2563eb", hover_color="#1d4ed8")

            elif self._connected:

                self._ui(self.connect_btn.configure, text=UI_LABELS["connect_ready"], fg_color="#16a085", hover_color="#138d75")

            else:

                self._ui(self.connect_btn.configure, text=UI_LABELS["connect_idle"], fg_color="#27ae60", hover_color="#219653")

        except Exception as e:

            self._log_exc("update_connect_button_ui", e)



    def update_system_status_ui(self):

        try:

            if not self._connected:

                self._base_status_text = UI_LABELS["status_disconnected"]

                self._ui(self.system_status_lbl.configure, text=self._base_status_text, text_color="#e74c3c")

                self._ui(self.control_switch_btn.configure, text=UI_LABELS["fleet_resume"], fg_color="#7f8c8d", hover_color="#5d6d7e", state="disabled")

            elif self.auto_paused:

                phase_labels = {

                    "WEEKEND_LOCKDOWN": ("🔴 WEEKEND LOCKDOWN", "#e74c3c", "⏸ Weekend Pause"),

                    "DEAD_ZONE_LOCKDOWN": ("🔴 ROLLOVER DEAD-ZONE SHIELD", "#e74c3c", "⏸ Dead-Zone Pause"),

                    "SPREAD_RECOVERY": (f"🟠 SPREAD RECOVERY ({market_hm_to_local_str(17, 30)}-{market_hm_to_local_str(18, 0)})", "#f39c12", "⏸ Spread Check"),

                }

                lbl_txt, lbl_col, btn_txt = phase_labels.get(self.market_phase, ("🔴 AUTO-PAUSED", "#e74c3c", "⏸ Auto-Paused"))

                self._base_status_text = lbl_txt

                self._ui(self.system_status_lbl.configure, text=lbl_txt, text_color=lbl_col)

                self._ui(self.control_switch_btn.configure, text=btn_txt, fg_color="#7f8c8d", hover_color="#5d6d7e", state="disabled")

            elif self.news_freeze_active:

                self._base_status_text = UI_LABELS["status_news_freeze"]

                self._ui(self.system_status_lbl.configure, text=self._base_status_text, text_color="#f1c40f")

                self._ui(self.control_switch_btn.configure, text="⏸ News Pause", fg_color="#7f8c8d", state="disabled")

            elif self.fleet_active:

                if self.market_phase == "ENTRY_CURFEW":

                    s, e = market_hm_to_local_str(15, 30), market_hm_to_local_str(16, 15)

                    txt, col = f"🟡 ACTIVE (Entry Curfew {s}–{e})", "#f1c40f"

                elif self.market_phase == "HARVEST_MODE":

                    s, e = market_hm_to_local_str(16, 15), market_hm_to_local_str(16, 40)

                    txt, col = f"🟠 ACTIVE (Harvest Decay {s}–{e})", "#e67e22"

                elif self.market_phase == "TRIAGE_WINDOW":

                    s, e = market_hm_to_local_str(16, 40), market_hm_to_local_str(16, 55)

                    txt, col = f"🟠 ACTIVE (Rollover Triage {s}–{e})", "#e67e22"

                else:

                    txt, col = UI_LABELS["status_active"], "#2ecc71"

                self._base_status_text = txt

                self._ui(self.system_status_lbl.configure, text=txt, text_color=col)

                self._ui(self.control_switch_btn.configure, text=UI_LABELS["fleet_pause"], fg_color="#c0392b", hover_color="#962d22", state="normal")

            else:

                self._base_status_text = UI_LABELS["status_paused_manual"]

                self._ui(self.system_status_lbl.configure, text=self._base_status_text, text_color="#bdc3c7")

                self._ui(self.control_switch_btn.configure, text=UI_LABELS["fleet_resume"], fg_color="#e67e22", hover_color="#d35400", state="normal")

        except Exception as e:

            self._log_exc("update_system_status_ui", e)



    def _update_rollover_timer(self):

        try:

            now = get_est_now()

            phase = self._compute_market_phase(now)

            target = None

            prefix = "Resuming in"



            if phase == "WEEKEND_LOCKDOWN":

                days_to_add = (6 - now.weekday()) % 7

                target = now.replace(hour=18, minute=0, second=0, microsecond=0) + timedelta(days=days_to_add)

                if now.weekday() == 6 and now.hour < 18:

                    target = now.replace(hour=18, minute=0, second=0, microsecond=0)

            elif phase in ("DEAD_ZONE_LOCKDOWN", "SPREAD_RECOVERY"):

                target = now.replace(hour=18, minute=0, second=0, microsecond=0)

            elif phase == "ENTRY_CURFEW":

                target = now.replace(hour=16, minute=15, second=0, microsecond=0)

                prefix = "Harvest mode in"

            elif phase == "HARVEST_MODE":

                target = now.replace(hour=16, minute=40, second=0, microsecond=0)

                prefix = "Triage window in"

            elif phase == "TRIAGE_WINDOW":

                target = now.replace(hour=16, minute=55, second=0, microsecond=0)

                prefix = "Dead-zone shield in"



            if target:

                delta = target - now

                if delta.total_seconds() > 0:

                    hrs, rem = divmod(int(delta.total_seconds()), 3600)

                    mins, secs = divmod(rem, 60)

                    self._safe_configure(self.rollover_timer_lbl, text=f"{prefix}: {hrs}h {mins}m {secs}s ({get_user_tz_abbr()})", text_color="#f1c40f")

                else:

                    self._safe_configure(self.rollover_timer_lbl, text="")

            else:

                self._safe_configure(self.rollover_timer_lbl, text="")

        except Exception as e:

            self._log_exc("_update_rollover_timer", e)



    def check_market_schedule(self):

        try:

            now = get_est_now()

            phase = self._compute_market_phase(now)

            prev_phase = self.market_phase

            self.market_phase = phase

            self._set_market_phase(phase)



            if prev_phase != phase:

                self.append_log_scroll_safe(f"[{datetime.now().strftime('%H:%M:%S')} {get_user_tz_abbr()}] [ROLLOVER] Phase -> {phase}\n")



            if phase == "TRIAGE_WINDOW" and self.fleet_active and self.cached_positions:

                for p in list(self.cached_positions):

                    if p.ticket not in self._closing:

                        should_close, reason = self._should_triage_close(p)

                        if should_close:

                            self._closing.add(p.ticket)

                            self.append_log_scroll_safe(

                                f"[{datetime.now().strftime('%H:%M:%S')} {get_user_tz_abbr()}] [TRIAGE] Closing #{p.ticket} ({p.symbol}) before rollover: {reason}\n"

                            )

                            self.close_order_action(p.ticket, comment=f"Triage {reason}"[:18])



            should_pause = phase in ("DEAD_ZONE_LOCKDOWN", "WEEKEND_LOCKDOWN", "SPREAD_RECOVERY")



            if should_pause:

                if not self.auto_paused:

                    self.auto_paused = True

                    self._sync_system_paused()

                    self.append_log_scroll_safe(

                        f"[{datetime.now().strftime('%H:%M:%S')} {get_user_tz_abbr()}] [SCHEDULER] {phase} ACTIVE. New entries halted; normal closes shielded from wide spreads.\n"

                    )

                self.update_system_status_ui()

            else:

                if self.auto_paused:

                    self.auto_paused = False

                    self._sync_system_paused()



                    if self.fleet_active and not self._fleet_workers:

                        self._launch_fleet_workers()

                        self.append_log_scroll_safe(

                            f"[{datetime.now().strftime('%H:%M:%S')} {get_user_tz_abbr()}] "

                            f"[FLEET] Workers were missing after resume; relaunched.\n"

                        )



                    self.append_log_scroll_safe(

                        f"[{datetime.now().strftime('%H:%M:%S')} {get_user_tz_abbr()}] [SCHEDULER] Rollover/Weekend window ended ({phase}). Normal operations restored.\n"

                    )

                self.update_system_status_ui()

        except Exception as e:

            self._log_exc("check_market_schedule", e)



    def check_news_freeze(self):

        try:

            if not os.path.exists(DB_FILE):

                return

            conn = sqlite3.connect(DB_FILE, timeout=5.0)

            c = conn.cursor()

            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='system_state';")

            if c.fetchone():

                row = c.execute("SELECT value FROM system_state WHERE key='news_freeze'").fetchone()

                is_freeze = bool(row and str(row[0]).lower() in ("true", "1"))

                log_path = os.path.join(LOG_DIR, "macro_sentinel.log")

                log_says_false = False

                if os.path.exists(log_path):

                    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:

                        lines = f.readlines()

                        for line in lines[-5:]:

                            if "News Freeze: False" in line:

                                log_says_false = True

                if is_freeze and log_says_false:

                    c.execute("INSERT OR REPLACE INTO system_state (key, value) VALUES ('news_freeze', 'false')")

                    conn.commit()

                    is_freeze = False

                if is_freeze != self.news_freeze_active:

                    self.news_freeze_active = is_freeze

                    self._sync_system_paused()

                    self.update_system_status_ui()

            conn.close()

        except Exception:

            pass



    def on_tab_changed(self):

        try:

            self._current_tab = self.tabview.get()

            if self._current_tab == "Live Orders & Account":

                if self._current_inner_tab == "Order History":

                    self.update_order_history()

        except Exception:

            pass



    def on_inner_tab_changed(self):

        try:

            self._current_inner_tab = self.orders_inner_tabs.get()

            if self._current_inner_tab == "Order History":

                self.update_order_history()

        except Exception:

            pass



    def _ui(self, fn, *args, **kwargs):

        try:

            self.after(0, lambda: fn(*args, **kwargs))

        except Exception:

            pass



    def _safe_configure(self, widget, **kwargs):

        try:

            if widget.winfo_exists():

                widget.configure(**kwargs)

        except Exception:

            pass



    def _log_exc(self, where, exc):

        try:

            os.makedirs(LOG_DIR, exist_ok=True)

            with open(os.path.join(LOG_DIR, "gui_diag.log"), "a", encoding="utf-8") as f:

                f.write(f"\n[{datetime.now()}] [RUNTIME] {where}: {type(exc).__name__}: {exc}\n")

        except Exception:

            pass



    def _find_mt5_window(self):

        try:

            user32 = ctypes.windll.user32

            hwnd = user32.FindWindowW("MetaQuotes::MetaTrader::5.00", None)

            if hwnd:

                return hwnd



            hwnds = []

            EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)



            def foreach_window(hwnd_enum, lParam):

                length = user32.GetWindowTextLengthW(hwnd_enum)

                if length > 0:

                    buff = ctypes.create_unicode_buffer(length + 1)

                    user32.GetWindowTextW(hwnd_enum, buff, length + 1)

                    title = buff.value.lower()

                    if "metatrader 5" in title or "metatrader5" in title:

                        hwnds.append(hwnd_enum)

                        return False

                return True



            user32.EnumWindows(EnumWindowsProc(foreach_window), 0)

            return hwnds[0] if hwnds else None

        except Exception as e:

            self._log_exc("_find_mt5_window", e)

            return None



    def toggle_mt5_visibility(self):

        if not MT5_AVAILABLE:

            self.append_log_scroll_safe(f"[{datetime.now().strftime('%H:%M:%S')} {get_user_tz_abbr()}] [MT5] MT5 module not available.\n")

            return

        hwnd = self._find_mt5_window()

        if hwnd:

            user32 = ctypes.windll.user32

            is_visible = user32.IsWindowVisible(hwnd)

            if is_visible:

                user32.ShowWindow(hwnd, 0)

                self.hide_mt5_btn.configure(text="Show MT5")

                self.append_log_scroll_safe(f"[{datetime.now().strftime('%H:%M:%S')} {get_user_tz_abbr()}] [MT5] Terminal window hidden.\n")

            else:

                user32.ShowWindow(hwnd, 9)

                self.hide_mt5_btn.configure(text="Hide MT5")

                self.append_log_scroll_safe(f"[{datetime.now().strftime('%H:%M:%S')} {get_user_tz_abbr()}] [MT5] Terminal window restored.\n")

        else:

            self.append_log_scroll_safe(f"[{datetime.now().strftime('%H:%M:%S')} {get_user_tz_abbr()}] [MT5] Terminal window not found. Is it running as Administrator?\n")



    def _update_mt5_button_state(self):

        if not hasattr(self, "hide_mt5_btn") or not self.hide_mt5_btn.winfo_exists():

            return

        hwnd = self._find_mt5_window()

        if hwnd:

            is_visible = ctypes.windll.user32.IsWindowVisible(hwnd)

            new_text = "Hide MT5" if is_visible else "Show MT5"

            if self.hide_mt5_btn.cget("text") != new_text:

                self.hide_mt5_btn.configure(text=new_text)

        else:

            if self.hide_mt5_btn.cget("text") != "Hide MT5":

                self.hide_mt5_btn.configure(text="Hide MT5")



    def _on_close(self):

        self.is_running = False

        if self._pulse_job is not None:

            try:

                self.after_cancel(self._pulse_job)

            except Exception:

                pass

        self._stop_fleet_workers()



        self.fleet_active = False

        self._persist_fleet_active()

        self._sync_system_paused()



        try:

            conn = sqlite3.connect(DB_FILE, timeout=30.0)

            c = conn.cursor()

            c.execute("CREATE TABLE IF NOT EXISTS bot_config (key TEXT PRIMARY KEY, value TEXT);")

            c.execute("INSERT OR REPLACE INTO bot_config (key, value) VALUES ('max_profit_radius', '0.0');")

            c.execute("INSERT OR REPLACE INTO bot_config (key, value) VALUES ('market_phase', 'ACTIVE');")

            conn.commit()

            try:

                c.execute("PRAGMA wal_checkpoint(PASSIVE);")

            except Exception:

                pass

            conn.close()

        except Exception:

            pass



        try:

            if MT5_AVAILABLE:

                hwnd = self._find_mt5_window()

                if hwnd:

                    ctypes.windll.user32.ShowWindow(hwnd, 9)

                mt5.shutdown()

        except Exception:

            pass

        self.destroy()



    def _launch_fleet_workers(self):

        if self._fleet_workers:

            return

        python_exe = sys.executable

        workers_dir = sys._MEIPASS if getattr(sys, "frozen", False) else BASE_DIR

        launched = 0

        for worker in WORKER_SCRIPTS:

            worker_path = os.path.join(workers_dir, worker)

            if not os.path.exists(worker_path):

                continue

            try:

                log_path = os.path.join(LOG_DIR, worker.replace(".py", ".log"))

                os.makedirs(LOG_DIR, exist_ok=True)

                log_file = open(log_path, "a", encoding="utf-8")

                p = subprocess.Popen([python_exe, worker_path], stdout=log_file, stderr=subprocess.STDOUT, cwd=BASE_DIR)

                self._fleet_workers[worker] = (p, log_file)

                launched += 1

            except Exception as e:

                self._log_exc(f"launch_{worker}", e)

        self.append_log_scroll_safe(f"[FLEET] Launched {launched}/{len(WORKER_SCRIPTS)} workers\n")



    def _stop_fleet_workers(self):

        if not self._fleet_workers:

            return

        stopped = 0

        for worker, (p, log_file) in list(self._fleet_workers.items()):

            try:

                p.terminate()

                try:

                    p.wait(timeout=3)

                except Exception:

                    p.kill()

                stopped += 1

            except Exception:

                pass

            try:

                log_file.close()

            except Exception:

                pass

        self._fleet_workers.clear()

        self.append_log_scroll_safe(f"[FLEET] Stopped {stopped} workers\n")



    def _compute_dynamic_scaling(self, balance):

        if balance >= 260.0 or (self.dynamic_slots == 4 and balance >= 240.0):

            return 4, 0.02

        elif balance >= 160.0 or (self.dynamic_slots == 3 and balance >= 140.0):

            return 3, 0.01

        else:

            return 2, 0.01



    def _persist_manual_controls(self, where="persist_manual_controls"):

        try:

            conn = sqlite3.connect(DB_FILE, timeout=15.0)

            c = conn.cursor()

            c.execute("CREATE TABLE IF NOT EXISTS bot_config (key TEXT PRIMARY KEY, value TEXT);")

            c.execute("INSERT OR REPLACE INTO bot_config (key, value) VALUES ('manual_lot_size', ?);", (str(self.manual_lot_size),))

            c.execute("INSERT OR REPLACE INTO bot_config (key, value) VALUES ('dollar_stop_loss', ?);", (str(self.dollar_stop_loss),))

            conn.commit()

            try:

                c.execute("PRAGMA wal_checkpoint(PASSIVE);")

            except Exception:

                pass

            conn.close()

        except Exception as e:

            self._log_exc(where, e)



    def _read_lot_size_input(self):

        if hasattr(self, "lot_size_entry") and self.lot_size_entry.winfo_exists():

            raw = self.lot_size_entry.get().strip()

        else:

            raw = str(getattr(self, "manual_lot_size", 0.01))

        if not raw:

            return None

        val = float(raw)

        if math.isnan(val) or math.isinf(val):

            return None

        return round(val, 4)



    def _read_dollar_sl_input(self):

        if hasattr(self, "dollar_sl_entry") and self.dollar_sl_entry.winfo_exists():

            raw = self.dollar_sl_entry.get().strip()

        else:

            raw = str(getattr(self, "dollar_stop_loss", 0.0))

        if raw == "":

            return 0.0

        val = float(raw)

        if math.isnan(val) or math.isinf(val):

            return None

        return round(val, 2)



    def save_manual_risk_settings(self, persist=True):

        try:

            lot_val = self._read_lot_size_input()

            if lot_val is None or lot_val <= 0:

                self._append_ai_chat("?? Lot Size must be greater than 0 (e.g. 0.01) before starting or resuming the fleet.\n\n")

                return False

            sl_val = self._read_dollar_sl_input()

            if sl_val is None:

                self._append_ai_chat("?? Dollar Stop Loss must be a valid number (use 0 for none, or e.g. -1.0 for -$1.00).\n\n")

                return False

            self.manual_lot_size = lot_val

            self.dollar_stop_loss = sl_val

            if persist:

                self._persist_manual_controls("save_manual_risk_settings")

            return True

        except Exception:

            self._append_ai_chat("?? Invalid Lot Size or Dollar Stop Loss entry.\n\n")

            return False



    def _enforce_dollar_stop_loss(self, positions):

        try:

            limit_val = float(getattr(self, "dollar_stop_loss", 0.0))

        except Exception:

            return

        if limit_val == 0.0 or not positions:

            return

        threshold = -abs(limit_val)

        for pos in list(positions):

            try:

                profit_val = float(getattr(pos, "profit", 0.0))

                if profit_val <= threshold:

                    ticket = getattr(pos, "ticket", None)

                    if ticket is not None:

                        self.close_order_action(ticket, comment="DollarSL Close")

            except Exception as e:

                self._log_exc("_enforce_dollar_stop_loss", e)



    def _persist_dynamic_scaling(self, where):

        current_state = (self.dynamic_slots, self.manual_lot_size, self.dollar_stop_loss)

        if self._last_persisted_scaling == current_state:

            return

        try:

            conn = sqlite3.connect(DB_FILE, timeout=15.0)

            c = conn.cursor()

            c.execute("CREATE TABLE IF NOT EXISTS bot_config (key TEXT PRIMARY KEY, value TEXT);")

            c.execute("INSERT OR REPLACE INTO bot_config (key, value) VALUES ('dynamic_slots', ?);", (str(self.dynamic_slots),))

            c.execute("INSERT OR REPLACE INTO bot_config (key, value) VALUES ('manual_lot_size', ?);", (str(self.manual_lot_size),))

            c.execute("INSERT OR REPLACE INTO bot_config (key, value) VALUES ('dollar_stop_loss', ?);", (str(self.dollar_stop_loss),))

            conn.commit()

            try:

                c.execute("PRAGMA wal_checkpoint(PASSIVE);")

            except Exception:

                pass

            conn.close()

            self._last_persisted_scaling = current_state

        except Exception as e:

            self._log_exc(where, e)



    def _order_send_with_fill_retry(self, req, sym):

        if not MT5_AVAILABLE:

            return None

        info = mt5.symbol_info(sym)

        flags = info.filling_mode if info else 0

        candidates = []

        if flags & 1:

            candidates.append(mt5.ORDER_FILLING_FOK)

        if flags & 2:

            candidates.append(mt5.ORDER_FILLING_IOC)

        if mt5.ORDER_FILLING_RETURN not in candidates:

            candidates.append(mt5.ORDER_FILLING_RETURN)

        last_res = None

        for mode in candidates:

            req["type_filling"] = mode

            res = mt5.order_send(req)

            last_res = res

            if res is not None and res.retcode != 10030:

                return res

        return last_res



    def _server_to_local_dt(self, symbol, server_epoch):

        try:

            tick = mt5.symbol_info_tick(symbol)

            if tick and tick.bid > 0:

                self._server_offset_cache = int(tick.time - time.time())

        except Exception:

            pass

        offset = getattr(self, "_server_offset_cache", 0)

        return datetime.fromtimestamp(server_epoch - offset, tz=timezone.utc).astimezone(get_user_tz())



    def _market_day_start_utc(self):

        now_market = datetime.now(MARKET_TZ)

        start_market = now_market.replace(hour=0, minute=0, second=0, microsecond=0)

        return start_market.astimezone(timezone.utc).replace(tzinfo=None)



    def setup_orders_tab(self):

        self.orders_inner_tabs = ctk.CTkTabview(self.tab_orders, command=self.on_inner_tab_changed)

        self.orders_inner_tabs.pack(fill="both", expand=True, padx=0, pady=0)



        _ai_wl_bar = ctk.CTkFrame(self.tab_orders, fg_color="transparent")

        _ai_wl_bar.pack(fill="x", padx=10, pady=(4, 2))

        self.ai_watchlist_btn = self._apply_3d_button_feel(

            ctk.CTkButton(

                _ai_wl_bar,

                text="AI Watchlist",

                width=140,

                height=28,

                fg_color="#1f618d",

                hover_color="#154360",

                command=self.open_ai_watchlist_window,

            )

        )

        self.ai_watchlist_btn.pack(side="right", padx=5)

        self.tab_active = self.orders_inner_tabs.add("Active Orders")

        self.tab_history = self.orders_inner_tabs.add("Order History")



        self.help_btn = self._apply_3d_button_feel(

            ctk.CTkButton(

                self.tab_orders, text="❓", width=26, height=26,

                font=ctk.CTkFont(size=12, weight="bold"),

                fg_color="#34495e", hover_color="#2c3e50",

                command=self.open_help_modal

            ),

            normal_border="#64748b", pressed_border="#e2e8f0"

        )

        self.help_btn.place(x=10, y=10)

        self.help_btn.lift()



        self.mt5_frame = ctk.CTkFrame(self.tab_active, fg_color="transparent")

        self.mt5_frame.pack(fill="x", padx=15, pady=(0, 0))



        self.mt5_frame.grid_columnconfigure(0, weight=1)

        self.mt5_frame.grid_columnconfigure(2, weight=1)



        btn_row = ctk.CTkFrame(self.mt5_frame, fg_color="transparent")

        btn_row.grid(row=0, column=0, sticky="w")



        self.connect_btn = self._apply_3d_button_feel(

            ctk.CTkButton(

                btn_row, text=UI_LABELS["connect_idle"], width=185, height=32,

                fg_color="#27ae60", hover_color="#219653", command=self.connect_mt5

            ),

            normal_border="#6ee7b7", pressed_border="#ecfdf5"

        )

        self.connect_btn.pack(side="left")



        right_col = ctk.CTkFrame(self.mt5_frame, fg_color="transparent")

        right_col.grid(row=0, column=2, sticky="ne")



        self.rollover_timer_lbl = ctk.CTkLabel(right_col, text="", font=ctk.CTkFont(family="Consolas", size=12, weight="bold"), text_color="#f1c40f")

        self.rollover_timer_lbl.pack(anchor="e", pady=0)



        self.fleet_brand_frame = ctk.CTkFrame(

            self.mt5_frame,

            fg_color="transparent",

            height=88,

        )

        self.fleet_brand_frame.place(relx=0.5, y=42, anchor="n")

        self.fleet_brand_frame.lift()



        self.fleet_banner = ctk.CTkLabel(

            self.fleet_brand_frame,

            text="F L E E T   U N I T",

            font=ctk.CTkFont(family="Consolas", size=30, weight="bold"),

            text_color="#39ff14",

            fg_color="transparent",

            height=48,

        )

        self.fleet_banner.pack()



        self.system_status_lbl = ctk.CTkLabel(

            self.fleet_brand_frame,

            text=UI_LABELS["status_paused_manual"],

            font=ctk.CTkFont(size=10, weight="bold"),

            text_color="#bdc3c7",

            fg_color="transparent",

            height=20,

        )

        self.system_status_lbl.pack()



        self.daily_profit_label = ctk.CTkLabel(right_col, text="Daily P/L: $0.00", font=ctk.CTkFont(family="Consolas", size=12, weight="bold"), text_color="#2ecc71")

        self.daily_profit_label.pack(anchor="e", pady=0)



        self.total_profit_summary_label = ctk.CTkLabel(right_col, text="Open Profits: $0.00", font=ctk.CTkFont(family="Consolas", size=12, weight="bold"), text_color="#2ecc71")

        self.total_profit_summary_label.pack(anchor="e", pady=0)



        self.control_switch_btn = self._apply_3d_button_feel(

            ctk.CTkButton(

                self.mt5_frame, text=UI_LABELS["fleet_resume"], width=245, height=38,

                font=ctk.CTkFont(size=13, weight="bold"),

                fg_color="#7f8c8d", hover_color="#5d6d7e", state="disabled",

                command=self.toggle_fleet_state

            ),

            normal_border="#94a3b8", pressed_border="#f8fafc"

        )

        self.control_switch_btn.place(relx=0.5, y=0, anchor="n")



        lot_top_row = ctk.CTkFrame(self.mt5_frame, fg_color="transparent")

        lot_top_row.grid(row=1, column=0, sticky="w", pady=(6, 0))



        self.lot_size_lbl = ctk.CTkLabel(lot_top_row, text="Lot Size:", font=ctk.CTkFont(size=12, weight="bold"), text_color="#3498db")

        self.lot_size_lbl.pack(side="left", padx=(0, 4))



        self.lot_size_entry = ctk.CTkEntry(lot_top_row, width=62, height=28, font=ctk.CTkFont(family="Consolas", size=12), state="normal")

        self.lot_size_entry.insert(0, "0.01")

        self.lot_size_entry.pack(side="left", padx=(0, 4))

        self.lot_size_entry.bind("<FocusOut>", self._on_lot_size_focus_out)

        self.lot_size_entry.bind("<Return>", lambda e: self.set_manual_lot_size())



        self.lot_size_set_btn = self._apply_3d_button_feel(

            ctk.CTkButton(

                lot_top_row, text=UI_LABELS["save_btn"], width=46, height=28,

                font=ctk.CTkFont(size=11, weight="bold"),

                fg_color="#2980b9", hover_color="#1f618d", command=self.set_manual_lot_size, state="normal"

            ),

            normal_border="#93c5fd", pressed_border="#eff6ff"

        )

        self.lot_size_set_btn.pack(side="left", padx=(0, 4))



        manual_risk_row = ctk.CTkFrame(self.mt5_frame, fg_color="transparent")

        manual_risk_row.grid(row=2, column=0, sticky="w", pady=(6, 0))



        self.radius_lbl = ctk.CTkLabel(manual_risk_row, text=UI_LABELS["profit_target"], font=ctk.CTkFont(size=12, weight="bold"), text_color="#f1c40f")

        self.radius_lbl.pack(side="left", padx=(0, 4))



        self.radius_entry = ctk.CTkEntry(manual_risk_row, width=65, height=28, font=ctk.CTkFont(family="Consolas", size=12), state="normal")

        self.radius_entry.pack(side="left", padx=(0, 4))

        self.radius_entry.bind("<FocusOut>", self._on_radius_focus_out)

        self.radius_entry.bind("<Return>", lambda e: self.save_profit_radius())



        self.radius_save_btn = self._apply_3d_button_feel(

            ctk.CTkButton(

                manual_risk_row, text=UI_LABELS["save_btn"], width=46, height=28,

                font=ctk.CTkFont(size=11, weight="bold"),

                fg_color="#8e44ad", hover_color="#732d91", command=self.save_profit_radius, state="normal"

            ),

            normal_border="#c084fc", pressed_border="#faf5ff"

        )

        self.radius_save_btn.pack(side="left", padx=(0, 4))



        self.dollar_sl_lbl = ctk.CTkLabel(manual_risk_row, text="Stop Loss ($):", font=ctk.CTkFont(size=12, weight="bold"), text_color="#e67e22")

        self.dollar_sl_lbl.pack(side="left", padx=(10, 4))



        self.dollar_sl_entry = ctk.CTkEntry(manual_risk_row, width=68, height=28, font=ctk.CTkFont(family="Consolas", size=12), state="normal")

        self.dollar_sl_entry.insert(0, "0.00")

        self.dollar_sl_entry.pack(side="left", padx=(0, 4))

        self.dollar_sl_entry.bind("<FocusOut>", self._on_dollar_sl_focus_out)

        self.dollar_sl_entry.bind("<Return>", lambda e: self.set_dollar_stop_loss())



        self.dollar_sl_set_btn = self._apply_3d_button_feel(

            ctk.CTkButton(

                manual_risk_row, text=UI_LABELS["save_btn"], width=46, height=28,

                font=ctk.CTkFont(size=11, weight="bold"),

                fg_color="#d35400", hover_color="#a04000", command=self.set_dollar_stop_loss, state="normal"

            ),

            normal_border="#fdba74", pressed_border="#fff7ed"

        )

        self.dollar_sl_set_btn.pack(side="left", padx=(0, 4))



        try:

            conn = sqlite3.connect(DB_FILE, timeout=15.0)

            c = conn.cursor()

            c.execute("CREATE TABLE IF NOT EXISTS bot_config (key TEXT PRIMARY KEY, value TEXT);")

            cfg_map = dict(c.execute("SELECT key, value FROM bot_config WHERE key IN ('max_profit_radius', 'manual_lot_size', 'dollar_stop_loss');").fetchall())

            if 'manual_lot_size' in cfg_map and cfg_map['manual_lot_size'] is not None:

                try:

                    self.manual_lot_size = float(cfg_map['manual_lot_size'])

                    self.lot_size_entry.delete(0, "end")

                    self.lot_size_entry.insert(0, str(self.manual_lot_size))

                except Exception:

                    pass

            if 'dollar_stop_loss' in cfg_map and cfg_map['dollar_stop_loss'] is not None:

                try:

                    self.dollar_stop_loss = float(cfg_map['dollar_stop_loss'])

                    self.dollar_sl_entry.delete(0, "end")

                    self.dollar_sl_entry.insert(0, str(self.dollar_stop_loss))

                except Exception:

                    pass

            row = (cfg_map.get('max_profit_radius'),) if 'max_profit_radius' in cfg_map else None

            if row:

                self._cached_radius = float(row[0])

            conn.close()

        except Exception as e:

            self._log_exc("load_saved_radius", e)



        self.radius_entry.insert(0, f"{self._cached_radius:.2f}")



        self.orders_frame = ctk.CTkScrollableFrame(self.tab_active)

        self.orders_frame.pack(fill="both", expand=True, padx=10, pady=(0, 0))

        try:

            self.orders_frame._scrollbar.grid_remove()

        except Exception:

            pass



        headers = ["Ticket", "Symbol", "Type", "Lots", "Open Time", "Elapsed", "Schedule Status", "Chart", "Profit", "Close Order"]

        col_weights = [1, 1, 1, 1, 2, 1, 2, 1, 1, 1]



        for col_idx, h in enumerate(headers):

            self.orders_frame.grid_columnconfigure(col_idx, weight=col_weights[col_idx])

            lbl = ctk.CTkLabel(self.orders_frame, text=h, font=ctk.CTkFont(family="Consolas", size=12, weight="bold"), text_color="#3498db")

            lbl.grid(row=0, column=col_idx, padx=4, pady=2, sticky="w")



        self.bottom_bar = ctk.CTkFrame(self.tab_active, fg_color="transparent", height=15)

        self.bottom_bar.pack(fill="x", side="bottom", padx=15, pady=0)



        self.balance_label = ctk.CTkLabel(self.bottom_bar, text=UI_LABELS["status_ready_query"], font=ctk.CTkFont(size=12, weight="bold"), text_color="#f1c40f")

        self.balance_label.pack(side="left", pady=0)



        history_control_frame = ctk.CTkFrame(self.tab_history, fg_color="transparent")

        history_control_frame.pack(fill="x", padx=10, pady=5)



        self.total_lifetime_profit_label = ctk.CTkLabel(history_control_frame, text="Total Profit (All-Time): $0.00", font=ctk.CTkFont(family="Consolas", size=12, weight="bold"), text_color="#3498db")

        self.total_lifetime_profit_label.pack(side="left", padx=5)



        self.hist_prev_btn = self._apply_3d_button_feel(

            ctk.CTkButton(

                history_control_frame, text="◀ Prev", width=78, height=28,

                fg_color="#34495e", hover_color="#2c3e50", command=self.prev_history_page, state="disabled"

            )

        )

        self.hist_prev_btn.pack(side="left", padx=(20, 4))



        self.hist_page_lbl = ctk.CTkLabel(history_control_frame, text="Page 1 / 1 (0 orders)", font=ctk.CTkFont(family="Consolas", size=11, weight="bold"), text_color="#bdc3c7")

        self.hist_page_lbl.pack(side="left", padx=10)



        self.hist_next_btn = self._apply_3d_button_feel(

            ctk.CTkButton(

                history_control_frame, text="Next ▶", width=78, height=28,

                fg_color="#34495e", hover_color="#2c3e50", command=self.next_history_page, state="disabled"

            )

        )

        self.hist_next_btn.pack(side="left", padx=4)



        self.refresh_history_btn = self._apply_3d_button_feel(

            ctk.CTkButton(

                history_control_frame, text=UI_LABELS["refresh_history"], width=125, height=28,

                fg_color="#2980b9", hover_color="#1f618d", command=self.update_order_history

            )

        )

        self.refresh_history_btn.pack(side="right", padx=5, pady=5)



        self.history_frame = ctk.CTkFrame(self.tab_history)

        self.history_frame.pack(fill="both", expand=True, padx=10, pady=5)



        hist_headers = ["Ticket", "Symbol", "Type", "Lots", "Close Time", "Profit", "Comment"]

        for col_idx, h in enumerate(hist_headers):

            lbl = ctk.CTkLabel(self.history_frame, text=h, font=ctk.CTkFont(family="Consolas", size=11, weight="bold"), text_color="#3498db")

            lbl.grid(row=0, column=col_idx, padx=8, pady=6, sticky="w")



    def _on_radius_focus_out(self, event=None):

        val = self.radius_entry.get().strip()

        try:

            float_val = float(val) if val else 0.0

            self.radius_entry.delete(0, "end")

            self.radius_entry.insert(0, f"{float_val:.2f}")

        except ValueError:

            pass



    def prev_history_page(self):

        if self._history_page > 0:

            self._history_page -= 1

            self._render_history_page()



    def next_history_page(self):

        total_pages = max(1, math.ceil(len(self._history_deals_cache) / HISTORY_PAGE_SIZE))

        if self._history_page + 1 < total_pages:

            self._history_page += 1

            self._render_history_page()



    def _ensure_history_pool(self):

        if not hasattr(self, "_hist_font_reg"):

            self._hist_font_reg = ctk.CTkFont(family="Consolas", size=11)

        if not hasattr(self, "_hist_font_bold"):

            self._hist_font_bold = ctk.CTkFont(family="Consolas", size=11, weight="bold")

        if not hasattr(self, "_history_empty_lbl"):

            self._history_empty_lbl = ctk.CTkLabel(

                self.history_frame,

                text="No closed orders found in the last 14 days.",

                font=self._hist_font_reg,

                text_color="#95a5a6",

            )

        if not hasattr(self, "_history_row_pool"):

            self._history_row_pool = []

            widths = [70, 85, 60, 60, 130, 90, 180]

            for _ in range(HISTORY_PAGE_SIZE):

                row_widgets = []

                for col_idx, w_px in enumerate(widths):

                    font_obj = self._hist_font_bold if col_idx in (2, 5) else self._hist_font_reg

                    lbl = ctk.CTkLabel(self.history_frame, text="", font=font_obj, width=w_px, anchor="w")

                    row_widgets.append(lbl)

                self._history_row_pool.append(row_widgets)



    def _render_history_page(self):

        self._init_order_history_profit_box()

        self.redraw_history_profit_graph()

        self._ensure_history_pool()



        total_items = len(self._history_deals_cache)

        total_pages = max(1, math.ceil(total_items / HISTORY_PAGE_SIZE))

        self._history_page = max(0, min(self._history_page, total_pages - 1))



        start = self._history_page * HISTORY_PAGE_SIZE

        end = start + HISTORY_PAGE_SIZE

        page_deals = self._history_deals_cache[start:end]



        self._safe_configure(self.hist_page_lbl, text=f"Page {self._history_page + 1} / {total_pages} ({total_items} closed orders)")

        self._safe_configure(self.hist_prev_btn, state="normal" if self._history_page > 0 else "disabled")

        self._safe_configure(self.hist_next_btn, state="normal" if (self._history_page + 1) < total_pages else "disabled")



        if not page_deals:

            for row_widgets in self._history_row_pool:

                for lbl in row_widgets:

                    try:

                        lbl.grid_remove()

                    except Exception:

                        pass

            try:

                if self._history_empty_lbl.winfo_exists():

                    self._history_empty_lbl.grid(row=1, column=0, columnspan=7, padx=10, pady=12, sticky="w")

            except Exception:

                pass

            self.history_ui_rows = {"EMPTY": {"widgets": [self._history_empty_lbl]}}

            return



        try:

            if self._history_empty_lbl.winfo_exists():

                self._history_empty_lbl.grid_remove()

        except Exception:

            pass



        active_rows = {}

        for idx, row_widgets in enumerate(self._history_row_pool, start=1):

            if idx <= len(page_deals):

                deal = page_deals[idx - 1]

                close_time = self._server_to_local_dt(deal.symbol, deal.time).strftime("%Y-%m-%d %H:%M")

                action = "BUY" if deal.type == mt5.DEAL_TYPE_SELL else "SELL"

                action_color = "#2ecc71" if action == "BUY" else "#e74c3c"

                p_color = "#2ecc71" if deal.profit >= 0 else "#e74c3c"



                vals = [

                    (str(deal.position_id), "#ecf0f1"),

                    (deal.symbol, "#ecf0f1"),

                    (action, action_color),

                    (f"{deal.volume:.2f}", "#ecf0f1"),

                    (close_time, "#ecf0f1"),

                    (f"{deal.profit:.2f}", p_color),

                    (deal.comment or "", "#bdc3c7"),

                ]

                for col_idx, lbl in enumerate(row_widgets):

                    txt, fg_col = vals[col_idx]

                    self._safe_configure(lbl, text=txt, text_color=fg_col)

                    padx_val = (8, 4) if col_idx == 0 else ((4, 8) if col_idx == 6 else 4)

                    try:

                        if lbl.winfo_exists():

                            lbl.grid(row=idx, column=col_idx, padx=padx_val, pady=2, sticky="w")

                    except Exception:

                        pass

                active_rows[f"{deal.position_id}_{idx}"] = {"widgets": row_widgets}

            else:

                for lbl in row_widgets:

                    try:

                        lbl.grid_remove()

                    except Exception:

                        pass



        self.history_ui_rows = active_rows



    def update_order_history(self, force=False):

        if not self._connected or not MT5_AVAILABLE:

            return

        now_ts = time.time()

        last_ts = getattr(self, "_history_last_fetch_ts", 0.0)

        if not force and (now_ts - last_ts) < 12.0:

            self._ui(self._render_history_page)

            return

        if getattr(self, "_history_fetching", False):

            return

        self._history_fetching = True



        def _fetch():

            try:

                from_date = datetime.now() - timedelta(days=14)

                to_date = datetime.now() + timedelta(days=1)

                deals = mt5.history_deals_get(from_date, to_date)

                if not deals:

                    self._history_deals_cache = []

                else:

                    close_deals = [d for d in deals if d.entry == mt5.DEAL_ENTRY_OUT and getattr(d, "type", 0) != mt5.DEAL_TYPE_BALANCE]

                    close_deals.sort(key=lambda x: x.time, reverse=True)

                    self._history_deals_cache = close_deals[:200]

                self._history_last_fetch_ts = time.time()

                self._ui(self._render_history_page)

            except Exception as e:

                self._log_exc("update_order_history", e)

            finally:

                self._history_fetching = False



        threading.Thread(target=_fetch, daemon=True).start()



    def _reset_radius_button(self):

        try:

            self.radius_save_btn.configure(text=UI_LABELS["save_btn"], fg_color="#8e44ad", hover_color="#732d91")

        except Exception:

            pass



    def _reset_lot_size_button(self):

        try:

            self.lot_size_set_btn.configure(text=UI_LABELS["save_btn"], fg_color="#2980b9", hover_color="#1f618d")

        except Exception:

            pass



    def _flash_lot_size_button(self, text, fg_color, hover_color, revert_ms=1500):

        try:

            self.lot_size_set_btn.configure(text=text, fg_color=fg_color, hover_color=hover_color)

            self.after(revert_ms, self._reset_lot_size_button)

        except Exception:

            pass



    def _reset_dollar_sl_button(self):

        try:

            self.dollar_sl_set_btn.configure(text=UI_LABELS["save_btn"], fg_color="#d35400", hover_color="#a04000")

        except Exception:

            pass



    def _flash_dollar_sl_button(self, text, fg_color, hover_color, revert_ms=1500):

        try:

            self.dollar_sl_set_btn.configure(text=text, fg_color=fg_color, hover_color=hover_color)

            self.after(revert_ms, self._reset_dollar_sl_button)

        except Exception:

            pass



    def _on_lot_size_focus_out(self, event=None):

        val = self.lot_size_entry.get().strip()

        try:

            float_val = float(val) if val else float(getattr(self, "manual_lot_size", 0.01))

            self.lot_size_entry.delete(0, "end")

            self.lot_size_entry.insert(0, f"{float_val:.2f}")

        except ValueError:

            pass



    def _on_dollar_sl_focus_out(self, event=None):

        val = self.dollar_sl_entry.get().strip()

        try:

            float_val = float(val) if val else float(getattr(self, "dollar_stop_loss", 0.0))

            self.dollar_sl_entry.delete(0, "end")

            self.dollar_sl_entry.insert(0, f"{float_val:.2f}")

        except ValueError:

            pass



    def set_manual_lot_size(self):

        if self.fleet_active or self.auto_paused or self.news_freeze_active:

            self.append_log_scroll_safe(f"[{datetime.now().strftime('%H:%M:%S')} {get_user_tz_abbr()}] [SECURITY] Cannot modify Lot Size while Fleet is active or paused.\n")

            self._flash_lot_size_button("🔒Locked", "#7f8c8d", "#5d6d7e")

            self.lot_size_entry.delete(0, "end")

            self.lot_size_entry.insert(0, f"{float(self.manual_lot_size):.2f}")

            return

        val = self.lot_size_entry.get().strip()

        try:

            float_val = float(val)

            if math.isnan(float_val) or math.isinf(float_val) or float_val <= 0:

                raise ValueError("Lot size must be greater than 0")

            conn = sqlite3.connect(DB_FILE, timeout=15.0)

            c = conn.cursor()

            c.execute("CREATE TABLE IF NOT EXISTS bot_config (key TEXT PRIMARY KEY, value TEXT);")

            c.execute("INSERT OR REPLACE INTO bot_config (key, value) VALUES ('manual_lot_size', ?);", (str(float_val),))

            conn.commit()

            try:

                c.execute("PRAGMA wal_checkpoint(PASSIVE);")

            except Exception:

                pass

            conn.close()

            self.manual_lot_size = float_val

            self.append_log_scroll_safe(f"[{datetime.now().strftime('%H:%M:%S')} {get_user_tz_abbr()}] [RISK CONFIG] Manual Lot Size updated to {float_val:.2f} lots.\n")

            self._flash_lot_size_button("✓ Saved!", "#27ae60", "#219653")

            self.lot_size_entry.delete(0, "end")

            self.lot_size_entry.insert(0, f"{float_val:.2f}")

        except Exception as e:

            self._log_exc("set_manual_lot_size", e)

            self.append_log_scroll_safe(f"[{datetime.now().strftime('%H:%M:%S')} {get_user_tz_abbr()}] [ERROR] Invalid Lot Size (must be greater than 0): {val}\n")

            self._flash_lot_size_button("? Invalid", "#c0392b", "#962d22")

            self.lot_size_entry.delete(0, "end")

            self.lot_size_entry.insert(0, f"{float(self.manual_lot_size):.2f}")



    def set_dollar_stop_loss(self):

        if self.fleet_active or self.auto_paused or self.news_freeze_active:

            self.append_log_scroll_safe(f"[{datetime.now().strftime('%H:%M:%S')} {get_user_tz_abbr()}] [SECURITY] Cannot modify Stop Loss ($) while Fleet is active or paused.\n")

            self._flash_dollar_sl_button("🔒Locked", "#7f8c8d", "#5d6d7e")

            self.dollar_sl_entry.delete(0, "end")

            self.dollar_sl_entry.insert(0, f"{float(self.dollar_stop_loss):.2f}")

            return

        val = self.dollar_sl_entry.get().strip()

        if not val:

            val = "0.0"

        try:

            float_val = float(val)

            if math.isnan(float_val) or math.isinf(float_val):

                raise ValueError("Dollar stop loss must be a valid number")

            conn = sqlite3.connect(DB_FILE, timeout=15.0)

            c = conn.cursor()

            c.execute("CREATE TABLE IF NOT EXISTS bot_config (key TEXT PRIMARY KEY, value TEXT);")

            c.execute("INSERT OR REPLACE INTO bot_config (key, value) VALUES ('dollar_stop_loss', ?);", (str(float_val),))

            conn.commit()

            try:

                c.execute("PRAGMA wal_checkpoint(PASSIVE);")

            except Exception:

                pass

            conn.close()

            self.dollar_stop_loss = float_val

            if float_val == 0.0:

                self.append_log_scroll_safe(f"[{datetime.now().strftime('%H:%M:%S')} {get_user_tz_abbr()}] [RISK CONFIG] Stop Loss ($) set to $0.00 (disabled).\n")

            else:

                self.append_log_scroll_safe(f"[{datetime.now().strftime('%H:%M:%S')} {get_user_tz_abbr()}] [RISK CONFIG] Stop Loss ($) updated to -${abs(float_val):.2f} per order.\n")

            self._flash_dollar_sl_button("✓ Saved!", "#27ae60", "#219653")

            self.dollar_sl_entry.delete(0, "end")

            self.dollar_sl_entry.insert(0, f"{float_val:.2f}")

        except Exception as e:

            self._log_exc("set_dollar_stop_loss", e)

            self.append_log_scroll_safe(f"[{datetime.now().strftime('%H:%M:%S')} {get_user_tz_abbr()}] [ERROR] Invalid Stop Loss ($) value: {val}\n")

            self._flash_dollar_sl_button("? Invalid", "#c0392b", "#962d22")

            self.dollar_sl_entry.delete(0, "end")

            self.dollar_sl_entry.insert(0, f"{float(self.dollar_stop_loss):.2f}")



    def _flash_radius_button(self, text, fg_color, hover_color, revert_ms=1500):

        try:

            self.radius_save_btn.configure(text=text, fg_color=fg_color, hover_color=hover_color)

            self.after(revert_ms, self._reset_radius_button)

        except Exception:

            pass



    def save_profit_radius(self):

        if self.fleet_active or self.auto_paused or self.news_freeze_active:

            self.append_log_scroll_safe(f"[{datetime.now().strftime('%H:%M:%S')} {get_user_tz_abbr()}] [SECURITY] Cannot modify Profit Target while Fleet is active or paused.\n")

            self._flash_radius_button("🔒Locked", "#7f8c8d", "#5d6d7e")

            self.radius_entry.delete(0, "end")

            self.radius_entry.insert(0, f"{self._cached_radius:.2f}")

            return

        val = self.radius_entry.get().strip()

        if not val:

            val = "0.0"

        try:

            float_val = float(val)

            if float_val < 0:

                raise ValueError("Profit target cannot be negative")

            conn = sqlite3.connect(DB_FILE, timeout=30.0)

            c = conn.cursor()

            c.execute("CREATE TABLE IF NOT EXISTS bot_config (key TEXT PRIMARY KEY, value TEXT);")

            c.execute("INSERT OR REPLACE INTO bot_config (key, value) VALUES ('max_profit_radius', ?);", (str(float_val),))

            conn.commit()

            try:

                c.execute("PRAGMA wal_checkpoint(PASSIVE);")

            except Exception:

                pass

            conn.close()

            self._cached_radius = float_val

            self.append_log_scroll_safe(f"[{datetime.now().strftime('%H:%M:%S')} {get_user_tz_abbr()}] [RISK CONFIG] Profit Target updated to ${float_val:.2f} per order.\n")

            self._flash_radius_button("✓ Saved", "#27ae60", "#219653")

            self.radius_entry.delete(0, "end")

            self.radius_entry.insert(0, f"{float_val:.2f}")

        except Exception as e:

            self._log_exc("save_profit_radius", e)

            self.append_log_scroll_safe(f"[{datetime.now().strftime('%H:%M:%S')} {get_user_tz_abbr()}] [ERROR] Invalid Profit Target value: {val}\n")

            self._flash_radius_button("✗ Invalid", "#c0392b", "#962d22")

            self.radius_entry.delete(0, "end")

            self.radius_entry.insert(0, f"{self._cached_radius:.2f}")















    def _infer_currency_tag(self, text: str) -> str:

        low = (text or "").lower()

        currency_rules = [

            ("USD", ("fed", "fomc", "powell", "u.s.", "us ", "united states", "nonfarm", "nfp", "cpi", "treasury", "dollar", "usd")),

            ("EUR", ("ecb", "lagarde", "eurozone", "euro area", "euro ", "germany", "bund", "eur")),

            ("GBP", ("boe", "bank of england", "bailey", "u.k.", "uk ", "britain", "sterling", "gilt", "gbp")),

            ("JPY", ("boj", "bank of japan", "ueda", "japan", "yen", "jpy")),

            ("CHF", ("snb", "swiss", "zurich", "franc", "chf")),

            ("AUD", ("rba", "australia", "aussie", "aud")),

            ("CAD", ("boc", "bank of canada", "canada", "loonie", "cad")),

            ("NZD", ("rbnz", "new zealand", "kiwi", "nzd")),

        ]

        matched = [code for code, keys in currency_rules if any(k in low for k in keys)]

        if not matched:

            return "MACRO"

        return "/".join(matched[:3])



    def _get_groq_news_key(self) -> str:

        if hasattr(self, "ai_api_key_entry"):

            try:

                key = self.ai_api_key_entry.get().strip()

                if key:

                    return key

            except Exception:

                pass

        import os

        return os.getenv("GROQ_API_KEY", "").strip()



    def _enrich_currencies_with_groq(self, stories: list[dict], api_key: str) -> list[str]:

        from groq_diagnostics import _call_groq

        numbered = "\n".join(

            f"{i + 1}. [{s['source']}] [{s['uploaded_at']}] {s['title']}"

            for i, s in enumerate(stories)

        )

        reply, _ = _call_groq(

            api_key=api_key,

            task_type="news_triage",

            system_msg=(

                "Map each numbered headline to the primary FX currency code(s) it specifically affects "

                "(such as USD, EUR, GBP, JPY, CHF, AUD, CAD, NZD, or MACRO). "

                "Return one line per number in the exact format: <number>: <CCY>"

            ),

            user_msg=numbered[:4500],

            max_tokens=500,

            temperature=0.0,

        )

        parsed_map: dict[int, str] = {}

        for line in (reply or "").splitlines():

            if ":" in line:

                left, right = line.split(":", 1)

                digits = "".join(ch for ch in left if ch.isdigit())

                ccy = right.strip().strip("[]()*").upper()

                if digits and ccy:

                    parsed_map[int(digits)] = ccy

        return [

            parsed_map.get(i + 1) or self._infer_currency_tag(s["title"])

            for i, s in enumerate(stories)

        ]



    def fetch_live_news(self):

        threading.Thread(target=self._load_rss_news, daemon=True).start()



    def _load_rss_news(self):

        self._ui(self.news_content_lbl.configure, text="Fetching live RSS feed...", text_color="#3498db")

        try:

            url = "https://www.investing.com/rss/news_25.rss"

            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

            with urllib.request.urlopen(req, timeout=6) as response:

                xml_data = response.read()

            root = ET.fromstring(xml_data)

            channel_title_el = root.find("./channel/title")

            default_source = (channel_title_el.text or "Investing.com").strip() if channel_title_el is not None else "Investing.com"

            items = root.findall(".//item")[:30]

            stories = []

            for item in items:

                src_el = item.find("source")

                source_name = (src_el.text or "").strip() if src_el is not None and src_el.text else default_source

                pub_el = item.find("pubDate")

                uploaded_at = (pub_el.text or "").strip() if pub_el is not None and pub_el.text else "Time N/A"

                title_el = item.find("title")

                headline = (title_el.text or "No Title").strip() if title_el is not None else "No Title"

                stories.append({"source": source_name, "uploaded_at": uploaded_at, "title": headline})



            if not stories:

                self._ui(self.news_content_lbl.configure, text="No live stories returned by feed.", text_color="#f1c40f")

                return



            api_key = self._get_groq_news_key()

            if api_key:

                try:

                    currencies = self._enrich_currencies_with_groq(stories, api_key)

                except Exception as ge:

                    self._log_exc("_enrich_currencies_with_groq", ge)

                    currencies = [self._infer_currency_tag(s["title"]) for s in stories]

            else:

                currencies = [self._infer_currency_tag(s["title"]) for s in stories]



            formatted_lines = [

                f"{idx:02d}. [{ccy}] [{s['source']}] | Uploaded: {s['uploaded_at']}\n    {s['title']}\n"

                for idx, (s, ccy) in enumerate(zip(stories, currencies), 1)

            ]

            self._ui(self.news_content_lbl.configure, text="\n".join(formatted_lines), text_color="#2ecc71")

        except Exception as e:

            self._log_exc("_load_rss_news", e)

            self._ui(self.news_content_lbl.configure, text=f"Live feed unavailable: {e}", text_color="#e74c3c")



    def _fast_forward_worker_log_positions(self):

        try:

            positions = getattr(self, "file_positions", None)

            if isinstance(positions, dict):

                for key in list(positions.keys()):

                    try:

                        from pathlib import Path

                        p = Path(str(key))

                        if p.is_file():

                            with open(p, "r", encoding="utf-8", errors="ignore") as f:

                                positions[key] = len(f.readlines())

                    except Exception:

                        pass

            log_paths = getattr(self, "log_paths", None)

            if isinstance(log_paths, dict) and isinstance(positions, dict):

                for w, p in log_paths.items():

                    try:

                        from pathlib import Path

                        fp = Path(str(p))

                        if fp.is_file():

                            with open(fp, "r", encoding="utf-8", errors="ignore") as f:

                                line_cnt = len(f.readlines())

                            positions[w] = line_cnt

                            positions[str(fp)] = line_cnt

                    except Exception:

                        pass

        except Exception:

            pass



    def reset_worker_activity(self, archive_first=False):

        import time

        try:

            self._startup_log_mute_until = time.monotonic() + 1.5

            self._fast_forward_worker_log_positions()

            if not hasattr(self, "log_textbox") or not self.log_textbox.winfo_exists():

                return

            current_content = self.log_textbox.get("0.0", "end")

            if archive_first and current_content.strip():

                self._archive_activity_text(current_content)

            self.log_textbox.configure(state="normal")

            self.log_textbox.delete("0.0", "end")

            self.log_textbox.insert("0.0", "[INIT] FleetUnit multi-agent telemetry online.\n")

            self._live_log_line_count = 1

            self.log_textbox.see("end")

        except Exception:

            pass



    def _reset_after_startup_logs(self):

        self.reset_worker_activity(archive_first=False)



    def _archive_activity_text(self, content):

        if not content or not content.strip():

            return

        if hasattr(self, "_archive_log_chunk"):

            try:

                self._archive_log_chunk(content)

                return

            except Exception:

                pass

        try:

            from datetime import datetime

            from pathlib import Path

            import sys

            base = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent

            archive_dir = base / "logs" / "archive"

            archive_dir.mkdir(parents=True, exist_ok=True)

            fname = f"activity_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

            (archive_dir / fname).write_text(content, encoding="utf-8")

        except Exception:

            pass



    def _schedule_activity_30m_archive(self):

        timer_id = getattr(self, "_activity_30m_timer_id", None)

        if timer_id is not None:

            try:

                self.after_cancel(timer_id)

            except Exception:

                pass

        self._activity_30m_timer_id = self.after(30 * 60 * 1000, self._on_activity_30m_archive)



    def _on_activity_30m_archive(self):

        self._activity_30m_timer_id = None

        try:

            if hasattr(self, "log_textbox") and self.log_textbox.winfo_exists():

                self.reset_worker_activity(archive_first=True)

        finally:

            if hasattr(self, "winfo_exists") and self.winfo_exists():

                self._schedule_activity_30m_archive()

        self._schedule_activity_30m_archive()



    def _apply_default_window_geometry(self):

        try:

            if hasattr(self, "winfo_exists") and not self.winfo_exists():

                return

            sw = int(self.winfo_screenwidth() or 1920)

            sh = int(self.winfo_screenheight() or 1080)

            # Usable vertical space excluding Windows taskbar (~48px)

            usable_h = max(560, sh - 48)

            win_w = max(800, min(sw - 40, int(round(sw * 0.65))))

            win_h = max(540, min(usable_h - 16, int(round(sh * 0.78))))

            pos_x = max(0, min(sw - win_w, (sw - win_w) // 2))

            pos_y = max(0, min(usable_h - win_h, max(4, (usable_h - win_h) // 2)))

            self.geometry(f"{win_w}x{win_h}+{pos_x}+{pos_y}")

        except Exception:

            pass



    def setup_live_tab(self):

        split_frame = ctk.CTkFrame(self.tab_live, fg_color="transparent")

        split_frame.pack(fill="both", expand=True, padx=8, pady=6)

        split_frame.grid_columnconfigure(0, weight=3, uniform="activity_chat")

        split_frame.grid_columnconfigure(1, weight=2, uniform="activity_chat")

        split_frame.grid_rowconfigure(0, weight=1)



        left_pane = ctk.CTkFrame(split_frame, fg_color="transparent")

        left_pane.grid(row=0, column=0, sticky="nsew", padx=(0, 6))



        right_pane = ctk.CTkFrame(split_frame)

        right_pane.grid(row=0, column=1, sticky="nsew", padx=(6, 0))



        control_frame = ctk.CTkFrame(left_pane, fg_color="transparent")

        control_frame.pack(fill="x", padx=6, pady=4)



        self.clear_btn = self._apply_3d_button_feel(

            ctk.CTkButton(control_frame, text=UI_LABELS["archive_clear"], width=135, height=28, command=self.clear_stream)

        )

        self.clear_btn.pack(side="left", padx=(0, 6), pady=4)



        self.open_archive_btn = self._apply_3d_button_feel(

            ctk.CTkButton(

                control_frame, text=UI_LABELS["open_archive"], width=150, height=28,

                fg_color="#34495e", hover_color="#2c3e50", command=self.open_archive_folder

            )

        )

        self.open_archive_btn.pack(side="left", padx=(0, 6), pady=4)



        self.clear_proposals_btn = self._apply_3d_button_feel(

            ctk.CTkButton(control_frame, text="Clear Proposals", width=135, height=28, fg_color="#c0392b", hover_color="#922b21", command=self.clear_worker_proposals)

        )

        self.clear_proposals_btn.pack(side="left", padx=(0, 6), pady=4)



        self.log_textbox = ctk.CTkTextbox(left_pane, font=ctk.CTkFont(family="Consolas", size=11), text_color="#2ecc71")

        self.log_textbox.pack(fill="both", expand=True, padx=6, pady=4)

        self.log_textbox.insert("0.0", "[INIT] FleetUnit multi-agent telemetry online.\n")



        if hasattr(self, "_build_global_chat_tab"):

            self._build_global_chat_tab(right_pane)

        if hasattr(self, "reset_worker_activity"):

            self.reset_worker_activity(archive_first=False)

            for _delay in (300, 1200, 2600, 4500):

                try:

                    self.after(_delay, self._reset_after_startup_logs)

                except Exception:

                    pass



    def clear_worker_proposals(self):

        threading.Thread(target=self._clear_proposals_worker, daemon=True).start()



    def _clear_proposals_worker(self):

        try:

            import sqlite3

            from datetime import datetime, timezone

            conn = sqlite3.connect(DB_FILE, timeout=15)

            try:

                cur = conn.execute("DELETE FROM signal_proposals")

                deleted = cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else 0

                conn.commit()

            finally:

                conn.close()



            ts = datetime.now(timezone.utc).strftime("%H:%M:%S")

            note = f"[{ts}] ({deleted}) proposals cleared\n"



            if hasattr(self, "log_textbox") and self.log_textbox is not None:

                def _append_log(msg=note):

                    self.log_textbox.configure(state="normal")

                    self.log_textbox.insert("end", msg)

                    self.log_textbox.see("end")

                self._ui(_append_log)



            if hasattr(self, "_append_ai_chat"):

                self._ui(self._append_ai_chat, f"({deleted}) proposals cleared\n")



            if hasattr(self, "refresh_live_activity"):

                self._ui(self.refresh_live_activity)

            elif hasattr(self, "refresh_worker_activity"):

                self._ui(self.refresh_worker_activity)

        except Exception as e:

            self._log_exc("_clear_proposals_worker", e)

            if hasattr(self, "_append_ai_chat"):

                self._ui(self._append_ai_chat, f"Failed to clear signal_proposals: {e}\n")



    def setup_ai_tab(self):

        settings_frame = ctk.CTkFrame(self.tab_ai, fg_color="#1e1e1e")

        settings_frame.pack(fill="x", padx=10, pady=(10, 0))



        ctk.CTkLabel(settings_frame, text="Groq API Key:", font=ctk.CTkFont(size=11)).pack(side="left", padx=5)



        self.ai_api_key_entry = ctk.CTkEntry(settings_frame, show="*", width=220, placeholder_text="gsk_...")

        self.ai_audit_btn = ctk.CTkButton(self.ai_api_key_entry.master, text="Audit Rejections", width=130, command=self._on_audit_rejections_clicked)

        self.ai_audit_btn.pack(side="left", padx=4)

        self.ai_pm_btn = ctk.CTkButton(self.ai_api_key_entry.master, text="Post-Mortem Digest", width=140, command=self._on_post_mortem_digest_clicked)

        self.ai_pm_btn.pack(side="left", padx=4)

        self.ai_api_key_entry.pack(side="left", padx=5, pady=5)



        existing_key = load_persisted_groq_key(DB_FILE)

        if existing_key:

            os.environ["GROQ_API_KEY"] = existing_key

            self.ai_api_key_entry.insert(0, existing_key)



        self.ai_test_btn = self._apply_3d_button_feel(

            ctk.CTkButton(

                settings_frame,

                text=UI_LABELS["test_conn"],

                width=110,

                height=28,

                fg_color="#34495e",

                hover_color="#2c3e50",

                command=self.test_groq_connection

            )

        )

        self.ai_test_btn.pack(side="left", padx=5, pady=5)



        self.ai_clear_key_btn = self._apply_3d_button_feel(

            ctk.CTkButton(

                settings_frame,

                text=UI_LABELS["clear_key"],

                width=90,

                height=28,

                fg_color="#7f8c8d",

                hover_color="#5d6d7e",

                command=self.clear_groq_key

            )

        )

        self.ai_clear_key_btn.pack(side="left", padx=5, pady=5)



        ai_header_frame = ctk.CTkFrame(self.tab_ai, fg_color="transparent")

        ai_header_frame.pack(fill="x", padx=10, pady=(4, 0))



        self.open_copilot_log_btn = self._apply_3d_button_feel(

            ctk.CTkButton(

                ai_header_frame,

                text="Open Copilot Log",

                width=145,

                height=26,

                fg_color="#2c3e50",

                hover_color="#1f2d3d",

                command=self.open_ai_copilot_log,

            )

        )

        self.open_copilot_log_btn.pack(side="right", padx=(6, 0))



        self.ai_chat_display = ctk.CTkTextbox(

            self.tab_ai,

            font=ctk.CTkFont(family="Consolas", size=13),

            wrap="word",

            text_color="#2ecc71"

        )

        self.ai_chat_display.pack(fill="both", expand=True, padx=10, pady=5)

        self.ai_chat_display.insert("end", "🤖 FleetUnit AI Copilot online (Powered by Groq).\n\n⚠️ IMPORTANT: You must enter a free Groq API key above to use the AI.\nGet one at console.groq.com\n\n")

        self.ai_chat_display.configure(state="disabled")



        input_frame = ctk.CTkFrame(self.tab_ai, fg_color="transparent")

        input_frame.pack(fill="x", padx=10, pady=(0, 10))



        self.ai_entry = ctk.CTkEntry(

            input_frame,

            placeholder_text="Ask about your trades, MT5 logs, or market correlation...",

            font=ctk.CTkFont(size=13)

        )

        self.ai_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.ai_entry.bind("<Return>", lambda e: self.send_ai_message())



        self.ai_send_btn = self._apply_3d_button_feel(

            ctk.CTkButton(

                input_frame,

                text=UI_LABELS["send_ai"],

                width=85,

                height=30,

                fg_color="#8e44ad",

                hover_color="#732d91",

                command=self.send_ai_message

            ),

            normal_border="#c084fc", pressed_border="#faf5ff"

        )

        self.ai_send_btn.pack(side="right")



        self.ai_clear_chat_btn = self._apply_3d_button_feel(

            ctk.CTkButton(

                input_frame,

                text="Clear Chat",

                width=90,

                height=30,

                fg_color="#34495e",

                hover_color="#2c3e50",

                command=self.clear_copilot_chat

            )

        )

        self.ai_clear_chat_btn.pack(side="right", padx=(0, 8))







    def clear_copilot_chat(self):

        clear_copilot_history(DB_FILE)

        self.ai_chat_display.configure(state="normal")

        self.ai_chat_display.delete("0.0", "end")

        self.ai_chat_display.insert("end", "?? FleetUnit AI Copilot online (Powered by Groq).\n\n?? Chat history cleared.\n\n")

        self.ai_chat_display.configure(state="disabled")

    def clear_groq_key(self):

        self.ai_api_key_entry.delete(0, "end")

        save_groq_api_key("", DB_FILE)

        self._append_ai_chat("🧹 Cleared Groq API key from runtime and local bot_config.\n\n")



    def test_groq_connection(self):

        api_key = self.ai_api_key_entry.get().strip()

        if not api_key:

            save_groq_api_key("", DB_FILE)

            self.ai_test_btn.configure(text="No Key", fg_color="#e74c3c", hover_color="#c0392b")

            self.after(3000, lambda: self.ai_test_btn.configure(text=UI_LABELS["test_conn"], fg_color="#34495e", hover_color="#2c3e50"))

            return



        save_groq_api_key(api_key, DB_FILE)

        self.ai_test_btn.configure(text="Testing...", fg_color="#f1c40f", hover_color="#f39c12", state="disabled")



        def _run_test():

            try:

                models_url = "https://api.groq.com/openai/v1/models"

                headers = {"Authorization": f"Bearer {api_key}"}

                resp = requests.get(models_url, headers=headers, timeout=10)



                if resp.status_code == 200:

                    self.after(0, lambda: self.ai_test_btn.configure(text="✅ Connected", fg_color="#27ae60", hover_color="#219653", state="normal"))

                elif resp.status_code == 401:

                    self.after(0, lambda: self.ai_test_btn.configure(text="❌ Invalid Key", fg_color="#e74c3c", hover_color="#c0392b", state="normal"))

                else:

                    self.after(0, lambda: self.ai_test_btn.configure(text="❌ API Error", fg_color="#e74c3c", hover_color="#c0392b", state="normal"))



            except Exception:

                self.after(0, lambda: self.ai_test_btn.configure(text="❌ Net Error", fg_color="#e74c3c", hover_color="#c0392b", state="normal"))



            def _reset():

                if self.ai_test_btn.winfo_exists():

                    self.ai_test_btn.configure(text=UI_LABELS["test_conn"], fg_color="#34495e", hover_color="#2c3e50", state="normal")



            self.after(4000, _reset)



        threading.Thread(target=_run_test, daemon=True).start()



    def send_ai_message(self):

        user_text = self.ai_entry.get().strip()

        if not user_text:

            return



        self.ai_entry.delete(0, "end")

        self._append_ai_chat(f"You: {user_text}\n\n")

        append_copilot_history("user", user_text, DB_FILE)

        self.ai_send_btn.configure(state="disabled", text="Thinking...")



        threading.Thread(target=self._fetch_ai_response, args=(user_text,), daemon=True).start()



    def _resolve_copilot_archive_dir(self):

        try:

            archive_dir = globals().get("ARCHIVE_LOG_DIR")

            if archive_dir:

                return str(archive_dir)

        except Exception:

            pass

        from pathlib import Path

        import sys

        base = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent

        return str(base / "logs" / "archive")



    def _cleanup_old_copilot_logs(self):

        try:

            import os, time

            archive_dir = self._resolve_copilot_archive_dir()

            if not os.path.exists(archive_dir):

                return

            retention_days = globals().get("ARCHIVE_RETENTION_DAYS", 14)

            cutoff = time.time() - (float(retention_days) * 86400)

            for fname in os.listdir(archive_dir):

                if not (fname.startswith("ai_copilot_") and fname.endswith(".log")):

                    continue

                fpath = os.path.join(archive_dir, fname)

                if os.path.isfile(fpath) and os.path.getmtime(fpath) < cutoff:

                    try:

                        os.remove(fpath)

                    except Exception:

                        pass

        except Exception as e:

            if hasattr(self, "_log_exc"):

                self._log_exc("_cleanup_old_copilot_logs", e)



    def get_ai_copilot_log_path(self):

        import os

        from datetime import datetime

        archive_dir = self._resolve_copilot_archive_dir()

        os.makedirs(archive_dir, exist_ok=True)

        stamp = datetime.now().strftime("%Y-%m-%d_%H")

        return os.path.join(archive_dir, f"ai_copilot_{stamp}.log")



    def _write_ai_copilot_log(self, text):

        try:

            if not text or not str(text).strip():

                return

            from datetime import datetime

            log_path = self.get_ai_copilot_log_path()

            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            cleaned = str(text).rstrip("\r\n")

            formatted_lines = [f"[{ts}] {line}" for line in cleaned.splitlines() if line.strip()]

            if not formatted_lines:

                return

            with open(log_path, "a", encoding="utf-8") as f:

                f.write("\n".join(formatted_lines) + "\n")

            self._cleanup_old_copilot_logs()

        except Exception as e:

            if hasattr(self, "_log_exc"):

                self._log_exc("_write_ai_copilot_log", e)



    def open_ai_copilot_log(self):

        try:

            import os

            archive_dir = self._resolve_copilot_archive_dir()

            os.makedirs(archive_dir, exist_ok=True)

            os.startfile(archive_dir)

        except Exception as e:

            if hasattr(self, "_log_exc"):

                self._log_exc("open_ai_copilot_log", e)



    def _append_ai_chat(self, text):

        if hasattr(self, "_write_ai_copilot_log"):

            self._write_ai_copilot_log(text)

        self.ai_chat_display.configure(state="normal")

        self.ai_chat_display.insert("end", text)

        self.ai_chat_display.see("end")

        self.ai_chat_display.configure(state="disabled")



    def _execute_safe_sql(self, query):

        query = query.strip()

        if not query.lower().startswith("select"):

            return "Error: Only SELECT queries are allowed."



        try:

            conn = sqlite3.connect(DB_FILE, timeout=10.0)

            c = conn.cursor()

            c.execute(query)

            columns = [desc[0] for desc in c.description]

            rows = c.fetchall()

            conn.close()



            if not rows:

                return "Query returned 0 rows."



            result = " | ".join(columns) + "\n"

            result += "-" * 40 + "\n"



            for row in rows[:50]:

                result += " | ".join(str(val) for val in row) + "\n"



            if len(rows) > 50:

                result += f"... and {len(rows) - 50} more rows."



            return result

        except Exception as e:

            return f"SQL Error: {str(e)}"





    def _on_audit_rejections_clicked(self):

        api_key = self.ai_api_key_entry.get().strip() if hasattr(self, "ai_api_key_entry") else ""

        self._append_ai_chat("?? Auditing recent REJECTED proposals (cap: 30 rows)...\n")

        run_async_task(

            self,

            fn=lambda: audit_rejected_proposals(DB_FILE, api_key, limit=30),

            on_complete=lambda res: self._append_ai_chat(

                f"?? Rejection Audit ({res.get('model_used', 'n/a')}, {res['rows_analyzed']} rows):\n{res['summary']}\n\n"

            ),

            on_error=lambda err: self._append_ai_chat(f"?? Rejection audit error: {err}\n\n"),

        )



    def _on_post_mortem_digest_clicked(self):

        api_key = self.ai_api_key_entry.get().strip() if hasattr(self, "ai_api_key_entry") else ""

        self._append_ai_chat("?? Synthesizing recent post-mortems (cap: 25 rows)...\n")

        run_async_task(

            self,

            fn=lambda: synthesize_post_mortems(DB_FILE, api_key, limit=25),

            on_complete=lambda res: self._append_ai_chat(

                f"?? Post-Mortem Synthesis ({res.get('model_used', 'n/a')}, {res['rows_analyzed']} rows):\n{res['summary']}\n\n"

            ),

            on_error=lambda err: self._append_ai_chat(f"?? Post-mortem synthesis error: {err}\n\n"),

        )



    def _fetch_ai_response(self, user_prompt):

        try:

            api_key = self.ai_api_key_entry.get().strip()

            if not api_key:

                self.after(0, lambda: self._append_ai_chat("?? Error: Please enter your Groq API Key at the top of this tab.\n\n"))

                return



            save_groq_api_key(api_key, DB_FILE)



            context = f"Balance: ${self._account_balance:.2f} | Phase: {self.market_phase} | "

            context += f"Open Trades: {len(self.cached_positions)} | "

            context += f"Daily P/L: ${self.fetch_daily_realized_profit():.2f}\n"



            if self.cached_positions:

                context += "Current Open Positions:\n"

                for p in self.cached_positions:

                    side = "BUY" if p.type == 0 else "SELL"

                    context += f"- {p.symbol} {side} | P/L: ${p.profit:.2f}\n"



            full_snapshot = build_full_system_snapshot(DB_FILE, max_chars=5500)



            db_schema = (

                "\n--- READ-ONLY SYSTEM & DATABASE ACCESS ---\n"

                "You have read-only access to ALL SQLite tables in trade_memory.db, all Python modules in the fleet directory, "

                "and recent log lines from logs/*.log (summarized in the system snapshot below). "

                "Do NOT claim you are limited to only bot_config, system_state, and signal_proposals.\n"

                "If you need specific rows from SQLite, output ONLY a read-only SELECT/WITH query wrapped in [SQL] and [/SQL] tags. "

                "Example: [SQL] SELECT name FROM sqlite_master WHERE type='table'; [/SQL]\n"

                "If you already have the answer or don't need SQL, reply normally.\n"

                "-----------------------------------------\n"

            )



            system_prompt = (

                "You are a concise Forex trading assistant with read-only visibility across all SQLite tables, fleet Python modules, and recent logs. "

                "Answer ONLY what the user directly asks. Do NOT repeat earlier tables, capability lists, or prior notes unless explicitly asked. "

                "Keep simple status/query answers brief and direct without extra unrequested sections. "

                f"Context:\n{context}{db_schema}\n{full_snapshot}"

            )



            prior_turns = load_copilot_history(limit=6, db_path=DB_FILE)

            history_payload = []

            bad_denials = (

                "don?t have a record",

                "don't have a record",

                "don?t have any record",

                "don't have any record",

                "didn?t actually say that",

                "didn't actually say that",

            )

            for turn in prior_turns:

                role = turn.get("role")

                txt = str(turn.get("content") or "").strip()

                if not txt or role not in ("user", "assistant"):

                    continue

                if role == "assistant" and any(b in txt.lower() for b in bad_denials):

                    continue

                history_payload.append({"role": role, "content": txt[:450]})

            if not history_payload or history_payload[-1]["content"] != user_prompt:

                history_payload.append({"role": "user", "content": user_prompt})

            messages = [{"role": "system", "content": system_prompt}] + history_payload



            model_candidates = ["openai/gpt-oss-20b", "openai/gpt-oss-120b", "gemma2-9b-it"]

            url = "https://api.groq.com/openai/v1/chat/completions"

            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}



            max_sql_rounds = 2

            sql_rounds = 0



            while True:

                ai_reply = None

                model_used = None

                last_error = None



                for model_name in model_candidates:

                    try:

                        payload = {

                            "model": model_name,

                            "messages": messages,

                            "temperature": 0.2,

                            "max_tokens": 2400,

                        }

                        response = requests.post(url, headers=headers, json=payload, timeout=25)



                        if response.status_code == 200:

                            data = response.json()

                            ai_reply = data["choices"][0]["message"]["content"]

                            model_used = model_name

                            break

                        else:

                            last_error = f"{model_name}: {response.status_code}"

                    except Exception as e:

                        last_error = f"{model_name}: {str(e)}"



                if not ai_reply:

                    raise Exception(f"All models failed. Last error: {last_error}")



                sql_match = re.search(r"\[SQL\](.*?)\[/SQL\]", ai_reply, re.DOTALL | re.IGNORECASE)

                if sql_match and sql_rounds < max_sql_rounds:

                    sql_rounds += 1

                    sql_query = sql_match.group(1).strip()

                    self.after(0, lambda q=sql_query: self._append_ai_chat(f"?? AI is querying database: {q}\n"))



                    sql_result = self._execute_safe_sql(sql_query)



                    messages.append({"role": "assistant", "content": ai_reply})

                    note = (

                        "No more SQL queries allowed on this turn. Give the final answer now."

                        if sql_rounds >= max_sql_rounds

                        else "Answer using this result or run at most one more focused query if needed."

                    )

                    messages.append({"role": "user", "content": f"SQL Result:\n{str(sql_result)[:2500]}\n{note}"})

                    continue



                clean_reply = re.sub(r"\[SQL\].*?\[/SQL\]", "", ai_reply, flags=re.DOTALL | re.IGNORECASE).strip()

                if not clean_reply:

                    clean_reply = "I ran the database check, but no final summary text was returned."



                append_copilot_history("assistant", clean_reply, DB_FILE)

                self.after(0, lambda r=clean_reply, m=model_used: self._append_ai_chat(f"?? AI ({m}): {r}\n\n"))

                break



        except Exception as e:

            err_msg = str(e)

            self.after(0, lambda msg=err_msg: self._append_ai_chat(f"?? Error: {msg}\n\n"))

        finally:

            self.after(0, lambda: self.ai_send_btn.configure(state="normal", text=UI_LABELS["send_ai"]))

    def setup_security_tab(self):

        scroll = ctk.CTkScrollableFrame(self.tab_security, fg_color="transparent")

        scroll.pack(fill="both", expand=True, padx=10, pady=10)



        title = ctk.CTkLabel(scroll, text="FleetUnit Trust & Support", font=ctk.CTkFont(size=20, weight="bold"))

        title.pack(anchor="w", pady=(0, 10))



        desc_text = (

            "We believe in complete transparency. FleetUnit is 100% Open Source. "

            "You can inspect every line of code to verify there is no malware, spyware, or hidden logic.\n\n"

            "Because algorithmic trading bots execute background scripts and connect to financial APIs, "

            "Windows Defender and other antivirus software sometimes throw 'False Positives'. "

            "Use the tools below to verify your installation."

        )

        desc = ctk.CTkLabel(

            scroll, text=desc_text, font=ctk.CTkFont(size=13), text_color="#bdc3c7", justify="left", wraplength=800

        )

        desc.pack(anchor="w", pady=(0, 20))



        donate_frame = ctk.CTkFrame(scroll, fg_color="#2b1b3d", corner_radius=8, border_width=1, border_color="#8e44ad")

        donate_frame.pack(fill="x", pady=(20, 10))



        ctk.CTkLabel(donate_frame, text="☕ Support the Developer", font=ctk.CTkFont(size=16, weight="bold"), text_color="#e0b0ff").pack(anchor="w", padx=15, pady=(15, 5))

        

        donate_text = (

            "FleetUnit is completely free and open-source. If this bot helps you make profitable trades, "

            "consider buying me a coffee! Your support helps cover server costs and fuels future updates."

        )

        ctk.CTkLabel(donate_frame, text=donate_text, text_color="#d1c4e9", wraplength=800, justify="left").pack(anchor="w", padx=15, pady=(0, 15))



        # UPDATE THIS URL TO YOUR PAYPAL.ME, KO-FI, OR BUYMEACOFFEE LINK

        self.donate_btn = self._apply_3d_button_feel(

            ctk.CTkButton(

                donate_frame, text="Donate via Buy Me a Coffee", width=220, height=36,

                font=ctk.CTkFont(size=14, weight="bold"),

                fg_color="#f39c12", hover_color="#e67e22", command=lambda: webbrowser.open("https://buymeacoffee.com/knackatronic")

            ),

            normal_border="#fde047", pressed_border="#fef08a"

        )

        self.donate_btn.pack(anchor="w", padx=15, pady=(0, 20))





        # --- 1. OPEN SOURCE VERIFICATION ---

        os_frame = ctk.CTkFrame(scroll, fg_color="#1e1e1e", corner_radius=8)

        os_frame.pack(fill="x", pady=10)



        ctk.CTkLabel(os_frame, text="Open Source Code", font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", padx=15, pady=(10, 5))

        ctk.CTkLabel(os_frame, text="View the entire codebase on GitHub. No hidden files, no obfuscated logic.", text_color="#95a5a6").pack(anchor="w", padx=15, pady=(0, 10))

        

        self.github_btn = self._apply_3d_button_feel(

            ctk.CTkButton(

                os_frame, text="View Source on GitHub", width=200, height=32,

                fg_color="#333333", hover_color="#444444", command=lambda: webbrowser.open("https://github.com/knackatronic/FleetUnit")

            ),

            normal_border="#666666"

        )

        self.github_btn.pack(anchor="w", padx=15, pady=(0, 15))



        # --- 2. WINDOWS DEFENDER SCAN ---

        defender_frame = ctk.CTkFrame(scroll, fg_color="#1e1e1e", corner_radius=8)

        defender_frame.pack(fill="x", pady=10)



        ctk.CTkLabel(defender_frame, text="Windows Defender Deep Scan", font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", padx=15, pady=(10, 5))

        ctk.CTkLabel(defender_frame, text="Runs a local, offline scan of the forexbot directory using your system's antivirus.", text_color="#95a5a6").pack(anchor="w", padx=15, pady=(0, 10))

        

        self.defender_btn = self._apply_3d_button_feel(

            ctk.CTkButton(

                defender_frame, text="Run Windows Defender Scan", width=220, height=32,

                fg_color="#2980b9", hover_color="#1f618d", command=self.run_defender_scan

            )

        )

        self.defender_btn.pack(anchor="w", padx=15, pady=(0, 10))



        self.defender_log = ctk.CTkTextbox(defender_frame, height=80, font=ctk.CTkFont(family="Consolas", size=11))

        self.defender_log.pack(fill="x", padx=15, pady=(0, 15))

        self.defender_log.insert("0.0", "Awaiting scan...\n")

        self.defender_log.configure(state="disabled")



        # --- 3. SHA-256 INTEGRITY HASH ---

        hash_frame = ctk.CTkFrame(scroll, fg_color="#1e1e1e", corner_radius=8)

        hash_frame.pack(fill="x", pady=10)



        ctk.CTkLabel(hash_frame, text="SHA-256 Integrity Hash", font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", padx=15, pady=(10, 5))

        ctk.CTkLabel(hash_frame, text="Verifies that the executable hasn't been modified or tampered with.", text_color="#95a5a6").pack(anchor="w", padx=15, pady=(0, 10))

        

        self.hash_lbl = ctk.CTkLabel(hash_frame, text="Calculating...", font=ctk.CTkFont(family="Consolas", size=12), text_color="#f1c40f", wraplength=800, justify="left")

        self.hash_lbl.pack(anchor="w", padx=15, pady=(0, 15))

        

        self.after(500, self.generate_file_hash)



    def generate_file_hash(self):

        try:

            exe_path = sys.executable

            sha256_hash = hashlib.sha256()

            with open(exe_path, "rb") as f:

                for byte_block in iter(lambda: f.read(4096), b""):

                    sha256_hash.update(byte_block)

            self.hash_lbl.configure(text=sha256_hash.hexdigest(), text_color="#2ecc71")

        except Exception as e:

            self.hash_lbl.configure(text=f"Error generating hash: {e}", text_color="#e74c3c")



    def run_defender_scan(self):

        self.defender_log.configure(state="normal")

        self.defender_log.delete("0.0", "end")

        self.defender_log.insert("end", "Starting Windows Defender scan. This may take a minute...\n")

        self.defender_log.configure(state="disabled")

        self.defender_btn.configure(state="disabled", text="Scanning...")



        def _scan():

            try:

                defender_exe = r"C:\Program Files\Windows Defender\MpCmdRun.exe"

                

                if not os.path.exists(defender_exe):

                    platform_dir = r"C:\ProgramData\Microsoft\Windows Defender\Platform"

                    if os.path.exists(platform_dir):

                        versions = [os.path.join(platform_dir, d) for d in os.listdir(platform_dir) if os.path.isdir(os.path.join(platform_dir, d))]

                        if versions:

                            versions.sort(reverse=True)

                            defender_exe = os.path.join(versions[0], "MpCmdRun.exe")



                if not os.path.exists(defender_exe):

                    self._ui_append_defender_log("Error: Could not find Windows Defender CLI on this system.\n")

                    return



                result = subprocess.run(

                    [defender_exe, "-Scan", "-ScanType", "3", "-File", BASE_DIR],

                    capture_output=True, text=True,

                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)

                )



                output = result.stdout + "\n" + result.stderr

                

                if "no threats" in output.lower() or result.returncode == 0:

                    self._ui_append_defender_log("✅ No threats found. The directory is clean.\n")

                else:

                    self._ui_append_defender_log("⚠️ Defender finished scanning. Check the results below:\n\n" + output)



            except Exception as e:

                self._ui_append_defender_log(f"❌ Error during scan: {e}\n")

            finally:

                self.ui_reset_defender_btn()



        threading.Thread(target=_scan, daemon=True).start()



    def _ui_append_defender_log(self, text):

        self.after(0, lambda: self._append_defender_log_main(text))



    def _append_defender_log_main(self, text):

        self.defender_log.configure(state="normal")

        self.defender_log.insert("end", text)

        self.defender_log.see("end")

        self.defender_log.configure(state="disabled")



    def ui_reset_defender_btn(self):

        self.after(0, lambda: self.defender_btn.configure(state="normal", text="Run Windows Defender Scan"))



    def open_archive_folder(self):

        try:

            os.makedirs(ARCHIVE_LOG_DIR, exist_ok=True)

            os.startfile(ARCHIVE_LOG_DIR)

        except Exception as e:

            self._log_exc("open_archive_folder", e)



    def _archive_log_chunk(self, text_block):

        if not text_block or not text_block.strip():

            return

        try:

            os.makedirs(ARCHIVE_LOG_DIR, exist_ok=True)

            stamp = datetime.now().strftime("%Y-%m-%d_%H")

            with open(os.path.join(ARCHIVE_LOG_DIR, f"worker_activity_{stamp}.log"), "a", encoding="utf-8") as f:

                f.write(text_block + "\n")

        except Exception as e:

            self._log_exc("_archive_log_chunk", e)



    def _cleanup_old_archived_logs(self):

        try:

            if not os.path.exists(ARCHIVE_LOG_DIR):

                return

            cutoff = time.time() - (ARCHIVE_RETENTION_DAYS * 86400)

            for fname in os.listdir(ARCHIVE_LOG_DIR):

                fpath = os.path.join(ARCHIVE_LOG_DIR, fname)

                if os.path.isfile(fpath) and os.path.getmtime(fpath) < cutoff:

                    try:

                        os.remove(fpath)

                    except Exception:

                        pass

        except Exception as e:

            self._log_exc("_cleanup_old_archived_logs", e)



    def open_help_modal(self):

        help_win = ctk.CTkToplevel(self)

        help_win.title("FleetUnit - MT5 Setup Guide")

        help_win.geometry("620x580")

        help_win.attributes("-topmost", True)

        if os.path.exists(ICON_FILE):

            try:

                help_win.wm_iconbitmap(ICON_FILE)

            except Exception:

                pass



        ctk.CTkLabel(help_win, text="MetaTrader 5 Configuration Checklist", font=ctk.CTkFont(size=15, weight="bold")).pack(pady=(12, 8))



        info_box = ctk.CTkFrame(help_win, fg_color="#2b2b2b", border_color="#f1c40f", border_width=1, corner_radius=6)

        info_box.pack(padx=20, pady=(0, 10), fill="x")

        info_text = (

            "HIDING MT5: You can hide or restore the MT5 terminal window to save screen space and reduce battery usage without stopping fleet monitoring. Use the 'Hide MT5' / 'Show MT5' button in this '?' guide window to toggle MT5 visibility."



        )

        ctk.CTkLabel(

            info_box, text=info_text, text_color="#f1c40f", wraplength=520,

            justify="left", font=ctk.CTkFont(family="Consolas", size=11)

        ).pack(padx=10, pady=10)



        mt5_toggle_row = ctk.CTkFrame(help_win, fg_color="transparent")

        mt5_toggle_row.pack(padx=20, pady=(0, 6), fill="x")

        self.hide_mt5_btn = self._apply_3d_button_feel(

            ctk.CTkButton(

                mt5_toggle_row,

                text="Hide MT5",

                width=120,

                height=28,

                fg_color="#2980b9",

                hover_color="#1f618d",

                command=self.toggle_mt5_visibility,

            )

        )

        self.hide_mt5_btn.pack(side="left")

        if hasattr(self, "_update_mt5_button_state") and callable(self._update_mt5_button_state):

            try:

                self._update_mt5_button_state()

            except Exception:

                pass



        chk_frame = ctk.CTkScrollableFrame(help_win, width=560, height=320)

        chk_frame.pack(padx=12, pady=4, fill="both", expand=True)

        steps = [

            ("1. Download & Install MT5", "Download official 64-bit MT5 terminal."),

            ("2. Log into Account", "Log into your broker live/demo account."),

            ("3. Enable Automated Trading", "Check 'Allow automated trading' in Tools > Options > Expert Advisors."),

            ("4. Enable DLL Imports", "Check 'Allow DLL imports' for Python bridge communication.")

        ]

        for t, d in steps:

            b = ctk.CTkFrame(chk_frame)

            b.pack(fill="x", padx=5, pady=5)

            ctk.CTkCheckBox(b, text=t, font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=10, pady=(6, 2))

            ctk.CTkLabel(b, text=d, font=ctk.CTkFont(size=11), text_color="#bdc3c7").pack(anchor="w", padx=30, pady=(0, 6))



        close_btn = self._apply_3d_button_feel(

            ctk.CTkButton(help_win, text="Close Guide", fg_color="#c0392b", hover_color="#962d22", command=help_win.destroy)

        )

        close_btn.pack(pady=12)



    def toggle_fleet_state(self):

        if not self._connected:

            return

        if self.auto_paused or self.news_freeze_active:

            return

        if not self.fleet_active:

            if not self.save_manual_risk_settings(persist=True):

                return

        else:

            try:

                lot_val = self._read_lot_size_input()

                sl_val = self._read_dollar_sl_input()

                if lot_val is not None and lot_val > 0:

                    self.manual_lot_size = lot_val

                if sl_val is not None:

                    self.dollar_stop_loss = sl_val

                self._persist_manual_controls("toggle_fleet_state_pause")

            except Exception:

                pass

        self.fleet_active = not self.fleet_active

        self._persist_fleet_active()

        if self.fleet_active:

            self._launch_fleet_workers()

        else:

            self._stop_fleet_workers()

        self._sync_system_paused()

        self.update_system_status_ui()



    def connect_mt5(self):

        if getattr(self, "_scanning", False):

            return

        self._scanning = True

        self.update_connect_button_ui()



        def _run():

            try:

                self._mt5_position_scan_task()

            finally:

                self._scanning = False

                self.update_connect_button_ui()

                self.update_system_status_ui()



        threading.Thread(target=_run, daemon=True).start()



    def _mt5_position_scan_task(self):

        if not MT5_AVAILABLE:

            self._connected = False

            self.update_system_status_ui()

            return

        if mt5.terminal_info() is None and not mt5.initialize():

            self._connected = False

            self._ui(self.balance_label.configure, text="Status: Failed to initialize MT5 Terminal", text_color="#e74c3c")

            self.update_system_status_ui()

            return

        acc_info = mt5.account_info()

        positions = mt5.positions_get()

        if acc_info is not None:

            self._connected = True

            self._account_balance = acc_info.balance

            self.dynamic_slots, _ = self._compute_dynamic_scaling(acc_info.balance)

            self._persist_dynamic_scaling("persist_dynamic_scaling_scan")



            self._account_line = f"Live Connected (Acc: {acc_info.login}) | Bal: ${acc_info.balance:.2f} {acc_info.currency} | Slots: {self.dynamic_slots}"

            self._ui(self.balance_label.configure, text=self._account_line, text_color="#2ecc71")

            self.cached_positions = list(positions) if positions else []

            self._enforce_dollar_stop_loss(self.cached_positions)

            daily_pl = self.fetch_daily_realized_profit()

            total_pl = self.fetch_lifetime_realized_profit()

            self._ui(self.render_orders_flicker_free, self.cached_positions, daily_pl, total_pl)

        else:

            self._connected = False

            self._ui(self.balance_label.configure, text="Status: No MT5 Account Logged In", text_color="#e74c3c")

        self.update_system_status_ui()



    def close_order_action(self, ticket_id, comment="FleetUnit Close"):

        threading.Thread(target=self._execute_close_order, args=(ticket_id, comment), daemon=True).start()



    def _execute_close_order(self, ticket_id, comment="FleetUnit Close"):

        try:

            if not MT5_AVAILABLE:

                return

            pos = mt5.positions_get(ticket=int(ticket_id))

            if not pos:

                return

            p = pos[0]

            tick = mt5.symbol_info_tick(p.symbol)

            if not tick:

                return

            price = tick.bid if p.type == 0 else tick.ask

            rev = mt5.ORDER_TYPE_SELL if p.type == 0 else mt5.ORDER_TYPE_BUY

            req = {

                "action": mt5.TRADE_ACTION_DEAL,

                "symbol": p.symbol,

                "volume": p.volume,

                "type": rev,

                "position": int(ticket_id),

                "price": price,

                "deviation": 20,

                "magic": 230000,

                "comment": str(comment)[:18],

                "type_time": mt5.ORDER_TIME_GTC,

                "type_filling": mt5.ORDER_FILLING_IOC,

            }

            res = self._order_send_with_fill_retry(req, p.symbol)

            if res is not None and res.retcode == mt5.TRADE_RETCODE_DONE:

                self._closed_tickets.add(int(ticket_id))

        except Exception as e:

            self._log_exc("_execute_close_order", e)



    def fetch_daily_realized_profit(self):

        now_ts = time.time()

        if now_ts - self._hist_cache["daily_ts"] < 30:

            return self._hist_cache["daily"]

        realized = 0.0

        try:

            if not MT5_AVAILABLE:

                return 0.0

            now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

            start_day = self._market_day_start_utc()

            deals = mt5.history_deals_get(start_day, now_utc + timedelta(days=1))

            if deals:

                for d in deals:

                    if d.entry == mt5.DEAL_ENTRY_OUT and getattr(d, "type", 0) != mt5.DEAL_TYPE_BALANCE:

                        realized += d.profit

        except Exception as e:

            self._log_exc("fetch_daily_realized_profit", e)

        self._hist_cache["daily"] = realized

        self._hist_cache["daily_ts"] = now_ts

        return realized



    def fetch_lifetime_realized_profit(self):

        now_ts = time.time()

        if now_ts - self._hist_cache["total_ts"] < 30:

            return self._hist_cache["total"]

        lifetime = 0.0

        try:

            if not MT5_AVAILABLE:

                return 0.0

            now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

            deals = mt5.history_deals_get(datetime(2020, 1, 1), now_utc + timedelta(days=1))

            if deals:

                for d in deals:

                    if d.entry == mt5.DEAL_ENTRY_OUT and getattr(d, "type", 0) != mt5.DEAL_TYPE_BALANCE:

                        lifetime += d.profit

        except Exception as e:

            self._log_exc("fetch_lifetime_realized_profit", e)

        self._hist_cache["total"] = lifetime

        self._hist_cache["total_ts"] = now_ts

        return lifetime



    def live_ticker_loop(self):

        last_pos_refresh, last_schedule_check = 0, 0

        last_mt5_btn_check = 0

        while self.is_running:

            time.sleep(1)

            now = time.time()



            if now - last_mt5_btn_check > 2:

                last_mt5_btn_check = now

                self._ui(self._update_mt5_button_state)



            if now - last_schedule_check >= 15:

                last_schedule_check = now

                self.check_market_schedule()

                self.check_news_freeze()



            self._ui(self._update_rollover_timer)



            if now - last_pos_refresh >= 2 and MT5_AVAILABLE and self._connected:

                last_pos_refresh = now

                try:

                    fresh = mt5.positions_get()

                    if fresh is not None:

                        self.cached_positions = list(fresh)

                        active_tickets = {p.ticket for p in self.cached_positions}

                        self._closing = {t for t in self._closing if t in active_tickets}



                        effective_radius = float(self._cached_radius)

                        if self.market_phase == "HARVEST_MODE" and effective_radius > 0:

                            effective_radius *= ROLLOVER_HARVEST_DECAY



                        in_dead_zone = self.market_phase in ("DEAD_ZONE_LOCKDOWN", "WEEKEND_LOCKDOWN")



                        if self.fleet_active and effective_radius > 0 and not in_dead_zone:

                            for p in self.cached_positions:

                                if p.ticket not in self._closing and p.profit >= effective_radius:

                                    self._closing.add(p.ticket)

                                    self.close_order_action(p.ticket, comment=f"Target ${effective_radius:.2f}")



                        if self.fleet_active:

                            for p in self.cached_positions:

                                pass

                    elif mt5.terminal_info() is None:

                        if self._connected:

                            self._connected = False

                            self.update_connect_button_ui()

                            self.update_system_status_ui()

                            self._ui(self.balance_label.configure, text="Status: MT5 Disconnected", text_color="#e74c3c")

                except Exception:

                    pass

            if self._connected and self._current_tab == "Live Orders & Account" and self._current_inner_tab == "Active Orders":

                try:

                    daily_pl = self.fetch_daily_realized_profit()

                    total_pl = self.fetch_lifetime_realized_profit()

                    self._ui(self.render_orders_flicker_free, self.cached_positions, daily_pl, total_pl)

                except Exception:

                    pass

    def background_event_listener(self):

        workers = [w.replace(".py", "") for w in WORKER_SCRIPTS]

        while self.is_running:

            time.sleep(2.0)

            try:

                for w in workers:

                    log_path = os.path.join(LOG_DIR, f"{w}.log")

                    if os.path.exists(log_path):

                        mtime = os.path.getmtime(log_path)

                        if w not in self.last_mtimes:

                            self.last_mtimes[w] = mtime

                            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:

                                lines = f.readlines()

                                self.file_positions[w] = len(lines)

                        elif mtime > self.last_mtimes[w]:

                            self.last_mtimes[w] = mtime

                            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:

                                lines = f.readlines()

                                last_pos = self.file_positions.get(w, 0)

                                if len(lines) > last_pos:

                                    new_lines = lines[last_pos:]

                                    self.file_positions[w] = len(lines)

                                    self.append_log_scroll_safe("".join(new_lines))

            except Exception as e:

                self._log_exc("background_event_listener", e)



    def classify_position_performance(self, pos, elapsed_secs):

        profit = float(pos.profit)

        lots = max(0.01, float(getattr(pos, "volume", 0.01) or 0.01))

        lot_scale = lots / 0.01



        effective_target = float(self._cached_radius or 0.0)

        if effective_target > 0 and getattr(self, "market_phase", "") == "HARVEST_MODE":

            effective_target *= ROLLOVER_HARVEST_DECAY



        if effective_target > 0:

            ratio = profit / effective_target

            if ratio >= 1.0:

                return "▲▲ TARGET REACHED", "#2ecc71"

            elif ratio >= 0.75:

                return "▲  APPROACHING TARGET", "#27ae60"

            elif ratio >= 0.35:

                return "▲  BUILDING MOMENTUM", "#3498db"

            elif profit >= -2.00 * lot_scale:

                return "●  ON TRACK", "#2980b9"

            elif profit >= -3.00 * lot_scale:

                return "▼  SLIGHTLY BEHIND", "#f39c12"

            elif profit >= -5.00 * lot_scale:

                return "▼  SEVERELY BEHIND", "#e67e22"

            else:

                return "▼▼ CRITICALLY BEHIND", "#e74c3c"



        if profit > 12.00 * lot_scale:

            return "▲▲ SIGNIFICANTLY AHEAD", "#27ae60"

        elif profit > 1.00 * lot_scale:

            return "▲  SLIGHTLY AHEAD", "#3498db"

        elif profit >= -2.00 * lot_scale:

            return "●  ON TRACK", "#2980b9"

        elif profit >= -3.00 * lot_scale:

            return "▼  SLIGHTLY BEHIND", "#f39c12"

        elif profit >= -5.00 * lot_scale:

            return "▼  SEVERELY BEHIND", "#e67e22"

        else:

            return "▼▼ CRITICALLY BEHIND", "#e74c3c"



    def _get_customer_local_tz(self):

        return datetime.now().astimezone().tzinfo



    def _format_bar_time(self, epoch_ts):

        dt_utc = datetime.fromtimestamp(int(epoch_ts), tz=timezone.utc)

        local_dt = dt_utc.astimezone(self._get_customer_local_tz())

        return local_dt.strftime("%H:%M")



    def _format_bar_time_long(self, epoch_ts):

        dt_utc = datetime.fromtimestamp(int(epoch_ts), tz=timezone.utc)

        local_dt = dt_utc.astimezone(self._get_customer_local_tz())

        return local_dt.strftime("%m-%d %H:%M")



    # ============================================================

    # Chart zoom & focus helpers

    # ============================================================

    def _get_chart_bars(self, tf, zoom):

        base = BASE_VISIBLE_BARS.get(tf, 96)

        max_b = MAX_BARS_FOR_TF.get(tf, 96)

        visible = int(round(base / max(zoom, 0.001)))

        visible = max(MIN_VISIBLE_BARS, min(max_b, visible))

        return visible, max_b



    def _chart_zoom_limits(self, tf):

        base = BASE_VISIBLE_BARS.get(tf, 96)

        max_b = MAX_BARS_FOR_TF.get(tf, 96)

        min_zoom = base / max_b

        max_zoom = base / MIN_VISIBLE_BARS

        return min_zoom, max_zoom



    def _update_chart_borders(self):

        """Highlight the focused chart with a distinct border color."""

        for t_str, rw in self.order_ui_rows.items():

            cf = rw.get("chart_frame")

            if cf and cf.winfo_exists():

                try:

                    if t_str == self._focused_chart_ticket:

                        cf.configure(border_color="#f1c40f", border_width=2)

                    else:

                        cf.configure(border_color="#2980b9", border_width=1)

                except Exception:

                    pass



    def _zoom_in_chart(self, ticket):

        ticket = str(ticket)

        rw = self.order_ui_rows.get(ticket)

        if not rw:

            return

        tf = rw.get("timeframe", CHART_DEFAULT_TF)

        _, max_zoom = self._chart_zoom_limits(tf)

        current = rw.get("chart_zoom", 1.0)



        new_zoom = current * ZOOM_STEP

        if new_zoom > max_zoom * (1.0 - ZOOM_SNAP_FRACTION):

            new_zoom = max_zoom

        new_zoom = min(max_zoom, new_zoom)



        if abs(new_zoom - current) < 1e-6:

            return

        rw["chart_zoom"] = new_zoom

        visible, max_b = self._get_chart_bars(tf, new_zoom)

        rw["chart_offset"] = min(rw.get("chart_offset", 0), max(0, max_b - visible))

        self._draw_candle_chart(ticket)



    def _zoom_out_chart(self, ticket):

        ticket = str(ticket)

        rw = self.order_ui_rows.get(ticket)

        if not rw:

            return

        tf = rw.get("timeframe", CHART_DEFAULT_TF)

        min_zoom, _ = self._chart_zoom_limits(tf)

        current = rw.get("chart_zoom", 1.0)



        new_zoom = current / ZOOM_STEP

        if new_zoom < min_zoom * (1.0 + ZOOM_SNAP_FRACTION):

            new_zoom = min_zoom

        new_zoom = max(min_zoom, new_zoom)



        if abs(new_zoom - current) < 1e-6:

            return

        rw["chart_zoom"] = new_zoom

        visible, max_b = self._get_chart_bars(tf, new_zoom)

        rw["chart_offset"] = min(rw.get("chart_offset", 0), max(0, max_b - visible))

        self._draw_candle_chart(ticket)



    def _on_chart_wheel(self, event, ticket):

        """Per-canvas mousewheel handler — zooms only the currently focused chart."""

        ticket = str(ticket)

        if self._focused_chart_ticket != ticket:

            return "break"



        rw = self.order_ui_rows.get(ticket)

        if not rw:

            return "break"

        if event.delta > 0:

            self._zoom_in_chart(ticket)

        elif event.delta < 0:

            self._zoom_out_chart(ticket)

        return "break"



    def toggle_order_chart(self, ticket):

        ticket = str(ticket)

        if ticket in self._expanded_tickets:

            self._expanded_tickets.remove(ticket)

            if self._focused_chart_ticket == ticket:

                self._focused_chart_ticket = None

                self._update_chart_borders()

            rw = self.order_ui_rows.get(ticket)

            if rw and rw.get("chart_frame"):

                try:

                    rw["chart_frame"].grid_forget()

                except Exception:

                    pass

            self.append_log_scroll_safe(f"[{datetime.now().strftime('%H:%M:%S')} {get_user_tz_abbr()}] [CHART] Closed chart for ticket {ticket}\n")

        else:

            if len(self._expanded_tickets) >= MAX_OPEN_CHARTS:

                self.append_log_scroll_safe(f"[{datetime.now().strftime('%H:%M:%S')} {get_user_tz_abbr()}] [CHART] Max {MAX_OPEN_CHARTS} charts open. Close one before opening another.\n")

                return

            self._expanded_tickets.append(ticket)

            # Do NOT auto-focus on open — focus is granted only by an explicit click.

            self.append_log_scroll_safe(f"[{datetime.now().strftime('%H:%M:%S')} {get_user_tz_abbr()}] [CHART] Opened chart for ticket {ticket} ({len(self._expanded_tickets)}/{MAX_OPEN_CHARTS} open)\n")

        try:

            daily_pl = self.fetch_daily_realized_profit()

            total_pl = self.fetch_lifetime_realized_profit()

            self.render_orders_flicker_free(self.cached_positions, daily_pl, total_pl)

        except Exception as e:

            self._log_exc("toggle_order_chart", e)



    def set_chart_timeframe(self, ticket, tf):

        ticket = str(ticket)

        rw = self.order_ui_rows.get(ticket)

        if not rw:

            return

        rw["timeframe"] = tf

        rw["chart_offset"] = 0

        min_z, max_z = self._chart_zoom_limits(tf)

        current_zoom = rw.get("chart_zoom", 1.0)

        rw["chart_zoom"] = max(min_z, min(max_z, current_zoom))

        try:

            if rw.get("chart_tf_btn_1m"):

                rw["chart_tf_btn_1m"].configure(fg_color="#2980b9" if tf == "1m" else "#34495e")

            if rw.get("chart_tf_btn_5m"):

                rw["chart_tf_btn_5m"].configure(fg_color="#2980b9" if tf == "5m" else "#34495e")

            if rw.get("chart_tf_btn_15m"):

                rw["chart_tf_btn_15m"].configure(fg_color="#2980b9" if tf == "15m" else "#34495e")

            if rw.get("chart_tf_btn_30m"):

                rw["chart_tf_btn_30m"].configure(fg_color="#2980b9" if tf == "30m" else "#34495e")

            if rw.get("chart_tf_btn_1h"):

                rw["chart_tf_btn_1h"].configure(fg_color="#2980b9" if tf == "1h" else "#34495e")

        except Exception:

            pass

        self._draw_candle_chart(ticket)



    def _on_chart_configure(self, event, ticket):

        if event.width < 80 or event.height < 60:

            return

        rw = self.order_ui_rows.get(ticket)

        if not rw:

            return

        if rw.get("_last_cfg_size") == (event.width, event.height):

            return

        rw["_last_cfg_size"] = (event.width, event.height)

        self._draw_candle_chart(ticket)



    def _on_chart_press(self, event, ticket):

        rw = self.order_ui_rows.get(ticket)

        if not rw:

            return

        rw["drag_start_x"] = event.x

        rw["drag_start_offset"] = rw.get("chart_offset", 0)



    def _on_chart_drag(self, event, ticket):

        rw = self.order_ui_rows.get(ticket)

        if not rw or rw.get("drag_start_x") is None:

            return

        canvas = rw.get("chart_canvas")

        if not canvas:

            return

        dx = event.x - rw["drag_start_x"]

        canvas_w = canvas.winfo_width()

        tf = rw.get("timeframe", CHART_DEFAULT_TF)



        if tf == "1m":

            max_bars = 5040

        elif tf == "5m":

            max_bars = 1008

        elif tf == "15m":

            max_bars = 336

        elif tf == "30m":

            max_bars = 168

        else:

            max_bars = 84



        zoom = rw.get("chart_zoom", 1.0)

        visible_bars, _ = self._get_chart_bars(tf, zoom)



        left_margin = 68

        right_margin = 14

        plot_w = max(10, canvas_w - left_margin - right_margin)

        slot_w = plot_w / visible_bars



        bars_dragged = int(dx / slot_w)

        new_offset = rw["drag_start_offset"] + bars_dragged



        max_offset = max_bars - visible_bars

        new_offset = max(0, min(new_offset, max_offset))



        if new_offset != rw.get("chart_offset", 0):

            rw["chart_offset"] = new_offset

            self._draw_candle_chart(ticket)



    def _on_chart_release(self, event, ticket):

        rw = self.order_ui_rows.get(ticket)

        if rw:

            rw["drag_start_x"] = None



    def _create_chart_frame(self, ticket, rw):

        parent = self.orders_frame

        cf = ctk.CTkFrame(parent, fg_color="#161616", corner_radius=6, border_width=1, border_color="#2980b9")



        header = ctk.CTkFrame(cf, fg_color="transparent")

        header.pack(fill="x", padx=6, pady=(2, 0))



        tf = rw.get("timeframe", CHART_DEFAULT_TF)



        btn_1m = self._apply_3d_button_feel(

            ctk.CTkButton(

                header, text="1m", width=45, height=24,

                font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),

                fg_color="#2980b9" if tf == "1m" else "#34495e",

                hover_color="#1f618d",

                command=lambda t=ticket: self.set_chart_timeframe(t, "1m"),

            )

        )

        btn_1m.pack(side="left", padx=2)



        btn_5m = self._apply_3d_button_feel(

            ctk.CTkButton(

                header, text="5m", width=45, height=24,

                font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),

                fg_color="#2980b9" if tf == "5m" else "#34495e",

                hover_color="#1f618d",

                command=lambda t=ticket: self.set_chart_timeframe(t, "5m"),

            )

        )

        btn_5m.pack(side="left", padx=2)



        btn_15m = self._apply_3d_button_feel(

            ctk.CTkButton(

                header, text="15m", width=45, height=24,

                font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),

                fg_color="#2980b9" if tf == "15m" else "#34495e",

                hover_color="#1f618d",

                command=lambda t=ticket: self.set_chart_timeframe(t, "15m"),

            )

        )

        btn_15m.pack(side="left", padx=2)



        btn_30m = self._apply_3d_button_feel(

            ctk.CTkButton(

                header, text="30m", width=45, height=24,

                font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),

                fg_color="#2980b9" if tf == "30m" else "#34495e",

                hover_color="#1f618d",

                command=lambda t=ticket: self.set_chart_timeframe(t, "30m"),

            )

        )

        btn_30m.pack(side="left", padx=2)



        btn_1h = self._apply_3d_button_feel(

            ctk.CTkButton(

                header, text="1h", width=45, height=24,

                font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),

                fg_color="#2980b9" if tf == "1h" else "#34495e",

                hover_color="#1f618d",

                command=lambda t=ticket: self.set_chart_timeframe(t, "1h"),

            )

        )

        btn_1h.pack(side="left", padx=2)



        canvas = tk.Canvas(cf, bg="#161616", highlightthickness=0, height=200, cursor="fleur")

        canvas.pack(fill="both", expand=True, padx=6, pady=(0, 4))



        rw["chart_frame"] = cf

        rw["chart_canvas"] = canvas

        rw["chart_tf_btn_1m"] = btn_1m

        rw["chart_tf_btn_5m"] = btn_5m

        rw["chart_tf_btn_15m"] = btn_15m

        rw["chart_tf_btn_30m"] = btn_30m

        rw["chart_tf_btn_1h"] = btn_1h

        rw["_last_cfg_size"] = None

        rw["chart_offset"] = 0

        rw["chart_zoom"] = 1.0



        canvas.bind("<Configure>", lambda e, t=ticket: self._on_chart_configure(e, t))

        canvas.bind("<ButtonPress-1>", lambda e, t=ticket: self._on_chart_press(e, t))

        canvas.bind("<B1-Motion>", lambda e, t=ticket: self._on_chart_drag(e, t))

        canvas.bind("<ButtonRelease-1>", lambda e, t=ticket: self._on_chart_release(e, t))

        canvas.bind("<MouseWheel>", lambda e, t=ticket: self._on_chart_wheel(e, t))



    def _draw_candle_chart(self, ticket, rates_all=None):

        rw = self.order_ui_rows.get(ticket)

        if not rw:

            return

        canvas = rw.get("chart_canvas")

        if not canvas or not canvas.winfo_exists():

            return



        # If the caller supplied pre-fetched data (background thread), use it.

        # Otherwise, the caller is asking us to fetch synchronously on the main thread.

        if rates_all is not None:

            pass

        else:

            if not MT5_AVAILABLE:

                canvas.delete("all")

                canvas.create_text(canvas.winfo_width() // 2, canvas.winfo_height() // 2, text="MT5 not available", fill="#e74c3c", font=("Consolas", 11))

                return

            symbol = rw.get("symbol_text", "")

            tf_now = rw.get("timeframe", CHART_DEFAULT_TF)

            tf_map = {

                "1m": mt5.TIMEFRAME_M1,

                "5m": mt5.TIMEFRAME_M5,

                "15m": mt5.TIMEFRAME_M15,

                "30m": mt5.TIMEFRAME_M30,

                "1h": mt5.TIMEFRAME_H1,

            }

            zoom = rw.get("chart_zoom", 1.0)

            _, max_bars = self._get_chart_bars(tf_now, zoom)

            mt5_tf = tf_map.get(tf_now, mt5.TIMEFRAME_M30)

            try:

                rates_all = mt5.copy_rates_from_pos(symbol, mt5_tf, 0, max_bars)

            except Exception:

                rates_all = None



        canvas.delete("all")

        w = canvas.winfo_width()

        h = canvas.winfo_height()

        if w < 80 or h < 60:

            return



        symbol = rw.get("symbol_text", "")

        tf = rw.get("timeframe", CHART_DEFAULT_TF)

        zoom = rw.get("chart_zoom", 1.0)

        visible_bars, max_bars = self._get_chart_bars(tf, zoom)



        if not MT5_AVAILABLE:

            canvas.create_text(w // 2, h // 2, text="MT5 not available", fill="#e74c3c", font=("Consolas", 11))

            return



        if rates_all is None or len(rates_all) == 0:

            canvas.create_text(w // 2, h // 2, text=f"No candle data for {symbol}", fill="#e74c3c", font=("Consolas", 11))

            return



        offset = rw.get("chart_offset", 0)

        end_idx = len(rates_all) - offset

        start_idx = max(0, end_idx - visible_bars)



        rates = rates_all[start_idx:end_idx]



        if len(rates) == 0:

            return



        n = len(rates)

        left_margin = 68

        right_margin = 14

        top_margin = 24

        bottom_margin = 20

        plot_w = max(10, w - left_margin - right_margin)

        plot_h = max(10, h - top_margin - bottom_margin)

        slot_w = plot_w / n

        candle_w = max(1.5, slot_w * 0.65)



        price_max = max(r["high"] for r in rates)

        price_min = min(r["low"] for r in rates)

        pad = (price_max - price_min) * 0.08 or 0.0001

        price_max += pad

        price_min -= pad

        price_range = price_max - price_min or 0.0001



        def y_for(p):

            return top_margin + (price_max - p) / price_range * plot_h



        for i in range(5):

            p = price_min + (price_range * i / 4)

            y = y_for(p)

            canvas.create_line(left_margin, y, w - right_margin, y, fill="#2a2a2a")

            digits = 5 if p < 10 else (3 if p > 100 else 4)

            canvas.create_text(left_margin - 6, y, text=f"{p:.{digits}f}", anchor="e", fill="#7f8c8d", font=("Consolas", 8))



        if rw.get("chart_mode", "candlestick") == "line":

            line_pts = []

            for i, r in enumerate(rates):

                cx = left_margin + i * slot_w + slot_w / 2

                cy = y_for(r["close"])

                line_pts.extend([cx, cy])

            if len(line_pts) >= 4:

                last_c = rates[-1]["close"]

                first_c = rates[0]["close"]

                lcol = "#2ecc71" if last_c >= first_c else "#e74c3c"

                canvas.create_line(*line_pts, fill=lcol, width=2, smooth=False)

        else:

          for i, r in enumerate(rates):

            cx = left_margin + i * slot_w + slot_w / 2

            o, c, hi, lo = r["open"], r["close"], r["high"], r["low"]

            color = "#2ecc71" if c >= o else "#e74c3c"

            y_hi, y_lo, y_o, y_c = y_for(hi), y_for(lo), y_for(o), y_for(c)

            canvas.create_line(cx, y_hi, cx, y_lo, fill=color, width=1)

            body_top = min(y_o, y_c)

            body_bot = max(y_o, y_c)

            if body_bot - body_top < 1:

                body_bot = body_top + 1

            canvas.create_rectangle(cx - candle_w / 2, body_top, cx + candle_w / 2, body_bot, fill=color, outline=color)



        step = max(1, n // 4)

        for i in range(0, n, step):

            cx = left_margin + i * slot_w + slot_w / 2

            try:

                t_str = self._format_bar_time(rates[i]["time"])

            except Exception:

                t_str = ""

            canvas.create_text(cx, h - 4, text=t_str, anchor="s", fill="#7f8c8d", font=("Consolas", 8))



        open_price = rw.get("open_price", 0.0)

        if open_price > 0 and price_min <= open_price <= price_max:

            y_open = y_for(open_price)

            canvas.create_line(left_margin, y_open, w - right_margin, y_open, fill="#ffffff", dash=(4, 4), width=1)

            canvas.create_text(w - right_margin - 2, y_open + 8, text=f"OPEN: {open_price:.5f}", anchor="e", fill="#ffffff", font=("Consolas", 8, "bold"))



        last_close = float(rates[-1]["close"])

        y_last = y_for(last_close)

        canvas.create_line(left_margin, y_last, w - right_margin, y_last, fill="#f1c40f", dash=(3, 2))

        canvas.create_text(w - right_margin - 2, y_last - 8, text=f"{last_close:.5f}", anchor="e", fill="#f1c40f", font=("Consolas", 8, "bold"))



    def render_orders_flicker_free(self, positions, daily_pl=0.0, total_pl=0.0):

        if self._current_tab != "Live Orders & Account" or self._current_inner_tab != "Active Orders":

            return



        current_tickets = {str(pos.ticket) for pos in positions}

        total_open_profit = 0.0



        stale = [t for t in self.order_ui_rows.keys() if t not in current_tickets and t != "NO_POS"]

        for s in stale:

            rw = self.order_ui_rows[s]

            if rw.get("chart_frame"):

                try:

                    rw["chart_frame"].destroy()

                except Exception:

                    pass

            if s in self._expanded_tickets:

                self._expanded_tickets.remove(s)

            for w in rw["widgets"]:

                try:

                    w.destroy()

                except Exception:

                    pass

            del self.order_ui_rows[s]



        if not positions:

            if "NO_POS" not in self.order_ui_rows:

                lbl = ctk.CTkLabel(self.orders_frame, text="No active open orders found in MetaTrader 5 terminal.", font=ctk.CTkFont(family="Consolas", size=13), text_color="#f1c40f")

                lbl.grid(row=1, column=0, columnspan=10, padx=15, pady=15, sticky="w")

                self.order_ui_rows["NO_POS"] = {"widgets": [lbl]}

            self.total_profit_summary_label.configure(text="Open Profits: $0.00", text_color="#2ecc71")

            self.daily_profit_label.configure(text=f"Daily P/L: ${daily_pl:.2f}", text_color=("#2ecc71" if daily_pl >= 0 else "#e74c3c"))

            self.total_lifetime_profit_label.configure(text=f"Total Profit (All-Time): ${total_pl:.2f}", text_color=("#3498db" if total_pl >= 0 else "#e74c3c"))

            return



        if "NO_POS" in self.order_ui_rows:

            for w in self.order_ui_rows["NO_POS"]["widgets"]:

                try:

                    w.destroy()

                except Exception:

                    pass

            del self.order_ui_rows["NO_POS"]



        visual_row = 1

        for pos in positions:

            ticket = str(pos.ticket)

            total_open_profit += float(pos.profit)

            symbol = str(pos.symbol)

            pos_type = "BUY" if pos.type == 0 else "SELL"

            volume = f"{pos.volume:.2f}"



            open_dt = datetime.fromtimestamp(pos.time, timezone.utc)



            server_time_now = 0

            try:

                if MT5_AVAILABLE:

                    tick = mt5.symbol_info_tick(pos.symbol)

                    if tick:

                        server_time_now = tick.time

            except Exception:

                pass

            if not server_time_now:

                server_time_now = int(time.time())



            elapsed_secs = max(0, int(server_time_now - int(pos.time)))

            hrs, rem = divmod(elapsed_secs, 3600)

            mins, secs = divmod(rem, 60)

            elapsed_str = f"{hrs}h {mins}m {secs}s"



            status_text, status_color = self.classify_position_performance(pos, elapsed_secs)

            profit_str = f"{pos.profit:.2f}"

            p_color = "#2ecc71" if pos.profit >= 0 else "#e74c3c"



            if ticket in self.order_ui_rows:

                rw = self.order_ui_rows[ticket]

                self._safe_configure(rw["elapsed"], text=elapsed_str)

                self._safe_configure(rw["status"], text=status_text, text_color=status_color)

                self._safe_configure(rw["profit"], text=profit_str, text_color=p_color)

                rw["open_price"] = float(pos.price_open)

                if rw.get("chart_btn"):

                    is_open = ticket in self._expanded_tickets

                    self._safe_configure(

                        rw["chart_btn"],

                        text="📉" if is_open else "📊",

                        fg_color="#8e44ad" if is_open else "#34495e",

                        hover_color="#732d91" if is_open else "#2c3e50",

                    )

                    if rw.get("close_btn"):

                        self._safe_configure(

                            rw["close_btn"],

                            state="disabled" if is_open else "normal",

                            fg_color="#555555" if is_open else "#c0392b",

                            hover_color="#444444" if is_open else "#962d22"

                        )

                for cid, wgt in enumerate(rw["widgets"]):

                    try:

                        wgt.grid(row=visual_row, column=cid, padx=4, pady=2, sticky="w")

                    except Exception:

                        pass

            else:

                w_ticket = ctk.CTkLabel(self.orders_frame, text=ticket, font=ctk.CTkFont(family="Consolas", size=12), width=80, anchor="w")

                w_symbol = ctk.CTkLabel(self.orders_frame, text=symbol, font=ctk.CTkFont(family="Consolas", size=12, weight="bold"), width=80, anchor="w")

                w_type = ctk.CTkLabel(self.orders_frame, text=pos_type, font=ctk.CTkFont(family="Consolas", size=12, weight="bold"), width=60, anchor="w")

                w_vol = ctk.CTkLabel(self.orders_frame, text=volume, font=ctk.CTkFont(family="Consolas", size=12), width=60, anchor="w")

                w_time = ctk.CTkLabel(self.orders_frame, text=open_dt.strftime("%Y-%m-%d %H:%M"), font=ctk.CTkFont(family="Consolas", size=12), width=130, anchor="w")

                w_elapsed = ctk.CTkLabel(self.orders_frame, text=elapsed_str, font=ctk.CTkFont(family="Consolas", size=12), text_color="#3498db", width=95, anchor="w")

                w_status = ctk.CTkLabel(self.orders_frame, text=status_text, font=ctk.CTkFont(family="Consolas", size=12, weight="bold"), text_color=status_color, width=215, anchor="w")



                b_chart = self._apply_3d_button_feel(

                    ctk.CTkButton(

                        self.orders_frame, text="📊", width=30, height=24,

                        font=ctk.CTkFont(size=11),

                        fg_color="#34495e", hover_color="#2c3e50",

                        command=lambda t=ticket: self.toggle_order_chart(t),

                    )

                )



                w_prof = ctk.CTkLabel(self.orders_frame, text=profit_str, font=ctk.CTkFont(family="Consolas", size=13, weight="bold"), text_color=p_color, width=85, anchor="w")



                b_cls = self._apply_3d_button_feel(

                    ctk.CTkButton(

                        self.orders_frame, text="X", width=36, height=24,

                        fg_color="#c0392b", hover_color="#962d22",

                        command=lambda t=ticket: self.close_order_action(t),

                    ),

                    normal_border="#fca5a5", pressed_border="#fef2f2"

                )



                widgets = [w_ticket, w_symbol, w_type, w_vol, w_time, w_elapsed, w_status, b_chart, w_prof, b_cls]

                for cid, wgt in enumerate(widgets):

                    wgt.grid(row=visual_row, column=cid, padx=4, pady=2, sticky="w")



                self.order_ui_rows[ticket] = {

                    "widgets": widgets,

                    "ticket": w_ticket, "symbol": w_symbol, "type": w_type, "volume": w_vol,

                    "time": w_time, "elapsed": w_elapsed, "status": w_status, "profit": w_prof,

                    "chart_btn": b_chart, "close_btn": b_cls, "symbol_text": symbol,

                    "open_price": float(pos.price_open),

                    "chart_frame": None, "chart_canvas": None,

                    "chart_tf_btn_1m": None, "chart_tf_btn_5m": None, "chart_tf_btn_15m": None,

                    "chart_tf_btn_30m": None, "chart_tf_btn_1h": None,

                    "timeframe": CHART_DEFAULT_TF, "_last_cfg_size": None,

                    "chart_offset": 0, "chart_zoom": 1.0,

                    "drag_start_x": None, "drag_start_offset": 0

                }



            rw = self.order_ui_rows[ticket]

            if ticket in self._expanded_tickets:

                was_visible = False

                if rw.get("chart_frame"):

                    try:

                        was_visible = bool(rw["chart_frame"].winfo_ismapped())

                    except Exception:

                        was_visible = False

                    if not was_visible:

                        self.after(60, lambda t=ticket: self._draw_candle_chart(t))

                else:

                    self._create_chart_frame(ticket, rw)

                    self.after(60, lambda t=ticket: self._draw_candle_chart(t))

                try:

                    rw["chart_frame"].grid(

                        row=visual_row + 1, column=0, columnspan=10,

                        padx=4, pady=(2, 4), sticky="ew",

                    )

                except Exception:

                    pass

                visual_row += 2

            else:

                if rw.get("chart_frame"):

                    try:

                        rw["chart_frame"].grid_forget()

                    except Exception:

                        pass

                visual_row += 1



        open_profit_color = "#2ecc71" if total_open_profit >= 0 else "#e74c3c"

        self.total_profit_summary_label.configure(text=f"Open Profits: ${total_open_profit:.2f}", text_color=open_profit_color)

        self.daily_profit_label.configure(text=f"Daily P/L: ${daily_pl:.2f}", text_color=("#2ecc71" if daily_pl >= 0 else "#e74c3c"))

        self.total_lifetime_profit_label.configure(text=f"Total Profit (All-Time): ${total_pl:.2f}", text_color=("#3498db" if total_pl >= 0 else "#e74c3c"))



    def append_log_scroll_safe(self, text):

        import time

        try:

            if time.monotonic() < getattr(self, "_startup_log_mute_until", 0.0):

                return

            self.log_textbox.insert("end", text)

            if self._current_tab == "Activity & Chat":

                self._live_log_line_count += text.count('\n')

                if self._live_log_line_count > LIVE_LOG_MAX_LINES:

                    try:

                        current_content = self.log_textbox.get("0.0", "end")

                        lines = current_content.splitlines(keepends=True)

                        if len(lines) > LIVE_LOG_ARCHIVE_BATCH:

                            archived_chunk = "".join(lines[:LIVE_LOG_ARCHIVE_BATCH])

                            self._archive_log_chunk(archived_chunk)

                            self.log_textbox.delete("0.0", f"{LIVE_LOG_ARCHIVE_BATCH}.0")

                            self._live_log_line_count = len(lines) - LIVE_LOG_ARCHIVE_BATCH

                    except Exception:

                        pass

                self.log_textbox.see("end")

        except Exception:

            pass



    def clear_stream(self):

        try:

            if not hasattr(self, "log_textbox") or not self.log_textbox.winfo_exists():

                return

            current_content = self.log_textbox.get("0.0", "end")

            if current_content.strip():

                if hasattr(self, "_archive_activity_text"):

                    self._archive_activity_text(current_content)

                elif hasattr(self, "_archive_log_chunk"):

                    self._archive_log_chunk(current_content)

            self.log_textbox.configure(state="normal")

            self.log_textbox.delete("0.0", "end")

            self.log_textbox.insert("0.0", "[INIT] FleetUnit multi-agent telemetry online.\n")

            self._live_log_line_count = 1

            self.log_textbox.see("end")

        except Exception:

            pass

    def open_ai_watchlist_window(self):

        # Open the window immediately with whatever proposals are already available, then refresh in background

        cached_top_5 = []

        try:

            from forex_grok_bot import read_worker_proposals, rank_top_5_proposals

            db_path = globals().get("DB_FILE", "trade_memory.db")

            existing = read_worker_proposals(db_path=db_path, limit=50)

            cached_top_5 = rank_top_5_proposals(existing)[:5]

        except Exception:

            cached_top_5 = []



        self._show_ai_watchlist_charts_window(cached_top_5)

        threading.Thread(target=self._ai_watchlist_fetch_worker, daemon=True).start()



    def _ai_watchlist_fetch_worker(self):

        top_5 = []

        try:

            from forex_grok_bot import run_scan, read_worker_proposals, rank_top_5_proposals

            db_path = globals().get("DB_FILE", "trade_memory.db")

            top_5 = run_scan(min_confidence=0.60, db_path=db_path, refresh_db=False)

            if not top_5:

                existing = read_worker_proposals(db_path=db_path, limit=50)

                top_5 = rank_top_5_proposals(existing)

        except Exception as e:

            if hasattr(self, "_log_exc"):

                self._ui(self._log_exc, "_ai_watchlist_fetch_worker", e)



        self._ui(self._show_ai_watchlist_charts_window, (top_5 or [])[:5])



    def _show_ai_watchlist_charts_window(self, top_5):

        win_attr = "_ai_watchlist_win"

        prev = getattr(self, win_attr, None)

        if prev is not None:

            try:

                if prev.winfo_exists():

                    prev.destroy()

            except Exception:

                pass



        win = ctk.CTkToplevel(self)

        win.title("AI Watchlist")

        win.geometry("1020x680")



        def _bring_wl_to_front(w=win):

            try:

                if w and w.winfo_exists():

                    w.transient(self)

                    w.deiconify()

                    w.lift()

                    w.attributes("-topmost", True)

                    w.focus_force()

                    w.after(150, lambda win_ref=w: win_ref.winfo_exists() and win_ref.attributes("-topmost", False))

            except Exception:

                pass

        _bring_wl_to_front()

        setattr(self, win_attr, win)



        header = ctk.CTkFrame(win, fg_color="#16202a")

        header.pack(fill="x", padx=10, pady=(10, 6))

        ctk.CTkLabel(

            header,

            text="AI Watchlist",

            font=ctk.CTkFont(family="Consolas", size=14, weight="bold"),

            text_color="#2ecc71",

        ).pack(side="left", padx=10, pady=6)

        ctk.CTkButton(

            header,

            text="Refresh",

            width=120,

            height=28,

            command=lambda: threading.Thread(target=self._ai_watchlist_fetch_worker, daemon=True).start(),

        ).pack(side="right", padx=10, pady=6)



        scroll_container = ctk.CTkScrollableFrame(win, fg_color="#0f1720")

        scroll_container.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        try:

            sb = getattr(scroll_container, "_scrollbar", None)

            if sb is not None:

                if sb.winfo_manager() == "grid":

                    sb.grid_remove()

                elif sb.winfo_manager() == "pack":

                    sb.pack_forget()

        except Exception:

            pass



        def _on_wl_scroll_wheel(event):

            try:

                p_canvas = getattr(scroll_container, "_parent_canvas", None)

                if p_canvas is not None and p_canvas.winfo_exists():

                    delta = getattr(event, "delta", 0)

                    if delta:

                        p_canvas.yview_scroll(int(-1 * (delta / 120)) or (-1 if delta > 0 else 1), "units")

                    elif getattr(event, "num", None) == 4:

                        p_canvas.yview_scroll(-1, "units")

                    elif getattr(event, "num", None) == 5:

                        p_canvas.yview_scroll(1, "units")

            except Exception:

                pass



        try:

            scroll_container.bind_all("<MouseWheel>", _on_wl_scroll_wheel, add="+")

            win.bind("<Destroy>", lambda e: scroll_container.unbind_all("<MouseWheel>"), add="+")

        except Exception:

            pass



        items = (top_5 or [])[:5]

        if not items:

            # Render 5 blank canvases when no pairs are available

            for slot_idx in range(1, 6):

                card = ctk.CTkFrame(scroll_container, fg_color="#1b2631", border_width=1, border_color="#2c3e50")

                card.pack(fill="x", padx=4, pady=6)

                top_bar = ctk.CTkFrame(card, fg_color="transparent")

                top_bar.pack(fill="x", padx=8, pady=(6, 2))

                ctk.CTkLabel(

                    top_bar,

                    text=f"#{slot_idx} No Signal",

                    font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),

                    text_color="#7f8c8d",

                ).pack(side="left")

                canvas = ctk.CTkCanvas(card, height=230, bg="#101820", highlightthickness=0)

                canvas.pack(fill="x", padx=8, pady=(2, 8))

            return



        for idx, item in enumerate(items, start=1):

            pair = str(item.get("pair", "")).strip().upper()

            bias = str(item.get("bias", "")).strip().upper()

            conf_pct = int(round(float(item.get("confidence_score", 0.0)) * 100))

            sl_pips = item.get("suggested_sl_pips", "")

            tp_pips = item.get("suggested_tp_pips", "")



            card = ctk.CTkFrame(scroll_container, fg_color="#1b2631", border_width=1, border_color="#2c3e50")

            card.pack(fill="x", padx=4, pady=6)



            top_bar = ctk.CTkFrame(card, fg_color="transparent")

            top_bar.pack(fill="x", padx=8, pady=(6, 2))

            ctk.CTkLabel(

                top_bar,

                text=f"#{idx} {pair}  |  {bias} ({conf_pct}%)  |  SL: {sl_pips}p / TP: {tp_pips}p",

                font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),

                text_color="#ecf0f1",

            ).pack(side="left")



            state = {{"tf": globals().get("CHART_DEFAULT_TF", "30m"), "zoom": 1.0, "offset": 0, "drag_x": None, "rates": []}}

            canvas = ctk.CTkCanvas(card, height=230, bg="#101820", highlightthickness=0)

            canvas.pack(fill="x", padx=8, pady=(2, 8))



            def _redraw(st=state, cv=canvas, p=pair, b=bias, cp=conf_pct):

                _ai_watchlist_render_candles_on_canvas(

                    cv,

                    st["rates"],

                    tf=st["tf"],

                    zoom=st["zoom"],

                    offset=st["offset"],

                    pair_label=p,

                    bias_label=b,

                    conf_pct=cp,

                )



            def _set_tf(new_tf, st=state, p=pair, r_fn=_redraw):

                st["tf"] = new_tf

                st["offset"] = 0

                st["rates"] = _fetch_pair_candles_for_watchlist(p, tf_str=new_tf)

                r_fn()



            for tf_opt in ("1m", "5m", "15m", "30m", "1h"):

                ctk.CTkButton(

                    top_bar,

                    text=tf_opt,

                    width=38,

                    height=22,

                    fg_color="#2980b9" if tf_opt == state["tf"] else "#34495e",

                    command=lambda t_val=tf_opt, fn=_set_tf: fn(t_val),

                ).pack(side="right", padx=2)



            def _on_wheel(ev, st=state, r_fn=_redraw):

                if getattr(ev, "delta", 0) > 0:

                    st["zoom"] = min(4.0, st["zoom"] * 1.15)

                else:

                    st["zoom"] = max(0.35, st["zoom"] / 1.15)

                r_fn()



            def _on_press(ev, st=state):

                st["drag_x"] = ev.x



            def _on_drag(ev, st=state, r_fn=_redraw):

                if st["drag_x"] is None:

                    return

                dx = ev.x - st["drag_x"]

                st["drag_x"] = ev.x

                st["offset"] = max(0, st["offset"] + int(round(dx / 12.0)))

                r_fn()



            canvas.bind("<Configure>", lambda ev, r_fn=_redraw: r_fn())

            canvas.bind("<MouseWheel>", _on_wheel)

            canvas.bind("<ButtonPress-1>", _on_press)

            canvas.bind("<B1-Motion>", _on_drag)



            state["rates"] = _fetch_pair_candles_for_watchlist(pair, tf_str=state["tf"])

            _redraw()















    def _collect_all_trade_profit_series(self):

        """Collect cumulative profit across all trade history (MT5 deals + SQLite fallback)."""

        entries = []

        try:

            cache = getattr(self, "_history_deals_cache", None) or []

            for d in cache:

                ts = getattr(d, "time", None)

                pnl = (

                    float(getattr(d, "profit", 0.0) or 0.0)

                    + float(getattr(d, "swap", 0.0) or 0.0)

                    + float(getattr(d, "commission", 0.0) or 0.0)

                )

                entries.append((float(ts or 0.0), pnl))

        except Exception:

            pass

        if not entries:

            try:

                conn = sqlite3.connect(DB_FILE, timeout=10.0)

                c = conn.cursor()

                tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]

                for tbl in ("closed_trades", "trade_history", "trade_memory"):

                    if tbl in tables:

                        cols = [d[1] for d in c.execute(f"PRAGMA table_info({tbl})").fetchall()]

                        pnl_col = next((col for col in ("profit", "pnl", "realized_pnl", "profit_usd") if col in cols), None)

                        if pnl_col:

                            rows = c.execute(f"SELECT rowid, {pnl_col} FROM {tbl} ORDER BY rowid ASC").fetchall()

                            for idx, r in enumerate(rows, 1):

                                entries.append((float(r[0] or idx), float(r[1] or 0.0)))

                            break

                conn.close()

            except Exception:

                pass

        cum = 0.0

        series = []

        for idx, (_, pnl) in enumerate(entries, 1):

            cum = round(cum + pnl, 2)

            series.append((idx, cum))

        return series



    def _init_order_history_profit_box(self):

        if not hasattr(self, "tab_history") or not self.tab_history.winfo_exists():

            return

        if hasattr(self, "history_profit_box") and self.history_profit_box.winfo_exists():

            return

        self._hist_profit_zoom = 1.0

        self._hist_profit_pan_frac = 0.0

        self._hist_profit_drag_x = None



        self.history_profit_box = ctk.CTkFrame(

            self.tab_history,

            fg_color="#0f172a",

            corner_radius=8,

            border_width=1,

            border_color="#334155",

            height=130,

        )

        try:

            mgr = self.history_frame.winfo_manager() if hasattr(self, "history_frame") and self.history_frame.winfo_exists() else ""

        except Exception:

            mgr = ""



        if mgr == "grid" and hasattr(self, "history_frame"):

            info = self.history_frame.grid_info()

            target_row = int(info.get("row", 1))

            target_col = int(info.get("column", 0))

            col_span = int(info.get("columnspan", 1))

            self.history_frame.grid_configure(row=target_row + 1)

            self.history_profit_box.grid(

                row=target_row,

                column=target_col,

                columnspan=col_span,

                sticky="ew",

                padx=10,

                pady=(4, 4),

            )

        else:

            if hasattr(self, "history_frame") and self.history_frame.winfo_exists() and self.history_frame.winfo_manager() == "pack":

                self.history_profit_box.pack(fill="x", padx=10, pady=(4, 4), before=self.history_frame)

            else:

                self.history_profit_box.pack(fill="x", padx=10, pady=(4, 4))

        self.history_profit_box.pack_propagate(False)



        top_bar = ctk.CTkFrame(self.history_profit_box, fg_color="transparent")

        top_bar.pack(fill="x", padx=8, pady=(4, 0))

        ctk.CTkLabel(

            top_bar,

            text="Profit History ($)",

            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),

            text_color="#e2e8f0",

        ).pack(side="left")



        self.history_profit_canvas = tk.Canvas(

            self.history_profit_box,

            bg="#090d16",

            highlightthickness=0,

            height=90,

        )

        self.history_profit_canvas.pack(fill="both", expand=True, padx=8, pady=(2, 6))

        self.history_profit_canvas.bind("<MouseWheel>", self._on_history_profit_wheel)

        self.history_profit_canvas.bind("<ButtonPress-1>", self._on_history_profit_press)

        self.history_profit_canvas.bind("<B1-Motion>", self._on_history_profit_drag)

        self.history_profit_canvas.bind("<Double-Button-1>", self._on_history_profit_reset)

        self.history_profit_canvas.bind("<Configure>", lambda e: self.redraw_history_profit_graph())

        self.redraw_history_profit_graph()



    def _on_history_profit_wheel(self, event):

        step = 1.25 if getattr(event, "delta", 0) > 0 else (1.0 / 1.25)

        self._hist_profit_zoom = max(1.0, min(25.0, getattr(self, "_hist_profit_zoom", 1.0) * step))

        self.redraw_history_profit_graph()



    def _on_history_profit_press(self, event):

        self._hist_profit_drag_x = event.x



    def _on_history_profit_drag(self, event):

        prev_x = getattr(self, "_hist_profit_drag_x", None)

        if prev_x is None:

            return

        dx = event.x - prev_x

        self._hist_profit_drag_x = event.x

        w = max(1, self.history_profit_canvas.winfo_width())

        cur = getattr(self, "_hist_profit_pan_frac", 0.0)

        self._hist_profit_pan_frac = max(0.0, min(1.0, cur - (dx / w)))

        self.redraw_history_profit_graph()



    def _on_history_profit_reset(self, event=None):

        self._hist_profit_zoom = 1.0

        self._hist_profit_pan_frac = 0.0

        self.redraw_history_profit_graph()



    def redraw_history_profit_graph(self):

        if not hasattr(self, "history_profit_canvas") or not self.history_profit_canvas.winfo_exists():

            return

        c = self.history_profit_canvas

        c.delete("all")

        w = max(120, c.winfo_width())

        h = max(48, c.winfo_height())

        pad_l, pad_r, pad_t, pad_b = 54, 10, 8, 16

        pw = max(20, w - pad_l - pad_r)

        ph = max(18, h - pad_t - pad_b)



        series = self._collect_all_trade_profit_series()

        if not series:

            c.create_text(w // 2, h // 2, text="No closed trade history yet", fill="#94a3b8", font=("Consolas", 10))

            return



        total_n = len(series)

        zoom = max(1.0, float(getattr(self, "_hist_profit_zoom", 1.0) or 1.0))

        vis_n = max(2, min(total_n, int(round(total_n / zoom))))

        max_start = max(0, total_n - vis_n)

        pan_frac = max(0.0, min(1.0, float(getattr(self, "_hist_profit_pan_frac", 0.0) or 0.0)))

        start_idx = int(round(pan_frac * max_start))

        window = series[start_idx:start_idx + vis_n]

        vals = [pt[1] for pt in window]



        lo_v = min(vals)

        hi_v = max(vals)

        if lo_v == hi_v:

            lo_v -= 1.0

            hi_v += 1.0

        pad = (hi_v - lo_v) * 0.1

        lo_v -= pad

        hi_v += pad



        if lo_v < 0.0 < hi_v:

            zy = pad_t + ph - ((0.0 - lo_v) / (hi_v - lo_v)) * ph

            c.create_line(pad_l, zy, pad_l + pw, zy, fill="#334155", dash=(2, 2))



        c.create_text(pad_l - 4, pad_t, text=f"${hi_v:+.2f}", anchor="ne", fill="#94a3b8", font=("Consolas", 8))

        c.create_text(pad_l - 4, pad_t + ph, text=f"${lo_v:+.2f}", anchor="se", fill="#94a3b8", font=("Consolas", 8))

        c.create_text(pad_l, h - 3, text=f"#{window[0][0]}", anchor="sw", fill="#64748b", font=("Consolas", 8))

        c.create_text(pad_l + pw, h - 3, text=f"#{window[-1][0]}", anchor="se", fill="#64748b", font=("Consolas", 8))



        coords = []

        m = len(window)

        for i, (_, v) in enumerate(window):

            px = pad_l if m == 1 else pad_l + (i / (m - 1)) * pw

            py = pad_t + ph - ((v - lo_v) / (hi_v - lo_v)) * ph

            coords.extend([px, py])

        if len(coords) >= 4:

            line_col = "#22c55e" if vals[-1] >= 0.0 else "#ef4444"

            c.create_line(*coords, fill=line_col, width=2)





    def open_support_message_window(self):

        win_attr = "_support_msg_win"

        existing = getattr(self, win_attr, None)

        if existing is not None and existing.winfo_exists():

            try:

                existing.deiconify()

                existing.lift()

                existing.attributes("-topmost", True)

                existing.focus_force()

                existing.after(150, lambda r=existing: r.winfo_exists() and r.attributes("-topmost", False))

                return

            except Exception:

                pass



        win = ctk.CTkToplevel(self)

        win.title("Send a Message")

        win.geometry("560x420")

        setattr(self, win_attr, win)



        try:

            win.transient(self)

            win.deiconify()

            win.lift()

            win.attributes("-topmost", True)

            win.focus_force()

            win.after(150, lambda r=win: r.winfo_exists() and r.attributes("-topmost", False))

        except Exception:

            pass



        ctk.CTkLabel(

            win,

            text="Send a Message",

            font=ctk.CTkFont(family="Consolas", size=14, weight="bold"),

        ).pack(anchor="w", padx=14, pady=(12, 6))



        ctk.CTkLabel(

            win,

            text="Subject",

            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),

        ).pack(anchor="w", padx=14, pady=(2, 2))



        subject_entry = ctk.CTkEntry(

            win,

            placeholder_text="Enter message subject...",

            height=32,

            font=ctk.CTkFont(family="Consolas", size=12),

        )

        subject_entry.pack(fill="x", padx=14, pady=(0, 8))

        subject_entry.focus_set()



        ctk.CTkLabel(

            win,

            text="Message",

            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),

        ).pack(anchor="w", padx=14, pady=(2, 2))



        message_box = ctk.CTkTextbox(

            win,

            height=190,

            font=ctk.CTkFont(family="Consolas", size=12),

        )

        message_box.pack(fill="both", expand=True, padx=14, pady=(0, 10))



        status_lbl = ctk.CTkLabel(

            win,

            text="",

            font=ctk.CTkFont(family="Consolas", size=11),

            text_color="#94a3b8",

        )

        status_lbl.pack(anchor="w", padx=14, pady=(0, 4))



        btn_row = ctk.CTkFrame(win, fg_color="transparent")

        btn_row.pack(fill="x", padx=14, pady=(0, 12))



        def _on_send():

            subj = (subject_entry.get() or "").strip()

            body = (message_box.get("1.0", "end") or "").strip()

            if not subj and not body:

                status_lbl.configure(text="Please enter a subject or message first.", text_color="#e74c3c")

                return

            status_lbl.configure(text="Sending to Gmail...", text_color="#3498db")

            threading.Thread(

                target=self._send_support_gmail,

                args=(subj or "FleetUnit Support Message", body, win, status_lbl),

                daemon=True,

            ).start()



        send_btn = self._apply_3d_button_feel(

            ctk.CTkButton(

                btn_row,

                text="Send",

                width=110,

                height=32,

                fg_color="#27ae60",

                hover_color="#1e8449",

                command=_on_send,

            )

        )

        send_btn.pack(side="right", padx=(6, 0))



        cancel_btn = self._apply_3d_button_feel(

            ctk.CTkButton(

                btn_row,

                text="Cancel",

                width=100,

                height=32,

                fg_color="#34495e",

                hover_color="#2c3e50",

                command=win.destroy,

            )

        )

        cancel_btn.pack(side="right")



    def _chat_prefs_path(self):

        from pathlib import Path

        import sys

        base = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent

        return base / "chat_prefs.json"



    def _generate_default_trader_name(self):

        import random

        return f"trader-{random.randint(100000, 999999)}"



    def _load_chat_nickname(self):

        try:

            p = self._chat_prefs_path()

            if p.is_file():

                data = json.loads(p.read_text(encoding="utf-8"))

                nick = str(data.get("nickname", "")).strip()

                if nick:

                    return nick[:24]

        except Exception:

            pass

        generated = self._generate_default_trader_name()

        self._save_chat_nickname(generated)

        return generated

    def _save_chat_nickname(self, nick):

        try:

            clean = (str(nick or "").strip() or "Trader")[:24]

            self._chat_prefs_path().write_text(json.dumps({"nickname": clean}), encoding="utf-8")

        except Exception:

            pass



    def _set_chat_nickname(self):

        if not hasattr(self, "_chat_nick_entry") or not self._chat_nick_entry.winfo_exists():

            return

        raw = self._chat_nick_entry.get().strip() or self._generate_default_trader_name()

        clean = raw[:24]

        self._save_chat_nickname(clean)

        self._chat_nick_entry.delete(0, "end")

        self._chat_nick_entry.insert(0, clean)



        btn = getattr(self, "_chat_nick_set_btn", None)

        status_lbl = getattr(self, "_chat_status_lbl", None)



        if status_lbl is not None and status_lbl.winfo_exists():

            status_lbl.configure(text=f"? Nickname updated to {clean}", text_color="#2ecc71")



        if btn is not None and btn.winfo_exists():

            prev_job = getattr(self, "_nick_set_anim_job", None)

            if prev_job is not None:

                try:

                    self.after_cancel(prev_job)

                except Exception:

                    pass

                self._nick_set_anim_job = None



            if not hasattr(self, "_nick_set_orig_style"):

                try:

                    self._nick_set_orig_style = {

                        "text": btn.cget("text"),

                        "width": btn.cget("width"),

                        "fg_color": btn.cget("fg_color"),

                        "hover_color": btn.cget("hover_color"),

                    }

                except Exception:

                    self._nick_set_orig_style = {

                        "text": "Set",

                        "width": 52,

                        "fg_color": "#2b5b84",

                        "hover_color": "#1f4566",

                    }



            orig = self._nick_set_orig_style

            frames = [

                ("✓ Set!", 74, "#2ecc71", "#27ae60", 120),

                ("✓ Saved", 78, "#27ae60", "#219653", 140),

                ("✓ Set!", 74, "#2ecc71", "#27ae60", 140),

                ("✓ Saved", 78, "#27ae60", "#219653", 1150),

            ]



            def _step(idx=0):

                if not btn.winfo_exists():

                    return

                if idx < len(frames):

                    lbl, w, fg, hov, delay = frames[idx]

                    try:

                        btn.configure(text=lbl, width=w, fg_color=fg, hover_color=hov)

                    except Exception:

                        pass

                    self._nick_set_anim_job = self.after(delay, lambda: _step(idx + 1))

                else:

                    try:

                        btn.configure(

                            text=orig.get("text", "Set"),

                            width=orig.get("width", 52),

                            fg_color=orig.get("fg_color", "#2b5b84"),

                            hover_color=orig.get("hover_color", "#1f4566"),

                        )

                    except Exception:

                        pass

                    if status_lbl is not None and status_lbl.winfo_exists():

                        try:

                            status_lbl.configure(text="Connected", text_color="#94a3b8")

                        except Exception:

                            pass

                    self._nick_set_anim_job = None



            _step(0)



    def _build_global_chat_tab(self, parent):

        import customtkinter as ctk

        import threading



        self._chat_last_ts = int(getattr(self, "_chat_last_ts", 0) or 0)

        self._chat_seen_ids = set(getattr(self, "_chat_seen_ids", set()))

        self._chat_polling_started = bool(getattr(self, "_chat_polling_started", False))



        top_bar = ctk.CTkFrame(parent, fg_color="transparent")

        top_bar.pack(fill="x", padx=12, pady=(10, 6))



        ctk.CTkLabel(top_bar, text="Global Chat", font=("Segoe UI", 15, "bold")).pack(side="left")



        self._chat_nick_set_btn = ctk.CTkButton(top_bar, text="Set", width=52, height=28, command=self._set_chat_nickname)

        self._chat_nick_set_btn.pack(side="right", padx=(4, 0))

        self._chat_nick_entry = ctk.CTkEntry(top_bar, width=130, placeholder_text="Nickname")

        self._chat_nick_entry.pack(side="right")

        self._chat_nick_entry.insert(0, self._load_chat_nickname())

        self._chat_nick_entry.bind("<Return>", lambda _e: (self._set_chat_nickname(), "break")[1])

        self._chat_nick_entry.bind("<FocusOut>", lambda _e: self._save_chat_nickname(self._chat_nick_entry.get()))

        ctk.CTkLabel(top_bar, text="Name:", font=("Segoe UI", 12)).pack(side="right", padx=(8, 4))



        self._chat_status_lbl = ctk.CTkLabel(parent, text="Connecting...", font=("Segoe UI", 11), text_color="#94a3b8")

        self._chat_status_lbl.pack(anchor="w", padx=14, pady=(0, 4))



        self._chat_log = ctk.CTkTextbox(parent, wrap="word", state="disabled", font=("Consolas", 12))

        self._chat_log.pack(fill="both", expand=True, padx=12, pady=(0, 8))



        input_row = ctk.CTkFrame(parent, fg_color="transparent")

        input_row.pack(fill="x", padx=12, pady=(0, 12))



        self._chat_input = ctk.CTkEntry(input_row, placeholder_text="Type a message to everyone...")

        self._chat_input.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self._chat_cmd_hint = ctk.CTkLabel(parent, text="/whisper /reply", font=("Segoe UI", 10), text_color="#888888")

        self._chat_cmd_hint.pack(anchor="w", padx=14, pady=(0, 4))

        self._chat_input.bind("<Return>", lambda _e: self._send_global_chat())



        self._chat_send_btn = ctk.CTkButton(input_row, text="Send", width=90, command=self._send_global_chat)

        self._chat_send_btn.pack(side="right")



        if not self._chat_polling_started:

            self._chat_polling_started = True

            threading.Thread(target=self._poll_global_chat_loop, daemon=True).start()



    def _append_chat_line(self, line, tag=None):

        if not hasattr(self, "_chat_log") or not self._chat_log.winfo_exists():

            return

        self._chat_log.configure(state="normal")

        tk_txt = getattr(self._chat_log, "_textbox", self._chat_log)

        if tag == "whisper":

            try:

                tk_txt.tag_config("whisper", foreground="#2ecc71")

            except Exception:

                pass

            start_idx = tk_txt.index("end-1c")

            self._chat_log.insert("end", line + "\n")

            end_idx = tk_txt.index("end-1c")

            try:

                tk_txt.tag_add("whisper", start_idx, end_idx)

            except Exception:

                pass

        else:

            self._chat_log.insert("end", line + "\n")

        self._chat_log.configure(state="disabled")

        self._chat_log.see("end")



    def _is_whisper_message(self, m):

        if not isinstance(m, dict):

            return False

        recipient = str(m.get("recipient") or "").strip()

        return bool(recipient or m.get("is_whisper"))



    def _current_chat_nick(self):

        try:

            if hasattr(self, "_chat_nick_entry") and self._chat_nick_entry.winfo_exists():

                val = self._chat_nick_entry.get().strip()

                if val:

                    return val

        except Exception:

            pass

        if hasattr(self, "_load_chat_nickname"):

            try:

                val = str(self._load_chat_nickname() or "").strip()

                if val:

                    return val

            except Exception:

                pass

        return "Trader"



    def _format_chat_message(self, m):

        from datetime import datetime

        ts = int(m.get("ts") or 0)

        sender = str(m.get("sender") or "Trader")

        recipient = str(m.get("recipient") or "").strip()

        body = str(m.get("text") or "")

        stamp = datetime.fromtimestamp(ts / 1000).strftime("%H:%M") if ts else ""

        prefix = f"[{stamp}] " if stamp else ""

        if recipient or m.get("is_whisper"):

            if recipient:

                return f"{prefix}{sender} {recipient}: {body}"

            return f"{prefix}{sender}: {body}"

        return f"{prefix}{sender}: {body}"





    def _parse_build_tuple(self, val):

        parts = [int(p) for p in re.findall(r"\d+", str(val or ""))]

        return tuple(parts)



    def _is_build_newer(self, remote_ver, local_ver=FLEET_BUILD):

        r_tup = self._parse_build_tuple(remote_ver)

        l_tup = self._parse_build_tuple(local_ver)

        if not r_tup or not l_tup:

            return str(remote_ver).strip() != str(local_ver).strip() and bool(str(remote_ver).strip())

        max_len = max(len(r_tup), len(l_tup))

        r_pad = r_tup + (0,) * (max_len - len(r_tup))

        l_pad = l_tup + (0,) * (max_len - len(l_tup))

        return r_pad > l_pad



    def _prompt_gui_update(self, latest, notes="", dl_url=""):

        import tkinter as tk

        from tkinter import ttk

        import webbrowser



        win = tk.Toplevel(self)

        win.title("FleetUnit Update Available")

        win.geometry("460x265")

        win.resizable(False, False)

        try:

            win.attributes("-topmost", True)

        except Exception:

            pass



        header = f"Build {latest} is available (current: {FLEET_BUILD})"

        tk.Label(

            win,

            text=header,

            font=("Segoe UI", 11, "bold"),

            pady=10,

            padx=14,

            anchor="w",

            justify="left",

        ).pack(fill="x")



        body_text = notes or "A newer version of FleetUnit GUI is ready to install."

        tk.Label(

            win,

            text=body_text,

            font=("Segoe UI", 9),

            pady=4,

            padx=14,

            anchor="w",

            justify="left",

            wraplength=430,

        ).pack(fill="both", expand=True)



        status_var = tk.StringVar(value="Ready to update.")

        tk.Label(win, textvariable=status_var, font=("Segoe UI", 9), padx=14, anchor="w").pack(fill="x")



        progress = ttk.Progressbar(win, orient="horizontal", mode="determinate", maximum=100)

        progress.pack(fill="x", padx=14, pady=(6, 4))

        progress["value"] = 0



        btn_frame = tk.Frame(win, pady=10, padx=14)

        btn_frame.pack(fill="x")



        def _on_update():

            if not dl_url:

                status_var.set("No download_url configured in /version.")

                return

            update_btn.configure(state="disabled")

            progress["value"] = 0

            status_var.set("Starting download... 0%")

            self._run_self_update(dl_url, status_var, progress, win)



        update_btn = tk.Button(btn_frame, text="Update Now", command=_on_update, padx=12, pady=4)

        update_btn.pack(side="left", padx=(0, 8))



        if dl_url:

            tk.Button(

                btn_frame,

                text="Open Link",

                command=lambda u=dl_url: webbrowser.open(u),

                padx=10,

                pady=4,

            ).pack(side="left", padx=(0, 8))



        tk.Button(btn_frame, text="Later", command=win.destroy, padx=10, pady=4).pack(side="right")



    def _safe_extract_zip(self, zip_path, dest_dir):

        import os

        import zipfile



        dest_real = os.path.realpath(dest_dir)

        os.makedirs(dest_real, exist_ok=True)

        extracted_files = []



        with zipfile.ZipFile(zip_path, "r") as zf:

            bad = zf.testzip()

            if bad:

                raise RuntimeError(f"Corrupt entry in zip archive: {bad}")



            members = [m for m in zf.infolist() if not m.is_dir()]

            for info in members:

                raw_name = info.filename.replace("\\", "/").lstrip("/")

                if not raw_name or raw_name.startswith("../") or "/../" in f"/{raw_name}" or raw_name == "..":

                    raise RuntimeError(f"Unsafe path in zip archive: {info.filename}")

                if len(raw_name) >= 2 and raw_name[1] == ":":

                    raise RuntimeError(f"Unsafe drive path in zip archive: {info.filename}")



                target_path = os.path.realpath(os.path.join(dest_real, raw_name))

                if target_path != dest_real and not target_path.startswith(dest_real + os.sep):

                    raise RuntimeError(f"Zip slip blocked for: {info.filename}")



                os.makedirs(os.path.dirname(target_path), exist_ok=True)

                with zf.open(info, "r") as src_f, open(target_path, "wb") as dst_f:

                    while True:

                        buf = src_f.read(8192)

                        if not buf:

                            break

                        dst_f.write(buf)

                extracted_files.append((raw_name, target_path))



        return extracted_files



    def _run_self_update(self, dl_url, status_var, progress, win=None):

        import os

        import shutil

        import subprocess

        import sys

        import tempfile

        import threading



        target_file = os.path.abspath(

            sys.argv[0] if sys.argv and sys.argv[0].endswith(".py") else __file__

        )

        app_dir = os.path.dirname(target_file)

        preserve_names = {

            "chat_nickname.txt",

            "chat_history.json",

            "fleet_state.json",

            ".env",

        }



        def _post_ui(fn):

            if hasattr(self, "_ui"):

                self._ui(fn)

            else:

                try:

                    self.after(0, fn)

                except Exception:

                    fn()



        def _worker():

            tmp_zip = None

            stage_dir = None

            try:

                req = urllib.request.Request(

                    dl_url,

                    headers={"User-Agent": f"FleetUnit-GUI/{FLEET_BUILD}"},

                    method="GET",

                )

                with urllib.request.urlopen(req, timeout=30) as resp:

                    total_hdr = resp.headers.get("Content-Length")

                    total_bytes = int(total_hdr) if (total_hdr and total_hdr.isdigit() and int(total_hdr) > 0) else 0

                    chunks = []

                    downloaded = 0

                    fallback_pct = 5.0



                    while True:

                        chunk = resp.read(8192)

                        if not chunk:

                            break

                        chunks.append(chunk)

                        downloaded += len(chunk)



                        if total_bytes > 0:

                            pct = min(75.0, (downloaded / total_bytes) * 75.0)

                            msg = f"Downloading update... {int(pct)}% ({downloaded // 1024} KB / {total_bytes // 1024} KB)"

                        else:

                            fallback_pct = min(70.0, fallback_pct + 6.0)

                            pct = fallback_pct

                            msg = f"Downloading update... ({downloaded // 1024} KB)"



                        _post_ui(lambda p=pct, m=msg: (

                            progress.configure(value=p) if progress.winfo_exists() else None,

                            status_var.set(m) if (win and win.winfo_exists()) else None,

                        ))



                content = b"".join(chunks)

                if not content or len(content) < 100:

                    raise RuntimeError("Downloaded package is empty or incomplete.")



                is_zip = (

                    dl_url.lower().split("?", 1)[0].endswith(".zip")

                    or content[:4] == b"PK\x03\x04"

                )



                _post_ui(lambda: (

                    progress.configure(value=82) if progress.winfo_exists() else None,

                    status_var.set("Validating update package... 82%") if (win and win.winfo_exists()) else None,

                ))



                if is_zip:

                    fd, tmp_zip = tempfile.mkstemp(prefix="fleet_pkg_", suffix=".zip")

                    os.close(fd)

                    with open(tmp_zip, "wb") as f:

                        f.write(content)



                    stage_dir = tempfile.mkdtemp(prefix="fleet_stage_")

                    extracted = self._safe_extract_zip(tmp_zip, stage_dir)

                    if not extracted:

                        raise RuntimeError("Zip archive contained no files.")



                    # If the zip wraps everything inside a single top-level folder, unwrap it

                    top_entries = [e for e in os.listdir(stage_dir) if not e.startswith("__MACOSX")]

                    source_root = stage_dir

                    if len(top_entries) == 1 and os.path.isdir(os.path.join(stage_dir, top_entries[0])):

                        candidate_root = os.path.join(stage_dir, top_entries[0])

                        if os.path.isfile(os.path.join(candidate_root, os.path.basename(target_file))):

                            source_root = candidate_root



                    staged_main = os.path.join(source_root, os.path.basename(target_file))

                    if os.path.isfile(staged_main) and staged_main.endswith(".py"):

                        with open(staged_main, "r", encoding="utf-8-sig") as f:

                            ast.parse(f.read())



                    _post_ui(lambda: (

                        progress.configure(value=92) if progress.winfo_exists() else None,

                        status_var.set("Injecting files & restarting... 92%") if (win and win.winfo_exists()) else None,

                    ))



                    def _apply_zip_and_restart():

                        try:

                            if progress.winfo_exists():

                                progress["value"] = 100

                            if win and win.winfo_exists():

                                status_var.set("Update applied (100%). Restarting...")

                        except Exception:

                            pass



                        if os.name == "nt":

                            bat_fd, bat_path = tempfile.mkstemp(prefix="fleet_swap_", suffix=".cmd")

                            os.close(bat_fd)

                            lines = [

                                "@echo off",

                                "ping 127.0.0.1 -n 2 > nul",

                            ]

                            for root, _, files in os.walk(source_root):

                                for fname in files:

                                    if fname in preserve_names:

                                        continue

                                    src_p = os.path.join(root, fname)

                                    rel_p = os.path.relpath(src_p, source_root)

                                    dst_p = os.path.join(app_dir, rel_p)

                                    dst_dir = os.path.dirname(dst_p)

                                    lines.append(f'if not exist "{dst_dir}" mkdir "{dst_dir}"')

                                    lines.append(f'copy /y "{src_p}" "{dst_p}" > nul')

                            lines.append(f'start "" "{sys.executable}" "{target_file}"')

                            lines.append(f'rmdir /s /q "{stage_dir}" > nul 2>&1')

                            lines.append(f'del /q "{tmp_zip}" > nul 2>&1')

                            lines.append(f'del /q "{bat_path}" > nul 2>&1')



                            with open(bat_path, "w", encoding="utf-8") as bf:

                                bf.write("\r\n".join(lines) + "\r\n")



                            subprocess.Popen(

                                ["cmd.exe", "/c", bat_path],

                                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,

                                close_fds=True,

                            )

                            try:

                                self.quit()

                                self.destroy()

                            except Exception:

                                pass

                            os._exit(0)

                        else:

                            for root, _, files in os.walk(source_root):

                                for fname in files:

                                    if fname in preserve_names:

                                        continue

                                    src_p = os.path.join(root, fname)

                                    rel_p = os.path.relpath(src_p, source_root)

                                    dst_p = os.path.join(app_dir, rel_p)

                                    os.makedirs(os.path.dirname(dst_p), exist_ok=True)

                                    shutil.copy2(src_p, dst_p)

                            shutil.rmtree(stage_dir, ignore_errors=True)

                            try:

                                os.remove(tmp_zip)

                            except Exception:

                                pass

                            os.execv(sys.executable, [sys.executable, target_file])



                    _post_ui(_apply_zip_and_restart)

                    return



                # Fallback for single raw .py / binary file

                if target_file.endswith(".py"):

                    text_src = content.decode("utf-8-sig")

                    ast.parse(text_src)

                    tmp_path = target_file + ".injecting"

                    with open(tmp_path, "w", encoding="utf-8") as f:

                        f.write(text_src)

                else:

                    fd, tmp_path = tempfile.mkstemp(prefix="fleet_upd_", suffix=".bin")

                    os.close(fd)

                    with open(tmp_path, "wb") as f:

                        f.write(content)



                _post_ui(lambda: (

                    progress.configure(value=95) if progress.winfo_exists() else None,

                    status_var.set("Injecting update & restarting... 95%") if (win and win.winfo_exists()) else None,

                ))



                def _inject_and_restart():

                    try:

                        if progress.winfo_exists():

                            progress["value"] = 100

                        if win and win.winfo_exists():

                            status_var.set("Update applied (100%). Restarting...")

                    except Exception:

                        pass



                    if os.name == "nt":

                        cmd = (

                            f'ping 127.0.0.1 -n 2 > nul & '

                            f'move /y "{tmp_path}" "{target_file}" > nul & '

                            f'start "" "{sys.executable}" "{target_file}"'

                        )

                        subprocess.Popen(

                            ["cmd.exe", "/c", cmd],

                            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,

                            close_fds=True,

                        )

                        try:

                            self.quit()

                            self.destroy()

                        except Exception:

                            pass

                        os._exit(0)

                    else:

                        os.replace(tmp_path, target_file)

                        os.execv(sys.executable, [sys.executable, target_file])



                _post_ui(_inject_and_restart)

            except Exception as exc:

                try:

                    if tmp_zip and os.path.exists(tmp_zip):

                        os.remove(tmp_zip)

                    if stage_dir and os.path.isdir(stage_dir):

                        shutil.rmtree(stage_dir, ignore_errors=True)

                except Exception:

                    pass



                def _fail(err=str(exc)):

                    try:

                        if win and win.winfo_exists():

                            status_var.set(f"Update failed: {err}")

                    except Exception:

                        pass

                _post_ui(_fail)



        threading.Thread(target=_worker, daemon=True).start()



    def _check_for_gui_update(self, show_if_current=False):

        import json

        import threading

        import urllib.request



        def _worker():

            try:

                req = urllib.request.Request(

                    FLEET_UPDATE_URL,

                    headers={"User-Agent": f"FleetUnit-GUI/{FLEET_BUILD}"},

                    method="GET",

                )

                with urllib.request.urlopen(req, timeout=8) as resp:

                    data = json.loads(resp.read().decode("utf-8", errors="replace") or "{}")

                latest = str(

                    data.get("latest_build")

                    or data.get("build")

                    or data.get("version")

                    or ""

                ).strip()

                notes = str(data.get("notes") or data.get("message") or "").strip()

                dl_url = str(data.get("download_url") or data.get("url") or "").strip()



                if latest and self._is_build_newer(latest, FLEET_BUILD):

                    def _notify():

                        if hasattr(self, "_append_chat_line"):

                            self._append_chat_line(f"[UPDATE] Build {latest} available (current: {FLEET_BUILD}).")

                        self._prompt_gui_update(latest=latest, notes=notes, dl_url=dl_url)



                    if hasattr(self, "_ui"):

                        self._ui(_notify)

                    else:

                        self.after(0, _notify)

                elif show_if_current:

                    def _up_to_date():

                        try:

                            from tkinter import messagebox

                            messagebox.showinfo("FleetUnit Up to Date", f"You are running the latest build ({FLEET_BUILD}).")

                        except Exception:

                            pass

                    if hasattr(self, "_ui"):

                        self._ui(_up_to_date)

                    else:

                        self.after(0, _up_to_date)

            except Exception:

                if show_if_current:

                    def _err():

                        try:

                            from tkinter import messagebox

                            messagebox.showinfo("Update Check", f"Current build: {FLEET_BUILD} (could not reach update server).")

                        except Exception:

                            pass

                    if hasattr(self, "_ui"):

                        self._ui(_err)

                    else:

                        self.after(0, _err)



        threading.Thread(target=_worker, daemon=True).start()



    def _consume_chat_messages(self, msgs):

        new_entries = []

        viewer_lower = self._current_chat_nick().strip().lower()

        for m in msgs or []:

            if not isinstance(m, dict):

                continue

            mid = str(m.get("id") or "")

            ts = int(m.get("ts") or 0)

            if ts > self._chat_last_ts:

                self._chat_last_ts = ts

            if mid and mid in self._chat_seen_ids:

                continue

            if mid:

                self._chat_seen_ids.add(mid)

            sender = str(m.get("sender") or "").strip()

            recipient = str(m.get("recipient") or "").strip()

            if (recipient or m.get("is_whisper")) and sender and sender.lower() != viewer_lower:

                if not recipient or recipient.lower() == viewer_lower:

                    self._last_whisper_from = sender

            tag = "whisper" if self._is_whisper_message(m) else None

            new_entries.append((self._format_chat_message(m), tag))

        if new_entries and hasattr(self, "_ui"):

            self._ui(lambda entries=new_entries: [self._append_chat_line(ln, tag=tg) for ln, tg in entries])



    def _send_global_chat(self):

        import threading

        if not hasattr(self, "_chat_input") or not self._chat_input.winfo_exists():

            return

        raw_input = self._chat_input.get().strip()

        if not raw_input:

            return

        nick = self._current_chat_nick() or "Trader"

        self._save_chat_nickname(nick)



        recipient = ""

        text = raw_input

        if raw_input.lower().startswith("/whisper"):

            remainder = raw_input[len("/whisper"):].strip()

            parts = remainder.split(None, 1) if remainder else []

            if len(parts) < 2 or not parts[0].strip() or not parts[1].strip():

                self._append_chat_line("Usage: /whisper <nickname> <message>", tag="whisper")

                return

            recipient = parts[0].strip()[:24]

            text = parts[1].strip()

        elif raw_input.lower().startswith("/reply"):

            reply_body = raw_input[len("/reply"):].strip()

            last_sender = str(getattr(self, "_last_whisper_from", "") or "").strip()

            if not last_sender:

                self._append_chat_line("No recent whisper to reply to. Use /whisper <nickname> <message>", tag="whisper")

                return

            if not reply_body:

                self._append_chat_line("Usage: /reply <message>", tag="whisper")

                return

            recipient = last_sender[:24]

            text = reply_body



        self._chat_input.delete(0, "end")



        relay_base = (

            os.getenv("SUPPORT_RELAY_URL")

            or "https://fleetunit-support.fleetunitsupport.workers.dev/messages"

        ).strip()

        if relay_base.endswith("/messages"):

            chat_url = relay_base[:-len("/messages")] + "/chat/send"

        else:

            chat_url = relay_base.rstrip("/") + "/chat/send"



        intake_token = (os.getenv("SUPPORT_INTAKE_TOKEN") or "fu_intake_9f8a7b6c5d4e").strip()



        def _worker():

            try:

                msg_payload = {"sender": nick, "text": text}

                if recipient:

                    msg_payload["recipient"] = recipient

                    msg_payload["is_whisper"] = True

                payload = json.dumps(msg_payload).encode("utf-8")

                headers = {

                    "Content-Type": "application/json",

                    "User-Agent": "FleetUnit-Chat/1.0",

                }

                if intake_token:

                    headers["X-Intake-Token"] = intake_token

                req = urllib.request.Request(chat_url, data=payload, headers=headers, method="POST")

                with urllib.request.urlopen(req, timeout=8) as resp:

                    code = getattr(resp, "status", 200)

                    raw = resp.read().decode("utf-8", errors="replace")

                    if 200 <= code < 300:

                        try:

                            data = json.loads(raw) if raw else {}

                        except Exception:

                            data = {}

                        msg_obj = data.get("message") if isinstance(data, dict) else None

                        if isinstance(msg_obj, dict):

                            self._consume_chat_messages([msg_obj])

                        else:

                            import time

                            self._consume_chat_messages([{

                                "id": f"local-{time.time_ns()}",

                                "ts": int(time.time() * 1000),

                                "sender": nick,

                                "text": text,

                            }])

                        if hasattr(self, "_ui"):

                            self._ui(lambda: hasattr(self, "_chat_status_lbl") and self._chat_status_lbl.winfo_exists() and self._chat_status_lbl.configure(text="Connected (Global Chat)", text_color="#2ecc71"))

            except Exception as exc:

                if hasattr(self, "_ui"):

                    self._ui(lambda err=str(exc): hasattr(self, "_chat_status_lbl") and self._chat_status_lbl.winfo_exists() and self._chat_status_lbl.configure(text=f"Send error: {err}", text_color="#e74c3c"))



        threading.Thread(target=_worker, daemon=True).start()



    def _poll_global_chat_loop(self):

        import time

        relay_base = (

            os.getenv("SUPPORT_RELAY_URL")

            or "https://fleetunit-support.fleetunitsupport.workers.dev/messages"

        ).strip()

        if relay_base.endswith("/messages"):

            poll_base = relay_base[:-len("/messages")] + "/chat/messages"

        else:

            poll_base = relay_base.rstrip("/") + "/chat/messages"

        viewer_nick = ""

        try:

            if hasattr(self, "_chat_nick_entry") and self._chat_nick_entry.winfo_exists():

                viewer_nick = self._chat_nick_entry.get().strip()

        except Exception:

            viewer_nick = ""

        if not viewer_nick and hasattr(self, "_load_chat_nickname"):

            try:

                viewer_nick = str(self._load_chat_nickname() or "").strip()

            except Exception:

                viewer_nick = ""

        if viewer_nick:

            from urllib.parse import quote

            sep = "&" if "?" in poll_base else "?"

            poll_base = f"{poll_base}{sep}viewer={quote(viewer_nick)}"



        while True:

            try:

                url = f"{poll_base}?after={int(self._chat_last_ts)}"

                req = urllib.request.Request(url, headers={"User-Agent": "FleetUnit-Chat/1.0"}, method="GET")

                with urllib.request.urlopen(req, timeout=8) as resp:

                    data = json.loads(resp.read().decode("utf-8"))

                    msgs = data.get("messages") or []

                    self._consume_chat_messages(msgs)

                    if hasattr(self, "_ui"):

                        self._ui(lambda: hasattr(self, "_chat_status_lbl") and self._chat_status_lbl.winfo_exists() and self._chat_status_lbl.configure(text="Connected (Global Chat)", text_color="#2ecc71"))

            except Exception as exc:

                if hasattr(self, "_ui"):

                    self._ui(lambda err=str(exc): hasattr(self, "_chat_status_lbl") and self._chat_status_lbl.winfo_exists() and self._chat_status_lbl.configure(text=f"Reconnecting... ({err})", text_color="#f59e0b"))

            time.sleep(1.0)



    def _send_support_gmail(self, subject, body, win=None, status_lbl=None):

        relay_url = (

            os.getenv("SUPPORT_RELAY_URL")

            or "https://fleetunit-support.fleetunitsupport.workers.dev/messages"

        ).strip()

        intake_token = (

            os.getenv("SUPPORT_INTAKE_TOKEN")

            or "fu_intake_9f8a7b6c5d4e"

        ).strip()

        app_ver = str(getattr(self, "APP_VERSION", "") or getattr(self, "app_version", "") or "FleetUnit Desktop").strip()



        def _set_status(msg, color):

            if hasattr(self, "_ui"):

                self._ui(lambda m=msg, c=color: status_lbl.winfo_exists() and status_lbl.configure(text=m, text_color=c))



        payload = json.dumps({

            "subject": subject,

            "body": body,

            "app_version": app_ver,

        }).encode("utf-8")



        headers = {

            "Content-Type": "application/json",

            "User-Agent": "FleetUnit-Support/1.0",

        }

        if intake_token:

            headers["X-Intake-Token"] = intake_token



        try:

            req = urllib.request.Request(relay_url, data=payload, headers=headers, method="POST")

            with urllib.request.urlopen(req, timeout=15) as resp:

                code = getattr(resp, "status", 200)

                if 200 <= code < 300:

                    if hasattr(self, "append_log_scroll_safe"):

                        self._ui(lambda s=subject: self.append_log_scroll_safe(f"[Support] Sent message '{s}' to support inbox.\n"))

                    _set_status("Message sent!", "#2ecc71")

                    if win is not None and hasattr(self, "_ui"):

                        self._ui(lambda: win.winfo_exists() and win.after(600, win.destroy))

                    return

                _set_status(f"Relay returned HTTP {code}", "#e74c3c")

                return

        except urllib.error.HTTPError as exc:

            _set_status(f"Relay HTTP error {exc.code}: {exc.reason}", "#e74c3c")

            return

        except Exception as exc:

            _set_status(f"Send failed: {exc}", "#e74c3c")

            return



if __name__ == "__main__":

    if len(sys.argv) > 1 and sys.argv[1].endswith(".py"):

        worker_script = sys.argv[1]

        if os.path.exists(worker_script):

            try:

                sys.path.insert(0, os.path.dirname(worker_script))

                with open(worker_script, "r", encoding="utf-8-sig") as _f:

                    exec(compile(_f.read(), worker_script, "exec"), {"__name__": "__main__", "__file__": worker_script})

                sys.exit(0)

            except SystemExit:

                raise

            except Exception:

                sys.exit(1)



    try:

        app = FleetApp()

        app.mainloop()

    except Exception as e:

        os.makedirs(LOG_DIR, exist_ok=True)

        with open(os.path.join(LOG_DIR, "gui_diag.log"), "a", encoding="utf-8") as f:

            f.write(f"\n=== {datetime.now()} ===\n")

            traceback.print_exc(file=f)

        raise





# === AI_WATCHLIST_WINDOW_INTEGRATION ===

def _ai_watchlist_render_candles_on_canvas(

    canvas,

    rates,

    tf="30m",

    zoom=1.0,

    offset=0,

    open_price=0.0,

    pair_label="",

    bias_label="",

    conf_pct=0,

):

    if canvas is None or not canvas.winfo_exists():

        return

    canvas.delete("all")

    w = max(canvas.winfo_width(), 220)

    h = max(canvas.winfo_height(), 140)

    left_pad = 10

    right_pad = 64

    top_pad = 22

    bot_pad = 20



    if pair_label:

        title_txt = f"{pair_label}  [{tf}]"

        if bias_label:

            title_txt += f"  ?  {bias_label} ({conf_pct}%)"

        canvas.create_text(

            left_pad,

            11,

            text=title_txt,

            anchor="w",

            fill="#ecf0f1",

            font=("Consolas", 9, "bold"),

        )



    # Blank canvas when no real candle data is available

    if not rates or len(rates) < 2:

        return



    tf_mult = {"1m": 1.0, "5m": 0.85, "15m": 0.75, "30m": 0.65, "1h": 0.55}.get(tf, 0.75)

    base_bars = max(25, int(90 * tf_mult))

    visible_bars = max(12, min(len(rates), int(base_bars / max(0.35, min(4.0, float(zoom or 1.0))))))

    max_off = max(0, len(rates) - visible_bars)

    safe_off = max(0, min(max_off, int(offset or 0)))

    end_idx = len(rates) - safe_off

    start_idx = max(0, end_idx - visible_bars)

    window = rates[start_idx:end_idx]

    if not window:

        return



    highs = [float(r["high"]) for r in window]

    lows = [float(r["low"]) for r in window]

    p_max = max(highs)

    p_min = min(lows)

    if p_max <= p_min:

        p_max = p_min + 0.001



    plot_w = max(40, w - left_pad - right_pad)

    plot_h = max(30, h - top_pad - bot_pad)



    def y_for(price_val):

        ratio = (float(price_val) - p_min) / (p_max - p_min)

        return top_pad + (1.0 - ratio) * plot_h



    for step_i in range(5):

        frac = step_i / 4.0

        gy = top_pad + (1.0 - frac) * plot_h

        gprice = p_min + frac * (p_max - p_min)

        canvas.create_line(left_pad, gy, w - right_pad, gy, fill="#2c3e50", dash=(2, 4))

        canvas.create_text(

            w - right_pad + 4,

            gy,

            text=f"{gprice:.5f}",

            anchor="w",

            fill="#7f8c8d",

            font=("Consolas", 8),

        )



    step_x = plot_w / float(max(1, len(window)))

    body_w = max(2.0, min(12.0, step_x * 0.65))



    if mode == "line":

        wl_pts = []

        for idx_c, candle in enumerate(window):

            cx = left_pad + (idx_c + 0.5) * step_x

            cy = y_for(float(candle["close"]))

            wl_pts.extend([cx, cy])

        if len(wl_pts) >= 4:

            first_val = float(window[0]["close"])

            last_val = float(window[-1]["close"])

            wl_col = "#2ecc71" if last_val >= first_val else "#e74c3c"

            canvas.create_line(*wl_pts, fill=wl_col, width=2, smooth=False)

    else:

      for candle in window:

        idx_c = window.index(candle)

        cx = left_pad + (idx_c + 0.5) * step_x

        o_val = float(candle["open"])

        c_val = float(candle["close"])

        h_val = float(candle["high"])

        l_val = float(candle["low"])



        y_h = y_for(h_val)

        y_l = y_for(l_val)

        y_o = y_for(o_val)

        y_c = y_for(c_val)



        bull = c_val >= o_val

        wick_col = "#2ecc71" if bull else "#e74c3c"

        body_col = "#27ae60" if bull else "#c0392b"



        canvas.create_line(cx, y_h, cx, y_l, fill=wick_col, width=1)

        top_y = min(y_o, y_c)

        bot_y = max(y_o, y_c)

        if abs(bot_y - top_y) < 1.5:

            bot_y = top_y + 1.5

        canvas.create_rectangle(

            cx - body_w / 2.0,

            top_y,

            cx + body_w / 2.0,

            bot_y,

            fill=body_col,

            outline=wick_col,

        )



    ref_open = float(open_price or 0.0)

    if ref_open <= 0.0 and window:

        ref_open = float(window[0]["open"])

    if ref_open > 0.0 and p_min <= ref_open <= p_max:

        y_open = y_for(ref_open)

        canvas.create_line(left_pad, y_open, w - right_pad, y_open, fill="#f1c40f", dash=(4, 2), width=1)

        canvas.create_text(

            w - right_pad - 2,

            y_open + 8,

            text=f"OPEN: {ref_open:.5f}",

            anchor="e",

            fill="#ffffff",

            font=("Consolas", 8, "bold"),

        )





def _fetch_pair_candles_for_watchlist(pair_symbol, tf_str="30m", count=240):

    clean_sym = (pair_symbol or "").replace("/", "").strip().upper()

    tf_map = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60}

    mins = tf_map.get(tf_str, 30)

    try:

        import MetaTrader5 as mt5

        mt5_tf = getattr(mt5, f"TIMEFRAME_M{mins}", None)

        if mt5_tf is not None and mt5.initialize():

            for cand in (clean_sym, clean_sym + "m", clean_sym + ".pro", pair_symbol):

                if not cand:

                    continue

                rates = mt5.copy_rates_from_pos(cand, mt5_tf, 0, count)

                if rates is not None and len(rates) > 0:

                    return [

                        {

                            "open": float(r["open"]),

                            "high": float(r["high"]),

                            "low": float(r["low"]),

                            "close": float(r["close"]),

                        }

                        for r in rates

                    ]

    except Exception:

        pass

    return []



















