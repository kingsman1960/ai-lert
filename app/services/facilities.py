from __future__ import annotations

import math
import asyncio
from typing import Any

import httpx


OVERPASS_URL = "https://overpass-api.de/api/interpreter"

FACILITY_CATEGORIES = {
    "hospital": "Hospital",
    "emergency": "Emergency care",
    "pharmacy": "Pharmacy",
    "fire_station": "Fire station",
    "police": "Police",
    "thw": "THW",
}

FACILITY_PRIORITY = {
    "Emergency care": 0,
    "Hospital": 1,
    "THW": 2,
    "Fire station": 3,
    "Police": 4,
    "Pharmacy": 5,
}


async def fetch_nearby_facilities(latitude: float, longitude: float) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        data_sets = await asyncio.gather(
            _run_overpass_query(
                client,
                f"""
[out:json][timeout:20];
(
  nwr(around:7000,{latitude},{longitude})[amenity=hospital];
  nwr(around:7000,{latitude},{longitude})[healthcare=hospital];
);
out center 30;
""".strip(),
            ),
            _run_overpass_query(
                client,
                f"""
[out:json][timeout:20];
(
  nwr(around:15000,{latitude},{longitude})[name~"Technisches Hilfswerk|THW",i];
  nwr(around:15000,{latitude},{longitude})[operator~"Technisches Hilfswerk|THW",i];
);
out center 20;
""".strip(),
            ),
            _run_overpass_query(
                client,
                f"""
[out:json][timeout:20];
(
  nwr(around:5000,{latitude},{longitude})[amenity=fire_station];
  nwr(around:3500,{latitude},{longitude})[amenity=police];
  nwr(around:3500,{latitude},{longitude})[amenity=pharmacy];
);
out center 40;
""".strip(),
            ),
            return_exceptions=True,
        )

    facilities = []
    for dataset in data_sets:
        if isinstance(dataset, Exception):
            continue
        for element in dataset.get("elements", []):
            tags = element.get("tags") or {}
            name = tags.get("name")
            lat, lon = _extract_coordinates(element)
            if not name or lat is None or lon is None:
                continue

            category = _resolve_category(tags)
            if category is None:
                continue

            facilities.append(
                {
                    "name": name,
                    "category": category,
                    "latitude": float(lat),
                    "longitude": float(lon),
                    "distance_km": round(
                        _haversine_km(latitude, longitude, float(lat), float(lon)), 2
                    ),
                    "address": _build_address(tags),
                }
            )

    deduped = _dedupe_facilities(facilities)
    deduped.sort(
        key=lambda facility: (
            FACILITY_PRIORITY.get(facility["category"], 99),
            facility["distance_km"],
        )
    )
    return deduped[:12]


async def _run_overpass_query(
    client: httpx.AsyncClient, query: str
) -> dict[str, Any]:
    response = await client.post(
        OVERPASS_URL,
        data={"data": query},
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "GeoAX/0.1",
        },
    )
    response.raise_for_status()
    return response.json()


def _build_address(tags: dict[str, Any]) -> str | None:
    parts = [
        " ".join(
            part
            for part in [tags.get("addr:street"), tags.get("addr:housenumber")]
            if part
        ).strip()
        or None,
        tags.get("addr:postcode"),
        tags.get("addr:city"),
    ]
    cleaned = [part for part in parts if part]
    return ", ".join(cleaned) if cleaned else None


def _extract_coordinates(element: dict[str, Any]) -> tuple[float | None, float | None]:
    lat = element.get("lat")
    lon = element.get("lon")
    if lat is not None and lon is not None:
        return float(lat), float(lon)

    center = element.get("center") or {}
    center_lat = center.get("lat")
    center_lon = center.get("lon")
    if center_lat is not None and center_lon is not None:
        return float(center_lat), float(center_lon)
    return None, None


def _resolve_category(tags: dict[str, Any]) -> str | None:
    amenity = tags.get("amenity")
    operator = (tags.get("operator") or "").lower()
    name = (tags.get("name") or "").lower()
    healthcare = tags.get("healthcare")

    if "technisches hilfswerk" in operator or " thw" in f" {name}":
        return FACILITY_CATEGORIES["thw"]
    if amenity == "hospital" or healthcare == "hospital":
        return FACILITY_CATEGORIES["hospital"]
    if amenity in FACILITY_CATEGORIES:
        return FACILITY_CATEGORIES[amenity]
    return None


def _dedupe_facilities(facilities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for facility in facilities:
        key = (facility["name"], facility["category"])
        existing = deduped.get(key)
        if existing is None or facility["distance_km"] < existing["distance_km"]:
            deduped[key] = facility
    return list(deduped.values())


def _haversine_km(
    latitude_1: float, longitude_1: float, latitude_2: float, longitude_2: float
) -> float:
    radius_km = 6371.0
    lat1 = math.radians(latitude_1)
    lon1 = math.radians(longitude_1)
    lat2 = math.radians(latitude_2)
    lon2 = math.radians(longitude_2)
    d_lat = lat2 - lat1
    d_lon = lon2 - lon1
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_km * c
