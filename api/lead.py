"""
POST /api/lead : receives the Relocation Guide form and
  1. validates name + email,
  2. creates the lead in Lofty, or adds tags if a lead with that email already exists,
  3. emails the visitor their guide link (via Resend),
  4. emails the agent a "new lead" notice (backup copy of every submission).

Runs as a Vercel Python serverless function (class `handler`). Uses only the Python
standard library. Lofty endpoints come from https://developer.lofty.com (Leads API, v1.0).

Environment variables (set in Vercel > Project > Settings > Environment Variables):
  LOFTY_API_KEY          required  Lofty: Settings > Integrations > API
  LOFTY_LEAD_TYPE        optional  Lofty lead type id(s), comma separated. Default "2" (Buyer).
                                   Lofty has no "Relocation" type, so "Relocation" is sent as a tag.
  LOFTY_ASSIGNED_USER_ID optional  Assign new leads to this Lofty user id (skips routing rules).
  RESEND_API_KEY         required for email   https://resend.com
  EMAIL_FROM             required for email   e.g. "Jane Agent <guide@yourdomain.com>" (domain verified in Resend)
  EMAIL_REPLY_TO         optional  where visitor replies go
  NOTIFY_EMAIL           optional  agent inbox that gets a copy of every new lead
  SITE_URL               required  e.g. https://relocate.yourdomain.com (no trailing slash)
  GUIDE_READY            "true" once the PDF is uploaded and set in public/assets/config.js
  AGENT_NAME             optional  used in the email signature
  DRY_RUN                "true" = validate and log only, call no outside service (for testing)
"""

import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler

LOFTY_BASE = "https://api.lofty.com/v1.0"
RESEND_URL = "https://api.resend.com/emails"
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")
UTM_KEYS = ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term")

TAG_GUIDE = "YouTube Relocation Guide"
TAG_RELOCATION = "Relocation"
TAG_CONSENT_YES = "Marketing Consent - Yes"
TAG_CONSENT_NO = "Marketing Consent - No"


def env(name, default=""):
    return os.environ.get(name, default).strip()


def log(*parts):
    print("[lead]", *parts, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- validation
def clean_text(value, limit):
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    return value[:limit]


def validate(data):
    """Return (lead_dict, errors_dict)."""
    errors = {}
    if not isinstance(data, dict):
        return None, {"form": "Invalid request."}
    name = clean_text(data.get("fullName"), 120)
    email = clean_text(data.get("email"), 300).lower()
    if len(name) < 2 or len(name) > 80:
        errors["fullName"] = "Please enter your full name."
    elif re.search(r"[<>{}]|https?://", name, re.I):
        errors["fullName"] = "Please enter your full name."
    if not EMAIL_RE.match(email) or len(email) > 254:
        errors["email"] = "Please enter a valid email address."
    # The current form always sends "phone". A browser still showing an older copy of the page
    # (opened before the phone field existed) sends no "phone" key at all; accept that lead
    # without a number rather than showing an error the visitor can't fix.
    phone = ""
    if "phone" in data:
        phone = normalize_phone(data.get("phone"))
        if not phone:
            errors["phone"] = "Please enter a valid phone number."

    utm_in = data.get("utm") if isinstance(data.get("utm"), dict) else {}
    utm = {k: clean_text(utm_in.get(k), 100) for k in UTM_KEYS if utm_in.get(k)}

    lead = {
        "fullName": name,
        "email": email,
        "phone": phone,
        "marketingConsent": data.get("marketingConsent") is True,
        "utm": utm,
        "honeypot": clean_text(data.get("website"), 200),
    }
    return lead, errors


def normalize_phone(raw):
    """US numbers in any format -> +1XXXXXXXXXX; international numbers must start with +."""
    value = str(raw or "").strip()
    digits = re.sub(r"\D", "", value)
    if value.startswith("+"):
        return "+" + digits if 8 <= len(digits) <= 15 else ""
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return "+1" + digits if len(digits) == 10 and digits[0] in "23456789" else ""


def split_name(full):
    parts = full.split(" ", 1)
    first = parts[0][:30]
    last = parts[1][:30] if len(parts) > 1 else ""
    return first, last


def lead_source(utm):
    src = (utm.get("utm_source") or "").lower()
    if not src or "youtube" in src or src in ("yt", "youtu.be"):
        return "YouTube"
    return utm["utm_source"][:40].title()


def lead_tags(lead):
    tags = [TAG_GUIDE, TAG_RELOCATION, TAG_CONSENT_YES if lead["marketingConsent"] else TAG_CONSENT_NO]
    video = lead["utm"].get("utm_content")
    if video:
        tags.append(("YT Video: " + video)[:64])
    return tags


# ---------------------------------------------------------------- HTTP helper
class ApiError(Exception):
    def __init__(self, service, status, body):
        super().__init__(f"{service} HTTP {status}: {body[:300]}")
        self.status = status


def http_json(method, url, headers, body=None, service="api", timeout=12):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in headers.items():
        req.add_header(k, v)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8") or "{}"
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        raise ApiError(service, e.code, e.read().decode("utf-8", "replace"))


# ---------------------------------------------------------------- Lofty
def lofty(method, path, body=None, query=None):
    url = LOFTY_BASE + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    headers = {"Authorization": "token " + env("LOFTY_API_KEY")}
    return http_json(method, url, headers, body, service="Lofty")


def find_lofty_lead(email):
    res = lofty("GET", "/leads", query={"email": email, "limit": 5})
    for item in res.get("leads") or []:
        if item.get("leadId"):
            return item["leadId"]
    return None


def upsert_lofty_lead(lead):
    """Create the lead, or add our tags to the existing one. Returns (action, leadId)."""
    tags = lead_tags(lead)
    existing = find_lofty_lead(lead["email"])
    if existing:
        # Duplicate: keep the existing record (source, stage, owner, tags) and only add our tags.
        # Swap the consent tag so a lead never carries both "Yes" and "No".
        stale = TAG_CONSENT_NO if lead["marketingConsent"] else TAG_CONSENT_YES
        lofty("PUT", f"/leads/{int(existing)}", body={"tagsAdd": tags, "tagsRemove": [stale]})
        return "updated", existing

    first, last = split_name(lead["fullName"])
    body = {
        "firstName": first,
        "emails": [lead["email"]],
        "source": lead_source(lead["utm"]),
        # The guide tag is added in a second call (below) so Lofty sees a "tag added" event,
        # which is what triggers the "YouTube Relocation Guide - Guide Delivery" Smart Plan.
        "tags": [t for t in tags if t != TAG_GUIDE],
        # Lofty emails the assigned agent (Dion) about the new lead. Turn off with LOFTY_LEAD_ALERT=false.
        "leadAlert": env("LOFTY_LEAD_ALERT", "true").lower() != "false",
    }
    if lead.get("phone"):
        body["phones"] = [lead["phone"]]
    if last:
        body["lastName"] = last
    lead_types = [int(x) for x in env("LOFTY_LEAD_TYPE", "2").split(",") if x.strip().lstrip("-").isdigit()]
    if lead_types:
        body["leadTypes"] = lead_types
    if env("LOFTY_ASSIGNED_USER_ID").isdigit():
        body["assignedUserId"] = int(env("LOFTY_ASSIGNED_USER_ID"))
    if lead["utm"]:
        body["content"] = "Relocation Guide request. Tracking: " + ", ".join(
            f"{k}={v}" for k, v in lead["utm"].items()
        )
    res = lofty("POST", "/leads", body=body)
    lead_id = res.get("leadId")
    if lead_id:
        add_tag_with_retry(lead_id, TAG_GUIDE)
    return "created", lead_id


def add_tag_with_retry(lead_id, tag, attempts=4, wait_seconds=1.0):
    """Lofty returns the new leadId before the lead is readable, so the first update can 404."""
    for attempt in range(attempts):
        try:
            lofty("PUT", f"/leads/{int(lead_id)}", body={"tagsAdd": [tag]})
            return True
        except ApiError as e:
            if e.status != 404 or attempt == attempts - 1:
                log("Could not add tag", tag, "to lead", lead_id, ":", e)
                return False
            time.sleep(wait_seconds)
    return False


# ---------------------------------------------------------------- Email (Resend)
def send_email(to, subject, html_body, reply_to=None):
    payload = {"from": env("EMAIL_FROM"), "to": [to], "subject": subject, "html": html_body}
    if reply_to:
        payload["reply_to"] = reply_to
    headers = {"Authorization": "Bearer " + env("RESEND_API_KEY")}
    return http_json("POST", RESEND_URL, headers, payload, service="Resend")


def guide_email_html(lead):
    first = html.escape(split_name(lead["fullName"])[0])
    agent = html.escape(env("AGENT_NAME", "Your Pacific Northwest Real Estate Team"))
    site = env("SITE_URL").rstrip("/")
    if env("GUIDE_READY").lower() == "true":
        body = (
            f'<p>Here is your free Pacific Northwest Relocation Guide:</p>'
            f'<p><a href="{html.escape(site)}/download.html?src=email" '
            f'style="display:inline-block;background:#b8673a;color:#fff;padding:14px 22px;'
            f'border-radius:8px;text-decoration:none;font-weight:bold">Download My Guide</a></p>'
        )
    else:
        body = "<p>Your guide is being finalized, and we'll send it to this address as soon as it's ready.</p>"
    return (
        '<div style="font-family:Arial,sans-serif;font-size:16px;line-height:1.6;color:#1d2523;max-width:560px">'
        f"<p>Hi {first},</p>"
        "<p>Thank you for requesting our Relocation Guide! We're excited to help you explore your next move.</p>"
        f"{body}"
        "<p>When you're ready, book a free 30-minute Zoom relocation planning call: "
        '<a href="https://calendly.com/dkjrealtors/30min">calendly.com/dkjrealtors/30min</a>. '
        "Questions about a specific town or neighborhood? Just reply to this email.</p>"
        f"<p>Warm regards,<br>{agent}</p>"
        '<p style="font-size:12px;color:#5d6b67">You received this email because you requested the '
        "Relocation Guide on our website.</p></div>"
    )


def notify_email_html(lead, lofty_result):
    rows = [
        ("Name", lead["fullName"]),
        ("Email", lead["email"]),
        ("Phone", lead.get("phone", "")),
        ("Marketing consent", "Yes" if lead["marketingConsent"] else "No"),
        ("Lofty", lofty_result),
    ] + [(k, v) for k, v in lead["utm"].items()]
    cells = "".join(
        f"<tr><td style='padding:4px 12px 4px 0'><b>{html.escape(k)}</b></td><td>{html.escape(str(v))}</td></tr>"
        for k, v in rows
    )
    return f"<p>New YouTube Relocation Guide lead:</p><table>{cells}</table>"


# ---------------------------------------------------------------- main flow
def process(data):
    """Returns (http_status, response_dict). Pure function apart from outbound calls."""
    lead, errors = validate(data)
    if errors:
        return 400, {"ok": False, "error": next(iter(errors.values())), "fields": errors}

    if lead["honeypot"]:
        log("honeypot filled, ignoring submission")
        return 200, {"ok": True}  # look successful to the bot, store nothing

    if env("DRY_RUN").lower() == "true":
        log("DRY_RUN lead:", json.dumps({**lead, "tags": lead_tags(lead), "source": lead_source(lead["utm"])}))
        return 200, {"ok": True, "dryRun": True, "tags": lead_tags(lead), "source": lead_source(lead["utm"])}

    crm_ok = email_ok = False
    lofty_result = "not configured"
    if env("LOFTY_API_KEY"):
        try:
            action, lead_id = upsert_lofty_lead(lead)
            lofty_result = f"{action} lead {lead_id}"
            crm_ok = True
            log("Lofty", lofty_result)
        except Exception as e:  # keep going so the visitor still gets the guide
            lofty_result = f"FAILED: {e}"
            log("Lofty error:", e, "| lead:", lead["fullName"], lead["email"])

    if env("RESEND_API_KEY") and env("EMAIL_FROM"):
        try:
            send_email(
                lead["email"],
                "Your Pacific Northwest Relocation Guide",
                guide_email_html(lead),
                reply_to=env("EMAIL_REPLY_TO") or None,
            )
            email_ok = True
        except Exception as e:
            log("Guide email error:", e)
        if env("NOTIFY_EMAIL"):
            try:
                send_email(env("NOTIFY_EMAIL"), "New lead: Relocation Guide (" + lead["fullName"] + ")",
                           notify_email_html(lead, lofty_result))
            except Exception as e:
                log("Notify email error:", e)

    if not crm_ok and not email_ok:
        return 502, {"ok": False, "error": "We couldn't process your request right now."}
    return 200, {"ok": True}


class handler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length > 10_000:
                return self._send(413, {"ok": False, "error": "Request too large."})
            data = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._send(400, {"ok": False, "error": "Invalid request."})
        status, payload = process(data)
        self._send(status, payload)

    def do_GET(self):
        self._send(405, {"ok": False, "error": "Use POST."})
