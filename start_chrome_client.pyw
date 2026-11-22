"""Double-click this to open Chrome Client with no console window.
(.pyw files run with pythonw, which doesn't open a terminal.)
If something goes wrong on startup, the error is saved to ~/.simple_mc_launcher/crash.log
and shown in a message box, since there's no terminal to print it in."""
import os
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.chdir(HERE)
sys.path.insert(0, str(HERE))

try:
    import launcher
    launcher.main()
except SystemExit:
    raise
except BaseException:
    text = traceback.format_exc()
    try:
        log = Path.home() / ".simple_mc_launcher" / "crash.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(text, encoding="utf-8")
    except Exception:
        pass
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0, "Chrome Client couldn't start.\n\n" + text[-900:] +
            "\n\n(Saved to .simple_mc_launcher\\crash.log)", "Chrome Client", 0x10)
    except Exception:
        pass
