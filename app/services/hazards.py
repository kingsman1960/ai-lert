from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx


NINA_BASE_URL = os.getenv("NINA_BASE_URL", "https://warnung.bund.de/api31")


async def fetch_hazard_feeds() -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        dwd_task = client.get(f"{NINA_BASE_URL}/dwd/mapData.json")
        lhp_task = client.get(f"{NINA_BASE_URL}/lhp/mapData.json")
        dwd_response, lhp_response = await asyncio.gather(dwd_task, lhp_task)

    dwd_response.raise_for_status()
    lhp_response.raise_for_status()
    dwd_data = dwd_response.json()
    lhp_data = lhp_response.json()

    return [
        {
            "source": "DWD feed",
            "count": len(dwd_data) if isinstance(dwd_data, list) else 0,
            "summary": _hazard_summary("DWD severe-weather feed", dwd_data),
        },
        {
            "source": "LHP feed",
            "count": len(lhp_data) if isinstance(lhp_data, list) else 0,
            "summary": _hazard_summary("LHP flood feed", lhp_data),
        },
    ]


def _hazard_summary(label: str, payload: Any) -> str:
    count = len(payload) if isinstance(payload, list) else 0
    if count == 0:
        return f"No active signals were returned from the {label}."
    return f"{count} active signal(s) were returned from the {label}."

