import json
import time
import unittest
from unittest.mock import patch

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
        self.assertEqual(r.json().get("database"), "sqlite")
        self.assertNotIn("postgres://", body)

    def test_book_route_is_gone(self):
        r = self.client.get("/book", follow_redirects=False)
        self.assertEqual(r.status_code, 404)

    def test_tip_rejects_tiny_amount(self):
        r = self.client.post("/api/tip", json={"amount_sats": 1})
        self.assertEqual(r.status_code, 400)
        self.assertNotIn("@blink", (r.text or "").lower())

    def test_serverless_mode_runs_inside_start_request(self):
        """On Vercel the search only queues; POST /start does the work and is safe to repeat."""
        import uuid
        from unittest.mock import patch

        email = f"inline-{uuid.uuid4().hex[:8]}@gmail.com"
        with patch("app.api.settings.inline_runs", True):
            r = self.client.post(
                "/api/search",
                data={
                    "name": "Sam",
                    "email": email,
                    "source": "describe",
                    "description": "Leads come on WhatsApp. Someone copies them into Excel by hand.",
                },
            )
            self.assertEqual(r.status_code, 200, r.text)
            body = r.json()
            self.assertTrue(body.get("start"))
            run_id = body["id"]
            self.assertEqual(self.client.get(f"/api/runs/{run_id}").json().get("status"), "queued")
            started = self.client.post(f"/api/runs/{run_id}/start")
            self.assertEqual(started.status_code, 200, started.text)
            self.assertEqual(started.json().get("status"), "completed")
            again = self.client.post(f"/api/runs/{run_id}/start")
            self.assertEqual(again.json().get("status"), "completed")
        self.assertEqual(self.client.post("/api/runs/999999/start").status_code, 404)

    def test_describe_flow_builds_downloadable_report(self):
        r = self.client.post(
            "/api/search",
            data={
                "name": "Alex",
                "email": "describe.flow@gmail.com",
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
                "email": "csv.flow@gmail.com",
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
            "email": "Repeat.Case@Gmail.com",
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
            data={**payload, "name": "Alexandra", "email": "repeat.case@gmail.com"},
        )
        self.assertEqual(second.status_code, 200, second.text)
        db = SessionLocal()
        try:
            rows = db.query(Inquiry).filter(Inquiry.email == "repeat.case@gmail.com").all()
            self.assertEqual(len(rows), 1)
            self.assertGreaterEqual(rows[0].search_count, 2)
            self.assertEqual(rows[0].name, "Alexandra")
        finally:
            db.close()

    def test_sixth_search_requires_lightning_payment(self):
        """From the 6th diagnosis the server only proceeds once Blink confirms the invoice is paid."""
        import uuid
        from unittest.mock import patch

        from app.db import SessionLocal
        from app.models import Inquiry

        email = f"paywall-{uuid.uuid4().hex[:8]}@gmail.com"
        payload = {
            "name": "Alex",
            "email": email,
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
        db = SessionLocal()
        try:
            row = db.query(Inquiry).filter(Inquiry.email == email).one()
            row.search_count = 5
            db.commit()
        finally:
            db.close()
        fake = {
            "ok": True,
            "amount_sats": 1000,
            "amount_usd": "$0.80",
            "invoice": "lnbc10u1p" + ("q" * 40),
            "verify_url": "https://lnurl.blink.sv/verify/abc",
            "qr_png": "data:image/png;base64,aaaa",
            "wallet_uri": "lightning:lnbc",
        }
        with patch("app.api.create_tip_invoice", return_value=fake):
            blocked = self.client.post("/api/search", data=payload)
        self.assertEqual(blocked.status_code, 402, blocked.text)
        body = blocked.json()
        self.assertTrue(body.get("need_payment"))
        self.assertEqual(body.get("amount_sats"), 1000)
        self.assertEqual(body.get("amount_usd"), "$0.80")
        token = body.get("payment")
        self.assertTrue(token)
        self.assertNotIn("verify", blocked.text)  # the verify link never reaches the browser

        # The old "I've paid" flag alone no longer unlocks anything.
        with patch("app.api.create_tip_invoice", return_value=fake):
            bluff = self.client.post("/api/search", data={**payload, "unlock": "1"})
        self.assertEqual(bluff.status_code, 402, bluff.text)

        # Not paid yet: same token is kept, no diagnosis starts.
        with patch("app.api.invoice_paid", return_value=False):
            waiting = self.client.post("/api/search", data={**payload, "payment": token})
        self.assertEqual(waiting.status_code, 402, waiting.text)
        self.assertTrue(waiting.json().get("pending"))

        # Someone else's email cannot use this payment.
        other = {**payload, "email": f"other-{uuid.uuid4().hex[:8]}@gmail.com"}
        with patch("app.api.invoice_paid", return_value=True):
            stolen = self.client.post("/api/search", data={**other, "payment": token})
        self.assertEqual(stolen.status_code, 200, stolen.text)  # free first run for the new email
        self.assertTrue(stolen.json().get("id"))

        # Paid: one diagnosis unlocks, and it is recorded as a paid credit.
        with patch("app.api.invoice_paid", return_value=True):
            paid = self.client.post("/api/search", data={**payload, "payment": token})
        self.assertEqual(paid.status_code, 200, paid.text)
        for _ in range(80):
            st = self.client.get(f"/api/runs/{paid.json()['id']}").json()
            if st.get("status") in ("completed", "failed"):
                break
            time.sleep(0.25)
        db = SessionLocal()
        try:
            row = db.query(Inquiry).filter(Inquiry.email == email).one()
            self.assertEqual(row.search_count, 6)
            self.assertEqual(row.paid_credits, 1)
        finally:
            db.close()

        # The same payment cannot be used twice: a fresh invoice is shown instead.
        with patch("app.api.invoice_paid", return_value=True), patch("app.api.create_tip_invoice", return_value=fake):
            reuse = self.client.post("/api/search", data={**payload, "payment": token})
        self.assertEqual(reuse.status_code, 402, reuse.text)
        self.assertNotEqual(reuse.json().get("payment"), token)

        # If Blink cannot be reached, nothing is given away.
        with patch("app.api.create_tip_invoice", return_value=fake):
            fresh = self.client.post("/api/search", data=payload).json()["payment"]
        with patch("app.api.invoice_paid", side_effect=RuntimeError("network")):
            down = self.client.post("/api/search", data={**payload, "payment": fresh})
        self.assertEqual(down.status_code, 502, down.text)

    def test_paywall_refuses_invoice_without_verify_link(self):
        import uuid
        from unittest.mock import patch

        from app.db import SessionLocal
        from app.models import Inquiry

        email = f"noverify-{uuid.uuid4().hex[:8]}@gmail.com"
        db = SessionLocal()
        try:
            db.add(Inquiry(name="N", email=email, source_kind="describe", source_value="", search_count=5))
            db.commit()
        finally:
            db.close()
        fake = {"invoice": "lnbc10u1p" + ("q" * 40), "verify_url": "", "qr_png": "", "amount_sats": 1000}
        with patch("app.api.create_tip_invoice", return_value=fake):
            r = self.client.post(
                "/api/search",
                data={"name": "Nina", "email": email, "source": "describe", "description": "x" * 40},
            )
        self.assertEqual(r.status_code, 502, r.text)

    def test_payment_check_never_skips_certificate_verification(self):
        from unittest.mock import patch

        import httpx

        from app import tip

        calls = []

        class FakeClient:
            def __init__(self, verify=True, **kw):
                calls.append(verify)

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def get(self, url, headers=None):
                raise httpx.ConnectError("cert failed")

        with patch.object(tip.httpx, "Client", FakeClient):
            with self.assertRaises(httpx.ConnectError):
                tip.invoice_paid("https://lnurl.blink.sv/verify/abc")
        self.assertEqual(calls, [True])  # tried once, securely, and did not retry insecurely
        self.assertFalse(tip.invoice_paid("https://evil.example/verify/abc"))  # wrong host

    def test_no_insecure_fallback_on_hosted_servers(self):
        import os
        from unittest.mock import patch

        from app import tip

        with patch.dict(os.environ, {"VERCEL": "1"}):
            self.assertFalse(tip._insecure_fallback_ok())
        with patch.dict(os.environ, {"RENDER": "true"}):
            self.assertFalse(tip._insecure_fallback_ok())

    def test_wrong_admin_pin(self):
        r = self.client.post("/api/admin/unlock", json={"pin": "definitely-wrong-pin-xx"})
        self.assertEqual(r.status_code, 403)

    def test_format_eat_is_gmt_plus_3(self):
        from datetime import datetime, timezone

        from app.api import format_eat

        stamped = datetime(2026, 10, 12, 15, 3, tzinfo=timezone.utc)
        self.assertEqual(format_eat(stamped), "2026-10-12 18:03 GMT+3")

    def test_admin_login_page_exists(self):
        r = self.client.get("/admin")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Management login", r.text)
        self.assertIn("/api/admin/login", r.text)

    def test_admin_login_disabled_without_settings(self):
        from app.config import settings

        with patch.object(settings, "admin_pin", ""), patch.object(settings, "admin_email", ""):
            r = self.client.post("/api/admin/login", json={"email": "", "password": ""})
            self.assertEqual(r.status_code, 403)
            r = self.client.get("/api/leads", headers={"X-Admin-Pin": ""})
            self.assertEqual(r.status_code, 403)

    @patch("app.config.settings.admin_email", "owner@example.com")
    @patch("app.config.settings.admin_pin", "test-pin-1234567890")
    def test_admin_login_requires_admin_email(self):
        from app.config import settings

        blocked = self.client.post(
            "/api/admin/login",
            json={"email": "someone.else@gmail.com", "password": settings.admin_pin},
        )
        self.assertEqual(blocked.status_code, 403)
        ok = self.client.post(
            "/api/admin/login",
            json={"email": "owner@example.com", "password": settings.admin_pin},
        )
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertTrue(ok.json().get("ok"))
        leads = self.client.get("/api/leads", headers={"X-Admin-Pin": settings.admin_pin})
        self.assertEqual(leads.status_code, 200)
        self.assertIsInstance(leads.json(), list)

    def test_company_leads_admin_only(self):
        self.assertEqual(self.client.get("/api/company-leads").status_code, 403)
        r = self.client.get("/api/company-leads", headers={"X-Admin-Pin": "definitely-wrong-pin-xx"})
        self.assertEqual(r.status_code, 403)

    @patch("app.config.settings.admin_pin", "test-pin-1234567890")
    def test_company_leads_use_search_email(self):
        email = "company.lead@gmail.com"
        r = self.client.post(
            "/api/search",
            data={
                "name": "Jane Bakery",
                "email": email,
                "source": "describe",
                "description": "Orders come on WhatsApp and someone types them into a notebook every morning.",
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        run_id = r.json()["id"]
        if r.json().get("start"):
            self.client.post(f"/api/runs/{run_id}/start")
        for _ in range(80):
            if self.client.get(f"/api/runs/{run_id}").json().get("status") in ("completed", "failed"):
                break
            time.sleep(0.25)
        rows = self.client.get("/api/company-leads", headers={"X-Admin-Pin": "test-pin-1234567890"}).json()
        mine = [row for row in rows if row["email"] == email]
        self.assertEqual(len(mine), 1, rows)
        self.assertEqual(mine[0]["contact_name"], "Jane Bakery")
        self.assertEqual(mine[0]["run_id"], run_id)
        self.assertIn("WhatsApp", mine[0]["note"])

    def test_delete_endpoints_admin_only(self):
        self.assertEqual(self.client.post("/api/leads/delete", json={"ids": [1]}).status_code, 403)
        self.assertEqual(self.client.post("/api/company-leads/delete", json={"ids": [1]}).status_code, 403)

    def _search_lead(self, db, email, name="Del Test"):
        from app.models import Company, Contact, ResearchRun

        run = ResearchRun(
            icp_text=json.dumps({"name": name, "email": email, "source": "describe", "description": "note"}),
            status="completed",
            kind="search",
        )
        db.add(run)
        db.commit()
        company = Company(run_id=run.id, name=name, source="describe")
        db.add(company)
        db.commit()
        db.add(Contact(company_id=company.id, name=name, email=email))
        db.commit()
        return company.id

    @patch("app.config.settings.admin_pin", "test-pin-1234567890")
    def test_delete_company_leads_and_inquiries(self):
        from app.db import SessionLocal
        from app.models import Company, Contact, Inquiry

        pin = {"X-Admin-Pin": "test-pin-1234567890"}
        db = SessionLocal()
        try:
            older = self._search_lead(db, "del.one@gmail.com")
            newer = self._search_lead(db, "del.one@gmail.com")
            keep = self._search_lead(db, "del.keep@gmail.com")
            other = self._search_lead(db, "del.two@gmail.com")
            db.add(Inquiry(name="A", email="del.a@gmail.com", source_kind="describe", source_value=""))
            db.add(Inquiry(name="B", email="del.b@gmail.com", source_kind="describe", source_value=""))
            db.add(Inquiry(name="C", email="del.c@gmail.com", source_kind="describe", source_value=""))
            db.commit()
            inquiry_ids = [
                i.id for i in db.query(Inquiry).filter(Inquiry.email.in_(["del.a@gmail.com", "del.b@gmail.com"]))
            ]
        finally:
            db.close()

        rows = self.client.get("/api/company-leads", headers=pin).json()
        self.assertEqual([r["id"] for r in rows if r["email"] == "del.one@gmail.com"], [newer])

        r = self.client.post("/api/company-leads/delete", headers=pin, json={"ids": [newer, other]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["deleted"], 2)
        emails = {row["email"] for row in self.client.get("/api/company-leads", headers=pin).json()}
        # The older duplicate must not reappear after its newer row is deleted.
        self.assertNotIn("del.one@gmail.com", emails)
        self.assertNotIn("del.two@gmail.com", emails)
        self.assertIn("del.keep@gmail.com", emails)

        r = self.client.post("/api/leads/delete", headers=pin, json={"ids": inquiry_ids})
        self.assertEqual(r.json()["deleted"], 2)
        left = {row["email"] for row in self.client.get("/api/leads", headers=pin).json()}
        self.assertNotIn("del.a@gmail.com", left)
        self.assertNotIn("del.b@gmail.com", left)
        self.assertIn("del.c@gmail.com", left)

        db = SessionLocal()
        try:
            gone = [older, newer, other]
            self.assertEqual(db.query(Company).filter(Company.id.in_(gone)).count(), 0)
            self.assertEqual(db.query(Contact).filter(Contact.company_id.in_(gone)).count(), 0)
            self.assertEqual(db.query(Company).filter(Company.id == keep).count(), 1)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
