# YouTube Relocation Guide Funnel

A landing page that collects **Full Name + Email** in exchange for a free Pacific Northwest Relocation Guide, puts each lead in **Lofty**, and emails the guide.

```
YouTube video ──(UTM link)──> index.html ──form──> /api/lead ──> Lofty (create, or tag if duplicate)
                                                       ├──> guide email to visitor (Resend)
                                                       └──> "new lead" copy to agent (Resend)
                              thank-you.html ──> download.html ──> PDF   (download counted in GA4)
```

## Status (read before going live)

| Piece | Status |
|---|---|
| Landing, thank-you, download and privacy pages | Built. Tested locally in a browser. |
| Form validation, spam trap, thank-you redirect | Built. Tested locally. |
| Lofty integration | **Tested live on 2026-11-18** at https://relocation-guide-tau.vercel.app: a test submission created a Lofty lead (Source YouTube, type Buyer, owner Dion, all tags, tracking note), and resubmitting the same email updated that lead instead of duplicating it. |
| Guide email + agent notification | Code written for Resend. **NOT yet tested with real sending.** Needs a Resend account and a verified sending domain. |
| Relocation Guide PDF | Placeholder. Waiting on the client. |
| Logo, headshot, contact info | Placeholders in `public/assets/config.js`. |

## Files

```
public/
  index.html          landing page
  thank-you.html      confirmation page
  download.html       counts the download, then opens the PDF
  privacy.html        privacy policy TEMPLATE (client should review)
  assets/config.js    ← all client details, logo, PDF path, GA4 ID go here
  assets/styles.css, app.js, pnw-scene.svg (placeholder scenery)
  assets/guide/       ← put the PDF (and an optional cover.jpg) here
api/lead.py           form handler (Vercel serverless function, Python standard library only)
tests/test_lead.py    unit tests (no outside calls)
dev_server.py         local preview
YOUTUBE_CTA.md        description / pinned comment copy + per-video tracking links
TRACKING.md           how to see downloads, leads, and leads per video
```

## Why this stack

Lofty's own landing-page builder can't do per-video tracking or custom design, and Zapier adds a monthly cost and another moving part. A static page plus one small function on **Vercel (free tier)** is the simplest setup that talks to Lofty directly, keeps the API key secret, and has nothing to maintain.

## Preview locally

```bash
python dev_server.py
```

Open http://localhost:8080. This runs in DRY_RUN mode: submissions are validated and printed in the console, and nothing is sent to Lofty or by email.

```bash
python -m unittest discover -s tests -v
```

## What's needed from the client

1. **Lofty API key.** In Lofty go to **Settings → Integrations → API** and generate a key. It must belong to a user allowed to create leads. Optional: the Lofty **user ID** new leads should be assigned to. Without it, Lofty's normal lead-routing rules apply.
2. **Lead type decision.** Lofty's lead types are fixed (Buyer, Seller, Renter, Investor, …). There is **no "Relocation" type**, so "Relocation" is sent as a **tag**, and the type defaults to **Buyer** (`LOFTY_LEAD_TYPE=2`). Change it if the client prefers.
3. **A domain or subdomain** for the page, e.g. `relocate.theirdomain.com`.
4. **Email sending.** A free [Resend](https://resend.com) account with that domain verified (DNS records), plus the "from" address, e.g. `guide@theirdomain.com`.
5. **The guide PDF**, the logo, an agent headshot, and the contact details.
6. Optional: a **Google Analytics 4** measurement ID.

## Deploy (Vercel)

1. Put this folder in a GitHub repo, then in Vercel choose **Add New → Project** and import it. Framework preset: **Other**. Vercel serves `public/` and turns `api/lead.py` into `/api/lead`.
2. Under **Settings → Environment Variables**, add:

| Variable | Example |
|---|---|
| `LOFTY_API_KEY` | (from Lofty) |
| `LOFTY_LEAD_TYPE` | `2` (Buyer). Comma-separate for several. |
| `LOFTY_ASSIGNED_USER_ID` | optional |
| `RESEND_API_KEY` | `re_...` |
| `EMAIL_FROM` | `Jane Agent <guide@theirdomain.com>` |
| `EMAIL_REPLY_TO` | `jane@theirdomain.com` |
| `NOTIFY_EMAIL` | agent inbox for a copy of each new lead |
| `SITE_URL` | `https://relocate.theirdomain.com` |
| `AGENT_NAME` | `Jane Agent, Brokerage` |
| `GUIDE_READY` | `false` until the PDF is uploaded, then `true` |

3. Add the custom domain under **Settings → Domains**.

## Adding the PDF when it arrives

1. Save it as `public/assets/guide/PNW-Relocation-Guide.pdf`. Optionally save the cover image as `public/assets/guide/cover.jpg` and add `<img src="assets/guide/cover.jpg" alt="">` inside `.guide-mock` in `index.html`.
2. In `public/assets/config.js`, set `guidePdf: "assets/guide/PNW-Relocation-Guide.pdf"`.
3. In Vercel, set `GUIDE_READY=true` and redeploy.
4. Leads who signed up before the PDF existed were told it's coming. In Lofty, filter by tag `YouTube Relocation Guide` and send them the link `https://[domain]/download.html?src=email`.

The PDF sits at a public but unlisted URL. That's normal for lead magnets and keeps the funnel simple.

## How submissions are handled

- **Validation** happens in the browser and again on the server: name 2–80 characters, a real-looking email. A hidden "honeypot" field silently drops bots.
- **New email:** creates a Lofty lead with first/last name, email, Source `YouTube`, lead type, a note with the UTM details, and these tags:
  - `YouTube Relocation Guide`
  - `Relocation`
  - `Marketing Consent - Yes` or `Marketing Consent - No`
  - `YT Video: <utm_content>` (when present)
- **Existing email (duplicate):** looks the lead up by email (`GET /v1.0/leads?email=`) and only **adds** those tags (`PUT /v1.0/leads/{id}` with `tagsAdd`). It doesn't overwrite the name, source, stage or agent, and it doesn't create a second lead.
- **If Lofty is down**, the visitor still gets the guide, and the agent's notification email says `Lofty: FAILED …` so the lead can be entered by hand. The error is also in Vercel's function logs.

## Email consent

- The guide email is sent because the visitor asked for it.
- The marketing checkbox is **optional and unchecked by default**. Visitors who leave it unchecked get the tag `Marketing Consent - No`. **In Lofty, exclude that tag from any newsletter, listing-alert or nurture Smart Plan.** The page doesn't unsubscribe them in Lofty, so the agent can still reply to their questions.

## Lofty integration test checklist (do this once the API key is in)

1. Deploy with real env vars and submit the form with a test name/email you control.
2. In Lofty, confirm the lead exists with the correct name, email, Source = YouTube, lead type, the 3–4 tags and the note.
3. Submit **the same email again**. Confirm there's still **one** lead and no duplicate.
4. Confirm the guide email arrived (check spam) and the agent notification arrived.
5. Delete the test lead in Lofty.

Only call the integration "working" after steps 2–4 pass. A few API details aren't covered in Lofty's docs, and this test checks them: whether the `content` note is saved on create, and how Lofty's own duplicate check behaves.

## Fallback: Zapier instead of the API

If the API key can't be used, Zapier's Lofty app has a **Create Lead** action. Point the form at a Zapier "Catch Hook" webhook instead of `/api/lead` (change the `fetch` URL in `assets/app.js`). Then map Name, Email, Source = YouTube and the tags in Zapier, and add a Gmail/Outlook step for the guide email. This needs a paid Zapier plan (multi-step zap) and loses the duplicate check unless a "Find Lead" step is added.
