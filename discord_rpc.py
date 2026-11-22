"""Tiny Discord Rich Presence client (no extra packages): talks to the Discord app running on your PC.

Usage:
    rpc = DiscordRPC()
    rpc.configure("123456789012345678")          # your Discord application ID
    rpc.set(details="Playing 1.21.11", state="Chrome Client", start=time.time(), large_image="logo")
    rpc.set(None)                                  # clear
    rpc.stop()
Everything runs on a background thread; nothing here can block or crash the launcher.
"""
import json
import os
import socket
import struct
import sys
import threading
import time
import uuid


class DiscordRPC:
    def __init__(self):
        self._client_id = ""
        self._want = None          # activity dict, or None = show nothing
        self._sent = "unset"       # what Discord currently has
        self._conn = None
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = False
        self._retry_at = 0.0
        self.connected = False
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    # ---- public ----
    def configure(self, client_id):
        client_id = (client_id or "").strip()
        with self._lock:
            if client_id != self._client_id:
                self._client_id = client_id
                self._drop()
                self._sent = "unset"
                self._retry_at = 0
        self._wake.set()

    def set(self, details=None, state=None, start=None, large_image=None, large_text=None):
        """details=None and state=None clears the presence."""
        if details is None and state is None:
            act = None
        else:
            act = {}
            if details:
                act["details"] = str(details)[:128]
            if state:
                act["state"] = str(state)[:128]
            if start:
                act["timestamps"] = {"start": int(start)}
            if large_image:
                assets = {"large_image": str(large_image)}
                if large_text:
                    assets["large_text"] = str(large_text)[:128]
                act["assets"] = assets
        with self._lock:
            self._want = act
        self._wake.set()

    def stop(self):
        self._stop = True
        self._wake.set()

    # ---- internals ----
    def _drop(self):
        c, self._conn = self._conn, None
        self.connected = False
        if c is not None:
            try:
                c.close()
            except Exception:
                pass

    def _loop(self):
        while not self._stop:
            self._wake.wait(timeout=5)
            self._wake.clear()
            if self._stop:
                break
            try:
                self._tick()
            except Exception:
                self._drop()
                self._sent = "unset"
                self._retry_at = time.time() + 15
        self._drop()

    def _tick(self):
        with self._lock:
            cid, want = self._client_id, self._want
        if not cid:
            self._drop()
            return
        if self._conn is None:
            if time.time() < self._retry_at:
                return
            self._connect(cid)
        if want != self._sent:
            self._send_activity(want)
            self._sent = want

    def _connect(self, cid):
        conn = None
        if sys.platform == "win32":
            for i in range(10):
                try:
                    conn = _PipeConn(open(rf"\\?\pipe\discord-ipc-{i}", "r+b", buffering=0))
                    break
                except OSError:
                    continue
        else:
            bases = [os.environ.get(k) for k in ("XDG_RUNTIME_DIR", "TMPDIR", "TMP", "TEMP")] + ["/tmp"]
            for base in [b for b in bases if b]:
                for sub in ("", "app/com.discordapp.Discord/", "snap.discord/"):
                    for i in range(10):
                        path = os.path.join(base, sub, f"discord-ipc-{i}")
                        if not os.path.exists(path):
                            continue
                        try:
                            s = socket.socket(socket.AF_UNIX)
                            s.settimeout(5)
                            s.connect(path)
                            conn = _SockConn(s)
                            break
                        except OSError:
                            continue
                    if conn:
                        break
                if conn:
                    break
        if conn is None:
            self._retry_at = time.time() + 15   # Discord isn't open: try again later
            return
        self._conn = conn
        conn.send(0, {"v": 1, "client_id": cid})
        op, data = conn.recv()
        if data.get("evt") == "ERROR" or op == 2:
            raise OSError(data.get("data", {}).get("message", "Discord refused the connection"))
        self.connected = True

    def _send_activity(self, act):
        self._conn.send(1, {"cmd": "SET_ACTIVITY", "nonce": str(uuid.uuid4()),
                            "args": {"pid": os.getpid(), "activity": act}})
        self._conn.recv()  # Discord answers every command


class _PipeConn:
    def __init__(self, f):
        self.f = f

    def send(self, op, payload):
        data = json.dumps(payload).encode("utf-8")
        self.f.write(struct.pack("<II", op, len(data)) + data)

    def recv(self):
        head = self.f.read(8)
        if len(head) < 8:
            raise OSError("Discord closed the connection")
        op, n = struct.unpack("<II", head)
        body = self.f.read(n)
        return op, json.loads(body.decode("utf-8") or "{}")

    def close(self):
        self.f.close()


class _SockConn:
    def __init__(self, s):
        self.s = s

    def send(self, op, payload):
        data = json.dumps(payload).encode("utf-8")
        self.s.sendall(struct.pack("<II", op, len(data)) + data)

    def _read(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.s.recv(n - len(buf))
            if not chunk:
                raise OSError("Discord closed the connection")
            buf += chunk
        return buf

    def recv(self):
        op, n = struct.unpack("<II", self._read(8))
        return op, json.loads(self._read(n).decode("utf-8") or "{}")

    def close(self):
        self.s.close()
