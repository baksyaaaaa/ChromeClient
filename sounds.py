"""Creamy UI sounds, synthesized on first run (no audio assets needed)."""
import time
import base64
import hashlib
import math
import random
import shutil
import struct
import subprocess
import sys
import threading
import wave
from array import array
from pathlib import Path

APP_DIR = Path.home() / ".simple_mc_launcher"
SOUND_DIR = APP_DIR / "sounds_v4"


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


def _finish(buf, path, gain=0.55, a=0.22, echo=((0.035, 0.30), (0.07, 0.16))):
    # one-pole lowpass for warmth
    a = a
    y = 0.0
    for i, v in enumerate(buf):
        y += a * (v - y)
        buf[i] = y
    # creamy little echo tail
    for delay, fb in echo:
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


# The bubble-pop sound every button / toggle / play / success / error uses by default (trimmed from the file you sent).
_POP_B64 = (
    "UklGRqRwAABXQVZFZm10IBAAAAABAAEAgLsAAAB3AQACABAAZGF0YYBwAAD+//3//v//////AAD///3//f/9//3//f/9//z//P/8"
    "//v/+//6//r/+v/7//v/+v/7//r/+//8//r/+v/7//r/+v/5//n/+v/6//n/+f/6//j/9//3//X/9P/0//T/9P/0//H/8f/v/+7/"
    "7f/r/+r/6v/p/+n/5//l/+b/5f/k/+T/4//j/+L/3//g/+D/3//d/93/3f/e/9//3v/f/97/3v/e/93/3v/e/9//3v/f/+L/4//j"
    "/+b/5v/n/+f/5//o/+n/6v/r/+r/6v/s/+z/7v/y//P/9f/2//j/+f/7//z///8AAAAABQAHAAkACwAOABEAEgASABQAFgAZABkA"
    "GQAZABgAGAAZABoAGgAbAB0AIAAgAB8AHgAfACEAIQAiACEAIQAiACAAHQAhACIAIAAhAB8AGgAYABcAEwARAA0ACQAMAAwACAAH"
    "AAgABgACAAMABAAGAAYACAAMAA8AEgAXABgAFQAUABMAEgAQABEAFQAVABEAEAASABUAFgAWABgAGQAWABUAGgAdABoAGwAjACQA"
    "IgAnACcAIwAkACQAHgAbAB4AIgAhACAAIQAhACIAJAAnACYAJwAoACIAHgAjAB4AFwAdACEAHAAdACUAJwAnACkAKgArAC4AMgA0"
    "ADYAOAA7ADoANQAxADYAOwA2AC4AMAA1AC0AIwAjACQAJAAmACIAHgAgAB0AGAAfACQAHQAXABsAHgAdAB4AHQAcAB0AHgAgACAA"
    "IAAfABgADQAOABIABwD8/wAACwAJAAQAAwAGAAsADwARABkAIAAdABsAHgAaAA4ABgADAP7/9f/y/+z/4f/e/+X/4v/V/9D/1P/R"
    "/83/zP/H/8T/x//E/8D/xP/K/8z/z//O/8f/wf/D/8D/vf/A/8T/xP/C/8T/y//R/9b/3//q//j/BQAMABAAHwAxADoAQwBPAFoA"
    "ZABwAHgAeQB4AHwAigCaAJ4AoQCqALIAtgC5ALsAvAC/AMkA2gDkAOEA5AD3AAkBGAEuAUIBUgFiAXMBgwGSAZ8BrwHDAcwBygHP"
    "AdYB2QHlAfgBAQIGAhECIgI6Ak0CUwJfAnQCfgJ/An0CcAJmAmkCZgJXAlICVgJVAlACRAI2AiYCDgLlAbYBlgGAAVsBLAEYAREB"
    "8gDZAM4AkgBKAEEANAD//+7/wP8P/43+4f51/4T/Cf+X/rD+1v5o/kX+8/4c/3/+lf73/kH+pf2R/pv/Tf9Y/r79v/0//rb+yP7b"
    "/lL/5/8jAAgABgBEAGMATQBdAJ4A7QAqAfsAiACwAIgBGwINAvUBKwJ+ApkCYwIeAgYCAgIIAjYCZwJCAqYB0QAmAOT/HQDlAEsC"
    "OARUBuwHYQimB/UFlQMUAe/+G/2Q+5n6MPr7+eT5+/ky+o/6GPub+9772fur+3b7Qfv7+oD6jfkT+FD2dPSA8pbw7O6O7W/shOu6"
    "6hPqqOmF6aTp7+k76oDqzuri6nzq8uml6W7pJ+ny6LboSOjA5xrnOeaL5Yrl2+XG5S7lguRF5NTkEOZ/59ToHep46//sye7B8Lny"
    "kfQ89rj3C/k9+mf7sfwZ/nf/ygAqApoDIQXKBo0IagptDIIOjRCcEqwUlhZcGBAaoBsGHVUehx+DIFQhECK2Ik0j3CNUJLckFiVk"
    "JYslkCV0JRwlhCS8I8cimyEyIIcelBxgGvkXXhWQEpoPhgxUCQgGqgI6/7n7Mviq9CLxpO1E6g3n++MN4UzeuttP2Q7XANUp04rR"
    "F9C7znDNTcxSy1vKXsl4yLjHFceUxkzGQ8ZuxsrGXscpyCLJSsqjyxrNm84t0NzRotN31WTXatl424Xdkt+n4dPjMObD6HbrPO4m"
    "8VL02Pe7+9j/5wOwBxoLNw45EVcUqRcvG+QeoiIxJngpgSxcLxsy0DRyN+k5LTxHPjJA70GEQ/xEXkapR8xIvEmAShdLfUu4S8ZL"
    "n0tBS6ZKwkmZSC9HdkVmQwJBTj5iO2A4UzVAMjIvEyy6KBwlRiFBHSYZBRXQEH4MGAidAxT/ivr39VHxr+wg6J7jON/82uHW5NIR"
    "z2zL+MfHxObBVL/+vNW617gUt5m1c7Sxs0uzNLNws/Kzp7SItZ625bdiuRu7EL1Gv8XBdsRQx3LK381w0RLV0Nio3KLgzeQa6Wvt"
    "wvEv9p36+f4/A3YHmgusD64TnBdvGyIfvCJEJrUpCy1DME8zKjbaOFc7mj2nP4ZBMkOrROpF6EazR2FI4kgdSRNJxUgtSE9HMkbY"
    "REpDgkFoP/I8KjoZN78zIjBDLCco2iNkH9AaMRaOEd0MGghDA1j+Zfl99Kvv8+pR5r/hT90b2SjVbdHtza3Kssf7xIPCTsBivr+8"
    "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"
    "1/2Q/k3/CgDJAIYBQAL0AqEDSATiBHEF9QVnBswGIgdkB5UHswe/B7gHnAdwBy8H3AZ4BgMGfwXsBE0EogPtAjECbgGoAOL/Gf9T"
    "/pD90vwd/HD7zvo5+rD5OPnQ+Hr4N/gI+Oz34/fv9w/4QfiH+N/4SvnF+U365PqH+zX86/yq/W7+Nf/+/8QAiwFOAgoDvgNoBAYF"
    "mAUbBo4G8gZDB4EHrQfBB8MHsgeKB1EHBAekBjMGsgUiBYUE3gMqA3ACsAHqACMAXP+W/tT9GP1i/Lb7FfuB+vv5hPkf+cr4h/hW"
    "+Dr4Mfg9+Fz4jvjT+Cv5k/kM+pT6KvvL+3j8K/3n/ab+aP8rAO4ArQFoAhsDxgNnBPsEgwX8BWUGvAYABzQHVAdhB1sHQQcUB9QG"
    "gQYeBqoFJwWXBPoDUgOiAuoBLgFuAK7/7v4w/nb9w/wY/Hf74/pb+uP5evki+d34qfiI+Hv4gfia+Mf4BvlW+bj5Kfqo+jX7zftw"
    "/Bv9zP2D/jv/9f+tAGQBFgK/AmED/AOIBAgFewXcBS8GcAaeBroGwwa6Bp0GcAYwBt8FfwUPBZAEBwRxA9ICLQJ/AdAAHQBr/7r+"
    "C/5i/cH8J/yY+xP7nfo1+tz5k/lb+Tf5Ivkg+TL5U/mI+c35IvqH+vj6ePsD/Jf8Nf3b/YT+Mf/f/4sANgHdAX8CGQOqAzEErAQa"
    "BXoFygUKBjkGWAZkBl4GSAYgBucFnwVHBeEEbwTwA2cD1QI8Ap0B+QBSAK3/CP9l/sf9Lv2f/Bj8mvsr+8f6cvos+vX50Pm7+bb5"
    "xPni+RD6Tvqc+vf6YPvV+1X83vxu/QX+ov4//9//fwAaAbQBSALVAlgD0gNABKIE9gQ+BXYFngW2Bb8FuQWiBXwFRgUCBbAEUQTm"
    "A3AD8gJqAt8BTgG3ACEAiv/0/mH+0P1J/cf8Tfzg+3v7I/vZ+pz6bvpM+jv6OvpF+mL6jPrE+gr7Wvu3+yD8kfwK/Yz9Ev6b/if/"
    "tP8/AMkATwHQAUsCvAIlA4UD1wMeBFkEhASkBLUEuASvBJcEcwRBBAMEvANqAw8DqwJAAtIBXgHnAHAA9/+B/w3/nP4x/sn9bP0V"
    "/cf8h/xN/CD8APzp++D74vvx+wz8Mfxh/Jv83/wr/X/92v07/qD+Cf9z/9//SQCzABkBfAHaATACggLLAgoDQANrA4wDoQOrA6oD"
    "nQOGA2QDOAMCA8ICfAItAtgBfwEfAb8AXAD4/5T/MP/Q/nT+Gv7H/Xr9NP35/MT8mfx4/GH8U/xR/Fj8afyF/Kr82PwO/Uz9k/3f"
    "/S/+h/7h/j3/m//6/1YAswAMAWIBtAEAAkUChAK6AugCDwMqAzwDRQNDAzcDIgMDA9sCqwJyAjMC6wGdAUwB9ACaAD4A4v+F/yn/"
    "zv53/iT+1v2M/Ur9EP3d/LL8kfx6/Gr8Z/xt/Hv8lvy4/OL8F/1S/ZX93f0s/n/+1f4w/4z/6P9DAJ8A+ABOAZ8B7AEzAnMCqwLb"
    "AgUDJAM5A0YDSANBAzADFQPxAsUCkAJVAhICyAF5ASYBzwB2ABoAwP9l/wn/s/5e/g7+xP2A/UP9Df3h/L38ovyR/Ir8jPyZ/K78"
    "zPz0/CP9W/2Z/d/9K/55/s3+JP99/9b/LwCIAN4AMQGCAcwBEAJPAoUCswLZAvYCCQMUAxUDDAP7At8CvAKQAlwCIQLfAZgBTAH9"
    "AKoAVQABAKz/V/8E/7P+aP4f/t39ov1t/UH9HP0A/e785Pzk/O38/vwY/Tv9Z/2Z/dL9Ev5W/qD+7v48/47/4P8xAIIA0QAdAWUB"
    "qQHnAR4CUAJ7ApwCtgLHAs8CzwLFArICmAJ0AkkCGALeAZ8BWwERAcYAdgAmANf/hP80/+f+nP5V/hT+1/2f/XH9SP0m/Q79/Pz0"
    "/PX8/vwP/Sj9Sf1y/aL92f0U/lX+m/7k/jH/ff/L/xkAZgCxAPkAPgF+AbkB7wEeAkUCZwJ/ApECmQKaApMCgwJrAk0CJgL5AcUB"
    "jQFQAQ8BygCDADsA8/+q/2L/HP/Z/pr+X/4q/vv90P2t/ZL9ff1w/Wr9bP12/Yf9n/2+/eT9D/5B/nf+sf7w/jD/c/+3//r/PAB+"
    "AL4A+wA0AWoBmgHFAeoBBwIeAi8CNwI5AjQCJwISAvkB2AGwAYUBUgEcAeMApgBnACgA6P+o/2n/K//y/rn+hf5X/iz+Cv7r/dT9"
    "xP26/bj9vf3H/dj98f0P/jH+W/6J/rj+8P4o/2L/n//a/xUAUwCMAMUA+QApAVcBfQGfAbwB0wHhAesB7wHqAd8BzgG2AZkBdQFO"
    "ASEB7wC8AIMASgARANj/nv9k/yv/9/7F/pf+bf5J/ir+EP79/e/96P3o/e79+/0N/iX+Qv5n/o/+u/7t/h//Vf+N/8T//f8zAGkA"
    "nwDQAP8AKgFQAXQBkAGoAbkBxAHLAckBwwG2AaEBiQFrAUgBIQH1AMcAlABhACwA9v/B/4z/V/8n//f+y/6k/oH+Yv5I/jT+Jf4e"
    "/hv+HP4m/jT+SP5i/n/+of7H/vD+G/9K/3n/q//c/woAOwBqAJcAwQDoAAwBKwFFAVwBbQF2AX8BfgF4AW4BXgFJAS4BDwHuAMkA"
    "oAB1AEgAGgDs/73/j/9i/zf/D//p/sX+p/6N/nX+Zf5Z/lD+T/5T/ln+Z/55/o/+qv7I/ur+EP83/2D/i/+3/+P/DgA3AGEAiQCr"
    "AM4A7QAGAR0BMAE9AUYBSQFJAUIBNwEoARMB+wDgAMEAnwB6AFMAKwADANv/sf+J/2L/Pf8c//v+3/7H/rL+of6U/oz+iP6J/pD+"
    "mf6n/rr+0P7p/gb/Jf9H/2r/j/+0/9r///8iAEYAaACHAKYAvwDWAOsA+gAGAQ0BDwEPAQoB/wDyAOEAywCzAJgAegBZADkAFQDy"
    "/9D/qv+H/2b/Rf8o/wz/9P7f/s3+wP60/q7+r/6v/rX+wP7N/t7+9P4L/yX/Qf9f/4D/oP/B/+T/BAAlAEYAZACCAJwAtADKANwA"
    "6gD0APoA/gD9APgA7wDiANMAwACqAJIAdgBaADwAHAD9/93/vf+e/37/Yf9H/yz/Ff8C//L+5P7b/tb+0/7W/tr+5P7x/v/+E/8p"
    "/0L/Xf95/5j/t//W//b/FAAzAFAAbACGAJ4AswDFANQA4ADnAO0A7gDsAOcA3gDRAMMAsgCdAIcAcABYADwAIQAHAOz/0v+4/57/"
    "iP9y/17/Tf8+/zH/Kf8i/x//H/8h/yf/Lv86/0j/WP9p/3z/kv+n/7//2P/w/wYAHQA0AEoAXgBxAIIAkACdAKcArwCyALYAtACw"
    "AKoAoQCVAIkAeQBnAFQAPwAoABIA/f/l/87/t/+h/4z/eP9n/1b/SP88/zP/Lf8o/yf/Kf8s/zL/PP9H/1T/ZP93/4r/nf+y/8n/"
    "3//0/woAHwAzAEcAWQBqAHkAhgCQAJYAngCiAKEAoACbAJUAjACBAHQAZABUAEIALgAaAAYA8v/c/8f/s/+f/43/e/9t/1//U/9K"
    "/0T/P/89/z//Qf9G/1D/Wv9m/3b/hf+W/6r/vf/R/+f/+v8NACEAMwBGAFUAZABxAHwAhQCMAI8AkgCRAI4AiQCBAHcAawBeAE8A"
    "PQArABgABADy/93/yv+3/6T/k/+C/3P/aP9c/1P/Tf9I/0f/SP9K/0//V/9g/2z/ev+I/5n/q/+9/9D/5f/3/wkAHAAtAD4ATgBb"
    "AGkAcwB8AIMAhgCJAIkAhgCCAHoAcQBnAFkASgA6ACoAGAAEAPL/3//L/7n/p/+W/4X/d/9r/1//WP9R/0z/S/9L/07/U/9b/2X/"
    "b/99/43/nP+t/8D/0v/l//n/CgAbAC0APgBNAFsAZwBwAHkAfwCDAIQAgwCBAHwAcwBrAF8AUgBEADMAIgAPAP3/6//Y/8b/sv+i"
    "/5L/gv91/2n/X/9X/1D/Tf9M/0z/UP9U/1v/Zf9u/3z/iv+Z/6n/u//M/93/7/8AABAAIAAvADwASQBTAFwAYwBnAGoAawBqAGcA"
    "YQBbAFEARgA7ACwAHQAPAP//7//e/83/v/+u/6H/lP+I/3//dv9v/2v/aP9o/2n/bP9y/3n/gv+N/5n/pv+2/8X/1f/m//b/BAAV"
    "ACUAMwBBAE0AWABhAGgAbQBxAHMAcgBwAGsAZQBeAFQASAA9AC4AIAASAAEA8//k/9T/xf+3/6r/nv+T/4r/gf99/3j/df91/3b/"
    "ef99/4T/jP+V/5//q/+4/8b/0//h//D//f8JABYAIwAuADgAQQBJAFEAVQBYAFsAWgBaAFcAUgBOAEYAPgA1ACoAIAAVAAkA/v/y"
    "/+f/2//Q/8b/vP+0/6z/p/+i/57/nP+b/5z/n/+i/6b/rf+z/7v/xP/N/9f/4v/t//b/AAAJABIAGwAkACsAMQA3ADsAPQBAAD8A"
    "PwA9ADkANgAxACsAJAAcABUADAADAPz/8//r/+P/2v/T/8v/x//C/73/uv+3/7b/t/+4/7n/vP/B/8T/yv/Q/9b/3P/j/+r/8f/4"
    "//7/BAALAA8AFAAaABwAIAAhACIAJAAiACEAHwAdABsAFgASAA0ACAACAP3/+P/x/+v/5v/f/9v/1//R/8//y//J/8f/xv/H/8f/"
    "x//K/8z/z//S/9X/2f/e/+L/5//s//D/9v/7//7/AgAFAAkADAAOABAAEgATABIAEwATABEAEQAPAA0ACwAIAAYAAwAAAP///P/4"
    "//X/8//x/+7/6//p/+j/5v/l/+X/5f/k/+X/5f/m/+b/6f/o/+v/7v/t/+//8f/x//X/9f/1//f/+P/3//n/+v/4//r/+v/3//j/"
    "9//2//T/9P/0//H/8f/x/+//8P/v/+7/7v/t/+7/7v/v/+//8P/x//H/8//0//b/+P/5//r//P/8//////8AAAEAAAABAAIAAAAC"
    "AAAAAAAAAP7//f/8//r/+P/3//T/8v/w/+7/7P/r/+j/5//m/+b/5f/l/+X/5f/l/+b/5//o/+r/6//t/+//8f/z//b/+P/5//v/"
    "/f///wAAAAABAAIAAgACAAIAAgABAAAAAAD+//z/+v/3//X/8//v/+3/6v/n/+X/4//g/9//3f/c/9v/2v/a/9v/2//c/93/3//h"
    "/+T/5//p/+3/7//0//f/+f/9/wAAAQAFAAYACAALAAwADQANAA0ADQAMAAsACQAHAAUAAgAAAP3/+f/1//L/7f/q/+f/4v/g/97/"
    "3P/Z/9f/1//W/9X/1v/X/9j/2v/c/97/4f/k/+j/7P/v//T/+f/8/wAAAgAGAAkADAAPABEAEwAUABUAFQAVABMAEgARAA8ACwAJ"
    "AAYAAAAAAPv/9v/0/+7/6f/n/+L/4P/d/9n/2P/W/9X/1P/U/9X/1f/X/9n/2v/f/+L/5P/o/+z/8f/1//n//f8AAAQABwALAA4A"
    "DwASABQAFAAUABUAFQATABIAEAAMAAkABgACAAAA+//3//L/7v/q/+T/4f/d/9r/1v/U/9P/0P/P/8//zv/Q/9D/0f/T/9X/2f/c"
    "/9//5P/n/+z/8P/1//n//P8AAAMABgAJAAsADgAOAA8ADwAPAA8ADQALAAkABgADAAAA/f/6//T/8f/t/+j/5P/f/9z/2P/V/9L/"
    "0P/O/8z/zf/L/8v/zf/O/9D/0v/W/9n/3P/h/+X/6P/s//H/9f/4//3/AAACAAYACAAJAAsADAANAA0ADQAMAAoACAAHAAMAAAD+"
    "//v/9v/z/+7/6v/m/+L/3//b/9j/1v/T/9H/z//O/8//z//O/9D/0v/U/9f/2f/c/+D/5f/p/+3/8v/2//r//v8AAAMACAAKAAwA"
    "DwARABEAEgASABAAEAAPAAwACgAHAAMAAAD+//r/9//z/+3/6//n/+L/4P/c/9n/2P/V/9T/0//S/9P/0//V/9b/1//a/93/4P/i"
    "/+f/6//u//P/9v/6//7/AAADAAYABwAKAAsADAAMAA0ADgAMAAsACwAIAAYAAwAAAP7/+//3//T/8f/u/+r/5//i/+H/3//c/9v/"
    "2f/Y/9f/2P/Y/9n/2//c/93/4P/j/+b/6P/t/+//8v/3//n//f8AAAAABAAFAAYACQAKAAsACwAKAAoACQAIAAYABAABAAAA/v/6"
    "//f/9P/x/+7/6v/n/+T/4f/f/9z/2//Z/9f/2P/W/9b/2f/X/9n/2f/c/93/3v/i/+X/5v/p/+z/7v/w//P/9f/3//n/+v/7//3/"
    "/f/+//7//v/+//3/+//6//j/9//1//P/8f/u/+v/6//m/+T/5P/h/97/3v/c/9v/2//a/9r/2f/b/9z/3P/e/+D/4P/j/+b/6P/p"
    "/+z/7//y//P/9v/4//n/+//7//z//v/+//7//v/9//3//P/7//r/9//1//T/8f/v/+z/6v/o/+X/4//h/9//3v/c/9r/2v/a/9n/"
    "2P/Z/9r/2f/b/93/3f/f/+L/4v/l/+f/6P/r/+3/7v/w//H/8//1//X/9v/3//b/9//3//b/9f/0//P/8v/w/+7/7f/q/+j/5//k"
    "/+L/4f/e/9z/2//Y/9f/1v/V/9X/1P/U/9P/0//U/9X/1f/W/9j/2v/b/93/3v/g/+L/5P/m/+f/6f/r/+r/7P/t/+3/7v/u/+7/"
    "7v/t/+z/7P/q/+n/6P/m/+X/4//i/+D/3v/d/9z/2f/Y/9f/1v/V/9T/1P/U/9T/1P/U/9T/1v/X/9f/2f/Z/9v/3P/e/+H/4v/j"
    "/+T/5v/n/+j/6v/p/+r/7P/r/+v/6//r/+v/6v/p/+j/5//m/+T/4v/i/+D/3//e/9z/2//a/9n/1//X/9b/1v/W/9T/1v/W/9X/"
    "1v/W/9f/2f/Z/9n/3P/c/93/3//f/+D/4v/i/+T/5P/k/+b/5f/l/+f/5f/m/+X/5f/l/+T/4//i/+L/4P/f/9//3f/c/9z/2v/Z"
    "/9n/2P/Y/9b/1v/X/9b/1//W/9f/1//X/9n/2f/b/9z/3P/d/9//3//h/+H/4v/k/+T/5P/l/+X/5f/m/+b/5f/l/+X/5P/j/+L/"
    "4v/g/9//3v/d/9z/2v/Z/9j/1v/V/9T/0//T/9D/0f/S/9D/0P/R/9D/0P/R/9H/0f/T/9P/1P/W/9b/1v/Y/9n/2v/a/9z/3f/d"
    "/97/3v/e/9//3//f/9//3//e/9//3//d/97/3f/c/9z/2//Z/9n/2f/Y/9f/1//X/9b/1v/W/9b/1f/W/9f/1//Y/9j/2f/a/9v/"
    "3P/c/97/4P/g/+H/4v/j/+T/5f/l/+b/5//m/+j/6P/o/+j/5//o/+j/5v/o/+b/5f/m/+X/5P/k/+T/4//i/+L/4//i/+P/4//i"
    "/+P/4//i/+X/5f/l/+f/5v/n/+n/6f/q/+v/7P/t/+3/7//x//D/8f/y//L/8//0//P/9P/1//T/9P/0//T/9P/0//P/8//y//P/"
    "8f/x//H/8P/w//D/8P/w/+//8P/w//D/8f/x//H/8v/0//L/9P/0//b/9//2//j/+f/5//r/+//8//3//f/+//3///8AAP7/AAAA"
    "AP//AAD//wAA///+//7//f/9//3//P/7//v/+v/6//r/+f/4//j/+P/4//j/+P/3//n/+P/4//j/+P/6//r/+v/7//v//f/9//3/"
    "///+////AAAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAA//8AAP////////3//f/9//z//P/9//z//P/7//z//P/8//z//P/9"
    "//3//f/9//7////+////AAAAAAAAAAAAAAAAAAABAAEAAAABAAEAAQABAAEAAQAAAAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAP//AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQABAAEAAgADAAMAAwADAAQABAAFAAQABQAFAAQABgAGAAQABAAGAAQABAAE"
    "AAMAAwADAAMAAwACAAMAAgABAAMAAgABAAMAAgABAAIAAwABAAMAAwABAAQAAwAEAAYABAAFAAYABgAGAAYABwAHAAcACAAIAAgA"
    "CAAJAAkACQAJAAkACQAJAAkACQAIAAkACgAIAAkACQAJAAoACQAJAAoACQAJAAoACQAJAAoACwALAAwADAAMAA0ADQAOAA4ADgAP"
    "ABAAEAAQABEAEgASABIAFAATABQAFQAUABUAFAAUABYAFQAVABYAFQAWABYAFgAXABYAFwAXABcAFwAYABgAFwAYABgAGAAYABgA"
    "GQAZABkAGwAaABoAGwAbABsAGwAcABwAHQAdAB0AHQAdAB4AHgAeAB8AHgAfAB8AHgAgACAAHwAgACAAIAAgACAAIQAhACEAIAAh"
    "ACEAIAAhACEAIQAhACIAIQAhACIAIgAjACMAIwAjACQAJAAjACQAJAAkACUAJAAlACYAJAAlACUAJAAmACUAJQAlACQAJgAlACUA"
    "JgAlACUAJQAmACYAJQAmACUAJgAmACUAJgAmACUAJgAnACYAJwAnACUAJgAnACcAJgAmACcAJwAmACcAJgAmACUAJgAmACUAJQAl"
    "ACUAJAAkACQAIwAkACMAIwAkACMAIwAjACIAIgAhACEAIgAhACEAIQAgACAAIAAgAB8AHwAfAB4AHgAeAB4AHgAdAB0AHAAcABwA"
    "GwAbABsAGQAaABoAGgAaABgAGAAYABgAGAAWABcAFwAVABYAFQAVABUAFQAVABQAEwATABMAEgASABIADwASABEADwAQAA8ADgAP"
    "AA4ADAAMAAwADAAMAAsACwAKAAkACgAKAAgACAAIAAYABwAIAAYABgAFAAQABQAFAAQAAwAEAAMAAwADAAMAAgABAAEAAAAAAAAA"
    "AAAAAAAAAAD//////v/+//3//f/9//v//f/7//r/+//6//r/+v/5//r/+f/4//j/9//4//f/9v/2//b/9v/0//X/9P/0//T/8v/y"
    "//L/8f/y//H/8P/w//D/8P/v/+7/7v/t/+7/7f/t/+3/7P/r/+z/6//r/+r/6//q/+r/6v/p/+j/6P/o/+j/6P/n/+b/5//m/+b/"
    "5//k/+X/5f/k/+T/5P/l/+P/4v/j/+L/4f/i/+H/4v/h/9//4P/f/9//3//f/97/3f/d/93/3P/d/9z/2//c/9v/2//b/9r/2v/Z"
    "/9r/2f/Z/9r/2f/Y/9n/2P/X/9f/1//W/9b/1v/W/9b/1f/W/9b/1P/U/9X/0//U/9T/0//T/9P/0//T/9L/0//R/9H/0f/R/9D/"
    "0f/R/8//0P/Q/8//z//P/87/zv/O/83/zf/N/83/zP/M/83/zP/L/8z/y//K/8v/yv/K/8r/yv/K/8j/yf/J/8j/yf/I/8f/x//G"
    "/8f/xv/G/8b/xf/G/8X/xP/F/8T/xP/E/8T/xP/D/8P/xP/D/8P/xP/C/8P/w//B/8L/w//B/8H/wf/B/8H/wf/A/7//wP/A/77/"
    "vv++/77/vv+9/73/vf+8/73/vf+7/7v/u/+8/7r/uf+6/7r/uv+6/7n/uf+5/7j/uP+4/7j/t/+3/7f/uP+3/7f/t/+3/7b/tv+2"
    "/7b/tv+1/7T/tf+0/7T/tP+0/7P/tP+z/7P/s/+z/7P/s/+y/7L/s/+y/7P/s/+y/7L/sv+x/7H/sf+y/7L/sf+x/7L/sv+y/7H/"
    "sf+x/7H/sf+x/7H/sv+x/7H/sf+x/7H/sf+w/7H/sf+x/7D/sf+x/7H/sf+y/7H/sv+y/7L/s/+z/7L/s/+0/7P/s/+0/7T/tP+0"
    "/7T/tf+1/7X/tv+1/7b/t/+2/7f/t/+3/7j/uP+5/7j/uf+6/7r/u/+7/7v/vP+8/73/vf+9/7//v/+//8D/wP/B/8L/wf/D/8P/"
    "xP/E/8X/xv/G/8f/yP/H/8n/yf/K/8z/y//N/8//zf/P/9D/0P/R/9P/0//T/9T/1v/W/9b/1//Z/9n/2v/c/9z/3f/e/9//4f/h"
    "/+L/4//k/+X/5f/n/+n/6f/q/+z/7P/t/+7/7//w//H/8v/z//X/9f/2//j/+P/6//v//P/+//7///8AAAAAAgADAAMABAAGAAgA"
    "CAAJAAwADAANAA8ADwARABIAFAAVABUAGAAYABkAGwAcAB0AHwAgACEAIQAkACUAJQAnACkAKgAqACsALAAuADAAMAAxADMANAA1"
    "ADYANwA5ADoAOwA8AD4APwBAAEEAQgBDAEQARgBGAEgASQBJAEsATQBNAE4AUABRAFEAUwBUAFUAVwBXAFgAWgBaAFsAXABcAF4A"
    "XwBgAGAAYQBjAGMAZABmAGYAaABnAGkAawBrAG0AbQBtAG8AbwBwAHIAcgBzAHMAcwB0AHUAdgB2AHcAeQB4AHoAegB6AHwAfAB8"
    "AH0AfwB/AH8AgACBAIEAggCDAIMAhACFAIUAhgCHAIcAhwCHAIkAiACJAIkAiACKAIsAigCMAIsAiwCNAIwAjQCOAIwAjQCPAI0A"
    "jwCPAI8AjwCPAI8AkACQAJAAkQCQAJEAkQCRAJEAkgCRAJEAkgCRAJEAkgCRAJIAkgCRAJIAkQCRAJEAjwCRAJEAjwCQAJAAkACQ"
    "AI8AkACPAI8AjwCPAI8AjgCOAI4AjQCNAI0AjQCMAIwAjACLAIoAiwCLAIoAiQCJAIkAiACGAIcAhgCFAIUAhACEAIMAgwCDAIIA"
    "gACBAIAAfwB/AH8AfQB9AHwAewB7AHoAeQB4AHgAdwB2AHYAdQBzAHMAcwBxAHAAcABvAG4AbQBsAGsAagBpAGkAZwBmAGUAZABj"
    "AGIAYQBgAF4AXgBdAFsAWgBZAFgAVwBWAFQAVABSAFEAUABOAE4ATQBKAEkASQBHAEYARABDAEIAQQA/AD4APAA7ADoAOQA3ADYA"
    "NAAzADIAMAAuAC0AKwAqACgAJwAkACMAIgAhACAAHQAdABsAGAAYABYAEwASABAADgAPAAwACgAJAAYABgADAAIAAQAAAP///f/6"
    "//r/9//2//T/8v/y/+7/7f/s/+r/5//m/+X/4v/h/+D/3f/b/9v/1//W/9X/0v/Q/8//zv/M/8n/x//H/8T/wv/B/77/vf+8/7n/"
    "uP+3/7T/s/+x/7D/rv+r/6r/qP+n/6T/o/+i/5//nv+c/5r/mf+W/5X/k/+S/5D/jv+N/4v/iv+I/4b/hP+D/4H/gP99/33/fP95"
    "/3f/d/91/3P/cv9x/27/bf9s/2v/af9o/2b/Zf9j/2L/Yf9f/17/Xf9b/1v/Wf9X/1b/Vf9U/1L/Uv9Q/0//T/9N/0z/S/9K/0n/"
    "SP9H/0X/RP9E/0L/Qv9B/0D/QP8+/z7/PP87/zv/Ov86/zn/OP84/zf/N/81/zX/Nf8z/zT/M/8x/zP/Mf8x/zH/L/8w/zD/L/8u"
    "/y7/L/8t/y7/Lv8t/y7/Lv8u/y3/Lf8u/y7/Lv8u/y7/Lv8u/y7/L/8u/y7/L/8w/y//MP8w/zH/Mf8x/zL/M/8z/zP/NP80/zX/"
    "Nv82/zf/OP84/zn/Ov86/zz/PP89/z7/P/8//0H/Qv9C/0P/RP9F/0f/R/9I/0r/S/9L/03/Tv9O/0//Uv9T/1P/Vf9W/1f/Wf9Z"
    "/1r/XP9e/1//X/9i/2P/ZP9m/2f/aP9q/2v/bP9u/3D/cf9y/3T/dv93/3n/ev98/37/f/+B/4P/hP+G/4f/iP+K/43/jv+P/5L/"
    "k/+U/5b/l/+a/5v/nP+f/6D/ov+k/6X/qP+p/6r/rf+u/7D/sf+z/7X/t/+4/7v/vP++/8D/wf/D/8X/xv/I/8r/zf/O/8//0f/T"
    "/9X/1v/Y/9r/3P/f/9//4P/k/+X/5v/o/+r/7P/t/+//8v/z//X/9//3//r/+//9/wAAAAABAAMAAwAGAAgACQALAA0ADgAQABIA"
    "EgAVABcAGAAaABwAHAAeACEAIQAkACUAJwAoACoAKwAtAC4AMAAxADMANQA2ADcAOQA7ADwAPgA+AEAAQwBDAEQARwBIAEkASwBM"
    "AEwATwBPAFEAUgBTAFYAVQBXAFoAWQBbAF0AXgBfAGAAYQBjAGQAZgBnAGcAaQBqAGsAbQBtAG4AcABwAHIAcwB0AHUAdgB2AHcA"
    "eQB6AHoAewB9AH0AfwCAAIAAgQCCAIMAhACFAIYAhgCHAIkAiQCJAIsAjACMAI0AjQCOAI8AjwCRAJEAkQCTAJIAkwCVAJUAlQCX"
    "AJcAlwCYAJkAmQCaAJoAmwCbAJsAmwCcAJ0AngCeAJ4AngCfAJ8AoACgAKEAoQChAKEAogCiAKIApACjAKMApACkAKQApQClAKQA"
    "pQCmAKUApgCmAKUApgCmAKYApgCmAKcApwCnAKcApwCnAKcApwCoAKcApwCnAKgApwCnAKcApwCnAKcApwCnAKcApwCnAKcApwCm"
    "AKcApwCmAKcApgCmAKYApQCmAKUApQClAKQApQCkAKQApACkAKMAowCjAKMAogChAKIAoQChAKEAoQCgAJ8AnwCeAJ8AngCdAJ4A"
    "nQCdAJwAmwCcAJsAmgCaAJkAmQCYAJcAmACWAJYAlgCVAJUAlACUAJMAlACSAJEAkgCQAJAAjwCPAI4AjQCNAIwAiwCLAIoAiQCJ"
    "AIkAiACHAIYAhgCFAIQAgwCDAIIAgQCBAH8AfwB/AH0AfQB8AHsAewB6AHkAeQB4AHcAdgB1AHQAdABzAHMAcQBwAHAAbwBvAG4A"
    "bABsAGsAagBpAGkAaABmAGcAZgBkAGQAYwBiAGEAYABgAF4AXgBdAFwAXABaAFkAWQBXAFgAVgBVAFUAVABTAFIAUQBQAFAATwBN"
    "AE0ASwBKAEsASQBIAEcARgBGAEUAQwBDAEIAQQBAAD4APgA9AD0APAA6ADoAOAA4ADcANgA1ADQAMwAyADAAMQAvAC0ALwAtACsA"
    "KwAqACkAKQAnACYAJQAkACQAIgAiACEAHwAeAB8AHQAbABwAGwAZABgAGAAXABYAFQAUABMAEgARABAADwAOAAwADAALAAoACQAJ"
    "AAgABgAGAAUAAwADAAEAAAAAAAAA//////7//f/8//v/+v/5//j/9//2//X/9P/z//L/8v/w/+//8P/t/+3/6//r/+v/6P/o/+f/"
    "5f/m/+T/4//i/+D/4P/g/97/3v/d/9z/2//a/9j/2P/X/9b/1f/V/9P/0v/S/9H/zv/O/83/zP/L/8v/yv/I/8j/x//F/8X/xP/C"
    "/8L/wf/A/8D/vv+9/73/u/+7/7r/uP+4/7f/tv+1/7T/tP+y/7H/sf+v/67/r/+t/6v/q/+q/6n/qP+o/6b/pv+l/6P/o/+j/6H/"
    "oP+g/57/nv+d/5v/m/+b/5n/mf+Z/5f/lv+V/5X/lP+T/5P/kf+R/5D/jv+P/47/jP+M/4v/iv+K/4n/iP+I/4f/hv+G/4X/hP+E"
    "/4T/gv+B/4H/gP9//3//fv99/33/fP97/3r/ev96/3n/eP94/3f/dv92/3b/dP90/3T/c/90/3P/cf9x/3H/cP9w/2//b/9u/27/"
    "bv9t/23/bP9s/2v/a/9r/2v/a/9q/2n/av9p/2j/aP9o/2f/Z/9o/2b/Z/9n/2X/Zv9m/2X/Zf9l/2X/Zf9l/2X/ZP9l/2T/ZP9l"
    "/2T/Y/9k/2X/ZP9j/2X/ZP9k/2T/ZP9l/2T/Zf9l/2T/Zf9l/2X/Zf9l/2b/Zf9m/2b/Zv9n/2j/aP9n/2j/aP9o/2n/aP9p/2v/"
    "af9r/2z/a/9t/2z/bf9u/23/b/9v/2//cP9w/3H/cv9x/3L/dP90/3T/dv92/3b/d/93/3n/ev96/3v/e/99/33/fv+A/3//gf+C"
    "/4L/hP+E/4T/hv+H/4f/iP+K/4v/i/+N/43/jv+Q/5H/kv+T/5T/lv+W/5f/mf+Z/5v/nP+d/5//oP+h/6L/ov+l/6b/pv+p/6n/"
    "q/+s/63/rv+w/7H/sv+0/7X/t/+3/7n/uv+8/73/vv/A/8L/wv/E/8b/x//I/8r/y//M/87/0P/Q/9P/1P/V/9b/2P/b/9v/3P/f"
    "/9//4f/j/+T/5v/n/+n/6v/r/+3/7//x//H/9P/1//b/+f/6//v//f/+/wAAAAABAAMABAAHAAgACQAKAAwADwAPABEAEwATABcA"
    "FwAYABsAGwAdAB4AIAAiACMAJQAnACcAKQArACwALgAvADAAMgA0ADUANwA5ADoAOwA8AD0AQABBAEIAQwBFAEYASABIAEoATABN"
    "AE8ATwBRAFIAVABVAFYAVwBZAFkAXABdAF0AXgBgAGEAYgBjAGQAZgBnAGcAagBqAGoAbQBsAG0AcABwAHEAcgBzAHUAdAB3AHcA"
    "dwB6AHkAewB7AHwAfQB9AH8AfwB/AIIAgQCDAIMAgwCFAIUAhQCGAIYAiACJAIkAigCJAIoAiwCLAI0AjACMAI4AjgCOAI4AjwCP"
    "AI8AkACQAJAAkQCRAJEAkgCSAJIAkgCSAJIAkwCSAJIAkwCTAJIAkwCTAJIAkwCTAJIAkgCTAJIAkgCSAJIAkwCSAJIAkgCRAJEA"
    "kQCQAJEAkACQAJAAjwCPAI4AjgCOAI4AjgCMAIwAjACMAIsAigCLAIoAiACIAIgAhwCHAIYAhgCFAIQAhQCDAIIAggCCAIAAgQB/"
    "AH0AfgB+AH0AfAB7AHoAegB5AHgAeAB3AHYAdgB0AHMAcwByAHEAcABvAG8AbQBtAG0AagBqAGoAaQBoAGcAZgBlAGQAYwBiAGEA"
    "YQBgAF8AXQBdAFwAWwBaAFgAWABXAFYAVQBUAFMAUgBRAFAATwBNAEwATQBLAEoASQBJAEgARgBGAEUAQgBDAEIAQAA/AD4APgA8"
    "ADsAOwA5ADkAOAA3ADYANQA0ADMAMwAyADAAMAAuAC4ALQAtACwAKgAqACgAKAAnACUAJgAlACQAJAAhACEAIQAfAB8AHgAdAB0A"
    "HAAbABoAGwAaABkAGAAYABcAFgAVABUAFQAVABMAEgASABIAEgAQABAAEAAPAA8ADgAPAA0ADQANAAwADQAMAAsACwAJAAoACgAJ"
    "AAkACAAJAAkACAAJAAcACAAIAAYABwAHAAUABgAGAAUABgAFAAUABAAEAAUABQAEAAQAAwAEAAQAAwADAAQAAwADAAQAAwADAAQA"
    "AwADAAMAAgADAAIAAgADAAMAAwADAAMAAwACAAIAAgADAAMAAgADAAMAAgADAAMAAgACAAIAAgADAAIAAwADAAIAAgADAAIAAwAB"
    "AAIAAwABAAIAAQACAAIAAAABAAEAAQAAAAAAAQAAAAAAAQAAAAAAAAAAAAAAAAAAAAAAAAAAAP////8AAP/////+//7//v/9//7/"
    "/f/9//3//P/6//v//P/7//r/+v/6//n/+v/5//f/+P/3//f/+P/2//X/9f/0//T/9P/0//L/8v/y//H/8P/v/+//7v/u/+7/7f/t"
    "/+z/6//r/+v/6//p/+j/6P/m/+b/5v/l/+T/5P/j/+L/4f/g/9//3//e/93/3f/c/9z/2//a/9n/2P/X/9X/1v/V/9P/1P/T/9L/"
    "0f/Q/8//zf/N/83/y//L/8r/yf/I/8f/x//F/8X/xP/E/8T/wP/A/8H/vv++/73/vf+8/7r/uv+4/7j/t/+3/7b/tP+0/7P/sv+x"
    "/7H/sf+u/67/rv+r/6v/rP+r/6n/qP+o/6j/pv+m/6b/pP+j/6T/ov+i/6H/oP+f/5//n/+e/53/nf+c/5v/m/+b/5r/mv+Z/5j/"
    "l/+Y/5j/lv+X/5f/lv+V/5P/lP+V/5T/k/+T/5P/k/+T/5H/kv+S/5H/kf+R/5H/kP+Q/5D/kP+Q/5D/kP+Q/5D/kP+Q/5D/kP+R"
    "/5D/j/+Q/5D/kP+R/5H/kf+S/5H/kf+R/5D/k/+T/5P/lP+T/5T/lP+V/5X/lf+X/5b/lv+X/5f/l/+Y/5v/mv+a/5z/m/+b/53/"
    "nf+e/5//n/+f/6H/of+g/6L/o/+l/6X/pf+m/6f/qP+o/6j/q/+r/6v/rP+s/63/sP+v/7D/sv+y/7L/tP+z/7X/t/+3/7n/uv+5"
    "/7r/uv+7/77/vv/A/8H/wf/C/8H/xP/G/8X/xv/H/8j/yf/J/8v/zP/N/87/0P/Q/9D/0P/S/9P/1P/W/9b/1v/Y/9f/2f/b/9z/"
    "3f/e/93/3v/f/+H/4f/j/+T/5f/m/+b/5v/n/+j/6//r/+v/6//t/+7/7v/v//H/8f/y//P/8v/z//X/9v/3//f/+P/5//j/+v/6"
    "//v//f/9//7/////////AAAAAAAAAgACAAMAAwADAAMABQAFAAYABwAIAAcACAAJAAkACwALAAsADAALAAsADAANAA4ADwAQABAA"
    "DwAPABAAEAARABIAEgASABMAEgASABMAFAAVABUAFQAVABUAFQAVABYAFgAXABgAFwAWABcAFwAYABkAGQAYABgAGQAYABgAGAAa"
    "ABoAGgAaABkAGQAaABoAGgAbABsAGgAZABoAGQAaABsAGwAbABoAGQAZABkAGQAbABsAGwAaABkAGAAYABoAGwAaABoAGQAYABgA"
    "GAAYABkAGQAZABgAFwAXABYAFgAXABcAGAAXABYAFQAVABUAFwAWABUAFQAUABIAEgATABQAFQAUABMAEgASABAAEAASABEAEgAR"
    "AA8ADwAPAA8AEAAPAA8ADgANAAwACwAMAA0ADQANAAwADAALAAoACQAJAAsACgAKAAkABwAHAAcABwAJAAgABwAGAAUABAAEAAQA"
    "BQAEAAQAAwADAAIAAQACAAMAAgACAAAAAAAAAAAAAAAAAAAAAAD///3//f/9//3//f/9//7//f/7//r/+v/7//z/+//7//n/+f/4"
    "//f/9//5//r/+f/4//f/9v/2//X/9f/3//b/9f/0//L/8v/z//X/9P/0//T/8v/x//D/8f/x//L/8f/x//D/7//v/+//7//w//H/"
    "7//t/+7/7P/s/+7/7v/v/+7/7P/s/+v/6v/r/+3/7f/s/+v/6v/p/+r/6//s/+3/6//q/+n/6P/p/+n/6v/r/+r/6v/o/+j/6P/p"
    "/+r/6v/q/+r/6P/n/+j/6f/q/+r/6//p/+f/6P/n/+j/6v/r/+v/6f/o/+j/6P/p/+n/6//r/+n/6P/o/+j/6P/q/+z/6//r/+v/"
    "6f/q/+r/6//s/+z/7P/r/+r/6f/s/+7/7v/v/+7/7P/s/+v/7P/u//D/8f/w/+//7v/u//D/8P/y//P/8v/y//H/8P/y//T/9P/1"
    "//X/8//0//T/8//0//f/+P/3//f/9//2//b/+f/6//r/+f/6//r/+f/5//v//f/9//7//v/8//z//f/9/wAAAAAAAAAAAAD+////"
    "AAABAAMABAACAAEAAAAAAAMABAAGAAYABgAFAAMABQAGAAgACQAJAAgACAAHAAcACAALAA0ADAAMAAsACwAKAAwADQAOAA8ADwAO"
    "AA4ADQAPABEAEQATABIAEAAQAA8AEQATABUAFQAUABMAEQATABQAFAAXABgAFwAVABUAFQAVABcAGQAZABgAGAAWABYAFwAZABoA"
    "GgAbABkAGAAYABgAGQAbABsAGwAaABgAGAAZABoAHAAdABwAGwAZABgAGQAaABsAHQAcABsAGwAYABoAGwAaABwAHQAbABoAGAAY"
    "ABoAGwAcABsAGwAZABkAGAAYABsAHAAbABoAGAAXABgAGAAZABoAGgAaABgAFgAVABcAFwAYABkAGAAXABUAFQAVABYAFwAYABYA"
    "FAATABIAEgAUABUAFQAVABIAEAAQABAAEQASABIAEgAQAA8ADwAOAA8ADwAQAA8ADQAMAAsACgAMAA4ADgANAAsACQAJAAgACQAK"
    "AAoACQAIAAYABgAGAAYACAAJAAcABgADAAIAAgADAAQABAAFAAIAAAABAAAAAAABAAIAAgAAAAAA///+////AAAAAAAA///+//v/"
    "+//8//3//v/+//3/+f/5//n/+f/7//z/+//6//j/9//3//f/+P/5//r/+P/3//X/9P/1//b/9//3//b/9P/z//P/8//0//X/9v/1"
    "//L/8f/x//D/8v/0//T/8v/x/+//7v/v//D/8f/y//D/7//u/+z/7f/v/+//8P/w/+7/7P/r/+v/7f/u/+7/7v/t/+v/6f/p/+z/"
    "7f/t/+3/6//q/+n/6P/q/+v/7P/s/+v/6f/p/+j/6P/r/+v/6v/q/+j/5//n/+j/6v/r/+r/6f/o/+b/5f/n/+n/6f/q/+j/5v/l"
    "/+b/5v/o/+n/6P/o/+b/5P/l/+X/5v/o/+j/6P/m/+X/5f/k/+X/5//n/+b/5f/l/+T/5P/l/+f/5//m/+T/4v/i/+T/5f/l/+b/"
    "5v/l/+T/4v/i/+T/5f/l/+X/5P/i/+L/4v/k/+X/5f/l/+X/4//h/+L/4//j/+T/5f/j/+L/4v/i/+L/5P/l/+X/4//h/+H/4v/i"
    "/+P/5f/k/+T/4v/h/+H/4f/i/+P/4//j/+H/4f/g/+D/4//j/+T/5P/g/+H/4P/g/+T/4//k/+T/4P/g/+D/4f/i/+P/4//j/+L/"
    "4P/g/+L/4v/k/+X/5P/i/+H/4P/h/+L/4//l/+T/4v/i/+H/4f/j/+X/5f/j/+L/4v/g/+L/4//l/+X/5f/l/+L/4v/i/+P/5v/l"
    "/+X/5f/j/+T/5P/k/+b/5//o/+X/5f/l/+P/5f/o/+j/6P/n/+f/5v/l/+f/6f/q/+n/6f/p/+f/6f/p/+v/7P/r/+z/6v/p/+v/"
    "6//s/+7/7v/u/+3/7f/s/+3/7//x//D/8P/w/+7/7v/w//H/8//z//P/8f/x//H/8v/0//T/9f/2//T/8//1//X/9v/3//r/+f/3"
    "//j/9//3//n/+v/8//z/+v/6//r/+//9//////////7//f/+//7/AAAAAAAAAgAAAAAAAAAAAAIAAwADAAUABAADAAMAAwAGAAYA"
    "BwAJAAgABwAGAAcACQAJAAsADAALAAsACwALAA0ADgAPAA8ADwAOAA0ADwARABIAEwASABIAEgASABIAEwAUABUAFwAXABYAFQAV"
    "ABYAGAAXABkAGQAXABgAGAAYABsAHAAcAB0AGwAaABsAGwAdAB4AHgAeAB4AHAAdAB4AHgAgACEAIQAgAB8AHwAfACAAIQAiACIA"
    "IQAgACAAIQAiACMAIwAiACMAIgAgACEAIwAjACMAIwAjACIAIQAhACEAIwAjACIAJAAiACAAIQAhACIAIgAhACEAIAAgACAAHwAh"
    "ACEAIQAfAB0AHgAeAB0AHgAeAB8AHgAcABwAGwAaABwAGwAbABsAGQAYABcAFwAYABgAGAAXABUAFAAUABQAEwASABIAEwARAA8A"
    "DwAQAA8AEAAPAA4ADQALAAoACgAKAAoACgAJAAgABwAGAAYABQAFAAMAAwADAAEAAAAAAAAAAAAAAAAA///9//3//P/8//v/+//8"
    "//n/9//3//f/9//2//X/9f/0//L/8f/x//H/8f/w//D/7//t/+3/7P/r/+z/6//q/+v/6P/o/+j/5//n/+b/5v/l/+T/5P/j/+L/"
    "4v/i/+L/4P/g/9//3v/f/9//3v/d/97/3f/b/9r/2v/a/9r/2v/a/9n/2P/Y/9f/1//Y/9f/1//W/9X/1v/W/9b/1f/V/9b/1P/U"
    "/9T/0//U/9P/1P/U/9T/1P/T/9P/0//U/9T/1P/U/9P/0//T/9P/1P/U/9T/1P/T/9X/0//T/9b/1P/W/9b/1P/W/9b/1v/X/9b/"
    "1//X/9j/1//X/9r/2f/Z/9v/3P/c/9v/2//c/9v/3P/d/97/3v/e/9//3//g/+H/4v/i/+L/4v/i/+P/5P/l/+b/5f/m/+j/5v/n"
    "/+n/6f/r/+v/6//r/+v/7P/t/+7/7//v//D/8f/w//H/8//z//L/9P/0//T/9v/1//b/9//4//n/+f/5//r/+v/6//v//P/8//3/"
    "/v/9/////v///wAAAAABAAEAAAABAAAAAwACAAIABAACAAMABQAEAAYABgAFAAYABwAHAAcACAAIAAgACQAJAAkACQAKAAoACgAM"
    "AAsADAAMAAwADAAMAAwADQAMAA0ADgANAA0ADgAPAA4ADgAPAA8ADgAOAA8ADwAPAA8AEAAQABAAEAAQAA8ADwAPABAAEQAQABEA"
    "EAAPABAAEQASABAAEAARABAAEAARABAAEQARABEAEAAQABEAEQASABEAEQARABEAEQAQABEAEgAQABEAEQAQABIAEAARABEAEAAR"
    "ABEAEQAQABAAEQAQABAAEAARABAAEAAQABAAEAARABEAEQARABAAEQAQABEAEQARABAAEQASAA8AEQASABEAEgARABIAEgARABIA"
    "EgASABEAEgATABIAEgATABMAEwASABQAFAATABQAEwAUABUAFQAVABUAFQAVABUAFgAWABgAGAAXABgAFwAYABgAGAAZABoAGgAZ"
    "ABoAGwAbABwAHAAbAB0AHAAeAB4AHQAeAB4AHgAfAB8AHwAhACEAIQAhACEAIwAiACIAIwAjACQAJAAlACcAJQAmACYAJgAnACcA"
    "JwAnACgAKAApACoAKgApACoAKgAqACsALAArACwALAAtAC0ALAAtAC0ALAAtAC8ALgAuAC4ALwAuAC4ALwAuAC4ALgAuADAALwAv"
    "ADAALwAwADAALgAvAC4ALgAvAC0ALgAuAC4ALQAtAC0ALQAsAC0ALAArACsAKwAqACkAKQAqACgAKQAoACcAJwAmACYAJAAjACMA"
    "JAAjACEAIQAhACAAHgAeAB0AHQAcABsAGgAZABkAGAAWABUAFAATABIAEgASABAADwAPAA0ADAALAAoACQAHAAYABgAFAAQAAwAC"
    "AAAAAAAAAP7//f/7//r/+v/5//f/9//2//X/8//x//D/8P/v/+3/7P/r/+n/6P/o/+b/5f/k/+L/4v/g/9//3//c/9z/2//Z/9n/"
    "1//W/9X/1P/T/9H/0P/Q/83/zv/N/8v/y//K/8j/yP/H/8b/xf/E/8P/w//C/8D/wf++/73/vf+8/7z/u/+6/7r/uf+5/7j/t/+3"
    "/7b/tf+1/7T/tP+0/7T/tP+y/7P/sv+x/7H/sf+x/7H/sP+x/7D/sP+x/7D/sP+w/7H/sf+w/7D/sf+v/7D/sv+x/7H/sv+x/7H/"
    "s/+0/7T/tP+0/7T/tv+2/7b/t/+3/7j/uf+5/7r/uv+8/73/vf++/77/v//B/8D/wv/D/8T/xf/G/8f/yP/J/8r/yv/M/83/zv/Q"
    "/9D/0f/T/9T/1v/X/9j/2f/Z/9r/3P/d/9//4f/i/+P/5P/l/+f/6P/q/+n/7P/u/+7/8P/x//L/9f/1//b/+P/4//v//f/9////"
    "AAAAAAEAAgADAAUABgAHAAoACgALAA0ADgAPABAAEQAUABMAFAAXABcAGAAaABsAHAAdAB4AHwAfACEAIgAjACQAJQAnACYAJwAp"
    "ACkAKwAsACsALgAtAC0AMAAwADAAMQAxADMAMwA0ADQANAA1ADYANwA2ADgAOQA3ADgAOQA5ADoAOQA5ADkAOgA7ADoAPAA8ADoA"
    "OwA8ADoAOgA7ADwAOgA8ADwAOwA7ADwAPAA5ADoAOwA5ADkAOgA4ADkAOQA4ADkAOQA4ADcANgA2ADYANQA1ADUAMwAzADQAMgAz"
    "ADIAMQAwADAAMAAuAC4ALgAsACwAKwAqACsAKQApACgAJwAnACYAJQAkACMAJAAiACEAIQAgACEAHgAdAB4AHQAcABsAGgAaABgA"
    "GAAXABYAFwAWABQAFAATABIAEgARABAADwAPAA4ADQANAAwACwAMAAoACQAJAAcABwAHAAYABQAGAAYABAADAAMAAgACAAIAAQAB"
    "AAAAAAAAAAAA//8AAP////////7//v/9//z//f/9//z//f/8//r//P/7//v/+//6//v/+v/6//v/+v/6//r/+//6//n/+v/6//r/"
    "+v/6//r/+v/7//r/+//7//r/+v/6//r/+//8//v//P/8//z//f/9//z//P/8//3//v/9//7////+////////////AAAAAAAAAAAA"
    "AAAAAQAAAAEAAwABAAEAAwACAAMABAADAAMABAAEAAQABQAEAAUABgAGAAcABwAGAAcABwAHAAgACAAJAAgACAAJAAgACQAJAAgA"
    "CgAJAAkACgAJAAkACQALAAoACgALAAoACwAMAAoACwAJAAoACwAJAAoACQAKAAoACQAKAAkACQAKAAgACQAHAAcACQAGAAgABwAG"
    "AAcABQAGAAYAAwAFAAQAAwADAAMAAgABAAEAAAAAAAAAAAAAAAAA///+//7//f/8//z/+//6//r/+f/5//j/9//3//f/9v/1//T/"
    "8//z//L/8P/x//D/8P/v/+z/7f/s/+r/6//p/+n/6P/n/+f/5f/l/+X/5P/k/+L/4v/h/+D/4P/f/97/3v/d/9z/3P/b/9v/2v/a"
    "/9n/2P/X/9f/1v/W/9X/1f/V/9T/0//T/9L/0v/R/9H/0v/Q/9D/0P/P/87/zv/P/83/zf/N/83/z//N/83/zv/M/83/zf/L/83/"
    "zP/N/87/zf/M/83/zv/N/83/zv/N/87/zv/P/9D/z//Q/9D/0P/Q/9H/0v/S/9P/0//T/9T/1f/V/9f/1v/X/9n/2f/Z/9v/2//b"
    "/93/3v/d/9//4P/g/+L/4v/k/+T/5f/n/+j/6P/p/+r/6//s/+3/7v/v//D/8f/y//T/9P/2//f/+P/5//r/+v/8//3//f8AAAAA"
    "AQADAAMABAAGAAYABwAIAAkADAALAAwADgAPABEAEgASABMAFQAWABYAGAAaABkAGwAdABwAHQAfAB8AIAAiACIAJAAlACQAJgAn"
    "ACcAKAApACoAKgArACwALQAuAC8ALgAvADAAMAAwADEAMwAzADIAMwA0ADUANQA0ADUANgA2ADUANwA2ADYANwA3ADgANwA3ADgA"
    "NgA4ADgANgA4ADgANwA4ADcANwA4ADYANgA3ADYANgA2ADYANQA1ADUANAA0ADQAMwAyADIAMgAxADAAMAAwADAALgAuAC0AKwAs"
    "ACsAKgAqACoAKQApACcAJgAmACUAJQAkACQAIgAiACEAIAAhAB4AHgAeABsAGwAbABkAGAAYABcAFgAWABQAEwATABMAEgARAA8A"
    "DwAOAAwADAALAAoACgAJAAgABwAGAAYABgAEAAMAAwABAAEAAAAAAAAA///9//7//f/8//z/+v/6//v/9//3//f/9v/2//X/9P/0"
    "//P/8v/x//H/8f/v/+//7v/t/+3/7f/s/+v/6//r/+r/6f/o/+j/6P/n/+f/5v/l/+X/5v/k/+X/5P/j/+P/4v/i/+L/4v/i/+H/"
    "4f/h/9//4P/g/9//3//e/9//3//d/9//3v/d/97/3f/d/93/3f/e/93/3v/e/97/3f/e/9//3f/e/97/3v/f/97/3v/f/9//4P/f"
    "/+D/4P/f/9//4P/g/+D/4v/i/+L/4//j/+T/5f/l/+X/5f/m/+b/5//o/+j/6f/p/+j/6//r/+v/7P/t/+7/7v/v/+//7//x//H/"
    "8v/z//T/9f/1//b/9//3//j/+v/6//r//P/8//z//f///wAAAAAAAAAAAQACAAIAAwAEAAQABgAGAAYACAAIAAkACQALAAwACwAN"
    "AAwADAAOAA4ADwAQABEAEQARABMAEQASABQAEwAUABQAFAAVABQAFQAWABUAFgAWABYAFgAVABYAFwAVABYAFgAVABUAFQAUABQA"
    "FAAUABQAEwATABMAEgARABEAEQAPABAAEAAOAA4ADgAOAA0ADAALAAsACQAJAAgABwAIAAYABQAFAAQAAwACAAIAAAAAAAAA///+"
    "//7//P/7//v/+v/5//j/9//2//T/9P/0//L/8f/x//H/8P/u/+7/7f/s/+z/6v/p/+r/6f/o/+f/5//n/+b/5v/l/+T/5P/k/+P/"
    "4v/j/+P/4v/i/+L/4v/h/+H/4f/h/+H/4f/j/+L/4v/i/+H/4//k/+L/5P/k/+T/5v/l/+b/5//n/+j/6P/p/+r/6v/s/+z/7f/t"
    "/+//8P/x//P/8//z//X/9f/3//j/+v/7//z//P/+/wAAAAAAAAIAAgAEAAUABgAIAAkACwANAAwADgAQABAAEgATABQAFgAWABgA"
    "GgAZABsAHQAdAB4AHwAhACMAIwAjACUAJQAmACcAKAAoACkAKgArACsALAAtAC0ALgAtAC4ALwAvAC8AMAAwADAAMAAwADEAMAAw"
    "ADAALwAvADAALwAuAC8ALQAtAC4ALAAsACwAKwAqACkAKAAoACcAJgAkACQAIwAiACIAIAAfAB4AHQAcABwAGgAYABgAFwAUABMA"
    "EgARABAADgANAAwACwAJAAgABwAFAAQAAwAAAAAAAAD///7//P/7//v/+f/3//X/9P/z//H/8f/w/+//7v/t/+z/6v/q/+r/5//m"
    "/+b/5f/k/+T/5P/j/+H/4f/g/+D/4P/f/9//3v/e/97/3v/d/93/3f/c/9z/3f/d/93/3f/d/93/3f/e/97/3//e/9//4P/g/+H/"
    "4v/h/+P/5P/k/+b/5v/m/+f/6P/o/+r/6v/s/+3/7v/u/+//8f/y//L/9P/0//b/9//3//n/+v/7//3//f/+////AAAAAAEAAgAD"
    "AAQABQAGAAcACAAJAAoACwAMAAwADQAPABAAEAAQABEAEQASABMAEwAUABUAFgAXABcAFwAXABgAGAAXABkAGQAZABkAGQAZABoA"
    "GgAZABkAGQAYABkAGAAYABgAFwAZABcAFQAWABUAFQAVABMAFAATABEAEQARABAADwAOAA4ADAAMAAsACgAJAAgABwAGAAYABQAE"
    "AAIAAgABAAAAAAD//////v/8//z/+//6//j/+P/3//b/9f/0//P/8//x//H/8f/v/+7/7f/s/+z/6//r/+r/6v/p/+n/6P/n/+b/"
    "5v/l/+X/5P/l/+X/4//k/+T/4//j/+P/4//j/+L/4//j/+P/5P/j/+P/5P/j/+X/5f/k/+b/5v/m/+f/5v/o/+n/6P/q/+r/6v/s"
    "/+z/7v/u/+7/8P/w//H/8f/y//P/9P/1//b/9v/4//n/+f/7//z//P/9//7///8AAAAAAAABAAIAAwAFAAUABgAHAAcACAAJAAkA"
    "CwALAAwADQANAA4ADwAPABEAEQAQABIAEgATABMAFAAVABUAFQAWABUAFQAWABYAFgAXABcAFwAXABcAGAAXABcAFwAXABcAFwAX"
    "ABcAFgAWABYAFQAUABQAFAATABMAEwASABIAEQAQABAADwAOAA8ADQANAAwACwALAAoACQAJAAcABwAGAAQABQAEAAIAAgABAAIA"
    "AAAAAAAA//////7//f/8//v/+//7//n/+f/4//j/9//2//b/9v/1//T/9P/z//L/8v/y//H/8f/x//D/8P/w//D/8P/v/+//7//v"
    "/+//7//v/+//7//v//D/8P/w//D/8f/w//H/8f/x//H/8v/y//L/9P/0//T/9f/1//b/9//3//j/+f/5//r/+v/7//3//f/+//7/"
    "//8AAAAAAAAAAAEAAgADAAQABQAFAAYACAAIAAgACgAKAAsADQAMAA0ADwAPAA8AEQARABEAEwAUABQAFAAVABUAFgAWABcAFwAX"
    "ABgAGAAYABoAGgAaABsAGgAaABoAGwAbABoAGwAbABsAHAAcABsAGwAbABoAGgAaABoAGQAZABkAGAAYABgAFwAWABUAFQAVABQA"
    "EwATABIAEQAQABAADwAOAA4ADAALAAsACgAJAAgABwAGAAUABQADAAIAAgAAAAAAAAD//////f/8//z/+//5//j/9//3//X/9f/1"
    "//P/8v/y//D/8P/v/+//7f/s/+v/6//q/+r/6f/o/+n/5//m/+b/5f/l/+X/5P/k/+T/4//j/+L/4v/i/+L/4v/i/+L/4v/h/+L/"
    "4v/h/+L/4v/i/+L/4v/j/+L/4//k/+T/5f/l/+X/5v/m/+b/6P/o/+j/6v/q/+v/6//s/+3/7v/u/+//8P/w//L/8//z//T/9f/2"
    "//f/+P/5//n/+//7//z//v/+////AAAAAAEAAgADAAMABQAFAAYABwAIAAkACgALAAwADAANAA4ADgAPABAAEQASABIAEwATABMA"
    "FAAVABYAFQAWABcAFwAYABgAGAAaABkAGQAaABkAGQAaABoAGgAaABoAGgAaABoAGQAaABoAGgAZABkAGQAZABgAGAAYABgAFwAW"
    "ABYAFgAVABQAFAATABIAEgASABEAEQAQAA8ADgAOAA0ADAAMAAsACgAJAAkACAAHAAYABgAFAAMAAwADAAEAAQAAAAAAAAD/////"
    "/f/9//3//P/7//v/+f/5//n/9//3//b/9v/1//T/9P/0//P/8v/y//L/8f/w//D/8P/v/+//7//v/+//7v/u/+7/7v/t/+7/7f/t"
    "/+3/7f/t/+3/7f/t/+3/7f/t/+3/7f/u/+7/7v/u/+//7v/v/+//8P/x//D/8f/x//H/8v/z//P/8//0//T/9f/1//X/9v/3//f/"
    "+P/4//n/+f/6//v/+v/7//z//P/9/////v///wAAAAAAAAAAAQABAAIAAQACAAMABAAFAAUABgAGAAYABwAHAAcACAAIAAkACgAJ"
    "AAoACgAKAAsACwALAAwADAAMAA0ADQANAA0ADgANAA0ADgAOAA4ADgAOAA8ADgAPAA8ADwAPAA8ADwAPAA8ADwAPAA8ADgAPAA4A"
    "DgAOAA4ADQANAA0ADgAMAAwADQAMAAsACwALAAsACgAKAAoACQAJAAkACQAIAAgACAAIAAcABgAGAAYABQAFAAUABQAEAAQABAAD"
    "AAIAAgACAAEAAQABAAEAAAAAAAAAAAAAAP//AAD////////+//7//v/+//3//f/8//z//P/8//z//P/7//v/+//7//v/+v/7//r/"
    "+v/6//r/+v/6//r/+v/6//n/+v/6//n/+f/5//n/+v/5//n/+f/5//n/+f/5//n/+f/5//n/+f/5//n/+v/6//r/+v/6//r/+v/6"
    "//r/+v/6//v/+v/6//v/+//7//v/+//7//v//P/8//z//P/8//z//P/8//3//f/9//3//f/9//3//f/+//7//v/+//3//v/+//7/"
    "///////////+//////////////8AAP////8AAP//AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEA"
    "AQAAAAAAAQAAAAAAAQABAAEAAQABAAEAAQABAAEAAQABAAIAAQABAAIAAgACAAIAAgACAAIAAgACAAIAAgACAAMAAwACAAIAAgAD"
    "AAMAAwADAAIAAwADAAMABAADAAMABAADAAQAAwADAAQAAwADAAQABAAEAAMABAADAAMABAADAAMABAADAAQABAAEAAQABAAEAAMA"
    "BAAEAAMABAAEAAQABAAEAAQABAADAAMAAwADAAMAAwADAAMAAwADAAMAAgACAAIAAgACAAIAAgACAAIAAgABAAEAAgABAAEAAQAB"
    "AAEAAQABAAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA/////////////////v////7////+//7//v/9//7//v/9//7/"
    "/f/9//3//f/9//3//P/9//z//P/8//z//P/8//z//P/8//z/+//8//v/+//7//v/+//7//v/+//7//v/+//7//v/+v/7//v/+//7"
    "//v/+//7//v/+//7//v/+//7//v/+//7//v/+//8//v//P/7//v//P/8//v//P/7//z//P/8//z//P/8//z//P/9//z//P/9//3/"
    "/f/9//3//f/9//7//v/+//7//v/+//7//v/+//7//v//////////////////////AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAEAAQABAAEAAQABAAEAAQABAAIAAQABAAIAAgACAAIAAgACAAIAAgACAAIAAgACAAIAAgADAAMA"
    "AwADAAIAAwADAAIAAwADAAMAAwADAAMAAwADAAMAAwADAAMAAwADAAMAAwADAAMAAwADAAMAAwADAAQAAwADAAMAAwADAAMAAwAD"
    "AAMAAwAEAAMAAwADAAMAAwADAAMAAwADAAMAAwADAAMAAwADAAMAAgADAAMAAgADAAMAAgACAAIAAgACAAIAAgACAAIAAgACAAIA"
    "AgACAAIAAgACAAIAAQACAAIAAQABAAIAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAQABAAAAAQABAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD/////AAAAAP//"
    "AAD//wAA/////wAA//////////////////8AAP////////////////////////////////////////////////7/////////////"
    "////////////////////////////////////////////////////////////AAAAAP//AAD/////AAD/////AAAAAP//AAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQAAAAAAAQAAAAEAAAAAAAEAAAAAAAAAAAAAAAAAAAABAAEAAQABAAEA"
    "AQABAAAAAQABAAEAAAABAAEAAAABAAAAAAABAAAAAAABAAAAAAAAAAAAAAABAAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAA//8AAP////8AAAAAAAAAAP//AAD//////////////////////////////////////////////////////////////v//"
    "//7///////7////+//7////+///////+/////v/+//7//v/+//7//v/+//7///////7//v////7///////7////+///////+////"
    "///+///////+/////////////////////////////////////////////////////////////////wAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEAAQAAAAEA"
    "AQABAAEAAQABAAEAAQABAAEAAQABAAEAAgABAAIAAgABAAIAAQACAAIAAgACAAIAAgACAAIAAgACAAIAAgACAAIAAgACAAIAAgAC"
    "AAIAAgACAAIAAgADAAMAAgADAAMAAgADAAMAAgADAAIAAgADAAMAAwADAAMAAgACAAMAAwADAAMAAwADAAMAAgADAAIAAgADAAIA"
    "AgACAAIAAwACAAIAAgACAAIAAgACAAIAAgACAAIAAgACAAIAAgACAAIAAgACAAIAAgACAAIAAQACAAIAAgACAAEAAgABAAEAAQAB"
    "AAEAAQABAAEAAQABAAEAAQABAAEAAQABAAEAAAABAAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA////////////////////////////////////////////"
    "////////////////////////////////////////////////////////////////////////////////////////////////////"
    "////////////////////////////////////////////////////////////////////////////////////////////////////"
    "/////////////////wAAAAAAAAAAAAD//wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
)


def _build_sounds():
    SOUND_DIR.mkdir(parents=True, exist_ok=True)
    defs = {
        "click": lambda: _mix([(0, _bloop(520, 760, 0.17, decay=24))]),
        "toggle": lambda: _mix([(0, _bloop(620, 900, 0.15, decay=26))]),
        "select": lambda: _mix([(0, _bloop(700, 1000, 0.16, decay=24)), (0.045, _bloop(900, 1200, 0.14, decay=28, vol=0.6))]),
        # play / success / error use the exact same creamy click sound as the buttons
        "play": lambda: _mix([(0, _bloop(520, 760, 0.17, decay=24))]),
        "success": lambda: _mix([(0, _bloop(520, 760, 0.17, decay=24))]),
        "error": lambda: _mix([(0, _bloop(520, 760, 0.17, decay=24))]),
    }
    try:
        pop = base64.b64decode("".join(_POP_B64))
    except Exception:
        pop = None
    for name, make in defs.items():
        p = SOUND_DIR / f"{name}.wav"
        if not p.exists():
            if pop:
                p.write_bytes(pop)
            else:
                _finish(make(), p)


# ---------------------------------------------------------------------------
# Custom click sound: pick any wav/mp3/ogg/flac and it replaces the creamy
# bloops for button clicks, checkboxes and dropdown picks. Stored in your home
# folder (not the project folder), so it never ends up in a GitHub upload.
# ---------------------------------------------------------------------------
CUSTOM_DIR = APP_DIR / "custom_sounds"
CUSTOM_FILE = CUSTOM_DIR / "click.wav"
CUSTOM_NAMES = ("click", "toggle", "select")


def _convert(src, dest, max_seconds=3.0):
    """Convert wav/mp3/ogg/flac `src` to a plain 16-bit WAV at `dest` (trimmed). Raises RuntimeError."""
    src, dest = Path(src), Path(dest)
    if not src.is_file():
        raise RuntimeError("That file doesn't exist.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.stem + ".tmp.wav")
    try:
        import miniaudio
    except ImportError:
        miniaudio = None
    try:
        if miniaudio is not None:
            dec = miniaudio.decode_file(str(src), output_format=miniaudio.SampleFormat.SIGNED16)
            samples = dec.samples[: int(max_seconds * dec.sample_rate * dec.nchannels)]
            with wave.open(str(tmp), "wb") as w:
                w.setnchannels(dec.nchannels)
                w.setsampwidth(2)
                w.setframerate(dec.sample_rate)
                w.writeframes(samples.tobytes())
        elif src.suffix.lower() == ".wav":
            # re-write as plain 16-bit (8 / 24 / 32-bit files don't play or pitch-shift properly as they are), trimmed
            with wave.open(str(src), "rb") as w:
                ch, sw, sr = w.getnchannels(), w.getsampwidth(), w.getframerate()
                raw = w.readframes(min(w.getnframes(), int(max_seconds * sr)))
            if sw == 2:
                pcm = raw
            else:
                out = array("h")
                if sw == 1:
                    out.extend((b - 128) << 8 for b in raw)
                elif sw == 3:
                    for i in range(0, len(raw) - 2, 3):
                        out.append(int.from_bytes(raw[i + 1:i + 3], "little", signed=True))
                elif sw == 4:
                    for i in range(0, len(raw) - 3, 4):
                        out.append(int.from_bytes(raw[i + 2:i + 4], "little", signed=True))
                else:
                    raise RuntimeError("Unsupported WAV format.")
                pcm = out.tobytes()
            with wave.open(str(tmp), "wb") as w:
                w.setnchannels(ch)
                w.setsampwidth(2)
                w.setframerate(sr)
                w.writeframes(pcm)
        else:
            raise RuntimeError("To use mp3/ogg files, run:  pip install miniaudio   (then try again). "
                               "Or pick a .wav file.")
        tmp.replace(dest)
    except RuntimeError:
        tmp.unlink(missing_ok=True)
        raise
    except Exception as e:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"Couldn't read that sound file ({type(e).__name__}).") from e
    return dest


def import_click_sound(src, max_seconds=3.0):
    """Convert a sound file to a plain WAV and use it for UI clicks. Raises RuntimeError on failure."""
    return _convert(src, CUSTOM_FILE, max_seconds)


def reset_click_sound():
    CUSTOM_FILE.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Sound library: the creamy default + any sounds you add. Each event (click, toggle,
# select, play, success, error) can use a different one.
# A sound id is "default" or "lib:<file name>".
# ---------------------------------------------------------------------------
LIB_DIR = CUSTOM_DIR / "library"
EVENTS = (("click", "Button click"), ("toggle", "Checkbox"), ("select", "Dropdown pick"),
          ("play", "Press Play"), ("success", "Success"), ("error", "Error"))


def library_sounds():
    return sorted(p.name for p in LIB_DIR.glob("*.wav")) if LIB_DIR.is_dir() else []


def sound_choices():
    """[(id, label)] for the dropdowns."""
    return [("default", "Creamy (default)")] + [(f"lib:{n}", Path(n).stem) for n in library_sounds()]


def import_sound(src, max_seconds=3.0):
    """Add a sound file to the library. Returns its id ('lib:<name>')."""
    src = Path(src)
    name = "".join(c for c in src.stem if c not in '\\/:*?"<>|').strip()[:60] or "sound"
    dest = LIB_DIR / f"{name}.wav"
    n = 2
    while dest.exists():
        dest = LIB_DIR / f"{name} {n}.wav"
        n += 1
    _convert(src, dest, max_seconds)
    return f"lib:{dest.name}"


def remove_sound(sound_id):
    if sound_id.startswith("lib:"):
        (LIB_DIR / Path(sound_id[4:]).name).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Pitch variation: each click plays a slightly higher/lower copy of the sound,
# so repeated clicks don't sound identical.
# ---------------------------------------------------------------------------
VAR_DIR = APP_DIR / "variants_v4"
VARY_EVENTS = ("click", "toggle", "select")
SEMITONES = (-4, -2, -1, 0, 1, 2, 4)


def _shift(src, dst, ratio):
    """Write a copy of WAV `src` played `ratio` times faster (higher pitch if > 1)."""
    with wave.open(str(src), "rb") as w:
        ch, sw, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if sw != 2:
        raise ValueError("only 16-bit wav")
    data = array("h")
    data.frombytes(raw)
    out = array("h")
    frames = len(data) // ch
    new_frames = max(1, int(frames / ratio))
    for i in range(new_frames):
        pos = i * ratio
        j = int(pos)
        frac = pos - j
        j2 = min(j + 1, frames - 1)
        for c in range(ch):
            a, b = data[j * ch + c], data[j2 * ch + c]
            out.append(int(a + (b - a) * frac))
    with wave.open(str(dst), "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(out.tobytes())


class SoundPlayer:
    def __init__(self):
        self.enabled = True
        self.ok = True
        self.assign = {}  # event -> sound id (missing = default)
        self.vary = True
        self._building = set()
        self._last = None
        try:
            _build_sounds()
        except Exception:
            import traceback
            self.ok = False
            try:
                APP_DIR.mkdir(parents=True, exist_ok=True)
                (APP_DIR / "sound_error.log").write_text("could not create the sound files:\n" + traceback.format_exc(), encoding="utf-8")
            except Exception:
                pass
        self.cmd = None
        if sys.platform not in ("win32", "darwin"):
            for c in ("paplay", "pw-play", "aplay", "ffplay"):
                if shutil.which(c):
                    self.cmd = [c, "-nodisp", "-autoexit", "-loglevel", "quiet"] if c == "ffplay" else [c]
                    break

    def resolve(self, name, sound_id=None):
        """File to play for an event (or for a given sound id); None = silent / missing."""
        sid = sound_id or getattr(self, "assign", {}).get(name)
        try:
            if sid and sid.startswith("lib:"):
                p = LIB_DIR / Path(sid[4:]).name
                if p.exists():
                    return str(p)
        except Exception:
            pass
        if name in ("play", "success", "error") and sid in (None, "default"):
            name = "click"  # these sound just like a button click unless you pick something else for them
        return str(SOUND_DIR / f"{name}.wav")

    def preview(self, sound_id, event="click"):
        if self.enabled and self.ok:
            path = self.resolve(event, sound_id or "default")
            if path:
                self._play_file(path)

    def play(self, name):
        if not (self.enabled and self.ok):
            return
        path = self.resolve(name)
        if path and getattr(self, "vary", False) and name in VARY_EVENTS:
            path = self._variant(path)
        if path:
            self._play_file(path)

    def _variant(self, path):
        """A random pitch variant of `path` (built in the background the first time)."""
        cache = self.__dict__.setdefault("_vcache", {})
        ready = cache.get(path)
        if ready:  # already checked: no disk access on the click
            pick = random.choice([f for f in ready if f != self._last] or ready)
            self._last = pick
            return str(pick)
        try:
            key = hashlib.sha1(f"{path}|{Path(path).stat().st_mtime_ns}".encode()).hexdigest()[:12]
        except OSError:
            return path
        files = [VAR_DIR / f"{key}_{i}.wav" for i in range(len(SEMITONES))]
        if all(f.exists() for f in files):
            cache[path] = files
            pick = random.choice([f for f in files if f != self._last] or files)
            self._last = pick
            return str(pick)
        if key not in self._building:
            self._building.add(key)

            def build():
                try:
                    VAR_DIR.mkdir(parents=True, exist_ok=True)
                    for f, semi in zip(files, SEMITONES):
                        if not f.exists():
                            tmp = f.with_name(f.stem + ".tmp.wav")
                            _shift(path, tmp, 2 ** (semi / 12))
                            tmp.replace(f)
                except Exception:
                    pass
                finally:
                    self._building.discard(key)
            threading.Thread(target=build, daemon=True).start()
        return path

    def _play_file(self, path):
        """Hand the file to a background thread: starting a sound (disk + audio device) must never stall the window."""
        now = time.monotonic()
        if now - getattr(self, "_last_play", 0) < 0.04:  # rapid clicking: skip the extra sounds instead of piling them up
            return
        self._last_play = now
        q = getattr(self, "_q", None)
        if not hasattr(self, "_mem"):
            self._mem = {}
        if q is None:
            import queue
            import threading
            q = self._q = queue.Queue()
            threading.Thread(target=self._worker, args=(q,), daemon=True).start()
        n = getattr(self, "_nplays", 0) + 1
        self._nplays = n
        if n <= 4:   # a short diagnostic note for the first few sounds (sound_error.log in the .simple_mc_launcher folder)
            self._log(f"v4 play #{n}: {path} exists={Path(path).exists()} platform={sys.platform} enabled={self.enabled} ok={self.ok}")
        if self._qt_play(path):
            return
        q.put(path)

    def _log(self, msg):
        try:  # leave a note so a silent launcher can be diagnosed
            APP_DIR.mkdir(parents=True, exist_ok=True)
            with open(APP_DIR / "sound_error.log", "a", encoding="utf-8") as lf:
                lf.write(msg + "\n")
        except Exception:
            pass

    def _qt_play(self, path):
        """Qt's own sound player (what the app already uses for its window): quick, never blocks, works where winsound stays silent."""
        if sys.platform == "win32" or getattr(self, "_qt_bad", False):
            return False   # on Windows the plain winsound player is the one that works (Qt stayed silent on some PCs)
        try:
            fx = self._fx.get(path) if hasattr(self, "_fx") else None
            if fx is None:
                from PySide6.QtCore import QUrl
                from PySide6.QtMultimedia import QSoundEffect
                if not hasattr(self, "_fx"):
                    self._fx = {}
                fx = QSoundEffect()
                fx.setSource(QUrl.fromLocalFile(str(path)))
                fx.setVolume(0.9)
                self._fx[path] = fx
            fx.play()
            return True
        except Exception:
            import traceback
            self._qt_bad = True
            self._log("Qt sound failed, using winsound:\n" + traceback.format_exc())
            return False

    def _worker(self, q):
        while True:
            path = q.get()
            while not q.empty():  # clicked faster than we can play: only the newest one matters
                path = q.get_nowait()
            try:
                if sys.platform == "win32":
                    import winsound
                    # started from this sound-only thread, so the window never waits for it
                    t0 = time.monotonic()
                    winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)   # returns at once; a new click cuts the old one off
                    self._wn = getattr(self, "_wn", 0) + 1
                    if self._wn <= 4:   # how long Windows took (a real 0.3 s sound takes about 0.3 s)
                        self._log(f"v5 winsound #{self._wn}: {time.monotonic() - t0:.3f}s for {path}")
                elif sys.platform == "darwin":
                    subprocess.Popen(["afplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                elif self.cmd:
                    subprocess.Popen(self.cmd + [path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                try:  # leave a note so a silent launcher can be diagnosed
                    import traceback
                    with open(APP_DIR / "sound_error.log", "a", encoding="utf-8") as lf:
                        lf.write(f"{path}\n{traceback.format_exc()}\n")
                except Exception:
                    pass
