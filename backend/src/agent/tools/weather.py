import httpx
from langchain_core.tools import tool


@tool
async def get_weather_forecast(location: str, days: int = 7) -> str:
    """
    Lấy dự báo thời tiết cho vùng trồng trọt sử dụng Open-Meteo API.

    - `location` có thể là tên thành phố (ví dụ: "Hanoi") hoặc "lat,lon".
    - `days` tối đa 7.
    """
    days = max(1, min(int(days or 7), 7))
    loc = (location or "").strip()

    # Try parse lat,lon
    lat = lon = None
    if "," in loc:
        try:
            parts = [p.strip() for p in loc.split(",")]
            lat = float(parts[0])
            lon = float(parts[1])
        except Exception:
            lat = lon = None

    # Geocoding if needed
    if lat is None or lon is None:
        geocode_url = "https://geocoding-api.open-meteo.com/v1/search"
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(geocode_url, params={"name": loc, "count": 1})
            if r.status_code != 200:
                return f"Không thể xác định vị trí '{location}' (lỗi geocoding)."
            data = r.json()
            results = data.get("results") or []
            if not results:
                return f"Không tìm thấy vị trí '{location}'."
            lat = results[0]["latitude"]
            lon = results[0]["longitude"]

    # Fetch forecast
    forecast_url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
        "timezone": "Asia/Bangkok",
    }

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(forecast_url, params=params)
        if r.status_code != 200:
            return f"Không thể lấy dự báo cho {location}."
        data = r.json()
        daily = data.get("daily", {})
        dates = daily.get("time", [])[:days]
        max_t = daily.get("temperature_2m_max", [])[:days]
        min_t = daily.get("temperature_2m_min", [])[:days]
        precip = daily.get("precipitation_sum", [])[:days]

        if not dates:
            return f"Không có dữ liệu dự báo cho vị trí {location}."

        lines = []
        for d, mx, mn, pr in zip(dates, max_t, min_t, precip):
            lines.append(f"- {d}: {mn}°C - {mx}°C, mưa {pr} mm")

        return f"Dự báo thời tiết cho {location} trong {days} ngày:\n" + "\n".join(
            lines
        )
