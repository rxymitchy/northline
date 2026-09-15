import unittest
from unittest.mock import patch

from app.emailer import redact_secrets, send_email, valid_email
from app.modules.diagnosis import build_diagnosis
from app.modules.page_type import should_skip_search_result
from app.modules.research import visitor_research
from app.modules.peers import guess_industry
from app.modules.peers import _on_topic, industry_profile
from app.brief import build_brief


class EmailValidationTests(unittest.TestCase):
    def test_accepts_normal_address(self):
        self.assertTrue(valid_email("alex@example.com"))

    def test_rejects_empty_and_garbage(self):
        self.assertFalse(valid_email(""))
        self.assertFalse(valid_email("not-an-email"))
        self.assertFalse(valid_email("a@b"))
        self.assertFalse(valid_email("alex@example"))

    @patch("app.emailer.smtp_ready", return_value=False)
    def test_smtp_unconfigured_does_not_send(self, _ready):
        result = send_email("alex@example.com", "Subject", "Body", html="<p>Hi</p>")
        self.assertFalse(result["sent"])
        self.assertEqual(result["code"], "smtp_unconfigured")

    def test_invalid_email_code(self):
        result = send_email("nope", "Subject", "Body")
        self.assertEqual(result["code"], "invalid_email")

    def test_redact_does_not_crash_on_empty(self):
        self.assertEqual(redact_secrets(""), "")


class DiagnosisTests(unittest.TestCase):
    def test_whatsapp_without_bot_is_high(self):
        research = {
            "text": "Message us on WhatsApp and we will get back to you.",
            "signals": {"whatsapp_channel": True, "manual_followup_language": True, "chatbot": False},
        }
        gap = {
            "exists": True,
            "facts": ["Public WhatsApp enquiry/contact channel on the site."],
            "gaps": ["WhatsApp is used as a customer channel with no visible chatbot — follow-up is likely manual."],
        }
        dx = build_diagnosis("website", research, gap, {})
        self.assertEqual(dx["overall"], "HIGH")
        self.assertTrue(any(p["process"] == "Lead capture" for p in dx["processes"]))
        self.assertIn("capture", dx["workflow"])
        self.assertIn("Based on the information provided", dx["summary"])
        self.assertNotIn("TODO", dx["automate_first"]["reason"])

    def test_describe_csv_record_keeping(self):
        research = {"text": "Leads sit in an Excel sheet and someone copy-pastes from WhatsApp.", "signals": {"whatsapp_channel": True, "enquiry_form": True}}
        gap = {"exists": True, "facts": [], "gaps": []}
        dx = build_diagnosis("csv", research, gap, {})
        names = [p["process"] for p in dx["processes"]]
        self.assertIn("Record keeping", names)

    def test_low_when_nothing_visible(self):
        dx = build_diagnosis("website", {"text": "Hello", "signals": {}}, {"exists": False, "facts": [], "gaps": []}, {})
        self.assertEqual(dx["overall"], "LOW")
        self.assertIn("limited public evidence", dx["summary"])


class BriefTests(unittest.TestCase):
    def test_report_includes_diagnosis_not_placeholders(self):
        dx = build_diagnosis(
            "describe",
            {"text": "whatsapp excel follow up", "signals": {"whatsapp_channel": True, "enquiry_form": True}},
            {"exists": True, "facts": ["Public WhatsApp enquiry/contact channel on the site."], "gaps": ["gap"]},
            {"state": "WhatsApp is the front door."},
        )
        brief = build_brief(
            "Alex",
            "",
            {"facts": ["Public WhatsApp enquiry/contact channel on the site."], "gaps": ["gap"]},
            {"observed_problem": dx["summary"], "automation_opportunity": dx["automate_first"]["reason"]},
            {"industry": "", "similar": [], "doing_it_right": []},
            emailed=False,
            channel={"state": "WhatsApp is the front door."},
            diagnosis=dx,
        )
        self.assertNotIn("sample brief", brief["html"].lower())
        self.assertNotIn("your space", brief["html"].lower())
        self.assertIn("BUSINESS OPERATIONS SNAPSHOT", brief["text"])
        self.assertIn("Alex", brief["html"])
        self.assertIn("Overall manual dependency", brief["html"])


class IndustryGuessTests(unittest.TestCase):
    def test_clinic_from_description(self):
        self.assertEqual(
            guess_industry("Alex", {"text": "Patients book dental appointments on WhatsApp"}, ""),
            "clinic",
        )

    def test_fragrance_not_salon(self):
        label = guess_industry(
            "Maison",
            {"text": "We manufacture perfume, cologne and fragrance oils for retailers in Nairobi."},
            "",
        )
        self.assertEqual(label, "fragrance and perfume brand")
        self.assertNotIn("salon", label)
        profile = industry_profile("Maison", {"text": "perfume fragrance"}, "")
        self.assertTrue(_on_topic("nairobi perfume house essential oils", profile))
        self.assertFalse(_on_topic("nairobi dental clinic appointments", profile))

    def test_fallback_is_not_a_service_agency(self):
        label = guess_industry("Alex", {"text": "we use excel"}, "")
        self.assertNotIn("agency", label)
        self.assertNotIn("clinic", label)


class PageFilterTests(unittest.TestCase):
    def test_skips_listicle(self):
        reason = should_skip_search_result(
            "https://example.com/blog/top-10-agencies",
            "Top 10 digital marketing agencies in Kenya",
            "Our list of the best agencies",
        )
        self.assertTrue(reason)


class VisitorResearchTests(unittest.TestCase):
    @patch("app.modules.research._public_mentions")
    @patch("app.modules.research._fetch_page")
    def test_mentions_are_merged_into_diagnosis_text(self, fetch, mentions):
        homepage = {
            "url": "https://ex.com/",
            "title": "Ex",
            "description": "",
            "text": "Message us on WhatsApp.",
            "html_sample": "",
            "emails": [],
            "email_records": [],
            "phones": [],
            "whatsapps": ["https://wa.me/254700000000"],
            "people": [],
            "links": ["/about"],
        }
        fetch.return_value = homepage
        mentions.return_value = [
            {
                "title": "Ex in Nairobi",
                "url": "https://news.example/ex",
                "snippet": "Customers call to book.",
                "host": "news.example",
            }
        ]
        result = visitor_research(1, "Ex Co", "https://ex.com", "")
        self.assertTrue(result["ok"])
        self.assertIn("PUBLIC MENTIONS", result["text"])
        self.assertIn("Customers call to book", result["text"])
        self.assertTrue(result["signals"].get("whatsapp_channel"))
        self.assertEqual(len(result["public_mentions"]), 1)

    def test_summary_notes_public_mentions(self):
        dx = build_diagnosis(
            "website",
            {
                "text": "whatsapp",
                "signals": {"whatsapp_channel": True},
                "public_mentions": [{"title": "News", "url": "https://n.example", "snippet": "x"}],
            },
            {"exists": True, "facts": [], "gaps": []},
            {},
        )
        self.assertIn("Public web mentions", dx["summary"])


class BookingTests(unittest.TestCase):
    def test_prefills_calendly_name_and_email(self):
        from app.booking import calendly_href, is_calendly

        href = calendly_href("https://calendly.com/northline/20min", "Alex", "alex@example.com")
        self.assertIn("calendly.com/northline/20min", href)
        self.assertIn("name=Alex", href)
        self.assertIn("email=alex%40example.com", href)
        self.assertTrue(is_calendly(href))

    def test_rejects_non_https(self):
        from app.booking import calendly_href

        self.assertEqual(calendly_href("javascript:alert(1)", "Alex", "a@b.com"), "")
        self.assertEqual(calendly_href("http://calendly.com/x", "Alex", "a@b.com"), "")


if __name__ == "__main__":
    unittest.main()
