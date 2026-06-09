"""Open-Meteo venue weather adapter."""
from __future__ import annotations

from typing import Any

import requests

BASE_URL = "https://api.open-meteo.com/v1/forecast"


def fetch_daily_weather(latitude: float, longitude: float, date: str) -> dict[str, Any]:
    response = requests.get(
        BASE_URL,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max",
            "start_date": date,
            "end_date": date,
            "timezone": "auto",
        },
        headers={"User-Agent": "wc26-dashboard/0.1"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("daily", {})

