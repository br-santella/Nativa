"""Recent point estimates from public providers; no local engine datasets required."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
import math
import logging
import time

import requests

log = logging.getLogger(__name__)


# Last valid NDVI per point is kept on disk: MOD13Q1 only changes every 16 days and the ORNL
# service often takes ~17 s per request, so a fresh copy skips the network and an expired one
# covers provider outages.
NDVI_CACHE_TTL = 3 * 24 * 3600  # s
ORNL_READ_TIMEOUT = 40  # s; the frontend gives the whole endpoint 50 s


@lru_cache(maxsize=128)
def _cached_json(url, params, bucket, read_timeout=18):
    response = requests.get(url, params=dict(params), timeout=(4, read_timeout), headers={"Accept": "application/json"})
    response.raise_for_status()
    return response.json()


def _get(url, read_timeout=18, **params):
    return _cached_json(url, tuple(sorted(params.items())), int(time.time() // 21600), read_timeout)


def _number(value, low, high):
    return isinstance(value, (int, float)) and math.isfinite(value) and low <= value <= high


def _card(source, url, unit, series=(), value=None, delta=None, comparison=None):
    valid = [p for p in series if p["value"] is not None]
    return dict(source=source, url=url, unit=unit, series=list(series), value=value, delta=delta,
                comparison=comparison, start=valid[0]["date"] if valid else None,
                end=valid[-1]["date"] if valid else None)


def power(lat, lon, today):
    data = _get("https://power.larc.nasa.gov/api/temporal/daily/point", parameters="T2M,PRECTOTCORR", community="AG", latitude=lat, longitude=lon,
                start=(today-timedelta(days=75)).strftime("%Y%m%d"), end=(today-timedelta(days=1)).strftime("%Y%m%d"), format="JSON")
    result = {}
    for key, parameter, unit, bounds in [("temperature", "T2M", "C", (-100, 70)), ("precipitation", "PRECTOTCORR", "mm/day", (0, 3000))]:
        if data["parameters"][parameter]["units"] != unit:
            raise ValueError("Unexpected provider units")
        values = {datetime.strptime(k, "%Y%m%d").date(): v for k, v in data["properties"]["parameter"][parameter].items() if _number(v, *bounds)}
        end = max(values) if values else today-timedelta(days=1)
        def window(offset):
            return [{"date": (end-timedelta(days=n)).isoformat(), "value": values.get(end-timedelta(days=n))} for n in range(offset+29, offset-1, -1)]
        current, previous = window(0), window(30)
        def aggregate(points):
            if any(p["value"] is None for p in points):
                return None
            total = sum(p["value"] for p in points)
            return total / 30 if key == "temperature" else total
        value, before = aggregate(current), aggregate(previous)
        delta = None if value is None or before is None else (value-before if key == "temperature" else (100*(value-before)/before if before else None))
        result[key] = _card("NASA POWER", "https://power.larc.nasa.gov/", "°C" if key == "temperature" else "mm", current, value, delta, "previous_30_days")
    return result


def soil(lat, lon, today):
    data = _get("https://archive-api.open-meteo.com/v1/archive", latitude=lat, longitude=lon, start_date=(today-timedelta(days=25)).isoformat(), end_date=(today-timedelta(days=5)).isoformat(), daily="soil_moisture_0_to_7cm_mean", models="era5_land", timezone="America/Sao_Paulo")
    if data["daily_units"]["soil_moisture_0_to_7cm_mean"] != "m³/m³":
        raise ValueError("Unexpected soil units")
    series = [{"date": d, "value": v*100 if _number(v, 0, 1) else None} for d, v in zip(data["daily"]["time"], data["daily"]["soil_moisture_0_to_7cm_mean"], strict=True)]
    valid = [p for p in series if p["value"] is not None]
    latest = valid[-1] if valid else None
    prior_date = (date.fromisoformat(latest["date"])-timedelta(days=7)).isoformat() if latest else None
    prior = next((p["value"] for p in series if p["date"] == prior_date), None)
    return {"moisture": _card("Open-Meteo · ERA5-Land", "https://open-meteo.com/en/docs/historical-weather-api", "%", series, latest["value"] if latest else None, latest["value"]-prior if latest and prior is not None else None, "previous_week")}


def _modis_date(day):
    """MOD13Q1 composite (A<year><doy>) containing `day`; composites start every 16 days from 1 Jan."""
    doy = (day.timetuple().tm_yday-1)//16*16+1
    return f"A{day.year}{doy:03d}"


def _fetch_vegetation(lat, lon, today):
    # One subset request over the last ~90 days (about 6 composites) instead of /dates + /subset.
    data = _get("https://modis.ornl.gov/rst/api/v1/MOD13Q1/subset", read_timeout=ORNL_READ_TIMEOUT, latitude=lat, longitude=lon,
                startDate=_modis_date(today-timedelta(days=90)), endDate=_modis_date(today), kmAboveBelow=0, kmLeftRight=0)
    rows = {(r["calendar_date"], r["band"]): r["data"] for r in data["subset"]}
    days = sorted({day for day, _ in rows if day <= (today-timedelta(days=16)).isoformat()})[-4:]
    series = []
    for day in days:
        raw = rows.get((day, "250m_16_days_NDVI"), [])
        qa = rows.get((day, "250m_16_days_pixel_reliability"), [])
        value = raw[0]*0.0001 if len(raw) == len(qa) == 1 and qa[0] in (0, 1) and _number(raw[0], -2000, 10000) else None
        series.append({"date": day, "value": value})
    valid = [p for p in series if p["value"] is not None]
    if not valid:
        # Nothing usable (e.g. only cloudy composites): fall back to the last cached reading.
        raise ValueError("All NDVI composites masked")
    latest = valid[-1]
    index = series.index(latest)
    previous = series[index-1]["value"] if index else None
    return {"vegetation": _card("NASA MODIS · ORNL DAAC", "https://modis.ornl.gov/data/modis_webservice.html", "NDVI", series, latest["value"], latest["value"]-previous if previous is not None else None, "previous_composite")}


def vegetation(lat, lon, today):
    from field_shift.context._base import com_cache

    # ~110 m key: well inside a 250 m MODIS pixel.
    result, _ = com_cache(f"ndvi_{lat:.3f}_{lon:.3f}", NDVI_CACHE_TTL, lambda: _fetch_vegetation(lat, lon, today))
    return result


def monitor(lat, lon):
    today = datetime.now(timezone.utc).date()
    indicators = {k: _card(s, u, unit) for k, s, u, unit in [
        ("temperature", "NASA POWER", "https://power.larc.nasa.gov/", "°C"),
        ("precipitation", "NASA POWER", "https://power.larc.nasa.gov/", "mm"),
        ("moisture", "Open-Meteo · ERA5-Land", "https://open-meteo.com/", "%"),
        ("vegetation", "NASA MODIS · ORNL DAAC", "https://modis.ornl.gov/", "NDVI")]}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(provider, round(lat, 5), round(lon, 5), today) for provider in (power, soil, vegetation)]
        for future in futures:
            try:
                indicators.update(future.result())
            except (requests.RequestException, ValueError, KeyError, TypeError, IndexError):
                # A provider outage must not discard measurements from other providers.
                log.warning("Monitoring provider unavailable", exc_info=True)
                continue
    return {"point": {"lat": lat, "lon": lon}, "queried_at": datetime.now(timezone.utc).isoformat(), "indicators": indicators}
