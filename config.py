"""Shared constants for the dashboard and the data-fetch script."""
from __future__ import annotations

TOPIC_GROUPS: dict[str, list[str]] = {
    "Contaminants": [
        "PFAS",
        "forever chemicals",
        "lead in water",
        "arsenic in water",
        "nitrate in water",
        "microplastics",
        "fluoride in water",
        "chromium 6",
    ],
    "Context / source": [
        "well water testing",
        "hard water",
        "bottled water",
    ],
    "Product Categories": [
        "water filter",
        "reverse osmosis",
        "water softener",
        "whole house water filter",
    ],
}

ALL_TOPICS: list[str] = [t for group in TOPIC_GROUPS.values() for t in group]

TIMEFRAMES: dict[str, str] = {
    "Last 3 months": "today 3-m",
    "Last 12 months": "today 12-m",
    "Last 2 years": "today 24-m",
    "Last 5 years": "today 5-y",
}

BATCH_SIZE = 5
GEO = "US"
