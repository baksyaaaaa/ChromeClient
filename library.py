"""
Your installed mods and texture packs: list them and turn them on/off.

- Mods: a mod is switched off by renaming  name.jar -> name.jar.disabled  (nothing is deleted).
  Minecraft/Fabric only load *.jar, so a .disabled file is ignored. Switch it on and it's renamed back.
- Texture packs: switched on/off in options.txt (the same list the in-game Resource Packs screen edits).
  Close the game first - Minecraft rewrites options.txt when it exits and would undo the change.
"""
import io
import json
import re
import shutil
import zipfile
from pathlib import Path

from pvp_packs import PACK_PREFIX, LEGACY_PREFIXES


# ---------------------------------------------------------------------------
# Mods
# ---------------------------------------------------------------------------
def _mod_info(jar):
    name, version = Path(jar).name.removesuffix(".disabled").removesuffix(".jar"), ""
    try:
        with zipfile.ZipFile(jar) as z:
            meta = json.loads(z.read("fabric.mod.json").decode("utf-8-sig"))
        if isinstance(meta, dict):
            name = str(meta.get("name") or meta.get("id") or name)
            version = str(meta.get("version") or "")
    except Exception:
        pass
    return name, version


def list_mods(mc_dir):
    """[{file, name, version, enabled, parked}] sorted by name. `parked` = set aside for another version."""
    mods, off = Path(mc_dir) / "mods", Path(mc_dir) / "mods_disabled"
    out = []
    if mods.is_dir():
        for p in mods.iterdir():
            if p.is_file() and (p.name.endswith(".jar") or p.name.endswith(".jar.disabled")):
                n, v = _mod_info(p)
                out.append({"file": p.name, "name": n, "version": v,
                            "enabled": p.name.endswith(".jar"), "parked": False})
    if off.is_dir():
        for p in off.glob("*.jar"):
            n, v = _mod_info(p)
            out.append({"file": p.name, "name": n, "version": v, "enabled": False, "parked": True})
    return sorted(out, key=lambda m: (m["parked"], m["name"].lower()))


def set_mod_enabled(mc_dir, file, on):
    """Rename name.jar <-> name.jar.disabled inside the mods folder (a mod that was set aside for another
    version is moved back first when you switch it on). Returns the new file name."""
    mods, off = Path(mc_dir) / "mods", Path(mc_dir) / "mods_disabled"
    name = Path(file).name
    src = mods / name
    if not src.is_file():
        parked = off / name
        if on and parked.is_file():
            mods.mkdir(parents=True, exist_ok=True)
            dst = mods / name
            if dst.exists():
                dst.unlink()
            shutil.move(str(parked), str(dst))
            return name
        raise FileNotFoundError(file)
    if on and src.name.endswith(".disabled"):
        dst = src.with_name(src.name.removesuffix(".disabled"))
    elif not on and src.name.endswith(".jar"):
        dst = src.with_name(src.name + ".disabled")
    else:
        return src.name
    if dst.exists():
        dst.unlink()
    src.rename(dst)
    return dst.name


def delete_mod(mc_dir, file):
    """Delete a mod file for good (from the mods folder or the set-aside folder)."""
    name = Path(file).name
    found = False
    for d in (Path(mc_dir) / "mods", Path(mc_dir) / "mods_disabled"):
        p = d / name
        if p.is_file():
            p.unlink()
            found = True
    if not found:
        raise FileNotFoundError(file)


# ---------------------------------------------------------------------------
# Dependencies between mods
# ---------------------------------------------------------------------------
BUILTIN_DEPS = {"minecraft", "java", "fabricloader", "fabric-loader", "fabric_loader"}


def _read_meta(zf):
    try:
        m = json.loads(zf.read("fabric.mod.json").decode("utf-8-sig"))
        return m if isinstance(m, dict) else None
    except Exception:
        return None


def _ids_of(meta, zf):
    """Every mod id this jar provides: its own, 'provides', and mods nested inside it (jar-in-jar)."""
    ids = set()
    if meta.get("id"):
        ids.add(str(meta["id"]))
    for p in meta.get("provides") or []:
        ids.add(str(p.get("id") if isinstance(p, dict) else p))
    for j in meta.get("jars") or []:
        try:
            with zipfile.ZipFile(io.BytesIO(zf.read(j["file"]))) as inner:
                nm = _read_meta(inner)
                if nm:
                    ids |= _ids_of(nm, inner)
        except Exception:
            pass
    return ids


def mod_details(jar):
    """(ids provided, ids required) for a mod file, or (set(), set()) if it can't be read."""
    try:
        with zipfile.ZipFile(jar) as z:
            meta = _read_meta(z)
            if not meta:
                return set(), set()
            deps = meta.get("depends")
            req = {str(k) for k in deps} - BUILTIN_DEPS if isinstance(deps, dict) else set()
            return _ids_of(meta, z), req
    except Exception:
        return set(), set()


def _scan(mc_dir):
    """[(file, name, enabled, ids, required)] for every mod file directly in the mods folder."""
    out = []
    for m in list_mods(mc_dir):
        if m["parked"]:
            continue
        ids, req = mod_details(Path(mc_dir) / "mods" / m["file"])
        out.append((m["file"], m["name"], m["enabled"], ids, req))
    return out


def missing_dependencies(mc_dir):
    """{mod name: [missing ids]} for mods that are switched on but need something that isn't switched on."""
    scan = _scan(mc_dir)
    have = set()
    for _f, _n, enabled, ids, _r in scan:
        if enabled:
            have |= ids
    out = {}
    for _f, name, enabled, _ids, req in scan:
        if enabled and (miss := sorted(req - have)):
            out[name] = miss
    return out


def disabled_provider(mc_dir, dep_id):
    """File name of a switched-off mod that provides `dep_id` (so we can just switch it on), or None."""
    for f, _n, enabled, ids, _r in _scan(mc_dir):
        if not enabled and dep_id in ids:
            return f
    return None


def dependents(mc_dir, file):
    """Names of switched-on mods that need `file` and have no other provider (used to warn before switching off)."""
    scan = _scan(mc_dir)
    mine = next((ids for f, _n, e, ids, _r in scan if f == file), set())
    others = set()
    for f, _n, enabled, ids, _r in scan:
        if enabled and f != file:
            others |= ids
    need = mine - others
    return [(f, n) for f, n, enabled, _ids, req in scan if enabled and f != file and req & need]


# ---------------------------------------------------------------------------
# Texture packs
# ---------------------------------------------------------------------------
def _read_options(mc_dir):
    opt = Path(mc_dir) / "options.txt"
    return opt, (opt.read_text(encoding="utf-8").splitlines() if opt.exists() else [])


def _enabled_list(lines):
    for line in lines:
        if line.startswith("resourcePacks:"):
            try:
                v = json.loads(line[len("resourcePacks:"):])
                return [str(x) for x in v] if isinstance(v, list) else []
            except ValueError:
                return []
    return []


def _pack_description(p):
    try:
        if p.is_dir():
            meta = json.loads((p / "pack.mcmeta").read_text(encoding="utf-8-sig"))
        else:
            with zipfile.ZipFile(p) as z:
                meta = json.loads(z.read("pack.mcmeta").decode("utf-8-sig"))
        d = meta["pack"]["description"]
        if isinstance(d, dict):
            d = d.get("text", "")
        elif isinstance(d, list):
            d = "".join(x if isinstance(x, str) else x.get("text", "") for x in d)
        return " ".join(re.sub("§.", "", str(d)).split())[:90]
    except Exception:
        return ""


def list_packs(mc_dir):
    """[{file, name, desc, enabled}]  - enabled packs first (in game order, top priority first), then the rest.
    Our own 'Chrome Client PvP ...' packs are left out: those are chosen on the Play page."""
    rp = Path(mc_dir) / "resourcepacks"
    _, lines = _read_options(mc_dir)
    enabled = _enabled_list(lines)
    found = {}
    if rp.is_dir():
        for p in rp.iterdir():
            if p.name.startswith((PACK_PREFIX,) + LEGACY_PREFIXES):
                continue
            if p.is_dir() or p.suffix.lower() == ".zip":
                found[p.name] = p
    out = []
    for e in reversed(enabled):  # last in options.txt = highest priority
        if e.startswith("file/") and e[5:] in found:
            n = e[5:]
            out.append({"file": n, "name": Path(n).stem if n.lower().endswith(".zip") else n,
                        "desc": _pack_description(found.pop(n)), "enabled": True})
    for n, p in sorted(found.items(), key=lambda kv: kv[0].lower()):
        out.append({"file": n, "name": p.stem if p.is_file() else n, "desc": _pack_description(p), "enabled": False})
    return out


def set_pack_enabled(mc_dir, file, on):
    """Turn a pack on (top priority) or off in options.txt. Other entries are kept as they are."""
    opt, lines = _read_options(mc_dir)
    entry = f"file/{Path(file).name}"
    idx = next((i for i, l in enumerate(lines) if l.startswith("resourcePacks:")), None)
    packs = _enabled_list(lines) if idx is not None else ["vanilla"]
    packs = [p for p in packs if p != entry]
    if on:
        if "vanilla" not in packs:
            packs.insert(0, "vanilla")
        packs.append(entry)
    new = "resourcePacks:" + json.dumps(packs, separators=(",", ":"))
    if idx is None:
        lines.append(new)
    else:
        lines[idx] = new
    for i, l in enumerate(lines):  # don't leave it flagged as incompatible
        if l.startswith("incompatibleResourcePacks:"):
            try:
                inc = [x for x in json.loads(l[len("incompatibleResourcePacks:"):]) if x != entry]
                lines[i] = "incompatibleResourcePacks:" + json.dumps(inc, separators=(",", ":"))
            except ValueError:
                pass
    opt.parent.mkdir(parents=True, exist_ok=True)
    opt.write_text("\n".join(lines) + "\n", encoding="utf-8")


def add_pack(mc_dir, src):
    """Copy a .zip texture pack into the resourcepacks folder. Returns the new file name."""
    src = Path(src)
    if src.suffix.lower() != ".zip" or not zipfile.is_zipfile(src):
        raise ValueError("That isn't a .zip texture pack.")
    rp = Path(mc_dir) / "resourcepacks"
    rp.mkdir(parents=True, exist_ok=True)
    dst = rp / src.name
    n = 2
    while dst.exists():
        dst = rp / f"{src.stem} ({n}){src.suffix}"
        n += 1
    shutil.copyfile(src, dst)
    return dst.name


def delete_pack(mc_dir, file):
    """Delete a texture pack (zip or folder) and take it out of the enabled list."""
    name = Path(file).name
    p = Path(mc_dir) / "resourcepacks" / name
    if not p.exists():
        raise FileNotFoundError(file)
    try:
        set_pack_enabled(mc_dir, name, False)
    except OSError:
        pass
    if p.is_dir():
        shutil.rmtree(p)
    else:
        p.unlink()
