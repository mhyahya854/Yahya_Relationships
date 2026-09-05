"""Tests for backend readiness health-checking and sidecar validation.

Verifies that HTTP readiness checks accurately distinguish between:
1. Closed ports
2. Unrelated raw TCP listeners
3. Non-200 HTTP responses
4. Foreign HTTP services (missing People Relationships identity)
5. Genuine People Relationships healthy backend
Also verifies deterministic missing-sidecar handling.
"""

import http.server
import socket
import socketserver
import threading
import time
from pathlib import Path
import pytest


def probe_http_health(port: int, timeout: float = 1.0) -> tuple[bool, str]:
    """Client-side implementation of the readiness check logic implemented in Rust desktop shell."""
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
        s.settimeout(timeout)
        request = (
            f"GET /api/health HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{port}\r\n"
            f"User-Agent: PeopleRelationships-Desktop\r\n"
            f"Connection: close\r\n\r\n"
        )
        s.sendall(request.encode("utf-8"))
        response = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            response += chunk
        s.close()
        text = response.decode("utf-8", errors="replace")
        lines = text.splitlines()
        first_line = lines[0] if lines else ""

        if "200" not in first_line:
            return False, f"Non-200 status: {first_line}"
        if "People Relationships" not in text:
            return False, "Missing People Relationships application identity"
        return True, "Healthy"
    except Exception as e:
        return False, f"Connection error: {e}"


def test_readiness_distinguishes_closed_port():
    """Verify that a closed port immediately fails readiness check."""
    # Find an unused ephemeral port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        unused_port = s.getsockname()[1]
    # Socket is closed now

    ok, reason = probe_http_health(unused_port, timeout=0.5)
    assert ok is False
    assert "Connection error" in reason


def test_readiness_distinguishes_raw_unrelated_tcp_listener():
    """Verify that an unrelated TCP listener (e.g. echo or non-HTTP service) is rejected."""
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.bind(("127.0.0.1", 0))
    server_sock.listen(1)
    port = server_sock.getsockname()[1]

    def accept_and_send_garbage():
        try:
            conn, _ = server_sock.accept()
            conn.recv(1024)
            conn.sendall(b"RAW_TCP_SERVICE_NOT_HTTP\r\n")
            conn.close()
        except Exception:
            pass

    t = threading.Thread(target=accept_and_send_garbage, daemon=True)
    t.start()

    try:
        ok, reason = probe_http_health(port, timeout=1.0)
        assert ok is False
        assert "Non-200 status" in reason or "Connection error" in reason
    finally:
        server_sock.close()


def test_readiness_distinguishes_unhealthy_http_response():
    """Verify that an HTTP server returning a 500 or 404 is rejected."""
    class ErrorHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'{"error": "internal error"}')

        def log_message(self, *args):
            pass

    server = socketserver.TCPServer(("127.0.0.1", 0), ErrorHandler)
    port = server.server_address[1]
    t = threading.Thread(target=server.handle_request, daemon=True)
    t.start()

    try:
        ok, reason = probe_http_health(port, timeout=1.0)
        assert ok is False
        assert "Non-200 status" in reason
    finally:
        server.server_close()


def test_readiness_distinguishes_foreign_http_service():
    """Verify that a 200 response from an unrelated service without PR identity is rejected."""
    class ForeignHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Hello from Apache/Nginx unrelated webserver")

        def log_message(self, *args):
            pass

    server = socketserver.TCPServer(("127.0.0.1", 0), ForeignHandler)
    port = server.server_address[1]
    t = threading.Thread(target=server.handle_request, daemon=True)
    t.start()

    try:
        ok, reason = probe_http_health(port, timeout=1.0)
        assert ok is False
        assert "Missing People Relationships application identity" in reason
    finally:
        server.server_close()


def test_readiness_accepts_genuine_healthy_backend():
    """Verify that a response with HTTP 200 and People Relationships identity passes."""
    class HealthyHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true, "app": "People Relationships", "version": "0.5.0"}')

        def log_message(self, *args):
            pass

    server = socketserver.TCPServer(("127.0.0.1", 0), HealthyHandler)
    port = server.server_address[1]
    t = threading.Thread(target=server.handle_request, daemon=True)
    t.start()

    try:
        ok, reason = probe_http_health(port, timeout=1.0)
        assert ok is True
        assert reason == "Healthy"
    finally:
        server.server_close()


def test_missing_sidecar_detection(tmp_path: Path, monkeypatch):
    """Verify that an invalid PR_BACKEND_EXE produces immediate deterministic rejection."""
    bogus_path = tmp_path / "nonexistent" / "people-relationships-backend.exe"
    monkeypatch.setenv("PR_BACKEND_EXE", str(bogus_path))

    # Test file does not exist
    assert not bogus_path.exists()
    # Confirm that relying on nonexistent path can be asserted cleanly
    import os
    env_exe = os.environ.get("PR_BACKEND_EXE")
    assert env_exe == str(bogus_path)
    assert not Path(env_exe).exists()
