from __future__ import annotations
import math
from typing import Any

import httpx


OVERPASS_URL = "https://overpass-api.de/api/interpreter"
HEILBRONN_CENTER = (49.142291, 9.218655)
HEILBRONN_FLOOD_LANDMARKS = [
    {
        "name": "Wartberg",
        "category": "Higher ground candidate",
        "latitude": 49.1597039,
        "longitude": 9.2354186,
        "address": "74076 Heilbronn",
        "note": "Prominent nearby hill above the inner city and useful as a quick uphill orientation point.",
    },
    {
        "name": "Stiftsberg",
        "category": "Higher ground candidate",
        "latitude": 49.168226,
        "longitude": 9.2314548,
        "address": None,
        "note": "Elevated ground north of central Heilbronn and away from immediate riverside low points.",
    },
    {
        "name": "Berufsfeuerwehr Heilbronn",
        "category": "Public-service landmark",
        "latitude": 49.151373,
        "longitude": 9.205776,
        "address": "Beethovenstrasse 29, 74074 Heilbronn",
        "note": "Not a public shelter, but a recognizable uphill public-service location away from low river corridors.",
    },
]
FLOOD_CATEGORY_PRIORITY = {
    "Higher ground candidate": 0,
    "Public-service landmark": 1,
    "Potential refuge point": 2,
    "Public refuge candidate": 3,
}


async def fetch_scenario_places(
    latitude: float, longitude: float, scenario_code: str
) -> list[dict[str, Any]]:
    query = _query_for_scenario(latitude, longitude, scenario_code)
    if not query:
        return []

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            OVERPASS_URL,
            data={"data": query},
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "GeoAX/0.1",
            },
        )
        response.raise_for_status()
        payload = response.json()

    places = []
    for element in payload.get("elements", []):
        tags = element.get("tags") or {}
        name = tags.get("name")
        lat, lon = _extract_coordinates(element)
        if not name or lat is None or lon is None:
            continue

        category, note = _categorize_scenario_place(tags, scenario_code)
        if category is None:
            continue

        places.append(
            {
                "name": name,
                "category": category,
                "latitude": lat,
                "longitude": lon,
                "distance_km": round(_haversine_km(latitude, longitude, lat, lon), 2),
                "address": _build_address(tags),
                "note": note,
            }
        )

    deduped = _dedupe_places(places)
    if scenario_code == "flood":
        deduped = _merge_heilbronn_flood_landmarks(latitude, longitude, deduped)
        deduped.sort(
            key=lambda place: (
                FLOOD_CATEGORY_PRIORITY.get(place["category"], 99),
                place["distance_km"],
            )
        )
    else:
        deduped.sort(key=lambda place: place["distance_km"])
    return deduped[:8]


def _query_for_scenario(latitude: float, longitude: float, scenario_code: str) -> str | None:
    if scenario_code == "heat":
        return f"""
[out:json][timeout:20];
(
  nwr(around:3500,{latitude},{longitude})[amenity=library];
  nwr(around:3500,{latitude},{longitude})[amenity=community_centre];
  nwr(around:3500,{latitude},{longitude})[leisure=swimming_pool];
  nwr(around:3500,{latitude},{longitude})[amenity=drinking_water];
  nwr(around:4500,{latitude},{longitude})[leisure=park];
);
out center 40;
""".strip()

    if scenario_code == "flood":
        return f"""
[out:json][timeout:20];
(
  nwr(around:6000,{latitude},{longitude})[natural=peak];
  nwr(around:6000,{latitude},{longitude})[natural=hill];
  nwr(around:6000,{latitude},{longitude})[tourism=viewpoint];
  nwr(around:5000,{latitude},{longitude})[amenity=fire_station];
  nwr(around:10000,{latitude},{longitude})[amenity=shelter];
  nwr(around:10000,{latitude},{longitude})[emergency=assembly_point];
  nwr(around:10000,{latitude},{longitude})[amenity=community_centre];
  nwr(around:10000,{latitude},{longitude})[amenity=townhall];
);
out center 40;
""".strip()

    if scenario_code == "storm":
        return f"""
[out:json][timeout:20];
(
  nwr(around:7000,{latitude},{longitude})[amenity=shelter];
  nwr(around:7000,{latitude},{longitude})[amenity=community_centre];
  nwr(around:7000,{latitude},{longitude})[amenity=townhall];
  nwr(around:7000,{latitude},{longitude})[amenity=library];
  nwr(around:7000,{latitude},{longitude})[amenity=school];
);
out center 40;
""".strip()

    if scenario_code == "air":
        return f"""
[out:json][timeout:20];
(
  nwr(around:5000,{latitude},{longitude})[amenity=pharmacy];
  nwr(around:7000,{latitude},{longitude})[amenity=hospital];
  nwr(around:7000,{latitude},{longitude})[healthcare=hospital];
  nwr(around:5000,{latitude},{longitude})[amenity=library];
  nwr(around:5000,{latitude},{longitude})[amenity=community_centre];
);
out center 40;
""".strip()

    return None


def _categorize_scenario_place(
    tags: dict[str, Any], scenario_code: str
) -> tuple[str | None, str | None]:
    amenity = tags.get("amenity")
    leisure = tags.get("leisure")
    natural = tags.get("natural")
    tourism = tags.get("tourism")
    emergency = tags.get("emergency")

    if scenario_code == "heat":
        if amenity == "library":
            return "Cooling space", "Indoor public space with shade."
        if amenity == "community_centre":
            return "Cooling space", "Indoor community building."
        if leisure == "swimming_pool":
            return "Cooling space", "Swimming or water-based heat relief."
        if amenity == "drinking_water":
            return "Hydration point", "Useful for drinking water access."
        if leisure == "park":
            return "Shaded outdoor space", "Use only if conditions remain safe."

    if scenario_code == "flood":
        if amenity == "shelter" or emergency == "assembly_point":
            return "Potential refuge point", "Check official instructions before using it."
        if amenity in {"community_centre", "townhall"}:
            return "Public refuge candidate", "Potential indoor refuge or coordination point."
        if amenity == "fire_station":
            return "Public-service landmark", "Not an official shelter, but often easier to locate quickly while moving uphill."
        if natural in {"peak", "hill"} or tourism == "viewpoint":
            return "Higher ground candidate", "Move away from river-adjacent low ground."

    if scenario_code == "storm":
        if amenity in {"shelter", "community_centre", "townhall", "library", "school"}:
            return "Indoor refuge candidate", "Use sturdy indoor shelter during severe weather."

    if scenario_code == "air":
        if amenity == "pharmacy":
            return "Support service", "Useful if symptoms or medication needs arise."
        if amenity == "hospital" or tags.get("healthcare") == "hospital":
            return "Medical support", "Escalate here if symptoms become severe."
        if amenity in {"library", "community_centre"}:
            return "Indoor refuge candidate", "Lower-exertion indoor public place."

    return None, None


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


def _dedupe_places(places: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for place in places:
        key = (place["name"], place["category"])
        existing = deduped.get(key)
        if existing is None or place["distance_km"] < existing["distance_km"]:
            deduped[key] = place
    return list(deduped.values())


def _merge_heilbronn_flood_landmarks(
    latitude: float, longitude: float, places: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if _haversine_km(latitude, longitude, *HEILBRONN_CENTER) > 10:
        return places

    curated = []
    for landmark in HEILBRONN_FLOOD_LANDMARKS:
        curated.append(
            {
                **landmark,
                "distance_km": round(
                    _haversine_km(
                        latitude,
                        longitude,
                        landmark["latitude"],
                        landmark["longitude"],
                    ),
                    2,
                ),
            }
        )

    return _dedupe_places([*places, *curated])


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
