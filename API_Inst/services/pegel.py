from __future__ import annotations

import math
import os
from typing import Any

import httpx


PEGELONLINE_BASE_URL = os.getenv(
    "PEGELONLINE_BASE_URL", "https://www.pegelonline.wsv.de/webservices/rest-api/v2"
)
HEILBRONN_STATION_UUID = "f77df170-d23a-451c-9c43-b1580ccd3e2c"
HEILBRONN_STATION_NUMBER = "23800560"
HEILBRONN_STATION_COORDINATES = {
    "latitude": 49.13696,
    "longitude": 9.19921,
}


async def fetch_water_context(location: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=25.0) as client:
        stations_response = await client.get(f"{PEGELONLINE_BASE_URL}/stations.json")
        stations_response.raise_for_status()
        stations = stations_response.json()

        station = _select_best_station(
            stations,
            location["latitude"],
            location["longitude"],
            city=location.get("city"),
            state=location.get("state"),
        )
        current = await _fetch_current_measurement(client, station["uuid"])
        recent = await _fetch_recent_measurements(client, station["uuid"])

    trend = _compute_24h_trend(recent)
    trend_label = _trend_label(trend)
    distance_km = _haversine_km(
        location["latitude"],
        location["longitude"],
        station["latitude"],
        station["longitude"],
    )
    state = current.get("stateMnwMhw") or "unknown"
    summary = _build_summary(station, current, trend, distance_km)

    return {
        "gauge_id": station["uuid"],
        "gauge_name": station["longname"],
        "water_name": (station.get("water") or {}).get("longname"),
        "gauge_latitude": station.get("latitude"),
        "gauge_longitude": station.get("longitude"),
        "distance_km": round(distance_km, 1),
        "current_level_cm": current.get("value"),
        "level_timestamp": current.get("timestamp"),
        "state_mnw_mhw": state,
        "state_nsw_hsw": current.get("stateNswHsw"),
        "trend_cm_24h": None if trend is None else round(trend, 1),
        "trend_label": trend_label,
        "history": _sample_history(recent),
        "summary": summary,
    }


async def _fetch_current_measurement(
    client: httpx.AsyncClient, station_id: str
) -> dict[str, Any]:
    response = await client.get(
        f"{PEGELONLINE_BASE_URL}/stations/{station_id}/W/currentmeasurement.json"
    )
    response.raise_for_status()
    return response.json()


async def _fetch_recent_measurements(
    client: httpx.AsyncClient, station_id: str
) -> list[dict[str, Any]]:
    response = await client.get(
        f"{PEGELONLINE_BASE_URL}/stations/{station_id}/W/measurements.json",
        params={"start": "P2D"},
    )
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, list) else []


def _select_best_station(
    stations: list[dict[str, Any]],
    latitude: float,
    longitude: float,
    city: str | None = None,
    state: str | None = None,
) -> dict[str, Any]:
    if _is_stadt_heilbronn(city, state):
        heilbronn_station = _resolve_heilbronn_station(stations)
        if heilbronn_station is not None:
            return heilbronn_station

    candidates: list[tuple[tuple[int, float], dict[str, Any]]] = []

    for station in stations:
        station_lat = station.get("latitude")
        station_lon = station.get("longitude")
        if station_lat is None or station_lon is None:
            continue

        water = (station.get("water") or {}).get("longname", "")
        distance = _haversine_km(latitude, longitude, station_lat, station_lon)
        neckar_priority = 0 if "NECKAR" in water.upper() else 1
        candidates.append(((neckar_priority, distance), station))

    if not candidates:
        raise RuntimeError("No PEGELONLINE stations could be evaluated.")

    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def _resolve_heilbronn_station(
    stations: list[dict[str, Any]],
) -> dict[str, Any] | None:
    for station in stations:
        if station.get("uuid") == HEILBRONN_STATION_UUID or station.get("number") == HEILBRONN_STATION_NUMBER:
            return {
                **station,
                "latitude": HEILBRONN_STATION_COORDINATES["latitude"],
                "longitude": HEILBRONN_STATION_COORDINATES["longitude"],
            }
    return None


def _is_stadt_heilbronn(city: str | None, state: str | None) -> bool:
    city_text = (city or "").strip().lower()
    state_text = (
        (state or "")
        .strip()
        .lower()
        .replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
    )
    return city_text == "heilbronn" and "baden-wuerttemberg" in state_text


def _compute_24h_trend(measurements: list[dict[str, Any]]) -> float | None:
    if len(measurements) < 2:
        return None

    first_value = measurements[0].get("value")
    last_value = measurements[-1].get("value")
    if first_value is None or last_value is None:
        return None
    return float(last_value) - float(first_value)


def _trend_label(trend: float | None) -> str:
    if trend is None:
        return "unknown"
    if trend > 10:
        return "rising"
    if trend < -10:
        return "falling"
    return "steady"


def _build_summary(
    station: dict[str, Any],
    current: dict[str, Any],
    trend: float | None,
    distance_km: float,
) -> str:
    level = current.get("value")
    state = current.get("stateMnwMhw") or "unknown"
    trend_label = _trend_label(trend)
    if level is None:
        return (
            f"The nearest gauge is {station['longname']}, about {distance_km:.1f} km away, "
            "but no current water level could be read."
        )

    return (
        f"The nearest relevant gauge is {station['longname']} on the "
        f"{(station.get('water') or {}).get('longname', 'nearby waterway')}, "
        f"about {distance_km:.1f} km away. The current level is {level:.0f} cm, "
        f"which is currently classified as {state}. Over the past 24-48 hours the "
        f"trend appears {trend_label}."
    )


def _sample_history(measurements: list[dict[str, Any]], target_points: int = 24) -> list[dict[str, Any]]:
    if not measurements:
        return []

    step = max(1, len(measurements) // target_points)
    sampled = measurements[::step]
    if sampled[-1] != measurements[-1]:
        sampled.append(measurements[-1])

    return [
        {"timestamp": point["timestamp"], "value": float(point["value"])}
        for point in sampled
        if point.get("timestamp") is not None and point.get("value") is not None
    ]


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
