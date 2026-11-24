"""Deterministic, explainable matching between workers and demo jobs."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence


SUPPORTED_TRADES = {"Electrician", "Plumber"}


@dataclass(frozen=True)
class JobListing:
    job_id: str
    job_title: str
    trade: str
    employer_name: str
    location: str
    description: str
    required_skills: tuple[str, ...]
    preferred_skills: tuple[str, ...]
    salary_min: int
    salary_max: int
    job_type: str


@dataclass(frozen=True)
class MatchedSkill:
    skill_name: str
    evidence_level: str


@dataclass(frozen=True)
class JobMatch:
    listing: JobListing
    match_percentage: float
    matched_skills: tuple[MatchedSkill, ...]
    missing_skills: tuple[str, ...]


def normalize_skill_name(skill_name: str) -> str:
    """Normalize case and whitespace for deterministic skill comparison."""
    if not isinstance(skill_name, str):
        return ""
    return " ".join(skill_name.strip().casefold().split())


def load_demo_jobs(path: str | Path | None = None) -> tuple[JobListing, ...]:
    """Load and validate the curated demo job dataset."""
    if path is None:
        path = Path(__file__).resolve().parents[1] / "data" / "jobs.json"
    else:
        path = Path(path)

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not load demo job data: {exc}") from exc
    if not isinstance(payload, list):
        raise ValueError("Demo job data must be a JSON array.")

    listings: list[JobListing] = []
    seen_ids: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("Every demo job must be a JSON object.")
        required_fields = (
            "job_id",
            "job_title",
            "trade",
            "employer_name",
            "location",
            "description",
            "required_skills",
            "preferred_skills",
            "salary_min",
            "salary_max",
            "job_type",
        )
        if any(field not in item for field in required_fields):
            raise ValueError("Demo job is missing required fields.")
        if item["trade"] not in SUPPORTED_TRADES:
            raise ValueError(f"Unsupported demo job trade: {item['trade']!r}.")
        if not isinstance(item["required_skills"], list) or not isinstance(
            item["preferred_skills"], list
        ):
            raise ValueError("Job skill lists must be JSON arrays.")
        if not all(isinstance(skill, str) and skill.strip() for skill in item["required_skills"]):
            raise ValueError("Required skill names must be non-empty strings.")
        if not all(isinstance(skill, str) and skill.strip() for skill in item["preferred_skills"]):
            raise ValueError("Preferred skill names must be non-empty strings.")
        if type(item["salary_min"]) is not int or type(item["salary_max"]) is not int:
            raise ValueError("Job salary values must be integers.")
        if item["job_id"] in seen_ids:
            raise ValueError(f"Duplicate demo job ID: {item['job_id']!r}.")
        seen_ids.add(item["job_id"])

        listings.append(
            JobListing(
                job_id=item["job_id"],
                job_title=item["job_title"],
                trade=item["trade"],
                employer_name=item["employer_name"],
                location=item["location"],
                description=item["description"],
                required_skills=tuple(item["required_skills"]),
                preferred_skills=tuple(item["preferred_skills"]),
                salary_min=item["salary_min"],
                salary_max=item["salary_max"],
                job_type=item["job_type"],
            )
        )
    return tuple(listings)


def evidence_level_map(
    worker_skills: Iterable[Mapping[str, object]],
) -> dict[str, str]:
    """Build normalized evidence levels without assigning independent verification."""
    evidence: dict[str, str] = {}
    precedence = {
        "SELF_REPORTED": 1,
        "ASSESSED": 2,
        "INDEPENDENTLY_VERIFIED": 3,
    }
    for skill in worker_skills:
        name = skill.get("skill_name")
        level = skill.get("evidence_level")
        if not isinstance(name, str) or not isinstance(level, str):
            continue
        if level not in precedence:
            continue
        normalized = normalize_skill_name(name)
        if not normalized:
            continue
        if normalized not in evidence or precedence[level] > precedence[evidence[normalized]]:
            evidence[normalized] = level
    return evidence


def match_jobs(
    trade: str,
    worker_skills: Sequence[Mapping[str, object]],
    jobs: Sequence[JobListing],
    *,
    location: str | None = None,
) -> tuple[JobMatch, ...]:
    """Match a worker to trade jobs using required-skill coverage only."""
    if trade not in SUPPORTED_TRADES:
        raise ValueError(f"Unsupported worker trade: {trade!r}.")

    evidence = evidence_level_map(worker_skills)
    location_filter = normalize_skill_name(location) if location is not None else ""
    matches: list[JobMatch] = []

    for job in jobs:
        if job.trade != trade:
            continue
        if location_filter:
            if location_filter not in normalize_skill_name(job.location):
                continue

        required_names = [skill.strip() for skill in job.required_skills]
        required_normalized = [normalize_skill_name(skill) for skill in required_names]
        if not required_normalized:
            percentage = 0.0
            matched: list[MatchedSkill] = []
            missing = tuple(required_names)
        else:
            matched = []
            missing = []
            for original, normalized in zip(required_names, required_normalized):
                if normalized in evidence:
                    matched.append(
                        MatchedSkill(
                            skill_name=original,
                            evidence_level=evidence[normalized],
                        )
                    )
                else:
                    missing.append(original)
            percentage = round(
                len(matched) * 100.0 / len(required_normalized),
                2,
            )

        matches.append(
            JobMatch(
                listing=job,
                match_percentage=percentage,
                matched_skills=tuple(matched),
                missing_skills=tuple(missing),
            )
        )

    matches.sort(
        key=lambda match: (
            -match.match_percentage,
            match.listing.job_id,
        )
    )
    return tuple(matches)
