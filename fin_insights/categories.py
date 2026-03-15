"""Category mapping and keyword-based fallback classification."""

import json
from pathlib import Path

from fin_insights.config import get_builtin_config_dir, get_user_config_dir

# Default fallback when no category match is found
UNCATEGORIZED = ("Uncategorized", "General")


def load_category_mappings(data_dir: Path) -> dict:
    """Load category mappings, merging user overrides on top of built-in defaults."""
    builtin_path = get_builtin_config_dir() / "category_mappings.json"
    user_path = get_user_config_dir(data_dir) / "category_mappings.json"

    mappings = {}
    if builtin_path.exists():
        mappings = json.loads(builtin_path.read_text())

    # User overrides merge on top
    if user_path.exists():
        user_mappings = json.loads(user_path.read_text())
        for key, val in user_mappings.items():
            if key in mappings and isinstance(val, dict) and isinstance(mappings[key], dict):
                mappings[key].update(val)
            else:
                mappings[key] = val

    return mappings


def map_category(
    institution: str,
    original_category: str | None,
    profile_mappings: dict | None,
    global_mappings: dict,
    description: str = "",
) -> tuple[str, str | None]:
    """Map an institution's category to unified (category, subcategory).

    Tries in order:
    1. Profile-level category_mappings
    2. Global institution-specific mappings
    3. Keyword fallback rules
    4. Returns UNCATEGORIZED
    """
    # 1. Profile-level mappings
    if original_category and profile_mappings:
        match = profile_mappings.get(original_category)
        if match:
            return (match[0], match[1] if len(match) > 1 else None)

    # 2. Global institution-specific mappings
    if original_category and institution in global_mappings:
        inst_map = global_mappings[institution]
        match = inst_map.get(original_category)
        if match:
            return (match[0], match[1] if len(match) > 1 else None)

    # 3. Keyword fallback
    keyword_rules = global_mappings.get("_keyword_fallback", {})
    desc_upper = description.upper()
    for keywords_str, category_pair in keyword_rules.items():
        keywords = [k.strip() for k in keywords_str.split("|")]
        if any(kw in desc_upper for kw in keywords):
            return (category_pair[0], category_pair[1] if len(category_pair) > 1 else None)

    # 4. If we have an original category but no mapping, use it as-is
    if original_category:
        return (original_category, None)

    return UNCATEGORIZED
