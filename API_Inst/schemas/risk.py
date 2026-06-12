from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


RiskTier = Literal["Low", "Medium", "High"]
FactorLevel = Literal["low", "medium", "high", "info"]


class RiskAssessmentRequest(BaseModel):
    query: str | None = Field(
        default=None, description="Address, postal code, or optional label"
    )
    latitude: float | None = Field(
        default=None, ge=-90, le=90, description="Optional direct latitude input"
    )
    longitude: float | None = Field(
        default=None, ge=-180, le=180, description="Optional direct longitude input"
    )
    include_weather: bool = Field(
        default=False,
        description="Attempt to enrich the response with weather context if available.",
    )

    @model_validator(mode="after")
    def validate_location_input(self) -> "RiskAssessmentRequest":
        has_query = bool((self.query or "").strip())
        has_coordinates = self.latitude is not None and self.longitude is not None

        if not has_query and not has_coordinates:
            raise ValueError("Provide either a query or both latitude and longitude.")
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Latitude and longitude must be provided together.")
        if has_query and len((self.query or "").strip()) < 2 and not has_coordinates:
            raise ValueError("Query must be at least 2 characters long.")
        return self


class LocationSummary(BaseModel):
    query: str
    display_name: str
    latitude: float
    longitude: float
    city: str | None = None
    county: str | None = None
    state: str | None = None
    country: str | None = None
    region_name: str | None = None
    ars: str | None = None
    inside_demo_region: bool


class WarningSummary(BaseModel):
    identifier: str
    title: str
    severity: str | None = None
    source: str | None = None
    sent: str | None = None
    effective: str | None = None
    expires: str | None = None
    description: str | None = None
    url: str | None = None


class WaterContext(BaseModel):
    gauge_id: str | None = None
    gauge_name: str | None = None
    water_name: str | None = None
    gauge_latitude: float | None = None
    gauge_longitude: float | None = None
    distance_km: float | None = None
    current_level_cm: float | None = None
    level_timestamp: str | None = None
    state_mnw_mhw: str | None = None
    state_nsw_hsw: str | None = None
    trend_cm_24h: float | None = None
    trend_label: str | None = None
    history: list["SeriesPoint"] = []
    summary: str


class WeatherContext(BaseModel):
    provider: str
    status: str
    station_id: str | None = None
    station_name: str | None = None
    distance_km: float | None = None
    current_temperature_c: float | None = None
    daily_min_c: float | None = None
    daily_max_c: float | None = None
    next_12h_precipitation_mm: float | None = None
    next_12h_precipitation_probability_pct: int | None = None
    warning_count: int = 0
    summary: str


class SeriesPoint(BaseModel):
    timestamp: str
    value: float


class AirQualityComponent(BaseModel):
    code: str
    value: float
    index: int | None = None
    label: str


class AirQualityContext(BaseModel):
    provider: str
    status: str
    station_id: str | None = None
    station_name: str | None = None
    station_city: str | None = None
    distance_km: float | None = None
    overall_index: int | None = None
    overall_label: str | None = None
    components: list[AirQualityComponent] = []
    summary: str


class HazardFeedSummary(BaseModel):
    source: str
    count: int
    summary: str


class NearbyFacility(BaseModel):
    name: str
    category: str
    latitude: float
    longitude: float
    distance_km: float
    address: str | None = None


class ScenarioPlace(BaseModel):
    name: str
    category: str
    latitude: float
    longitude: float
    distance_km: float
    address: str | None = None
    note: str | None = None


class MapPoint(BaseModel):
    latitude: float
    longitude: float


class FloodplainFeature(BaseModel):
    geometry_type: Literal["Polygon", "MultiPolygon"]
    coordinates: list[Any]


class FloodEvacuationContext(BaseModel):
    source: str
    status: Literal["inside", "nearby", "outside", "unavailable"]
    summary: str
    hq_extreme_considered: bool = False
    hq_extreme_at_location: bool = False
    hq_extreme_pixel_value: str | None = None
    distance_to_edge_m: float | None = None
    escape_direction: str | None = None
    recommended_exit_point: MapPoint | None = None
    route: list[MapPoint] = []
    polygons: list[FloodplainFeature] = []


class ScenarioContext(BaseModel):
    code: str
    source: Literal["simulated", "live"]
    title: str
    summary: str
    manual_title: str
    manual_steps: list[str]
    safe_places_label: str
    safe_places_note: str
    safe_places: list[ScenarioPlace]
    flood_context: FloodEvacuationContext | None = None


class RiskFactor(BaseModel):
    name: str
    level: FactorLevel
    points: int
    summary: str
    source: str


class SourceLink(BaseModel):
    name: str
    url: str


class RiskOverview(BaseModel):
    tier: RiskTier
    score: int
    summary: str


class Guidance(BaseModel):
    title: str
    actions: list[str]
    disclaimer: str


class PreparednessItem(BaseModel):
    label: str
    priority: Literal["core", "recommended", "watch"]
    reason: str


class RiskAssessmentResponse(BaseModel):
    location: LocationSummary
    risk: RiskOverview
    warnings: list[WarningSummary]
    warning_count: int
    water_context: WaterContext
    weather_context: WeatherContext | None = None
    air_quality_context: AirQualityContext | None = None
    hazard_feeds: list[HazardFeedSummary]
    nearby_facilities: list[NearbyFacility]
    active_scenario: ScenarioContext | None = None
    factors: list[RiskFactor]
    guidance: Guidance
    checklist: list[PreparednessItem]
    sources: list[SourceLink]
