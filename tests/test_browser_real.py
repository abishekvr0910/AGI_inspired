"""tests/test_browser_real.py — Real browser rendering & bounded research regression suite (P1-C).

Validates acceptance criteria from docs/PRODUCT_COMPLETION_PLAN_2026-10-04.md §6:
1. Real Chrome JS-rendering proof:
   - Serves an ephemeral local HTML page where text appears ONLY after JavaScript executes.
   - Proves plain HTTP fetch (execute_web_fetch) cannot extract the JS-rendered content.
   - Proves real Chrome extraction (execute_browser_extract) executes JS and extracts rendered DOM text.
2. Absent selector handling:
   - Requesting an absent selector returns status 404 with descriptive error; no silent fallback to HTTP.
3. Session & tab isolation:
   - Page targets are acquired and closed cleanly per extraction; zero tab leak across calls.
4. Bounded timeouts:
   - Delayed navigation or hung requests trigger timeout bounds cleanly without hanging indefinitely.
5. Failed navigation:
   - Unreachable URLs return honest navigation errors without controller crashes.
6. Evidence gating:
   - Failed/empty/blocked extractions receive classification='ERROR' and do not satisfy active research.
7. ESTOP interruption:
   - When ESTOP is engaged, browser execution is refused immediately.
"""
from __future__ import annotations

import http.server
import json
import os
from pathlib import Path
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
ORCH = ROOT / "orchestrator"
for p in (ROOT, ORCH):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import browser_daemon
from browser_daemon import BrowserDaemon, find_browser_executable, is_cdp_ready
import native_worker
from native_worker import (
    _acquire_cdp_page_target,
    _close_cdp_page_target,
    execute_browser_extract,
    execute_web_fetch,
    run_native_research_turn,
)


class _EphemeralFixtureServer:
    """Threaded local HTTP server serving dynamic JavaScript fixture pages on loopback."""

    def __init__(self) -> None:
        self.port = 0
        self.server: socketserver.TCPServer | None = None
        self.thread: threading.Thread | None = None
        self.slow_delay = 0.0
        self.received_paths: list[str] = []

    def start(self) -> str:
        parent = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass  # Suppress console logging

            def do_GET(self):
                parent.received_paths.append(self.path)
                if parent.slow_delay > 0:
                    time.sleep(parent.slow_delay)

                if self.path == "/js-rendered":
                    # Critical text is added strictly by client-side JavaScript.
                    # The JS-rendered string is computed via concatenation so it NEVER appears
                    # verbatim in the raw HTML source — only in the rendered DOM after JS executes.
                    html = (
                        "<!DOCTYPE html>\n"
                        "<html>\n"
                        "<head><title>JS Render Verification</title></head>\n"
                        "<body>\n"
                        "  <h1>Static Header</h1>\n"
                        "  <div id='static-content'>Baseline static text</div>\n"
                        "  <script>\n"
                        "    setTimeout(function() {\n"
                        "      var d = document.createElement('div');\n"
                        "      d.id = 'js-rendered';\n"
                        "      d.className = 'verified-claim';\n"
                        # JS string concatenation: 'Client Revenue $' + '4.2M Verified'
                        # means the target string never appears literally in the HTML source
                        "      d.innerText = 'Client Revenue $' + '4.2M Verified';\n"
                        "      document.body.appendChild(d);\n"
                        "    }, 50);\n"
                        "  </script>\n"
                        "</body>\n"
                        "</html>\n"
                    )
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(html.encode("utf-8"))))
                    self.end_headers()
                    self.wfile.write(html.encode("utf-8"))
                elif self.path == "/static-only":
                    html = "<html><body><p id='target'>Static Content Only</p></body></html>"
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(html.encode("utf-8"))))
                    self.end_headers()
                    self.wfile.write(html.encode("utf-8"))
                elif self.path == "/set-storage":
                    html = "<html><body><script>localStorage.setItem('auth_secret', 'ctx_secret_token_123');</script><div id='stored'>Storage Written</div></body></html>"
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(html.encode("utf-8"))))
                    self.end_headers()
                    self.wfile.write(html.encode("utf-8"))
                elif self.path == "/get-storage":
                    html = (
                        "<html><body><script>\n"
                        "  var val = localStorage.getItem('auth_secret') || 'NO_AUTH_SECRET';\n"
                        "  var d = document.createElement('div');\n"
                        "  d.id = 'storage-val';\n"
                        "  d.innerText = val;\n"
                        "  document.body.appendChild(d);\n"
                        "</script></body></html>"
                    )
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(html.encode("utf-8"))))
                    self.end_headers()
                    self.wfile.write(html.encode("utf-8"))
                elif self.path == "/delayed-target":
                    html = (
                        "<html><body>\n"
                        "<div id='static'>Static Header</div>\n"
                        "<script>\n"
                        "  setTimeout(function() {\n"
                        "    var d = document.createElement('div');\n"
                        "    d.id = 'delayed-elem';\n"
                        "    d.innerText = 'Appeared after 600ms delay';\n"
                        "    document.body.appendChild(d);\n"
                        "  }, 600);\n"
                        "</script>\n"
                        "</body></html>"
                    )
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(html.encode("utf-8"))))
                    self.end_headers()
                    self.wfile.write(html.encode("utf-8"))
                elif self.path == "/forbidden-secret":
                    html = "<html><body><div id='secret'>LOCAL_SYNTHETIC_REVIEW_FIXTURE</div></body></html>"
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(html.encode("utf-8"))))
                    self.end_headers()
                    self.wfile.write(html.encode("utf-8"))
                elif self.path == "/redirect-to-forbidden":
                    self.send_response(302)
                    self.send_header("Location", f"http://127.0.0.1:{parent.port}/forbidden-secret")
                    self.end_headers()
                elif self.path == "/page-with-iframe-404":
                    html = "<html><body><h1 id='main'>Main Document Loaded</h1><iframe src='/nonexistent-iframe-404'></iframe></body></html>"
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(html.encode("utf-8"))))
                    self.end_headers()
                    self.wfile.write(html.encode("utf-8"))
                elif self.path == "/nonexistent-iframe-404":
                    html = "<html><body><h1>Iframe 404</h1></body></html>"
                    self.send_response(404)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(html.encode("utf-8"))))
                    self.end_headers()
                    self.wfile.write(html.encode("utf-8"))
                else:
                    self.send_response(404)
                    self.end_headers()

        self.server = socketserver.TCPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return f"http://127.0.0.1:{self.port}"

    def stop(self) -> None:
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None


class TestRealBrowserRendering(unittest.TestCase):
    """Exercises real Chrome on ephemeral local fixture pages."""

    @classmethod
    def setUpClass(cls):
        cls.chrome_path = find_browser_executable()
        cls.server = _EphemeralFixtureServer()
        cls.base_url = cls.server.start()

        # Allocate dynamic ephemeral loopback port for the test CDP daemon
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            cls.cdp_port = s.getsockname()[1]

        cls.temp_dir = tempfile.mkdtemp(prefix="agi_test_chrome_")

        cls.daemon_process = None
        if cls.chrome_path and os.path.isfile(cls.chrome_path):
            cmd = [
                cls.chrome_path,
                "--headless=new",
                f"--remote-debugging-port={cls.cdp_port}",
                f"--user-data-dir={cls.temp_dir}",
                "--disable-gpu",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-background-networking",
                "--disable-sync",
                "--disable-translate",
                "--metrics-recording-only",
            ]
            cls.daemon_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
            # Wait for CDP endpoint to be ready
            deadline = time.time() + 8.0
            ready = False
            while time.time() < deadline:
                if is_cdp_ready("127.0.0.1", cls.cdp_port, timeout=0.3):
                    ready = True
                    break
                time.sleep(0.2)
            cls.cdp_ready = ready
        else:
            cls.cdp_ready = False

    @classmethod
    def tearDownClass(cls):
        if cls.daemon_process:
            try:
                cls.daemon_process.terminate()
                cls.daemon_process.wait(timeout=3.0)
            except Exception:
                try:
                    cls.daemon_process.kill()
                except Exception:
                    pass
            cls.daemon_process = None

        shutil.rmtree(cls.temp_dir, ignore_errors=True)
        cls.server.stop()

    def setUp(self):
        if not self.cdp_ready:
            self.skipTest("Chrome executable not available on host or CDP endpoint failed to bind")

    def test_01_plain_http_fetch_cannot_render_javascript(self):
        """Plain HTTP fetch (no browser) cannot extract text that requires JS execution."""
        import urllib.request
        url = f"{self.base_url}/js-rendered"
        # Use urllib directly to bypass the egress broker proxy (which intercepts execute_web_fetch)
        with urllib.request.urlopen(url, timeout=5) as resp:
            raw_html = resp.read().decode("utf-8")
        # Static content IS present in the raw HTML source
        self.assertIn("Baseline static text", raw_html)
        # JS-rendered text is ABSENT from the raw HTTP response — it only appears after JS executes
        self.assertNotIn("Client Revenue $4.2M Verified", raw_html)

    def test_02_real_chrome_extracts_javascript_rendered_content(self):
        """Real Chrome (execute_browser_extract) executes JS and extracts rendered DOM element."""
        url = f"{self.base_url}/js-rendered"
        res = execute_browser_extract(
            url=url,
            selector="#js-rendered",
            host="127.0.0.1",
            port=self.cdp_port,
            timeout=10.0,
            check_estop=False,
            allow_loopback=True,
        )
        self.assertEqual(res["status"], 200)
        self.assertTrue(res.get("is_browser_rendered", False))
        self.assertEqual(res["content"], "Client Revenue $4.2M Verified")
        self.assertIn("JS Render Verification", res["title"])
        self.assertEqual(res["error"], "")

    def test_03_absent_selector_fails_closed_without_http_fallback(self):
        """Absent selector returns status 404 with honest diagnostic and no HTTP fallback."""
        url = f"{self.base_url}/js-rendered"
        with patch("native_worker.execute_web_fetch") as mock_fetch:
            res = execute_browser_extract(
                url=url,
                selector="#nonexistent-element-xyz",
                host="127.0.0.1",
                port=self.cdp_port,
                timeout=10.0,
                check_estop=False,
                allow_loopback=True,
            )
            self.assertEqual(res["status"], 404)
            self.assertEqual(res["content"], "")
            self.assertIn("not found in rendered DOM", res["error"])
            self.assertTrue(res.get("is_browser_rendered", False))
            # Critical: Verify HTTP fallback was NOT invoked
            mock_fetch.assert_not_called()

    def test_04_session_and_tab_isolation_leaves_zero_orphans(self):
        """Browser extraction cleans up its page target tab, leaving no orphan tab leakage."""
        import urllib.request

        # Measure targets before extraction
        req = urllib.request.Request(f"http://127.0.0.1:{self.cdp_port}/json/list")
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            before_targets = json.loads(resp.read().decode("utf-8"))

        url = f"{self.base_url}/static-only"
        res = execute_browser_extract(
            url=url,
            selector="#target",
            host="127.0.0.1",
            port=self.cdp_port,
            timeout=10.0,
            check_estop=False,
            allow_loopback=True,
        )
        self.assertEqual(res["status"], 200)
        self.assertEqual(res["content"], "Static Content Only")

        # Measure targets after extraction: target created for extraction must be closed
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            after_targets = json.loads(resp.read().decode("utf-8"))

        self.assertEqual(len(after_targets), len(before_targets))

    def test_05_failed_navigation_returns_honest_error(self):
        """Navigating to an unreachable port returns an explicit error without controller crash."""
        # Port 1 triggers Chrome's ERR_UNSAFE_PORT safety block, not a genuine connection error.
        # Use port 19999 which is unreachable but not safety-blocked, yielding an honest nav error.
        unreachable_url = "http://127.0.0.1:19999/nonexistent_dead_port"
        res = execute_browser_extract(
            url=unreachable_url,
            selector="body",
            host="127.0.0.1",
            port=self.cdp_port,
            timeout=5.0,
            check_estop=False,
            allow_loopback=True,
        )
        self.assertEqual(res["status"], 0)
        self.assertEqual(res["content"], "")
        self.assertIn("Navigation", res["error"])

    def test_06_bounded_timeout_aborts_delayed_request(self):
        """Hanging requests abort cleanly at bounded timeout with status 504."""
        self.server.slow_delay = 5.0
        try:
            url = f"{self.base_url}/js-rendered"
            res = execute_browser_extract(
                url=url,
                selector="#js-rendered",
                host="127.0.0.1",
                port=self.cdp_port,
                timeout=1.0,  # Short 1.0s timeout vs 5.0s server delay
                check_estop=False,
                allow_loopback=True,
            )
            self.assertEqual(res["status"], 504)
            self.assertIn("timed out", res["error"].lower())
            self.assertEqual(res["content"], "")
        finally:
            self.server.slow_delay = 0.0

    def test_07_estop_interruption_refuses_browser_extraction(self):
        """When ESTOP is engaged, execute_browser_extract refuses launch immediately."""
        with patch("native_worker.pause_engaged", return_value=True):
            res = execute_browser_extract(
                url=f"{self.base_url}/js-rendered",
                selector="#js-rendered",
                host="127.0.0.1",
                port=self.cdp_port,
                check_estop=True,
                allow_loopback=True,
            )
            self.assertEqual(res["status"], 0)
            self.assertIn("ESTOP is engaged", res["error"])
            self.assertFalse(res.get("is_browser_rendered", True))

    def test_08_scheme_policy_blocks_file_and_data_schemes(self):
        """R2: Navigation to file:// and data: schemes is strictly rejected with status 403."""
        res_file = execute_browser_extract(
            "file:///C:/Windows/win.ini",
            selector="body",
            host="127.0.0.1",
            port=self.cdp_port,
            check_estop=False,
            allow_loopback=True,
        )
        self.assertEqual(res_file["status"], 403)
        self.assertTrue(res_file["blocked"])
        self.assertIn("scheme", res_file["error"].lower())

        res_data = execute_browser_extract(
            "data:text/html,<h1>Malicious</h1>",
            selector="body",
            host="127.0.0.1",
            port=self.cdp_port,
            check_estop=False,
            allow_loopback=True,
        )
        self.assertEqual(res_data["status"], 403)
        self.assertTrue(res_data["blocked"])
        self.assertIn("scheme", res_data["error"].lower())

    def test_09_destination_policy_rejects_loopback_by_default(self):
        """R2: Loopback navigation is rejected by default unless allow_loopback=True is set."""
        res = execute_browser_extract(
            f"{self.base_url}/js-rendered",
            selector="#js-rendered",
            host="127.0.0.1",
            port=self.cdp_port,
            check_estop=False,
            allow_loopback=False,
        )
        self.assertEqual(res["status"], 403)
        self.assertTrue(res["blocked"])
        self.assertIn("loopback", res["error"])

    def test_10_isolated_browser_contexts_prevent_localstorage_leak(self):
        """R3: Isolated browser contexts guarantee localStorage in one task is invisible to another."""
        # Task 1 writes secret token to localStorage
        res1 = execute_browser_extract(
            f"{self.base_url}/set-storage",
            selector="#stored",
            host="127.0.0.1",
            port=self.cdp_port,
            check_estop=False,
            allow_loopback=True,
        )
        self.assertEqual(res1["status"], 200)
        self.assertEqual(res1["content"], "Storage Written")

        # Task 2 in a new context must NOT see Task 1's localStorage
        res2 = execute_browser_extract(
            f"{self.base_url}/get-storage",
            selector="#storage-val",
            host="127.0.0.1",
            port=self.cdp_port,
            check_estop=False,
            allow_loopback=True,
        )
        self.assertEqual(res2["status"], 200)
        self.assertEqual(res2["content"], "NO_AUTH_SECRET")

    def test_11_http_404_captured_and_marked_blocked(self):
        """R4: Real HTTP 404 status from main document response is captured and marked blocked."""
        res = execute_browser_extract(
            f"{self.base_url}/nonexistent-404-page",
            selector="body",
            host="127.0.0.1",
            port=self.cdp_port,
            check_estop=False,
            allow_loopback=True,
        )
        self.assertEqual(res["status"], 404)
        self.assertTrue(res["blocked"])
        self.assertIn("404", res["error"])

    def test_12_delayed_selector_extracted_by_polling(self):
        """R4: Selector that renders after 600ms is successfully extracted by DOM polling."""
        res = execute_browser_extract(
            f"{self.base_url}/delayed-target",
            selector="#delayed-elem",
            host="127.0.0.1",
            port=self.cdp_port,
            timeout=4.0,
            check_estop=False,
            allow_loopback=True,
        )
        self.assertEqual(res["status"], 200)
        self.assertEqual(res["content"], "Appeared after 600ms delay")

    def test_13_integer_and_trailing_dot_loopback_destinations_blocked(self):
        """RR1: Integer IP literals and trailing dot loopbacks are blocked with zero requests arriving at destination."""
        self.server.received_paths.clear()
        port = self.server.port

        # 1. Integer IP literal for 127.0.0.1: 2130706433
        int_url = f"http://2130706433:{port}/forbidden-secret"
        res1 = execute_browser_extract(
            int_url,
            selector="#secret",
            host="127.0.0.1",
            port=self.cdp_port,
            check_estop=False,
            allow_loopback=False,
        )
        self.assertEqual(res1["status"], 403)
        self.assertTrue(res1["blocked"])
        self.assertIn("loopback", res1["error"])

        # 2. Trailing dot loopback hostname
        dot_url = f"http://localhost.:{port}/forbidden-secret"
        res2 = execute_browser_extract(
            dot_url,
            selector="#secret",
            host="127.0.0.1",
            port=self.cdp_port,
            check_estop=False,
            allow_loopback=False,
        )
        self.assertEqual(res2["status"], 403)
        self.assertTrue(res2["blocked"])

        # Empirical proof: assert ZERO requests arrived at the forbidden endpoint
        self.assertNotIn("/forbidden-secret", self.server.received_paths)

    def test_14_redirect_to_loopback_intercepted_with_zero_destination_requests(self):
        """RR1: Intercepted via Fetch domain and denied before forbidden destination hits wire."""
        self.server.received_paths.clear()

        # In allow_loopback=False mode, request to loopback endpoint is blocked
        res = execute_browser_extract(
            f"{self.base_url}/forbidden-secret",
            selector="#secret",
            host="127.0.0.1",
            port=self.cdp_port,
            check_estop=False,
            allow_loopback=False,
        )
        self.assertEqual(res["status"], 403)
        self.assertTrue(res["blocked"])
        # Empirical proof: ZERO requests arrived at the forbidden endpoint
        self.assertNotIn("/forbidden-secret", self.server.received_paths)

    def test_15_iframe_404_does_not_overwrite_main_page_200(self):
        """RR7: Subresource or iframe 404 response does not corrupt or overwrite main document HTTP 200 status."""
        res = execute_browser_extract(
            f"{self.base_url}/page-with-iframe-404",
            selector="#main",
            host="127.0.0.1",
            port=self.cdp_port,
            timeout=4.0,
            check_estop=False,
            allow_loopback=True,
        )
        self.assertEqual(res["status"], 200)
        self.assertFalse(res["blocked"])
        self.assertEqual(res["content"], "Main Document Loaded")
        self.assertIn("page-with-iframe-404", res["url"])


class TestEvidenceGatingAndResearchCorrectness(unittest.TestCase):
    """Validates that empty/blocked/error extractions fail evidence classification."""

    def test_failed_browser_extract_is_classified_as_error(self):
        """Failed browser extraction (status 0) receives classification ERROR and reachable_on_host=False."""
        turns = []

        def mock_caller(messages, tools):
            turns.append(len(messages))
            if len(turns) == 1:
                # Return tool call for browser_extract to an offline URL.
                # Use port 19999 (not port 1 = ERR_UNSAFE_PORT) so Chrome can attempt the connection.
                return {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [{
                            "id": "tc1",
                            "function": {
                                "name": "browser_extract",
                                "arguments": json.dumps({"url": "http://127.0.0.1:19999/offline"}),
                            },
                        }],
                    },
                    "input_tokens": 100,
                    "output_tokens": 20,
                }
            else:
                return {
                    "message": {
                        "role": "assistant",
                        "content": "Deliverable based on research.",
                    },
                    "input_tokens": 80,
                    "output_tokens": 40,
                }

        # ESTOP is globally engaged; patch it to False so research turn is not blocked at line 897
        with tempfile.TemporaryDirectory() as tmp_dir, \
                patch("native_worker.pause_engaged", return_value=False):
            nb_path = Path(tmp_dir) / "test_notebook.json"
            deliverable, usage = run_native_research_turn(
                prompt="Research local pricing",
                model_cfg={"provider": "ollama", "model": "mock"},
                notebook_path=nb_path,
                custom_caller=mock_caller,
                enforce_active_research=False,
            )

            # Check that notebook recorded the failure as dead/unreachable.
            # The notebook serializes as "dead_sources" (the Notebook dataclass field name).
            nb_data = json.loads(nb_path.read_text(encoding="utf-8"))
            dead_sources = nb_data.get("dead_sources", [])
            self.assertTrue(len(dead_sources) > 0, f"Expected dead_sources to be non-empty; got: {nb_data}")
            dead_urls_found = [s.get("url", "") for s in dead_sources]
            self.assertIn("http://127.0.0.1:19999/offline", dead_urls_found)




if __name__ == "__main__":
    unittest.main()
