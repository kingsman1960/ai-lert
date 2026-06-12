from __future__ import annotations

from typing import Any


SCENARIO_METADATA = {
    "heat": {
        "title": "Heat alert playbook",
        "summary": "A heat-warning scenario is active for this location.",
        "manual_title": "Heat response manual",
        "manual_steps": [
            "Avoid strenuous outdoor activity during the hottest hours.",
            "Hydrate regularly and use shaded or cooled indoor spaces whenever possible.",
            "Check on older adults, children, and anyone with chronic illness.",
            "Escalate quickly if there are signs of heat exhaustion or heat stroke.",
        ],
        "safe_places_label": "Cooling and hydration options",
        "safe_places_note": "These are candidate places for shade, indoor cooling, or hydration support.",
        "simulated_warning": {
            "identifier": "demo-heat",
            "title": "Simulated heat warning",
            "severity": "Severe",
            "source": "Scenario simulator",
            "description": "Demo scenario for a local heat alert in the selected area.",
        },
    },
    "flood": {
        "title": "Flood alert playbook",
        "summary": "A flood-warning scenario is active for this location.",
        "manual_title": "Flood response manual",
        "manual_steps": [
            "Move away from river-adjacent low ground and avoid underpasses or submerged roads.",
            "Follow official warning updates and prepare immediate low-regret evacuation steps.",
            "Move vehicles, valuables, and critical documents away from flood-prone areas.",
            "Use official shelters or public refuge points only if instructed or clearly needed.",
        ],
        "safe_places_label": "Potential refuge points and higher ground",
        "safe_places_note": "Use these as orientation aids only and always follow official evacuation instructions.",
        "simulated_warning": {
            "identifier": "demo-flood",
            "title": "Simulated flood warning",
            "severity": "Extreme",
            "source": "Scenario simulator",
            "description": "Demo scenario for a flood alert near the selected location.",
        },
    },
    "storm": {
        "title": "Severe-weather playbook",
        "summary": "A severe-weather scenario is active for this location.",
        "manual_title": "Severe-weather response manual",
        "manual_steps": [
            "Move indoors and stay away from trees, scaffolding, and exposed river paths.",
            "Delay travel where possible until the warning window passes.",
            "Keep phones charged and monitor official warning updates.",
            "Use sturdy indoor public buildings only if you cannot safely remain where you are.",
        ],
        "safe_places_label": "Indoor refuge candidates",
        "safe_places_note": "These are nearby sturdy public places that may be useful during severe weather.",
        "simulated_warning": {
            "identifier": "demo-storm",
            "title": "Simulated severe-weather warning",
            "severity": "Severe",
            "source": "Scenario simulator",
            "description": "Demo scenario for a severe-weather alert in the selected area.",
        },
    },
    "air": {
        "title": "Air-quality advisory playbook",
        "summary": "An air-quality deterioration scenario is active for this location.",
        "manual_title": "Air-quality response manual",
        "manual_steps": [
            "Reduce strenuous outdoor activity while the air-quality advisory remains active.",
            "Prefer indoor public spaces if you need to stay outside your home area.",
            "Keep medication with you if you have asthma or respiratory vulnerability.",
            "Escalate to medical support if symptoms become severe or persistent.",
        ],
        "safe_places_label": "Indoor refuge and support options",
        "safe_places_note": "These are nearby indoor or support-oriented places that may help during poor air quality.",
        "simulated_warning": {
            "identifier": "demo-air",
            "title": "Simulated air-quality advisory",
            "severity": "Moderate",
            "source": "Scenario simulator",
            "description": "Demo scenario for degraded air quality near the selected location.",
        },
    },
}


def infer_live_scenario(
    warnings: list[dict[str, Any]],
    weather_context: dict[str, Any] | None,
    air_quality_context: dict[str, Any] | None,
) -> str | None:
    text = " ".join(
        " ".join(
            str(warning.get(field) or "")
            for field in ["title", "description", "severity", "source"]
        )
        for warning in warnings
    ).lower()

    if any(keyword in text for keyword in ["hitze", "heat"]):
        return "heat"
    if any(keyword in text for keyword in ["hochwasser", "flood", "überflutung", "ueberflutung"]):
        return "flood"
    if any(keyword in text for keyword in ["unwetter", "gewitter", "storm", "orkan"]):
        return "storm"

    if air_quality_context and (air_quality_context.get("overall_index") or 0) >= 4:
        return "air"

    if weather_context and (weather_context.get("warning_count") or 0) > 0:
        return "storm"

    return None


def build_active_scenario(
    scenario_code: str,
    source: str,
    safe_places: list[dict[str, Any]],
    flood_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = SCENARIO_METADATA[scenario_code]
    summary = metadata["summary"]
    if scenario_code == "flood" and flood_context is not None:
        summary = flood_context.get("summary") or summary

    return {
        "code": scenario_code,
        "source": source,
        "title": metadata["title"],
        "summary": summary,
        "manual_title": metadata["manual_title"],
        "manual_steps": metadata["manual_steps"],
        "safe_places_label": metadata["safe_places_label"],
        "safe_places_note": metadata["safe_places_note"],
        "safe_places": safe_places,
        "flood_context": flood_context,
    }


def simulated_warning_for_scenario(scenario_code: str) -> dict[str, Any]:
    return SCENARIO_METADATA[scenario_code]["simulated_warning"].copy()
