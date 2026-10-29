"""Creamy UI sounds, synthesized on first run (no audio assets needed)."""
import math
import shutil
import struct
import subprocess
import sys
import wave
from pathlib import Path

APP_DIR = Path.home() / ".simple_mc_launcher"
SOUND_DIR = APP_DIR / "sounds_v1"


# ---------------------------------------------------------------------------
# Creamy UI sounds: synthesized on first run (no audio assets needed).
# Soft-attack sine "bloops" with a little warmth, a lowpass and a tiny echo.
# ---------------------------------------------------------------------------
SR = 44100


def _bloop(f_start, f_end, dur, decay=20.0, glide=40.0, vol=1.0):
    """One smooth, bubbly note: pitch glides f_start -> f_end, soft attack."""
    n = int(SR * dur)
    out = []
    phase = 0.0
    for i in range(n):
        t = i / SR
        freq = f_end + (f_start - f_end) * math.exp(-t * glide)
        phase += 2 * math.pi * freq / SR
        env = (1 - math.exp(-t * 700)) * math.exp(-t * decay)
        s = math.sin(phase) + 0.22 * math.sin(2 * phase) + 0.12 * math.sin(0.5 * phase)
        out.append(s * env * vol)
    return out


def _mix(parts):
    """parts: list of (start_seconds, samples)."""
    total = max(int(SR * s) + len(x) for s, x in parts)
    buf = [0.0] * total
    for s, x in parts:
        o = int(SR * s)
        for i, v in enumerate(x):
            buf[o + i] += v
    return buf


def _finish(buf, path, gain=0.55):
    # one-pole lowpass for warmth
    a = 0.22
    y = 0.0
    for i, v in enumerate(buf):
        y += a * (v - y)
        buf[i] = y
    # creamy little echo tail
    for delay, fb in ((0.035, 0.30), (0.07, 0.16)):
        d = int(SR * delay)
        buf.extend([0.0] * d)
        for i in range(d, len(buf)):
            buf[i] += buf[i - d] * fb
    peak = max(1e-9, max(abs(v) for v in buf))
    scale = gain / peak
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, v * scale)) * 32767)) for v in buf))


def _build_sounds():
    SOUND_DIR.mkdir(parents=True, exist_ok=True)
    defs = {
        "click": lambda: _mix([(0, _bloop(520, 760, 0.17, decay=24))]),
        "toggle": lambda: _mix([(0, _bloop(620, 900, 0.15, decay=26))]),
        "select": lambda: _mix([(0, _bloop(700, 1000, 0.16, decay=24)), (0.045, _bloop(900, 1200, 0.14, decay=28, vol=0.6))]),
        "play": lambda: _mix([(i * 0.07, _bloop(f * 0.9, f, 0.35, decay=11, vol=1.0 - i * 0.12))
                              for i, f in enumerate((523, 659, 784, 1047))]),
        "success": lambda: _mix([(0, _bloop(660, 880, 0.3, decay=12)), (0.1, _bloop(880, 1175, 0.4, decay=10))]),
        "error": lambda: _mix([(0, _bloop(330, 220, 0.28, decay=14, glide=25)), (0.1, _bloop(260, 175, 0.3, decay=14, glide=25, vol=0.8))]),
    }
    for name, make in defs.items():
        p = SOUND_DIR / f"{name}.wav"
        if not p.exists():
            _finish(make(), p)


class SoundPlayer:
    def __init__(self):
        self.enabled = True
        self.ok = True
        try:
            _build_sounds()
        except Exception:
            self.ok = False
        self.cmd = None
        if sys.platform not in ("win32", "darwin"):
            for c in ("paplay", "pw-play", "aplay", "ffplay"):
                if shutil.which(c):
                    self.cmd = [c, "-nodisp", "-autoexit", "-loglevel", "quiet"] if c == "ffplay" else [c]
                    break

    def play(self, name):
        if not (self.enabled and self.ok):
            return
        path = str(SOUND_DIR / f"{name}.wav")
        try:
            if sys.platform == "win32":
                import winsound
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            elif sys.platform == "darwin":
                subprocess.Popen(["afplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif self.cmd:
                subprocess.Popen(self.cmd + [path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
