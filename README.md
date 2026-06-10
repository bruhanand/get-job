# get-job 🛰️

A self-contained **remote-job scraper + application tracker**. One Python process, one SQLite
file, zero paid APIs, zero API keys, zero accounts — every listing comes from public,
unauthenticated JSON/RSS feeds.

## Features

- **Job Scraper Dashboard** — aggregates remote jobs from 8 public sources with a
  *Scrape Now* button, search (title/company), date-posted filter, source filter, and sorting.
- **Resume Match Scoring** — paste your resume + skills in the *Profile* tab; every listing
  gets a 0–100% match score from a pure-Python, IDF-weighted keyword-overlap algorithm
  (stdlib only — no ML deps, no external AI). Matched keywords are shown so scores are explainable.
- **Manual Job Tracker** — Kanban board (*To Apply → Applied → Interviewing → Offer →
  Rejected*) with drag-and-drop **and** a per-card status dropdown. Fields: title, company,
  salary range, URL, notes, date applied.
- **Quick Save** — a *Track This Job* button on every scraped listing clones it onto the
  board under *To Apply* (duplicates detected).
- **Application Analytics** — Chart.js dashboard: applications over time (zero-filled
  timeline), interview-conversion %, offer rate, and a status-breakdown doughnut.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
# open http://127.0.0.1:5000
```

On first run the profile is seeded from `seed/resume.txt` (replace it with your own, or just
edit the Profile tab). The SQLite DB (`jobs.db`) is created next to `app.py`.

Run the (network-free) test suite:

```bash
python -m tests.test_app
```

## Job sources & polite-use etiquette

All sources are free and keyless. The scraper honors per-source cooldowns so *Scrape Now*
never hammers anyone, sends a browser `User-Agent` (several feeds bot-block the default
`python-requests` UA), and degrades per source — a failed feed shows an error chip while the
rest still load.

| Source | Endpoint | Notes |
|---|---|---|
| Remote OK | `remoteok.com/api` | JSON; ToS require naming Remote OK + direct link back (the UI does both); feed ~24 h delayed; Cloudflare-fronted |
| We Work Remotely | `weworkremotely.com/remote-jobs.rss` | RSS 2.0; attribution requested |
| Remotive | `remotive.com/api/remote-jobs` | JSON; ≤ 4 pulls/day advised, > 2/min blocked → 6 h cooldown; attribution required |
| Jobicy | `jobicy.com/api/v2/remote-jobs` | JSON; ≤ 1 check/hour requested → 1 h cooldown; link-back attribution |
| Himalayas | `himalayas.app/jobs/api` | JSON; `limit` capped at 20/request |
| Arbeitnow | `arbeitnow.com/api/job-board-api` | JSON; EU-heavy board — non-remote rows are filtered out |
| Working Nomads | `workingnomads.com/api/exposed_jobs/` | JSON flat array |
| Hacker News | `hn.algolia.com/api/v1/search_by_date?tags=job` | Algolia HN Search (10 k req/h/IP), falls back to the official Firebase API (`/v0/jobstories.json`) |

If a source returns HTTP 403/429 (anti-bot, rate limit, or a restricted network), the app
reports it per source and keeps running — nothing crashes.

## Stack

- **Backend:** Flask + SQLAlchemy 2 (SQLite), `requests` + BeautifulSoup/`xml.etree` for
  feed parsing. No background workers — scraping runs on demand.
- **Frontend:** single HTML page, Tailwind CSS v4 (browser build) + Chart.js 4 — both
  **vendored locally** in `static/vendor/`, so the UI works fully offline.
- **Matching:** `matcher.py` — tech-aware tokenizer (keeps `c++`, `node.js`, `ci/cd`, …),
  unigrams + bigrams, corpus IDF weighting, title/tag boost, explicit skills count double.

## Layout

```
app.py            Flask routes (jobs, scrape, tracker, profile, analytics)
scraper.py        8 feed fetchers + cooldown-aware scrape_all()
matcher.py        resume ↔ job match scoring (pure stdlib)
models.py         SQLAlchemy models: ScrapedJob, TrackedJob, Profile, SourceState
templates/        index.html (single-page dashboard)
static/           app.js, app.css, vendored tailwind.js + chart.umd.js
seed/resume.txt   initial profile text (replace with yours)
tests/            stdlib-only suite with fixture-mocked feeds
```
