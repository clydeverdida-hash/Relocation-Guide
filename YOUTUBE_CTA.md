# YouTube Call-to-Action Copy

Replace `[LANDING PAGE LINK]` with the tracked link for that video (see "Per-video links" below).

## Video description (put it in the first 2 lines so it shows above "...more")

```
🏔️ Thinking about moving to the Pacific Northwest? Download our FREE Relocation Guide to explore the area and prepare for your next move.
👉 Get your free copy here: [LANDING PAGE LINK]
```

## Pinned comment

```
Thinking about moving to the Pacific Northwest? 🌲 I put together a FREE Relocation Guide to help you explore the area, compare communities, and plan your move.
Grab your free copy here 👉 [LANDING PAGE LINK]
```

## Spoken CTA (end of video, ~15 seconds)

> "If you're thinking about moving to the Pacific Northwest, I made a free Relocation Guide that walks you through the area, the communities, and how to prepare for your move. The link is in the description and in the pinned comment. Go grab your free copy."

## Per-video links (UTM tracking)

Use a different `utm_content` for each video so you can see which videos bring in leads:

```
https://[YOUR-DOMAIN]/?utm_source=youtube&utm_medium=video&utm_campaign=relocation-guide&utm_content=[VIDEO-SLUG]
```

| Where the link goes | utm_medium | Example utm_content |
|---|---|---|
| Video description | `video` | `seattle-vs-portland` |
| Pinned comment | `pinned-comment` | `seattle-vs-portland` |
| Channel "About" / banner link | `channel` | `about-page` |
| Community post / Shorts | `community` or `shorts` | `shorts-rainy-days` |

Rules for `[VIDEO-SLUG]`: lowercase, hyphens instead of spaces, no special characters, under 50 characters. Example for the video "Cost of Living in Tacoma 2027": `cost-of-living-tacoma-2027`.

Each lead from that link gets the Lofty tag **`YT Video: cost-of-living-tacoma-2027`**, so filtering by that tag in Lofty shows how many leads that video produced.
