from __future__ import annotations

import asyncio
import math
from typing import Any

import httpx


LUBW_FLOOD_QUERY_URL = (
    "https://rips-gdi.lubw.baden-wuerttemberg.de/arcgis/rest/services/"
    "wfs/Ueberschwemmungsgebiet/MapServer/1/query"
)
LUBW_HWEXTREM_IDENTIFY_URL = (
    "https://rips-gdi.lubw.baden-wuerttemberg.de/arcgis/rest/services/"
    "wms/UIS_0100000039300004/MapServer/identify"
)
QUERY_RADIUS_M = 2500
NEARBY_THRESHOLD_M = 400
EXIT_OFFSET_M = 120


async def fetch_flood_evacuation_context(
    latitude: float, longitude: float
) -> dict[str, Any]:
    features, hw_extreme_signal = await _fetch_flood_context_payload(latitude, longitude)
    if not features:
        return {
            "source": "LUBW HQ100 floodplain + HWextrem",
            "status": "outside",
            "summary": (
                "No nearby LUBW HQ100 floodplain polygon was found around this location. "
                "Use official warnings and local topography to stay away from low river corridors."
            ),
            "hq_extreme_considered": True,
            "hq_extreme_at_location": hw_extreme_signal["active"],
            "hq_extreme_pixel_value": hw_extreme_signal["pixel_value"],
            "distance_to_edge_m": None,
            "escape_direction": None,
            "recommended_exit_point": None,
            "route": [],
            "polygons": [],
        }

    containing_feature: dict[str, Any] | None = None
    nearest_boundary_point: tuple[float, float] | None = None
    nearest_distance_m: float | None = None

    for feature in features:
        geometry = feature.get("geometry") or {}
        if geometry.get("type") not in {"Polygon", "MultiPolygon"}:
            continue

        boundary_point, distance_m = _nearest_point_on_geometry(
            geometry, latitude, longitude
        )
        if boundary_point is None or distance_m is None:
            continue

        if nearest_distance_m is None or distance_m < nearest_distance_m:
            nearest_boundary_point = boundary_point
            nearest_distance_m = distance_m

        if _geometry_contains_point(geometry, latitude, longitude):
            containing_feature = feature
            nearest_boundary_point = boundary_point
            nearest_distance_m = distance_m
            break

    polygons = [_feature_to_polygon(feature) for feature in features if feature.get("geometry")]
    if nearest_boundary_point is None:
        return {
            "source": "LUBW HQ100 floodplain + HWextrem",
            "status": "unavailable",
            "summary": "The local LUBW floodplain geometry could not be interpreted for routing.",
            "hq_extreme_considered": True,
            "hq_extreme_at_location": hw_extreme_signal["active"],
            "hq_extreme_pixel_value": hw_extreme_signal["pixel_value"],
            "distance_to_edge_m": None,
            "escape_direction": None,
            "recommended_exit_point": None,
            "route": [],
            "polygons": polygons,
        }

    if containing_feature is not None:
        exit_point = _project_beyond_boundary(
            latitude, longitude, nearest_boundary_point[0], nearest_boundary_point[1]
        )
        route = [
            {"latitude": latitude, "longitude": longitude},
            {
                "latitude": round(nearest_boundary_point[0], 6),
                "longitude": round(nearest_boundary_point[1], 6),
            },
            exit_point,
        ]
        return {
            "source": "LUBW HQ100 floodplain + HWextrem",
            "status": "inside",
            "summary": (
                f"This location sits inside a mapped LUBW HQ100 floodplain. "
                f"Move roughly {_bearing_label(latitude, longitude, exit_point['latitude'], exit_point['longitude'])} "
                f"to leave the mapped inundation area."
                + (
                    " HWextrem depth tiles also indicate possible extreme-flood exposure here."
                    if hw_extreme_signal["active"]
                    else ""
                )
            ),
            "hq_extreme_considered": True,
            "hq_extreme_at_location": hw_extreme_signal["active"],
            "hq_extreme_pixel_value": hw_extreme_signal["pixel_value"],
            "distance_to_edge_m": round(nearest_distance_m, 0),
            "escape_direction": _bearing_label(
                latitude, longitude, exit_point["latitude"], exit_point["longitude"]
            ),
            "recommended_exit_point": exit_point,
            "route": route,
            "polygons": polygons,
        }

    if nearest_distance_m is not None and nearest_distance_m <= NEARBY_THRESHOLD_M:
        exit_point = _project_away_from_boundary(
            latitude, longitude, nearest_boundary_point[0], nearest_boundary_point[1]
        )
        return {
            "source": "LUBW HQ100 floodplain + HWextrem",
            "status": "nearby",
            "summary": (
                f"This location is outside but very close to a mapped LUBW HQ100 floodplain. "
                f"Avoid moving toward the floodplain and bias movement {_bearing_label(latitude, longitude, exit_point['latitude'], exit_point['longitude'])}."
                + (
                    " HWextrem depth tiles also indicate possible extreme-flood exposure at the current point."
                    if hw_extreme_signal["active"]
                    else ""
                )
            ),
            "hq_extreme_considered": True,
            "hq_extreme_at_location": hw_extreme_signal["active"],
            "hq_extreme_pixel_value": hw_extreme_signal["pixel_value"],
            "distance_to_edge_m": round(nearest_distance_m, 0),
            "escape_direction": _bearing_label(
                latitude, longitude, exit_point["latitude"], exit_point["longitude"]
            ),
            "recommended_exit_point": exit_point,
            "route": [
                {"latitude": latitude, "longitude": longitude},
                exit_point,
            ],
            "polygons": polygons,
        }

    return {
        "source": "LUBW HQ100 floodplain + HWextrem",
        "status": "outside",
        "summary": (
            "Nearby LUBW HQ100 floodplain polygons were checked, but this location is not immediately adjacent "
            "to the mapped inundation area."
            + (
                " The HWextrem layer still indicates potential extreme-flood exposure at the current point."
                if hw_extreme_signal["active"]
                else ""
            )
        ),
        "hq_extreme_considered": True,
        "hq_extreme_at_location": hw_extreme_signal["active"],
        "hq_extreme_pixel_value": hw_extreme_signal["pixel_value"],
        "distance_to_edge_m": round(nearest_distance_m, 0) if nearest_distance_m is not None else None,
        "escape_direction": None,
        "recommended_exit_point": None,
        "route": [],
        "polygons": polygons,
    }


async def prioritize_places_by_hwextrem(
    latitude: float, longitude: float, places: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if not places:
        return []

    signals = await _sample_hwextrem_points(
        [(latitude, longitude), *[(place["latitude"], place["longitude"]) for place in places]]
    )
    place_signals = signals[1:]

    ranked = []
    for place, signal in zip(places, place_signals, strict=False):
        updated = dict(place)
        if signal["active"]:
            note_prefix = "Inside or touching the HWextrem depth layer. "
            updated["note"] = note_prefix + (updated.get("note") or "Prefer a safer nearby high-ground option.")
            updated["_hwextreme_penalty"] = 1
        else:
            updated["_hwextreme_penalty"] = 0
        ranked.append(updated)

    ranked.sort(key=lambda place: (place["_hwextreme_penalty"], place["distance_km"]))
    for place in ranked:
        place.pop("_hwextreme_penalty", None)
    return ranked


async def _fetch_flood_context_payload(
    latitude: float, longitude: float
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        features_task = _fetch_local_floodplain_features(latitude, longitude, client)
        extreme_task = _sample_hwextrem_signal(latitude, longitude, client)
        features, extreme_signal = await asyncio.gather(features_task, extreme_task)
    return features, extreme_signal


async def _fetch_local_floodplain_features(
    latitude: float, longitude: float, client: httpx.AsyncClient
) -> list[dict[str, Any]]:
    delta_lat = QUERY_RADIUS_M / 111_320
    delta_lon = QUERY_RADIUS_M / (111_320 * max(math.cos(math.radians(latitude)), 0.2))
    bbox = (
        f"{longitude - delta_lon},{latitude - delta_lat},"
        f"{longitude + delta_lon},{latitude + delta_lat}"
    )
    params = {
        "f": "geojson",
        "where": "1=1",
        "outFields": "OBJECTID,CODE,BG_LD",
        "geometry": bbox,
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outSR": "4326",
        "resultRecordCount": "8",
        "geometryPrecision": "6",
        "maxAllowableOffset": "0.00008",
    }

    response = await client.get(LUBW_FLOOD_QUERY_URL, params=params)
    response.raise_for_status()
    payload = response.json()

    return payload.get("features", [])


async def _sample_hwextrem_points(
    points: list[tuple[float, float]]
) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        tasks = [_sample_hwextrem_signal(lat, lon, client) for lat, lon in points]
        return await asyncio.gather(*tasks)


async def _sample_hwextrem_signal(
    latitude: float, longitude: float, client: httpx.AsyncClient
) -> dict[str, Any]:
    params = {
        "f": "pjson",
        "geometry": f"{longitude},{latitude}",
        "geometryType": "esriGeometryPoint",
        "sr": "4326",
        "mapExtent": f"{longitude - 0.02},{latitude - 0.02},{longitude + 0.02},{latitude + 0.02}",
        "imageDisplay": "800,800,96",
        "tolerance": "3",
        "layers": "all:0",
        "returnGeometry": "false",
    }
    response = await client.get(LUBW_HWEXTREM_IDENTIFY_URL, params=params)
    response.raise_for_status()
    payload = response.json()
    result = ((payload.get("results") or [{}])[0]).get("attributes", {})
    pixel_value = result.get("UniqueValue.Pixel Value")
    active = pixel_value not in {None, "NoData"}
    return {"active": active, "pixel_value": pixel_value}


def _feature_to_polygon(feature: dict[str, Any]) -> dict[str, Any]:
    geometry = feature.get("geometry") or {}
    return {
        "geometry_type": geometry.get("type"),
        "coordinates": geometry.get("coordinates", []),
    }


def _geometry_contains_point(
    geometry: dict[str, Any], latitude: float, longitude: float
) -> bool:
    if geometry.get("type") == "Polygon":
        return _polygon_contains_point(geometry.get("coordinates", []), latitude, longitude)
    if geometry.get("type") == "MultiPolygon":
        return any(
            _polygon_contains_point(polygon, latitude, longitude)
            for polygon in geometry.get("coordinates", [])
        )
    return False


def _polygon_contains_point(
    polygon: list[list[list[float]]], latitude: float, longitude: float
) -> bool:
    if not polygon:
        return False
    outer_ring = polygon[0]
    if not _ring_contains_point(outer_ring, latitude, longitude):
        return False
    for hole in polygon[1:]:
        if _ring_contains_point(hole, latitude, longitude):
            return False
    return True


def _ring_contains_point(
    ring: list[list[float]], latitude: float, longitude: float
) -> bool:
    inside = False
    x = longitude
    y = latitude

    for index in range(len(ring)):
        x1, y1 = ring[index]
        x2, y2 = ring[(index + 1) % len(ring)]
        intersects = ((y1 > y) != (y2 > y)) and (
            x < ((x2 - x1) * (y - y1) / ((y2 - y1) or 1e-12) + x1)
        )
        if intersects:
            inside = not inside
    return inside


def _nearest_point_on_geometry(
    geometry: dict[str, Any], latitude: float, longitude: float
) -> tuple[tuple[float, float] | None, float | None]:
    polygons = []
    if geometry.get("type") == "Polygon":
        polygons = [geometry.get("coordinates", [])]
    elif geometry.get("type") == "MultiPolygon":
        polygons = geometry.get("coordinates", [])

    nearest_point = None
    nearest_distance = None
    for polygon in polygons:
        for ring in polygon:
            candidate_point, candidate_distance = _nearest_point_on_ring(
                ring, latitude, longitude
            )
            if candidate_point is None or candidate_distance is None:
                continue
            if nearest_distance is None or candidate_distance < nearest_distance:
                nearest_point = candidate_point
                nearest_distance = candidate_distance
    return nearest_point, nearest_distance


def _nearest_point_on_ring(
    ring: list[list[float]], latitude: float, longitude: float
) -> tuple[tuple[float, float] | None, float | None]:
    if len(ring) < 2:
        return None, None

    nearest_point = None
    nearest_distance = None
    for index in range(len(ring) - 1):
        lon1, lat1 = ring[index]
        lon2, lat2 = ring[index + 1]
        point, distance_m = _nearest_point_on_segment(
            latitude, longitude, lat1, lon1, lat2, lon2
        )
        if nearest_distance is None or distance_m < nearest_distance:
            nearest_point = point
            nearest_distance = distance_m
    return nearest_point, nearest_distance


def _nearest_point_on_segment(
    latitude: float,
    longitude: float,
    segment_lat_1: float,
    segment_lon_1: float,
    segment_lat_2: float,
    segment_lon_2: float,
) -> tuple[tuple[float, float], float]:
    reference_lat = latitude
    px, py = _project_xy(latitude, longitude, reference_lat, longitude)
    ax, ay = _project_xy(segment_lat_1, segment_lon_1, reference_lat, longitude)
    bx, by = _project_xy(segment_lat_2, segment_lon_2, reference_lat, longitude)
    dx = bx - ax
    dy = by - ay
    length_sq = dx * dx + dy * dy

    if length_sq <= 1e-9:
        nearest_x = ax
        nearest_y = ay
    else:
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
        nearest_x = ax + t * dx
        nearest_y = ay + t * dy

    nearest_lat, nearest_lon = _unproject_xy(nearest_x, nearest_y, reference_lat, longitude)
    distance_m = math.hypot(px - nearest_x, py - nearest_y)
    return (nearest_lat, nearest_lon), distance_m


def _project_beyond_boundary(
    start_lat: float, start_lon: float, boundary_lat: float, boundary_lon: float
) -> dict[str, float]:
    x1, y1 = _project_xy(start_lat, start_lon, start_lat, start_lon)
    x2, y2 = _project_xy(boundary_lat, boundary_lon, start_lat, start_lon)
    dx = x2 - x1
    dy = y2 - y1
    length = max(math.hypot(dx, dy), 1e-6)
    x3 = x2 + (dx / length) * EXIT_OFFSET_M
    y3 = y2 + (dy / length) * EXIT_OFFSET_M
    lat3, lon3 = _unproject_xy(x3, y3, start_lat, start_lon)
    return {"latitude": round(lat3, 6), "longitude": round(lon3, 6)}


def _project_away_from_boundary(
    start_lat: float, start_lon: float, boundary_lat: float, boundary_lon: float
) -> dict[str, float]:
    x1, y1 = _project_xy(start_lat, start_lon, start_lat, start_lon)
    x2, y2 = _project_xy(boundary_lat, boundary_lon, start_lat, start_lon)
    dx = x1 - x2
    dy = y1 - y2
    length = max(math.hypot(dx, dy), 1e-6)
    x3 = x1 + (dx / length) * EXIT_OFFSET_M
    y3 = y1 + (dy / length) * EXIT_OFFSET_M
    lat3, lon3 = _unproject_xy(x3, y3, start_lat, start_lon)
    return {"latitude": round(lat3, 6), "longitude": round(lon3, 6)}


def _project_xy(
    latitude: float, longitude: float, reference_lat: float, reference_lon: float
) -> tuple[float, float]:
    meters_per_degree_lat = 111_320
    meters_per_degree_lon = 111_320 * math.cos(math.radians(reference_lat))
    x = (longitude - reference_lon) * meters_per_degree_lon
    y = (latitude - reference_lat) * meters_per_degree_lat
    return x, y


def _unproject_xy(
    x: float, y: float, reference_lat: float, reference_lon: float
) -> tuple[float, float]:
    meters_per_degree_lat = 111_320
    meters_per_degree_lon = 111_320 * math.cos(math.radians(reference_lat))
    latitude = reference_lat + y / meters_per_degree_lat
    longitude = reference_lon + x / max(meters_per_degree_lon, 1e-6)
    return latitude, longitude


def _bearing_label(
    start_lat: float, start_lon: float, end_lat: float, end_lon: float
) -> str:
    angle = math.degrees(
        math.atan2(
            (end_lon - start_lon) * math.cos(math.radians((start_lat + end_lat) / 2)),
            end_lat - start_lat,
        )
    )
    directions = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]
    index = round(angle / 45) % 8
    return directions[index]
