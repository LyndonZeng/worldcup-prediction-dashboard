"""Open-Meteo venue weather adapter."""
from __future__ import annotations

from typing import Any

from .http import get_json

BASE_URL = "https://api.open-meteo.com/v1/forecast"

VENUE_COORDINATES = {
    "Mexico City": (19.3029, -99.1505),
    "Guadalajara": (20.6819, -103.4626),
    "Monterrey": (25.6689, -100.2443),
    "Toronto": (43.6327, -79.4186),
    "Vancouver": (49.2768, -123.1119),
    "Inglewood": (33.9535, -118.3392),
    "Santa Clara": (37.4033, -121.9694),
    "East Rutherford": (40.8135, -74.0745),
    "Houston": (29.6847, -95.4107),
    "Arlington": (32.7473, -97.0945),
    "Atlanta": (33.7554, -84.4008),
    "Seattle": (47.5952, -122.3316),
    "Philadelphia": (39.9008, -75.1675),
    "Boston": (42.0909, -71.2643),
    "Miami": (25.9580, -80.2389),
    "Kansas City": (39.0489, -94.4839),
}

CLIMATE_FALLBACKS = {
    "Mexico City": (22, 37, 8, "altitude"),
    "Guadalajara": (27, 43, 10, "altitude-lite"),
    "Monterrey": (33, 58, 12, "heat"),
    "Toronto": (21, 55, 14, "cool"),
    "Vancouver": (19, 58, 12, "indoor watch"),
    "Inglewood": (20, 58, 11, "mild"),
    "Santa Clara": (22, 52, 15, "dry"),
    "East Rutherford": (24, 63, 13, "humid"),
    "Houston": (31, 72, 10, "indoor watch"),
    "Arlington": (29, 64, 12, "indoor watch"),
    "Atlanta": (28, 68, 9, "indoor watch"),
    "Seattle": (18, 62, 10, "cool"),
    "Philadelphia": (27, 66, 12, "humid"),
    "Boston": (23, 64, 13, "humid"),
    "Miami": (31, 74, 14, "heat"),
    "Kansas City": (29, 61, 16, "plains wind"),
}


def fetch_daily_weather(latitude: float, longitude: float, date: str) -> dict[str, Any]:
    data = get_json(
        BASE_URL,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "daily": (
                "temperature_2m_max,temperature_2m_min,temperature_2m_mean,"
                "relative_humidity_2m_mean,precipitation_sum,weather_code,wind_speed_10m_max"
            ),
            "start_date": date,
            "end_date": date,
            "timezone": "auto",
        },
        headers={"User-Agent": "wc26-dashboard/0.1"},
        timeout=30,
    )
    return data.get("daily", {})


def coordinates_for_city(city: str) -> tuple[float, float] | None:
    return VENUE_COORDINATES.get(city)


def climate_fallback_for_city(city: str) -> dict[str, Any]:
    temperature, humidity, wind, condition = CLIMATE_FALLBACKS.get(city, (24, 58, 10, "normal"))
    return {
        "temperature_c": temperature,
        "humidity_pct": humidity,
        "wind_kph": wind,
        "precipitation_mm": None,
        "condition": condition,
    }


def normalize_daily_weather(daily: dict[str, Any], date: str) -> dict[str, Any] | None:
    times = daily.get("time") or []
    if date not in times:
        return None
    index = times.index(date)

    def value(name: str):
        values = daily.get(name) or []
        return values[index] if index < len(values) else None

    high = value("temperature_2m_max")
    low = value("temperature_2m_min")
    mean = value("temperature_2m_mean")
    temperature = mean if mean is not None else _mean(high, low)
    wind = value("wind_speed_10m_max")
    humidity = value("relative_humidity_2m_mean")
    precipitation = value("precipitation_sum")
    return {
        "temperature_c": _rounded(temperature),
        "humidity_pct": _rounded(humidity),
        "wind_kph": _rounded(wind),
        "precipitation_mm": _rounded(precipitation),
        "condition": condition_from_weather_code(value("weather_code"), precipitation),
    }


def condition_from_weather_code(weather_code: int | float | None, precipitation: float | None) -> str:
    if precipitation and precipitation >= 8:
        return "heavy rain"
    if precipitation and precipitation > 0:
        return "rain risk"
    if weather_code is None:
        return "forecast"
    code = int(weather_code)
    if code in {0, 1}:
        return "clear"
    if code in {2, 3}:
        return "cloudy"
    if 45 <= code <= 48:
        return "fog"
    if 51 <= code <= 67 or 80 <= code <= 82:
        return "rain risk"
    if 95 <= code <= 99:
        return "storm risk"
    return "forecast"


def _mean(high: float | None, low: float | None) -> float | None:
    if high is None and low is None:
        return None
    if high is None:
        return low
    if low is None:
        return high
    return (high + low) / 2


def _rounded(value):
    return round(float(value), 1) if value is not None else None
