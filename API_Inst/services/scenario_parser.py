from __future__ import annotations

import re
from typing import Literal


ScenarioCode = Literal["heat", "flood", "storm", "air"]

SCENARIO_PATTERNS = [
    re.compile(r"\[demo:(heat|flood|storm|air)\]", re.IGNORECASE),
    re.compile(r"#(heat|flood|storm|air)\b", re.IGNORECASE),
]


def extract_scenario_code(query: str) -> tuple[str, ScenarioCode | None]:
    cleaned = query
    scenario: ScenarioCode | None = None

    for pattern in SCENARIO_PATTERNS:
        match = pattern.search(cleaned)
        if match:
            scenario = match.group(1).lower()  # type: ignore[assignment]
            cleaned = pattern.sub("", cleaned).strip()
            break

    return cleaned or query, scenario
