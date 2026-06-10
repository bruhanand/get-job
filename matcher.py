"""Resume <-> job-description match scoring, pure Python (stdlib only).

Approach: IDF-weighted keyword coverage.

1. Tokenize the resume and each job (title + tags + description) into
   unigrams and bigrams. The tokenizer is tech-aware: it preserves terms
   like "c++", "c#", "node.js", "ci/cd", and keeps a whitelist of short
   tech tokens ("go", "ai", "qa", ...) that a naive length filter would drop.
2. Weight every job term by its inverse document frequency (IDF) computed
   over the currently scraped corpus, so boilerplate that appears in every
   ad ("team", "remote", "benefits") counts far less than discriminative
   skills ("django", "react native", "postgresql").
3. Match Score = the share of a job's IDF mass covered by resume terms,
   passed through a square-root curve so realistic coverage (5-40%) maps
   to an intuitive 0-100 display range. Terms found in the job title/tags
   weigh 1.5x; terms the user listed explicitly as skills count double.

The scorer also returns the top matched keywords per job so the UI can
explain *why* a job scored the way it did.
"""

from __future__ import annotations

import math
import re
from collections import Counter

# Generic English + job-ad boilerplate. Deliberately includes words that are
# near-universal in postings so they never dominate the score.
STOPWORDS = frozenset(
    """
    a about above after again all also am an and any are as at be because been
    before being below between both but by can could did do does doing down
    during each few for from further had has have having he her here hers him
    his how i if in into is it its itself just me more most my myself no nor
    not now of off on once only or other our ours out over own same she should
    so some such than that the their theirs them then there these they this
    those through to too under until up very was we were what when where which
    while who whom why will with you your yours yourself
    ability able across additional advantage applicants application apply
    benefits best bonus build building career click company compensation
    culture customers day days dedicated description detail details
    environment etc excellent exciting experience experienced family fast
    flexible full fully great group growing growth help high hire hiring hours
    ideal including industry info job jobs join knowledge learn least level
    like looking love make manage member mission month months need new offer
    opportunity opportunities others paid part people per perks plus position
    preferred product products proven range related remote required
    requirements responsibilities responsible role salary seeking skills
    someone strong success team teams time today together tools understanding
    us use using want way ways week weeks well within work working world year
    years
    """.split()
)

# Short tokens that are real tech terms and must survive the length filter.
SHORT_TECH = frozenset(
    """
    c r go js ts py ai ml dl qa ui ux db os ci cd cv 3d k8s aws gcp api sql
    css php ios sre etl llm nlp gis sap crm erp seo vue git npm jvm tdd ddd
    iot ar vr c# c++ f# .net
    """.split()
)

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#.\-/]*")


def tokenize(text: str) -> list[str]:
    """Lowercase, split into tech-aware tokens, drop stopwords/noise."""
    text = (text or "").lower()
    # Normalize unicode dashes/ligatures that commonly appear in resumes.
    text = text.replace("–", "-").replace("—", "-")
    text = text.replace("ﬂ", "fl").replace("ﬁ", "fi")
    tokens = []
    for raw in _TOKEN_RE.findall(text):
        tok = raw.strip(".-/")
        # Re-allow trailing symbols that are part of the term itself.
        if raw in ("c++", "c#", "f#", ".net"):
            tok = raw
        if not tok or tok in STOPWORDS:
            continue
        if len(tok) < 3 and tok not in SHORT_TECH:
            continue
        if tok.isdigit():
            continue
        tokens.append(tok)
    return tokens


def extract_terms(text: str) -> set[str]:
    """Unigrams + adjacent bigrams (catches 'react native', 'machine learning')."""
    toks = tokenize(text)
    terms = set(toks)
    terms.update(f"{a} {b}" for a, b in zip(toks, toks[1:]))
    return terms


def score_jobs(resume_text: str, skills_text: str, jobs: list[dict]) -> list[dict]:
    """Annotate each job dict with match_score (0-100) and matched_keywords.

    ``jobs`` are dicts with at least title/tags/description. If the profile is
    empty, match_score is None for every job (UI prompts to set up a profile).
    """
    profile_blob = f"{resume_text or ''}\n{skills_text or ''}"
    resume_terms = extract_terms(profile_blob)
    skill_terms = extract_terms(skills_text or "")

    if not resume_terms:
        for job in jobs:
            job["match_score"] = None
            job["matched_keywords"] = []
        return jobs

    job_term_data = []
    doc_freq: Counter = Counter()
    for job in jobs:
        tags = job.get("tags") or []
        tag_text = " ".join(tags) if isinstance(tags, list) else str(tags)
        head_terms = extract_terms(f"{job.get('title', '')} {tag_text}")
        all_terms = head_terms | extract_terms(job.get("description", ""))
        job_term_data.append((head_terms, all_terms))
        doc_freq.update(all_terms)

    n_docs = max(len(jobs), 1)

    def idf(term: str) -> float:
        return math.log(1.0 + n_docs / (1.0 + doc_freq[term]))

    for job, (head_terms, all_terms) in zip(jobs, job_term_data):
        if not all_terms:
            job["match_score"] = 0
            job["matched_keywords"] = []
            continue
        total = 0.0
        matched = 0.0
        matched_terms: list[tuple[float, str]] = []
        for term in all_terms:
            weight = idf(term) * (1.5 if term in head_terms else 1.0)
            total += weight
            if term in resume_terms:
                gain = weight * (2.0 if term in skill_terms else 1.0)
                matched += gain
                matched_terms.append((gain, term))
        raw = min(matched / total, 1.0) if total else 0.0
        job["match_score"] = round(100 * math.sqrt(raw))
        matched_terms.sort(reverse=True)
        # Prefer showing specific terms; bigrams already imply their unigrams.
        seen: set[str] = set()
        keywords = []
        for _, term in matched_terms:
            if any(term in k or k in term for k in seen):
                continue
            seen.add(term)
            keywords.append(term)
            if len(keywords) >= 8:
                break
        job["matched_keywords"] = keywords
    return jobs
