"""get-job: self-contained remote-job scraper + application tracker.

Flask + SQLite (SQLAlchemy). No paid APIs, no keys: jobs come from public,
unauthenticated JSON/RSS feeds (see scraper.py). Run with: python app.py
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta

from flask import Flask, jsonify, render_template, request
from sqlalchemy import or_, select

import matcher
import scraper
from models import (
    STATUSES,
    Profile,
    ScrapedJob,
    SessionLocal,
    SourceState,
    TrackedJob,
    init_db,
)

app = Flask(__name__)
init_db()

SNIPPET_LEN = 420


def _get_profile(session) -> Profile:
    profile = session.get(Profile, 1)
    if profile is None:
        profile = Profile(id=1, resume_text="", skills="")
        session.add(profile)
        session.commit()
    return profile


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


@app.get("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------------- scraper ---


@app.get("/api/jobs")
def list_jobs():
    q = (request.args.get("q") or "").strip()
    date_filter = request.args.get("date", "all")
    source = (request.args.get("source") or "").strip()
    sort = request.args.get("sort", "match")

    with SessionLocal() as session:
        stmt = select(ScrapedJob)
        if q:
            like = f"%{q}%"
            stmt = stmt.where(or_(ScrapedJob.title.ilike(like), ScrapedJob.company.ilike(like)))
        if source:
            stmt = stmt.where(ScrapedJob.source == source)
        days = {"today": 1, "3d": 3, "7d": 7, "30d": 30}.get(date_filter)
        if days:
            stmt = stmt.where(ScrapedJob.posted_at >= datetime.utcnow() - timedelta(days=days))
        stmt = stmt.order_by(ScrapedJob.posted_at.desc().nullslast(), ScrapedJob.id.desc()).limit(800)
        jobs = [job.to_dict() for job in session.scalars(stmt)]
        profile = _get_profile(session)
        tracked_ids = {
            sid
            for sid in session.scalars(
                select(TrackedJob.scraped_job_id).where(TrackedJob.scraped_job_id.is_not(None))
            )
        }

    matcher.score_jobs(profile.resume_text, profile.skills, jobs)
    for job in jobs:
        job["tracked"] = job["id"] in tracked_ids
        full = job.pop("description", "") or ""
        job["snippet"] = full[:SNIPPET_LEN] + ("…" if len(full) > SNIPPET_LEN else "")

    if sort == "match" and any(j["match_score"] is not None for j in jobs):
        jobs.sort(key=lambda j: ((j["match_score"] or 0), j["posted_at"] or ""), reverse=True)

    return jsonify({"jobs": jobs, "total": len(jobs)})


@app.get("/api/jobs/<int:job_id>")
def job_detail(job_id: int):
    with SessionLocal() as session:
        job = session.get(ScrapedJob, job_id)
        if job is None:
            return jsonify({"error": "job not found"}), 404
        payload = job.to_dict()
        profile = _get_profile(session)
    matcher.score_jobs(profile.resume_text, profile.skills, [payload])
    return jsonify(payload)


@app.post("/api/scrape")
def scrape_now():
    results = scraper.scrape_all()
    ok = sum(1 for r in results.values() if r["status"] == "ok")
    added = sum(r.get("added", 0) for r in results.values())
    return jsonify({"sources": results, "ok_sources": ok, "added": added})


@app.get("/api/sources")
def sources():
    with SessionLocal() as session:
        states = {s.source: s for s in session.scalars(select(SourceState))}
    payload = []
    for key, meta in scraper.SOURCES.items():
        state = states.get(key)
        payload.append(
            {
                "key": key,
                "label": meta["label"],
                "home": meta["home"],
                "cooldown_minutes": meta["cooldown_minutes"],
                "last_fetched_at": state.last_fetched_at.isoformat() if state and state.last_fetched_at else None,
                "last_status": state.last_status if state else "never",
                "last_error": state.last_error if state else "",
                "last_count": state.last_count if state else 0,
            }
        )
    return jsonify({"sources": payload})


# ---------------------------------------------------------------- tracker ---


@app.get("/api/tracked")
def list_tracked():
    with SessionLocal() as session:
        rows = session.scalars(
            select(TrackedJob).order_by(TrackedJob.updated_at.desc())
        ).all()
    return jsonify({"jobs": [r.to_dict() for r in rows], "statuses": STATUSES})


@app.post("/api/tracked")
def create_tracked():
    data = request.get_json(silent=True) or {}
    status = data.get("status") or "to_apply"
    if status not in STATUSES:
        return jsonify({"error": f"invalid status '{status}'"}), 400

    with SessionLocal() as session:
        scraped_id = data.get("scraped_job_id")
        if scraped_id:
            # "Track This Job": clone details from the scraped listing.
            src = session.get(ScrapedJob, scraped_id)
            if src is None:
                return jsonify({"error": "scraped job not found"}), 404
            existing = session.scalar(
                select(TrackedJob).where(TrackedJob.scraped_job_id == scraped_id)
            )
            if existing:
                return jsonify({"job": existing.to_dict(), "duplicate": True})
            tags = ", ".join(t for t in (src.tags or "").split(",") if t)
            note_bits = [f"Source: {scraper.SOURCES.get(src.source, {}).get('label', src.source)}"]
            if src.location:
                note_bits.append(f"Location: {src.location}")
            if tags:
                note_bits.append(f"Tags: {tags}")
            job = TrackedJob(
                title=src.title,
                company=src.company,
                salary_range=src.salary,
                url=src.url,
                notes="\n".join(note_bits),
                status="to_apply",
                scraped_job_id=src.id,
            )
        else:
            title = (data.get("title") or "").strip()
            if not title:
                return jsonify({"error": "title is required"}), 400
            job = TrackedJob(
                title=title,
                company=(data.get("company") or "").strip(),
                salary_range=(data.get("salary_range") or "").strip(),
                url=(data.get("url") or "").strip(),
                notes=data.get("notes") or "",
                status=status,
                date_applied=_parse_date(data.get("date_applied")),
            )
        session.add(job)
        session.commit()
        return jsonify({"job": job.to_dict()}), 201


@app.patch("/api/tracked/<int:job_id>")
def update_tracked(job_id: int):
    data = request.get_json(silent=True) or {}
    with SessionLocal() as session:
        job = session.get(TrackedJob, job_id)
        if job is None:
            return jsonify({"error": "job not found"}), 404
        if "status" in data:
            if data["status"] not in STATUSES:
                return jsonify({"error": f"invalid status '{data['status']}'"}), 400
            moving_to_applied = job.status == "to_apply" and data["status"] != "to_apply"
            job.status = data["status"]
            # First move off the backlog counts as "application sent" today.
            if moving_to_applied and job.date_applied is None:
                job.date_applied = date.today()
        for field in ("title", "company", "salary_range", "url", "notes"):
            if field in data:
                value = data[field] or ""
                setattr(job, field, value if field == "notes" else value.strip())
        if "date_applied" in data:
            job.date_applied = _parse_date(data["date_applied"])
        session.commit()
        return jsonify({"job": job.to_dict()})


@app.delete("/api/tracked/<int:job_id>")
def delete_tracked(job_id: int):
    with SessionLocal() as session:
        job = session.get(TrackedJob, job_id)
        if job is None:
            return jsonify({"error": "job not found"}), 404
        session.delete(job)
        session.commit()
    return jsonify({"deleted": job_id})


# ---------------------------------------------------------------- profile ---


@app.get("/api/profile")
def get_profile():
    with SessionLocal() as session:
        return jsonify(_get_profile(session).to_dict())


@app.put("/api/profile")
def save_profile():
    data = request.get_json(silent=True) or {}
    with SessionLocal() as session:
        profile = _get_profile(session)
        if "resume_text" in data:
            profile.resume_text = data["resume_text"] or ""
        if "skills" in data:
            profile.skills = data["skills"] or ""
        session.commit()
        payload = profile.to_dict()
    payload["term_count"] = len(matcher.extract_terms(f"{payload['resume_text']}\n{payload['skills']}"))
    return jsonify(payload)


# -------------------------------------------------------------- analytics ---


@app.get("/api/analytics")
def analytics():
    with SessionLocal() as session:
        rows = session.scalars(select(TrackedJob)).all()

    by_status = Counter(r.status for r in rows)
    sent = [r for r in rows if r.status != "to_apply"]
    interviews_plus = sum(by_status[s] for s in ("interviewing", "offer"))
    conversion = round(100 * interviews_plus / len(sent), 1) if sent else 0.0
    offer_rate = round(100 * by_status["offer"] / len(sent), 1) if sent else 0.0

    # Applications over time: one bucket per day, zero-filled, last 60 days max.
    sent_dates = sorted(r.date_applied or r.created_at.date() for r in sent)
    timeline_labels: list[str] = []
    timeline_counts: list[int] = []
    if sent_dates:
        start = max(sent_dates[0], date.today() - timedelta(days=59))
        per_day = Counter(d for d in sent_dates if d >= start)
        day = start
        while day <= date.today():
            timeline_labels.append(day.isoformat())
            timeline_counts.append(per_day.get(day, 0))
            day += timedelta(days=1)

    return jsonify(
        {
            "total_tracked": len(rows),
            "applications_sent": len(sent),
            "interview_conversion": conversion,
            "offer_rate": offer_rate,
            "by_status": {s: by_status.get(s, 0) for s in STATUSES},
            "timeline": {"labels": timeline_labels, "counts": timeline_counts},
        }
    )


@app.errorhandler(Exception)
def on_error(exc):  # keep the API JSON-only, never a stack-trace HTML page
    if hasattr(exc, "code") and isinstance(getattr(exc, "code"), int):
        return jsonify({"error": str(exc)}), exc.code
    app.logger.exception("unhandled error")
    return jsonify({"error": f"internal error: {exc}"}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
