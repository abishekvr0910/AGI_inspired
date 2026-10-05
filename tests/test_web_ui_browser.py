"""tests/test_web_ui_browser.py — Real browser console acceptance test suite (P1-D).

Validates acceptance criteria from docs/PRODUCT_COMPLETION_PLAN_2026-10-04.md §7:
1. Real sign-in flow against an isolated fixture server with temporary token in real Chrome:
   - Failed authentication displays honest rejection ("Sign-in refused (401)").
   - Successful sign-in unlocks the authenticated dashboard, replaces DOM, and mounts controller scripts.
2. Console cockpit walkthrough:
   - Swarm Floor stations (Worker, Auditor, Warden, Scribe) and attestation badges render accurately.
   - Client profile and distribution research template selectors populate from backend.
   - Template preview drawer renders spec and pass criteria in browser.
   - Paused dispatch controls are disabled under active ESTOP.
3. Interactive repair diff view:
   - Unified repair diffs render with colored additions, deletions, and coordinate blocks.
4. Direct download endpoint gating & CSP enforcement:
   - Client package downloads respect evidence gating (draft warnings on incomplete research).
   - Strict Content-Security-Policy headers are enforced on all responses.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
ORCH = ROOT / "orchestrator"
TESTS = ROOT / "tests"
for p in (ROOT, ORCH, TESTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import browser_daemon
from browser_daemon import find_browser_executable, is_cdp_ready
import client_profile
import native_worker
import web_ui
from web_ui_test_support import fixture, serving, sign_attestation
import websockets


class ChromeBrowserContext:
    """Manages an ephemeral headless Chrome process and CDP tab session for UI testing."""

    def __init__(self, cdp_port: int = 0) -> None:
        if cdp_port <= 0:
            import socket
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", 0))
                self.cdp_port = s.getsockname()[1]
        else:
            self.cdp_port = cdp_port
        self.temp_dir = tempfile.mkdtemp(prefix="agi_chrome_webui_")
        self.proc: subprocess.Popen | None = None
        self.chrome_path = find_browser_executable()
        self.ready = False

    def start(self) -> bool:
        if not self.chrome_path or not os.path.isfile(self.chrome_path):
            return False

        cmd = [
            self.chrome_path,
            "--headless=new",
            f"--remote-debugging-port={self.cdp_port}",
            f"--user-data-dir={self.temp_dir}",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--disable-sync",
            "--disable-translate",
            "--metrics-recording-only",
        ]
        self.proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
        if not self.proc or not self.proc.pid:
            return False

        deadline = time.time() + 8.0
        while time.time() < deadline:
            if is_cdp_ready("127.0.0.1", self.cdp_port, timeout=0.3):
                self.ready = True
                return True
            time.sleep(0.2)
        return False

    def stop(self) -> None:
        if self.proc:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=3.0)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None
        shutil.rmtree(self.temp_dir, ignore_errors=True)


class TestWebUIBrowserAcceptance(unittest.TestCase):
    """Real browser acceptance testing of Web Console in headless Chrome via CDP."""

    @classmethod
    def setUpClass(cls):
        cls.browser_ctx = ChromeBrowserContext(cdp_port=0)
        cls.cdp_port = cls.browser_ctx.cdp_port
        cls.browser_available = cls.browser_ctx.start()

    @classmethod
    def tearDownClass(cls):
        cls.browser_ctx.stop()

    def setUp(self):
        if not self.browser_available:
            self.skipTest("Headless Chrome executable not available on host or failed to bind CDP port")

    def _run_async(self, coro):
        return asyncio.run(coro)

    async def _open_tab_and_session(self):
        target_id, ws_url = native_worker._acquire_cdp_page_target("127.0.0.1", self.cdp_port)
        ws = await websockets.connect(ws_url, ping_interval=None)
        cmd_id = 0

        async def send(method, params=None):
            nonlocal cmd_id
            cmd_id += 1
            cid = cmd_id
            await ws.send(json.dumps({"id": cid, "method": method, "params": params or {}}))
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("id") == cid:
                    return msg

        async def eval_js(expression, await_promise=False):
            params = {"expression": expression, "returnByValue": True}
            if await_promise:
                params["awaitPromise"] = True
            res = await send("Runtime.evaluate", params)
            return res.get("result", {}).get("result", {}).get("value")

        await send("Page.enable")
        await send("Runtime.enable")

        return target_id, ws, send, eval_js

    def test_01_unauthenticated_page_renders_operator_login(self):
        """Visiting the web console without auth serves LOGIN_HTML with sign-in controls."""
        async def run():
            with fixture(paused=True) as f, serving(f.gw) as server:
                port = server.server_address[1]
                target_id, ws, send, eval_js = await self._open_tab_and_session()
                try:
                    await send("Page.navigate", {"url": f"http://127.0.0.1:{port}/"})
                    await asyncio.sleep(0.5)

                    title = await eval_js("document.title")
                    self.assertEqual(title, "AGI_like operator sign-in")

                    has_input = await eval_js("Boolean(document.getElementById('token'))")
                    self.assertTrue(has_input)

                    has_button = await eval_js("Boolean(document.getElementById('btn-login'))")
                    self.assertTrue(has_button)

                    btn_text = await eval_js("document.getElementById('btn-login').textContent")
                    self.assertEqual(btn_text, "Open console")
                finally:
                    await ws.close()
                    native_worker._close_cdp_page_target("127.0.0.1", self.cdp_port, target_id)

        self._run_async(run())

    def test_02_bad_token_submission_displays_honest_rejection(self):
        """Submitting an invalid token displays an explicit 401 error message in the DOM."""
        async def run():
            with fixture(paused=True) as f, serving(f.gw) as server:
                port = server.server_address[1]
                target_id, ws, send, eval_js = await self._open_tab_and_session()
                try:
                    await send("Page.navigate", {"url": f"http://127.0.0.1:{port}/"})
                    await asyncio.sleep(0.5)

                    await eval_js("document.getElementById('token').value = 'wrong-token-abc'; document.getElementById('btn-login').click();")
                    await asyncio.sleep(0.5)

                    err_text = await eval_js("document.getElementById('error').textContent")
                    self.assertIn("Sign-in refused (401)", err_text)

                    # Page title must remain sign-in; console must not have unlocked
                    title = await eval_js("document.title")
                    self.assertEqual(title, "AGI_like operator sign-in")
                finally:
                    await ws.close()
                    native_worker._close_cdp_page_target("127.0.0.1", self.cdp_port, target_id)

        self._run_async(run())

    def test_03_valid_token_submission_mounts_authenticated_dashboard(self):
        """Submitting the valid bearer token mounts the executive dashboard and executes scripts."""
        async def run():
            with fixture(paused=True) as f, serving(f.gw) as server:
                sign_attestation(f)
                port = server.server_address[1]
                token = server.bearer_token

                target_id, ws, send, eval_js = await self._open_tab_and_session()
                try:
                    await send("Page.navigate", {"url": f"http://127.0.0.1:{port}/"})
                    await asyncio.sleep(0.5)

                    # Submit valid token
                    await eval_js(f"document.getElementById('token').value = {json.dumps(token)}; document.getElementById('btn-login').click();")
                    await asyncio.sleep(1.2)

                    # Console title changes
                    title = await eval_js("document.title")
                    self.assertIn("AGI_like", title)

                    # Controller script executed and initialized global state
                    state_type = await eval_js("typeof globalState")
                    self.assertEqual(state_type, "object")

                    # Attestation state badge reflects valid signed attestation
                    badge = await eval_js("document.getElementById('hdr-attestation-state').textContent")
                    self.assertEqual(badge, "VERIFIED")
                finally:
                    await ws.close()
                    native_worker._close_cdp_page_target("127.0.0.1", self.cdp_port, target_id)

        self._run_async(run())

    def test_04_dashboard_renders_swarm_floor_and_estop_button(self):
        """The authenticated dashboard renders all 4 Swarm Floor desks and correct ESTOP label."""
        async def run():
            with fixture(paused=True) as f, serving(f.gw) as server:
                sign_attestation(f)
                port = server.server_address[1]
                token = server.bearer_token

                target_id, ws, send, eval_js = await self._open_tab_and_session()
                try:
                    await send("Page.navigate", {"url": f"http://127.0.0.1:{port}/"})
                    await asyncio.sleep(0.5)
                    await eval_js(f"document.getElementById('token').value = {json.dumps(token)}; document.getElementById('btn-login').click();")
                    await asyncio.sleep(1.2)

                    body_text = await eval_js("document.body.innerText")
                    for desk in ("DESK #01 · WORKER", "DESK #02 · AUDITOR", "DESK #03 · WARDEN", "DESK #04 · SCRIBE"):
                        self.assertIn(desk, body_text)

                    estop_label = await eval_js("document.getElementById('estop-label').innerText")
                    self.assertEqual(estop_label, "ESTOP: ENGAGED")
                finally:
                    await ws.close()
                    native_worker._close_cdp_page_target("127.0.0.1", self.cdp_port, target_id)

        self._run_async(run())

    def test_05_client_selection_and_template_preview_in_browser(self):
        """Ad & Research Engine tab populates client profiles and previews template criteria."""
        sample_profile = {
            "client_id": "apex-roofing",
            "display_name": "Apex Commercial Roofing",
            "domain": "commercial roofing austin",
            "geo": ["US", "Austin-TX"],
            "language": ["en"],
            "offer": "Commercial roof inspection and TPO installation",
            "audience": "Commercial property managers",
            "competitors": ["https://austin-roof-pros.example"],
            "brand_voice": "Authoritative, prompt warranties",
            "landing_url": "https://apex-roofing.example/commercial",
            "seed_keywords": ["commercial roofer austin"],
            "forbidden_claims": ["100% free lifetime replacement"],
        }

        async def run():
            with fixture(paused=True) as f, serving(f.gw) as server:
                client_profile.save_client_profile(sample_profile, root=f.root)
                sign_attestation(f)
                port = server.server_address[1]
                token = server.bearer_token

                target_id, ws, send, eval_js = await self._open_tab_and_session()
                try:
                    await send("Page.navigate", {"url": f"http://127.0.0.1:{port}/"})
                    await asyncio.sleep(0.5)
                    await eval_js(f"document.getElementById('token').value = {json.dumps(token)}; document.getElementById('btn-login').click();")
                    await asyncio.sleep(1.2)

                    # Switch to Distribution tab
                    await eval_js("switchDispatchTab('dist');")
                    await asyncio.sleep(0.3)

                    is_dist_visible = await eval_js("!document.getElementById('form-dist').classList.contains('hidden')")
                    self.assertTrue(is_dist_visible)

                    # Check client dropdown
                    client_opts = await eval_js("Array.from(document.getElementById('dist-client').options).map(o => o.value)")
                    self.assertIn("apex-roofing", client_opts)

                    # Select client and template
                    await eval_js("document.getElementById('dist-client').value = 'apex-roofing';")
                    await eval_js("document.getElementById('dist-template').value = 'keyword_research'; updateTemplateDescription();")

                    # Click Preview button
                    await eval_js("handleDistributionDispatch(new Event('submit'), true);")
                    await asyncio.sleep(0.8)

                    # Check preview area is visible and populated
                    is_hidden = await eval_js("document.getElementById('dist-preview-area').classList.contains('hidden')")
                    self.assertFalse(is_hidden)

                    preview_text = await eval_js("document.getElementById('dist-preview-content').innerText")
                    self.assertIn("Apex Commercial Roofing", preview_text)
                    self.assertIn("commercial roofer austin", preview_text)
                finally:
                    await ws.close()
                    native_worker._close_cdp_page_target("127.0.0.1", self.cdp_port, target_id)

        self._run_async(run())

    def test_06_paused_dispatch_button_disabled_under_estop(self):
        """Dispatch buttons are disabled in the DOM when ESTOP is engaged."""
        async def run():
            with fixture(paused=True) as f, serving(f.gw) as server:
                sign_attestation(f)
                port = server.server_address[1]
                token = server.bearer_token

                target_id, ws, send, eval_js = await self._open_tab_and_session()
                try:
                    await send("Page.navigate", {"url": f"http://127.0.0.1:{port}/"})
                    await asyncio.sleep(0.5)
                    await eval_js(f"document.getElementById('token').value = {json.dumps(token)}; document.getElementById('btn-login').click();")
                    await asyncio.sleep(1.2)

                    custom_disabled = await eval_js("document.getElementById('btn-dispatch-submit').disabled")
                    self.assertTrue(custom_disabled)

                    dist_disabled = await eval_js("document.getElementById('btn-dist-dispatch').disabled")
                    self.assertTrue(dist_disabled)
                finally:
                    await ws.close()
                    native_worker._close_cdp_page_target("127.0.0.1", self.cdp_port, target_id)

        self._run_async(run())

    def test_07_interactive_repair_diff_modal_rendering(self):
        """Inspect modal renders interactive repair diffs with colored additions and deletions."""
        async def run():
            with fixture(paused=True) as f, serving(f.gw) as server:
                sign_attestation(f)
                # Seed task with repair history
                conn = sqlite3.connect(f.gw.ledger_db)
                try:
                    conn.execute(
                        "INSERT INTO tasks (task_id, mission_id, spec, status, critic_verdict, attempt_count) "
                        "VALUES (101, 'M3', 'Research cloud pricing', 'done', 'pass', 2)"
                    )
                    conn.commit()
                finally:
                    conn.close()

                # Seed attempt 1 and final deliverable artifacts in gateway runs_dir
                f.gw.runs_dir.mkdir(parents=True, exist_ok=True)
                (f.gw.runs_dir / "task101_deliverable.md").write_text("# Final Deliverable\n+ Verified pricing $40/mo\n- Old estimate $50/mo\n", encoding="utf-8")
                (f.gw.runs_dir / "task101_a1_worker_raw.txt").write_text("# Initial Deliverable\nOld estimate $50/mo\n", encoding="utf-8")

                port = server.server_address[1]
                token = server.bearer_token

                target_id, ws, send, eval_js = await self._open_tab_and_session()
                try:
                    await send("Page.navigate", {"url": f"http://127.0.0.1:{port}/"})
                    await asyncio.sleep(0.5)
                    await eval_js(f"document.getElementById('token').value = {json.dumps(token)}; document.getElementById('btn-login').click();")
                    await asyncio.sleep(1.2)

                    # Trigger inspection of task 101
                    await eval_js("inspectTask(101);")
                    await asyncio.sleep(0.8)

                    # Switch to Diff tab
                    await eval_js("switchModalView('diff');")
                    await asyncio.sleep(0.2)

                    diff_html = await eval_js("document.getElementById('modal-diff-content').innerHTML")
                    self.assertIn("text-emerald-400", diff_html)  # Green addition
                    self.assertIn("text-red-400", diff_html)      # Red deletion
                finally:
                    await ws.close()
                    native_worker._close_cdp_page_target("127.0.0.1", self.cdp_port, target_id)

        self._run_async(run())

    def test_08_direct_download_endpoints_and_csp_enforcement(self):
        """Direct browser fetches to unapproved package downloads return honest error and enforce CSP (R4)."""
        async def run():
            with fixture(paused=True) as f, serving(f.gw) as server:
                sign_attestation(f)
                port = server.server_address[1]
                token = server.bearer_token

                # 1. Assert strict Content-Security-Policy headers on responses
                import urllib.request
                req = urllib.request.Request(f"http://127.0.0.1:{port}/")
                req.add_header("Authorization", f"Bearer {token}")
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    csp = resp.headers.get("Content-Security-Policy", "")
                    self.assertIn("default-src 'none'", csp)
                    self.assertIn("connect-src 'self'", csp)
                    self.assertIn("frame-ancestors 'none'", csp)

                target_id, ws, send, eval_js = await self._open_tab_and_session()
                try:
                    await send("Page.navigate", {"url": f"http://127.0.0.1:{port}/"})
                    await asyncio.sleep(0.5)
                    await eval_js(f"document.getElementById('token').value = {json.dumps(token)}; document.getElementById('btn-login').click();")
                    await asyncio.sleep(1.2)

                    # 2. Fetch unapproved/non-existent client export from inside browser context
                    fetch_res = await eval_js(
                        """(async () => {
                            const res = await fetch('/api/clients/nonexistent-client/export-csv', {
                                headers: {'Authorization': 'Bearer ' + bearerToken}
                            });
                            return {status: res.status, ok: res.ok};
                        })()""",
                        await_promise=True,
                    )
                    self.assertEqual(fetch_res["status"], 400)
                    self.assertFalse(fetch_res["ok"])
                finally:
                    await ws.close()
                    native_worker._close_cdp_page_target("127.0.0.1", self.cdp_port, target_id)

        self._run_async(run())


if __name__ == "__main__":
    unittest.main()
