"""
Keeps your mods folder matching the Minecraft version you launch.

Mods only work on the Minecraft version(s) they were made for, but all versions share one
`mods` folder. Before launching with Fabric, this reads each mod's fabric.mod.json, moves mods
that don't fit the version into `mods_disabled/`, and moves mods that DO fit back into `mods/`.
So you can flip between 1.21.11 and 26.3 without Fabric refusing to start.

Mods we can't read (not Fabric mods, broken jars) are never touched.
"""
import json
import re
import shutil
import zipfile
from pathlib import Path


def parse_version(s):
    """'1.21.11' -> (1, 21, 11); '26.3-snapshot-10' -> (26, 3); None if it isn't numeric."""
    m = re.match(r"\s*(\d+(?:\.\d+)*)", str(s))
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def _cmp(a, b):
    n = max(len(a), len(b))
    a = tuple(a) + (0,) * (n - len(a))
    b = tuple(b) + (0,) * (n - len(b))
    return (a > b) - (a < b)


def _match_term(mc, term):
    m = re.match(r"^(>=|<=|>|<|=|~|\^)?(.*)$", term)
    op, v = m.group(1) or "=", m.group(2).rstrip("-")  # a trailing '-' only marks pre-releases
    if v in ("", "*"):
        return True
    parts = v.split(".")
    if any(p in ("x", "X", "*") for p in parts):  # wildcard like 1.21.x
        prefix = []
        for p in parts:
            if p in ("x", "X", "*"):
                break
            prefix.append(int(p))
        return tuple(mc[:len(prefix)]) == tuple(prefix)
    t = tuple(int(p) for p in parts)
    c = _cmp(mc, t)
    if op == "=":
        return c == 0
    if op == ">=":
        return c >= 0
    if op == ">":
        return c > 0
    if op == "<=":
        return c <= 0
    if op == "<":
        return c < 0
    if op == "~":
        keep = max(1, len(t) - 1)
        return c >= 0 and tuple(mc[:keep]) == tuple(t[:keep])
    if op == "^":
        return c >= 0 and mc[0] == t[0]
    raise ValueError(term)


def version_matches(mc_version, predicate):
    """Does Minecraft `mc_version` satisfy a Fabric dependency like '>=1.21.11- <1.21.12-'?
    `predicate` may be a string or a list of strings (any one matching is enough).
    Returns True/False, or None if we can't tell."""
    mc = parse_version(mc_version)
    if mc is None:
        return None
    alts = predicate if isinstance(predicate, list) else [predicate]
    try:
        for alt in alts:
            terms = str(alt).split()
            if not terms or all(_match_term(mc, t) for t in terms):
                return True
        return False
    except (ValueError, AttributeError):
        return None


_TAG = re.compile(r"(?:\bmc|\+)(\d+(?:\.\d+){1,2})(?!\d)", re.IGNORECASE)


def version_tags(text):
    """Minecraft versions written into a mod's version/file name, e.g. '0.8.15+mc1.21.11' -> ['1.21.11']."""
    return [tuple(int(x) for x in t.split(".")) for t in _TAG.findall(str(text))]


def _tag_fits(mc_version, tags):
    mc = parse_version(mc_version)
    if mc is None:
        return None
    # a short tag like 'mc1.21' covers 1.21.x; a full tag must match exactly
    return any(tuple(mc[:len(t)]) == t for t in tags)


def mod_fits(jar, mc_version):
    """True if the mod fits this Minecraft version, False if not, None if unknown (leave it alone).

    1. If the mod declares which Minecraft versions it needs, believe that.
    2. Many mods (Sodium, Iris...) don't, but put it in their version, like '+mc1.21.11'. Use that.
    3. Otherwise try the same tag in the file name."""
    jar = Path(jar)
    try:
        with zipfile.ZipFile(jar) as z:
            meta = json.loads(z.read("fabric.mod.json").decode("utf-8-sig"))
    except Exception:
        return None
    if not isinstance(meta, dict):
        return None
    if meta.get("id") in ("chromeclient", "ytmusic", "chromeboost"):
        # our own mods are built with intermediary names for 1.21.11: they can't load on 26.x (unobfuscated), whatever they declare
        return version_matches(mc_version, ">=1.21.11 <1.22")
    depends = meta.get("depends")
    if isinstance(depends, dict) and "minecraft" in depends:
        return version_matches(mc_version, depends["minecraft"])
    for text in (meta.get("version", ""), jar.name):
        tags = version_tags(text)
        if tags:
            return _tag_fits(mc_version, tags)
    return None


def _move(src, dst_dir):
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / src.name
    if dst.exists():
        dst.unlink()
    shutil.move(str(src), str(dst))


def sync_mods(mc_dir, mc_version):
    """Returns (parked, restored, problems): lists of mod file names."""
    mods = Path(mc_dir) / "mods"
    off = Path(mc_dir) / "mods_disabled"
    parked, restored, problems = [], [], []
    if mods.is_dir():
        for jar in sorted(mods.glob("*.jar")):
            if mod_fits(jar, mc_version) is False:
                try:
                    _move(jar, off)
                    parked.append(jar.name)
                except OSError:
                    problems.append(jar.name)
    if off.is_dir():
        for jar in sorted(off.glob("*.jar")):
            if mod_fits(jar, mc_version) is True and not (mods / jar.name).exists():
                try:
                    _move(jar, mods)
                    restored.append(jar.name)
                except OSError:
                    problems.append(jar.name)
    return parked, restored, problems


def describe(parked, restored, problems):
    bits = []
    if parked:
        bits.append(f"{len(parked)} mod(s) for other versions set aside")
    if restored:
        bits.append(f"{len(restored)} mod(s) brought back")
    if problems:
        bits.append(f"couldn't move {len(problems)} (is the game still open?)")
    return ", ".join(bits)
