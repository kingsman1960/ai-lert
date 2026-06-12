from __future__ import annotations

from typing import Any


def build_risk_result(
    *,
    location: dict[str, Any],
    warnings: list[dict[str, Any]],
    water_context: dict[str, Any],
    weather_context: dict[str, Any] | None = None,
    air_quality_context: dict[str, Any] | None = None,
    active_scenario_code: str | None = None,
    active_scenario_source: str | None = None,
) -> dict[str, Any]:
    factors: list[dict[str, Any]] = []
    score = 5

    warning_factor = _warning_factor(warnings)
    factors.append(warning_factor)
    score += warning_factor["points"]

    water_factor = _water_factor(water_context)
    factors.append(water_factor)
    score += water_factor["points"]

    proximity_factor = _proximity_factor(water_context)
    factors.append(proximity_factor)
    score += proximity_factor["points"]

    if weather_context:
        weather_factor = _weather_factor(weather_context)
        factors.append(weather_factor)
        score += weather_factor["points"]

    if air_quality_context:
        air_factor = _air_quality_factor(air_quality_context)
        factors.append(air_factor)
        score += air_factor["points"]

    if active_scenario_code:
        scenario_factor = _scenario_factor(active_scenario_code, active_scenario_source)
        factors.append(scenario_factor)
        score += scenario_factor["points"]

    region_factor = _region_factor(location)
    factors.append(region_factor)
    score += region_factor["points"]

    if score >= 65:
        tier = "High"
    elif score >= 30:
        tier = "Medium"
    else:
        tier = "Low"

    return {
        "risk": {
            "tier": tier,
            "score": min(score, 100),
            "summary": _build_summary(
                tier,
                warnings,
                water_context,
                location,
                weather_context,
                air_quality_context,
                active_scenario_code,
            ),
        },
        "factors": factors,
        "guidance": _guidance_for_tier(
            tier, location["inside_demo_region"], active_scenario_code
        ),
        "checklist": _checklist_for_tier(
            tier,
            water_context,
            warnings,
            location["inside_demo_region"],
            air_quality_context,
            active_scenario_code,
        ),
    }


def _warning_factor(warnings: list[dict[str, Any]]) -> dict[str, Any]:
    if not warnings:
        return {
            "name": "Official warnings",
            "level": "low",
            "points": 0,
            "summary": "No active NINA warnings were returned for the mapped region.",
            "source": "NINA API",
        }

    severities = " ".join((warning.get("severity") or "").lower() for warning in warnings)
    if "extreme" in severities or "severe" in severities:
        level = "high"
        points = 40
    elif "moderate" in severities:
        level = "medium"
        points = 25
    else:
        level = "medium"
        points = 20

    return {
        "name": "Official warnings",
        "level": level,
        "points": points,
        "summary": f"{len(warnings)} active official warning(s) were found for the relevant region.",
        "source": "NINA API",
    }


def _water_factor(water_context: dict[str, Any]) -> dict[str, Any]:
    state = (water_context.get("state_mnw_mhw") or "unknown").lower()
    trend = water_context.get("trend_cm_24h")

    if water_context.get("current_level_cm") is None:
        return {
            "name": "Water level state",
            "level": "info",
            "points": 0,
            "summary": "Water-level context was unavailable for this request, so the score relies on other sources.",
            "source": "PEGELONLINE",
        }

    if state == "high":
        return {
            "name": "Water level state",
            "level": "high",
            "points": 30,
            "summary": "The nearest gauge currently reports a high water-level state.",
            "source": "PEGELONLINE",
        }

    if trend is not None and trend > 20:
        return {
            "name": "Water level state",
            "level": "medium",
            "points": 18,
            "summary": "The nearest gauge is rising noticeably even though it is not classified as high.",
            "source": "PEGELONLINE",
        }

    if state == "normal":
        return {
            "name": "Water level state",
            "level": "low",
            "points": 5,
            "summary": "The nearest gauge is currently within its normal range.",
            "source": "PEGELONLINE",
        }

    return {
        "name": "Water level state",
        "level": "info",
        "points": 8,
        "summary": "Water-level context is available but does not indicate an elevated state.",
        "source": "PEGELONLINE",
    }


def _proximity_factor(water_context: dict[str, Any]) -> dict[str, Any]:
    distance = water_context.get("distance_km")
    if distance is None:
        return {
            "name": "River proximity",
            "level": "info",
            "points": 0,
            "summary": "No gauge distance could be derived for this location.",
            "source": "PEGELONLINE",
        }

    if distance <= 5:
        return {
            "name": "River proximity",
            "level": "medium",
            "points": 12,
            "summary": "The location is close to a relevant river gauge, so local hydrological context matters.",
            "source": "PEGELONLINE",
        }

    if distance <= 15:
        return {
            "name": "River proximity",
            "level": "low",
            "points": 6,
            "summary": "The location is still reasonably close to a relevant river gauge.",
            "source": "PEGELONLINE",
        }

    return {
        "name": "River proximity",
        "level": "low",
        "points": 2,
        "summary": "The nearest relevant river gauge is not especially close to the queried location.",
        "source": "PEGELONLINE",
    }


def _region_factor(location: dict[str, Any]) -> dict[str, Any]:
    if location["inside_demo_region"]:
        return {
            "name": "Demo-region confidence",
            "level": "info",
            "points": 0,
            "summary": "The location is inside Baden-Wuerttemberg, so local flood layers and heuristics are available.",
            "source": "Geocoding",
        }

    return {
        "name": "Demo-region confidence",
        "level": "medium",
        "points": -5,
        "summary": "This location is outside Baden-Wuerttemberg, so flood-layer guidance is less tailored.",
        "source": "Geocoding",
    }


def _weather_factor(weather_context: dict[str, Any]) -> dict[str, Any]:
    precipitation_probability = weather_context.get(
        "next_12h_precipitation_probability_pct"
    )
    precipitation_mm = weather_context.get("next_12h_precipitation_mm")

    if precipitation_probability is None and precipitation_mm is None:
        return {
            "name": "Weather outlook",
            "level": "info",
            "points": 0,
            "summary": "Live DWD weather data was available but did not materially change the flood-awareness score.",
            "source": "DWD",
        }

    if (precipitation_probability or 0) >= 70 or (precipitation_mm or 0) >= 10:
        return {
            "name": "Weather outlook",
            "level": "medium",
            "points": 10,
            "summary": "The DWD forecast suggests notable precipitation potential over the next 12 hours.",
            "source": "DWD",
        }

    return {
        "name": "Weather outlook",
        "level": "low",
        "points": 3,
        "summary": "The live DWD forecast does not currently show a strong short-term precipitation signal.",
        "source": "DWD",
    }


def _air_quality_factor(air_quality_context: dict[str, Any]) -> dict[str, Any]:
    overall_index = air_quality_context.get("overall_index")
    if overall_index is None:
        return {
            "name": "Air quality",
            "level": "info",
            "points": 0,
            "summary": "Air-quality context was available but did not change the score materially.",
            "source": "UBA",
        }
    if overall_index >= 4:
        return {
            "name": "Air quality",
            "level": "medium",
            "points": 8,
            "summary": "The latest UBA air-quality signal is poor enough to add health-related caution.",
            "source": "UBA",
        }
    return {
        "name": "Air quality",
        "level": "low",
        "points": 2,
        "summary": "The nearest UBA air-quality station does not indicate severe conditions right now.",
        "source": "UBA",
    }


def _scenario_factor(
    scenario_code: str, scenario_source: str | None
) -> dict[str, Any]:
    points = {
        "heat": 22,
        "flood": 38,
        "storm": 30,
        "air": 18,
    }.get(scenario_code, 0)
    labels = {
        "heat": "heat alert scenario",
        "flood": "flood alert scenario",
        "storm": "severe-weather scenario",
        "air": "air-quality advisory scenario",
    }
    source_label = "Scenario simulator" if scenario_source == "simulated" else "Live signals"
    level = "high" if scenario_code in {"flood", "storm"} else "medium"
    return {
        "name": "Scenario context",
        "level": level,
        "points": points,
        "summary": f"The active {labels.get(scenario_code, 'scenario')} raises the urgency of the result.",
        "source": source_label,
    }


def _build_summary(
    tier: str,
    warnings: list[dict[str, Any]],
    water_context: dict[str, Any],
    location: dict[str, Any],
    weather_context: dict[str, Any] | None,
    air_quality_context: dict[str, Any] | None,
    active_scenario_code: str | None,
) -> str:
    if active_scenario_code == "heat":
        return "A heat-alert scenario is active, so the app is prioritizing cooling guidance and low-exposure options."
    if active_scenario_code == "flood":
        return "A flood-alert scenario is active, so the app is prioritizing refuge points and movement away from low ground."
    if active_scenario_code == "storm":
        return "A severe-weather scenario is active, so the app is prioritizing indoor shelter and reduced travel."
    if active_scenario_code == "air":
        return "An air-quality advisory scenario is active, so the app is prioritizing lower-exposure indoor options."

    if tier == "High":
        return (
            "Current public signals suggest elevated local flood-related concern. "
            "Review official channels and prepare immediate low-regret actions."
        )
    if tier == "Medium":
        return (
            "There is no strong indication of acute danger, but nearby river context or "
            "official alerts justify closer monitoring."
        )

    if weather_context and (weather_context.get("next_12h_precipitation_mm") or 0) >= 8:
        return (
            "Current flood indicators remain limited, but the live DWD outlook suggests "
            "rainfall worth monitoring together with nearby river conditions."
        )
    if air_quality_context and (air_quality_context.get("overall_index") or 0) >= 4:
        return (
            "Flood indicators remain limited, but nearby UBA air-quality measurements suggest "
            "additional health caution for outdoor activity."
        )
    if warnings:
        return "Overall risk remains low, but official information still deserves attention."
    if location["inside_demo_region"]:
        return (
            "No active official warnings were found and the nearest gauge is not showing "
            "an elevated state."
        )
    return (
        "This location currently appears low risk based on the available warning and gauge "
        "signals, but the app is optimized for Baden-Wuerttemberg coverage."
    )


def _guidance_for_tier(
    tier: str, inside_demo_region: bool, active_scenario_code: str | None
) -> dict[str, Any]:
    if active_scenario_code == "heat":
        return {
            "title": "Reduce heat exposure",
            "actions": [
                "Avoid prolonged outdoor activity during peak heat hours.",
                "Use shaded or cooled indoor places and hydrate often.",
                "Check on children, older adults, and anyone with chronic illness.",
            ],
            "disclaimer": (
                "This scenario view supports awareness only. Official instructions remain authoritative."
            ),
        }
    if active_scenario_code == "flood":
        return {
            "title": "Move away from flood-prone low ground",
            "actions": [
                "Stay away from riverbanks, low underpasses, and waterlogged routes.",
                "Prepare evacuation basics and monitor official channels closely.",
                "Use shelters or refuge points only when appropriate and safe.",
            ],
            "disclaimer": (
                "This scenario view is a preparedness aid and does not replace official evacuation orders."
            ),
        }
    if active_scenario_code == "storm":
        return {
            "title": "Shelter indoors during severe weather",
            "actions": [
                "Move indoors and stay away from exposed outdoor areas.",
                "Delay travel and monitor official updates until the warning window passes.",
                "Use sturdy public indoor spaces if you need nearby shelter.",
            ],
            "disclaimer": (
                "This scenario view is a simplified emergency aid and does not replace official warnings."
            ),
        }
    if active_scenario_code == "air":
        return {
            "title": "Reduce outdoor exposure",
            "actions": [
                "Limit strenuous outdoor activity while air quality is degraded.",
                "Prefer indoor public places if you need a nearby refuge.",
                "Escalate to medical support if respiratory symptoms worsen.",
            ],
            "disclaimer": (
                "This scenario view is a health-awareness aid and not medical advice."
            ),
        }

    if tier == "High":
        return {
            "title": "Act now and follow official channels",
            "actions": [
                "Check the latest official warning details and local authority updates.",
                "Avoid riverbanks, underpasses, and low-lying areas near the Neckar.",
                "Prepare essential items, important documents, and contact plans.",
                "Share the warning with nearby household members or neighbors who may need support.",
            ],
            "disclaimer": (
                "This prototype supports awareness and preparedness. Always follow official emergency guidance."
            ),
        }

    if tier == "Medium":
        actions = [
            "Monitor official warnings and gauge updates over the next few hours.",
            "Review low-regret preparedness steps such as moving valuables or checking travel routes.",
            "Be cautious near river-adjacent paths, parking areas, or flood-prone low points.",
        ]
        if inside_demo_region:
            actions.append("Use local Baden-Wuerttemberg authority channels for the most relevant updates.")
        return {
            "title": "Stay alert and prepare sensible precautions",
            "actions": actions,
            "disclaimer": (
                "This prototype provides a simplified interpretation of public data and is not a replacement for official instructions."
            ),
        }

    return {
        "title": "Stay informed",
        "actions": [
            "No immediate action is indicated, but keep an eye on official warning channels.",
            "If you live or travel near rivers or flood-prone valleys, review your flood-preparedness plan before conditions change.",
            "Use this result as a quick interpretation layer, not as authoritative emergency advice.",
        ],
        "disclaimer": (
            "This prototype summarizes public information for awareness and preparedness."
        ),
    }


def _checklist_for_tier(
    tier: str,
    water_context: dict[str, Any],
    warnings: list[dict[str, Any]],
    inside_demo_region: bool,
    air_quality_context: dict[str, Any] | None,
    active_scenario_code: str | None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    if active_scenario_code == "heat":
        items.extend(
            [
                {
                    "label": "Plan the next few hours around shade or indoor cooling",
                    "priority": "core",
                    "reason": "Heat scenarios are safest when exposure is reduced early.",
                },
                {
                    "label": "Carry water and check vulnerable people nearby",
                    "priority": "recommended",
                    "reason": "Heat stress escalates quickly for vulnerable groups.",
                },
            ]
        )
    elif active_scenario_code == "flood":
        items.extend(
            [
                {
                    "label": "Move away from river-adjacent low ground now",
                    "priority": "core",
                    "reason": "Flood scenarios are driven by local topographic exposure.",
                },
                {
                    "label": "Identify your nearest refuge point or higher-ground option",
                    "priority": "recommended",
                    "reason": "Preparedness improves if you know where you would move next.",
                },
            ]
        )
    elif active_scenario_code == "storm":
        items.extend(
            [
                {
                    "label": "Choose the nearest sturdy indoor fallback",
                    "priority": "core",
                    "reason": "Severe weather safety depends on reaching shelter early.",
                },
                {
                    "label": "Secure travel and delay unnecessary outdoor movement",
                    "priority": "recommended",
                    "reason": "Exposure risk is highest while moving through open areas.",
                },
            ]
        )
    elif active_scenario_code == "air":
        items.extend(
            [
                {
                    "label": "Reduce strenuous outdoor activity",
                    "priority": "recommended",
                    "reason": "Air-quality advisories mainly affect outdoor exertion and vulnerable groups.",
                },
                {
                    "label": "Keep medication and support options nearby",
                    "priority": "watch",
                    "reason": "Respiratory symptoms can worsen quickly for sensitive users.",
                },
            ]
        )

    if tier == "High":
        items.extend(
            [
                {
                    "label": "Check official warning updates immediately",
                    "priority": "core",
                    "reason": "High-risk results should always be anchored in official alerts.",
                },
                {
                    "label": "Move vehicles or valuables away from low-lying areas",
                    "priority": "core",
                    "reason": "Low-regret protection steps matter most when local river context is elevated.",
                },
                {
                    "label": "Inform household members and confirm contact plans",
                    "priority": "recommended",
                    "reason": "Preparedness is stronger when everyone knows the plan before conditions worsen.",
                },
            ]
        )
    elif tier == "Medium":
        items.extend(
            [
                {
                    "label": "Monitor NINA and local authority updates tonight",
                    "priority": "recommended",
                    "reason": "Conditions do not indicate immediate danger, but they deserve attention.",
                },
                {
                    "label": "Review routes and avoid river-adjacent low points if conditions change",
                    "priority": "recommended",
                    "reason": "Preparedness is easier before travel or mobility decisions become urgent.",
                },
            ]
        )
    else:
        items.extend(
            [
                {
                    "label": "Keep official warning channels bookmarked",
                    "priority": "watch",
                    "reason": "Low-risk results can still change if warnings or river conditions update.",
                },
                {
                    "label": "Review your flood-readiness basics before severe weather periods",
                    "priority": "watch",
                    "reason": "Preparedness is most useful before conditions become stressful.",
                },
            ]
        )

    if water_context.get("distance_km") is not None and water_context["distance_km"] <= 8:
        items.append(
            {
                "label": "Pay extra attention to Neckar-adjacent areas near your location",
                "priority": "recommended" if tier != "Low" else "watch",
                "reason": "The nearest relevant gauge is close enough that local river conditions are meaningful.",
            }
        )

    if warnings:
        items.append(
            {
                "label": "Open the official warning detail and check timing or expiry",
                "priority": "core" if tier == "High" else "recommended",
                "reason": "Warning relevance depends on severity, timing, and the authority source.",
            }
        )

    if inside_demo_region:
        items.append(
            {
                "label": "Use local Baden-Wuerttemberg official channels for the most local updates",
                "priority": "watch" if tier == "Low" else "recommended",
                "reason": "This prototype covers Baden-Wuerttemberg, but local authorities remain authoritative.",
            }
        )

    if air_quality_context and (air_quality_context.get("overall_index") or 0) >= 4:
        items.append(
            {
                "label": "Reduce strenuous outdoor activity if air quality worsens further",
                "priority": "recommended" if tier != "Low" else "watch",
                "reason": "UBA air-quality context suggests a meaningful health-related signal near this location.",
            }
        )

    return items
