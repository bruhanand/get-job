"""Scrapers for free, public, keyless remote-job feeds (no paid APIs, no auth).

Sources and polite-use etiquette (verified against official docs, June 2026):

- Remote OK         https://remoteok.com/api                      JSON; legal notice requires naming
                    Remote OK + direct link back; feed ~24h delayed; browser UA required (Cloudflare).
- We Work Remotely  https://weworkremotely.com/remote-jobs.rss    RSS 2.0; attribution requested.
- Remotive          https://remotive.com/api/remote-jobs          JSON; advises <= 4 pulls/day and blocks
                    > 2 req/min, hence the 6h cooldown; attribution (link + name Remotive) required.
- Jobicy            https://jobicy.com/api/v2/remote-jobs         JSON; asks <= 1 check/hour; link back.
- Himalayas         https://himalayas.app/jobs/api                JSON; limit capped at 20/request.
- Arbeitnow         https://www.arbeitnow.com/api/job-board-api   JSON; EU-heavy, filter remote==true.
- Working Nomads    https://www.workingnomads.com/api/exposed_jobs/  JSON flat array.
- Hacker News       https://hn.algolia.com/api/v1/search_by_date?tags=job  (10k req/h limit), with the
                    official Firebase API (/v0/jobstories.json) as fallback — both keyless, no rate limit
                    documented on Firebase.

Every fetcher returns a list of normalized dicts; scrape_all() upserts them and
NEVER raises: timeouts, HTTP 403/429, and parse errors are captured per source
so one broken feed can't take down the rest.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

import requests
from bs4 import BeautifulSoup
from sqlalchemy import select

from models import ScrapedJob, SessionLocal, SourceState

HEADERS = {
    # Default python-requests UA is widely bot-blocked; use a realistic browser UA.
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Accept": "application/json, application/rss+xml, text/xml;q=0.9, */*;q=0.8",
    "Accept-Language": "en-US,en;q=0.8",
}
TIMEOUT = 25
MAX_DESC = 20000


def _get(url: str, **kwargs) -> requests.Response:
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, **kwargs)
    resp.raise_for_status()
    return resp


def strip_html(markup: str) -> str:
    if not markup:
        return ""
    text = BeautifulSoup(markup, "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text)[:MAX_DESC]


def _from_epoch(value) -> datetime | None:
    try:
        return datetime.utcfromtimestamp(float(value))
    except (TypeError, ValueError, OSError):
        return None


def _from_iso(value) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.replace(tzinfo=None) if dt.tzinfo else dt
    except ValueError:
        try:
            return datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None


def _fmt_salary(lo, hi, unit: str = "$") -> str:
    def num(v):
        try:
            v = float(v)
            return v if v > 0 else None
        except (TypeError, ValueError):
            return None

    lo, hi = num(lo), num(hi)

    def k(n: float) -> str:
        return f"{unit}{n / 1000:g}k" if n >= 1000 else f"{unit}{n:g}"

    if lo and hi:
        return f"{k(lo)} – {k(hi)}"
    if lo:
        return f"from {k(lo)}"
    if hi:
        return f"up to {k(hi)}"
    return ""


# ------------------------------------------------------------- fetchers ---


def fetch_remoteok() -> list[dict]:
    data = _get("https://remoteok.com/api").json()
    jobs = []
    for row in data:
        # First element is the API legal notice / metadata, not a job.
        if not isinstance(row, dict) or not row.get("id") or not (row.get("position") or row.get("title")):
            continue
        jobs.append(
            {
                "external_id": str(row["id"]),
                "title": row.get("position") or row.get("title") or "",
                "company": row.get("company") or "",
                "location": row.get("location") or "Remote",
                "salary": _fmt_salary(row.get("salary_min"), row.get("salary_max")),
                "tags": [t for t in (row.get("tags") or []) if isinstance(t, str)],
                "description": strip_html(row.get("description") or ""),
                # ToS: direct link back to the listing on Remote OK, no redirects.
                "url": row.get("url") or "",
                "posted_at": _from_epoch(row.get("epoch")) or _from_iso(row.get("date")),
            }
        )
    return jobs


def fetch_weworkremotely() -> list[dict]:
    root = ET.fromstring(_get("https://weworkremotely.com/remote-jobs.rss").content)
    jobs = []
    for item in root.iter("item"):
        get = lambda tag: (item.findtext(tag) or "").strip()  # noqa: E731
        title = get("title")
        company, _, position = title.partition(": ")
        if not position:  # no "Company: Position" pattern
            company, position = "", title
        link = get("link")
        guid = get("guid") or link
        tags = [t for t in (get("category"), get("type")) if t]
        jobs.append(
            {
                "external_id": guid,
                "title": position,
                "company": company,
                "location": get("region") or "Remote",
                "salary": "",
                "tags": tags,
                "description": strip_html(get("description")),
                "url": link,
                "posted_at": _parse_rfc822(get("pubDate")),
            }
        )
    return jobs


def _parse_rfc822(value: str) -> datetime | None:
    try:
        dt = parsedate_to_datetime(value)
        return dt.replace(tzinfo=None) if dt.tzinfo else dt
    except (TypeError, ValueError):
        return None


def fetch_remotive() -> list[dict]:
    data = _get("https://remotive.com/api/remote-jobs", params={"limit": 100}).json()
    jobs = []
    for row in data.get("jobs", []):
        tags = [t for t in (row.get("tags") or []) if isinstance(t, str)]
        for extra in (row.get("category"), row.get("job_type")):
            if extra and extra not in tags:
                tags.append(extra)
        jobs.append(
            {
                "external_id": str(row.get("id") or row.get("url") or ""),
                "title": row.get("title") or "",
                "company": row.get("company_name") or "",
                "location": row.get("candidate_required_location") or "Remote",
                "salary": row.get("salary") or "",
                "tags": tags,
                "description": strip_html(row.get("description") or ""),
                # ToS: link back to the Remotive listing and credit Remotive.
                "url": row.get("url") or "",
                "posted_at": _from_iso(row.get("publication_date")),
            }
        )
    return jobs


def fetch_jobicy() -> list[dict]:
    data = _get("https://jobicy.com/api/v2/remote-jobs", params={"count": 50}).json()
    jobs = []
    for row in data.get("jobs", []):
        industry = row.get("jobIndustry")
        tags = industry if isinstance(industry, list) else [industry] if industry else []
        for extra_key in ("jobLevel", "jobType"):
            extra = row.get(extra_key)
            extra = extra if isinstance(extra, list) else [extra] if extra else []
            tags.extend(extra)
        currency = row.get("salaryCurrency") or "USD"
        jobs.append(
            {
                "external_id": str(row.get("id") or row.get("url") or ""),
                "title": row.get("jobTitle") or "",
                "company": row.get("companyName") or "",
                "location": row.get("jobGeo") or "Anywhere",
                "salary": _fmt_salary(row.get("annualSalaryMin"), row.get("annualSalaryMax"), f"{currency} "),
                "tags": [str(t) for t in tags if t],
                "description": strip_html(row.get("jobDescription") or row.get("jobExcerpt") or ""),
                "url": row.get("url") or "",
                "posted_at": _from_iso(row.get("pubDate")),
            }
        )
    return jobs


def fetch_himalayas() -> list[dict]:
    data = _get("https://himalayas.app/jobs/api", params={"limit": 20}).json()
    jobs = []
    for row in data.get("jobs", []):
        locations = row.get("locationRestrictions") or []
        tags = [str(t) for t in (row.get("categories") or [])]
        for extra in (row.get("seniority"), row.get("employmentType")):
            extra = extra if isinstance(extra, list) else [extra] if extra else []
            tags.extend(str(t) for t in extra)
        ext = row.get("guid") or row.get("applicationLink") or f"{row.get('companyName')}::{row.get('title')}"
        jobs.append(
            {
                "external_id": str(ext),
                "title": row.get("title") or "",
                "company": row.get("companyName") or "",
                "location": ", ".join(locations) if locations else "Worldwide",
                "salary": _fmt_salary(row.get("minSalary"), row.get("maxSalary")),
                "tags": tags,
                "description": strip_html(row.get("description") or row.get("excerpt") or ""),
                "url": row.get("applicationLink") or "",
                "posted_at": _from_epoch(row.get("pubDate")),
            }
        )
    return jobs


def fetch_arbeitnow() -> list[dict]:
    data = _get("https://www.arbeitnow.com/api/job-board-api").json()
    jobs = []
    for row in data.get("data", []):
        if not row.get("remote"):  # board is EU-heavy and mixes on-site roles
            continue
        jobs.append(
            {
                "external_id": str(row.get("slug") or row.get("url") or ""),
                "title": row.get("title") or "",
                "company": row.get("company_name") or "",
                "location": row.get("location") or "Remote",
                "salary": "",
                "tags": [str(t) for t in (row.get("tags") or []) + (row.get("job_types") or [])],
                "description": strip_html(row.get("description") or ""),
                "url": row.get("url") or "",
                "posted_at": _from_epoch(row.get("created_at")),
            }
        )
    return jobs


def fetch_workingnomads() -> list[dict]:
    data = _get("https://www.workingnomads.com/api/exposed_jobs/").json()
    jobs = []
    for row in data if isinstance(data, list) else []:
        tags = [t.strip() for t in (row.get("tags") or "").split(",") if t.strip()]
        if row.get("category_name"):
            tags.append(row["category_name"])
        jobs.append(
            {
                "external_id": str(row.get("id") or row.get("url") or ""),
                "title": row.get("title") or "",
                "company": row.get("company_name") or "",
                "location": row.get("location") or "Remote",
                "salary": "",
                "tags": tags,
                "description": strip_html(row.get("description") or ""),
                "url": row.get("url") or "",
                "posted_at": _from_iso(row.get("pub_date")),
            }
        )
    return jobs


_HN_COMPANY_RE = re.compile(r"^(.*?)\s*(?:\(YC [^)]+\))?\s*is hiring", re.IGNORECASE)


def _hn_normalize(title: str, text_html: str, url: str, item_id, posted) -> dict:
    company = ""
    match = _HN_COMPANY_RE.match(title or "")
    if match:
        company = match.group(1).strip()
    tags = ["hacker news"]
    if "(YC " in (title or ""):
        tags.append("yc startup")
    return {
        "external_id": str(item_id),
        "title": title or "",
        "company": company or "Hacker News post",
        "location": "See posting",
        "salary": "",
        "tags": tags,
        "description": strip_html(text_html or "") or (title or ""),
        "url": url or f"https://news.ycombinator.com/item?id={item_id}",
        "posted_at": posted,
    }


def fetch_hackernews() -> list[dict]:
    # Preferred: Algolia HN Search — one request for the latest job posts.
    try:
        data = _get(
            "https://hn.algolia.com/api/v1/search_by_date",
            params={"tags": "job", "hitsPerPage": 50},
        ).json()
        jobs = [
            _hn_normalize(
                h.get("title") or "",
                h.get("story_text") or "",
                h.get("url") or "",
                h.get("objectID"),
                _from_epoch(h.get("created_at_i")) or _from_iso(h.get("created_at")),
            )
            for h in data.get("hits", [])
            if h.get("title")
        ]
        if jobs:
            return jobs
    except (requests.RequestException, ValueError):
        pass  # Algolia had an ingestion outage in 2025; fall back to Firebase.

    # Fallback: official Firebase API (keyless, "currently no rate limit").
    ids = _get("https://hacker-news.firebaseio.com/v0/jobstories.json").json()[:40]

    def fetch_item(item_id):
        try:
            return _get(f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json").json()
        except (requests.RequestException, ValueError):
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        items = [i for i in pool.map(fetch_item, ids) if i]
    return [
        _hn_normalize(i.get("title") or "", i.get("text") or "", i.get("url") or "", i.get("id"), _from_epoch(i.get("time")))
        for i in items
        if i.get("title")
    ]


# ------------------------------------------------------------- registry ---

SOURCES: dict[str, dict] = {
    "remoteok": {"label": "Remote OK", "home": "https://remoteok.com", "cooldown_minutes": 60, "fetch": fetch_remoteok},
    "weworkremotely": {"label": "We Work Remotely", "home": "https://weworkremotely.com", "cooldown_minutes": 60, "fetch": fetch_weworkremotely},
    "remotive": {"label": "Remotive", "home": "https://remotive.com", "cooldown_minutes": 360, "fetch": fetch_remotive},
    "jobicy": {"label": "Jobicy", "home": "https://jobicy.com", "cooldown_minutes": 60, "fetch": fetch_jobicy},
    "himalayas": {"label": "Himalayas", "home": "https://himalayas.app", "cooldown_minutes": 60, "fetch": fetch_himalayas},
    "arbeitnow": {"label": "Arbeitnow", "home": "https://www.arbeitnow.com", "cooldown_minutes": 30, "fetch": fetch_arbeitnow},
    "workingnomads": {"label": "Working Nomads", "home": "https://www.workingnomads.com", "cooldown_minutes": 60, "fetch": fetch_workingnomads},
    "hackernews": {"label": "Hacker News", "home": "https://news.ycombinator.com/jobs", "cooldown_minutes": 30, "fetch": fetch_hackernews},
}


def _upsert(session, source: str, jobs: list[dict]) -> int:
    existing = {
        row.external_id: row
        for row in session.scalars(select(ScrapedJob).where(ScrapedJob.source == source))
    }
    added = 0
    seen: set[str] = set()
    for data in jobs:
        ext = str(data.get("external_id") or "").strip()[:255]
        if not ext or ext in seen or not data.get("title"):
            continue
        seen.add(ext)
        row = existing.get(ext)
        if row is None:
            row = ScrapedJob(source=source, external_id=ext)
            session.add(row)
            added += 1
        row.title = (data.get("title") or "")[:300]
        row.company = (data.get("company") or "")[:200]
        row.location = (data.get("location") or "")[:200]
        row.salary = (data.get("salary") or "")[:200]
        row.url = data.get("url") or ""
        row.description = data.get("description") or ""
        row.tags = ",".join(dict.fromkeys(t.strip().lower() for t in data.get("tags") or [] if t.strip()))[:2000]
        row.posted_at = data.get("posted_at")
        row.scraped_at = datetime.utcnow()
    return added


def _error_message(exc: Exception) -> str:
    if isinstance(exc, requests.HTTPError):
        code = exc.response.status_code if exc.response is not None else 0
        if code == 429:
            return "rate limited (HTTP 429) — will retry on a later pull"
        if code in (403, 530):
            return f"blocked by the source (HTTP {code}) — likely anti-bot/network policy; try again later or from another network"
        return f"source returned HTTP {code}"
    if isinstance(exc, requests.Timeout):
        return "request timed out"
    if isinstance(exc, requests.RequestException):
        return f"network error ({type(exc).__name__})"
    if isinstance(exc, (ValueError, KeyError, ET.ParseError)):
        return f"unexpected response format: {exc}"
    return f"unexpected error: {exc}"


def scrape_all() -> dict[str, dict]:
    """Pull every source, honoring per-source cooldowns. Never raises."""
    results: dict[str, dict] = {}
    now = datetime.utcnow()
    with SessionLocal() as session:
        for key, meta in SOURCES.items():
            state = session.get(SourceState, key)
            if state is None:
                state = SourceState(source=key)
                session.add(state)
            cooldown = timedelta(minutes=meta["cooldown_minutes"])
            if (
                state.last_status == "ok"
                and state.last_fetched_at
                and now - state.last_fetched_at < cooldown
            ):
                next_at = state.last_fetched_at + cooldown
                results[key] = {
                    "label": meta["label"],
                    "status": "cooldown",
                    "added": 0,
                    "fetched": 0,
                    "error": "",
                    "next_allowed_at": next_at.isoformat(),
                }
                continue
            try:
                jobs = meta["fetch"]()
                added = _upsert(session, key, jobs)
                state.last_fetched_at = datetime.utcnow()
                state.last_status = "ok"
                state.last_error = ""
                state.last_count = len(jobs)
                results[key] = {
                    "label": meta["label"],
                    "status": "ok",
                    "added": added,
                    "fetched": len(jobs),
                    "error": "",
                }
            except Exception as exc:  # noqa: BLE001 — one bad feed must not sink the rest
                session.rollback()
                msg = _error_message(exc)
                state = session.get(SourceState, key) or SourceState(source=key)
                state.last_fetched_at = datetime.utcnow()
                state.last_status = "error"
                state.last_error = msg
                session.add(state)
                results[key] = {
                    "label": meta["label"],
                    "status": "error",
                    "added": 0,
                    "fetched": 0,
                    "error": msg,
                }
            session.commit()
    return results
