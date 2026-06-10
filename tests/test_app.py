"""Stdlib-only test suite: parser fixtures, matcher, and API round-trips.

Run from the repo root:  python -m tests.test_app
Network is never touched — scraper._get is monkey-patched with canned
responses shaped exactly like each feed's documented format.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["GETJOB_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")

import matcher  # noqa: E402
import models  # noqa: E402
import scraper  # noqa: E402

PASS = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS
    assert cond, f"FAIL: {name} {detail}"
    PASS += 1
    print(f"  ok - {name}")


class FakeResponse:
    def __init__(self, payload, is_json=True):
        self._payload = payload
        self.content = payload.encode() if isinstance(payload, str) else json.dumps(payload).encode()

    def json(self):
        if isinstance(self._payload, (dict, list)):
            return self._payload
        return json.loads(self._payload)


FIXTURES = {
    "remoteok.com/api": [
        {"last_updated": 1765000000, "legal": "API Terms of Service: link back to Remote OK."},
        {
            "id": "1042", "slug": "senior-python-dev", "epoch": 1765300000,
            "date": "2026-06-08T12:00:00+00:00", "company": "Acme Remote",
            "position": "Senior Python Developer", "tags": ["python", "django", "api"],
            "description": "<p>Build <b>Django</b> services with PostgreSQL.</p>",
            "location": "Worldwide", "salary_min": 70000, "salary_max": 110000,
            "url": "https://remoteok.com/remote-jobs/1042",
            "apply_url": "https://remoteok.com/remote-jobs/1042",
        },
    ],
    "weworkremotely.com/remote-jobs.rss": """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss" xmlns:dc="http://purl.org/dc/elements/1.1/">
<channel><title>We Work Remotely</title><ttl>60</ttl>
<item>
  <title>Globex: React Native Engineer</title>
  <region>Anywhere in the World</region>
  <category>Full-Stack Programming</category>
  <type>full-time</type>
  <description>&lt;p&gt;Ship Expo apps. Headquarters: Berlin&lt;/p&gt;</description>
  <pubDate>Mon, 08 Jun 2026 09:30:00 +0000</pubDate>
  <link>https://weworkremotely.com/remote-jobs/globex-react-native-engineer</link>
  <guid>https://weworkremotely.com/remote-jobs/globex-react-native-engineer</guid>
</item>
</channel></rss>""",
    "remotive.com/api/remote-jobs": {
        "0-legal-notice": "Remotive API Legal Notice",
        "job-count": 1,
        "jobs": [{
            "id": 990001, "url": "https://remotive.com/remote-jobs/software-dev/x-990001",
            "title": "Backend Engineer (Django)", "company_name": "Initech",
            "category": "Software Development", "job_type": "full_time",
            "publication_date": "2026-06-07T08:00:00", "candidate_required_location": "Worldwide",
            "salary": "$80,000 - $120,000", "tags": ["python", "django", "postgresql"],
            "description": "<p>REST APIs with Django REST Framework and Redis.</p>",
        }],
    },
    "jobicy.com/api/v2/remote-jobs": {
        "jobs": [{
            "id": 55001, "url": "https://jobicy.com/jobs/55001-next-js-engineer",
            "jobTitle": "Next.js Engineer", "companyName": "Umbrella Web",
            "jobIndustry": ["Web & App Development"], "jobType": ["full-time"],
            "jobGeo": "Anywhere", "jobLevel": "Senior",
            "jobExcerpt": "Build SSR apps.",
            "jobDescription": "<p>Next.js App Router, TypeScript, Tailwind CSS.</p>",
            "pubDate": "2026-06-09 18:02:14",
            "annualSalaryMin": 90000, "annualSalaryMax": 130000, "salaryCurrency": "USD",
        }],
    },
    "himalayas.app/jobs/api": {
        "jobs": [{
            "title": "Full Stack Developer", "excerpt": "React + Node.",
            "companyName": "Hooli", "companyLogo": "x.png",
            "employmentType": "Full Time", "categories": ["Engineering"],
            "locationRestrictions": ["United States"], "seniority": ["Mid-level"],
            "minSalary": 100000, "maxSalary": 140000,
            "description": "<p>React, Node.js, PostgreSQL, CI/CD.</p>",
            "pubDate": 1765200000,
            "applicationLink": "https://himalayas.app/companies/hooli/jobs/full-stack-developer",
            "guid": "himalayas-hooli-fsd-1",
        }],
        "totalCount": 1, "offset": 0, "limit": 20,
    },
    "arbeitnow.com/api/job-board-api": {
        "data": [
            {
                "slug": "remote-devops-engineer-berlin", "company_name": "Stark GmbH",
                "title": "DevOps Engineer", "description": "<p>Docker, Kubernetes, GitHub Actions.</p>",
                "remote": True, "url": "https://www.arbeitnow.com/jobs/companies/stark/devops",
                "tags": ["devops"], "job_types": ["full-time"], "location": "Berlin",
                "created_at": 1765100000,
            },
            {   # on-site row must be filtered out
                "slug": "onsite-chef-munich", "company_name": "Bistro", "title": "Chef",
                "description": "cook", "remote": False, "url": "x", "tags": [],
                "job_types": [], "location": "Munich", "created_at": 1765100000,
            },
        ],
        "links": {"next": None}, "meta": {"current_page": 1, "last_page": 1},
    },
    "workingnomads.com/api/exposed_jobs": [
        {
            "id": 777, "url": "https://www.workingnomads.com/jobs?job=777",
            "title": "Site Reliability Engineer", "company_name": "Wayne Cloud",
            "description": "Terraform, AWS, on-call rotation.",
            "category_name": "Development", "tags": "aws,terraform,sre",
            "location": "USA", "pub_date": "2026-06-06T10:00:00",
        },
    ],
    "hn.algolia.com/api/v1/search_by_date": {
        "hits": [{
            "objectID": "41234567",
            "title": "WidgetCo (YC W26) is hiring a founding full-stack engineer",
            "url": "https://widget.co/jobs", "author": "wc",
            "story_text": "TypeScript, React, Postgres. Remote friendly.",
            "created_at": "2026-06-09T15:00:00Z", "created_at_i": 1781017200,
        }],
    },
}


def fake_get(url, **kwargs):
    for key, payload in FIXTURES.items():
        if key in url:
            return FakeResponse(payload)
    raise AssertionError(f"unexpected URL in test: {url}")


def test_fetchers():
    print("fetchers:")
    scraper._get = fake_get

    jobs = scraper.fetch_remoteok()
    check("remoteok skips legal-notice row", len(jobs) == 1)
    check("remoteok fields", jobs[0]["company"] == "Acme Remote" and jobs[0]["salary"] == "$70k – $110k")
    check("remoteok html stripped", "<" not in jobs[0]["description"])

    jobs = scraper.fetch_weworkremotely()
    check("wwr company/title split", jobs[0]["company"] == "Globex" and jobs[0]["title"] == "React Native Engineer")
    check("wwr region->location", jobs[0]["location"] == "Anywhere in the World")
    check("wwr pubDate parsed", jobs[0]["posted_at"] is not None and jobs[0]["posted_at"].year == 2026)

    jobs = scraper.fetch_remotive()
    check("remotive fields", jobs[0]["company"] == "Initech" and jobs[0]["salary"] == "$80,000 - $120,000")
    check("remotive tags merged", "software development" in [t.lower() for t in jobs[0]["tags"]])

    jobs = scraper.fetch_jobicy()
    check("jobicy fields", jobs[0]["title"] == "Next.js Engineer" and "USD" in jobs[0]["salary"])
    check("jobicy pubDate parsed", jobs[0]["posted_at"] is not None)

    jobs = scraper.fetch_himalayas()
    check("himalayas fields", jobs[0]["company"] == "Hooli" and jobs[0]["location"] == "United States")

    jobs = scraper.fetch_arbeitnow()
    check("arbeitnow filters non-remote", len(jobs) == 1 and jobs[0]["title"] == "DevOps Engineer")

    jobs = scraper.fetch_workingnomads()
    check("workingnomads tag string split", jobs[0]["tags"][:3] == ["aws", "terraform", "sre"])

    jobs = scraper.fetch_hackernews()
    check("hn company parsed", jobs[0]["company"] == "WidgetCo")
    check("hn yc tag", "yc startup" in jobs[0]["tags"])


def test_scrape_all_and_api():
    print("scrape_all + API:")
    models.init_db()
    results = scraper.scrape_all()
    check("all sources ok with fixtures", all(r["status"] == "ok" for r in results.values()), str(results))
    total_added = sum(r["added"] for r in results.values())
    check("eight jobs ingested", total_added == 8, f"got {total_added}")

    results2 = scraper.scrape_all()
    check("cooldown honored on immediate re-pull", all(r["status"] == "cooldown" for r in results2.values()))

    import app as app_module

    client = app_module.app.test_client()

    res = client.get("/api/jobs")
    jobs = res.get_json()["jobs"]
    check("GET /api/jobs returns 8", len(jobs) == 8)
    check("match scores computed", all(isinstance(j["match_score"], int) for j in jobs))
    django_job = next(j for j in jobs if "Django" in j["title"])
    check("django scores high for this resume", django_job["match_score"] >= 50, str(django_job["match_score"]))

    res = client.get("/api/jobs?q=django")
    check("title search filters", len(res.get_json()["jobs"]) == 1)
    res = client.get("/api/jobs?source=jobicy")
    check("source filter works", len(res.get_json()["jobs"]) == 1)

    # Track This Job (clone from scraped)
    res = client.post("/api/tracked", json={"scraped_job_id": django_job["id"]})
    check("clone returns 201", res.status_code == 201, str(res.get_json()))
    cloned = res.get_json()["job"]
    check("clone copies fields", cloned["title"] == django_job["title"] and cloned["status"] == "to_apply")
    res = client.post("/api/tracked", json={"scraped_job_id": django_job["id"]})
    check("duplicate clone flagged", res.get_json().get("duplicate") is True)

    res = client.get(f"/api/jobs?q=django")
    check("tracked flag set in feed", res.get_json()["jobs"][0]["tracked"] is True)

    # Manual add with all fields
    res = client.post("/api/tracked", json={
        "title": "Dream Job", "company": "DreamCo", "salary_range": "$1 – $2",
        "url": "https://example.com", "notes": "n", "status": "applied", "date_applied": "2026-06-01",
    })
    check("manual add", res.status_code == 201 and res.get_json()["job"]["date_applied"] == "2026-06-01")
    manual_id = res.get_json()["job"]["id"]

    res = client.post("/api/tracked", json={"company": "NoTitle Inc"})
    check("missing title rejected", res.status_code == 400)
    res = client.post("/api/tracked", json={"title": "X", "status": "bogus"})
    check("bad status rejected", res.status_code == 400)

    # Status move auto-stamps date_applied
    res = client.patch(f"/api/tracked/{cloned['id']}", json={"status": "interviewing"})
    moved = res.get_json()["job"]
    check("status moved", moved["status"] == "interviewing")
    check("date_applied auto-stamped on first move", moved["date_applied"] is not None)

    res = client.patch("/api/tracked/99999", json={"status": "applied"})
    check("patch missing job -> 404", res.status_code == 404)

    res = client.get("/api/analytics").get_json()
    check("analytics totals", res["total_tracked"] == 2 and res["applications_sent"] == 2)
    check("conversion computed", res["interview_conversion"] == 50.0, str(res))
    check("timeline zero-filled", len(res["timeline"]["labels"]) == len(res["timeline"]["counts"]) > 0)

    res = client.delete(f"/api/tracked/{manual_id}")
    check("delete works", res.status_code == 200)
    check("delete reflected", client.get("/api/analytics").get_json()["total_tracked"] == 1)

    # Profile round-trip reshapes scores
    res = client.put("/api/profile", json={"resume_text": "", "skills": ""})
    check("profile cleared", res.status_code == 200)
    res = client.get("/api/jobs").get_json()["jobs"]
    check("empty profile -> null scores", all(j["match_score"] is None for j in res))
    res = client.put("/api/profile", json={"resume_text": "django postgresql react", "skills": "django"})
    check("profile saved with term count", res.get_json()["term_count"] >= 3)


def test_matcher_edges():
    print("matcher edges:")
    jobs = [{"title": "", "tags": [], "description": ""}]
    matcher.score_jobs("python", "", jobs)
    check("empty job text scores 0", jobs[0]["match_score"] == 0)
    jobs = [{"title": "C++ Engineer", "tags": ["c++"], "description": "Modern C++ and Go."}]
    matcher.score_jobs("I write C++ and Go services", "", jobs)
    check("short tech tokens kept", jobs[0]["match_score"] > 0 and "c++" in jobs[0]["matched_keywords"])


if __name__ == "__main__":
    test_fetchers()
    test_scrape_all_and_api()
    test_matcher_edges()
    print(f"\nall {PASS} checks passed")
