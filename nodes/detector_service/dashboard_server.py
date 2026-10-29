"""Server HTTP kecil untuk dashboard (satu jaringan lokal dengan pengguna)."""
from __future__ import annotations

import json
import socket
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from shared.config import ROOT, Config

DASHBOARD_DIR = ROOT / "dashboard"


class _Handler(SimpleHTTPRequestHandler):
    cfg: Config

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DASHBOARD_DIR), **kwargs)

    def do_GET(self):
        if self.path.split("?")[0] == "/config.json":
            body = json.dumps({"project_id": self.cfg.project_id,
                               "ws_url": self.cfg.mqtt_ws_url}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def log_message(self, *args):  # diamkan log akses
        pass


def lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))   # tidak mengirim paket; hanya memilih interface
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def start_dashboard(cfg: Config, port: int) -> ThreadingHTTPServer:
    handler = type("Handler", (_Handler,), {"cfg": cfg})
    server = ThreadingHTTPServer(("0.0.0.0", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
