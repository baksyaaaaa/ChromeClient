"""
PvP color resource packs for Simple MC Launcher.

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
import sys
import zipfile
from pathlib import Path

BUILD = "1"  # bump this to force packs to rebuild
PACK_PREFIX = "SimpleMC PvP "
STAMP_FILE = "simplemc_stamp.txt"
TEX = "assets/minecraft/textures/"

# hue in degrees
COLORS = {"pink": 328, "green": 125, "blue": 212, "orange": 28, "red": 0}

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
]


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
    desc = f"SimpleMC PvP - {color.title()}"
    if fmt <= 65:  # old style (1.21.8 and older)
        pack = {"pack_format": fmt, "description": desc}
    else:          # 1.21.9+ uses a min/max range
        pack = {"min_format": fmt, "max_format": fmt + 10, "description": desc}
    return json.dumps({"pack": pack}, indent=2)


def _pack_icon(hue):
    Image, ImageDraw = _pil()
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

        for label, patterns, params in RULES:
            hit = False
            for pat in patterns:
                for n in names:
                    if not n.endswith(".png") or n in out or not fnmatch.fnmatch(n, TEX + pat):
                        continue
                    out[n] = _png_bytes(recolor(Image.open(io.BytesIO(zf.read(n))), hue, **params))
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
    sky = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(hue / 360, 0.60, 0.95))
    fog = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(hue / 360, 0.35, 1.0))
    out["assets/minecraft/optifine/colormap/sky0.png"] = _png_bytes(Image.new("RGB", (256, 256), sky))
    out["assets/minecraft/optifine/colormap/fog0.png"] = _png_bytes(Image.new("RGB", (256, 256), fog))

    out["pack.mcmeta"] = _pack_mcmeta(fmt, color).encode()
    out["pack.png"] = _pack_icon(hue)
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
    ours = f"file/{PACK_PREFIX}"
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
    """Used by the launcher right before launch. Returns a status string."""
    if not color or color.lower() == "none":
        set_active_pack(mc_dir, None)
        return "PvP pack: off"
    color = color.lower()
    dest = Path(mc_dir) / "resourcepacks" / pack_name(color)
    note = ""
    if not (dest.exists() and _is_current(dest, version, color)):
        try:
            dest, changed, missing = build_pack(mc_dir, version, color)
            note = f" ({changed} textures"
            note += f", not found: {', '.join(missing)})" if missing else ")"
        except PermissionError:
            if not dest.exists():  # locked by a running game and nothing to fall back on
                raise
    set_active_pack(mc_dir, dest.name)
    return f"PvP {color.title()} pack on{note}"


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
