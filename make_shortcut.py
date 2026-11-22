"""Creates a 'Chrome Client' shortcut on your Desktop (Windows). Run once:  py make_shortcut.py"""
import subprocess
import sys
from pathlib import Path


def ps_quote(s):
    return "'" + str(s).replace("'", "''") + "'"


def build_script(pythonw, pyw, icon, folder):
    args = '"' + str(pyw) + '"'
    return ("$d=[Environment]::GetFolderPath('Desktop');"
            "$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'Chrome Client.lnk'));"
            f"$s.TargetPath={ps_quote(pythonw)};"
            f"$s.Arguments={ps_quote(args)};"
            f"$s.WorkingDirectory={ps_quote(folder)};"
            f"$s.IconLocation={ps_quote(icon)};"
            "$s.Save()")


def main():
    if sys.platform != "win32":
        print("This shortcut maker is for Windows only.")
        return 1
    here = Path(__file__).resolve().parent
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.exists():
        print(f"Couldn't find pythonw.exe next to {sys.executable}")
        return 1
    script = build_script(pythonw, here / "start_chrome_client.pyw", here / "chrome_client.ico", here)
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], check=True)
    print("Done! 'Chrome Client' is on your Desktop. Double-click it to open the launcher.")
    return 0


if __name__ == "__main__":
    code = main()
    if "--quiet" not in sys.argv:
        input("Press Enter to close...")
    sys.exit(code)
