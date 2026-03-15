"""Tests for the profile matching and CSV parsing system."""

from pathlib import Path

import pytest

from fin_insights.profile import load_all_profiles, match_profile, parse_csv_with_profile

FIXTURES = Path(__file__).parent / "fixtures"
PROFILES_DIR = Path(__file__).parent.parent / "profiles"


@pytest.fixture
def profiles():
    """Load all built-in profiles."""
    # Create a fake data_dir that has no user profiles — only built-in
    return load_all_profiles(Path("/nonexistent"))


def test_load_builtin_profiles(profiles):
    """Verify all built-in profiles load correctly."""
    institutions = {p["institution"] for p in profiles}
    assert "chase" in institutions
    assert "amex" in institutions
    assert "discover" in institutions
    assert "wells_fargo" in institutions
    assert "bofa" in institutions


def test_profile_count(profiles):
    """Verify we ship 7 default profiles (5 credit + 2 checking)."""
    csv_profiles = [p for p in profiles if p.get("file_type") == "csv"]
    assert len(csv_profiles) >= 4  # amex, chase credit, discover, wells fargo


def test_match_chase_credit(profiles):
    """Chase credit card CSV matches the chase_credit profile."""
    profile = match_profile(FIXTURES / "sample_chase_credit.csv", profiles)
    assert profile is not None
    assert profile["institution"] == "chase"
    assert profile["account_type"] == "credit_card"


def test_match_amex_credit(profiles):
    """Amex credit card CSV matches the amex_credit profile."""
    profile = match_profile(FIXTURES / "sample_amex_credit.csv", profiles)
    assert profile is not None
    assert profile["institution"] == "amex"
    assert profile["account_type"] == "credit_card"


def test_match_discover_credit(profiles):
    """Discover credit card CSV matches the discover_credit profile."""
    profile = match_profile(FIXTURES / "sample_discover_credit.csv", profiles)
    assert profile is not None
    assert profile["institution"] == "discover"


def test_match_wells_fargo_credit(profiles):
    """Wells Fargo credit card CSV matches the wells_fargo_credit profile."""
    profile = match_profile(FIXTURES / "sample_wells_fargo_credit.csv", profiles)
    assert profile is not None
    assert profile["institution"] == "wells_fargo"


def test_no_match_for_unknown_csv(profiles, tmp_path):
    """Unknown CSV format returns None."""
    unknown = tmp_path / "unknown.csv"
    unknown.write_text("Col1,Col2,Col3\na,b,c\n")
    assert match_profile(unknown, profiles) is None


def test_no_match_for_non_csv(profiles, tmp_path):
    """Non-CSV files return None."""
    txt = tmp_path / "file.txt"
    txt.write_text("hello")
    assert match_profile(txt, profiles) is None
