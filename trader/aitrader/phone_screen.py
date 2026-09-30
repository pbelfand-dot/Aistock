"""
phone_screen.py: the Kestrel screen on your phone, over your own private Tailscale network.

Tailscale (free, on the Mac and the iPhone, same account) links your devices privately and encrypts
everything between them. This serves the same Kestrel screen to your phone:
  - only on the Mac's Tailscale address (100.x.y.z): never on your Wi-Fi or the internet;
  - only with Kestrel's access key (in the link from Setup, then remembered by the phone);
  - only watching and the safety buttons: pause, resume, emergency stop (typed confirmation) and
    Stage 1. Keys and settings are changed on the Mac only.

Add it to the Home Screen (Share -> Add to Home Screen) and it opens like an app.
"""
import contextlib
import hmac
import http.server
import io
import ipaddress
import json
import os
import secrets
import socket
import sys
import threading
import time

from .config import ROOT, data_path

PORT = 8765
TAILNET = ipaddress.ip_network("100.64.0.0/10")        # Tailscale gives every device an address in here
ALLOWED = {"snapshot", "setup-status", "pause", "resume", "kill", "start-stage1", "start-stage2", "phone-test"}
WEB = ROOT / "aitrader" / "web"
SHIM = """<script>
window.kestrelPhone = true;
(function () {                                        // the phone talks to the Mac over Tailscale
  var key = (location.hash.match(/key=([\\w-]+)/) || [])[1];
  try {
    if (key) { localStorage.setItem("kestrel-key", key); history.replaceState(null, "", location.pathname); }
    key = key || localStorage.getItem("kestrel-key") || "";
  } catch (e) {}
  window.webkit = { messageHandlers: { aitrader: { postMessage: function (m) {
    return fetch("/api", { method: "POST", headers: { "Content-Type": "application/json", "X-Kestrel-Key": key },
                           body: JSON.stringify(m) }).then(function (r) { return r.text(); });
  } } } };
})();
</script>
<link rel="manifest" href="/manifest.json"><link rel="apple-touch-icon" href="/kestrel-icon.png">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-title" content="Kestrel">"""
MANIFEST = {"name": "Kestrel", "short_name": "Kestrel", "start_url": "/", "display": "standalone",
            "background_color": "#0b1f33", "theme_color": "#0b1f33",
            "icons": [{"src": "/kestrel-icon.png", "sizes": "96x96", "type": "image/png"}]}


def tailscale_ip():
    """The Mac's Tailscale address, or None when Tailscale isn't on (no packet is actually sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("100.100.100.100", 53))            # Tailscale's own helper address
            ip = s.getsockname()[0]
    except OSError:
        return None
    return ip if ipaddress.ip_address(ip) in TAILNET else None


def access_key(cfg, new: bool = False) -> str:
    path = data_path(cfg, "phone_screen_key")
    if new or not path.exists():
        path.write_text(secrets.token_urlsafe(24))
        os.chmod(path, 0o600)
    return path.read_text().strip()


def link(cfg):
    ip = tailscale_ip()
    return f"http://{ip}:{PORT}/#key={access_key(cfg)}" if ip else None


def answer(cfg, raw: bytes, key: str) -> tuple:
    """(status code, JSON text) for one request from the phone."""
    from .app_api import handle, plain_json
    from .config import load_config
    if not hmac.compare_digest(key or "", access_key(cfg)):
        return 401, json.dumps({"error": "Open Kestrel on your phone with the link from the Mac's Setup screen."})
    try:
        msg = json.loads(raw or b"{}")
        action = str(msg.get("action", ""))
        if action == "app-version":
            version = (ROOT / "VERSION").read_text().strip() if (ROOT / "VERSION").exists() else "dev"
            return 200, json.dumps({"version": version})
        if action not in ALLOWED:
            return 200, json.dumps({"error": "That's done on the Mac (Kestrel's Setup screen)."})
        with contextlib.redirect_stdout(io.StringIO()):        # the bot's own messages stay out of the answer
            result = handle(action, load_config(), bool(msg.get("demo")), msg.get("confirm"), None)
    except Exception as e:
        result = {"error": str(e) or type(e).__name__}
    return 200, json.dumps(plain_json(result), default=str, allow_nan=False)


def make_handler(cfg):
    class Handler(http.server.BaseHTTPRequestHandler):
        def _send(self, code, body: bytes, kind: str):
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/":
                page = (WEB / "dashboard.html").read_text().replace("<head>", "<head>\n" + SHIM, 1)
                return self._send(200, page.encode(), "text/html; charset=utf-8")
            if path == "/manifest.json":
                return self._send(200, json.dumps(MANIFEST).encode(), "application/manifest+json")
            if path == "/kestrel-icon.png" and (WEB / "kestrel-icon.png").exists():
                return self._send(200, (WEB / "kestrel-icon.png").read_bytes(), "image/png")
            return self._send(404, b"Not here", "text/plain")

        def do_POST(self):
            if self.path != "/api":
                return self._send(404, b"Not here", "text/plain")
            length = min(int(self.headers.get("Content-Length") or 0), 10_000)
            code, text = answer(cfg, self.rfile.read(length), self.headers.get("X-Kestrel-Key", ""))
            return self._send(code, text.encode(), "application/json")

        def log_message(self, *args):                   # quiet
            pass
    return Handler


def serve_forever(cfg, stop: threading.Event = None, check_every: float = 60):
    """Runs in the autopilot: serves the phone screen whenever Tailscale is on (and follows its address)."""
    server, ip = None, None
    while not (stop and stop.is_set()):
        now_ip = tailscale_ip()
        if now_ip != ip:
            if server:
                server.shutdown()
                server.server_close()
                server = None
            ip = now_ip
            if ip:
                try:
                    server = http.server.ThreadingHTTPServer((ip, PORT), make_handler(cfg))
                    threading.Thread(target=server.serve_forever, daemon=True, name="phone-screen").start()
                except OSError as e:                     # e.g. the port is taken
                    print(f"phone screen: couldn't start on {ip}:{PORT} ({e})", file=sys.stderr)
                    server, ip = None, None
        (stop.wait(check_every) if stop else time.sleep(check_every))
    if server:
        server.shutdown()
        server.server_close()
