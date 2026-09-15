import time
import unittest

from fastapi.testclient import TestClient

from app.main import app


class ApiGuardTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_search_rejects_invalid_email(self):
        r = self.client.post(
            "/api/search",
            data={"name": "Alex", "email": "not-valid", "source": "describe", "description": "WhatsApp and Excel every day by hand."},
        )
        self.assertEqual(r.status_code, 400)

    def test_search_rejects_short_description(self):
        r = self.client.post(
            "/api/search",
            data={"name": "Alex", "email": "alex@example.com", "source": "describe", "description": "too short"},
        )
        self.assertEqual(r.status_code, 400)

    def test_admin_endpoints_require_pin(self):
        self.assertEqual(self.client.get("/api/leads").status_code, 403)
        self.assertEqual(self.client.get("/api/runs").status_code, 403)
        self.assertEqual(self.client.get("/api/prospects/1").status_code, 403)
        self.assertEqual(self.client.post("/api/runs", json={"icp": "test"}).status_code, 403)

    def test_health_has_no_secrets(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        body = r.text.lower()
        self.assertNotIn("password", body)
        self.assertIn("smtp_configured", r.json())

    def test_describe_flow_builds_downloadable_report(self):
        r = self.client.post(
            "/api/search",
            data={
                "name": "Alex",
                "email": "alex@example.com",
                "source": "describe",
                "description": "Leads come on WhatsApp. Someone copies them into Excel. Follow-up is typed by hand.",
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json().get("lead_saved"))
        run_id = r.json()["id"]
        payload = {}
        for _ in range(80):
            payload = self.client.get(f"/api/runs/{run_id}").json()
            if payload.get("status") in ("completed", "failed"):
                break
            time.sleep(0.25)
        self.assertEqual(payload.get("status"), "completed", payload)
        self.assertNotIn("icp_text", payload)
        self.assertIn("diagnosis", payload.get("result") or {})
        report = self.client.get(f"/api/runs/{run_id}/report")
        self.assertEqual(report.status_code, 200)
        self.assertIn("attachment", report.headers.get("content-disposition", ""))
        self.assertIn("Overall manual dependency", report.text)
        mailed = self.client.post(f"/api/runs/{run_id}/email")
        self.assertEqual(mailed.status_code, 200)
        body = mailed.json()
        self.assertFalse(body.get("sent"))
        self.assertIn("Download", body.get("reason") or "")
        help_r = self.client.post(f"/api/runs/{run_id}/help")
        self.assertEqual(help_r.status_code, 200)
        self.assertTrue(help_r.json().get("saved"))

    def test_csv_flow_completes(self):
        r = self.client.post(
            "/api/search",
            data={
                "name": "Alex",
                "email": "alex@example.com",
                "source": "csv",
                "description": "This is our lead list exported from WhatsApp follow-up.",
            },
            files={"file": ("leads.csv", b"name,phone,status\nJane,0711,new\n", "text/csv")},
        )
        self.assertEqual(r.status_code, 200, r.text)
        run_id = r.json()["id"]
        payload = {}
        for _ in range(80):
            payload = self.client.get(f"/api/runs/{run_id}").json()
            if payload.get("status") in ("completed", "failed"):
                break
            time.sleep(0.25)
        self.assertEqual(payload.get("status"), "completed", payload)
        self.assertEqual((payload.get("result") or {}).get("source"), "csv")

    def test_wrong_admin_pin(self):
        r = self.client.post("/api/admin/unlock", json={"pin": "definitely-wrong-pin-xx"})
        self.assertEqual(r.status_code, 403)


if __name__ == "__main__":
    unittest.main()
