from __future__ import annotations

import os
from typing import Any

import httpx


NINA_BASE_URL = os.getenv("NINA_BASE_URL", "https://warnung.bund.de/api31")

HEILBRONN_CITY_ARS = "081210000000"
HEILBRONN_DISTRICT_ARS = "081250000000"


def resolve_ars_for_location(location: dict[str, Any]) -> tuple[str | None, str | None]:
    city = (location.get("city") or "").strip().lower()
    county = (location.get("county") or "").strip().lower()
    state = (location.get("state") or "").strip().lower()

    if "baden-württemberg" not in state:
        return None, None

    if city == "heilbronn":
        return HEILBRONN_CITY_ARS, "Heilbronn (city)"

    if "heilbronn" in county:
        return HEILBRONN_DISTRICT_ARS, "Landkreis Heilbronn"

    return None, None


async def fetch_warnings_for_location(location: dict[str, Any]) -> dict[str, Any]:
    ars, region_name = resolve_ars_for_location(location)
    if not ars:
        return {"ars": None, "region_name": None, "warnings": []}

    overview = await _fetch_dashboard(ars)
    warnings = await _normalize_warnings(overview)
    return {"ars": ars, "region_name": region_name, "warnings": warnings}


async def _fetch_dashboard(ars: str) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(f"{NINA_BASE_URL}/dashboard/{ars}.json")
        response.raise_for_status()
        data = response.json()
    return data if isinstance(data, list) else []


async def _normalize_warnings(overview: list[dict[str, Any]]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=20.0) as client:
        for item in overview[:5]:
            warning = await _normalize_warning_item(client, item)
            warnings.append(warning)
    return warnings


async def _normalize_warning_item(
    client: httpx.AsyncClient, item: dict[str, Any]
) -> dict[str, Any]:
    identifier = _extract_identifier(item)
    detail: dict[str, Any] = {}
    if identifier:
        try:
            response = await client.get(f"{NINA_BASE_URL}/warnings/{identifier}.json")
            response.raise_for_status()
            detail = response.json()
        except httpx.HTTPError:
            detail = {}

    info = _extract_primary_info(detail)
    title = (
        info.get("headline")
        or item.get("i18nTitle")
        or item.get("title")
        or "Official warning"
    )
    severity = info.get("severity") or item.get("severity")
    description = info.get("description") or item.get("description")
    source = item.get("source") or detail.get("senderName") or detail.get("sender")

    return {
        "identifier": identifier or title,
        "title": title,
        "severity": severity,
        "source": source,
        "sent": detail.get("sent"),
        "effective": info.get("effective"),
        "expires": info.get("expires"),
        "description": description,
        "url": f"{NINA_BASE_URL}/warnings/{identifier}.json" if identifier else None,
    }


def _extract_identifier(item: dict[str, Any]) -> str | None:
    payload = item.get("payload") or {}
    data = payload.get("data") or {}
    return (
        item.get("id")
        or item.get("identifier")
        or payload.get("id")
        or data.get("id")
        or data.get("identifier")
    )


def _extract_primary_info(detail: dict[str, Any]) -> dict[str, Any]:
    info = detail.get("info")
    if isinstance(info, list) and info:
        first = info[0]
        return first if isinstance(first, dict) else {}
    return {}
