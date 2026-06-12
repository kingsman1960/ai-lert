from __future__ import annotations

import math
from typing import Any

import httpx


UBA_STATIONS_URL = (
    "https://www.umweltbundesamt.de/api/air_data/v4/stations/json"
)
UBA_AIRQUALITY_URL = (
    "https://www.umweltbundesamt.de/api/air_data/v2/airquality/json"
)

COMPONENT_CODES = {
    1: "PM10",
    3: "O3",
    5: "NO2",
    9: "PM2.5",
}

INDEX_LABELS = {
    1: "very good",
    2: "good",
    3: "moderate",
    4: "poor",
    5: "very poor",
}


async def fetch_air_quality_context(latitude: float, longitude: float) -> dict[str, Any]:
    params = {"date_from": _yesterday_ymd(), "date_to": _today_ymd()}

    async with httpx.AsyncClient(timeout=30.0) as client:
        stations_response = await client.get(UBA_STATIONS_URL, params=params)
        stations_response.raise_for_status()
        stations = stations_response.json()["data"]

        air_response = await client.get(UBA_AIRQUALITY_URL, params=params)
        air_response.raise_for_status()
        air_data = air_response.json()["data"]

    available_station_ids = set(air_data.keys())
    nearest_station = _find_nearest_station_with_data(
        stations, available_station_ids, latitude, longitude
    )
    station_id = nearest_station["station_id"]
    latest_timestamp, overall_index, latest_components = _extract_latest_components(
        air_data[station_id]
    )

    components = []
    for component_id, component_entry in latest_components.items():
        component_index = component_entry.get("index")
        components.append(
            {
                "code": COMPONENT_CODES.get(component_id, str(component_id)),
                "value": float(component_entry["value"]),
                "index": component_index,
                "label": INDEX_LABELS.get(component_index, "measured"),
            }
        )

    overall_label = INDEX_LABELS.get(overall_index, "measured") if overall_index else None
    summary = (
        f"Nearest UBA air-quality station is {nearest_station['station_name']} in "
        f"{nearest_station['station_city']}, about {nearest_station['distance_km']:.1f} km away. "
        f"The latest overall air-quality signal is {overall_label or 'available'}."
    )

    return {
        "provider": "UBA",
        "status": "live",
        "station_id": station_id,
        "station_name": nearest_station["station_name"],
        "station_city": nearest_station["station_city"],
        "distance_km": round(nearest_station["distance_km"], 1),
        "overall_index": overall_index,
        "overall_label": overall_label,
        "components": sorted(components, key=lambda item: item["code"]),
        "summary": summary,
    }


def _find_nearest_station_with_data(
    stations: dict[str, list[Any]],
    available_station_ids: set[str],
    latitude: float,
    longitude: float,
) -> dict[str, Any]:
    best: dict[str, Any] | None = None
    best_distance = float("inf")

    for station_id, row in stations.items():
        if station_id not in available_station_ids:
            continue

        try:
            station_longitude = float(row[7])
            station_latitude = float(row[8])
        except (TypeError, ValueError, IndexError):
            continue

        distance = _haversine_km(
            latitude, longitude, station_latitude, station_longitude
        )
        if distance < best_distance:
            best_distance = distance
            best = {
                "station_id": station_id,
                "station_name": row[2],
                "station_city": row[3],
                "latitude": station_latitude,
                "longitude": station_longitude,
                "distance_km": distance,
            }

    if best is None:
        raise RuntimeError("No nearby UBA station with air-quality data was found.")
    return best


def _extract_latest_components(
    station_series: dict[str, list[Any]],
) -> tuple[str, int | None, dict[int, dict[str, Any]]]:
    latest_timestamp = sorted(station_series.keys())[-1]
    raw = station_series[latest_timestamp]
    overall_index = int(raw[1]) if len(raw) > 1 and raw[1] is not None else None
    grouped: dict[int, dict[str, Any]] = {}

    for component_raw in raw[3:]:
        if not isinstance(component_raw, list) or len(component_raw) < 3:
            continue
        component_id = int(component_raw[0])
        value = float(component_raw[1])
        component_index = (
            int(component_raw[2]) if component_raw[2] is not None else None
        )
        grouped[component_id] = {"value": value, "index": component_index}

    return latest_timestamp, overall_index, grouped


def _today_ymd() -> str:
    from datetime import datetime

    return datetime.now().strftime("%Y-%m-%d")


def _yesterday_ymd() -> str:
    from datetime import datetime, timedelta

    return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")


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
