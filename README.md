# EU Pay Transparency Directive Tracker

A single-page, static web utility showing the implementation status of
**Directive (EU) 2023/970** (the EU Pay Transparency Directive) across all
27 member states — traffic-light status, a one-to-two sentence explanation,
expected dates, and links to official sources.

No backend, no database, no authentication. Just three files that matter:

```
index.html                    the app (self-contained UI, fetches data.json)
data.json                     canonical data — the only file that changes
sources.json                  official watch URLs for the update monitor
scripts/update.py             automated refresh + change detection
.github/workflows/update.yml  scheduled runner (GitHub Actions)
netlify.toml                  Netlify config (site + counter function)
netlify/functions/visits.mjs  visit counter (Netlify Blobs, optional)
package.json                  declares @netlify/blobs for the counter
```

## Deploy in one minute

**Netlify (recommended):** drag the folder onto https://app.netlify.com/drop,
or connect the GitHub repo — Netlify auto-deploys every commit, including the
automated data refreshes. No build step.

**GitHub Pages:** Settings → Pages → deploy from branch → root.

**Any web server:** upload the files. `index.html` must be served over HTTP(S)
so it can fetch `data.json`; opened directly from disk it falls back to an
embedded snapshot and says so in the footer.

## How updates work

The design deliberately keeps a human in the loop for anything legal:

1. **Scheduled monitor** (weekday mornings, GitHub Actions) runs
   `scripts/update.py`, which:
   - checks the **EUR-Lex national transposition measures page** (structured,
     official) for new notified measures per country;
   - runs **change detection** on any official watch URLs listed in
     `sources.json` (content-hash comparison, noise-stripped);
   - refreshes `lastChecked` per country and `lastGlobalRefresh` globally,
     and commits `data.json` — so the site always shows when it was verified.
2. **When a change is detected**, the country is flagged
   `reviewNeeded: true` and a GitHub issue is opened automatically.
3. **Optional AI summarisation:** if the `ANTHROPIC_API_KEY` repo secret is
   set, Claude drafts a 1–2 sentence summary *of the fetched official text
   only*, written to `proposedSummary`. **AI never sets or changes a
   country's `status`, and never overwrites the published `summary`** — a
   human verifies the official source and edits `status`, `summary`,
   `expectedDate` and `lastUpdated` by hand, then deletes the proposal.
4. Existing official source links in `data.json` are always preserved.

To improve monitoring, add stable official URLs (ministry pages, gazette
search pages, parliament bill trackers) to `sources.json` per country.
Official sources only — no blogs, vendors, or law-firm trackers.

## Editing a country by hand

Edit its entry in `data.json`:

```json
{
  "code": "FR",
  "status": "implemented | in_progress | not_yet",
  "summary": "One or two sentences, plain language.",
  "expectedDate": "2027-01-01 or free text or null",
  "lastUpdated": "YYYY-MM-DD",
  "sources": [{ "label": "...", "url": "https://official-source" }]
}
```

Commit; the site redeploys automatically.

## Data policy

- Statuses derive from official publications (EUR-Lex, European Commission,
  national governments, ministries, parliaments, official gazettes).
- Every country links to at least one official source.
- Traffic-light meanings: 🟢 final national law in force · 🟡 draft
  published, partial transposition or formal process underway · 🔴 no
  published draft, or process paused.
- This is an informational overview, not legal advice.

## Visit counter

The "Visits" pill is powered by a tiny Netlify Function backed by Netlify
Blobs — no database, no third-party analytics. Netlify installs
`@netlify/blobs` automatically at deploy (declared in `package.json`).
Counting is once per browser session (sessionStorage-deduplicated). On any
host that isn't Netlify (GitHub Pages, plain server, local file), the badge
simply stays hidden — everything else works unchanged.

## Costs

Hosting: free tier (Netlify/GitHub Pages/Cloudflare Pages).
Automation: free (GitHub Actions minutes).
Optional AI summarisation: a few cents per detected change, only if enabled.
