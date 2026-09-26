# cdp.py — cliente minimo do Chrome DevTools Protocol (websocket em socket cru)
import base64, json, os, socket, struct, sys, time, urllib.request, subprocess

class WS:
    def __init__(self, url):
        assert url.startswith("ws://")
        hostport, path = url[5:].split("/", 1)
        host, port = hostport.split(":")
        self.s = socket.create_connection((host, int(port)))
        key = base64.b64encode(os.urandom(16)).decode()
        req = (f"GET /{path} HTTP/1.1\r\nHost: {hostport}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.s.sendall(req.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.s.recv(4096)
        assert b" 101 " in buf.split(b"\r\n")[0], buf
        self.buf = buf.split(b"\r\n\r\n", 1)[1]
        self.next_id = 0
    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.s.recv(65536)
            if not chunk:
                raise EOFError
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out
    def send(self, text):
        data = text.encode()
        head = bytes([0x81])
        n = len(data)
        if n < 126: head += bytes([0x80 | n])
        elif n < 65536: head += bytes([0x80 | 126]) + struct.pack(">H", n)
        else: head += bytes([0x80 | 127]) + struct.pack(">Q", n)
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        self.s.sendall(head + mask + masked)
    def recv(self):
        while True:
            b0, b1 = self._read(2)
            op = b0 & 0x0f
            n = b1 & 0x7f
            if n == 126: n = struct.unpack(">H", self._read(2))[0]
            elif n == 127: n = struct.unpack(">Q", self._read(8))[0]
            payload = self._read(n)
            if op == 1: return payload.decode()
            if op == 9: self.s.sendall(bytes([0x8a, 0x80]) + os.urandom(4))  # pong
            if op == 8: raise EOFError
    def call(self, method, params=None):
        self.next_id += 1
        mid = self.next_id
        self.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self.recv())
            if msg.get("id") == mid:
                if "error" in msg: raise RuntimeError(msg["error"])
                return msg.get("result", {})

def start_chrome(port):
    p = subprocess.Popen(["google-chrome", "--headless=new", "--disable-gpu", "--no-sandbox",
                          f"--remote-debugging-port={port}", "--window-size=1200,800", "about:blank"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version").read()
            return p
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("chrome nao subiu")

def page_ws(port):
    targets = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/json").read())
    page = [t for t in targets if t["type"] == "page"][0]
    return page["webSocketDebuggerUrl"]
