"""
Chrome Client - Modrinth-style, fully recolorable (PySide6)

- Dark sidebar UI in the style of the Modrinth app; every color is changeable
  (Appearance page) and saved
- Microsoft sign-in that finishes on its own (local callback, no URL pasting)
- Modrinth mod browser: search + one-click install of Fabric mods (and their
  required dependencies)
- Fabric toggle, PvP color texture packs, creamy UI sounds, demo mode

Run:  pip install -r requirements.txt && python launcher.py
"""
import hashlib
import html
import http.server
import json
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path
from string import Template

import minecraft_launcher_lib as mll
from PySide6.QtCore import QEvent, QObject, QPointF, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QColorDialog, QComboBox, QFileDialog,
    QFrame, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QProgressBar, QPushButton, QScrollArea, QSlider,
    QStackedWidget, QVBoxLayout, QWidget,
)

import pvp_packs
from sounds import SoundPlayer

APP_DIR = Path.home() / ".simple_mc_launcher"
CONFIG_FILE = APP_DIR / "config.json"
ICON_DIR = APP_DIR / "theme_icons"
DEFAULT_MC_DIR = str(Path(mll.utils.get_minecraft_directory()))

# Microsoft sign-in: register a free Azure app once (see README) and paste its
# client ID in Settings. The redirect URI below must match the one you register.
CALLBACK_PORT = 3000
REDIRECT_URI = f"http://localhost:{CALLBACK_PORT}/callback"

MODRINTH_API = "https://api.modrinth.com/v2"
USER_AGENT = "chrome-client/2.0 (personal use)"

# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------
DEFAULT_THEME = {"bg": "#16181c", "surface": "#26292f", "accent": "#1bd96a", "text": "#ecf0f1"}
ACCENTS = {"Green": "#1bd96a", "Pink": "#ff5fa8", "Blue": "#3b9bff",
           "Orange": "#ff8a2b", "Red": "#ff4d4d", "Purple": "#a56bff"}


def tinted_theme(accent):
    """A full dark theme whose background and cards are tinted to the accent."""
    h = QColor(accent).hsvHueF()
    return {"bg": QColor.fromHsvF(h, 0.40, 0.10).name(),
            "surface": QColor.fromHsvF(h, 0.32, 0.17).name(),
            "accent": accent, "text": "#f3eef0"}


PRESETS = {"Classic": dict(DEFAULT_THEME), **{n: tinted_theme(c) for n, c in ACCENTS.items()}}


def mix(a, b, t):
    ca, cb = QColor(a), QColor(b)
    return QColor(round(ca.red() * (1 - t) + cb.red() * t),
                  round(ca.green() * (1 - t) + cb.green() * t),
                  round(ca.blue() * (1 - t) + cb.blue() * t)).name()


def luminance(c):
    c = QColor(c)
    return 0.2126 * c.red() / 255 + 0.7152 * c.green() / 255 + 0.0722 * c.blue() / 255


def clean_theme(t):
    out = dict(DEFAULT_THEME)
    for k in out:
        if isinstance(t, dict) and QColor(str(t.get(k, ""))).isValid():
            out[k] = QColor(t[k]).name()
    return out


def _draw_icon(path, draw):
    pm = QPixmap(48, 48)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    draw(p)
    p.end()
    pm.save(str(path))


def make_icons(color_chev, color_check):
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    chev = ICON_DIR / f"chev_{color_chev[1:]}.png"
    check = ICON_DIR / f"check_{color_check[1:]}.png"

    def d_chev(p):
        p.setPen(QPen(QColor(color_chev), 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(11, 18), QPointF(24, 31))
        p.drawLine(QPointF(24, 31), QPointF(37, 18))

    def d_check(p):
        p.setPen(QPen(QColor(color_check), 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(12, 25), QPointF(21, 34))
        p.drawLine(QPointF(21, 34), QPointF(37, 15))

    if not chev.exists():
        _draw_icon(chev, d_chev)
    if not check.exists():
        _draw_icon(check, d_check)
    return chev.as_posix(), check.as_posix()


QSS = Template("""
* { color: $text; font-size: 13px; }
QMainWindow, QWidget#root { background: $bg; }
QWidget#sidebar { background: $surface; border-right: 1px solid $border; }
QLabel { background: transparent; border: none; }
QLabel[muted="true"] { color: $muted; }
QLabel[h1="true"] { font-size: 24px; font-weight: 700; }
QLabel[h2="true"] { font-size: 15px; font-weight: 600; }
QLabel[brand="true"] { font-size: 18px; font-weight: 800; color: $accent; }
QLabel#modicon { background: $surface_hi; border-radius: 10px; }
QLabel#avatar { background: $accent; color: $accent_text; border-radius: 18px; font-weight: 700; font-size: 15px; }
QFrame[card="true"] { background: $surface; border: 1px solid $border; border-radius: 14px; }
QFrame[chip="true"] { background: $bg; border: 1px solid $border; border-radius: 12px; }
QPushButton { background: $surface_hi; border: 1px solid $border; border-radius: 10px; padding: 8px 16px; font-weight: 600; }
QPushButton:hover { background: $surface_hi2; }
QPushButton:pressed { background: $border; }
QPushButton:disabled { color: $muted; }
QPushButton[primary="true"] { background: $accent; color: $accent_text; border: none; }
QPushButton[primary="true"]:hover { background: $accent_hover; }
QPushButton[primary="true"]:disabled { background: $border; color: $muted; }
QPushButton[nav="true"] { background: transparent; border: none; text-align: left; padding: 10px 14px; color: $muted; }
QPushButton[nav="true"]:hover { background: $surface_hi; color: $text; }
QPushButton[nav="true"]:checked { background: $accent_soft; color: $accent; }
QPushButton[ghost="true"] { background: transparent; border: 1px solid $border; }
QPushButton[ghost="true"]:hover { background: $surface_hi; }
QLineEdit, QSpinBox, QComboBox { background: $bg; border: 1px solid $border; border-radius: 10px; padding: 8px 12px; selection-background-color: $accent; selection-color: $accent_text; }
QLineEdit:focus, QComboBox:focus { border: 1px solid $accent; }
QComboBox { padding-right: 30px; }
QComboBox::drop-down { border: none; width: 30px; }
QComboBox::down-arrow { image: url("$chev"); width: 12px; height: 12px; }
QComboBox QAbstractItemView { background: $surface; border: 1px solid $border; selection-background-color: $accent_soft; selection-color: $accent; outline: 0; padding: 4px; }
QCheckBox { spacing: 10px; background: transparent; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 6px; border: 2px solid $border2; background: $bg; }
QCheckBox::indicator:hover { border-color: $accent; }
QCheckBox::indicator:checked { background: $accent; border-color: $accent; image: url("$check"); }
QProgressBar { background: $bg; border: none; border-radius: 5px; max-height: 10px; min-height: 10px; color: transparent; }
QProgressBar::chunk { background: $accent; border-radius: 5px; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: $border2; border-radius: 4px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QSlider::groove:horizontal { height: 8px; background: $bg; border-radius: 4px; }
QSlider::sub-page:horizontal { background: $accent; border-radius: 4px; }
QSlider::handle:horizontal { background: $accent; width: 18px; height: 18px; margin: -5px 0; border-radius: 9px; }
QToolTip, QMessageBox, QDialog, QInputDialog { background: $surface; color: $text; border: 1px solid $border; }
""")


def build_qss(theme):
    t = clean_theme(theme)
    bg, surf, acc, text = t["bg"], t["surface"], t["accent"], t["text"]
    accent_text = "#0b0b0d" if luminance(acc) > 0.5 else "#ffffff"
    chev, check = make_icons(text, accent_text)
    return QSS.substitute(
        bg=bg, surface=surf, text=text, accent=acc, accent_text=accent_text,
        surface_hi=mix(surf, text, 0.07), surface_hi2=mix(surf, text, 0.13),
        border=mix(surf, text, 0.12), border2=mix(surf, text, 0.28),
        muted=mix(text, bg, 0.45), accent_hover=mix(acc, "#ffffff", 0.18),
        accent_soft=mix(bg, acc, 0.22), chev=chev, check=check)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DEFAULT_CONFIG = {
    "client_id": "",
    "minecraft_dir": DEFAULT_MC_DIR,
    "ram_mb": 4096,
    "last_version": "",
    "show_snapshots": False,
    "use_fabric": False,
    "demo": False,
    "sounds": True,
    "pvp_pack": "none",
    "theme": dict(DEFAULT_THEME),
    "account": None,  # {"name","id","refresh_token"}
}


def load_config():
    APP_DIR.mkdir(parents=True, exist_ok=True)
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        try:
            cfg.update(json.loads(CONFIG_FILE.read_text()))
        except Exception:
            pass
    cfg["theme"] = clean_theme(cfg.get("theme"))
    return cfg


def save_config(cfg):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


# ---------------------------------------------------------------------------
# Microsoft sign-in (local callback server)
# ---------------------------------------------------------------------------
def callback_error(url):
    """If Microsoft sent the browser back with an error (or no code), explain it. Else None."""
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    if "error" in q or "code" not in q:
        desc = (q.get("error_description") or q.get("error") or ["Microsoft didn't send a sign-in code."])[0]
        low = desc.lower()
        hint = ""
        if "redirect" in low:
            hint = (" Fix: in your Azure app open Authentication and make sure the redirect URI is exactly "
                    f"{REDIRECT_URI} under 'Mobile and desktop applications'.")
        elif "unauthorized_client" in low or "not enabled for consumers" in low or "not configured" in low:
            hint = (" Fix: in your Azure app set Supported account types to 'Personal Microsoft accounts only' "
                    "and turn on 'Allow public client flows'.")
        elif "application" in low and "not found" in low:
            hint = " Fix: check the Azure client ID in Settings - it must be the one from YOUR app registration."
        return desc.replace("+", " ") + hint
    return None


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if not self.path.startswith("/callback"):
            self.send_response(404)
            self.end_headers()
            return
        self.server.callback_url = f"http://localhost:{CALLBACK_PORT}{self.path}"
        th = self.server.theme
        err = callback_error(self.server.callback_url)
        if err:
            title, msg = "Sign-in failed", html.escape(err)
        else:
            title, msg = "Signed in", "You can close this tab and go back to the launcher."
        body = (f"<html><body style='margin:0;display:grid;place-items:center;height:100vh;"
                f"background:{th['bg']};color:{th['text']};font-family:system-ui,sans-serif'>"
                f"<div style='text-align:center;max-width:560px;padding:20px'>"
                f"<h1 style='color:{th['accent']}'>{title}</h1>"
                f"<p>{msg}</p></div></body></html>").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def open_callback_server(theme):
    """Start listening for Microsoft's redirect. Raises OSError if the port is busy."""
    srv = http.server.HTTPServer(("127.0.0.1", CALLBACK_PORT), _CallbackHandler)
    srv.timeout = 1
    srv.callback_url = None
    srv.theme = theme
    return srv


def wait_for_callback(srv, timeout=180):
    """Blocks until the browser hits /callback; returns the full URL (None on timeout)."""
    try:
        end = time.time() + timeout
        while srv.callback_url is None and time.time() < end:
            srv.handle_request()
        return srv.callback_url
    finally:
        srv.server_close()


def friendly_login_error(e):
    n = type(e).__name__
    if n == "AzureAppNotPermitted":
        return ("Microsoft hasn't approved your Azure app for the Minecraft API yet. "
                "Request access at https://aka.ms/AppRegInfo (can take a few days). "
                "Demo mode works in the meantime.")
    if n == "AccountNotOwnMinecraft":
        return "That Microsoft account doesn't own Minecraft: Java Edition."
    if isinstance(e, KeyError):
        return "Microsoft's reply was missing something (" + str(e) + "). Check your Azure app settings and try again."
    if isinstance(e, AssertionError):
        return "The sign-in response didn't match this request. Please try signing in again."
    if n == "InvalidRefreshToken":
        return "Your sign-in expired. Sign in again."
    return str(e) or n


# ---------------------------------------------------------------------------
# Modrinth API
# ---------------------------------------------------------------------------
def modrinth_get(path, params=None):
    url = MODRINTH_API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def search_mods(query, mc_version):
    facets = [["project_type:mod"], ["categories:fabric"]]
    if mc_version:
        facets.append([f"versions:{mc_version}"])
    params = {"facets": json.dumps(facets), "limit": 20,
              "index": "relevance" if query else "downloads"}
    if query:
        params["query"] = query
    return modrinth_get("/search", params)["hits"]


def download_file(url, dest, sha512=None):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    tmp = dest.with_name(dest.name + ".part")
    h = hashlib.sha512()
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        while chunk := r.read(65536):
            h.update(chunk)
            f.write(chunk)
    if sha512 and h.hexdigest() != sha512:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"Checksum mismatch for {dest.name}")
    tmp.replace(dest)


def install_mod(project_id, mc_version, mods_dir, seen=None):
    """Install the newest Fabric build for mc_version plus required dependencies.
    Returns the list of installed file names."""
    seen = seen if seen is not None else set()
    if project_id in seen:
        return []
    seen.add(project_id)
    versions = modrinth_get(f"/project/{project_id}/version",
                            {"loaders": json.dumps(["fabric"]),
                             "game_versions": json.dumps([mc_version])})
    if not versions:
        raise RuntimeError(f"No Fabric build for Minecraft {mc_version}")
    v = versions[0]
    f = next((x for x in v["files"] if x.get("primary")), v["files"][0])
    name = Path(f["filename"]).name  # never trust a path from the network
    mods_dir.mkdir(parents=True, exist_ok=True)
    download_file(f["url"], mods_dir / name, f.get("hashes", {}).get("sha512"))
    done = [name]
    for dep in v.get("dependencies", []):
        if dep.get("dependency_type") == "required" and dep.get("project_id"):
            done += install_mod(dep["project_id"], mc_version, mods_dir, seen)
    return done


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------
def label(text, kind=None):
    l = QLabel(text)
    if kind == "muted":
        l.setProperty("muted", True)
        l.setWordWrap(True)
    elif kind:
        l.setProperty(kind, True)
    return l


def dot_icon(color):
    pm = QPixmap(32, 32)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    p.drawEllipse(4, 4, 24, 24)
    p.end()
    return QIcon(pm)


def card():
    f = QFrame()
    f.setProperty("card", True)
    return f


def header(title, sub):
    box = QVBoxLayout()
    box.setSpacing(2)
    box.addWidget(label(title, "h1"))
    box.addWidget(label(sub, "muted"))
    return box


def primary(btn):
    btn.setProperty("primary", True)
    return btn


class Bus(QObject):
    versions = Signal(list)
    status = Signal(str)
    progress = Signal(int, int)       # value, max (max < 0 keeps the old max)
    play_done = Signal(bool, str)
    login_done = Signal(object, str)  # account or None, error text
    mods = Signal(int, list, str)     # search id, hits, error
    mod_status = Signal(str)
    mod_installed = Signal(str)       # project id (empty on failure)
    icon = Signal(str, bytes)


class SfxFilter(QObject):
    """Plays the click sounds for every button / checkbox in the app."""
    def __init__(self, sfx, skip):
        super().__init__()
        self.sfx, self.skip = sfx, skip

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Type.MouseButtonPress and obj is not self.skip and obj.isEnabled():
            if isinstance(obj, QCheckBox):
                self.sfx.play("toggle")
            elif isinstance(obj, QPushButton):
                self.sfx.play("click")
        return False


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------
class Launcher(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Chrome Client")
        self.resize(1000, 660)
        self.setMinimumSize(880, 580)
        self.cfg = load_config()
        self.versions = []
        self.busy = False
        self.mod_search_id = 0
        self.icon_labels = {}
        self.sfx = SoundPlayer()
        self.sfx.enabled = self.cfg["sounds"]
        self.bus = Bus()
        self._connect_bus()

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_sidebar())
        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)
        self.stack.addWidget(self._build_play())
        self.stack.addWidget(self._build_mods())
        self.stack.addWidget(self._build_appearance())
        self.stack.addWidget(self._build_settings())

        self.apply_theme(self.cfg["theme"], save=False)
        self._refresh_account()
        self._sfx_filter = SfxFilter(self.sfx, self.play_btn)
        QApplication.instance().installEventFilter(self._sfx_filter)
        self.nav_buttons[0].setChecked(True)
        threading.Thread(target=self._load_versions, daemon=True).start()

    def _connect_bus(self):
        b = self.bus
        b.versions.connect(self._on_versions)
        b.status.connect(lambda t: self.status_lbl.setText(t))
        b.progress.connect(self._on_progress)
        b.play_done.connect(self._on_play_done)
        b.login_done.connect(self._on_login_done)
        b.mods.connect(self._on_mods)
        b.mod_status.connect(self._set_mod_status)
        b.mod_installed.connect(self._on_mod_installed)
        b.icon.connect(self._on_icon)

    # ---------- sidebar ----------
    def _build_sidebar(self):
        sb = QWidget()
        sb.setObjectName("sidebar")
        sb.setFixedWidth(220)
        lay = QVBoxLayout(sb)
        lay.setContentsMargins(14, 18, 14, 14)
        lay.setSpacing(4)
        lay.addWidget(label("Chrome Client", "brand"))
        lay.addWidget(label("Minecraft launcher", "muted"))
        lay.addSpacing(14)
        self.nav_group = QButtonGroup(self)
        self.nav_buttons = []
        for i, name in enumerate(("Play", "Mods", "Appearance", "Settings")):
            b = QPushButton(name)
            b.setProperty("nav", True)
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, i=i: self.stack.setCurrentIndex(i))
            self.nav_group.addButton(b)
            self.nav_buttons.append(b)
            lay.addWidget(b)
        lay.addStretch(1)

        chip = QFrame()
        chip.setProperty("chip", True)
        cl = QHBoxLayout(chip)
        cl.setContentsMargins(10, 10, 10, 10)
        self.avatar = QLabel("?")
        self.avatar.setObjectName("avatar")
        self.avatar.setFixedSize(36, 36)
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(self.avatar)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.acc_name = QLabel("Not signed in")
        self.acc_name.setProperty("h2", True)
        col.addWidget(self.acc_name)
        self.acc_btn = QPushButton("Sign in")
        self.acc_btn.setProperty("ghost", True)
        self.acc_btn.clicked.connect(self.account_clicked)
        col.addWidget(self.acc_btn)
        cl.addLayout(col, 1)
        lay.addWidget(chip)
        return sb

    # ---------- play page ----------
    def _page(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(32, 28, 32, 24)
        lay.setSpacing(16)
        return w, lay

    def _build_play(self):
        page, lay = self._page()
        lay.addLayout(header("Play", "Pick a version, a PvP pack, and jump in."))
        c = card()
        g = QGridLayout(c)
        g.setContentsMargins(22, 20, 22, 20)
        g.setHorizontalSpacing(14)
        g.setVerticalSpacing(14)
        g.setColumnStretch(1, 1)

        g.addWidget(label("Version", "h2"), 0, 0)
        self.version_box = QComboBox()
        self.version_box.activated.connect(lambda _: self.sfx.play("select"))
        self.version_box.currentTextChanged.connect(self._version_changed)
        g.addWidget(self.version_box, 0, 1)
        self.snap_cb = QCheckBox("Snapshots")
        self.snap_cb.setChecked(self.cfg["show_snapshots"])
        self.snap_cb.toggled.connect(lambda _: (self._fill_versions(), self._save_settings()))
        g.addWidget(self.snap_cb, 0, 2)

        g.addWidget(label("Loader", "h2"), 1, 0)
        self.fabric_cb = QCheckBox("Fabric (needed for mods)")
        self.fabric_cb.setChecked(self.cfg["use_fabric"])
        self.fabric_cb.toggled.connect(lambda _: (self._save_settings(), self._update_mods_hint()))
        g.addWidget(self.fabric_cb, 1, 1, 1, 2)

        g.addWidget(label("PvP pack", "h2"), 2, 0)
        self.pack_box = QComboBox()
        self.pack_box.addItems(["None"] + [c_.title() for c_ in pvp_packs.COLORS])
        self.pack_box.setCurrentText(self.cfg["pvp_pack"].title())
        self.pack_box.activated.connect(lambda _: (self.sfx.play("select"), self._save_settings()))
        g.addWidget(self.pack_box, 2, 1)
        g.addWidget(label("Recolors obsidian, crystals, anchors, glowstone, crosshair, sky...", "muted"), 3, 1, 1, 2)
        lay.addWidget(c)

        self.play_btn = primary(QPushButton("Play"))
        self.play_btn.setMinimumHeight(52)
        self.play_btn.setStyleSheet("font-size: 17px;")
        self.play_btn.clicked.connect(self.play)
        lay.addWidget(self.play_btn)
        self.status_lbl = label("Loading versions...", "muted")
        lay.addWidget(self.status_lbl)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 1)
        lay.addWidget(self.progress)
        lay.addStretch(1)
        return page

    # ---------- mods page ----------
    def _build_mods(self):
        page, lay = self._page()
        lay.addLayout(header("Mods", "Browse Modrinth and install Fabric mods in one click."))
        row = QHBoxLayout()
        self.mod_query = QLineEdit()
        self.mod_query.setPlaceholderText("Search mods...")
        self.mod_query.returnPressed.connect(self.search_clicked)
        row.addWidget(self.mod_query, 1)
        sb = primary(QPushButton("Search"))
        sb.clicked.connect(self.search_clicked)
        row.addWidget(sb)
        ob = QPushButton("Open mods folder")
        ob.clicked.connect(self.open_mods_folder)
        row.addWidget(ob)
        lay.addLayout(row)
        self.mods_hint = label("", "muted")
        lay.addWidget(self.mods_hint)
        self.mod_status_lbl = label("", "muted")
        lay.addWidget(self.mod_status_lbl)

        self.mod_scroll = QScrollArea()
        self.mod_scroll.setWidgetResizable(True)
        self.mod_list = QWidget()
        self.mod_list_lay = QVBoxLayout(self.mod_list)
        self.mod_list_lay.setContentsMargins(0, 0, 8, 0)
        self.mod_list_lay.setSpacing(10)
        self.mod_list_lay.addStretch(1)
        self.mod_scroll.setWidget(self.mod_list)
        lay.addWidget(self.mod_scroll, 1)
        self._mods_loaded = False
        self.nav_group.buttonClicked.connect(self._maybe_load_mods)
        return page

    def _set_mod_status(self, text):
        self.mod_status_lbl.setText(text)
        self.mod_status_lbl.setVisible(bool(text))

    def _maybe_load_mods(self, btn):
        if btn is self.nav_buttons[1] and not self._mods_loaded:
            self._mods_loaded = True
            self.search_clicked()

    def _update_mods_hint(self):
        v = self.version_box.currentText() or "any version"
        fab = "" if self.fabric_cb.isChecked() else " Tick Fabric on the Play page to load them."
        self.mods_hint.setText(f"Showing Fabric mods for Minecraft {v}.{fab}")

    def _mods_dir(self):
        return Path(self.cfg["minecraft_dir"]) / "mods"

    def open_mods_folder(self):
        d = self._mods_dir()
        d.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(d)))

    def search_clicked(self):
        self.mod_search_id += 1
        sid = self.mod_search_id
        q, v = self.mod_query.text().strip(), self.version_box.currentText()
        self._update_mods_hint()
        self._set_mod_status("Searching Modrinth...")

        def work():
            try:
                self.bus.mods.emit(sid, search_mods(q, v), "")
            except Exception as e:
                self.bus.mods.emit(sid, [], "Couldn't reach Modrinth - check your connection and search again.")
        threading.Thread(target=work, daemon=True).start()

    def _on_mods(self, sid, hits, err):
        if sid != self.mod_search_id:
            return
        while self.mod_list_lay.count() > 1:
            it = self.mod_list_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.icon_labels.clear()
        self._set_mod_status(err or ("" if hits else "No mods found for this version."))
        for h in hits:
            self.mod_list_lay.insertWidget(self.mod_list_lay.count() - 1, self._mod_card(h))

    def _mod_card(self, h):
        c = card()
        row = QHBoxLayout(c)
        row.setContentsMargins(14, 12, 14, 12)
        row.setSpacing(14)
        ic = QLabel()
        ic.setObjectName("modicon")
        ic.setFixedSize(52, 52)
        row.addWidget(ic)
        pid = h["project_id"]
        self.icon_labels[pid] = ic
        if h.get("icon_url"):
            def fetch(url=h["icon_url"], pid=pid):
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                    with urllib.request.urlopen(req, timeout=15) as r:
                        self.bus.icon.emit(pid, r.read())
                except Exception:
                    pass
            threading.Thread(target=fetch, daemon=True).start()
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(label(h.get("title", "?"), "h2"))
        col.addWidget(label(h.get("description", ""), "muted"))
        dl = h.get("downloads", 0)
        col.addWidget(label(f"{dl:,} downloads  -  by {h.get('author', '?')}", "muted"))
        row.addLayout(col, 1)
        btn = primary(QPushButton("Install"))
        btn.setFixedWidth(110)
        btn.clicked.connect(lambda _=False, b=btn, p=pid, t=h.get("title", "mod"): self.install_clicked(b, p, t))
        row.addWidget(btn)
        return c

    def _on_icon(self, pid, data):
        lbl = self.icon_labels.get(pid)
        if lbl is None:
            return
        pm = QPixmap()
        if not pm.loadFromData(data):
            return
        pm = pm.scaled(52, 52, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                       Qt.TransformationMode.SmoothTransformation)
        out = QPixmap(52, 52)
        out.fill(Qt.GlobalColor.transparent)
        p = QPainter(out)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, 52, 52, 10, 10)
        p.setClipPath(path)
        p.drawPixmap(0, 0, pm)
        p.end()
        lbl.setPixmap(out)

    def install_clicked(self, btn, pid, title):
        version = self.version_box.currentText()
        if not version:
            self._set_mod_status("Pick a Minecraft version on the Play page first.")
            return
        btn.setEnabled(False)
        btn.setText("Installing...")
        self._install_btns = getattr(self, "_install_btns", {})
        self._install_btns[pid] = btn
        mods_dir = self._mods_dir()

        def work():
            try:
                names = install_mod(pid, version, mods_dir)
                extra = f" (+{len(names) - 1} required)" if len(names) > 1 else ""
                self.bus.mod_status.emit(f"Installed {title}{extra}.")
                self.bus.mod_installed.emit(pid)
            except Exception as e:
                self.bus.mod_status.emit(f"{title}: {e}")
                self.bus.mod_installed.emit("!" + pid)
        threading.Thread(target=work, daemon=True).start()

    def _on_mod_installed(self, pid):
        failed = pid.startswith("!")
        btn = getattr(self, "_install_btns", {}).get(pid.lstrip("!"))
        if btn is not None:
            try:
                btn.setEnabled(failed)
                btn.setText("Retry" if failed else "Installed")
            except RuntimeError:
                pass  # card was replaced by a newer search

    # ---------- appearance page ----------
    def _build_appearance(self):
        page, lay = self._page()
        lay.addLayout(header("Appearance", "Recolor the whole launcher. Changes apply instantly and are saved."))

        c = card()
        cl = QVBoxLayout(c)
        cl.setContentsMargins(22, 18, 22, 18)
        cl.addWidget(label("Presets", "h2"))
        row = QHBoxLayout()
        for name, th in PRESETS.items():
            b = QPushButton(name)
            b.setIcon(dot_icon(th["accent"]))
            b.clicked.connect(lambda _=False, th=th: self.apply_theme(dict(th)))
            row.addWidget(b)
        row.addStretch(1)
        cl.addLayout(row)
        lay.addWidget(c)

        c2 = card()
        g = QGridLayout(c2)
        g.setContentsMargins(22, 18, 22, 18)
        g.setHorizontalSpacing(14)
        g.setVerticalSpacing(12)
        g.addWidget(label("Custom colors", "h2"), 0, 0, 1, 4)
        self.swatches, self.hex_edits = {}, {}
        for i, (key, title) in enumerate((("bg", "Background"), ("surface", "Cards & sidebar"),
                                          ("accent", "Accent"), ("text", "Text")), start=1):
            g.addWidget(QLabel(title), i, 0)
            sw = QPushButton()
            sw.setFixedSize(54, 32)
            sw.clicked.connect(lambda _=False, k=key: self.pick_color(k))
            g.addWidget(sw, i, 1)
            he = QLineEdit()
            he.setMaximumWidth(110)
            he.editingFinished.connect(lambda k=key: self.hex_edited(k))
            g.addWidget(he, i, 2)
            self.swatches[key], self.hex_edits[key] = sw, he
        g.setColumnStretch(3, 1)
        reset = QPushButton("Reset to default")
        reset.setProperty("ghost", True)
        reset.clicked.connect(lambda: self.apply_theme(dict(DEFAULT_THEME)))
        g.addWidget(reset, 5, 0, 1, 2)
        lay.addWidget(c2)
        lay.addStretch(1)
        return page

    def pick_color(self, key):
        col = QColorDialog.getColor(QColor(self.cfg["theme"][key]), self, f"Pick {key} color")
        if col.isValid():
            self.apply_theme({**self.cfg["theme"], key: col.name()})

    def hex_edited(self, key):
        txt = self.hex_edits[key].text().strip()
        if not txt.startswith("#"):
            txt = "#" + txt
        if QColor(txt).isValid():
            self.apply_theme({**self.cfg["theme"], key: QColor(txt).name()})
        else:
            self.hex_edits[key].setText(self.cfg["theme"][key])

    def apply_theme(self, theme, save=True):
        theme = clean_theme(theme)
        self.cfg["theme"] = theme
        QApplication.instance().setStyleSheet(build_qss(theme))
        for k, sw in self.swatches.items():
            sw.setStyleSheet(f"background: {theme[k]}; border: 2px solid {mix(theme['surface'], theme['text'], 0.35)};"
                             " border-radius: 8px;")
            self.hex_edits[k].setText(theme[k])
        if save:
            save_config(self.cfg)

    # ---------- settings page ----------
    def _build_settings(self):
        page, lay = self._page()
        lay.addLayout(header("Settings", "Memory, folders, sign-in and sounds."))
        c = card()
        g = QGridLayout(c)
        g.setContentsMargins(22, 20, 22, 20)
        g.setHorizontalSpacing(14)
        g.setVerticalSpacing(14)
        g.setColumnStretch(1, 1)

        g.addWidget(label("Memory", "h2"), 0, 0)
        self.ram_slider = QSlider(Qt.Orientation.Horizontal)
        self.ram_slider.setRange(2, 64)  # steps of 512 MB -> 1..32 GB
        self.ram_slider.setValue(max(2, min(64, round(self.cfg["ram_mb"] / 512))))
        self.ram_lbl = QLabel()
        self.ram_slider.valueChanged.connect(self._ram_changed)
        g.addWidget(self.ram_slider, 0, 1)
        g.addWidget(self.ram_lbl, 0, 2)
        self._ram_changed()

        g.addWidget(label("Game folder", "h2"), 1, 0)
        self.dir_edit = QLineEdit(self.cfg["minecraft_dir"])
        self.dir_edit.editingFinished.connect(self._save_settings)
        g.addWidget(self.dir_edit, 1, 1)
        browse = QPushButton("Browse")
        browse.clicked.connect(self._browse_dir)
        g.addWidget(browse, 1, 2)

        g.addWidget(label("Azure client ID", "h2"), 2, 0)
        self.cid_edit = QLineEdit(self.cfg["client_id"])
        self.cid_edit.setPlaceholderText("paste your Azure app's Application (client) ID")
        self.cid_edit.editingFinished.connect(self._save_settings)
        g.addWidget(self.cid_edit, 2, 1, 1, 2)
        g.addWidget(label("One-time setup so Microsoft lets this launcher sign you in. "
                          "Steps are in the README.", "muted"), 3, 1, 1, 2)

        self.demo_cb = QCheckBox("Demo mode (no sign-in needed)")
        self.demo_cb.setChecked(self.cfg["demo"])
        self.demo_cb.toggled.connect(lambda _: self._save_settings())
        g.addWidget(self.demo_cb, 4, 1, 1, 2)
        self.sound_cb = QCheckBox("UI sounds")
        self.sound_cb.setChecked(self.cfg["sounds"])
        self.sound_cb.toggled.connect(lambda _: self._save_settings())
        g.addWidget(self.sound_cb, 5, 1, 1, 2)
        lay.addWidget(c)
        lay.addStretch(1)
        return page

    def _ram_changed(self):
        self.ram_lbl.setText(f"{self.ram_slider.value() * 512 / 1024:.1f} GB")
        if hasattr(self, "dir_edit"):
            self._save_settings()

    def _browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Choose game folder", self.dir_edit.text())
        if d:
            self.dir_edit.setText(d)
            self._save_settings()

    def _save_settings(self):
        self.cfg.update({
            "ram_mb": self.ram_slider.value() * 512,
            "minecraft_dir": self.dir_edit.text().strip() or DEFAULT_MC_DIR,
            "client_id": self.cid_edit.text().strip(),
            "show_snapshots": self.snap_cb.isChecked(),
            "use_fabric": self.fabric_cb.isChecked(),
            "demo": self.demo_cb.isChecked(),
            "sounds": self.sound_cb.isChecked(),
            "pvp_pack": self.pack_box.currentText().lower(),
            "last_version": self.version_box.currentText() or self.cfg["last_version"],
        })
        self.sfx.enabled = self.cfg["sounds"]
        save_config(self.cfg)

    # ---------- versions ----------
    def _load_versions(self):
        try:
            self.bus.versions.emit(mll.utils.get_version_list())
        except Exception:
            self.bus.status.emit("Couldn't reach Mojang's servers to load versions - check your connection and restart.")

    def _on_versions(self, versions):
        self.versions = versions
        self._fill_versions()

    def _fill_versions(self):
        types = {"release"} | ({"snapshot"} if self.snap_cb.isChecked() else set())
        ids = [v["id"] for v in self.versions if v["type"] in types]
        self.version_box.blockSignals(True)
        self.version_box.clear()
        self.version_box.addItems(ids)
        last = self.cfg.get("last_version")
        self.version_box.setCurrentText(last if last in ids else (ids[0] if ids else ""))
        self.version_box.blockSignals(False)
        self.status_lbl.setText("Ready")
        self._update_mods_hint()

    def _version_changed(self, _):
        if self.version_box.currentText():
            self._save_settings()
            self._update_mods_hint()

    # ---------- account ----------
    def _refresh_account(self):
        acc = self.cfg.get("account")
        if acc:
            self.acc_name.setText(acc["name"])
            self.avatar.setText(acc["name"][:1].upper())
            self.acc_btn.setText("Sign out")
        else:
            self.acc_name.setText("Not signed in")
            self.avatar.setText("?")
            self.acc_btn.setText("Sign in")

    def account_clicked(self):
        if self.cfg.get("account"):
            self.cfg["account"] = None
            save_config(self.cfg)
            self._refresh_account()
        else:
            self.start_login()

    def start_login(self):
        self._save_settings()
        cid = self.cfg["client_id"]
        if not cid:
            self.nav_buttons[3].setChecked(True)
            self.stack.setCurrentIndex(3)
            self.sfx.play("error")
            QMessageBox.information(self, "Azure client ID needed",
                                    "Paste your Azure client ID in Settings first (steps are in the README).")
            return
        self.acc_btn.setEnabled(False)
        self.acc_name.setText("Waiting for browser...")
        threading.Thread(target=self._login_worker, args=(cid,), daemon=True).start()

    def _login_worker(self, cid):
        try:
            url, state, verifier = mll.microsoft_account.get_secure_login_data(cid, REDIRECT_URI)
            try:
                srv = open_callback_server(self.cfg["theme"])
            except OSError:
                raise RuntimeError(f"Port {CALLBACK_PORT} is busy - close whatever is using it and try again.")
            webbrowser.open(url)
            cb = wait_for_callback(srv)
            if not cb:
                raise RuntimeError("Sign-in timed out. Try again.")
            err = callback_error(cb)
            if err:
                raise RuntimeError(f"Microsoft refused the sign-in: {err}")
            code = mll.microsoft_account.parse_auth_code_url(cb, state)
            data = mll.microsoft_account.complete_login(cid, None, REDIRECT_URI, code, verifier)
            acc = {"name": data["name"], "id": data["id"], "refresh_token": data["refresh_token"]}
            self.bus.login_done.emit(acc, "")
        except Exception as e:
            self.bus.login_done.emit(None, friendly_login_error(e))

    def _on_login_done(self, acc, err):
        self.acc_btn.setEnabled(True)
        if acc:
            self.cfg["account"] = acc
            save_config(self.cfg)
            self.sfx.play("success")
        else:
            self.sfx.play("error")
            QMessageBox.warning(self, "Sign-in failed", err)
        self._refresh_account()

    def _get_session(self):
        acc = self.cfg["account"]
        data = mll.microsoft_account.complete_refresh(self.cfg["client_id"], None, REDIRECT_URI, acc["refresh_token"])
        acc.update({"name": data["name"], "id": data["id"], "refresh_token": data["refresh_token"]})
        save_config(self.cfg)
        return data["name"], data["id"], data["access_token"]

    # ---------- play ----------
    def _on_progress(self, value, maximum):
        if maximum >= 0:
            self.progress.setMaximum(max(maximum, 1))
        self.progress.setValue(value)

    def play(self):
        if self.busy:
            return
        version = self.version_box.currentText()
        if not version:
            self.sfx.play("error")
            self.status_lbl.setText("Select a Minecraft version first.")
            return
        self._save_settings()
        if not self.cfg["demo"] and not self.cfg["account"]:
            self.sfx.play("error")
            QMessageBox.information(self, "Sign in first",
                                    "Sign in with Microsoft (bottom-left), or tick Demo mode in Settings.")
            return
        self.sfx.play("play")
        self.busy = True
        self.play_btn.setEnabled(False)
        threading.Thread(target=self._play_worker, args=(version,), daemon=True).start()

    def _play_worker(self, version):
        mc_dir = self.cfg["minecraft_dir"]
        b = self.bus
        callback = {
            "setStatus": lambda t: b.status.emit(t),
            "setProgress": lambda v: b.progress.emit(int(v), -1),
            "setMax": lambda m: b.progress.emit(0, int(m)),
        }
        try:
            launch_id = version
            if self.cfg["use_fabric"]:
                b.status.emit("Installing Fabric...")
                mll.mod_loader.get_mod_loader("fabric").install(version, mc_dir, callback=callback)
                ids = [v["id"] for v in mll.utils.get_installed_versions(mc_dir)
                       if v["id"].startswith("fabric-loader") and v["id"].endswith(version)]
                if not ids:
                    raise RuntimeError("Fabric install finished but version not found.")
                launch_id = ids[-1]
            else:
                b.status.emit("Installing / verifying files...")
                mll.install.install_minecraft_version(version, mc_dir, callback=callback)

            b.status.emit("Applying PvP pack...")
            try:
                pack_msg = pvp_packs.apply_pack(mc_dir, version, self.cfg["pvp_pack"])
            except Exception as e:  # a pack problem never blocks launching
                pack_msg = f"PvP pack skipped: {e}"

            ram = self.cfg["ram_mb"]
            options = {"jvmArguments": [f"-Xmx{ram}M", f"-Xms{min(ram, 1024)}M"]}
            if self.cfg["demo"]:
                options.update({"username": "Player", "uuid": "", "token": "", "demo": True})
            else:
                b.status.emit("Signing in...")
                name, uuid, token = self._get_session()
                options.update({"username": name, "uuid": uuid, "token": token})

            cmd = mll.command.get_minecraft_command(launch_id, mc_dir, options)
            b.status.emit("Launching Minecraft...")
            subprocess.Popen(cmd, cwd=mc_dir)
            b.play_done.emit(True, f"Minecraft started. {pack_msg}")
        except Exception as e:
            b.play_done.emit(False, friendly_login_error(e))

    def _on_play_done(self, ok, msg):
        self.busy = False
        self.play_btn.setEnabled(True)
        self.status_lbl.setText(msg)
        self.progress.setValue(self.progress.maximum() if ok else 0)
        self.sfx.play("success" if ok else "error")


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Chrome Client")
    w = Launcher()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
