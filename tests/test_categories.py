"""Tests for category mapping and keyword-based fallback classification."""

import pytest

from fin_insights.categories import UNCATEGORIZED, map_category


@pytest.fixture
def global_mappings():
    """Sample global mappings for testing."""
    return {
        "chase": {
            "Food & Drink": ["Food & Dining", "Restaurants"],
            "Gas": ["Transportation", "Gas"],
        },
        "_keyword_fallback": {
            "STARBUCKS|DUNKIN|COFFEE": ["Food & Dining", "Coffee"],
            "UBER|LYFT": ["Transportation", "Rideshare"],
            "NETFLIX|HULU|SPOTIFY": ["Entertainment", "Streaming"],
        },
    }


def test_profile_level_mapping():
    """Profile-level mappings take highest priority."""
    profile_mappings = {
        "Merchandise": ["Shopping", "General"],
    }
    result = map_category(
        institution="discover",
        original_category="Merchandise",
        profile_mappings=profile_mappings,
        global_mappings={},
        description="AMAZON",
    )
    assert result == ("Shopping", "General")


def test_global_institution_mapping(global_mappings):
    """Global institution-specific mappings work."""
    result = map_category(
        institution="chase",
        original_category="Food & Drink",
        profile_mappings=None,
        global_mappings=global_mappings,
        description="CHIPOTLE",
    )
    assert result == ("Food & Dining", "Restaurants")


def test_keyword_fallback(global_mappings):
    """Keyword fallback matches on description when no category mapping exists."""
    result = map_category(
        institution="unknown_bank",
        original_category=None,
        profile_mappings=None,
        global_mappings=global_mappings,
        description="STARBUCKS #1234",
    )
    assert result == ("Food & Dining", "Coffee")


def test_keyword_fallback_case_insensitive(global_mappings):
    """Keyword fallback is case-insensitive."""
    result = map_category(
        institution="unknown_bank",
        original_category=None,
        profile_mappings=None,
        global_mappings=global_mappings,
        description="netflix subscription",
    )
    assert result == ("Entertainment", "Streaming")


def test_original_category_passthrough(global_mappings):
    """Unmapped original categories are passed through as-is."""
    result = map_category(
        institution="amex",
        original_category="Business Services",
        profile_mappings=None,
        global_mappings=global_mappings,
        description="ACME CORP",
    )
    assert result == ("Business Services", None)


def test_uncategorized_fallback(global_mappings):
    """No category and no keyword match returns UNCATEGORIZED."""
    result = map_category(
        institution="unknown_bank",
        original_category=None,
        profile_mappings=None,
        global_mappings=global_mappings,
        description="RANDOM MERCHANT XYZ",
    )
    assert result == UNCATEGORIZED


def test_profile_takes_priority_over_global(global_mappings):
    """Profile mappings override global institution mappings."""
    profile_mappings = {
        "Food & Drink": ["Food & Dining", "Fast Food"],
    }
    result = map_category(
        institution="chase",
        original_category="Food & Drink",
        profile_mappings=profile_mappings,
        global_mappings=global_mappings,
        description="MCDONALDS",
    )
    # Profile says "Fast Food", global says "Restaurants" — profile wins
    assert result == ("Food & Dining", "Fast Food")


def test_subcategory_none_when_single_element():
    """Profile mapping with single element returns None subcategory."""
    profile_mappings = {
        "Other": ["Shopping"],
    }
    result = map_category(
        institution="discover",
        original_category="Other",
        profile_mappings=profile_mappings,
        global_mappings={},
        description="STORE",
    )
    assert result == ("Shopping", None)
