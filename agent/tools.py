from __future__ import annotations

from datetime import date
from langchain.tools import tool


@tool
def today_date() -> str:
    """Return today's date in ISO format (YYYY-MM-DD)."""
    return date.today().isoformat()


@tool
def estimate_trip_cost(nights: int, adults: int = 2) -> str:
    """
    Estimate total cost for a simple demo trip.
    Pricing rule (demo): 80 EUR/night for 2 adults, +15 EUR/night for each extra adult.
    """
    base_per_night = 80
    extra_adult_fee = max(0, adults - 2) * 15
    total = nights * (base_per_night + extra_adult_fee)
    return f"Estimated total: {total} EUR for {nights} night(s), {adults} adult(s)."
