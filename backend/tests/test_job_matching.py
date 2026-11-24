"""Focused tests for deterministic demo job matching."""

import pytest

from jobs.matching import JobListing, load_demo_jobs, match_jobs, normalize_skill_name


@pytest.fixture
def electrician_job():
    return JobListing(
        job_id="TEST-E-1",
        job_title="Electrician Test Listing",
        trade="Electrician",
        employer_name="Sample Demo Employer",
        location="Hyderabad",
        description="Sample listing.",
        required_skills=("Electrical safety", "Wiring repair"),
        preferred_skills=("Fan installation",),
        salary_min=18000,
        salary_max=28000,
        job_type="Full-time",
    )


@pytest.fixture
def plumber_job():
    return JobListing(
        job_id="TEST-P-1",
        job_title="Plumber Test Listing",
        trade="Plumber",
        employer_name="Sample Demo Employer",
        location="Hyderabad",
        description="Sample listing.",
        required_skills=("Pipe joint repair", "Leakage"),
        preferred_skills=("Tap installation",),
        salary_min=18000,
        salary_max=28000,
        job_type="Full-time",
    )


def test_normalize_skill_name_is_case_and_whitespace_insensitive():
    assert normalize_skill_name("  Wiring   REPAIR ") == "wiring repair"


def test_electrician_match_percentage_and_missing_skills(electrician_job):
    matches = match_jobs(
        "Electrician",
        [{"skill_name": " electrical SAFETY ", "evidence_level": "ASSESSED"}],
        [electrician_job],
    )

    assert len(matches) == 1
    assert matches[0].match_percentage == 50.0
    assert [skill.skill_name for skill in matches[0].matched_skills] == ["Electrical safety"]
    assert matches[0].missing_skills == ("Wiring repair",)
    assert matches[0].listing.preferred_skills == ("Fan installation",)


def test_preferred_skills_are_not_counted_as_required(electrician_job):
    matches = match_jobs(
        "Electrician",
        [{"skill_name": "Fan installation", "evidence_level": "ASSESSED"}],
        [electrician_job],
    )

    assert matches[0].match_percentage == 0.0
    assert matches[0].missing_skills == (
        "Electrical safety",
        "Wiring repair",
    )


def test_plumber_matching_and_case_insensitive_comparison(plumber_job):
    matches = match_jobs(
        "Plumber",
        [{"skill_name": "PIPE JOINT repair", "evidence_level": "SELF_REPORTED"}],
        [plumber_job],
    )

    assert matches[0].match_percentage == 50.0
    assert matches[0].matched_skills[0].evidence_level == "SELF_REPORTED"
    assert matches[0].missing_skills == ("Leakage",)


def test_trade_filtering(electrician_job, plumber_job):
    matches = match_jobs(
        "Electrician",
        [{"skill_name": "Electrical safety", "evidence_level": "ASSESSED"}],
        [plumber_job, electrician_job],
    )

    assert len(matches) == 1
    assert matches[0].listing.trade == "Electrician"


def test_location_filtering(electrician_job):
    matches = match_jobs(
        "Electrician",
        [],
        [electrician_job],
        location="hyderabad",
    )
    assert len(matches) == 1

    nonmatching = match_jobs(
        "Electrician",
        [],
        [electrician_job],
        location="Chennai",
    )
    assert nonmatching == ()


def test_empty_required_skills_has_safe_zero_percentage():
    job = JobListing(
        job_id="TEST-EMPTY",
        job_title="General Listing",
        trade="Electrician",
        employer_name="Sample Employer",
        location="Hyderabad",
        description="Sample.",
        required_skills=(),
        preferred_skills=("Basic electrical tools",),
        salary_min=10000,
        salary_max=20000,
        job_type="Contract",
    )

    matches = match_jobs("Electrician", [], [job])

    assert matches[0].match_percentage == 0.0
    assert matches[0].matched_skills == ()
    assert matches[0].missing_skills == ()


def test_sorting_is_descending_with_job_id_tiebreaker():
    high = JobListing(
        "TEST-H",
        "High",
        "Electrician",
        "Sample",
        "Hyderabad",
        "Sample",
        ("Electrical safety",),
        (),
        10000,
        20000,
        "Full-time",
    )
    low = JobListing(
        "TEST-L",
        "Low",
        "Electrician",
        "Sample",
        "Hyderabad",
        "Sample",
        ("Electrical safety", "Wiring repair"),
        (),
        10000,
        20000,
        "Full-time",
    )

    matches = match_jobs(
        "Electrician",
        [{"skill_name": "Electrical safety", "evidence_level": "ASSESSED"}],
        [low, high],
    )

    assert [match.listing.job_id for match in matches] == ["TEST-H", "TEST-L"]


def test_loaded_demo_dataset_contains_electrician_and_plumber_jobs():
    jobs = load_demo_jobs()

    assert len(jobs) == 10
    assert sum(job.trade == "Electrician" for job in jobs) == 5
    assert sum(job.trade == "Plumber" for job in jobs) == 5


def test_unsupported_trade_is_rejected():
    with pytest.raises(ValueError, match="Unsupported worker trade"):
        match_jobs("Carpenter", [], [])
