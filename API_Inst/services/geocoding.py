from __future__ import annotations

import os
from typing import Any

import httpx


class GeocodingError(RuntimeError):
    pass


GEOCODING_BASE_URL = os.getenv(
    "GEOCODING_BASE_URL", "https://nominatim.openstreetmap.org"
)


async def geocode_query(query: str) -> dict[str, Any]:
    params = {
        "q": query,
        "format": "jsonv2",
        "addressdetails": 1,
        "limit": 1,
        "countrycodes": "de",
    }
    headers = {
        "User-Agent": "GeoAX-BW-Risk-Guide/0.1 (hackathon prototype)"
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            f"{GEOCODING_BASE_URL}/search", params=params, headers=headers
        )
        response.raise_for_status()
        payload = response.json()

    if not payload:
        raise GeocodingError("No matching German location was found.")

    result = payload[0]
    address = result.get("address", {})
    latitude = float(result["lat"])
    longitude = float(result["lon"])

    city = (
        address.get("city")
        or address.get("town")
        or address.get("municipality")
        or address.get("village")
    )
    county = address.get("county")
    state = address.get("state")
    country = address.get("country")

    inside_demo_region = _is_inside_demo_region(city=city, county=county, state=state)

    return {
        "query": query,
        "display_name": result.get("display_name", query),
        "latitude": latitude,
        "longitude": longitude,
        "city": city,
        "county": county,
        "state": state,
        "country": country,
        "inside_demo_region": inside_demo_region,
    }


async def reverse_geocode_coordinates(
    latitude: float, longitude: float, label: str = "Current location"
) -> dict[str, Any]:
    params = {
        "lat": latitude,
        "lon": longitude,
        "format": "jsonv2",
        "addressdetails": 1,
        "zoom": 18,
    }
    headers = {
        "User-Agent": "GeoAX-BW-Risk-Guide/0.1 (hackathon prototype)"
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            f"{GEOCODING_BASE_URL}/reverse", params=params, headers=headers
        )
        response.raise_for_status()
        payload = response.json()

    address = payload.get("address", {})
    city = (
        address.get("city")
        or address.get("town")
        or address.get("municipality")
        or address.get("village")
    )
    county = address.get("county")
    state = address.get("state")
    country = address.get("country")
    inside_demo_region = _is_inside_demo_region(city=city, county=county, state=state)

    return {
        "query": label,
        "display_name": payload.get("display_name", label),
        "latitude": latitude,
        "longitude": longitude,
        "city": city,
        "county": county,
        "state": state,
        "country": country,
        "inside_demo_region": inside_demo_region,
    }


def _is_inside_demo_region(
    city: str | None, county: str | None, state: str | None
) -> bool:
    text = " ".join(part for part in [city, county, state] if part).lower()
    normalized = (
        text.replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
    )
    return "baden-wuerttemberg" in normalized
