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

    def test_search_rejects_example_dot_com(self):
        r = self.client.post(
            "/api/search",
            data={"name": "Ada", "email": "ada@example.com", "source": "describe", "description": "WhatsApp and Excel every day by hand."},
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("real personal or company", (r.json().get("detail") or "").lower())

    def test_search_rejects_incomplete_website(self):
        r = self.client.post(
            "/api/search",
            data={"name": "Alex", "email": "alex@gmail.com", "source": "website", "url": ""},
        )
        self.assertEqual(r.status_code, 400)

    def test_search_rejects_blank_name(self):
        r = self.client.post(
            "/api/search",
            data={
                "name": " ",
                "email": "alex@gmail.com",
                "source": "website",
                "url": "https://northline.example.org",
            },
        )
        self.assertEqual(r.status_code, 400)

    def test_search_rejects_csv_without_note(self):
        r = self.client.post(
            "/api/search",
            data={"name": "Alex", "email": "alex@gmail.com", "source": "csv", "description": ""},
            files={"file": ("leads.csv", b"name,phone\nJane,0711\n", "text/csv")},
        )
        self.assertEqual(r.status_code, 400)

    def test_search_rejects_short_description(self):
        r = self.client.post(
            "/api/search",
            data={"name": "Alex", "email": "alex@gmail.com", "source": "describe", "description": "too short"},
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

    def test_book_route_is_gone(self):
        r = self.client.get("/book", follow_redirects=False)
        self.assertEqual(r.status_code, 404)

    def test_tip_rejects_tiny_amount(self):
        r = self.client.post("/api/tip", json={"amount_sats": 1})
        self.assertEqual(r.status_code, 400)
        self.assertNotIn("@blink", (r.text or "").lower())

    def test_describe_flow_builds_downloadable_report(self):
        r = self.client.post(
            "/api/search",
            data={
                "name": "Alex",
                "email": "alex@gmail.com",
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
        self.assertIn(".pdf", report.headers.get("content-disposition", ""))
        self.assertTrue(report.content.startswith(b"%PDF"))
        self.assertIn("application/pdf", report.headers.get("content-type", ""))
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
                "email": "alex@gmail.com",
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

    def test_repeat_email_keeps_one_inquiry(self):
        from app.db import SessionLocal
        from app.models import Inquiry

        payload = {
            "name": "Alex",
            "email": "Alex@Gmail.com",
            "source": "describe",
            "description": "Leads come on WhatsApp. Someone copies them into Excel by hand every day.",
        }
        first = self.client.post("/api/search", data=payload)
        self.assertEqual(first.status_code, 200, first.text)
        for _ in range(80):
            st = self.client.get(f"/api/runs/{first.json()['id']}").json()
            if st.get("status") in ("completed", "failed"):
                break
            time.sleep(0.25)
        second = self.client.post(
            "/api/search",
            data={**payload, "name": "Alexandra", "email": "alex@gmail.com"},
        )
        self.assertEqual(second.status_code, 200, second.text)
        db = SessionLocal()
        try:
            rows = db.query(Inquiry).filter(Inquiry.email == "alex@gmail.com").all()
            self.assertEqual(len(rows), 1)
            self.assertGreaterEqual(rows[0].search_count, 2)
            self.assertEqual(rows[0].name, "Alexandra")
        finally:
            db.close()

    def test_wrong_admin_pin(self):
        r = self.client.post("/api/admin/unlock", json={"pin": "definitely-wrong-pin-xx"})
        self.assertEqual(r.status_code, 403)


if __name__ == "__main__":
    unittest.main()
