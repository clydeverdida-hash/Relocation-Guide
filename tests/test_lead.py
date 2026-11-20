"""
Unit tests for api/lead.py. Outside services are mocked; nothing is sent to Lofty or Resend.
Run:  python -m unittest discover -s tests -v
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api"))
import lead  # noqa: E402

BASE_ENV = {
    "LOFTY_API_KEY": "test-key",
    "RESEND_API_KEY": "re_test",
    "EMAIL_FROM": "Agent <guide@example.com>",
    "SITE_URL": "https://example.com",
    "NOTIFY_EMAIL": "agent@example.com",
    "DRY_RUN": "",
}
GOOD = {"fullName": "  Jane   Q Smith ", "email": "Jane@Example.com", "phone": "(206) 555-0142",
        "utm": {"utm_source": "youtube", "utm_campaign": "relocation-guide", "utm_content": "seattle-vs-portland"}}


class ValidationTests(unittest.TestCase):
    def test_valid(self):
        l, err = lead.validate(GOOD)
        self.assertEqual(err, {})
        self.assertEqual(l["fullName"], "Jane Q Smith")
        self.assertEqual(l["email"], "jane@example.com")
        self.assertFalse(l["marketingConsent"])

    def test_bad_inputs(self):
        ok_phone = "2065550142"
        for data in ({"fullName": "", "email": "a@b.co", "phone": ok_phone},
                     {"fullName": "A", "email": "a@b.co", "phone": ok_phone},
                     {"fullName": "Jane", "email": "nope", "phone": ok_phone},
                     {"fullName": "<script>", "email": "a@b.co", "phone": ok_phone},
                     {"fullName": "Jane", "email": "a@b", "phone": ok_phone},
                     {"fullName": "Jane", "email": "a@b.co", "phone": ""},
                     {"fullName": "Jane", "email": "a@b.co", "phone": "555-1234"},
                     {"fullName": "Jane", "email": "a@b.co", "phone": "123-456-7890"},
                     "notadict"):
            _, err = lead.validate(data)
            self.assertTrue(err, data)

    def test_old_form_without_phone_key_is_accepted(self):
        l, err = lead.validate({"fullName": "Jane Smith", "email": "jane@example.com"})
        self.assertEqual(err, {})
        self.assertEqual(l["phone"], "")

    def test_phone_normalization(self):
        n = lead.normalize_phone
        self.assertEqual(n("(206) 250-6197"), "+12062506197")
        self.assertEqual(n("206.250.6197"), "+12062506197")
        self.assertEqual(n("1-206-250-6197"), "+12062506197")
        self.assertEqual(n("+44 20 7946 0958"), "+442079460958")
        for bad in ("", "555-1234", "123-456-7890", "+12", "abc"):
            self.assertEqual(n(bad), "", bad)

    def test_split_and_tags(self):
        self.assertEqual(lead.split_name("Jane Q Smith"), ("Jane", "Q Smith"))
        self.assertEqual(lead.split_name("Cher"), ("Cher", ""))
        l, _ = lead.validate({**GOOD, "marketingConsent": True})
        self.assertEqual(lead.lead_tags(l), ["YouTube Relocation Guide", "Relocation",
                                             "Marketing Consent - Yes", "YT Video: seattle-vs-portland"])
        self.assertEqual(lead.lead_source({}), "YouTube")
        self.assertEqual(lead.lead_source({"utm_source": "instagram"}), "Instagram")


@mock.patch.dict(os.environ, BASE_ENV, clear=False)
class FlowTests(unittest.TestCase):
    def setUp(self):
        self.calls = []

    def fake_http(self, existing=None, fail_lofty=False, fail_email=False):
        def _f(method, url, headers, body=None, service="api", timeout=12):
            self.calls.append((method, url, headers, body))
            if service == "Lofty":
                if fail_lofty:
                    raise lead.ApiError("Lofty", 401, "bad token")
                if method == "GET":
                    return {"get_metadata": {}, "leads": [{"leadId": existing}] if existing else []}
                if method == "POST":
                    return {"leadId": 555}
                return {}
            if fail_email:
                raise lead.ApiError("Resend", 500, "down")
            return {"id": "email_1"}
        return _f

    def test_new_lead_created(self):
        with mock.patch.object(lead, "http_json", self.fake_http()):
            status, res = lead.process(GOOD)
        self.assertEqual((status, res), (200, {"ok": True}))
        get, post = self.calls[0], self.calls[1]
        self.assertIn("email=jane%40example.com", get[1])
        self.assertEqual(get[2]["Authorization"], "token test-key")
        self.assertEqual(post[0], "POST")
        self.assertEqual(post[1], "https://api.lofty.com/v1.0/leads")
        self.assertEqual(post[3]["firstName"], "Jane")
        self.assertEqual(post[3]["lastName"], "Q Smith")
        self.assertEqual(post[3]["emails"], ["jane@example.com"])
        self.assertEqual(post[3]["phones"], ["+12065550142"])
        self.assertEqual(post[3]["source"], "YouTube")
        self.assertEqual(post[3]["leadTypes"], [2])
        self.assertIs(post[3]["leadAlert"], True)
        # Guide tag is left off the create call and added right after, to fire Lofty's tag trigger.
        self.assertNotIn("YouTube Relocation Guide", post[3]["tags"])
        self.assertIn("Relocation", post[3]["tags"])
        put = self.calls[2]
        self.assertEqual(put[0], "PUT")
        self.assertTrue(put[1].endswith("/leads/555"))
        self.assertEqual(put[3], {"tagsAdd": ["YouTube Relocation Guide"]})
        self.assertIn("Marketing Consent - No", post[3]["tags"])
        emails = [c for c in self.calls if "resend" in c[1]]
        self.assertEqual([e[3]["to"] for e in emails], [["jane@example.com"], ["agent@example.com"]])

    def test_guide_tag_retries_until_lead_is_readable(self):
        attempts = {"put": 0}
        base = self.fake_http()
        def flaky(method, url, headers, body=None, service="api", timeout=12):
            if service == "Lofty" and method == "PUT":
                attempts["put"] += 1
                if attempts["put"] < 3:
                    self.calls.append((method, url, headers, body))
                    raise lead.ApiError("Lofty", 404, "not found yet")
            return base(method, url, headers, body, service, timeout)
        with mock.patch.object(lead, "http_json", flaky), mock.patch.object(lead.time, "sleep"):
            status, _ = lead.process(GOOD)
        self.assertEqual(status, 200)
        self.assertEqual(attempts["put"], 3)

    def test_old_form_lead_sent_without_phones(self):
        old = {k: v for k, v in GOOD.items() if k != "phone"}
        with mock.patch.object(lead, "http_json", self.fake_http()):
            status, _ = lead.process(old)
        self.assertEqual(status, 200)
        post = [c for c in self.calls if c[0] == "POST" and "lofty" in c[1]][0]
        self.assertNotIn("phones", post[3])

    def test_duplicate_only_adds_tags(self):
        with mock.patch.object(lead, "http_json", self.fake_http(existing=42)):
            status, _ = lead.process(GOOD)
        self.assertEqual(status, 200)
        lofty_calls = [c for c in self.calls if "lofty" in c[1]]
        self.assertEqual([c[0] for c in lofty_calls], ["GET", "PUT"])
        self.assertTrue(lofty_calls[1][1].endswith("/leads/42"))
        self.assertEqual(set(lofty_calls[1][3]), {"tagsAdd", "tagsRemove"})
        self.assertEqual(lofty_calls[1][3]["tagsRemove"], ["Marketing Consent - Yes"])

    def test_lofty_down_still_sends_guide(self):
        with mock.patch.object(lead, "http_json", self.fake_http(fail_lofty=True)):
            status, _ = lead.process(GOOD)
        self.assertEqual(status, 200)
        notify = [c for c in self.calls if "resend" in c[1]][-1]
        self.assertIn("FAILED", notify[3]["html"])

    def test_everything_down_returns_error(self):
        with mock.patch.object(lead, "http_json", self.fake_http(fail_lofty=True, fail_email=True)):
            status, res = lead.process(GOOD)
        self.assertEqual(status, 502)
        self.assertFalse(res["ok"])

    def test_honeypot_stores_nothing(self):
        with mock.patch.object(lead, "http_json", self.fake_http()):
            status, _ = lead.process({**GOOD, "website": "spam.com"})
        self.assertEqual(status, 200)
        self.assertEqual(self.calls, [])

    def test_invalid_makes_no_calls(self):
        with mock.patch.object(lead, "http_json", self.fake_http()):
            status, _ = lead.process({"fullName": "J", "email": "x"})
        self.assertEqual(status, 400)
        self.assertEqual(self.calls, [])

    def test_email_link_only_when_guide_ready(self):
        l, _ = lead.validate(GOOD)
        self.assertNotIn("download.html", lead.guide_email_html(l))
        with mock.patch.dict(os.environ, {"GUIDE_READY": "true"}):
            self.assertIn("https://example.com/download.html?src=email", lead.guide_email_html(l))

    def test_html_escaped(self):
        l, _ = lead.validate({**GOOD, "utm": {"utm_content": "<b>x</b>"}})
        self.assertNotIn("<b>x</b>", lead.notify_email_html(l, "ok"))


if __name__ == "__main__":
    unittest.main()
