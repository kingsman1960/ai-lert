from __future__ import annotations

import csv
import io
import math
from typing import Any

import httpx


DWD_STATION_LIST_URL = (
    "https://opendata.dwd.de/weather/weather_reports/stationlist_synoptic_germany.csv"
)
DWD_STATION_OVERVIEW_URL = (
    "https://app-prod-ws.warnwetter.de/v30/stationOverviewExtended"
)

_station_cache: list[dict[str, Any]] | None = None


async def fetch_weather_context(latitude: float, longitude: float) -> dict[str, Any]:
    station = await _find_nearest_station(latitude, longitude)

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            DWD_STATION_OVERVIEW_URL, params={"stationIds": station["station_id"]}
        )
        response.raise_for_status()
        payload = response.json()

    station_payload = payload.get(station["station_id"]) or {}
    forecast = station_payload.get("forecast1") or {}
    today = (station_payload.get("days") or [{}])[0]
    warnings = station_payload.get("warnings") or []

    temperatures = forecast.get("temperature") or []
    precipitation = forecast.get("precipitationTotal") or []
    precipitation_probability = forecast.get("precipitationProbablity") or []

    current_temperature_c = _tenths_to_float(temperatures[0]) if temperatures else None
    daily_min_c = _tenths_to_float(today.get("temperatureMin"))
    daily_max_c = _tenths_to_float(today.get("temperatureMax"))
    next_12h_precipitation_mm = _tenths_series_sum_to_mm(precipitation[:12])
    next_12h_precipitation_probability_pct = (
        int(max(precipitation_probability[:12])) if precipitation_probability else None
    )

    summary_parts = []
    if current_temperature_c is not None:
        summary_parts.append(f"Current temperature near {station['station_name']} is {current_temperature_c:.1f} C.")
    if daily_min_c is not None and daily_max_c is not None:
        summary_parts.append(
            f"Today's forecast range is {daily_min_c:.1f} C to {daily_max_c:.1f} C."
        )
    if next_12h_precipitation_mm is not None:
        summary_parts.append(
            f"The next 12 hours indicate about {next_12h_precipitation_mm:.1f} mm precipitation signal."
        )
    if next_12h_precipitation_probability_pct is not None:
        summary_parts.append(
            f"Peak short-term precipitation probability is around {next_12h_precipitation_probability_pct}%."
        )

    return {
        "provider": "DWD",
        "status": "live",
        "station_id": station["station_id"],
        "station_name": station["station_name"],
        "distance_km": round(station["distance_km"], 1),
        "current_temperature_c": current_temperature_c,
        "daily_min_c": daily_min_c,
        "daily_max_c": daily_max_c,
        "next_12h_precipitation_mm": next_12h_precipitation_mm,
        "next_12h_precipitation_probability_pct": next_12h_precipitation_probability_pct,
        "warning_count": len(warnings),
        "summary": " ".join(summary_parts)
        or "Live DWD data was loaded, but forecast details were limited for this station.",
    }


async def _find_nearest_station(latitude: float, longitude: float) -> dict[str, Any]:
    stations = await _load_station_cache()
    best_station = min(
        stations,
        key=lambda station: _haversine_km(
            latitude, longitude, station["latitude"], station["longitude"]
        ),
    )
    return {
        **best_station,
        "distance_km": _haversine_km(
            latitude, longitude, best_station["latitude"], best_station["longitude"]
        ),
    }


async def _load_station_cache() -> list[dict[str, Any]]:
    global _station_cache
    if _station_cache is not None:
        return _station_cache

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(DWD_STATION_LIST_URL)
        response.raise_for_status()
        raw = response.text

    reader = csv.DictReader(io.StringIO(raw), delimiter=";")
    stations: list[dict[str, Any]] = []
    for row in reader:
        station_id = (row.get("Kennung") or "").strip()
        if not station_id.isdigit():
            continue

        try:
            latitude = float(row["Geog_Breite"])
            longitude = float(row["Geog_Laenge"])
        except (TypeError, ValueError, KeyError):
            continue

        stations.append(
            {
                "station_id": station_id,
                "station_name": (row.get("Stationsname") or station_id).strip(),
                "latitude": latitude,
                "longitude": longitude,
            }
        )

    if not stations:
        raise RuntimeError("Could not load a usable DWD station list.")

    _station_cache = stations
    return stations


def _tenths_to_float(value: Any) -> float | None:
    if value is None:
        return None
    return round(float(value) / 10.0, 1)


def _tenths_series_sum_to_mm(values: list[Any]) -> float | None:
    if not values:
        return None
    return round(sum(float(value) for value in values if value is not None) / 10.0, 1)


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
