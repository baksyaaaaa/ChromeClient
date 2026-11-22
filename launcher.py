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
import re
import math
import shutil
import zipfile
import subprocess
import os
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path
from string import Template

import minecraft_launcher_lib as mll
from PySide6.QtCore import QEasingCurve, QEvent, QEventLoop, QObject, QPointF, QRectF, QPropertyAnimation, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (QColor, QDesktopServices, QIcon, QLinearGradient, QMouseEvent, QPainter, QPainterPath,
                           QPen, QPixmap, QImage, QRadialGradient)
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog,
    QFrame, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout, QInputDialog, QLabel as _QLabel, QLineEdit,
    QMainWindow, QMessageBox as _QMessageBox, QProgressBar, QPushButton as _QPushButton, QScrollArea, QSlider as _QSlider,
    QStackedWidget, QStyle, QStyleOptionButton, QStyleOptionSlider, QStylePainter, QVBoxLayout, QWidget,
)

# ---------------------------------------------------------------------------
# Ad blocking for the Create tab's built-in browser (blocks well-known ad networks, hides empty ad slots)
# ---------------------------------------------------------------------------
AD_DOMAINS = (
    "doubleclick.net", "googlesyndication.com", "googleadservices.com", "adservice.google.com", "adsense.google.com",
    "2mdn.net", "amazon-adsystem.com", "adnxs.com", "adsystem.com", "taboola.com", "outbrain.com", "criteo.com",
    "criteo.net", "pubmatic.com", "rubiconproject.com", "openx.net", "adsterra.com", "propellerads.com",
    "popads.net", "popcash.net", "mgid.com", "monetag.com", "a-ads.com", "coinzilla.com", "carbonads.net",
    "carbonads.com", "buysellads.com", "ethicalads.io", "snigelweb.com", "nitropay.com", "ad.plus", "adinplay.com",
    "publift.com", "fuseplatform.net", "indexww.com", "casalemedia.com", "smartadserver.com", "sharethrough.com",
    "teads.tv", "media.net", "bidswitch.net", "adform.net", "lijit.com", "sovrn.com", "gumgum.com", "yieldmo.com",
    "triplelift.com", "33across.com", "adthrive.com", "mediavine.com", "ezoic.net", "ezodn.com", "moatads.com",
    "adsrvr.org", "adition.com", "advertising.com", "adcolony.com", "applovin.com", "revcontent.com",
    "zemanta.com", "adroll.com", "quantserve.com", "scorecardresearch.com", "ads-twitter.com", "hotjar.com",
)
AD_HIDE_CSS = (
    "ins.adsbygoogle, .adsbygoogle, [id^='google_ads_'], [id^='div-gpt-ad'], [data-ad-slot], [data-ad-client], "
    "[data-google-query-id], iframe[src*='doubleclick'], iframe[src*='googlesyndication'], iframe[id^='google_ads'], "
    "iframe[src*='adnxs'], iframe[src*='taboola'], iframe[src*='outbrain'], .ad-slot, .ad-container, .ad-banner, "
    ".advert, .advertisement, [class*='adsbox'], [id*='ad-slot'], [aria-label='Advertisement'] "
    "{ display: none !important; visibility: hidden !important; height: 0 !important; min-height: 0 !important; }"
)


def is_ad_host(host):
    host = (host or "").lower().rstrip(".")
    return any(host == d or host.endswith("." + d) for d in AD_DOMAINS if "/" not in d)


# ---------------------------------------------------------------------------
# Privacy: hide your Windows username / folder paths in everything the launcher shows
# ---------------------------------------------------------------------------
HIDE_PATHS = True


def scrub(text):
    """Replace your home folder (which contains your Windows username) with ~ in text shown on screen."""
    if not HIDE_PATHS or not isinstance(text, str) or not text:
        return text
    import re
    home = str(Path.home())
    user = Path.home().name
    for variant in {home, home.replace("\\", "/"), home.replace("/", "\\")}:
        text = re.sub(re.escape(variant), "~", text, flags=re.IGNORECASE)
    if user:
        text = re.sub(r"([\\/])" + re.escape(user) + r"(?=[\\/]|$)", r"\1user", text, flags=re.IGNORECASE)
    return text


class QLabel(_QLabel):
    """Label that never shows your username inside a folder path."""
    def __init__(self, *a, **kw):
        a = tuple(scrub(x) if isinstance(x, str) else x for x in a)
        super().__init__(*a, **kw)

    def setText(self, t):
        super().setText(scrub(t))


class QMessageBox(_QMessageBox):
    """Message boxes with paths scrubbed as well."""
    @staticmethod
    def warning(parent, title, text, *a, **k):
        return _QMessageBox.warning(parent, scrub(title), scrub(text), *a, **k)

    @staticmethod
    def information(parent, title, text, *a, **k):
        return _QMessageBox.information(parent, scrub(title), scrub(text), *a, **k)

    @staticmethod
    def critical(parent, title, text, *a, **k):
        return _QMessageBox.critical(parent, scrub(title), scrub(text), *a, **k)

    @staticmethod
    def question(parent, title, text, *a, **k):
        return _QMessageBox.question(parent, scrub(title), scrub(text), *a, **k)


class QSlider(_QSlider):
    """Slider that behaves: clicking the bar jumps there (and keeps dragging), and the mouse wheel only
    changes it when it has focus - so scrolling a page over it doesn't accidentally move it."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _handle_rect(self):
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        return opt, self.style().subControlRect(QStyle.ComplexControl.CC_Slider, opt,
                                                QStyle.SubControl.SC_SliderHandle, self)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and self.orientation() == Qt.Orientation.Horizontal:
            opt, handle = self._handle_rect()
            if not handle.contains(ev.position().toPoint()):
                groove = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, opt,
                                                     QStyle.SubControl.SC_SliderGroove, self)
                span = max(1, groove.width() - handle.width())
                x = ev.position().x() - handle.width() / 2 - groove.x()
                self.setValue(QStyle.sliderValueFromPosition(self.minimum(), self.maximum(),
                                                             int(max(0, min(span, x))), span, opt.upsideDown))
                _, handle = self._handle_rect()
                ev = QMouseEvent(ev.type(), QPointF(handle.center()), ev.globalPosition(),
                                 ev.button(), ev.buttons(), ev.modifiers())
        super().mousePressEvent(ev)

    def wheelEvent(self, ev):
        if self.hasFocus():
            super().wheelEvent(ev)
        else:
            ev.ignore()  # let the page scroll instead


class QPushButton(_QPushButton):
    """A normal button, except that text which doesn't fit slowly scrolls from right to left."""
    _GAP, _PAUSE = 24, 22  # px of blank space before the text loops, ticks to wait at each end

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._off = 0.0
        self._wait = self._PAUSE
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)

    def _geometry(self):
        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        area = self.style().subElementRect(QStyle.SubElement.SE_PushButtonContents, opt, self)
        icon_w = (self.iconSize().width() + 4) if not self.icon().isNull() else 0
        text_w = self.fontMetrics().horizontalAdvance(self.text())
        return opt, area, icon_w + text_w

    def _overflowing(self):
        if not self.text():
            return False
        _, area, need = self._geometry()
        return need > area.width() + 1

    def _sync_timer(self):
        if self.isVisible() and self._overflowing():
            if not self._timer.isActive():
                self._off, self._wait = 0.0, self._PAUSE
                self._timer.start()
        elif self._timer.isActive():
            self._timer.stop()
            self._off = 0.0
            self.update()

    def showEvent(self, ev):
        super().showEvent(ev)
        self._sync_timer()

    def hideEvent(self, ev):
        super().hideEvent(ev)
        self._timer.stop()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._sync_timer()

    def setText(self, t):
        super().setText(t)
        self._sync_timer()

    def _tick(self):
        if not self._overflowing():
            self._sync_timer()
            return
        _, area, need = self._geometry()
        span = need - area.width() + self._GAP
        if self._wait > 0:
            self._wait -= 1
        else:
            self._off += 1.2
            if self._off >= span:  # reached the end: pause, then jump back
                self._off, self._wait = 0.0, self._PAUSE
        self.update()

    def paintEvent(self, ev):
        if not self._timer.isActive():
            return super().paintEvent(ev)
        p = QStylePainter(self)
        opt, area, need = self._geometry()
        label = QStyleOptionButton(opt)
        opt.text = ""
        opt.icon = QIcon()
        p.drawControl(QStyle.ControlElement.CE_PushButton, opt)  # background + border only
        p.setClipRect(area)
        label.rect = area.adjusted(-int(self._off), 0, 0, 0)
        label.rect.setWidth(need + 8)
        p.drawControl(QStyle.ControlElement.CE_PushButtonLabel, label)
        p.end()


import discord_rpc
import library
import mods_sync
import pvp_packs  # only used to clean up packs older versions generated
import sounds
from sounds import EVENTS, LIB_DIR, SoundPlayer

APP_DIR = Path.home() / ".simple_mc_launcher"
CONFIG_FILE = APP_DIR / "config.json"
ICON_DIR = APP_DIR / "theme_icons"
BG_DIR = APP_DIR / "backgrounds"
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


# the default look: flat dark panels, soft lavender accent, big rounded corners, Poppins
CHROME_THEME = {"bg": "#0a0c13", "surface": "#151922", "accent": "#9aa5ff", "text": "#f3f5ff",
                "style": "one", "mode": "solid", "glass": 0, "dim": 0}

PRESETS = {"Chrome": dict(CHROME_THEME), "Classic": dict(DEFAULT_THEME),
           **{n: tinted_theme(c) for n, c in ACCENTS.items()}}


def mix(a, b, t):
    ca, cb = QColor(a), QColor(b)
    return QColor(round(ca.red() * (1 - t) + cb.red() * t),
                  round(ca.green() * (1 - t) + cb.green() * t),
                  round(ca.blue() * (1 - t) + cb.blue() * t)).name()


def luminance(c):
    c = QColor(c)
    return 0.2126 * c.red() / 255 + 0.7152 * c.green() / 255 + 0.0722 * c.blue() / 255


def shift_hue(c, deg):
    q = QColor(c)
    h, s, v, _ = q.getHsvF()
    if h < 0:
        return q.name()
    return QColor.fromHsvF(((h * 360 + deg) % 360) / 360, s, v).name()


def rgba(c, a):
    q = QColor(c)
    return f"rgba({q.red()},{q.green()},{q.blue()},{int(max(0, min(1, a)) * 255)})"


BG_MODES = ("solid", "gradient", "image")
BG_DEFAULTS = {"mode": "solid", "grad": ["#2b1055", "#c0392b", "#ff9a56"], "angle": 135,
               "image": "", "dim": 30, "glass": 65}
# name -> (gradient stops, accent)
GRADIENTS = {
    "Sunset": (["#2b1055", "#c0392b", "#ff9a56"], "#ff8a5c"),
    "Ocean": (["#021b3a", "#0b6fa4", "#26d0ce"], "#2fd3e0"),
    "Aurora": (["#0b1a2e", "#14746f", "#7b2ff7"], "#3ee6a8"),
    "Cherry": (["#2a0a1e", "#8e1e5a", "#ff5fa8"], "#ff5fa8"),
    "Midnight": (["#05050f", "#141e4a", "#4b2a8a"], "#8b7bff"),
    "Mint": (["#06201a", "#0f5a46", "#1bd96a"], "#1bd96a"),
    "Evolution": (["#0d0a1f", "#2a1a5e", "#6b3fd4"], "#8b6cff"),
}


def gradient_theme(stops, accent):
    return {"bg": mix(stops[0], "#000000", 0.35), "surface": mix(stops[1], "#000000", 0.55),
            "accent": accent, "text": "#f3f1f6", "mode": "gradient", "grad": list(stops),
            "angle": 135, "dim": 20, "glass": 62}


def clean_theme(t):
    t = t if isinstance(t, dict) else {}
    out = dict(DEFAULT_THEME)
    for k in DEFAULT_THEME:
        if QColor(str(t.get(k, ""))).isValid():
            out[k] = QColor(t[k]).name()
    out["style"] = "one" if t.get("style") == "one" else "glass"
    out["mode"] = t.get("mode") if t.get("mode") in BG_MODES else BG_DEFAULTS["mode"]
    g = t.get("grad")
    stops = [QColor(c).name() for c in g if isinstance(c, str) and QColor(c).isValid()] if isinstance(g, list) else []
    out["grad"] = stops[:3] if len(stops) >= 2 else list(BG_DEFAULTS["grad"])
    for k, lo, hi in (("angle", 0, 360), ("dim", 0, 85), ("glass", 0, 100)):
        try:
            out[k] = max(lo, min(hi, int(t.get(k, BG_DEFAULTS[k]))))
        except (TypeError, ValueError):
            out[k] = BG_DEFAULTS[k]
    img = t.get("image")
    out["image"] = img if isinstance(img, str) and img and Path(img).is_file() else ""
    return out


def picture_colors(path):
    """Pick background / cards / accent colors from a picture (dark base colors + one vivid accent)."""
    from PIL import Image
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((128, 128))
        q = im.quantize(colors=8, method=Image.Quantize.MEDIANCUT)
        pal = q.getpalette()[:24]
        counts = sorted(q.getcolors(), reverse=True)  # [(count, index)]
    total = sum(n for n, _ in counts)
    cols = []
    for n, i in counts:
        c = QColor(pal[i * 3], pal[i * 3 + 1], pal[i * 3 + 2])
        h, sat, v, _ = c.getHsvF()
        cols.append((n / total, c, max(h, 0.0), sat, v))
    # accent: the most vivid color that covers a visible part of the picture
    pool = [c for c in cols if c[0] >= 0.02 and c[3] > 0.25] or cols
    _, ac, ah, asat, av = max(pool, key=lambda c: c[3] * c[4] ** 2 * (0.3 + c[0] ** 0.5))
    accent = QColor.fromHsvF(ah, max(asat, 0.55), max(av, 0.85)).name()
    # bg / cards: the two most common colors, darkened so light text stays readable
    base = [c for c in cols if c[1].name() != ac.name()] or cols
    _, c1, h1, s1, _v1 = base[0]
    c2h, c2s = (base[1][2], base[1][3]) if len(base) > 1 else (h1, s1)
    bg = QColor.fromHsvF(h1, min(s1, 0.75), 0.10).name()
    surface = QColor.fromHsvF(c2h, min(c2s, 0.65), 0.18).name()
    return {"bg": bg, "surface": surface, "accent": accent, "text": "#f3f1f6"}


def bg_pictures():
    """Your saved background pictures, newest first."""
    if not BG_DIR.is_dir():
        return []
    return sorted(BG_DIR.glob("*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)


def bg_thumb(path):
    th = BG_DIR / "thumbs" / (Path(path).stem + ".png")
    if not th.exists():
        try:
            from PIL import Image
            th.parent.mkdir(parents=True, exist_ok=True)
            with Image.open(path) as im:
                im = im.convert("RGB")
                im.thumbnail((240, 136))
                im.save(th, "PNG")
        except Exception:
            return None
    return th


def save_bg_picture(src):
    """Copy a picture into your saved library (shrunk to fit 2560x1600). Same picture twice = one copy."""
    from PIL import Image
    BG_DIR.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as im:
        im = im.convert("RGB")
        im.thumbnail((2560, 1600))
        digest = hashlib.sha1(im.resize((32, 32)).tobytes()).hexdigest()[:8]
        stem = "".join(c if c.isalnum() or c in " -_" else "_" for c in Path(src).stem).strip()[:40] or "picture"
        dest = BG_DIR / f"{stem}_{digest}.jpg"
        if not dest.exists():
            im.save(dest, "JPEG", quality=90)
    dest.touch()  # newest first
    bg_thumb(dest)
    return dest


_PIX_CACHE = {}


def load_bg_pixmap(path):
    if not path:
        return None
    if path not in _PIX_CACHE:
        pm = QPixmap(path)
        _PIX_CACHE.clear()
        _PIX_CACHE[path] = None if pm.isNull() else pm
    return _PIX_CACHE[path]


def card_alpha(theme):
    """How see-through the cards are: 'Glass' slider 0 = nearly solid, 100 = almost clear glass."""
    return 0.92 - 0.82 * theme["glass"] / 100


def paint_background(p, rect, theme, pix=None):
    """Paint the app background (solid / gradient / image) plus the darkening layer."""
    w, h = rect.width(), rect.height()
    mode = theme["mode"]
    painted = False
    if mode == "gradient":
        a = math.radians(theme["angle"])
        dx, dy = math.cos(a), math.sin(a)
        half = (abs(dx) * w + abs(dy) * h) / 2
        cx, cy = rect.x() + w / 2, rect.y() + h / 2
        g = QLinearGradient(cx - dx * half, cy - dy * half, cx + dx * half, cy + dy * half)
        stops = theme["grad"]
        for i, c in enumerate(stops):
            g.setColorAt(i / (len(stops) - 1), QColor(c))
        p.fillRect(rect, g)
        painted = True
    elif mode == "image" and pix is not None and not pix.isNull():
        p.fillRect(rect, QColor(theme["bg"]))
        # `pix` is already scaled to cover the rect; just center it
        p.drawPixmap(rect.x() + (w - pix.width()) // 2, rect.y() + (h - pix.height()) // 2, pix)
        painted = True
    if not painted:
        p.fillRect(rect, QColor(theme["bg"]))
        # soft color glows so the glass cards have something to show through even on a plain background
        big = max(w, h)
        for (fx, fy, rad, col, al) in ((0.12, 0.08, 0.62, theme["accent"], 115),
                                       (0.92, 0.98, 0.55, shift_hue(theme["accent"], 32), 90),
                                       (0.88, 0.05, 0.35, shift_hue(theme["accent"], -40), 50)):
            c = QColor(col)
            g = QRadialGradient(rect.x() + fx * w, rect.y() + fy * h, rad * big)
            if theme.get("style") == "one":
                al = int(al * 0.4)   # the flat look keeps only a faint glow
            c.setAlpha(al)
            g.setColorAt(0, c)
            c.setAlpha(0)
            g.setColorAt(1, c)
            p.fillRect(rect, g)
    elif theme["dim"]:
        p.fillRect(rect, QColor(0, 0, 0, int(theme["dim"] * 2.55)))


class Backdrop(QWidget):
    """A widget that paints the themed background (used for the window and the live preview)."""
    def __init__(self):
        super().__init__()
        self.theme = clean_theme(None)
        self._scaled = None  # (key, pixmap)

    def set_theme(self, theme):
        self.theme = theme
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint(p)
        p.end()

    def _paint(self, p):
        pix = load_bg_pixmap(self.theme["image"]) if self.theme["mode"] == "image" else None
        if pix is not None:
            # scale once per size, not on every repaint
            w, h = self.width(), self.height()
            key = (self.theme["image"], w, h)
            if not self._scaled or self._scaled[0] != key:
                scale = max(w / pix.width(), h / pix.height())
                pm = pix.scaled(max(1, round(pix.width() * scale)), max(1, round(pix.height() * scale)),
                                Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self._scaled = (key, pm)
            pix = self._scaled[1]
        paint_background(p, self.rect(), self.theme, pix)


class PreviewStrip(Backdrop):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(96)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(self.rect().adjusted(0, 0, -1, -1), 8, 8)
        p.setClipPath(path)
        self._paint(p)
        # a mock card so you can judge the glass effect and text color
        t = self.theme
        a = card_alpha(t)
        p.setPen(QPen(QColor(mix(t["surface"], "#ffffff" if luminance(t["bg"]) < 0.5 else "#000000", 0.15)), 1))
        p.setBrush(self._rgba_color(t["surface"], a))
        p.drawRoundedRect(14, 14, 150, self.height() - 28, 6, 6)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t["accent"]))
        p.drawRoundedRect(26, self.height() - 40, 70, 14, 7, 7)
        p.setBrush(self._rgba_color(t["text"], 0.85))
        p.drawRoundedRect(26, 28, 90, 8, 4, 4)
        p.setBrush(self._rgba_color(t["text"], 0.45))
        p.drawRoundedRect(26, 44, 120, 6, 3, 3)
        p.end()

    @staticmethod
    def _rgba_color(c, a):
        q = QColor(c)
        q.setAlphaF(max(0.0, min(1.0, a)))
        return q


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
* { outline: none; }
* { color: $text; font-size: 13px; }
QMainWindow { background: $bg; }
QWidget#sidebar { background: $side; border-right: 1px solid $edge; }
QLabel { background: transparent; border: none; }
QLabel[muted="true"] { color: $muted; }
QLabel[h1="true"] { font-size: 26px; font-weight: 800; }
QLabel[h2="true"] { font-size: 15px; font-weight: 600; }
QLabel[brand="true"] { font-size: 19px; font-weight: 800; color: $accent; }
QLabel#modicon { background: $surface_hi; border-radius: 5px; }
QLabel#avatar { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 $accent, stop:1 $accent2); color: $accent_text; border-radius: 6px; font-weight: 700; font-size: 15px; }
QFrame[card="true"] { background: $card; border: 1px solid $border; border-top: 1px solid $edge; border-radius: 8px; }
QFrame[chip="true"] { background: $chip; border: 1px solid $border; border-top: 1px solid $edge; border-radius: 8px; }
QFrame[chip="true"]:hover { border-color: $accent; background: $chip_hi; }
QPushButton { background: $chip; border: 1px solid $border; border-top: 1px solid $edge; border-radius: 8px; padding: 8px 16px; font-weight: 600; }
QPushButton:hover { background: $chip_hi; border-color: $accent; }
QPushButton:pressed { background: $p_press; }
QPushButton:disabled { color: $muted; background: $chip; border-color: $border; }
QPushButton[primary="true"] { background: $p_fill; color: $text; border: 1px solid $p_border; border-top: 1px solid $p_edge; border-radius: 8px; }
QPushButton[primary="true"]:hover { background: $p_fill_hi; border-color: $accent; border-top: 1px solid $p_edge; }
QPushButton[primary="true"]:pressed { background: $p_press; }
QPushButton[primary="true"]:disabled { background: $chip; color: $muted; border: 1px solid $border; }
QPushButton[nav="true"] { background: transparent; border: none; border-left: 3px solid transparent; border-radius: 4px; text-align: left; padding: 10px 14px; color: $nav; font-size: 14px; }
QPushButton[nav="true"]:hover { background: $g_bg; border: none; border-left: 3px solid transparent; color: $text; }
QPushButton[nav="true"]:checked { background: transparent; color: $accent; border: none; border-left: 3px solid $accent; }
QPushButton[ghost="true"] { background: $chip; border: 1px solid $border; border-top: 1px solid $edge; }
QPushButton[ghost="true"]:hover { background: $chip_hi; }
QPushButton[seg="true"], QPushButton[pack="true"] { background: $chip; border: 2px solid $border; }
QPushButton[pack="true"] { padding: 8px 8px; }
QPushButton[seg="true"]:hover, QPushButton[pack="true"]:hover { background: $chip_hi; border-color: $accent; }
QPushButton[seg="true"]:checked, QPushButton[pack="true"]:checked { background: $p_fill; border: 2px solid $accent; }
QLineEdit, QSpinBox, QComboBox { background: $input; border: 1px solid $border; border-radius: 5px; padding: 8px 12px; selection-background-color: $accent; selection-color: $accent_text; }
QLineEdit:focus, QComboBox:focus { border: 1px solid $accent; }
QComboBox { padding-right: 30px; }
QComboBox::drop-down { border: none; width: 30px; }
QComboBox::down-arrow { image: url("$chev"); width: 12px; height: 12px; }
QComboBox QAbstractItemView { background: $surface; border: 1px solid $border; selection-background-color: $accent_soft; selection-color: $accent; outline: 0; padding: 4px; }
QCheckBox { spacing: 10px; background: transparent; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 3px; border: 2px solid $border2; background: $input; }
QCheckBox::indicator:hover { border-color: $accent; }
QCheckBox::indicator:checked { background: $accent; border-color: $accent; image: url("$check"); }
QProgressBar { background: $input; border: 1px solid $border; border-radius: 5px; min-height: 28px; max-height: 28px; color: $text; font-weight: 600; text-align: center; }
QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 $accent_fill, stop:1 $accent2_fill); border-radius: 4px; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: $border2; border-radius: 4px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QSlider::groove:horizontal { height: 8px; background: $input; border-radius: 4px; }
QSlider::sub-page:horizontal { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 $accent, stop:1 $accent2); border-radius: 4px; }
QSlider::handle:horizontal { background: $text; border: 3px solid $accent; width: 12px; height: 12px; margin: -6px 0; border-radius: 9px; }
QToolTip, QMessageBox, QDialog, QInputDialog { background: $surface; color: $text; border: 1px solid $border; }
""")


QSS_ONE = Template("""
* { outline: none; }
* { color: $text; font-size: 13px; font-family: "Poppins", "Segoe UI", sans-serif; }
QMainWindow { background: $bg; }
QWidget#sidebar { background: $side; border-right: 1px solid $border; }
QLabel { background: transparent; border: none; }
QLabel[muted="true"] { color: $muted; }
QLabel[h1="true"] { font-size: 26px; font-weight: 700; }
QLabel[h2="true"] { font-size: 15px; font-weight: 600; }
QLabel[brand="true"] { font-size: 19px; font-weight: 700; color: $accent; }
QLabel#modicon { background: $chip; border-radius: 10px; }
QLabel#avatar { background: $p_fill; color: $accent_text; border-radius: 10px; font-weight: 700; font-size: 15px; }
QFrame[card="true"] { background: $card; border: 1px solid $border; border-radius: 16px; }
QFrame[chip="true"] { background: $chip; border: 1px solid $border; border-radius: 14px; }
QFrame[chip="true"]:hover { border-color: $accent_line; background: $chip_hi; }
QPushButton { background: $chip; border: 1px solid $border2; border-radius: 12px; padding: 9px 18px; font-weight: 500; }
QPushButton:hover { background: $chip_hi; border-color: $accent_line; }
QPushButton:pressed { background: $card; }
QPushButton:disabled { color: $muted; background: $chip; border-color: $border; }
QPushButton[primary="true"] { background: $p_fill; color: $accent_text; border: none; border-radius: 12px; font-weight: 600; }
QPushButton[primary="true"]:hover { background: $p_fill_hi; }
QPushButton[primary="true"]:pressed { background: $p_press; }
QPushButton[primary="true"]:disabled { background: $chip; color: $muted; border: 1px solid $border; }
QPushButton[nav="true"] { background: transparent; border: none; border-radius: 12px; text-align: left; padding: 11px 16px; color: $nav; font-size: 14px; font-weight: 500; }
QPushButton[nav="true"]:hover { background: $chip; border: none; color: $text; }
QPushButton[nav="true"]:checked { background: $accent_soft; color: $accent; border: none; font-weight: 600; }
QPushButton[ghost="true"] { background: $chip; border: 1px solid $border2; }
QPushButton[ghost="true"]:hover { background: $chip_hi; }
QPushButton[seg="true"], QPushButton[pack="true"] { background: $chip; border: 1px solid $border2; }
QPushButton[pack="true"] { padding: 8px 8px; }
QPushButton[seg="true"]:hover, QPushButton[pack="true"]:hover { background: $chip_hi; border-color: $accent_line; }
QPushButton[seg="true"]:checked, QPushButton[pack="true"]:checked { background: $p_fill; color: $accent_text; border: none; }
QLineEdit, QSpinBox, QComboBox { background: $input; border: 1px solid $border2; border-radius: 12px; padding: 9px 14px; selection-background-color: $accent; selection-color: $accent_text; }
QLineEdit:focus, QComboBox:focus { border: 1px solid $accent; }
QComboBox { padding-right: 32px; }
QComboBox::drop-down { border: none; width: 30px; }
QComboBox::down-arrow { image: url("$chev"); width: 12px; height: 12px; }
QComboBox QAbstractItemView { background: $card; border: 1px solid $border2; border-radius: 10px; selection-background-color: $accent_soft; selection-color: $accent; outline: 0; padding: 6px; }
QCheckBox { spacing: 10px; background: transparent; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 6px; border: 2px solid $border2; background: $input; }
QCheckBox::indicator:hover { border-color: $accent; }
QCheckBox::indicator:checked { background: $accent; border-color: $accent; image: url("$check"); }
QProgressBar { background: $input; border: 1px solid $border; border-radius: 12px; min-height: 28px; max-height: 28px; color: $text; font-weight: 500; text-align: center; }
QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 $accent_deep, stop:1 $accent); border-radius: 11px; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: $border2; border-radius: 4px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QSlider::groove:horizontal { height: 8px; background: $input; border-radius: 4px; }
QSlider::sub-page:horizontal { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 $accent_deep, stop:1 $accent); border-radius: 4px; }
QSlider::handle:horizontal { background: $text; border: 3px solid $accent; width: 12px; height: 12px; margin: -6px 0; border-radius: 9px; }
QToolTip, QMessageBox, QDialog, QInputDialog { background: $card; color: $text; border: 1px solid $border2; border-radius: 10px; }
""")


def build_qss_one(t):
    bg, surf, acc, text = t["bg"], t["surface"], t["accent"], t["text"]
    accent_text = "#0c0e18" if luminance(acc) > 0.45 else "#ffffff"
    chev, check = make_icons(text, accent_text)
    deep = mix(acc, "#3b4bd0", 0.45)
    def vgrad(top, bot):
        return f"qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {top}, stop:1 {bot})"
    return QSS_ONE.substitute(
        bg=bg, text=text, accent=acc, accent_text=accent_text, chev=chev, check=check,
        side=mix(bg, surf, 0.35), card=mix(bg, surf, 0.75), chip=mix(bg, surf, 1.0), chip_hi=mix(surf, acc, 0.12),
        input=mix(bg, surf, 0.45), border=mix(surf, "#ffffff", 0.07), border2=mix(surf, "#ffffff", 0.14),
        muted=mix(text, bg, 0.45), nav=mix(text, bg, 0.30),
        accent_soft=mix(bg, acc, 0.20), accent_line=rgba(acc, 0.65), accent_deep=deep,
        p_fill=vgrad(mix(acc, "#ffffff", 0.14), mix(acc, deep, 0.35)),
        p_fill_hi=vgrad(mix(acc, "#ffffff", 0.28), mix(acc, "#ffffff", 0.04)),
        p_press=mix(acc, deep, 0.6))


def build_qss(theme):
    t = clean_theme(theme)
    if t.get("style") == "one":
        return build_qss_one(t)
    bg, surf, acc, text = t["bg"], t["surface"], t["accent"], t["text"]
    # glass is tinted white (dark themes) or black (light themes) - never by the text color, so changing
    # the text color only changes text
    tint = "#ffffff" if luminance(bg) < 0.5 else "#000000"
    accent_text = "#0b0b0d" if luminance(acc) > 0.5 else "#ffffff"
    chev, check = make_icons(text, accent_text)
    acc2 = shift_hue(acc, 32)
    a = card_alpha(t)  # glass in every mode: the background (or the soft glows on a plain one) shows through
    g = t["glass"] / 100
    # as the glass slider goes up the fill gets lighter (frosted), not just more see-through (darker)
    base = mix(surf, tint, 0.50 * g)
    hi = mix(base, tint, 0.14)
    bgt = mix(bg, tint, 0.30 * g)

    def vgrad(top, bot):
        return f"qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {top}, stop:1 {bot})"
    card = vgrad(rgba(hi, min(1, a + 0.06)), rgba(base, a))
    side = vgrad(rgba(hi, min(1, a + 0.12)), rgba(base, min(1, a + 0.12)))
    chip = vgrad(rgba(hi, min(1, a + 0.04)), rgba(bgt, min(1, a + 0.02)))
    chip_hi = vgrad(rgba(mix(hi, acc, 0.15), min(1, a + 0.14)), rgba(mix(bgt, acc, 0.10), min(1, a + 0.08)))
    inp = rgba(mix(bg, tint, 0.12 * g), min(1, a + 0.28))
    return QSS.substitute(
        bg=bg, surface=surf, text=text, accent=acc, accent2=acc2, accent_text=accent_text,
        card=card, side=side, input=inp, chip=chip, chip_hi=chip_hi, edge=rgba(tint, 0.26),
        surface_hi=mix(surf, tint, 0.07), surface_hi2=mix(surf, tint, 0.13),
        border=mix(surf, tint, 0.12), border2=mix(surf, tint, 0.28),
        muted=mix(text, bg, 0.35), nav=mix(text, bg, 0.18), accent_hover=mix(acc, "#ffffff", 0.18),
        accent2_hover=mix(acc2, "#ffffff", 0.18),
        accent_fill=rgba(acc, 0.55), accent2_fill=rgba(acc2, 0.55),
        accent_soft=mix(bg, acc, 0.22), chev=chev, check=check,
        # buttons are always glass: a see-through tint of white/black (or the accent) with a light edge
        g_bg=rgba(tint, 0.08), g_hover=rgba(tint, 0.16), g_press=rgba(tint, 0.24),
        g_border=rgba(tint, 0.34), g_border2=rgba(tint, 0.52),
        g_fill=f"qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {rgba(tint, 0.26)}, stop:1 {rgba(tint, 0.15)})",
        g_fill_hi=f"qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {rgba(tint, 0.36)}, stop:1 {rgba(tint, 0.22)})",
        g_edge=rgba(tint, 0.60),
        p_fill=f"qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {rgba(acc, 0.55)}, stop:1 {rgba(acc, 0.36)})",
        p_fill_hi=f"qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {rgba(acc, 0.70)}, stop:1 {rgba(acc, 0.48)})",
        p_edge=rgba(mix(acc, "#ffffff", 0.45), 0.85),
        p_bg=rgba(acc, 0.30), p_hover=rgba(acc, 0.46), p_press=rgba(acc, 0.58), p_border=rgba(acc, 0.80))


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
    "rpc_enabled": True,           # Discord Rich Presence (needs your Discord application ID)
    "rpc_client_id": "",
    "rpc_details_idle": "In the launcher",
    "rpc_state_idle": "Chrome Client",
    "rpc_details_play": "Playing Minecraft {version}",
    "rpc_state_play": "{loader}",
    "rpc_image": "logo",          # name of an art asset you uploaded to your Discord app
    "rpc_timer": True,
    "jvm_opt": True,               # tuned Java flags: smoother frame times, fewer stutters
    "entity_culling": True,  # auto-install the performance mods (Sodium, Lithium, FerriteCore, ImmediatelyFast, Entity Culling)
    "instances": [],   # extra game setups: {"id","name","version","fabric"}
    "instance": "",    # id of the selected one ("" = Default, your normal game folder)
    "pack_groups": {},  # group name -> [texture pack file names]
    "hide_paths": True,  # never show your Windows username / folder paths on screen
    "vary_pitch": True,
    "sound_map": {},  # event -> sound id (see sounds.py)
    "create_url": "https://createtextures.com/",
    "theme": dict(CHROME_THEME),
    "ui_style_v2": False,   # the new default look has been applied once
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
    cu = str(cfg.get("create_url") or "")
    if not cu or "resourcepackcreator.com" in cu:
        cfg["create_url"] = "https://createtextures.com/"  # Resource Pack Creator was removed
    if not cfg.get("ui_style_v2"):   # once: switch to the new default look (other themes stay in the presets)
        cfg["theme"] = dict(CHROME_THEME)
        cfg["ui_style_v2"] = True
    cfg["theme"] = clean_theme(cfg.get("theme"))
    global HIDE_PATHS
    HIDE_PATHS = bool(cfg.get("hide_paths", True))
    cfg.pop("pvp_pack", None)
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


JVM_TUNED = [  # the widely used G1 flags (Aikar's): shorter, rarer garbage-collection pauses = fewer stutters
    "-XX:+UseG1GC", "-XX:+ParallelRefProcEnabled", "-XX:MaxGCPauseMillis=200", "-XX:+UnlockExperimentalVMOptions",
    "-XX:+DisableExplicitGC", "-XX:G1NewSizePercent=30", "-XX:G1MaxNewSizePercent=40", "-XX:G1HeapRegionSize=8M",
    "-XX:G1ReservePercent=20", "-XX:G1HeapWastePercent=5", "-XX:G1MixedGCCountTarget=4",
    "-XX:InitiatingHeapOccupancyPercent=15", "-XX:G1MixedGCLiveThresholdPercent=90",
    "-XX:G1RSetUpdatingPauseTimePercent=5", "-XX:SurvivorRatio=32", "-XX:+PerfDisableSharedMem",
    "-XX:MaxTenuringThreshold=1",
]


def jvm_arguments(ram_mb, tuned=True):
    if not tuned:
        return [f"-Xmx{ram_mb}M", f"-Xms{min(ram_mb, 1024)}M"]
    # starting heap = most of the max, so the game never stalls to grow it
    return [f"-Xmx{ram_mb}M", f"-Xms{min(ram_mb, 2048)}M"] + JVM_TUNED


def friendly_login_error(e):
    n = type(e).__name__
    if isinstance(e, subprocess.CalledProcessError):
        err = e.stderr if isinstance(e.stderr, str) else ""
        out = e.output if isinstance(e.output, str) else ""
        lines = [l.strip() for l in (err.strip() or out).splitlines() if l.strip()]
        key = [l for l in lines if not l.startswith(("at ", "..."))]  # skip the stack-trace frames: the error is above them
        what = "The Fabric installer failed" if "fabric" in str(e.cmd).lower() else "A helper program failed"
        why = " | ".join(key[:3])[:400] if key else "no details (is Java installed and are you online?)"
        low = why.lower()
        if "being used by another process" in low:
            why += "  -> Minecraft is probably still open. Close it and try again."
        if any(w in low for w in ("unknownhost", "connect", "timed out", "ssl", "handshake", "sockettimeout")):
            why += "  -> looks like a network problem: check your internet / VPN / firewall and try again."
        return f"{what} (exit code {e.returncode}): {why}"
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




_HASH_CACHE = {}


def _sha1_of(path):
    st = path.stat()
    key = (str(path), st.st_size, st.st_mtime_ns)
    h = _HASH_CACHE.get(key)
    if h is None:
        d = hashlib.sha1()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                d.update(chunk)
        h = _HASH_CACHE[key] = d.hexdigest()
    return h


def installed_project_ids(folder, suffixes=(".jar", ".jar.disabled")):
    """Modrinth project ids of the files in `folder` (matched by file hash, so ones you added by hand count too)."""
    try:
        files = [p for p in Path(folder).iterdir()
                 if p.is_file() and p.name.lower().endswith(suffixes) and p.stat().st_size < 600 * 1024 * 1024]
    except OSError:
        return set()
    hashes = []
    for p in files:
        try:
            hashes.append(_sha1_of(p))
        except OSError:
            pass
    if not hashes:
        return set()
    body = json.dumps({"hashes": hashes, "algorithm": "sha1"}).encode()
    req = urllib.request.Request(MODRINTH_API + "/version_files", data=body, method="POST",
                                 headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)
    return {v.get("project_id") for v in data.values() if isinstance(v, dict) and v.get("project_id")}


def upgrade_mods_for(mc_dir, mc_version):
    """Mods that don't fit this Minecraft version: look each one up on Modrinth (by file hash) and, when its maker has a
    Fabric build for this version, download it into mods/. The old file stays, and the usual matching step then sets it
    aside (so it comes back when you play the old version). Returns (updated names, names with no build for this version)."""
    mc = Path(mc_dir)
    mods, off = mc / "mods", mc / "mods_disabled"
    cands = []
    for d in (mods, off):
        if d.is_dir():
            cands += [j for j in sorted(d.glob("*.jar")) if mods_sync.mod_fits(j, mc_version) is False]
    if not cands:
        return [], []
    by_hash = {}
    for j in cands:
        try:
            by_hash.setdefault(_sha1_of(j), j)
        except OSError:
            pass
    if not by_hash:
        return [], []
    body = json.dumps({"hashes": list(by_hash), "algorithm": "sha1",
                       "loaders": ["fabric"], "game_versions": [mc_version]}).encode()
    req = urllib.request.Request(MODRINTH_API + "/version_files/update", data=body, method="POST",
                                 headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        found = json.load(r)
    updated, missing = [], []
    for h, jar in by_hash.items():
        v = found.get(h) if isinstance(found, dict) else None
        if not isinstance(v, dict) or not v.get("files"):
            missing.append(jar.name)
            continue
        f = next((x for x in v["files"] if x.get("primary")), v["files"][0])
        name = Path(f["filename"]).name  # never trust a path from the network
        if (mods / name).exists() or (off / name).exists():
            continue  # already have that build: the matching step puts it in the right folder
        try:
            mods.mkdir(parents=True, exist_ok=True)
            download_file(f["url"], mods / name, f.get("hashes", {}).get("sha512"))
            updated.append(name)
        except Exception:
            missing.append(jar.name)
    return updated, missing


PERF_MODS = [  # (Modrinth slug, word that shows it's already in the mods folder, nice name)
    ("sodium", "sodium", "Sodium"),                    # much faster rendering
    ("lithium", "lithium", "Lithium"),                 # faster game logic
    ("ferrite-core", "ferritecore", "FerriteCore"),    # far less RAM used
    ("immediatelyfast", "immediatelyfast", "ImmediatelyFast"),  # faster HUD / text / GUI drawing
    ("entityculling", "cull", "Entity Culling"),       # skips entities you can't see
]


def fix_pack_formats(gd):
    """Resource packs that declare a format above 64 (made for 1.21.9+) but have no min_format / max_format are rejected by
    the game ("Couldn't load pack metadata"). Add the two fields, keeping everything else in the pack as it is.
    Works on .zip packs and on pack folders. Returns the names of the packs that were fixed."""
    fixed = []
    folder = Path(mc_dir) / "resourcepacks"
    if not folder.is_dir():
        return fixed

    def patched(text):
        data = json.loads(text.lstrip("\ufeff"))
        pack = data.get("pack") if isinstance(data, dict) else None
        if not isinstance(pack, dict):
            return None
        fmt = pack.get("pack_format")
        if isinstance(fmt, int) and fmt > 64 and ("min_format" not in pack or "max_format" not in pack):
            pack.setdefault("min_format", fmt)
            pack.setdefault("max_format", fmt)
            return json.dumps(data, indent=2, ensure_ascii=False)
        return None

    for p in sorted(folder.iterdir()):
        try:
            if p.is_dir() and (p / "pack.mcmeta").is_file():
                new = patched((p / "pack.mcmeta").read_text(encoding="utf-8"))
                if new:
                    (p / "pack.mcmeta").write_text(new, encoding="utf-8")
                    fixed.append(p.name)
            elif p.is_file() and p.suffix.lower() == ".zip":
                with zipfile.ZipFile(p) as zin:
                    names = zin.namelist()
                    if "pack.mcmeta" not in names:
                        continue
                    new = patched(zin.read("pack.mcmeta").decode("utf-8"))
                    if not new:
                        continue
                    tmp = p.with_suffix(".zip.fixing")
                    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
                        for item in zin.infolist():
                            zout.writestr(item, new.encode("utf-8") if item.filename == "pack.mcmeta" else zin.read(item.filename))
                tmp.replace(p)
                fixed.append(p.name)
        except Exception:
            try:
                p.with_suffix(".zip.fixing").unlink()
            except Exception:
                pass
    return fixed


def install_bundled_mods(gd):
    """Copy the jars from the launcher's bundled_mods folder (Chrome Client + YT Music) into the mods folder.
    An older copy of the same mod (same fabric mod id) is replaced; jars already up to date are left alone."""
    src = Path(__file__).resolve().parent / "bundled_mods"
    if not src.is_dir():
        return []
    mods = Path(mc_dir) / "mods"
    mods.mkdir(parents=True, exist_ok=True)

    def mod_id(jar):
        try:
            with zipfile.ZipFile(jar) as z:
                return json.loads(z.read("fabric.mod.json").decode("utf-8-sig")).get("id")
        except Exception:
            return None

    done = []
    for jar in sorted(src.glob("*.jar")):
        mid = mod_id(jar)
        target = mods / jar.name
        if target.exists() and target.stat().st_size == jar.stat().st_size:
            continue
        if mid:
            for folder in (mods, Path(mc_dir) / "mods_disabled"):
                for old in folder.glob("*.jar") if folder.is_dir() else []:
                    if old.name != jar.name and mod_id(old) == mid:
                        try:
                            old.unlink()
                        except OSError:
                            pass
        shutil.copy2(jar, target)
        done.append(jar.stem)
    return done


RELEASE_MODS = [  # (name, GitHub repo, oldest Minecraft version the releases work on - newer ones get it too)
    ("Chrome Client", "baksyaaaaa/ChromeMod", "1.21.11"),
    ("YT Music", "baksyaaaaa/MusicMod", "1.21.11"),
    ("Chrome Boost", "baksyaaaaa/ChromeMod", "1.21.11", "chromeboost"),   # performance mod; lives in a fixed release tag
]


def _jar_mod_id(jar):
    try:
        with zipfile.ZipFile(jar) as z:
            return json.loads(z.read("fabric.mod.json").decode("utf-8-sig")).get("id")
    except Exception:
        return None


OUR_MOD_IDS = ("chromeclient", "ytmusic", "chromeboost")


def park_our_mods_for_26(gd, mc_version):
    """Minecraft 26.x is unobfuscated: mods built with intermediary names (ours are, for 1.21.11) crash there.
    Set them aside (never deleted) until there are builds for 26.x. Returns the mod ids moved."""
    ok = mods_sync.version_matches(mc_version, ">=1.21.11 <1.22")
    if ok is not False:
        return []
    mods, off = Path(gd) / "mods", Path(gd) / "mods_disabled"
    moved = []
    for jar in (mods.glob("*.jar") if mods.is_dir() else []):
        mid = _jar_mod_id(jar)
        if mid in OUR_MOD_IDS:
            off.mkdir(parents=True, exist_ok=True)
            try:
                dest = off / jar.name
                if dest.exists():
                    dest.unlink()
                jar.replace(dest)
                moved.append(mid)
            except OSError:
                pass
    return moved


def install_release_mods(mc_dir, mc_version):
    """Install / update our own mods from their newest GitHub Release. The release tag we installed is remembered
    in release_mods.json, so nothing is downloaded again until a newer release appears. Returns the names updated."""
    state_file = APP_DIR / "release_mods.json"
    try:
        state = json.loads(state_file.read_text("utf-8"))
    except Exception:
        state = {}
    mods = Path(mc_dir) / "mods"
    done = []
    for entry in RELEASE_MODS:
        name, repo, mc = entry[:3]
        tag = entry[3] if len(entry) > 3 else None
        if not mods_sync.version_matches(mc_version, ">=" + mc + " <1.22"):   # 1.21.11 up to the last 1.x; 26.x has no intermediary names, so these builds can't load there
            continue
        key = repo + ("#" + tag if tag else "")
        try:
            req = urllib.request.Request(f"https://api.github.com/repos/{repo}/releases/" + (f"tags/{tag}" if tag else "latest"),
                                         headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=15) as r:
                rel = json.loads(r.read().decode("utf-8"))
            assets = [a for a in rel.get("assets", [])
                      if a["name"].endswith(".jar") and "sources" not in a["name"] and "dev" not in a["name"]]
            if not assets:
                continue
            a = assets[0]
            stamp = f"{rel.get('tag_name')}|{a['name']}|{a.get('updated_at', '')}"
            installed = mods / a["name"]
            if state.get(key) == stamp and installed.exists():
                continue
            mods.mkdir(parents=True, exist_ok=True)
            download_file(a["browser_download_url"], installed)
            mid = _jar_mod_id(installed)
            if mid:
                for folder in (mods, Path(mc_dir) / "mods_disabled"):
                    for old in (folder.glob("*.jar") if folder.is_dir() else []):
                        if old.name != installed.name and _jar_mod_id(old) == mid:
                            try:
                                old.unlink()
                            except OSError:
                                pass
            state[key] = stamp
            done.append(name)
        except Exception:
            continue  # offline, rate limited, no release yet - never blocks launching
    if done:
        try:
            APP_DIR.mkdir(parents=True, exist_ok=True)
            state_file.write_text(json.dumps(state, indent=1), "utf-8")
        except OSError:
            pass
    return done


CHROMEPOLY_REPO = "baksyaaaaa/ChromeMod"
CHROMEPOLY_TAG = "polyplus-latest"


def install_chromepoly(mc_dir, mc_version):
    """Chrome Client's own copy of PolyPlus (GPL-3.0, source in the ChromeMod repo, polyplus folder) has one jar per Minecraft
    version on the 'polyplus-latest' release. Installs / updates the right one; a Polyfrost PolyPlus jar (same mod id) is
    switched off, not deleted. Returns True when something was installed."""
    m = re.match(r"^(1\.21\.11|26\.[123])(?:\D|$)", mc_version or "")
    if not m:
        return False
    v = m.group(1)
    name = f"ChromePoly-{v}.jar"
    mods = Path(mc_dir) / "mods"
    state_file = APP_DIR / "release_mods.json"
    try:
        state = json.loads(state_file.read_text("utf-8"))
    except Exception:
        state = {}
    req = urllib.request.Request(f"https://api.github.com/repos/{CHROMEPOLY_REPO}/releases/tags/{CHROMEPOLY_TAG}",
                                 headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        rel = json.loads(r.read().decode("utf-8"))
    a = next((x for x in rel.get("assets", []) if x["name"] == name), None)
    if not a:
        return False
    stamp = f"{a['name']}|{a.get('updated_at', '')}"
    installed = mods / name
    changed = False
    if not (state.get("ChromePoly") == stamp and installed.exists()):
        mods.mkdir(parents=True, exist_ok=True)
        for old in mods.glob("ChromePoly-*.jar"):   # a jar for another version
            if old.name != name:
                try:
                    old.unlink()
                except OSError:
                    pass
        download_file(a["browser_download_url"], installed)
        state["ChromePoly"] = stamp
        changed = True
        try:
            APP_DIR.mkdir(parents=True, exist_ok=True)
            state_file.write_text(json.dumps(state, indent=1), "utf-8")
        except OSError:
            pass
    for other in mods.glob("*.jar"):   # same mod id twice would stop the game: switch Polyfrost's jar off
        if other.name != name and "polyplus" in other.name.lower() and not other.name.startswith("ChromePoly"):
            try:
                other.rename(other.with_name(other.name + ".disabled"))
            except OSError:
                pass
    return changed


def ensure_perf_mods(mc_dir, mc_version):
    """Install the performance mods that aren't in the mods folder yet (switched on or off - if you turned one off
    we respect that). Mods with no build for this version are skipped. Returns (installed names, failed names)."""
    have = [(m["name"] + " " + m["file"]).lower() for m in library.list_mods(mc_dir)]
    got, bad = [], []
    for slug, word, nice in PERF_MODS:
        if any(word in h for h in have):
            continue
        try:
            if install_mod(slug, mc_version, Path(mc_dir) / "mods"):
                got.append(nice)
        except Exception:
            bad.append(nice)
    return got, bad


def ensure_required_libs(mc_dir, mc_version):
    """Makes sure OneConfig (>= 1.9.0, needed by the Chrome Client menu) and Balm (needed by Maptip) are in the mods folder for
    this Minecraft version, downloading them from Modrinth when missing, too old or built for another version.
    Returns (installed names, names that failed)."""
    mods_dir = Path(mc_dir) / "mods"
    got, bad = [], []

    def jars(word):
        return [m["file"] for m in library.list_mods(mc_dir) if m["enabled"] and word in m["file"].lower()]

    def ver_of(fname):
        m = re.search(r"(\d+)\.(\d+)\.(\d+)(?:\.\d+)?\.jar$", fname)
        return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)

    wanted = [("oneconfig", "oneconfig", (1, 9, 0), True)]
    if jars("maptip"):
        wanted.append(("balm", "balm", (0, 0, 0), False))
    for slug, word, min_ver, check_ver in wanted:
        have = jars(word)
        ok = [f for f in have if mc_version in f and ver_of(f) >= min_ver]
        if ok:
            continue
        try:
            names = install_mod(slug, mc_version, mods_dir)
            got.append(slug)
            for f in have:            # an older / other-version copy would clash with the new one
                if f not in names:
                    try:
                        library.set_mod_enabled(mc_dir, f, False)
                    except Exception:
                        pass
        except Exception:
            bad.append(slug)
    return got, bad


DEP_SLUGS = {"oneconfigv1": "oneconfig", "oneconfig": "oneconfig", "balm-fabric": "balm", "fabric": "fabric-api",
             "fabric-api": "fabric-api", "fabric-language-kotlin": "fabric-language-kotlin"}


def resolve_dependencies(mc_dir, mc_version):
    """Make sure every switched-on mod has the mods it needs: switch on ones you turned off, download the
    rest from Modrinth. Returns (switched_on, installed, still_missing)."""
    mods_dir = Path(mc_dir) / "mods"
    switched, installed, failed = [], [], set()
    for _ in range(5):  # a dependency can have dependencies of its own
        ids = sorted({d for v in library.missing_dependencies(mc_dir).values() for d in v} - failed)
        if not ids:
            break
        for dep in ids:
            f = library.disabled_provider(mc_dir, dep)
            if f:
                switched.append(library.set_mod_enabled(mc_dir, f, True))
                continue
            got = None
            for cand in dict.fromkeys([DEP_SLUGS.get(dep, dep), dep, dep.replace("-fabric", "").replace("_fabric", "")]):
                try:   # a mod's id is not always its Modrinth name (oneconfigv1 -> oneconfig, balm-fabric -> balm)
                    got = install_mod(cand, mc_version, mods_dir)
                    break
                except Exception:
                    continue
            if got is None:
                failed.add(dep)
            else:
                installed += got
    still = sorted({d for v in library.missing_dependencies(mc_dir).values() for d in v})
    return switched, installed, still


def describe_deps(switched, installed, still):
    bits = []
    if switched:
        bits.append(f"switched on {len(switched)} mod(s) they need")
    if installed:
        bits.append(f"installed {len(installed)} missing mod(s)")
    if still:
        bits.append("couldn't find: " + ", ".join(still))
    return ", ".join(bits)


def search_packs(query, mc_version, only_version=False):
    facets = [["project_type:resourcepack"]]
    if mc_version and only_version:
        facets.append([f"versions:{mc_version}"])
    params = {"facets": json.dumps(facets), "limit": 20,
              "index": "relevance" if query else "downloads"}
    if query:
        params["query"] = query
    return modrinth_get("/search", params)["hits"]


def install_pack(project_id, mc_version, packs_dir):
    """Download a texture pack (the build for mc_version if there is one, else the newest).
    Returns (file name, exact_match)."""
    versions = modrinth_get(f"/project/{project_id}/version", {"game_versions": json.dumps([mc_version])}) if mc_version else []
    exact = bool(versions)
    if not versions:
        versions = modrinth_get(f"/project/{project_id}/version", {})
    if not versions:
        raise RuntimeError("This pack has no downloads.")
    f = next((x for x in versions[0]["files"] if x.get("primary")), versions[0]["files"][0])
    name = Path(f["filename"]).name  # never trust a path from the network
    if not name.lower().endswith(".zip"):
        raise RuntimeError("This pack isn't a .zip file, so it can't be installed here.")
    packs_dir.mkdir(parents=True, exist_ok=True)
    download_file(f["url"], packs_dir / name, f.get("hashes", {}).get("sha512"))
    return name, exact


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


def grad_icon(stops):
    pm = QPixmap(32, 32)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    g = QLinearGradient(4, 4, 28, 28)
    for i, c in enumerate(stops):
        g.setColorAt(i / (len(stops) - 1), QColor(c))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawEllipse(4, 4, 24, 24)
    p.end()
    return QIcon(pm)


_LOGO_CACHE = {}


def logo_pixmap(accent, size=64, glass=0):
    """The Chrome Client logo: an accent tile with a bold ring-'C' and a spark.
    `glass` (0-100) follows the 'Glass cards' slider: the more glass, the more see-through the tile, with a light edge and shine."""
    try:  # glassy logo: a tile in your accent colour with the glass "C" on top
        key = (accent, size)
        if key in _LOGO_CACHE:
            return QPixmap.fromImage(_LOGO_CACHE[key])
        glassc = QImage(str(Path(__file__).with_name("chrome_client_c.png")))
        if not glassc.isNull():
            img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
            img.fill(Qt.GlobalColor.transparent)
            q = QPainter(img)
            q.setRenderHint(QPainter.RenderHint.Antialiasing)
            q.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            u = size / 1024.0
            tile = QRectF(40 * u, 40 * u, 944 * u, 944 * u)
            rad = 230 * u
            lo = QColor(accent)
            hi = QColor(accent).lighter(125)
            dk = QColor(accent).darker(230)
            g = QLinearGradient(0, 0, size, size)
            g.setColorAt(0, hi)
            g.setColorAt(0.45, lo)
            g.setColorAt(1, dk)
            q.setPen(Qt.PenStyle.NoPen)
            q.setBrush(g)
            q.drawRoundedRect(tile, rad, rad)
            shine = QLinearGradient(0, 0, 0, size * 0.55)
            shine.setColorAt(0, QColor(255, 255, 255, 60))
            shine.setColorAt(1, QColor(255, 255, 255, 0))
            q.setBrush(shine)
            q.drawRoundedRect(tile, rad, rad)
            q.setPen(QPen(QColor(255, 255, 255, 80), max(1.0, 8 * u)))
            q.setBrush(Qt.BrushStyle.NoBrush)
            q.drawRoundedRect(tile.adjusted(4 * u, 4 * u, -4 * u, -4 * u), rad, rad)
            q.drawImage(QRectF(0, 0, size, size), glassc)
            q.end()
            _LOGO_CACHE[key] = img
            return QPixmap.fromImage(img)
    except Exception:
        pass
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    u = size / 64
    a = int(255 * (1 - 0.62 * max(0, min(100, glass)) / 100))  # tile see-through-ness: solid at 0, ~40% at 100
    c1, c2 = QColor(accent), QColor(shift_hue(accent, 40))
    c1.setAlpha(a)
    c2.setAlpha(a)
    g = QLinearGradient(0, 0, size, size)
    g.setColorAt(0, c1)
    g.setColorAt(1, c2)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    tile = QRectF(2 * u, 2 * u, 60 * u, 60 * u)
    p.drawRoundedRect(tile, 10 * u, 10 * u)
    shine = QLinearGradient(0, 0, 0, size / 2)
    shine.setColorAt(0, QColor(255, 255, 255, 90 + int(60 * glass / 100)))
    shine.setColorAt(1, QColor(255, 255, 255, 0))
    p.setBrush(shine)
    p.drawRoundedRect(QRectF(2 * u, 2 * u, 60 * u, 30 * u), 10 * u, 10 * u)
    if glass > 0:  # thin light edge like the glass cards
        p.setPen(QPen(QColor(255, 255, 255, int(40 + 140 * glass / 100)), 1.6 * u))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(tile.adjusted(0.8 * u, 0.8 * u, -0.8 * u, -0.8 * u), 9.5 * u, 9.5 * u)
    ink = QColor("#0b0b0d") if luminance(accent) > 0.5 else QColor("#ffffff")
    p.setPen(QPen(ink, 8 * u, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(QRectF(16 * u, 16 * u, 32 * u, 32 * u), 40 * 16, 280 * 16)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(ink)
    p.drawEllipse(QRectF(36 * u, 28 * u, 8 * u, 8 * u))
    p.end()
    return pm


def drop_widget(wd):
    """Remove a widget from the screen right away (deleteLater alone leaves it painted until the next event)."""
    if wd is not None:
        wd.hide()
        wd.setParent(None)
        wd.deleteLater()


def card():
    f = QFrame()
    f.setProperty("card", True)
    return f


def header(title, sub):
    box = QVBoxLayout()
    box.setSpacing(2)
    box.addWidget(label(title, "h1"))
    return box


def primary(btn):
    btn.setProperty("primary", True)
    return btn


QUICK_COLORS = ["#1bd96a", "#3b9bff", "#a56bff", "#ff5fa8", "#ff4d4d", "#ff8a2b", "#ffd23f", "#2fd3e0",
                "#ffffff", "#c9ced6", "#26292f", "#0b0b0d"]


class ColorPicker(QDialog):
    """Small built-in color picker (hue / saturation / brightness sliders, hex box, quick colors)."""
    def __init__(self, parent, initial, title):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(380)
        c = QColor(initial)
        h, s, v, _ = c.getHsv()
        self.h, self.s, self.v = max(h, 0), s, v
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(12)
        lay.addWidget(label(title, "h2"))
        self.swatch = QLabel()
        self.swatch.setFixedHeight(54)
        lay.addWidget(self.swatch)
        self.sliders = {}
        for key, name, hi in (("h", "Hue", 359), ("s", "Saturation", 255), ("v", "Brightness", 255)):
            row = QHBoxLayout()
            lb = QLabel(name)
            lb.setMinimumWidth(80)
            row.addWidget(lb)
            sl = QSlider(Qt.Orientation.Horizontal)
            sl.setRange(0, hi)
            sl.setValue(getattr(self, key))
            sl.valueChanged.connect(lambda val, k=key: self._moved(k, val))
            row.addWidget(sl, 1)
            self.sliders[key] = sl
            lay.addLayout(row)
        hexrow = QHBoxLayout()
        hexrow.addWidget(QLabel("Hex"))
        self.hex = QLineEdit()
        self.hex.setMaximumWidth(120)
        self.hex.editingFinished.connect(self._hex_typed)
        hexrow.addWidget(self.hex)
        hexrow.addStretch(1)
        lay.addLayout(hexrow)
        quick = QHBoxLayout()
        quick.setSpacing(6)
        for q in QUICK_COLORS:
            b = QPushButton()
            b.setFixedSize(26, 26)
            b.setStyleSheet(f"background: {q}; border: 2px solid rgba(128,128,128,120); border-radius: 13px; padding: 0;")
            b.clicked.connect(lambda _=False, q=q: self._set(QColor(q)))
            quick.addWidget(b)
        quick.addStretch(1)
        lay.addLayout(quick)
        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setProperty("ghost", True)
        cancel.clicked.connect(self.reject)
        ok = primary(QPushButton("Use this color"))
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        lay.addLayout(btns)
        self._refresh()

    def color(self):
        return QColor.fromHsv(self.h, self.s, self.v)

    def _moved(self, k, val):
        setattr(self, k, val)
        self._refresh(skip=k)

    def _set(self, c):
        h, s, v, _ = c.getHsv()
        self.h, self.s, self.v = (self.h if h < 0 else h), s, v
        self._refresh()

    def _hex_typed(self):
        t = self.hex.text().strip()
        c = QColor(t if t.startswith("#") else "#" + t)
        if c.isValid():
            self._set(c)
        else:
            self._refresh()

    def _refresh(self, skip=None):
        c = self.color()
        self.swatch.setStyleSheet(f"background: {c.name()}; border-radius: 6px;")
        self.hex.setText(c.name())
        for k, sl in self.sliders.items():
            if k != skip:
                sl.blockSignals(True)
                sl.setValue(getattr(self, k))
                sl.blockSignals(False)


def ask_color(parent, initial, title):
    dlg = ColorPicker(parent, initial, title)
    return dlg.color().name() if dlg.exec() == QDialog.DialogCode.Accepted else None


class StatusBar(QProgressBar):
    """Progress bar with the status message written on top of it, centered."""
    def __init__(self):
        super().__init__()
        self.setTextVisible(False)
        self.setMinimumHeight(30)
        self.text_lbl = QLabel(self)
        self.text_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.text_lbl.setStyleSheet("background: transparent; border: none; font-weight: 600;")

    def setText(self, text):
        self.text_lbl.setText(str(text))
        self.setToolTip(str(text))

    def text(self):
        return self.text_lbl.text()

    def resizeEvent(self, ev):
        self.text_lbl.setGeometry(8, 0, max(0, self.width() - 16), self.height())
        super().resizeEvent(ev)


class WideCheck(QCheckBox):
    """A checkbox you can click anywhere along its width (Qt only reacts on the box and the text by default)."""
    def hitButton(self, pos):
        return self.rect().contains(pos)


class ClickRow(QFrame):
    """A card that toggles its checkbox when you click anywhere on it."""
    def __init__(self):
        super().__init__()
        self.setProperty("card", True)
        self.check = None

    def mouseReleaseEvent(self, ev):
        if (self.check is not None and self.check.isEnabled() and ev.button() == Qt.MouseButton.LeftButton
                and self.rect().contains(ev.position().toPoint())):
            self.check.click()
        super().mouseReleaseEvent(ev)


class ClickableChip(QFrame):
    """A box that acts like a button (used for the account box)."""
    def __init__(self, on_click):
        super().__init__()
        self._on_click = on_click

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and self.rect().contains(ev.position().toPoint()):
            self._on_click()
        super().mouseReleaseEvent(ev)



class Bus(QObject):
    versions = Signal(list)
    versions_done = Signal()           # a version-list refresh finished (hit or miss)
    status = Signal(str)
    progress = Signal(int, int)       # value, max (max < 0 keeps the old max)
    play_done = Signal(bool, str)
    park_web = Signal()
    login_done = Signal(object, str)  # account or None, error text
    mods = Signal(int, list, str)     # search id, hits, error
    mod_status = Signal(str)
    mod_installed = Signal(str)       # project id (empty on failure)
    installed_ids = Signal(object)    # set of Modrinth project ids already in the mods folder
    installed_pack_ids = Signal(object)  # same for the resourcepacks folder
    icon = Signal(str, bytes)
    packs = Signal(int, list, str)       # search id, hits, error
    lib_msg = Signal(str)                # message for the Library page (then refresh)
    pack_installed = Signal(str, str)    # project id ('!' prefix on failure), message


class GroupDialog(QDialog):
    """Make or edit a texture-pack group: a name plus ticks for the packs in it."""
    def __init__(self, parent, packs, name="", members=()):
        super().__init__(parent)
        self.setWindowTitle("Pack group")
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(label("Group name", "h2"))
        self.name_edit = QLineEdit(name)
        self.name_edit.setPlaceholderText("e.g. PvP set, Cozy, Hardcore")
        lay.addWidget(self.name_edit)
        lay.addWidget(label("Packs in this group", "h2"))
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setMinimumHeight(220)
        inner = QWidget()
        il = QVBoxLayout(inner)
        il.setSpacing(4)
        self.checks = []
        known = {p["file"] for p in packs}
        for p in packs:
            cb = QCheckBox(p["name"])
            cb.setChecked(p["file"] in members)
            self.checks.append((cb, p["file"]))
            il.addWidget(cb)
        for f in members:  # packs that were in the group but are gone: keep them listed so nothing is lost silently
            if f not in known:
                cb = QCheckBox(f"{Path(f).stem} (not found)")
                cb.setChecked(True)
                self.checks.append((cb, f))
                il.addWidget(cb)
        if not self.checks:
            il.addWidget(label("You have no texture packs yet.", "muted"))
        il.addStretch(1)
        sa.setWidget(inner)
        lay.addWidget(sa, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        ok = primary(QPushButton("Save group"))
        ok.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)

    def result_group(self):
        return self.name_edit.text().strip(), [f for cb, f in self.checks if cb.isChecked()]


class SfxFilter(QObject):
    """Plays the click sounds for every button / checkbox in the app."""
    def __init__(self, sfx, skip):
        super().__init__()
        self.sfx, self.skip = sfx, skip

    def eventFilter(self, obj, ev):
        # the filter sees events for every object (including QWindow), so check the type first
        if ev.type() == QEvent.Type.Polish and isinstance(obj, (QCheckBox, _QPushButton)):
            obj.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # clicking a button never leaves a focus box on it
            return False
        if (ev.type() == QEvent.Type.MouseButtonPress and isinstance(obj, (QCheckBox, _QPushButton))
                and obj is not self.skip and obj.isEnabled()):
            self.sfx.play("toggle" if isinstance(obj, QCheckBox) else "click")
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
        self.sfx.assign = dict(self.cfg.get("sound_map") or {})
        self.sfx.vary = bool(self.cfg.get("vary_pitch", True))
        self.bus = Bus()
        self._connect_bus()

        root = Backdrop()
        root.setObjectName("root")
        self.root = root
        self.setCentralWidget(root)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(lambda: save_config(self.cfg))
        self._game_proc, self._game_info, self._game_start = None, {}, 0.0
        self._launcher_start = time.time()
        try:
            self.rpc = discord_rpc.DiscordRPC()
        except Exception:
            self.rpc = None
        self._rpc_timer = QTimer(self)  # notices when the game closes
        self._rpc_timer.timeout.connect(self._rpc_poll)
        self._rpc_timer.start(3000)
        QTimer.singleShot(800, self._rpc_update)  # show "In the launcher" once everything is built
        self._restyle_timer = QTimer(self)
        self._restyle_timer.setSingleShot(True)
        self._restyle_timer.timeout.connect(self._restyle_now)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_sidebar())
        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)
        self.stack.addWidget(self._build_play())
        self.stack.addWidget(self._build_mods())
        self.stack.addWidget(self._build_packs_page())
        self.stack.addWidget(self._build_library())
        self.stack.addWidget(self._build_appearance())
        self.stack.addWidget(self._build_settings())
        self.stack.addWidget(self._build_create())
        self.stack.addWidget(self._build_instances())

        self.apply_theme(self.cfg["theme"], save=False)
        self._refresh_instances()
        self._refresh_account()
        self._sfx_filter = SfxFilter(self.sfx, self.play_btn)
        QApplication.instance().installEventFilter(self._sfx_filter)
        for w in self.findChildren(_QPushButton) + self.findChildren(QCheckBox):
            w.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # no focus box when you click a button
        self.nav_buttons[0].setChecked(True)
        threading.Thread(target=self._load_versions, daemon=True).start()

    def _connect_bus(self):
        b = self.bus
        b.versions.connect(self._on_versions)
        b.versions_done.connect(lambda: self.ver_refresh.setEnabled(True))
        b.status.connect(lambda t: self.status_lbl.setText(t))
        b.progress.connect(self._on_progress)
        b.play_done.connect(self._on_play_done)
        b.park_web.connect(self._park_web)
        b.login_done.connect(self._on_login_done)
        b.mods.connect(self._on_mods)
        b.mod_status.connect(self._set_mod_status)
        b.mod_installed.connect(self._on_mod_installed)
        b.installed_ids.connect(self._on_installed_ids)
        b.installed_pack_ids.connect(self._on_installed_pack_ids)
        b.icon.connect(self._on_icon)
        b.packs.connect(self._on_packs)
        b.lib_msg.connect(self._on_lib_msg)
        b.pack_installed.connect(self._on_pack_installed)

    # ---------- sidebar ----------
    def _build_sidebar(self):
        sb = QWidget()
        sb.setObjectName("sidebar")
        sb.setFixedWidth(220)
        lay = QVBoxLayout(sb)
        lay.setContentsMargins(14, 18, 14, 14)
        lay.setSpacing(4)
        brand = QHBoxLayout()
        brand.setSpacing(10)
        self.logo = QLabel()
        self.logo.setFixedSize(40, 40)
        brand.addWidget(self.logo)
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(label("Chrome Client", "brand"))
        names.addWidget(label("Minecraft launcher", "muted"))
        brand.addLayout(names, 1)
        lay.addLayout(brand)
        lay.addSpacing(14)
        self.nav_group = QButtonGroup(self)
        self.nav_buttons = []
        names = ("Play", "Mods", "Texture packs", "Library", "Appearance", "Settings", "Create", "Instances")
        for i, name in enumerate(names):  # nav_buttons[i] is the button for stack page i
            b = QPushButton(name)
            b.setProperty("nav", True)
            b.setCheckable(True)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # no focus rectangle around the page you click
            b.clicked.connect(lambda _=False, i=i: self.go_page(i))
            self.nav_group.addButton(b)
            self.nav_buttons.append(b)
        for i in (0, 7, 1, 2, 3, 4, 5):  # the Create page was removed (its nav button 6 is never shown)
            lay.addWidget(self.nav_buttons[i])
        lay.addStretch(1)

        chip = ClickableChip(lambda: self.acc_btn.isEnabled() and (self.sfx.play("click"), self.account_clicked()))
        chip.setProperty("chip", True)
        chip.setCursor(Qt.CursorShape.PointingHandCursor)
        chip.setMinimumHeight(68)
        cl = QHBoxLayout(chip)
        cl.setContentsMargins(12, 12, 12, 12)
        cl.setSpacing(10)
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
        self.acc_btn = label("Click to sign in", "muted")
        col.addWidget(self.acc_btn)
        cl.addLayout(col, 1)
        lay.addWidget(chip)
        return sb

    def go_page(self, i):
        """Switch page instantly (a fade forces the whole page to re-render offscreen every frame = lag)."""
        if i == self.stack.currentIndex():
            return
        self.stack.setCurrentIndex(i)

    # ---------- play page ----------
    def _page(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(32, 28, 32, 24)
        lay.setSpacing(16)
        return w, lay

    def _build_play(self):
        page, lay = self._page()
        lay.addLayout(header("Play", "Pick a version and jump in."))
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
        self.ver_refresh = QPushButton("Refresh")
        self.ver_refresh.setToolTip("Load the version list again")
        self.ver_refresh.clicked.connect(self._refresh_versions)
        g.addWidget(self.ver_refresh, 0, 3)

        g.addWidget(label("Loader", "h2"), 1, 0)
        self.fabric_cb = QCheckBox("Fabric (needed for mods)")
        self.fabric_cb.setChecked(self.cfg["use_fabric"])
        self.fabric_cb.toggled.connect(lambda _: (self._save_settings(), self._update_mods_hint()))
        g.addWidget(self.fabric_cb, 1, 1, 1, 2)

        g.addWidget(label("Instance", "h2"), 2, 0)
        self.inst_box = QComboBox()
        self.inst_box.activated.connect(lambda _: self.sfx.play("select"))
        self.inst_box.activated.connect(lambda i: self.select_instance(self.inst_box.itemData(i) or ""))
        g.addWidget(self.inst_box, 2, 1, 1, 3)

        lay.addWidget(c)

        self.play_btn = primary(QPushButton("Play"))
        self.play_btn.setMinimumHeight(58)
        self.play_btn.setStyleSheet("font-size: 17px;")
        self.play_btn.clicked.connect(self.play)
        lay.addWidget(self.play_btn)
        # one bar: the status text is written ON the progress bar
        self.progress = StatusBar()
        self.progress.setRange(0, 1)
        self.progress.setText("Loading versions...")
        lay.addWidget(self.progress)
        self.status_lbl = self.progress
        lay.addStretch(1)
        return page

    # ---------- instances ----------
    def current_instance(self):
        iid = self.cfg.get("instance") or ""
        for it in self.cfg.get("instances") or []:
            if it.get("id") == iid:
                return it
        return None

    def game_dir(self):
        """The folder the game runs in: your normal game folder, or the selected instance's own folder."""
        inst = self.current_instance()
        if not inst:
            return self.cfg["minecraft_dir"]
        d = APP_DIR / "instances" / inst["id"]
        d.mkdir(parents=True, exist_ok=True)
        return str(d)

    def _instance_dir(self, inst):
        return Path(self.cfg["minecraft_dir"]) if inst is None else APP_DIR / "instances" / inst["id"]

    def select_instance(self, iid):
        if self.busy:
            return
        self.cfg["instance"] = iid or ""
        inst = self.current_instance()
        if inst is None:
            self.cfg["instance"] = ""
        else:
            self.fabric_cb.blockSignals(True)
            self.fabric_cb.setChecked(bool(inst.get("fabric", True)))
            self.fabric_cb.blockSignals(False)
            idx = self.version_box.findText(inst.get("version", ""))
            if idx >= 0:
                self.version_box.blockSignals(True)
                self.version_box.setCurrentIndex(idx)
                self.version_box.blockSignals(False)
        self._save_settings()
        self._update_mods_hint()
        self._refresh_instances()
        try:
            self._refresh_library()
        except Exception:
            pass

    def _count_files(self, folder, suffix):
        try:
            return sum(1 for f in Path(folder).iterdir() if f.name.lower().endswith(suffix))
        except Exception:
            return 0

    def _build_instances(self):
        page, lay = self._page()
        top = QHBoxLayout()
        top.addLayout(header("Instances", "Separate game setups. Each one has its own version, mods, texture packs, worlds and settings."))
        top.addStretch(1)
        nb = primary(QPushButton("New instance"))
        nb.clicked.connect(self._new_instance)
        top.addWidget(nb)
        lay.addLayout(top)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.Shape.NoFrame)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.inst_host = QWidget()
        self.inst_grid = QGridLayout(self.inst_host)
        self.inst_grid.setSpacing(14)
        self.inst_grid.setContentsMargins(0, 0, 0, 0)
        sa.setWidget(self.inst_host)
        lay.addWidget(sa, 1)
        return page

    def _refresh_instances(self):
        if not hasattr(self, "inst_grid"):
            return
        while self.inst_grid.count():
            it = self.inst_grid.takeAt(0)
            drop_widget(it.widget())
        cur = self.cfg.get("instance") or ""
        entries = [None] + list(self.cfg.get("instances") or [])
        for n, inst in enumerate(entries):
            iid = "" if inst is None else inst["id"]
            c = card()
            v = QVBoxLayout(c)
            v.setContentsMargins(16, 14, 16, 14)
            v.setSpacing(6)
            head = QHBoxLayout()
            logo = QLabel()
            logo.setFixedSize(34, 34)
            try:
                logo.setPixmap(logo_pixmap(self.cfg["theme"]["accent"], 34))
            except Exception:
                pass
            head.addWidget(logo)
            col = QVBoxLayout()
            col.setSpacing(0)
            col.addWidget(label("Default" if inst is None else inst["name"], "h2"))
            if inst is None:
                sub = "Your normal game folder"
            else:
                sub = ("Fabric " if inst.get("fabric", True) else "Vanilla ") + (inst.get("version") or "?")
            col.addWidget(label(sub, "muted"))
            head.addLayout(col, 1)
            v.addLayout(head)
            folder = self._instance_dir(inst)
            nm = self._count_files(folder / "mods", ".jar")
            np_ = self._count_files(folder / "resourcepacks", ".zip")
            v.addWidget(label(f"{nm} mod{'s' if nm != 1 else ''}  \u00b7  {np_} texture pack{'s' if np_ != 1 else ''}", "muted"))
            row = QHBoxLayout()
            row.setSpacing(6)
            pb = primary(QPushButton("Play"))
            pb.clicked.connect(lambda _=False, i=iid: (self.select_instance(i), self.play()))
            row.addWidget(pb)
            sel = QPushButton("Selected" if iid == cur else "Select")
            sel.setEnabled(iid != cur)
            sel.clicked.connect(lambda _=False, i=iid: self.select_instance(i))
            row.addWidget(sel)
            ob = QPushButton("Folder")
            ob.clicked.connect(lambda _=False, f=folder: (Path(f).mkdir(parents=True, exist_ok=True),
                                                         QDesktopServices.openUrl(QUrl.fromLocalFile(str(f)))))
            row.addWidget(ob)
            v.addLayout(row)
            if inst is not None:
                row2 = QHBoxLayout()
                row2.setSpacing(6)
                db = QPushButton("Duplicate")
                db.clicked.connect(lambda _=False, i=iid: self._duplicate_instance(i))
                row2.addWidget(db)
                xb = QPushButton("Delete")
                xb.clicked.connect(lambda _=False, i=iid: self._delete_instance(i))
                row2.addWidget(xb)
                v.addLayout(row2)
            self.inst_grid.addWidget(c, n // 2, n % 2)
        self.inst_grid.setRowStretch(len(entries) // 2 + 1, 1)
        # the box on the Play page
        self.inst_box.blockSignals(True)
        self.inst_box.clear()
        self.inst_box.addItem("Default", "")
        for inst in self.cfg.get("instances") or []:
            self.inst_box.addItem(inst["name"], inst["id"])
        k = self.inst_box.findData(cur)
        self.inst_box.setCurrentIndex(k if k >= 0 else 0)
        self.inst_box.blockSignals(False)

    def _unique_id(self, name):
        base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "instance"
        used = {i["id"] for i in self.cfg.get("instances") or []}
        iid, n = base, 2
        while iid in used:
            iid = f"{base}-{n}"
            n += 1
        return iid

    def _new_instance(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("New instance")
        dlg.setMinimumWidth(380)
        lay = QVBoxLayout(dlg)
        lay.setSpacing(10)
        lay.addWidget(label("Name", "h2"))
        name = QLineEdit()
        name.setPlaceholderText("e.g. PvP, Survival, Modpack testing")
        lay.addWidget(name)
        lay.addWidget(label("Minecraft version", "h2"))
        vb = QComboBox()
        vb.addItems([self.version_box.itemText(i) for i in range(self.version_box.count())])
        vb.setCurrentText(self.version_box.currentText())
        lay.addWidget(vb)
        fab = QCheckBox("Fabric (needed for mods)")
        fab.setChecked(True)
        lay.addWidget(fab)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(dlg.reject)
        ok = primary(QPushButton("Create"))
        ok.clicked.connect(dlg.accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        nm = name.text().strip() or "New instance"
        inst = {"id": self._unique_id(nm), "name": nm, "version": vb.currentText(), "fabric": fab.isChecked()}
        self.cfg.setdefault("instances", []).append(inst)
        (APP_DIR / "instances" / inst["id"]).mkdir(parents=True, exist_ok=True)
        self.select_instance(inst["id"])

    def _duplicate_instance(self, iid):
        src = next((i for i in self.cfg.get("instances") or [] if i["id"] == iid), None)
        if not src:
            return
        new = dict(src, id=self._unique_id(src["name"] + " copy"), name=src["name"] + " copy")
        try:
            shutil.copytree(APP_DIR / "instances" / src["id"], APP_DIR / "instances" / new["id"], dirs_exist_ok=True)
        except Exception as e:
            QMessageBox.warning(self, "Couldn't duplicate", scrub(str(e)))
            return
        self.cfg["instances"].append(new)
        save_config(self.cfg)
        self._refresh_instances()

    def _delete_instance(self, iid):
        inst = next((i for i in self.cfg.get("instances") or [] if i["id"] == iid), None)
        if not inst:
            return
        r = QMessageBox.question(self, "Delete instance",
                                 f"Delete \"{inst['name']}\"? Its mods, texture packs, worlds and settings are removed for good.")
        if r != QMessageBox.StandardButton.Yes:
            return
        if (self.cfg.get("instance") or "") == iid:
            self.select_instance("")
        try:
            shutil.rmtree(APP_DIR / "instances" / iid, ignore_errors=True)
        except Exception:
            pass
        self.cfg["instances"] = [i for i in self.cfg["instances"] if i["id"] != iid]
        save_config(self.cfg)
        self._refresh_instances()

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
        ab = QPushButton("Add mod file...")
        ab.clicked.connect(self.add_mod_file)
        row.addWidget(ab)
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
        fab = (" Mods for other versions are set aside automatically when you launch." if self.fabric_cb.isChecked()
               else " Tick Fabric on the Play page to load them.")
        inst = self.current_instance()
        self.mods_hint.setText((f"Instance: {inst['name']}. " if inst else "") + f"Showing Fabric mods for Minecraft {v}.{fab}")

    def _mods_dir(self):
        return Path(self.game_dir()) / "mods"

    def add_mod_file(self):
        """Copy a .jar you downloaded (like the Chrome Client in-game menu mod) into the mods folder."""
        paths, _ = QFileDialog.getOpenFileNames(self, "Choose mod files", str(Path.home() / "Downloads"),
                                                "Mods (*.jar)")
        if not paths:
            return
        mods = self._mods_dir()
        mods.mkdir(parents=True, exist_ok=True)
        added = []
        try:
            for p in paths:
                src = Path(p)
                if src.suffix.lower() != ".jar":
                    continue
                shutil.copyfile(src, mods / src.name)
                added.append(src.name)
        except OSError as e:
            self.sfx.play("error")
            self._set_mod_status(f"Couldn't copy the file: {e.strerror or e}")
            return
        if added:
            self.sfx.play("success")
            self._set_mod_status("Added: " + ", ".join(added) + ("" if self.fabric_cb.isChecked()
                                 else "  (tick Fabric on the Play page to load it)"))
            self._refresh_library()
            self._check_deps_async()

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
            drop_widget(self.mod_list_lay.takeAt(0).widget())
        for k in [k for k in self.icon_labels if not k.startswith("p:")]:
            del self.icon_labels[k]
        self._set_mod_status(err or ("" if hits else "No mods found for this version."))
        self._mod_btns = {}
        for h in hits:
            self.mod_list_lay.insertWidget(self.mod_list_lay.count() - 1, self._mod_card(h))
        if hits:
            mods_dir = self._mods_dir()

            def mark():
                try:
                    self.bus.installed_ids.emit(installed_project_ids(mods_dir))
                except Exception:
                    pass  # offline or a locked file: the cards just keep saying Install
            threading.Thread(target=mark, daemon=True).start()

    def _on_installed_ids(self, ids):
        for pid, btn in getattr(self, "_mod_btns", {}).items():
            if pid in ids:
                try:
                    if btn.text() == "Install":
                        btn.setText("Installed")
                        btn.setEnabled(False)
                except RuntimeError:
                    pass  # card was replaced by a newer search

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
        self._mod_btns[pid] = btn
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

    # ---------- texture packs page (browse Modrinth) ----------
    def _build_packs_page(self):
        page, bl = self._page()
        bl.addLayout(header("Texture packs", ""))
        brow = QHBoxLayout()
        self.pack_query = QLineEdit()
        self.pack_query.setPlaceholderText("Search texture packs...")
        self.pack_query.returnPressed.connect(self.search_packs_clicked)
        brow.addWidget(self.pack_query, 1)
        bsb = primary(QPushButton("Search"))
        bsb.clicked.connect(self.search_packs_clicked)
        brow.addWidget(bsb)
        badd = QPushButton("Add texture pack file...")
        badd.clicked.connect(self._add_pack_file)
        brow.addWidget(badd)
        bopen = QPushButton("Open texture pack folder")
        bopen.clicked.connect(self._open_packs_folder)
        brow.addWidget(bopen)
        bl.addLayout(brow)
        self.pack_ver_cb = QCheckBox("Only packs made for my selected version")
        self.pack_ver_cb.toggled.connect(lambda _: self.search_packs_clicked())
        bl.addWidget(self.pack_ver_cb)
        self.pack_status = label("", "muted")
        bl.addWidget(self.pack_status)
        bsa = QScrollArea()
        bsa.setWidgetResizable(True)
        binner = QWidget()
        self.pack_results = QVBoxLayout(binner)
        self.pack_results.setContentsMargins(0, 0, 8, 0)
        self.pack_results.setSpacing(10)
        self.pack_results.addStretch(1)
        bsa.setWidget(binner)
        bl.addWidget(bsa, 1)
        self.pack_search_id = 0
        self._packs_loaded = False
        self._pack_btns = {}
        self.nav_group.buttonClicked.connect(self._maybe_load_packs)
        return page

    def _maybe_load_packs(self, btn):
        if btn is self.nav_buttons[2] and not self._packs_loaded:
            self._packs_loaded = True
            self.search_packs_clicked()

    # ---------- create page (createtextures.com pack maker + PvP mashup, inside the launcher) ----------
    def _build_create(self):
        """The Create page (createtextures.com web view) was removed; this keeps the page numbering intact."""
        page, cl = self._page()
        self._create_view = None
        self._webengine_ok = False
        return page

    def _ad_block_setup(self, prof):
        """Block ad networks and hide leftover ad slots in the Create tab's browser."""
        try:
            from PySide6.QtWebEngineCore import QWebEngineScript, QWebEngineUrlRequestInterceptor

            class _Blocker(QWebEngineUrlRequestInterceptor):
                def interceptRequest(self, info):
                    try:
                        if is_ad_host(info.requestUrl().host()):
                            info.block(True)
                    except Exception:
                        pass

            self._ad_blocker = _Blocker(self)
            prof.setUrlRequestInterceptor(self._ad_blocker)
            js = ("(function(){var s=document.createElement('style');s.textContent=%s;"
                  "(document.head||document.documentElement).appendChild(s);})();" % json.dumps(AD_HIDE_CSS))
            sc = QWebEngineScript()
            sc.setName("chrome-client-adhide")
            sc.setSourceCode(js)
            sc.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
            sc.setWorldId(QWebEngineScript.ScriptWorldId.ApplicationWorld)
            sc.setRunsOnSubFrames(True)
            prof.scripts().insert(sc)
        except Exception:
            pass  # ad blocking is a nice-to-have; never stop the page from loading

    def _create_back(self):
        v = self._create_view
        if v is not None and v.history().canGoBack():
            v.history().back()
        else:
            self.cr_status.setText("Nothing to go back to.")

    def _create_nav_state(self):
        v = self._create_view
        if v is not None:
            self.cr_back.setEnabled(v.history().canGoBack())

    def _create_current_url(self):
        if self._create_view is not None:
            u = self._create_view.url().toString()
            if u:
                return u
        return self.cfg.get("create_url") or "https://createtextures.com/"

    def _open_create_page(self):
        """First visit: make sure the view exists, then load the start page once."""
        self._ensure_create_view()
        if self._create_view is not None and not self._create_loaded:
            self._create_loaded = True
            self._create_view.setUrl(QUrl(self.cfg.get("create_url") or "https://createtextures.com/"))

    def warm_webview(self):
        """Do the web view's one-time window setup at start-up, invisibly, so clicking Create later never
        makes the window flash / look like it relaunched (that flash is Qt switching the window to GPU drawing)."""
        self._ensure_create_view()
        if self._create_view is None:
            return
        keep = self.stack.currentIndex()
        try:
            self.setWindowOpacity(0.0)
            self.show()
            self.stack.setCurrentIndex(6)
            loop = QEventLoop()
            QTimer.singleShot(350, loop.quit)
            loop.exec()
        finally:
            self.stack.setCurrentIndex(keep)
            self.setWindowOpacity(1.0)

    def _ensure_create_view(self):
        """Create the web view (done a moment after start-up, so any window redraw happens then, not on click)."""
        if not self._webengine_ok or self._create_view is not None:
            return
        try:
            from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
            from PySide6.QtWebEngineWidgets import QWebEngineView
            store = APP_DIR / "webdata"
            store.mkdir(parents=True, exist_ok=True)
            prof = QWebEngineProfile("ChromeClient", self)  # its own storage: stays signed in between launches
            prof.setPersistentStoragePath(str(store))
            prof.setCachePath(str(store / "cache"))
            prof.downloadRequested.connect(self._create_download)
            self._ad_block_setup(prof)
            class _Page(QWebEnginePage):
                def createWindow(self, _type):
                    # links that want a new tab/window open in this same view instead (so Back works)
                    tmp = QWebEnginePage(self.profile(), self)
                    tmp.urlChanged.connect(lambda u, t=tmp: (self.setUrl(u), t.deleteLater()))
                    return tmp

            view = QWebEngineView()
            view.setPage(_Page(prof, view))
            self._create_profile = prof
            self._create_view = view
            self.cr_holder.addWidget(view, 1)
            self.cr_maker.clicked.connect(lambda: view.setUrl(QUrl("https://createtextures.com/")))  # the original pack maker
            self.cr_mash.clicked.connect(lambda: view.setUrl(QUrl("https://createtextures.com/tools/pvp-mashup")))
            self.cr_back.clicked.connect(lambda _=False: self._create_back())
            view.urlChanged.connect(lambda _u: self._create_nav_state())
            view.loadFinished.connect(lambda _ok: self._create_nav_state())
            self.cr_back.setEnabled(False)
            self.cr_reload.clicked.connect(view.reload)
            self.cr_start.clicked.connect(lambda: view.setUrl(QUrl(self.cfg.get("create_url") or "https://createtextures.com/")))
        except Exception as e:
            self._webengine_ok = False
            self.cr_status.setText(f"Couldn't start the built-in browser: {e}. Use 'Open in browser' instead.")

    def _create_download(self, dl):
        """Texture packs (.zip) made on the site go straight into your resourcepacks folder."""
        name = dl.downloadFileName() or "download.zip"
        is_pack = name.lower().endswith(".zip")
        folder = Path(self.game_dir()) / "resourcepacks" if is_pack else Path.home() / "Downloads"
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            folder = Path.home()
        stem, suf, n = Path(name).stem, Path(name).suffix, 1
        while (folder / name).exists():
            n += 1
            name = f"{stem} ({n}){suf}"
        dl.setDownloadDirectory(str(folder))
        dl.setDownloadFileName(name)
        dl.isFinishedChanged.connect(lambda: self._create_download_done(dl, name, is_pack))
        dl.accept()
        self.cr_status.setText(f"Downloading {name}...")

    def _create_download_done(self, dl, name, is_pack):
        if not dl.isFinished():
            return
        ok = str(dl.state()).endswith("DownloadCompleted")
        if ok:
            self.cr_status.setText(f"Saved {name} to your texture packs - find it in Library > My texture packs."
                                   if is_pack else f"Saved {name} to your Downloads folder.")
            if is_pack:
                self._refresh_library()
        else:
            self.cr_status.setText(f"Download of {name} didn't finish.")

    # ---------- library page (installed mods + texture packs) ----------
    def _build_library(self):
        page, lay = self._page()
        lay.addLayout(header("Library", ""))
        seg = QHBoxLayout()
        self.lib_group = QButtonGroup(self)
        self.lib_btns = []
        for i, title in enumerate(("My mods", "My texture packs")):
            b = QPushButton(title)
            b.setProperty("seg", True)
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, i=i: self._lib_tab(i))
            self.lib_group.addButton(b)
            self.lib_btns.append(b)
            seg.addWidget(b)
        seg.addStretch(1)
        lay.addLayout(seg)
        self.lib_stack = QStackedWidget()
        lay.addWidget(self.lib_stack, 1)
        self.lib_lists = []
        for i in range(2):
            w = QWidget()
            wl = QVBoxLayout(w)
            wl.setContentsMargins(0, 0, 0, 0)
            wl.setSpacing(10)
            top = QHBoxLayout()
            if i == 0:
                add = primary(QPushButton("Add mod file..."))
                add.clicked.connect(self.add_mod_file)
                opn = QPushButton("Open mods folder")
                opn.clicked.connect(self.open_mods_folder)
                dep = QPushButton("Install missing dependencies")
                dep.clicked.connect(self.fix_deps_clicked)
            else:
                add = primary(QPushButton("Add texture pack..."))
                add.clicked.connect(self._add_pack_file)
                opn = QPushButton("Open packs folder")
                opn.clicked.connect(self._open_packs_folder)
                grp = QPushButton("New group...")
                grp.clicked.connect(lambda: self._edit_group(None))
            top.addWidget(add)
            top.addWidget(opn)
            if i == 0:
                top.addWidget(dep)
            else:
                top.addWidget(grp)
            top.addStretch(1)
            wl.addLayout(top)
            if i == 0:
                self.lib_msg_lbl = label("", "muted")
                wl.addWidget(self.lib_msg_lbl)
            sa = QScrollArea()
            sa.setWidgetResizable(True)
            inner = QWidget()
            il = QVBoxLayout(inner)
            il.setContentsMargins(0, 0, 8, 0)
            il.setSpacing(8)
            il.addStretch(1)
            sa.setWidget(inner)
            wl.addWidget(sa, 1)
            self.lib_stack.addWidget(w)
            self.lib_lists.append(il)
        self.lib_btns[0].setChecked(True)
        self.nav_group.buttonClicked.connect(lambda b: b is self.nav_buttons[3] and self._refresh_library())
        return page

    def _lib_tab(self, i):
        self.lib_stack.setCurrentIndex(i)
        self._refresh_library()

    def search_packs_clicked(self):
        self.pack_search_id += 1
        sid = self.pack_search_id
        q, v = self.pack_query.text().strip(), self.version_box.currentText()
        only = self.pack_ver_cb.isChecked()
        self.pack_status.setText("Searching Modrinth...")

        def work():
            try:
                self.bus.packs.emit(sid, search_packs(q, v, only), "")
            except Exception:
                self.bus.packs.emit(sid, [], "Couldn't reach Modrinth - check your connection and search again.")
        threading.Thread(target=work, daemon=True).start()

    def _on_packs(self, sid, hits, err):
        if sid != self.pack_search_id:
            return
        while self.pack_results.count() > 1:
            drop_widget(self.pack_results.takeAt(0).widget())
        for k in [k for k in self.icon_labels if k.startswith("p:")]:
            del self.icon_labels[k]
        self.pack_status.setText(err or ("" if hits else "No texture packs found."))
        self._pack_btns = {}
        for h in hits:
            self.pack_results.insertWidget(self.pack_results.count() - 1, self._pack_card(h))
        if hits:
            packs_dir = Path(self.game_dir()) / "resourcepacks"

            def mark():
                try:
                    self.bus.installed_pack_ids.emit(installed_project_ids(packs_dir, (".zip",)))
                except Exception:
                    pass  # offline or a locked file: the cards just keep saying Install
            threading.Thread(target=mark, daemon=True).start()

    def _on_installed_pack_ids(self, ids):
        for pid, btn in self._pack_btns.items():
            if pid in ids:
                try:
                    if btn.text() == "Install":
                        btn.setText("Installed")
                        btn.setEnabled(False)
                except RuntimeError:
                    pass  # card was replaced by a newer search

    def _pack_card(self, h):
        c = card()
        row = QHBoxLayout(c)
        row.setContentsMargins(14, 12, 14, 12)
        row.setSpacing(14)
        ic = QLabel()
        ic.setObjectName("modicon")
        ic.setFixedSize(52, 52)
        row.addWidget(ic)
        pid = h["project_id"]
        self.icon_labels["p:" + pid] = ic
        if h.get("icon_url"):
            def fetch(url=h["icon_url"], pid=pid):
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                    with urllib.request.urlopen(req, timeout=15) as r:
                        self.bus.icon.emit("p:" + pid, r.read())
                except Exception:
                    pass
            threading.Thread(target=fetch, daemon=True).start()
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(label(h.get("title", "?"), "h2"))
        col.addWidget(label(h.get("description", ""), "muted"))
        col.addWidget(label(f"{h.get('downloads', 0):,} downloads  -  by {h.get('author', '?')}", "muted"))
        row.addLayout(col, 1)
        btn = primary(QPushButton("Install"))
        btn.setFixedWidth(110)
        btn.clicked.connect(lambda _=False, b=btn, p=pid, t=h.get("title", "pack"): self.install_pack_clicked(b, p, t))
        row.addWidget(btn)
        self._pack_btns[pid] = btn
        return c

    def install_pack_clicked(self, btn, pid, title):
        btn.setEnabled(False)
        btn.setText("Installing...")
        self._pack_btns[pid] = btn
        version = self.version_box.currentText()
        packs_dir = Path(self.game_dir()) / "resourcepacks"

        def work():
            try:
                name, exact = install_pack(pid, version, packs_dir)
                note = "" if exact or not version else f" (it isn't listed for {version}, so I got the newest build - it may still work)"
                self.bus.pack_installed.emit(pid, f"Installed {title}{note}. Turn it on in the Texture packs tab.")
            except Exception as e:
                self.bus.pack_installed.emit("!" + pid, f"{title}: {e}")
        threading.Thread(target=work, daemon=True).start()

    def _on_pack_installed(self, pid, msg):
        failed = pid.startswith("!")
        btn = self._pack_btns.get(pid.lstrip("!"))
        if btn is not None:
            try:
                btn.setEnabled(failed)
                btn.setText("Retry" if failed else "Installed")
            except RuntimeError:
                pass
        self.pack_status.setText(msg)

    def _clear_list(self, il):
        while il.count() > 1:
            drop_widget(il.takeAt(0).widget())

    def _lib_row(self, il, title, sub, checked, on_toggle, on_delete=None, enabled=True, on_edit=None,
                 delete_text="Delete"):
        c = ClickRow()
        if enabled:
            c.setCursor(Qt.CursorShape.PointingHandCursor)
        row = QHBoxLayout(c)
        row.setContentsMargins(16, 10, 16, 10)
        cb = WideCheck(title)
        cb.setChecked(checked)
        cb.setEnabled(enabled)
        cb.toggled.connect(on_toggle)
        c.check = cb
        row.addWidget(cb, 1)
        if sub:
            row.addWidget(label(sub, "muted"))
        if on_edit is not None:
            e = QPushButton("Edit")
            e.setProperty("ghost", True)
            e.clicked.connect(lambda _=False: on_edit())
            row.addWidget(e)
        if on_delete is not None:
            d = QPushButton(delete_text)
            d.setProperty("ghost", True)
            d.clicked.connect(lambda _=False: on_delete())
            row.addWidget(d)
        il.insertWidget(il.count() - 1, c)

    def _purge_pvp_packs(self):
        try:
            pvp_packs.remove_all(self.game_dir())
        except Exception:
            pass

    def _refresh_library(self):
        # rebuilding the lists must not throw the user back to the top
        bars = [sa.verticalScrollBar() for sa in self.findChildren(QScrollArea) if sa.isVisible()]
        keep = [b.value() for b in bars]
        self._refresh_library_inner()
        QTimer.singleShot(0, lambda: [b.setValue(v) for b, v in zip(bars, keep)])

    def _refresh_library_inner(self):
        mc = self.game_dir()
        # mods
        il = self.lib_lists[0]
        self._clear_list(il)
        mods = library.list_mods(mc)
        if not mods:
            il.insertWidget(0, label("No mods yet. Install some on the Mods page, or add a .jar file here.", "muted"))
        for m in mods:
            sub = ("set aside (other version)" if m["parked"] else m["version"])
            self._lib_row(il, m["name"], sub, m["enabled"],
                          lambda on, f=m["file"]: self._toggle_mod(f, on),
                          on_delete=lambda f=m["file"], n=m["name"]: self._delete_mod(f, n))
        # packs
        il = self.lib_lists[1]
        self._clear_list(il)
        packs = sorted(library.list_packs(mc), key=lambda p: p["name"].lower())  # fixed order: toggling never moves a row
        groups = self.cfg.get("pack_groups") or {}
        state = {p["file"]: p["enabled"] for p in packs}
        if groups:
            il.insertWidget(il.count() - 1, label("Groups", "h2"))
        for gname, files in groups.items():
            present = [f for f in files if f in state]
            on = bool(present) and all(state[f] for f in present)
            sub = f"{len(present)} pack{'s' if len(present) != 1 else ''}" + (
                f" ({len(files) - len(present)} missing)" if len(present) != len(files) else "")
            self._lib_row(il, gname, sub, on, lambda v, g=gname: self._toggle_group(g, v),
                          on_delete=lambda g=gname: self._delete_group(g), on_edit=lambda g=gname: self._edit_group(g),
                          delete_text="Delete group")
        if groups and packs:
            il.insertWidget(il.count() - 1, label("All texture packs", "h2"))
        if not packs:
            il.insertWidget(0, label("No texture packs yet. Add a .zip pack here, or put it in the packs folder.", "muted"))
        for p in packs:
            self._lib_row(il, p["name"], p["desc"], p["enabled"], lambda on, f=p["file"]: self._toggle_pack(f, on),
                          on_delete=lambda f=p["file"], n=p["name"]: self._delete_pack(f, n))

    def _toggle_mod(self, file, on):
        mc = self.game_dir()
        try:
            if not on:
                need = library.dependents(mc, file)
                if need:
                    names = ", ".join(n for _f, n in need)
                    r = QMessageBox.question(self, "Chrome Client",
                                             f"{names} need(s) this mod to work.\nTurn them off too?",
                                             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                                             | QMessageBox.StandardButton.Cancel)
                    if r == QMessageBox.StandardButton.Cancel:
                        self._refresh_library()
                        return
                    if r == QMessageBox.StandardButton.Yes:
                        for f, _n in need:
                            library.set_mod_enabled(mc, f, False)
            new = library.set_mod_enabled(mc, file, on)
            state = "on" if on else "off"
            self.lib_msg_lbl.setText(f"Turned {state}: {Path(new).name.removesuffix('.disabled')}. "
                                     "Takes effect the next time you press Play. (A mod that isn't made for the "
                                     "version you launch is set aside again automatically.)")
        except Exception as e:
            self.sfx.play("error")
            QMessageBox.warning(self, "Chrome Client",
                                f"Couldn't turn that mod {'on' if on else 'off'}. If Minecraft is open, close it first.\n\n"
                                f"{type(e).__name__}: {e}")
        self._refresh_library()
        if on:
            self._check_deps_async()

    def _check_deps_async(self, announce=False):
        """Switch on / download any mods the switched-on mods need (in the background)."""
        mc, version = self.game_dir(), self.version_box.currentText()
        if not version:
            if announce:
                self.bus.lib_msg.emit("Pick a Minecraft version on the Play page first.")
            return
        if announce:
            self.lib_msg_lbl.setText("Checking what your mods need...")

        def work():
            try:
                res = resolve_dependencies(mc, version)
                msg = describe_deps(*res)
                self.bus.lib_msg.emit(("Done: " + msg + ".") if msg else
                                      ("All the mods they need are already there." if announce else ""))
            except Exception as e:
                self.bus.lib_msg.emit(f"Couldn't check dependencies: {e}" if announce else "")
        threading.Thread(target=work, daemon=True).start()

    def fix_deps_clicked(self):
        self._check_deps_async(announce=True)

    def _on_lib_msg(self, msg):
        if msg:
            self.lib_msg_lbl.setText(msg)
        self._refresh_library()

    def _delete_mod(self, file, name):
        mc = self.game_dir()
        need = [n for f, n in library.dependents(mc, file)] if file.endswith(".jar") else []
        extra = f"\n\n{', '.join(need)} need(s) it and may stop working." if need else ""
        r = QMessageBox.question(self, "Delete mod", f"Delete {name}? The file is removed from your PC.{extra}",
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                 QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes:
            return
        try:
            library.delete_mod(mc, file)
            self.lib_msg_lbl.setText(f"Deleted {name}.")
        except Exception as e:
            self.sfx.play("error")
            QMessageBox.warning(self, "Chrome Client", f"Couldn't delete it (is the game still open?)\n{type(e).__name__}: {e}")
        self._refresh_library()

    def _delete_all_mods(self):
        mc = Path(self.game_dir())
        jars = []
        for folder in (mc / "mods", mc / "mods_disabled"):
            if folder.is_dir():
                jars += [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in (".jar", ".disabled")]
        if not jars:
            QMessageBox.information(self, "Chrome Client", "There are no mods to delete.")
            return
        r = QMessageBox.question(self, "Delete all mods",
                                 f"Delete all {len(jars)} mod files from your PC?\n\nThis can't be undone. Chrome Client, YT Music and the performance "
                                 "mods (Sodium, Lithium...) come back the next time you press Play.",
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                 QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes:
            return
        failed = 0
        for p in jars:
            try:
                p.unlink()
            except Exception:
                failed += 1
        if failed:
            self.sfx.play("error")
            QMessageBox.warning(self, "Chrome Client", f"{failed} file(s) couldn't be deleted (is the game still open?).")
        else:
            QMessageBox.information(self, "Chrome Client", f"Deleted {len(jars)} mod files.")
        try:
            self._refresh_library()
        except Exception:
            pass

    def _delete_pack(self, file, name):
        r = QMessageBox.question(self, "Delete texture pack", f"Delete {name}? The file is removed from your PC.",
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                 QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes:
            return
        try:
            library.delete_pack(self.game_dir(), file)
            self.cfg["pack_groups"] = {g: [f for f in fs if f != file]
                                       for g, fs in (self.cfg.get("pack_groups") or {}).items()}
            save_config(self.cfg)
        except Exception as e:
            self.sfx.play("error")
            QMessageBox.warning(self, "Chrome Client", f"Couldn't delete it (is the game still open?)\n{type(e).__name__}: {e}")
        self._refresh_library()

    def _edit_group(self, name):
        """New group (name None) or edit an existing one."""
        packs = library.list_packs(self.game_dir())
        groups = dict(self.cfg.get("pack_groups") or {})
        dlg = GroupDialog(self, packs, name or "", groups.get(name, []) if name else [])
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_name, files = dlg.result_group()
        if not new_name:
            QMessageBox.information(self, "Chrome Client", "Give the group a name first.")
            return
        if new_name != name and new_name in groups:
            QMessageBox.information(self, "Chrome Client", f"There's already a group called '{new_name}'.")
            return
        out = {}
        for k, v in groups.items():  # keep the order; a renamed group stays where it was
            out[new_name if k == name else k] = files if k == name else v
        if name is None:
            out[new_name] = files
        self.cfg["pack_groups"] = out
        save_config(self.cfg)
        self._refresh_library()

    def _delete_group(self, name):
        r = QMessageBox.question(self, "Delete group", f"Delete the group '{name}'? The packs themselves stay.",
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                 QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes:
            return
        groups = dict(self.cfg.get("pack_groups") or {})
        groups.pop(name, None)
        self.cfg["pack_groups"] = groups
        save_config(self.cfg)
        self._refresh_library()

    def _toggle_group(self, name, on):
        """Turn every pack in the group on (or off) in one go."""
        mc = self.game_dir()
        present = {p["file"] for p in library.list_packs(mc)}
        try:
            for f in (self.cfg.get("pack_groups") or {}).get(name, []):
                if f in present:
                    library.set_pack_enabled(mc, f, on)
        except Exception as e:
            self.sfx.play("error")
            QMessageBox.warning(self, "Chrome Client",
                                f"Couldn't change the group. If Minecraft is open, close it first.\n\n{type(e).__name__}: {e}")
        self._refresh_library()

    def _toggle_pack(self, file, on):
        try:
            library.set_pack_enabled(self.game_dir(), file, on)
        except Exception as e:
            self.sfx.play("error")
            QMessageBox.warning(self, "Chrome Client", f"Couldn't change that pack: {type(e).__name__}: {e}")
        self._refresh_library()

    def _add_pack_file(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Choose texture packs", str(Path.home() / "Downloads"),
                                                "Texture packs (*.zip)")
        problems = []
        added = 0
        for p in paths:
            try:
                library.add_pack(self.game_dir(), p)
                added += 1
            except (ValueError, OSError) as e:
                problems.append(f"{Path(p).name}: {e}")
        if added:
            self.pack_status.setText(f"Added {added} texture pack(s). Turn them on in Library > My texture packs.")
        if problems:
            self.sfx.play("error")
            QMessageBox.warning(self, "Some packs weren't added", "\n".join(problems[:6]))
        self._refresh_library()

    def _open_packs_folder(self):
        d = Path(self.game_dir()) / "resourcepacks"
        d.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(d)))

    # ---------- appearance page ----------
    def _build_appearance(self):
        inner, lay = self._page()
        lay.addLayout(header("Appearance", "Colors, gradients or your own picture. Changes apply instantly and are saved."))

        # --- background ---
        bgc = card()
        bl = QVBoxLayout(bgc)
        bl.setContentsMargins(22, 18, 22, 18)
        bl.setSpacing(12)
        bl.addWidget(label("Background", "h2"))
        self.preview = PreviewStrip()
        bl.addWidget(self.preview)
        seg = QHBoxLayout()
        self.mode_group = QButtonGroup(self)
        self.mode_btns = {}
        for m, title in (("gradient", "Gradient"), ("image", "Picture")):
            b = QPushButton(title)
            b.setProperty("seg", True)
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, m=m: self.set_mode(m))
            self.mode_group.addButton(b)
            self.mode_btns[m] = b
            seg.addWidget(b)
        self.pick_btn = QPushButton("Add pictures...")
        self.pick_btn.setProperty("seg", True)
        self.pick_btn.clicked.connect(self.choose_image)
        seg.addWidget(self.pick_btn)
        self.del_btn = QPushButton("Delete this one")
        self.del_btn.setProperty("seg", True)
        self.del_btn.clicked.connect(self.remove_image)
        seg.addWidget(self.del_btn)
        seg.addStretch(1)
        bl.addLayout(seg)

        self.opts = QStackedWidget()
        # solid
        solid = QWidget()
        sl = QVBoxLayout(solid)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.addWidget(label("The background is the Background color under Custom colors below.", "muted"))
        self.opts.addWidget(solid)
        # gradient
        gw = QWidget()
        gl = QGridLayout(gw)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setHorizontalSpacing(12)
        gl.setVerticalSpacing(10)
        gl.addWidget(QLabel("Colors"), 0, 0)
        stops = QHBoxLayout()
        self.stop_sw = []
        for i in range(3):
            sw = QPushButton()
            sw.setFixedSize(54, 32)
            sw.clicked.connect(lambda _=False, i=i: self.pick_stop(i))
            stops.addWidget(sw)
            self.stop_sw.append(sw)
        self.third_cb = QCheckBox("Use a third color")
        self.third_cb.toggled.connect(self.toggle_third)
        stops.addWidget(self.third_cb)
        stops.addStretch(1)
        gl.addLayout(stops, 0, 1)
        gl.addWidget(QLabel("Angle"), 1, 0)
        arow = QHBoxLayout()
        self.angle_sl = QSlider(Qt.Orientation.Horizontal)
        self.angle_sl.setRange(0, 360)
        self.angle_sl.valueChanged.connect(lambda v: self._slider("angle", v))
        arow.addWidget(self.angle_sl, 1)
        self.angle_lbl = QLabel()
        self.angle_lbl.setMinimumWidth(40)
        arow.addWidget(self.angle_lbl)
        gl.addLayout(arow, 1, 1)
        self.opts.addWidget(gw)
        # image
        iw = QWidget()
        ivl = QVBoxLayout(iw)
        ivl.setContentsMargins(0, 0, 0, 0)
        ivl.setSpacing(10)
        il = QHBoxLayout()
        self.match_btn = primary(QPushButton("Match colors to picture"))
        self.match_btn.clicked.connect(self.match_picture_colors)
        il.addWidget(self.match_btn)
        self.image_lbl = label("", "muted")
        il.addWidget(self.image_lbl, 1)
        ivl.addLayout(il)
        self.gallery = QGridLayout()
        self.gallery.setSpacing(8)
        ivl.addLayout(self.gallery)
        self.opts.addWidget(iw)
        bl.addWidget(self.opts)

        # shared sliders (gradient + picture)
        self.shared = QWidget()
        sg = QGridLayout(self.shared)
        sg.setContentsMargins(0, 0, 0, 0)
        sg.setHorizontalSpacing(12)
        sg.setVerticalSpacing(10)
        self.dim_sl, self.glass_sl = QSlider(Qt.Orientation.Horizontal), QSlider(Qt.Orientation.Horizontal)
        self.dim_lbl, self.glass_lbl = QLabel(), QLabel()
        for r, (title, sl_, lb, key, lo, hi) in enumerate((
                ("Darken", self.dim_sl, self.dim_lbl, "dim", 0, 85),
                ("Glass cards", self.glass_sl, self.glass_lbl, "glass", 0, 100))):
            sg.addWidget(QLabel(title), r, 0)
            sl_.setRange(lo, hi)
            sl_.valueChanged.connect(lambda v, k=key: self._slider(k, v))
            sg.addWidget(sl_, r, 1)
            lb.setMinimumWidth(40)
            sg.addWidget(lb, r, 2)
        sg.setColumnStretch(1, 1)
        bl.addWidget(self.shared)
        lay.addWidget(bgc)

        # --- presets ---
        c = card()
        cl = QVBoxLayout(c)
        cl.setContentsMargins(22, 18, 22, 18)
        cl.setSpacing(10)
        cl.addWidget(label("Color presets", "h2"))
        grid = QGridLayout()
        grid.setSpacing(8)
        for i, (name, th) in enumerate(PRESETS.items()):
            b = QPushButton(name)
            b.setIcon(dot_icon(th["accent"]))
            b.clicked.connect(lambda _=False, th=th: self.apply_theme(dict(th)))
            grid.addWidget(b, i // 4, i % 4)
        cl.addLayout(grid)
        cl.addWidget(label("Gradient presets", "h2"))
        grid2 = QGridLayout()
        grid2.setSpacing(8)
        for i, (name, (stops_, acc_)) in enumerate(GRADIENTS.items()):
            b = QPushButton(name)
            b.setIcon(grad_icon(stops_))
            b.clicked.connect(lambda _=False, st=stops_, ac=acc_: self.apply_theme(gradient_theme(st, ac)))
            grid2.addWidget(b, i // 4, i % 4)
        cl.addLayout(grid2)
        lay.addWidget(c)

        # --- custom colors ---
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

        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.Shape.NoFrame)
        sa.setWidget(inner)
        return sa

    def _swatch_style(self, color):
        t = self.cfg["theme"]
        return (f"background: {color}; border: 2px solid {mix(t['surface'], t['text'], 0.35)}; border-radius: 4px;")

    def pick_color(self, key):
        names = {"bg": "Background", "surface": "Cards & sidebar", "accent": "Accent", "text": "Text"}
        col = ask_color(self, self.cfg["theme"][key], f"{names.get(key, key)} color")
        if col:
            self.apply_theme({**self.cfg["theme"], key: col})

    def hex_edited(self, key):
        txt = self.hex_edits[key].text().strip()
        if not txt.startswith("#"):
            txt = "#" + txt
        if QColor(txt).isValid():
            self.apply_theme({**self.cfg["theme"], key: QColor(txt).name()})
        else:
            self.hex_edits[key].setText(self.cfg["theme"][key])

    def pick_stop(self, i):
        stops = list(self.cfg["theme"]["grad"])
        col = ask_color(self, stops[i], "Gradient color")
        if col:
            stops[i] = col
            self.apply_theme({**self.cfg["theme"], "grad": stops})

    def toggle_third(self, on):
        stops = list(self.cfg["theme"]["grad"])
        if on and len(stops) == 2:
            stops.append(shift_hue(stops[1], 40))
        elif not on and len(stops) == 3:
            stops = stops[:2]
        else:
            return
        self.apply_theme({**self.cfg["theme"], "grad": stops})

    def set_mode(self, mode):
        t = dict(self.cfg["theme"])
        if mode == "image" and t["mode"] != "image":
            # nothing is picked for you: switch to Picture mode with no picture yet and choose from the gallery
            # (or, if you have no saved pictures at all, choose a file first)
            if not bg_pictures():
                if not self.choose_image():
                    self._sync_controls()  # cancelled: keep the old mode
                return
            t["image"] = ""
        t["mode"] = mode
        self._glass_for_picture(t)
        self.apply_theme(t)

    def _glass_for_picture(self, t):
        """Coming from a solid/gradient background into a picture: glass cards go to 60%."""
        if t.get("mode") == "image" and self.cfg["theme"]["mode"] != "image":
            t["glass"] = 60
        return t

    def choose_image(self):
        """Add one or more pictures to your saved library and use the last one."""
        paths, _ = QFileDialog.getOpenFileNames(self, "Choose background pictures", str(Path.home()),
                                                "Pictures (*.png *.jpg *.jpeg *.bmp *.webp *.gif)")
        if not paths:
            return False
        dest, problems = None, []
        for p in paths:
            try:
                dest = save_bg_picture(p)
            except Exception as e:  # unreadable / not an image
                problems.append(f"{Path(p).name}: {e}")
        if problems:
            QMessageBox.warning(self, "Chrome Client", "Couldn't use:\n" + "\n".join(problems[:5]))
        if dest is None:
            return False
        self.apply_theme(self._glass_for_picture({**self.cfg["theme"], "mode": "image", "image": str(dest)}))
        return True

    def use_picture(self, path):
        self.apply_theme(self._glass_for_picture({**self.cfg["theme"], "mode": "image", "image": str(path)}))

    def _refresh_gallery(self):
        pics = bg_pictures()
        key = (tuple(str(p) for p in pics), self.cfg["theme"]["image"])
        if key == getattr(self, "_gallery_key", None):
            return  # same pictures, same selection: switching colors doesn't need to rebuild every thumbnail
        self._gallery_key = key
        while self.gallery.count():
            it = self.gallery.takeAt(0)
            drop_widget(it.widget())
        cur = self.cfg["theme"]["image"]
        for i, p in enumerate(pics):
            b = QPushButton()
            b.setProperty("seg", True)
            b.setCheckable(True)
            b.setChecked(str(p) == cur)
            b.setFixedSize(132, 80)
            b.setIconSize(QSize(120, 68))
            th = bg_thumb(p)
            if th:
                b.setIcon(QIcon(str(th)))
            b.setToolTip(p.stem)
            b.clicked.connect(lambda _=False, p=p: self.use_picture(p))
            self.gallery.addWidget(b, i // 4, i % 4)
        self.gallery.setColumnStretch(4, 1)
        n = len(pics)
        self.image_lbl.setText(f"{n} saved picture{'s' if n != 1 else ''}" if n else "No pictures yet - add some.")

    def match_picture_colors(self):
        t = self.cfg["theme"]
        if not t["image"]:
            return
        try:
            cols = picture_colors(t["image"])
        except Exception as e:
            QMessageBox.warning(self, "Chrome Client", f"Couldn't read colors from the picture: {e}")
            return
        self.apply_theme({**t, **cols})

    def remove_image(self):
        """Delete the picture that's in use from your saved pictures."""
        t = dict(self.cfg["theme"])
        cur = Path(t["image"]) if t["image"] else None
        if cur is None:
            return
        cur.unlink(missing_ok=True)
        (BG_DIR / "thumbs" / (cur.stem + ".png")).unlink(missing_ok=True)
        left = bg_pictures()
        if left:
            t["image"] = str(left[0])
        else:
            t["image"], t["mode"] = "", ("solid" if t["mode"] == "image" else t["mode"])
        self.apply_theme(t)

    def _slider(self, key, value):
        """Live slider change: repaint (and restyle for glass), save a moment later."""
        self.cfg["theme"][key] = value
        self.angle_lbl.setText(f"{self.cfg['theme']['angle']}\u00b0")
        self.dim_lbl.setText(f"{self.cfg['theme']['dim']}%")
        self.glass_lbl.setText(f"{self.cfg['theme']['glass']}%")
        self.root.set_theme(self.cfg["theme"])
        self.preview.set_theme(self.cfg["theme"])
        if key == "glass":
            # the live strip above already shows it; restyle the whole app once the slider settles
            self._restyle_timer.start(140)
        self._save_timer.start(400)

    def _restyle_now(self):
        if self.glass_sl.isSliderDown():  # never restyle in the middle of a drag
            self._restyle_timer.start(140)
            return
        self._apply_qss(self.cfg["theme"])

    def _apply_qss(self, theme):
        # styled on the window (not the whole app): ~4x cheaper, and every dialog is parented to it
        q = build_qss(theme)
        if q == getattr(self, "_last_qss", None):  # backdrop-only change (angle, dim, picture...)
            return
        self._last_qss = q
        self.setUpdatesEnabled(False)
        try:
            self.setStyleSheet(q)
        finally:
            self.setUpdatesEnabled(True)

    def _sync_controls(self):
        t = self.cfg["theme"]
        for k, sw in self.swatches.items():
            sw.setStyleSheet(self._swatch_style(t[k]))
            self.hex_edits[k].setText(t[k])
        for i, sw in enumerate(self.stop_sw):
            sw.setVisible(i < len(t["grad"]))
            if i < len(t["grad"]):
                sw.setStyleSheet(self._swatch_style(t["grad"][i]))
        for w in (self.third_cb, self.angle_sl, self.dim_sl, self.glass_sl):
            w.blockSignals(True)
        self.third_cb.setChecked(len(t["grad"]) == 3)
        self.angle_sl.setValue(t["angle"])
        self.dim_sl.setValue(t["dim"])
        self.glass_sl.setValue(t["glass"])
        for w in (self.third_cb, self.angle_sl, self.dim_sl, self.glass_sl):
            w.blockSignals(False)
        self.angle_lbl.setText(f"{t['angle']}\u00b0")
        self.dim_lbl.setText(f"{t['dim']}%")
        self.glass_lbl.setText(f"{t['glass']}%")
        btn = self.mode_btns.get(t["mode"])
        if btn is not None:
            btn.setChecked(True)
        else:  # plain-color background (from a preset): neither Gradient nor Picture is lit
            self.mode_group.setExclusive(False)
            for b in self.mode_btns.values():
                b.setChecked(False)
            self.mode_group.setExclusive(True)
        self.opts.setCurrentIndex(BG_MODES.index(t["mode"]))
        self.shared.setVisible(t["mode"] != "solid")
        self.pick_btn.setVisible(t["mode"] == "image")
        self.del_btn.setVisible(t["mode"] == "image" and bool(t["image"]))
        self.match_btn.setEnabled(bool(t["image"]))  # nothing to match until you pick a picture
        self._refresh_gallery()
        self.preview.set_theme(t)

    # ---------- Discord Rich Presence ----------
    def _rpc_fmt(self, text):
        info = self._game_info or {"version": self.cfg.get("last_version") or "", "loader": "Vanilla"}
        try:
            return str(text).format(version=info.get("version", ""), loader=info.get("loader", ""))
        except (KeyError, IndexError, ValueError):
            return str(text)  # a stray { } in the text: show it as typed

    def _rpc_update(self):
        r = getattr(self, "rpc", None)
        if r is None:
            return
        c = self.cfg
        cid = c.get("rpc_client_id", "").strip()
        if not c.get("rpc_enabled", True) or not cid:
            r.configure("")
            return
        r.configure(cid)
        playing = self._game_proc is not None and self._game_proc.poll() is None
        det = self._rpc_fmt(c.get("rpc_details_play" if playing else "rpc_details_idle", "")).strip()
        st = self._rpc_fmt(c.get("rpc_state_play" if playing else "rpc_state_idle", "")).strip()
        start = (self._game_start if playing else self._launcher_start) if c.get("rpc_timer", True) else None
        if not det and not st:
            r.set(None)
        else:
            r.set(det or None, st or None, start=start, large_image=(c.get("rpc_image") or "").strip() or None,
                  large_text="Chrome Client")

    def closeEvent(self, ev):
        r = getattr(self, "rpc", None)
        if r is not None:
            try:
                r.set(None)
                time.sleep(0.2)  # let the background thread clear the presence
                r.stop()
            except Exception:
                pass
        super().closeEvent(ev)

    def _rpc_poll(self):
        if self._game_proc is not None and self._game_proc.poll() is not None:
            self._game_proc = None
            self._rpc_update()

    def _crossfade_start(self):
        """Freeze the current look on top of the window; _crossfade_run fades it away once the new theme is in."""
        if not self.isVisible() or self.stack.currentIndex() == 6:  # the web view can't be grabbed cleanly
            return None
        snap = QLabel(self.root)
        snap.setPixmap(self.root.grab())
        snap.setGeometry(self.root.rect())
        snap.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        snap.show()
        snap.raise_()
        return snap

    def _crossfade_run(self, snap):
        old = getattr(self, "_fade_old", None)
        if old is not None:
            old.hide()
            old.deleteLater()
        eff = QGraphicsOpacityEffect(snap)
        snap.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", snap)
        anim.setDuration(260)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

        def done():
            snap.hide()
            snap.deleteLater()
            if getattr(self, "_fade_old", None) is snap:
                self._fade_old = None
        anim.finished.connect(done)
        self._fade_old = snap
        self._fade_anim = anim
        anim.start()

    def apply_theme(self, theme, save=True):
        snap = self._crossfade_start() if save else None  # startup (save=False) doesn't animate
        theme = clean_theme(theme)
        self.cfg["theme"] = theme
        self._apply_qss(theme)
        self.root.set_theme(theme)
        lp = logo_pixmap(theme["accent"], 96, theme["glass"])  # sidebar logo goes glassy with the cards
        self.logo.setPixmap(lp.scaled(40, 40, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation))
        self.setWindowIcon(QIcon(logo_pixmap(theme["accent"], 96)))  # taskbar icon stays solid
        self._sync_controls()
        if snap is not None:
            self._crossfade_run(snap)
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
        self.dir_edit = QLineEdit()
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

        self.hide_cb = QCheckBox("Hide my username and folder paths (for streaming and screenshots)")
        self.hide_cb.setChecked(HIDE_PATHS)
        self.hide_cb.toggled.connect(self._hide_toggled)
        g.addWidget(self.hide_cb, 6, 1, 1, 2)
        self._show_dir()

        self.demo_cb = QCheckBox("Demo mode (no sign-in needed)")
        self.demo_cb.setChecked(self.cfg["demo"])
        self.demo_cb.toggled.connect(lambda _: self._save_settings())
        g.addWidget(self.demo_cb, 4, 1, 1, 2)
        self.sound_cb = QCheckBox("UI sounds")
        self.sound_cb.setChecked(self.cfg["sounds"])
        self.sound_cb.toggled.connect(lambda _: self._save_settings())
        g.addWidget(self.sound_cb, 5, 1, 1, 2)

        lay.addWidget(c)

        mc_card = card()
        mcg = QGridLayout(mc_card)
        mcg.setContentsMargins(22, 18, 22, 18)
        mcg.setHorizontalSpacing(14)
        mcg.setVerticalSpacing(10)
        mcg.setColumnStretch(0, 1)
        mcg.addWidget(label("Mods", "h2"), 0, 0, 1, 2)
        mcg.addWidget(label("Removes every mod jar from your mods folder (also the turned-off ones). "
                            "Chrome Client, YT Music and the performance mods are installed again the next time you press Play.", "muted"), 1, 0)
        del_all = QPushButton("Delete all mods")
        del_all.clicked.connect(self._delete_all_mods)
        mcg.addWidget(del_all, 1, 1)
        lay.addWidget(mc_card)

        dc = card()
        dg = QGridLayout(dc)
        dg.setContentsMargins(22, 18, 22, 18)
        dg.setHorizontalSpacing(14)
        dg.setVerticalSpacing(10)
        dg.setColumnStretch(1, 1)
        dg.addWidget(label("Discord", "h2"), 0, 0, 1, 2)
        self.rpc_cb = QCheckBox("Show what I'm doing on Discord")
        self.rpc_cb.setChecked(self.cfg.get("rpc_enabled", True))
        self.rpc_cb.toggled.connect(lambda _: self._save_settings())
        dg.addWidget(self.rpc_cb, 1, 0, 1, 2)
        self.rpc_edits = {}
        rows = [("rpc_client_id", "Application ID", "paste it from discord.com/developers"),
                ("rpc_details_idle", "In launcher: line 1", ""), ("rpc_state_idle", "In launcher: line 2", ""),
                ("rpc_details_play", "Playing: line 1", "{version} and {loader} get filled in"),
                ("rpc_state_play", "Playing: line 2", ""),
                ("rpc_image", "Image name", "an art asset from your Discord app (default: logo)")]
        for n, (key, text, hint) in enumerate(rows, start=2):
            dg.addWidget(label(text, "h2"), n, 0)
            ed = QLineEdit(str(self.cfg.get(key, "")))
            ed.setPlaceholderText(hint)
            ed.editingFinished.connect(self._save_settings)
            dg.addWidget(ed, n, 1)
            self.rpc_edits[key] = ed
        self.rpc_timer_cb = QCheckBox("Show elapsed time")
        self.rpc_timer_cb.setChecked(self.cfg.get("rpc_timer", True))
        self.rpc_timer_cb.toggled.connect(lambda _: self._save_settings())
        dg.addWidget(self.rpc_timer_cb, 2 + len(rows), 0, 1, 2)
        dg.addWidget(label("One-time: create an app at discord.com/developers, copy its Application ID, and upload a picture "
                           "named 'logo' under Rich Presence > Art Assets. The app's name is what shows after 'Playing'.",
                           "muted"), 3 + len(rows), 0, 1, 2)
        lay.addWidget(dc)

        sc = card()
        sg = QGridLayout(sc)
        sg.setContentsMargins(22, 18, 22, 18)
        sg.setHorizontalSpacing(14)
        sg.setVerticalSpacing(10)
        sg.setColumnStretch(1, 1)
        sg.addWidget(label("Sounds", "h2"), 0, 0, 1, 3)
        self.sound_combos = {}
        for r, (ev, title) in enumerate(EVENTS, start=1):
            sg.addWidget(QLabel(title), r, 0)
            cb = QComboBox()
            cb.setMinimumHeight(34)
            cb.activated.connect(lambda _=0, ev=ev: self._sound_picked(ev))
            sg.addWidget(cb, r, 1, 1, 2)
            self.sound_combos[ev] = cb
        self.vary_cb = QCheckBox("Change the pitch a little on every click (so it never sounds the same twice)")
        self.vary_cb.setChecked(bool(self.cfg.get("vary_pitch", True)))
        self.vary_cb.toggled.connect(self._vary_toggled)
        sg.addWidget(self.vary_cb, len(EVENTS) + 1, 0, 1, 3)
        row = QHBoxLayout()
        add = primary(QPushButton("Add sounds..."))
        add.clicked.connect(self._add_sounds)
        row.addWidget(add)
        rem = QPushButton("Remove a sound...")
        rem.setProperty("ghost", True)
        rem.clicked.connect(self._remove_sound)
        row.addWidget(rem)
        opn = QPushButton("Open sounds folder")
        opn.setProperty("ghost", True)
        opn.clicked.connect(self._open_sounds_folder)
        row.addWidget(opn)
        row.addStretch(1)
        sg.addLayout(row, len(EVENTS) + 2, 0, 1, 3)
        sg.addWidget(label("Add as many sounds as you like (wav, mp3, ogg, flac - up to 3 seconds each), then pick "
                           "one for each action. Stored on your PC only.", "muted"), len(EVENTS) + 3, 0, 1, 3)
        self._refresh_sound_combos()
        lay.addWidget(sc)
        lay.addStretch(1)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.Shape.NoFrame)
        sa.setWidget(page)
        return sa

    def _vary_toggled(self, on):
        self.cfg["vary_pitch"] = bool(on)
        self.sfx.vary = bool(on)
        save_config(self.cfg)

    def _refresh_sound_combos(self):
        choices = sounds.sound_choices()
        for ev, cb in self.sound_combos.items():
            cb.blockSignals(True)
            cb.clear()
            for sid, name in choices:
                cb.addItem(name, sid)
            idx = cb.findData((self.cfg.get("sound_map") or {}).get(ev, "default"))
            cb.setCurrentIndex(max(0, idx))
            cb.blockSignals(False)

    def _sound_picked(self, ev):
        sid = self.sound_combos[ev].currentData()
        m = dict(self.cfg.get("sound_map") or {})
        if sid == "default":
            m.pop(ev, None)
        else:
            m[ev] = sid
        self.cfg["sound_map"] = m
        self.sfx.assign = dict(m)
        save_config(self.cfg)
        self.sfx.preview(sid, ev)

    def _add_sounds(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Add sounds", str(Path.home() / "Downloads"),
                                                "Sounds (*.wav *.mp3 *.ogg *.flac)")
        added, problems = [], []
        for p in paths:
            try:
                added.append(sounds.import_sound(p))
            except RuntimeError as e:
                problems.append(f"{Path(p).name}: {e}")
        self._refresh_sound_combos()
        if added:
            self.sfx.preview(added[-1])
        if problems:
            self.sfx.play("error")
            QMessageBox.warning(self, "Some sounds weren't added", "\n".join(problems[:6]))
        elif added:
            self.status_lbl.setText(f"Added {len(added)} sound(s). Pick them in the lists on the Settings page.")

    def _remove_sound(self):
        lib = sounds.library_sounds()
        if not lib:
            QMessageBox.information(self, "Chrome Client", "You haven't added any sounds yet.")
            return
        name, ok = QInputDialog.getItem(self, "Remove a sound", "Which one?", [Path(n).stem for n in lib], 0, False)
        if not ok:
            return
        sid = f"lib:{name}.wav"
        sounds.remove_sound(sid)
        m = {k: v for k, v in (self.cfg.get("sound_map") or {}).items() if v != sid}
        self.cfg["sound_map"] = m
        self.sfx.assign = dict(m)
        save_config(self.cfg)
        self._refresh_sound_combos()

    def _open_sounds_folder(self):
        LIB_DIR.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(LIB_DIR)))

    def _ram_changed(self):
        self.ram_lbl.setText(f"{self.ram_slider.value() * 512 / 1024:.1f} GB")
        if hasattr(self, "dir_edit"):
            self._save_settings()

    def _show_dir(self):
        """The game folder box: the real path, or a hidden placeholder while 'Hide my username...' is on."""
        if HIDE_PATHS:
            self.dir_edit.setReadOnly(True)
            self.dir_edit.setText("\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022  hidden")
        else:
            self.dir_edit.setReadOnly(False)
            self.dir_edit.setText(self.cfg["minecraft_dir"])

    def _hide_toggled(self, on):
        global HIDE_PATHS
        HIDE_PATHS = bool(on)
        self.cfg["hide_paths"] = HIDE_PATHS
        self._show_dir()
        self._save_settings()

    def _browse_dir(self):
        # (the Windows folder picker itself shows real paths - don't screen-share it)
        d = QFileDialog.getExistingDirectory(self, "Choose game folder", self.cfg["minecraft_dir"])
        if d:
            self.cfg["minecraft_dir"] = d
            self._show_dir()
            self._save_settings()

    def _save_settings(self):
        self.cfg.update({
            "ram_mb": self.ram_slider.value() * 512,
            "minecraft_dir": (self.cfg["minecraft_dir"] if HIDE_PATHS
                              else (self.dir_edit.text().strip() or DEFAULT_MC_DIR)),
            "client_id": self.cid_edit.text().strip(),
            "show_snapshots": self.snap_cb.isChecked(),
            "use_fabric": self.fabric_cb.isChecked(),
            "demo": self.demo_cb.isChecked(),
            "sounds": self.sound_cb.isChecked(),
            "entity_culling": True,    # performance mods (Sodium, Lithium...) are always installed on Play
            "jvm_opt": True,           # tuned Java flags are always on
            "rpc_enabled": self.rpc_cb.isChecked(),
            "rpc_timer": self.rpc_timer_cb.isChecked(),
            **{k: ed.text().strip() for k, ed in self.rpc_edits.items()},
            "last_version": self.version_box.currentText() or self.cfg["last_version"],
        })
        inst = self.current_instance()
        if inst:
            inst["version"] = self.version_box.currentText() or inst.get("version", "")
            inst["fabric"] = self.fabric_cb.isChecked()
        self.sfx.enabled = self.cfg["sounds"]
        save_config(self.cfg)
        self._rpc_update()

    # ---------- versions ----------
    VERSIONS_CACHE = APP_DIR / "versions_cache.json"

    def _load_versions(self):
        """Ask Mojang for the version list (a few tries); if that fails, use the last list we saved."""
        last_err = None
        for attempt in range(3):
            try:
                vs = mll.utils.get_version_list()
                try:
                    APP_DIR.mkdir(parents=True, exist_ok=True)
                    self.VERSIONS_CACHE.write_text(json.dumps(vs), encoding="utf-8")
                except Exception:
                    pass
                self.bus.versions.emit(vs)
                return
            except Exception as e:
                last_err = e
                time.sleep(1.5)
        try:
            vs = json.loads(self.VERSIONS_CACHE.read_text(encoding="utf-8"))
            if vs:
                self.bus.versions.emit(vs)
                self.bus.status.emit("Offline: using the saved version list. Press Refresh when you're back online.")
                return
        except Exception:
            pass
        self.bus.status.emit("Couldn't reach Mojang's servers to load versions - check your connection and press Refresh.")

    def _refresh_versions(self):
        """The Refresh button: try loading the version list again without restarting."""
        self.ver_refresh.setEnabled(False)
        self.status_lbl.setText("Loading versions...")

        def work():
            self._load_versions()
            self.bus.versions_done.emit()
        threading.Thread(target=work, daemon=True).start()

    def _on_versions(self, versions):
        self.versions = versions
        self._fill_versions()

    def _fill_versions(self):
        types = {"release"} | ({"snapshot"} if self.snap_cb.isChecked() else set())
        ids = [v["id"] for v in self.versions if v["type"] in types]
        self.version_box.blockSignals(True)
        self.version_box.clear()
        self.version_box.addItems(ids)
        last = (self.current_instance() or {}).get("version") or self.cfg.get("last_version")
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
            self.acc_btn.setText("Click to sign out")
        else:
            self.acc_name.setText("Not signed in")
            self.avatar.setText("?")
            self.acc_btn.setText("Click to sign in")

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
            self.nav_buttons[5].setChecked(True)
            self.stack.setCurrentIndex(5)
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
        threading.Thread(target=self._play_worker, args=(version, self.game_dir()), daemon=True).start()

    def _play_worker(self, version, gd=None):
        mc_dir = self.cfg["minecraft_dir"]   # shared: game versions, libraries, assets
        gd = gd or mc_dir                    # this instance's own mods, packs, worlds and settings
        Path(gd).mkdir(parents=True, exist_ok=True)
        b = self.bus
        callback = {
            "setStatus": lambda t: b.status.emit(t),
            "setProgress": lambda v: b.progress.emit(int(v), -1),
            "setMax": lambda m: b.progress.emit(0, int(m)),
        }
        try:
            launch_id = version
            try:  # a missing or half-downloaded game jar makes Fabric stop with "Uncaught exception in thread main": fetch it again
                jar = Path(mc_dir) / "versions" / version / (version + ".jar")
                good = False
                if jar.is_file():
                    try:
                        with zipfile.ZipFile(jar) as zf:
                            good = zf.testzip() is None
                    except Exception:
                        good = False
                if not good:
                    if jar.is_file():
                        jar.unlink()
                    b.status.emit("Downloading the game files...")
                    mll.install.install_minecraft_version(version, mc_dir, callback=callback)
            except Exception as e:
                raise RuntimeError("Couldn't download the game files (" + scrub(str(e))[:120] + "). Check your internet connection and press Play again.")
            if self.cfg["use_fabric"]:
                def _fabric_ids():
                    return [v["id"] for v in mll.utils.get_installed_versions(mc_dir)
                            if v["id"].startswith("fabric-loader") and v["id"].endswith(version)]
                if _fabric_ids():
                    b.status.emit("Fabric is already installed.")  # no reinstall: it also fails while the game is open
                    _need_install = False
                else:
                    b.status.emit("Installing Fabric...")
                    _need_install = True
                _orig_run = subprocess.run

                def _run_capture(*a, **k):  # so a failed installer tells us WHY, and no console window pops up
                    if "stdout" not in k and "capture_output" not in k:
                        k["capture_output"] = True
                        k["text"] = True
                        k["errors"] = "replace"
                    if sys.platform == "win32":
                        k.setdefault("creationflags", 0x08000000)
                    return _orig_run(*a, **k)
                if _need_install:
                    subprocess.run = _run_capture
                    try:
                        mll.mod_loader.get_mod_loader("fabric").install(version, mc_dir, callback=callback)
                    finally:
                        subprocess.run = _orig_run
                ids = [v["id"] for v in mll.utils.get_installed_versions(mc_dir)
                       if v["id"].startswith("fabric-loader") and v["id"].endswith(version)]
                if not ids:
                    raise RuntimeError("Fabric install finished but version not found.")
                launch_id = ids[-1]
            else:
                b.status.emit("Installing / verifying files...")
                mll.install.install_minecraft_version(version, mc_dir, callback=callback)

            mods_note = ""
            if self.cfg["use_fabric"]:
                # Mods only work on the version they were made for, but all versions share one
                # mods folder, so set aside the ones that don't fit (nothing is deleted).
                try:
                    bundled = install_bundled_mods(mc_dir)
                    if bundled:
                        mods_note = "installed " + ", ".join(bundled)
                except Exception:
                    pass  # never blocks launching
                try:
                    fix_pack_formats(mc_dir)   # your own resource packs that the game would reject
                except Exception:
                    pass
                b.status.emit("Checking for Chrome Client and YT Music updates...")
                try:
                    rel = install_release_mods(gd, version)
                    if rel:
                        mods_note = (mods_note + ", " if mods_note else "") + "updated " + ", ".join(rel)
                except Exception:
                    pass
                try:
                    parked = park_our_mods_for_26(gd, version)
                    if parked:
                        mods_note = (mods_note + ", " if mods_note else "") + "Chrome Client mods set aside (not built for " + version + " yet)"
                except Exception:
                    pass
                b.status.emit("Updating your mods for this version...")
                up_note = ""
                try:  # mods with a newer build for this version get it; the rest are set aside just below
                    upd, _none = upgrade_mods_for(gd, version)
                    if upd:
                        up_note = f"{len(upd)} mod(s) updated for {version}"
                except Exception:
                    pass  # offline etc. - never blocks launching
                b.status.emit("Matching your mods to this version...")
                try:
                    mods_note = mods_sync.describe(*mods_sync.sync_mods(gd, version))
                except Exception:
                    mods_note = ""
                if up_note:
                    mods_note = (up_note + ", " + mods_note) if mods_note else up_note
                if True:   # performance mods are always installed (no settings box any more)
                    b.status.emit("Checking performance mods...")
                    try:
                        got, bad = ensure_perf_mods(gd, version)
                        if got:
                            mods_note = (mods_note + ", " if mods_note else "") + "installed " + ", ".join(got)
                        if bad:
                            mods_note = (mods_note + ", " if mods_note else "") + "no build for this version: " + ", ".join(bad)
                    except Exception as e:  # never blocks launching
                        mods_note = (mods_note + ", " if mods_note else "") + f"performance mods skipped ({scrub(str(e))[:100]})"
                b.status.emit("Checking mod dependencies...")
                try:
                    dnote = describe_deps(*resolve_dependencies(gd, version))
                    if dnote:
                        mods_note = (mods_note + ", " if mods_note else "") + dnote
                except Exception:
                    pass  # offline etc. - never blocks launching
                try:   # Chrome Client's copy of PolyPlus (3D lobby menu, wardrobe...)
                    if install_chromepoly(gd, version):
                        mods_note = (mods_note + ", " if mods_note else "") + "updated the Chrome Client menu mod"
                except Exception:
                    pass
                try:   # the menu mod needs OneConfig (and Maptip needs Balm): download them automatically, every launch
                    got_libs, bad_libs = ensure_required_libs(gd, version)
                    if got_libs:
                        mods_note = (mods_note + ", " if mods_note else "") + "installed " + ", ".join(got_libs)
                    if bad_libs:
                        mods_note = (mods_note + ", " if mods_note else "") + "couldn't install " + ", ".join(bad_libs)
                except Exception:
                    pass
                try:   # and anything else it lists
                    dnote = describe_deps(*resolve_dependencies(gd, version))
                    if dnote:
                        mods_note = (mods_note + ", " if mods_note else "") + dnote
                except Exception:
                    pass

            try:  # the PvP packs are gone: clear out any left over from older versions
                pvp_packs.remove_all(gd)
            except Exception:
                pass
            pack_msg = ""

            ram = self.cfg["ram_mb"]
            options = {"jvmArguments": jvm_arguments(ram, True), "gameDirectory": str(gd)}
            if self.cfg["demo"]:
                options.update({"username": "Player", "uuid": "", "token": "", "demo": True})
            else:
                b.status.emit("Signing in...")
                name, uuid, token = self._get_session()
                options.update({"username": name, "uuid": uuid, "token": token})

            try:  # a PC with no Java: download the Java this version was made for (no install needed)
                info = mll.runtime.get_version_runtime_information(launch_id, mc_dir)
                if info and not mll.runtime.get_executable_path(info["name"], mc_dir):
                    b.status.emit("Downloading Java for Minecraft...")
                    mll.runtime.install_jvm_runtime(info["name"], mc_dir, callback=callback)
            except Exception as e:
                if not shutil.which("java"):
                    raise RuntimeError("Couldn't get Java for Minecraft (" + scrub(str(e))[:120] + "). Check your internet connection and press Play again.")
            cmd = mll.command.get_minecraft_command(launch_id, mc_dir, options)
            if cmd and not (os.path.isfile(cmd[0]) or shutil.which(cmd[0])):
                raise RuntimeError("Java wasn't found. Press Play again and the launcher will download it.")
            b.status.emit("Launching Minecraft...")
            kw = {}
            if sys.platform == "win32":
                # javaw.exe is the Java that doesn't open a console window; CREATE_NO_WINDOW makes sure of it
                try:
                    exe = Path(cmd[0])
                    if exe.name.lower() == "java.exe" and exe.with_name("javaw.exe").exists():
                        cmd[0] = str(exe.with_name("javaw.exe"))
                except Exception:
                    pass
                kw["creationflags"] = 0x08000000 | 0x00008000  # no console window + above-normal priority for the game
            try:  # game output goes to a log file (handy if it ever crashes) instead of a window
                log = open(APP_DIR / "last_game.log", "w", encoding="utf-8", errors="replace")
                kw.update(stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
            except OSError:
                kw.update(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
            self._game_proc = subprocess.Popen(cmd, cwd=str(gd), **kw)
            self._game_info = {"version": version, "loader": "Fabric" if self.cfg["use_fabric"] else "Vanilla"}
            self._game_start = time.time()
            threading.Thread(target=self._watch_game_start, args=(self._game_proc, version), daemon=True).start()
            try:  # free the launcher's embedded browser (a whole Chromium) while the game runs
                if sys.platform == "win32":
                    import ctypes
                    ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x00004000)  # launcher: below normal
                b.park_web.emit()
            except Exception:
                pass
            b.play_done.emit(True, "Minecraft started." + (f" Mods: {mods_note}." if mods_note else ""))
        except Exception as e:
            b.play_done.emit(False, friendly_login_error(e))

    def _watch_game_start(self, proc, version):
        """If the game dies in its first seconds, say WHY (read from its own log) instead of failing silently."""
        try:
            for _ in range(60):          # up to ~30 s
                if proc.poll() is not None:
                    break
                time.sleep(0.5)
            code = proc.poll()
            if code is None or code == 0:
                return
            try:
                text = (APP_DIR / "last_game.log").read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            strong = ("incompatible mod set", "formattedexception", "exception in thread", "description:", "unsupportedclassversion",
                      "has been compiled by a more recent version", "could not create the java virtual machine", "unrecognized vm option",
                      "unrecognized option", "error: could not", "unable to launch", "requires version", "requires any version",
                      "depends on", "mod resolution", "failed to start")
            hits = []
            for l in lines:
                low = l.lower()
                if any(k in low for k in strong) and "mixin target" not in low and l not in hits:
                    hits.append(l)
            if not hits:
                for l in lines:
                    low = l.lower()
                    if ("caused by" in low or " error]" in low or "/error]" in low or "exception" in low) and not l.startswith("at ") \
                            and "mixin" not in low and "error loading class" not in low and l not in hits:
                        hits.append(l)
            why = "\n".join(hits[:6]) if hits else "\n".join(lines[-8:])
            self.bus.play_done.emit(False, f"Minecraft {version} closed right after starting (exit code {code}).\n\n"
                                           f"{why[:900] or 'No details in the log.'}\n\n"
                                           f"Full log: {APP_DIR / 'last_game.log'}")
        except Exception:
            pass

    def _park_web(self):
        """Stop the embedded browser while the game runs so it doesn't use GPU/CPU/RAM next to Minecraft."""
        v = getattr(self, "_create_view", None)
        if v is None:
            return
        try:
            v.setUrl(QUrl("about:blank"))
            v.page().setAudioMuted(True)
            v.page().setLifecycleState(v.page().LifecycleState.Discarded)
        except Exception:
            try:
                v.page().setLifecycleState(v.page().LifecycleState.Frozen)
            except Exception:
                pass

    def _on_play_done(self, ok, msg):
        self.busy = False
        self.play_btn.setEnabled(True)
        short = msg if len(msg) <= 70 else msg[:67] + "..."
        self.status_lbl.setText(short if not ok else msg)
        self.progress.setValue(self.progress.maximum() if ok else 0)
        self.sfx.play("success" if ok else "error")
        self._rpc_update()
        if not ok:  # the bar is too small for a long error: show all of it
            QMessageBox.warning(self, "Couldn't start Minecraft", msg)


def install_error_hook():
    """Errors inside buttons/switches used to vanish (no console). Save them to crash.log and show them."""
    import traceback
    shown = {"n": 0}

    def hook(etype, value, tb):
        text = "".join(traceback.format_exception(etype, value, tb))
        try:
            APP_DIR.mkdir(parents=True, exist_ok=True)
            with open(APP_DIR / "crash.log", "a", encoding="utf-8") as f:
                f.write(time.strftime("[%Y-%m-%d %H:%M:%S] ") + text + "\n")
        except OSError:
            pass
        if shown["n"] < 3:
            shown["n"] += 1
            try:
                QMessageBox.critical(None, "Chrome Client - something went wrong",
                                     f"{etype.__name__}: {value}\n\n(Details saved to .simple_mc_launcher\\crash.log)")
            except Exception:
                pass
        sys.__excepthook__(etype, value, tb)

    sys.excepthook = hook


def main():
    if sys.platform == "win32":  # so the taskbar shows our icon, not Python's
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ChromeClient.Launcher")
        except Exception:
            pass
    try:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)  # recommended for WebEngine
    except Exception:
        pass
    app = QApplication(sys.argv)
    app.setApplicationName("Chrome Client")
    try:   # Poppins (OFL) ships in the fonts folder next to the launcher
        from PySide6.QtGui import QFontDatabase
        for f in sorted(Path(__file__).resolve().with_name("fonts").glob("*.ttf")):
            QFontDatabase.addApplicationFont(str(f))
    except Exception:
        pass
    install_error_hook()
    ico = Path(__file__).resolve().with_name("chrome_client.ico")
    if ico.exists():
        app.setWindowIcon(QIcon(str(ico)))
    w = Launcher()
    try:
        w.warm_webview()
    except Exception:
        pass
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
