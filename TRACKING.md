# Lead Tracking

## The three numbers

| Metric | Where to look |
|---|---|
| **Total names & emails collected** | Lofty → People → filter by tag **`YouTube Relocation Guide`**. The count is the number of unique leads (duplicates are merged). |
| **Leads generated from YouTube** | Lofty → People → filter **Source = YouTube** *and* tag `YouTube Relocation Guide`. Or in GA4 → Reports → Engagement → Events → `generate_lead`, broken down by **Session source**. |
| **Total guide downloads** | GA4 → Events → **`guide_download`**. The `method` parameter shows `email` (clicked the email link) or `web` (clicked the thank-you page button). |

**Leads per video:** in Lofty, filter by tag `YT Video: <video-slug>`. In GA4, open the `generate_lead` event and add the **Session manual ad content** dimension (that's `utm_content`).

## Setting up GA4 (5 minutes)

1. At analytics.google.com, create a GA4 property and a **Web** data stream for the landing page domain.
2. Copy the Measurement ID (`G-XXXXXXXXXX`) into `ga4Id` in `public/assets/config.js` and redeploy.
3. In GA4 → Admin → Events, mark **`generate_lead`** as a **Key event** (conversion).
4. To use the event parameters in reports, go to Admin → Custom definitions and add event-scoped dimensions **`video`**, **`campaign`**, **`lead_source`** and **`method`**.

GA4 can take 24–48 hours to show new events in standard reports. Use **Realtime** to check right after setup.

## Events sent by the page

| Event | When | Parameters |
|---|---|---|
| `page_view` | every page (automatic) | UTM params are picked up automatically |
| `generate_lead` | form submitted successfully | `form`, `lead_source`, `campaign`, `video` |
| `guide_download` | download page opened, PDF served | `method` = `email` / `web` |

## Notes

- UTM values are saved for the browser session, so a visitor who lands with a UTM link, reads the privacy page, and then submits is still credited to the right video.
- Visitors who arrive from youtube.com **without** UTM parameters are still counted as source `youtube` (detected from the referrer), but without a video name. That's why per-video UTM links matter (see `YOUTUBE_CTA.md`).
- The agent's "new lead" notification email lists the UTM values for every lead, which serves as a second record.
