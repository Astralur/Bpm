"""Loopback-only HTTP service. Never exposes arbitrary filesystem paths."""
import json
import mimetypes
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

WEB_ROOT = Path(__file__).resolve().parent.parent / "web"


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, state, banana, **kwargs):
        self.state = state
        self.banana = banana
        super().__init__(*args, **kwargs)

    def log_message(self, *_):
        pass

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.end_headers()

    def do_GET(self):
        route = urlsplit(self.path).path
        if route in ("/state", "/asset-info"):
            payload = self.state.snapshot() if route == "/state" else {
                "kind": "video" if self.banana and self.banana.suffix.lower() in (".mp4", ".webm")
                else "image" if self.banana else "emoji"
            }
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        files = {"/": WEB_ROOT / "index.html", "/bridge.js": WEB_ROOT / "bridge.js"}
        if self.banana:
            files["/banana"] = self.banana
        target = files.get(route)
        if target is None or not target.is_file():
            self.send_error(404)
            return
        # Range support enables video seeks and loop playback in Chromium/OBS.
        size = target.stat().st_size
        start, end = 0, size-1
        partial_content = False
        header = self.headers.get("Range")
        if header:
            try:
                unit, interval = header.split("=", 1)
                first, last = interval.split("-", 1)
                if unit != "bytes" or "," in interval:
                    raise ValueError
                if first:
                    start = int(first)
                    end = min(int(last), end) if last else end
                else:
                    start = max(0, size - int(last))
                if start < 0 or start >= size or end < start:
                    raise ValueError
                partial_content = True
            except ValueError:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
        self.send_response(206 if partial_content else 200)
        self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(end-start+1))
        self.send_header("Accept-Ranges", "bytes")
        if partial_content:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with target.open("rb") as handle:
            handle.seek(start)
            remaining = end-start+1
            while remaining > 0:
                data = handle.read(min(65536, remaining))
                if not data:
                    break
                self.wfile.write(data)
                remaining -= len(data)


def make_server(state, port=8767, banana=None):
    path = Path(banana).resolve() if banana else None
    if path is not None and not path.is_file():
        raise ValueError(f"Banana file does not exist: {path}")
    if path is not None and path.suffix.lower() not in (".mp4", ".webm", ".png", ".jpg", ".jpeg"):
        raise ValueError("Use MP4/WebM or a still PNG/JPG. Convert animated GIFs to video first.")
    return ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, state=state, banana=path))
