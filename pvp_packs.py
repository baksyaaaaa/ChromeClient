"""
PvP color resource packs for Chrome Client.

Instead of shipping Mojang's textures, this builds each pack on your machine
from the Minecraft jar you already have installed: it recolors the textures it
finds (obsidian, end crystal, respawn anchor, glowstone, crosshair, ...) and
writes a normal resource pack zip into <minecraft dir>/resourcepacks, then
turns it on in options.txt.

Needs Pillow:  pip install Pillow

CLI (build zips without the launcher):
    python pvp_packs.py 1.21.4 all
    python pvp_packs.py 1.21.4 pink "C:/Users/you/AppData/Roaming/.minecraft"
"""
import colorsys
import fnmatch
import io
import json
import os
import random
import sys
import zipfile
from pathlib import Path

BUILD = "4"  # bump this to force packs to rebuild
PACK_PREFIX = "Chrome Client PvP "
LEGACY_PREFIXES = ("SimpleMC PvP ",)  # the old name: those packs are cleaned up automatically
STAMP_FILE = "chromeclient_stamp.txt"
TEX = "assets/minecraft/textures/"

# hue in degrees
COLORS = {"pink": 328, "green": 125, "blue": 212, "orange": 28, "cherry blossom": 345}
# the colored dot shown for each pack in the launcher
SWATCH = {"pink": "#ff4db0", "green": "#4dff5a", "blue": "#4d95ff", "orange": "#ff9a3d", "cherry blossom": "#ffc2d1"}

# Cherry Blossom is a different style, not just another hue: soft pastel colors plus little petals
# scattered over the textures. How many petals per 16x16 pixels on each kind of texture:
CHERRY = "cherry blossom"
PETALS = {"obsidian": 7, "respawn anchor": 5, "glowstone": 5, "end crystal": 2,
          "totem / pearl / gapples": 2, "clouds": 3, "end sky": 3}
PETAL_COLORS = [(255, 244, 248), (255, 214, 226), (255, 183, 205), (248, 150, 182)]
PETAL_SHAPES = [[(0, 0), (1, 0), (0, 1)], [(0, 0), (1, 0), (1, 1)], [(0, 0), (0, 1), (1, 1)],
                [(1, 0), (0, 1), (1, 1)], [(0, 0), (1, 0)], [(0, 0), (0, 1)]]

# (label, patterns relative to assets/minecraft/textures/, recolor settings)
#   s_floor  - minimum saturation (so grey/black textures actually pick up color)
#   v_mul/v_add - brightness tweak (obsidian is nearly black, so it gets a lift)
#   colorize - force one flat saturation (used for crosshair / sun / moon)
RULES = [
    ("obsidian", ["block/obsidian.png", "block/crying_obsidian.png"],
     dict(s_floor=0.65, v_mul=1.5, v_add=0.10)),
    ("respawn anchor", ["block/respawn_anchor_*.png"], dict(s_floor=0.5, v_mul=1.15)),
    ("glowstone", ["block/glowstone.png", "item/glowstone_dust.png"], dict(s_floor=0.55)),
    ("end crystal", ["entity/end_crystal/*.png", "item/end_crystal.png"], dict(s_floor=0.55)),
    ("totem / pearl / gapples", ["item/totem_of_undying.png", "item/ender_pearl.png",
                                 "item/golden_apple.png", "item/enchanted_golden_apple.png"],
     dict(s_floor=0.5)),
    ("fire overlay", ["block/fire_0.png", "block/fire_1.png"], dict(s_floor=0.5)),
    ("sun / moon", ["environment/sun.png", "environment/moon*.png"],
     dict(s_floor=0.7, colorize=True)),
    ("clouds", ["environment/clouds.png"], dict(s_floor=0.35)),
    ("end sky", ["environment/end_sky.png"], dict(s_floor=0.6, v_mul=1.1)),
    ("crosshair", ["gui/sprites/hud/crosshair*.png"], dict(s_floor=0.9, colorize=True)),
    ("hotbar / xp bar", ["gui/sprites/hud/hotbar_selection.png", "gui/sprites/hud/experience_bar_progress.png"],
     dict(s_floor=0.45)),
    ("hit particles", ["particle/critical_hit.png", "particle/enchanted_hit.png", "particle/damage.png"],
     dict(s_floor=0.6)),
]
# Cherry Blossom only: every oak/jungle/acacia/dark oak/mangrove leaf in the world turns blossom pink
# (vanilla reads leaf colors from this colormap, so no mod is needed)
CHERRY_EXTRA = [("pink leaves", ["colormap/foliage.png"], dict(s_floor=0.16, s_mul=0.42, v_mul=1.15, v_add=0.12))]
PETALS["hit particles"] = 0


def _pil():
    try:
        from PIL import Image, ImageDraw
        return Image, ImageDraw
    except ImportError as e:
        raise RuntimeError("Pillow is missing. Run: pip install Pillow") from e


def recolor(img, hue_deg, s_floor=0.0, s_mul=1.0, v_mul=1.0, v_add=0.0, colorize=False):
    """Set the hue of every pixel, keep alpha. Returns an RGBA image."""
    Image, _ = _pil()
    img = img.convert("RGBA")
    r, g, b, a = img.split()
    h, s, v = Image.merge("RGB", (r, g, b)).convert("HSV").split()
    h = Image.new("L", img.size, int(round(hue_deg / 360 * 255)) % 256)
    floor = int(s_floor * 255)
    if colorize:
        s = Image.new("L", img.size, floor)
    else:
        s = s.point([min(255, max(floor, int(i * s_mul))) for i in range(256)])
    v = v.point([min(255, max(0, int(i * v_mul + v_add * 255))) for i in range(256)])
    rr, gg, bb = Image.merge("HSV", (h, s, v)).convert("RGB").split()
    return Image.merge("RGBA", (rr, gg, bb, a))


def add_petals(img, seed, per_16=5):
    """Scatter small cherry petals over a texture (only on opaque pixels, alpha is kept)."""
    img = img.convert("RGBA")
    w, h = img.size
    px = img.load()
    rng = random.Random(seed)
    big = max(1, min(w, h) // 64)  # on huge textures (clouds) petals are drawn bigger
    for _ in range(max(1, min(500, int(per_16 * w * h / 256)))):
        x, y = rng.randrange(w), rng.randrange(h)
        col = rng.choice(PETAL_COLORS)
        for dx, dy in rng.choice(PETAL_SHAPES):
            for ox in range(big):
                for oy in range(big):
                    xx, yy = x + dx * big + ox, y + dy * big + oy
                    if xx < w and yy < h and px[xx, yy][3] > 40:
                        px[xx, yy] = col + (px[xx, yy][3],)
    return img


def cherry_crosshair(img):
    """Soft pink crosshair with four tiny petals in the corners (the middle stays clear)."""
    img = img.convert("RGBA")
    w, h = img.size
    px = img.load()
    for cx, cy in ((w // 4, h // 4), (w - 1 - w // 4, h // 4), (w // 4, h - 1 - h // 4), (w - 1 - w // 4, h - 1 - h // 4)):
        for dx, dy, col in ((0, 0, (255, 183, 205)), (1, 0, (255, 230, 238)), (0, 1, (255, 230, 238))):
            x, y = cx + dx, cy + dy
            if 0 <= x < w and 0 <= y < h and px[x, y][3] == 0:
                px[x, y] = col + (230,)
    return img


def _soften(params):
    """Pastel version of a rule's recolor settings (used for Cherry Blossom)."""
    p = dict(params)
    p["s_floor"] = p.get("s_floor", 0.0) * 0.5
    p["v_mul"] = p.get("v_mul", 1.0) * 1.05
    p["v_add"] = p.get("v_add", 0.0) + 0.07
    return p


def _png_bytes(img):
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _resource_format(zf):
    """Resource pack format of this Minecraft version, read from its jar."""
    try:
        data = json.loads(zf.read("version.json"))
    except (KeyError, ValueError):
        return None
    pv = data.get("pack_version")
    if isinstance(pv, int):
        return pv
    if isinstance(pv, dict):
        for k in ("resource_major", "resource", "resource_pack"):
            if isinstance(pv.get(k), int):
                return pv[k]
        for k, v in pv.items():
            if "resource" in k and isinstance(v, int):
                return v
    return None


def _pack_mcmeta(fmt, color):
    desc = (f"\u00a7dCherry Blossom \u00a78| \u00a77Chrome Client PvP \u00a7f- petals, pink leaves, pastel PvP"
            if color == CHERRY else f"Chrome Client PvP - {color.title()}")
    if fmt <= 65:  # old style (1.21.8 and older)
        pack = {"pack_format": fmt, "description": desc}
    else:          # 1.21.9+ uses a min/max range
        pack = {"min_format": fmt, "max_format": fmt + 10, "description": desc}
    return json.dumps({"pack": pack}, indent=2)


def _pack_icon(hue, cherry=False):
    Image, ImageDraw = _pil()
    if cherry:  # a detailed sakura blossom on a dusk-rose gradient, drawn big then shrunk for smooth edges
        import math
        S = 512
        bg = Image.new("RGB", (S, S))
        bp = bg.load()
        top, bot = (58, 24, 52), (176, 78, 118)
        for y in range(S):
            t = y / (S - 1)
            row = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3))
            for x in range(S):
                bp[x, y] = row
        rng = random.Random(7)

        def petal(size, rot, fill, notch=True):
            """One heart-tipped petal as an RGBA layer, pointing up from the centre, then rotated."""
            L = Image.new("RGBA", (size * 2, size * 2), (0, 0, 0, 0))
            d = ImageDraw.Draw(L)
            cx, cy = size, size
            pw, ph = size * 0.50, size * 0.95
            d.ellipse([cx - pw, cy - ph, cx + pw, cy + ph * 0.15], fill=fill)
            if notch:  # the little V cut at the tip of a cherry petal
                d.polygon([(cx - pw * 0.16, cy - ph - 2), (cx + pw * 0.16, cy - ph - 2), (cx, cy - ph * 0.80)], fill=(0, 0, 0, 0))
            # soft darker vein from the base up the middle
            d.line([(cx, cy), (cx, cy - ph * 0.62)], fill=(236, 128, 166, 255), width=max(2, size // 38))
            return L.rotate(rot, resample=Image.BICUBIC, center=(cx, cy))

        def paste_center(base, layer, x, y):
            base.alpha_composite(layer, (int(x - layer.width / 2), int(y - layer.height / 2)))

        canvas = bg.convert("RGBA")
        # little drifting petals in the background
        for _ in range(14):
            x, y = rng.randrange(20, S - 20), rng.randrange(20, S - 20)
            if math.hypot(x - S / 2, y - S / 2) < 190:
                continue
            sz = rng.randrange(14, 30)
            paste_center(canvas, petal(sz, rng.randrange(360), (255, 205, 222, 200), notch=False), x, y)
        # the blossom: five petals, a lighter inner glow, then stamens
        for k in range(5):
            ang = k * 72
            lay = petal(200, -ang, (255, 196, 214, 255))
            paste_center(canvas, lay, S / 2, S / 2)
        glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        ImageDraw.Draw(glow).ellipse([S / 2 - 80, S / 2 - 80, S / 2 + 80, S / 2 + 80], fill=(255, 236, 244, 230))
        canvas.alpha_composite(glow)
        d = ImageDraw.Draw(canvas)
        for k in range(10):
            a = math.radians(k * 36 + 9)
            ex, ey = S / 2 + 74 * math.cos(a), S / 2 + 74 * math.sin(a)
            d.line([(S / 2, S / 2), (ex, ey)], fill=(214, 84, 134, 255), width=5)
            d.ellipse([ex - 8, ey - 8, ex + 8, ey + 8], fill=(255, 212, 120, 255))
        d.ellipse([S / 2 - 16, S / 2 - 16, S / 2 + 16, S / 2 + 16], fill=(214, 84, 134, 255))
        return _png_bytes(canvas.convert("RGB").resize((128, 128), Image.LANCZOS))
    base = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(hue / 360, 0.75, 0.55))
    light = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(hue / 360, 0.55, 1.0))
    im = Image.new("RGB", (128, 128), base)
    d = ImageDraw.Draw(im)
    d.polygon([(64, 14), (114, 64), (64, 114), (14, 64)], fill=light)
    d.polygon([(64, 38), (90, 64), (64, 90), (38, 64)], fill=base)
    return _png_bytes(im)


def pack_name(color):
    return f"{PACK_PREFIX}{color.title()}.zip"


def jar_path(mc_dir, version):
    return Path(mc_dir) / "versions" / version / f"{version}.jar"


def build_pack(mc_dir, version, color, out_dir=None):
    """Build the pack zip. Returns (zip_path, textures_changed, missing_labels)."""
    Image, _ = _pil()
    color = color.lower()
    if color not in COLORS:
        raise ValueError(f"Unknown color '{color}'. Pick one of: {', '.join(COLORS)}")
    hue = COLORS[color]
    jar = jar_path(mc_dir, version)
    if not jar.exists():
        raise FileNotFoundError(f"Client jar not found: {jar}")
    dest_dir = Path(out_dir) if out_dir else Path(mc_dir) / "resourcepacks"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / pack_name(color)

    out = {}
    missing = []
    with zipfile.ZipFile(jar) as zf:
        names = sorted(zf.namelist())
        fmt = _resource_format(zf)
        if fmt is None:
            raise RuntimeError("Couldn't read the pack format from this version's jar.")

        cherry = color == CHERRY
        for label, patterns, params in (RULES + CHERRY_EXTRA if cherry else RULES):
            if cherry:
                params = _soften(params)
            hit = False
            for pat in patterns:
                for n in names:
                    if not n.endswith(".png") or n in out or not fnmatch.fnmatch(n, TEX + pat):
                        continue
                    img = recolor(Image.open(io.BytesIO(zf.read(n))), hue, **params)
                    if cherry:
                        if label == "crosshair":
                            img = cherry_crosshair(img)
                        elif PETALS.get(label) and not n.endswith("_beam.png"):
                            img = add_petals(img, n, PETALS[label])
                    out[n] = _png_bytes(img)
                    if n + ".mcmeta" in names:  # keep animations (fire, etc.)
                        out[n + ".mcmeta"] = zf.read(n + ".mcmeta")
                    hit = True
            if not hit:
                missing.append(label)

        # Older versions keep the crosshair inside gui/icons.png (top-left 15x15)
        if "crosshair" in missing and TEX + "gui/icons.png" in names:
            icons = Image.open(io.BytesIO(zf.read(TEX + "gui/icons.png"))).convert("RGBA")
            box = (0, 0, 15, 15)
            icons.paste(recolor(icons.crop(box), hue, s_floor=0.9, colorize=True), box)
            out[TEX + "gui/icons.png"] = _png_bytes(icons)
            missing.remove("crosshair")

        changed = sum(1 for n in out if n.endswith(".png"))
        jar_mtime = int(jar.stat().st_mtime)

    # Overworld sky/fog color: vanilla can't do this from a resource pack, but
    # OptiFine-style colormaps are picked up by OptiFine / Colormatic-type mods.
    sat = 0.30 if color == CHERRY else 0.60
    sky = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(hue / 360, sat, 0.95))
    fog = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(hue / 360, sat * 0.6, 1.0))
    out["assets/minecraft/optifine/colormap/sky0.png"] = _png_bytes(Image.new("RGB", (256, 256), sky))
    out["assets/minecraft/optifine/colormap/fog0.png"] = _png_bytes(Image.new("RGB", (256, 256), fog))

    out["pack.mcmeta"] = _pack_mcmeta(fmt, color).encode()
    out["pack.png"] = _pack_icon(hue, color == CHERRY)
    out[STAMP_FILE] = f"{BUILD}|{version}|{color}|{jar_mtime}".encode()

    tmp = dest.with_name(dest.name + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in out.items():
            z.writestr(name, data)
    os.replace(tmp, dest)
    return dest, changed, missing


def _is_current(dest, version, color):
    try:
        jar_mtime = int(jar_path(dest.parent.parent, version).stat().st_mtime)
        with zipfile.ZipFile(dest) as z:
            return z.read(STAMP_FILE).decode() == f"{BUILD}|{version}|{color}|{jar_mtime}"
    except Exception:
        return False


def set_active_pack(mc_dir, zip_name):
    """Enable our pack in options.txt (or remove ours when zip_name is None).
    Any other packs you have enabled are left alone."""
    opt = Path(mc_dir) / "options.txt"
    lines = opt.read_text(encoding="utf-8").splitlines() if opt.exists() else []
    ours = tuple(f"file/{p}" for p in (PACK_PREFIX,) + LEGACY_PREFIXES)
    entry = f"file/{zip_name}" if zip_name else None

    def edit(key, add):
        for i, line in enumerate(lines):
            if line.startswith(key):
                try:
                    packs = json.loads(line[len(key):])
                except ValueError:
                    packs = ["vanilla"] if add else []
                packs = [p for p in packs if not str(p).startswith(ours)]
                if add:
                    if "vanilla" not in packs:
                        packs.insert(0, "vanilla")
                    packs.append(add)
                lines[i] = key + json.dumps(packs, separators=(",", ":"))
                return True
        return False

    if not edit("resourcePacks:", entry) and entry:
        lines.append("resourcePacks:" + json.dumps(["vanilla", entry], separators=(",", ":")))
    edit("incompatibleResourcePacks:", None)  # never leave ours flagged as incompatible
    opt.parent.mkdir(parents=True, exist_ok=True)
    opt.write_text("\n".join(lines) + "\n", encoding="utf-8")


def apply_pack(mc_dir, version, color):
    """Used by the launcher right before launch. Returns a status string.

    Builds ALL the color packs (only the ones that are missing or out of date), so
    you can swap between them in game - with the Chrome Client mod's menu (press O)
    or the normal Options -> Resource Packs screen. Only the chosen one is switched on."""
    color = (color or "none").lower()
    packs_dir = Path(mc_dir) / "resourcepacks"
    built, failed = 0, {}
    # remove packs of colors that no longer exist (like the old Red one)
    keep = {pack_name(c) for c in COLORS}
    if packs_dir.is_dir():
        for prefix in (PACK_PREFIX,) + LEGACY_PREFIXES:  # also removes the old "SimpleMC PvP ..." zips
            for old in packs_dir.glob(f"{prefix}*.zip"):
                if old.name not in keep:
                    try:
                        old.unlink()
                    except OSError:
                        pass
    for c in COLORS:
        dest = packs_dir / pack_name(c)
        if dest.exists() and _is_current(dest, version, c):
            continue
        try:
            build_pack(mc_dir, version, c)
            built += 1
        except Exception as e:  # e.g. file locked by a running game; keep going
            failed[c] = e
    if color == "none":
        set_active_pack(mc_dir, None)
        return "PvP pack: off" + (f" ({built} packs ready for the in-game menu)" if built else "")
    if color not in COLORS:
        set_active_pack(mc_dir, None)  # e.g. 'red' from an older version: switch the pack off
        return f"PvP pack '{color}' no longer exists - pick another on the Play page"
    dest = packs_dir / pack_name(color)
    if not dest.exists():
        raise failed.get(color) or RuntimeError("Couldn't build the pack.")
    set_active_pack(mc_dir, dest.name)
    return f"PvP {color.title()} pack on" + (f" ({built} packs built)" if built else "")


def remove_all(mc_dir):
    """Delete every pack this launcher ever generated and switch them off. Returns how many were removed."""
    packs_dir = Path(mc_dir) / "resourcepacks"
    n = 0
    try:
        set_active_pack(mc_dir, None)
    except Exception:
        pass
    if packs_dir.is_dir():
        for prefix in (PACK_PREFIX,) + LEGACY_PREFIXES:
            for old in packs_dir.glob(f"{prefix}*.zip"):
                try:
                    old.unlink()
                    n += 1
                except OSError:
                    pass
    return n


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    ver, which = sys.argv[1], sys.argv[2].lower()
    try:
        import minecraft_launcher_lib as _mll
        default_dir = _mll.utils.get_minecraft_directory()
    except Exception:
        default_dir = str(Path.home() / ".minecraft")
    mcd = sys.argv[3] if len(sys.argv) > 3 else default_dir
    for c in (COLORS if which == "all" else [which]):
        p, n, miss = build_pack(mcd, ver, c)
        print(f"{c:7} -> {p}  ({n} textures" + (f"; not found: {', '.join(miss)}" if miss else "") + ")")
