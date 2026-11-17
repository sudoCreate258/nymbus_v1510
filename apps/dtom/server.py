"""Nymbus twin capture - local pairing server (stdlib only).

PC page : http://localhost:8765            (this computer only)
Phone   : https://<this-PC-LAN-IP>:8443/phone   (same Wi-Fi; enter the 6-digit code)

The phone runs pose estimation in its own browser and sends ONLY joint positions
(33 points x 4 numbers, ~10 times a second). No video or images leave the phone.
Nothing is written to disk except a self-signed certificate in ./certs/.
"""
import json, os, secrets, socket, ssl, subprocess, sys, threading, time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

HERE = Path(__file__).resolve().parent
CERTS = HERE / "certs"
CODE = f"{secrets.randbelow(900000) + 100000}"
STATE = {"seq": 0}
PHONES = {}          # phone IP -> {"cam": "C", "last": {...}}; up to 6 phones (C..H)
LETTERS = "CDEFGH"
LOCK = threading.Condition()
MAX_BODY = 64 * 1024


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # no packet is sent; picks the LAN interface
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def ensure_cert(ip):
    CERTS.mkdir(exist_ok=True)
    key, crt = CERTS / "phone.key", CERTS / "phone.crt"
    if key.exists() and crt.exists():
        return str(crt), str(key)
    subj = "/CN=nymbus-twin-local"
    san = f"subjectAltName=IP:{ip},IP:127.0.0.1,DNS:localhost"
    local = os.environ.get("LOCALAPPDATA", "")
    candidates = ["openssl",  # Linux/macOS: system openssl
                  os.path.join(local, r"Programs\Git\usr\bin\openssl.exe"),
                  os.path.join(local, r"Programs\Git\mingw64\bin\openssl.exe"),
                  r"C:\Program Files\Git\usr\bin\openssl.exe",
                  r"C:\Program Files\Git\mingw64\bin\openssl.exe"]
    args = ["req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "365", "-subj", subj, "-addext", san]
    for exe in candidates:
        try:
            subprocess.run([exe, *args, "-keyout", str(key), "-out", str(crt)], check=True, capture_output=True)
            print(f"Certificate created with {exe}")
            return str(crt), str(key)
        except (OSError, subprocess.CalledProcessError):
            continue
    # Fallback: official alpine image's openssl writes into ./certs (Docker Desktop must be running)
    try:
        subprocess.run(["docker", "run", "--rm", "-v", f"{CERTS}:/c", "alpine:3.20", "sh", "-c",
                        "apk add --no-cache openssl >/dev/null && openssl " + " ".join(
                            f"'{a}'" for a in args) + " -keyout /c/phone.key -out /c/phone.crt"],
                       check=True, capture_output=True)
        print("Certificate created with Docker (alpine:3.20)")
        return str(crt), str(key)
    except (OSError, subprocess.CalledProcessError) as e:
        detail = getattr(e, "stderr", b"") or b""
        sys.exit("Could not create a certificate. Start Docker Desktop and run again.\n"
                 + detail.decode(errors="replace")[-400:])


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(HERE), **kw)

    def log_message(self, fmt, *args):
        if "/api/landmarks" not in str(args[0] if args else ""):
            sys.stderr.write("%s - %s\n" % (self.client_address[0], fmt % args))

    def local(self):
        # PC-only endpoints are served only on the PC port (published on 127.0.0.1 only)
        return self.server.server_address[1] == 8765

    def json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > MAX_BODY:
            return None
        try:
            return json.loads(self.rfile.read(n))
        except ValueError:
            return None

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/certs", "/certs/") or path.startswith("/certs/") or path.endswith(".py"):
            return self.send_error(404)
        if path == "/phone":
            self.path = "/phone.html"
            return super().do_GET()
        if path == "/api/info":
            if not self.local():
                return self.send_error(403)
            now = time.time()
            with LOCK:
                phones = [{"cam": p["cam"], "ip": ip, "age": round(now - p["last"]["t"], 1) if p["last"] else None}
                          for ip, p in sorted(PHONES.items(), key=lambda kv: kv[1]["cam"])]
            return self.json(200, {"code": CODE, "phone_url": f"https://{IP}:8443/phone",
                                   "paired": bool(phones), "phones": phones})
        if path == "/api/stream":
            if not self.local():
                return self.send_error(403)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            seen = -1
            try:
                while True:
                    with LOCK:
                        LOCK.wait_for(lambda: STATE["seq"] != seen, timeout=5)
                        seen, now = STATE["seq"], time.time()
                        cams = {p["cam"]: p["last"] for p in PHONES.values() if p["last"] and now - p["last"]["t"] < 2}
                    payload = json.dumps({"phones": cams})
                    self.wfile.write(f"data: {payload}\n\n".encode())
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ssl.SSLError, OSError):
                return
        return super().do_GET()

    def do_POST(self):
        path = self.path.split("?")[0]
        data = self.read_json()
        if data is None or str(data.get("code")) != CODE:
            return self.json(403, {"ok": False, "error": "wrong pairing code"})
        ip = self.client_address[0]
        if path == "/api/pair":
            with LOCK:
                if ip not in PHONES:
                    free = [c for c in LETTERS if c not in {p["cam"] for p in PHONES.values()}]
                    if not free:
                        return self.json(409, {"ok": False, "error": "already 6 phones paired"})
                    PHONES[ip] = {"cam": free[0], "last": None}
                cam = PHONES[ip]["cam"]
            print(f"Phone paired from {ip} as camera {cam}")
            return self.json(200, {"ok": True, "cam": cam})
        if path == "/api/landmarks":
            if ip not in PHONES:
                return self.json(409, {"ok": False, "error": "pair this phone first"})
            world, img = data.get("world"), data.get("img")
            if not (isinstance(world, list) and isinstance(img, list) and len(world) == 33 and len(img) == 33):
                return self.json(400, {"ok": False})
            try:
                world = [[float(v) for v in p[:3]] for p in world]
                img = [[float(v) for v in p[:4]] for p in img]
            except (TypeError, ValueError):
                return self.json(400, {"ok": False})
            with LOCK:
                PHONES[ip]["last"] = {"t": time.time(), "world": world, "img": img,
                                      "facing": str(data.get("facing", ""))[:12]}
                STATE["seq"] += 1
                LOCK.notify_all()
            return self.json(200, {"ok": True})
        return self.send_error(404)


def serve(server):
    server.serve_forever()


if __name__ == "__main__":
    IP = os.environ.get("NYMBUS_LAN_IP") or lan_ip()
    crt, key = ensure_cert(IP)
    pc_bind = "0.0.0.0" if os.environ.get("NYMBUS_IN_DOCKER") else "127.0.0.1"
    pc = ThreadingHTTPServer((pc_bind, 8765), Handler)
    phone = ThreadingHTTPServer(("0.0.0.0", 8443), Handler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(crt, key)
    phone.socket = ctx.wrap_socket(phone.socket, server_side=True)
    for s in (pc, phone):
        threading.Thread(target=serve, args=(s,), daemon=True).start()
    print("\n  PC page    : http://localhost:8765")
    print(f"  Phone page : https://{IP}:8443/phone   (same Wi-Fi)")
    print(f"  Pair code  : {CODE}\n")
    print("  The phone will warn about the certificate (it is self-signed on this PC):")
    print("  tap Advanced -> Proceed. Each phone that pairs becomes the next camera (C, D, E ...).")
    print("  If the firewall asks, allow PRIVATE networks only (Ubuntu: sudo ufw allow from 192.168.0.0/16 to any port 8443).\n")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
