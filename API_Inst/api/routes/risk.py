from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from app.schemas.risk import (
    AirQualityContext,
    FloodEvacuationContext,
    HazardFeedSummary,
    LocationSummary,
    NearbyFacility,
    MapPoint,
    FloodplainFeature,
    RiskAssessmentRequest,
    RiskAssessmentResponse,
    ScenarioContext,
    ScenarioPlace,
    SourceLink,
    WarningSummary,
    WaterContext,
    WeatherContext,
)
from app.services.air_quality import fetch_air_quality_context
from app.services.dwd import fetch_weather_context
from app.services.facilities import fetch_nearby_facilities
from app.services.geocoding import (
    GeocodingError,
    geocode_query,
    reverse_geocode_coordinates,
)
from app.services.hazards import fetch_hazard_feeds
from app.services.lubw_flood import (
    fetch_flood_evacuation_context,
    prioritize_places_by_hwextrem,
)
from app.services.nina import fetch_warnings_for_location
from app.services.pegel import fetch_water_context
from app.services.scenario_parser import extract_scenario_code
from app.services.scenario_places import fetch_scenario_places
from app.services.scenarios import (
    build_active_scenario,
    infer_live_scenario,
    simulated_warning_for_scenario,
)
from app.services.scoring import build_risk_result

router = APIRouter(tags=["risk"])


@router.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/risk-assessment", response_model=RiskAssessmentResponse)
async def create_risk_assessment(
    payload: RiskAssessmentRequest,
) -> RiskAssessmentResponse:
    raw_query = (payload.query or "").strip()
    clean_query, requested_scenario = extract_scenario_code(raw_query) if raw_query else ("", None)

    if payload.latitude is not None and payload.longitude is not None:
        try:
            location = await reverse_geocode_coordinates(
                payload.latitude,
                payload.longitude,
                label=clean_query or "Current location",
            )
        except Exception:  # noqa: BLE001
            location = {
                "query": clean_query or "Current location",
                "display_name": f"Current location ({payload.latitude:.5f}, {payload.longitude:.5f})",
                "latitude": payload.latitude,
                "longitude": payload.longitude,
                "city": None,
                "county": None,
                "state": None,
                "country": None,
                "inside_demo_region": False,
            }
    else:
        try:
            location = await geocode_query(clean_query)
        except GeocodingError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail="Failed to geocode the location.") from exc

    nina_task = fetch_warnings_for_location(location)
    pegel_task = fetch_water_context(location)

    weather_task = (
        fetch_weather_context(location["latitude"], location["longitude"])
        if payload.include_weather
        else None
    )
    air_quality_task = fetch_air_quality_context(location["latitude"], location["longitude"])
    facilities_task = fetch_nearby_facilities(location["latitude"], location["longitude"])
    hazard_feeds_task = fetch_hazard_feeds()

    nina_result, water_context = await asyncio.gather(
        nina_task, pegel_task, return_exceptions=True
    )

    if isinstance(nina_result, Exception):
        nina_result = {"ars": None, "region_name": None, "warnings": []}

    if isinstance(water_context, Exception):
        water_context = {
            "gauge_id": None,
            "gauge_name": None,
            "water_name": None,
            "gauge_latitude": None,
            "gauge_longitude": None,
            "distance_km": None,
            "current_level_cm": None,
            "level_timestamp": None,
            "state_mnw_mhw": None,
            "state_nsw_hsw": None,
            "trend_cm_24h": None,
            "trend_label": "unknown",
            "history": [],
            "summary": (
                "PEGELONLINE could not be reached for this request, so the result is "
                "based on the remaining available sources."
            ),
        }

    weather_context = None
    if weather_task is not None:
        try:
            weather_context = await weather_task
        except Exception:  # noqa: BLE001
            weather_context = {
                "provider": "DWD",
                "status": "failed",
                "warning_count": 0,
                "summary": "Weather enrichment was requested but could not be loaded.",
            }

    try:
        air_quality_context, nearby_facilities, hazard_feeds = await asyncio.gather(
            air_quality_task, facilities_task, hazard_feeds_task, return_exceptions=False
        )
    except Exception:  # noqa: BLE001
        air_quality_context = {
            "provider": "UBA",
            "status": "failed",
            "overall_index": None,
            "overall_label": None,
            "summary": "Air-quality enrichment could not be loaded for this request.",
            "components": [],
        }
        nearby_facilities = []
        hazard_feeds = [
            {
                "source": "DWD feed",
                "count": 0,
                "summary": "Hazard feed data could not be loaded.",
            },
            {
                "source": "LHP feed",
                "count": 0,
                "summary": "Hazard feed data could not be loaded.",
            },
        ]

    location["ars"] = nina_result["ars"]
    location["region_name"] = nina_result["region_name"]
    warnings = nina_result["warnings"]

    active_scenario_code = requested_scenario or infer_live_scenario(
        warnings, weather_context, air_quality_context
    )
    active_scenario_source = "simulated" if requested_scenario else ("live" if active_scenario_code else None)

    if requested_scenario:
        warnings = [simulated_warning_for_scenario(requested_scenario), *warnings]

    scenario_places = []
    active_scenario = None
    flood_context = None
    if active_scenario_code:
        if active_scenario_code == "flood":
            try:
                flood_context = await fetch_flood_evacuation_context(
                    location["latitude"], location["longitude"]
                )
            except Exception:  # noqa: BLE001
                flood_context = {
                    "source": "LUBW HQ100 floodplain",
                    "status": "unavailable",
                    "summary": "Floodplain routing context could not be loaded for this request.",
                    "hq_extreme_considered": False,
                    "hq_extreme_at_location": False,
                    "hq_extreme_pixel_value": None,
                    "distance_to_edge_m": None,
                    "escape_direction": None,
                    "recommended_exit_point": None,
                    "route": [],
                    "polygons": [],
                }
        try:
            scenario_places = await fetch_scenario_places(
                location["latitude"], location["longitude"], active_scenario_code
            )
        except Exception:  # noqa: BLE001
            scenario_places = []

        if active_scenario_code == "flood" and scenario_places:
            try:
                scenario_places = await prioritize_places_by_hwextrem(
                    location["latitude"], location["longitude"], scenario_places
                )
            except Exception:  # noqa: BLE001
                pass

        active_scenario = build_active_scenario(
            active_scenario_code,
            active_scenario_source or "live",
            scenario_places,
            flood_context=flood_context,
        )

    risk_result = build_risk_result(
        location=location,
        warnings=warnings,
        water_context=water_context,
        weather_context=weather_context,
        air_quality_context=air_quality_context,
        active_scenario_code=active_scenario_code,
        active_scenario_source=active_scenario_source,
    )

    sources = [
        SourceLink(name="NINA API", url="https://nina.api.bund.dev/"),
        SourceLink(name="PEGELONLINE API", url="https://pegel-online.api.bund.dev/"),
        SourceLink(
            name="UBA Air Data API",
            url="https://luftqualitaet.api.bund.dev/",
        ),
        SourceLink(name="Overpass API", url="https://overpass-api.de/"),
        SourceLink(
            name="VerkNet BWaStr WMS",
            url="https://via.bund.de/wsv/bwastr/wms?request=GetCapabilities&service=wms&Version=1.3.0",
        ),
        SourceLink(
            name="LUBW floodplain service",
            url=(
                "https://rips-gdi.lubw.baden-wuerttemberg.de/arcgis/rest/services/"
                "wfs/Ueberschwemmungsgebiet/MapServer/1"
            ),
        ),
    ]
    if weather_context:
        sources.append(
            SourceLink(
                name="DWD API reference", url="https://github.com/bundesAPI/dwd-api"
            )
        )

    return RiskAssessmentResponse(
        location=LocationSummary(**location),
        risk=risk_result["risk"],
        warnings=[WarningSummary(**warning) for warning in warnings],
        warning_count=len(warnings),
        water_context=WaterContext(**water_context),
        weather_context=WeatherContext(**weather_context) if weather_context else None,
        air_quality_context=AirQualityContext(**air_quality_context)
        if air_quality_context
        else None,
        hazard_feeds=[HazardFeedSummary(**feed) for feed in hazard_feeds],
        nearby_facilities=[NearbyFacility(**facility) for facility in nearby_facilities],
        active_scenario=ScenarioContext(
            **{
                **active_scenario,
                "safe_places": [ScenarioPlace(**place) for place in scenario_places],
                "flood_context": FloodEvacuationContext(
                    **{
                        **flood_context,
                        "recommended_exit_point": MapPoint(**flood_context["recommended_exit_point"])
                        if flood_context and flood_context.get("recommended_exit_point")
                        else None,
                        "route": [
                            MapPoint(**point) for point in (flood_context or {}).get("route", [])
                        ],
                        "polygons": [
                            FloodplainFeature(**feature)
                            for feature in (flood_context or {}).get("polygons", [])
                        ],
                    }
                )
                if flood_context
                else None,
            }
        )
        if active_scenario
        else None,
        factors=risk_result["factors"],
        guidance=risk_result["guidance"],
        checklist=risk_result["checklist"],
        sources=sources,
    )
