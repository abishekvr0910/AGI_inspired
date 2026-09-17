"""Authenticated web console integration tests with temporary state only."""
import json
import unittest
from web_ui_test_support import fixture, request, serving, sign_attestation


class WebConsoleTests(unittest.TestCase):
    def test_authenticated_dashboard_and_apis(self):
        with fixture(paused=False) as f, serving(f.gw) as server:
            sign_attestation(f)
            code, headers, body = request(server)
            self.assertEqual(code, 200)
            html = body.decode()
            for label in (
                "AGI_like", "MiroFish", "Munder Difflin", "Swarm Floor", "BUDGET PARAMETER CAP",
                "Ad & Research Engine", "CLIENT PROFILE", "RESEARCH TEMPLATE", "RESEARCH WORKER ENGINE",
                "Preview (Dry Run)", "Dispatch (Attested)",
            ):
                self.assertIn(label, html)
            self.assertNotIn("__BEARER_TOKEN_JSON__", html)
            self.assertNotIn("cdn.tailwindcss.com", html)
            self.assertNotIn("json.stringify", html)
            self.assertEqual(headers["cache-control"], "no-store")
            code, _, body = request(server, "POST", "/api/dispatch", {"spec": "fixture mission", "max_budget_usd": 0.5})
            self.assertEqual(code, 200)
            queued = json.loads(body)
            self.assertEqual(queued["status"], "queued")
            code, _, body = request(server, path="/api/tasks")
            self.assertEqual(code, 200)
            self.assertEqual(len(json.loads(body)["tasks"]), 1)
            code, _, body = request(server, path="/api/status")
            status = json.loads(body)
            self.assertTrue(status["attestation_valid"])
            self.assertFalse(status["estop_engaged"])
            self.assertEqual(status["total_tasks"], 1)
            self.assertEqual(status["worker_identity"], "fixture-worker")
            for path, key in (("/api/graph", "nodes"), ("/api/candidates", "candidates"),
                              (f"/api/tasks/{queued['task_id']}", "broker_audit")):
                code, _, body = request(server, path=path)
                self.assertEqual(code, 200)
                self.assertIn(key, json.loads(body))
            self.assertEqual(request(server, path="/unknown")[0], 404)
            self.assertEqual(request(server, path="/api/tasks/nope")[0], 400)

    def test_distribution_api_endpoints(self):
        import client_profile
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

        # 1. Unpaused: test clients, templates, dry-run, live admission
        with fixture(paused=False) as f, serving(f.gw) as server:
            client_profile.save_client_profile(sample_profile, root=f.root)

            # Templates endpoint
            code, _, body = request(server, path="/api/templates")
            self.assertEqual(code, 200)
            templates_data = json.loads(body)
            self.assertIn("templates", templates_data)
            t_ids = [t["id"] for t in templates_data["templates"]]
            self.assertEqual(len(t_ids), 7)
            self.assertIn("keyword_research", t_ids)
            self.assertIn("negative_keyword_harvest", t_ids)
            self.assertIn("audience_pain_point_research", t_ids)

            # Clients endpoint
            code, _, body = request(server, path="/api/clients")
            self.assertEqual(code, 200)
            clients_data = json.loads(body)
            self.assertIn("clients", clients_data)
            self.assertEqual(len(clients_data["clients"]), 1)
            self.assertEqual(clients_data["clients"][0]["client_id"], "apex-roofing")
            self.assertEqual(clients_data["clients"][0]["display_name"], "Apex Commercial Roofing")

            # Validation errors
            code, _, body = request(server, "POST", "/api/distribution/dispatch", {})
            self.assertEqual(code, 400)
            self.assertIn("client_id is required", json.loads(body)["error"])

            code, _, body = request(server, "POST", "/api/distribution/dispatch", {"client_id": "apex-roofing"})
            self.assertEqual(code, 400)
            self.assertIn("template is required", json.loads(body)["error"])

            code, _, body = request(server, "POST", "/api/distribution/dispatch", {
                "client_id": "apex-roofing", "template": "invalid_template"
            })
            self.assertEqual(code, 400)
            self.assertIn("unknown template", json.loads(body)["error"])

            code, _, body = request(server, "POST", "/api/distribution/dispatch", {
                "client_id": "apex-roofing", "template": "keyword_research", "worker_engine": "unknown_engine"
            })
            self.assertEqual(code, 400)
            self.assertIn("invalid worker_engine", json.loads(body)["error"])

            # Dry-run dispatch
            code, _, body = request(server, "POST", "/api/distribution/dispatch", {
                "client_id": "apex-roofing",
                "template": "negative_keyword_harvest",
                "dry_run": True,
                "worker_engine": "native",
            })
            self.assertEqual(code, 200)
            dry_res = json.loads(body)
            self.assertTrue(dry_res["dry_run"])
            self.assertEqual(dry_res["worker_engine"], "native")
            self.assertIn("spec", dry_res)
            self.assertIn("pass_criteria", dry_res)
            self.assertIn("Negative keyword", dry_res["spec"])

            # Live single dispatch under unpaused gateway
            code, _, body = request(server, "POST", "/api/distribution/dispatch", {
                "client_id": "apex-roofing",
                "template": "keyword_research",
                "dry_run": False,
                "worker_engine": "native",
                "target_keyword": "tpo roofing austin",
            })
            self.assertEqual(code, 200)
            live_res = json.loads(body)
            self.assertFalse(live_res["dry_run"])
            self.assertEqual(live_res["status"], "queued")
            self.assertEqual(live_res["worker_engine"], "native")
            task_id = live_res["task_id"]
            self.assertIsInstance(task_id, int)

            # Verify task in ledger
            with f.gw._conn() as c:
                row = c.execute("SELECT mission_id, status FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row["mission_id"], "distribution")
                self.assertEqual(row["status"], "queued")

            # Batch dry-run dispatch
            code, _, body = request(server, "POST", "/api/distribution/dispatch", {
                "client_id": "apex-roofing",
                "template": "all",
                "dry_run": True,
            })
            self.assertEqual(code, 200)
            batch_res = json.loads(body)
            self.assertTrue(batch_res["success"])
            self.assertEqual(batch_res["count"], 7)

            # Test /api/clients/apex-roofing/dossier
            code, _, body = request(server, "GET", "/api/clients/apex-roofing/dossier")
            self.assertEqual(code, 200)
            dossier_res = json.loads(body)
            self.assertTrue(dossier_res["success"])
            self.assertIn("Executive Strategy & Distribution Audit", dossier_res["dossier_markdown"])
            self.assertIn("<!doctype html>", dossier_res["dossier_html"])
            self.assertIn("campaign_summary", dossier_res)

            # Test /api/clients/apex-roofing/export-csv
            code, _, body = request(server, "GET", "/api/clients/apex-roofing/export-csv")
            self.assertEqual(code, 200)
            self.assertIn(b"Campaign,Ad Group,Keyword", body)

        # 2. Paused / ESTOP engaged: verify fail-closed live dispatch rejection
        with fixture(paused=True) as f, serving(f.gw) as server:
            client_profile.save_client_profile(sample_profile, root=f.root)

            # Dry-run still allowed under ESTOP
            code, _, body = request(server, "POST", "/api/distribution/dispatch", {
                "client_id": "apex-roofing",
                "template": "keyword_research",
                "dry_run": True,
            })
            self.assertEqual(code, 200)
            self.assertTrue(json.loads(body)["dry_run"])

            # Live admission rejected under ESTOP
            code, _, body = request(server, "POST", "/api/distribution/dispatch", {
                "client_id": "apex-roofing",
                "template": "keyword_research",
                "dry_run": False,
            })
            self.assertEqual(code, 400)
            self.assertIn("ESTOP engaged", json.loads(body)["error"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
