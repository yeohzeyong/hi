"""Walking distance to the nearest MRT / LRT / Monorail station.

Station coordinates come from OpenStreetMap (Overpass API) and building
coordinates from Nominatim; both are cached in ``data/`` so each lookup is
done once, ever. You can pin any building's coordinates in
``data/building_overrides.yaml`` (lat/lon) if geocoding picks the wrong spot.
"""

from __future__ import annotations

import json
import logging
import math
import time
from pathlib import Path

import requests

from .config import DATA_DIR

log = logging.getLogger(__name__)

OVERPASS = "https://overpass-api.de/api/interpreter"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "malaysia-auction-tracker/1.0 (personal investment research)"}

STATIONS_FILE = DATA_DIR / "stations.json"
GEOCODE_FILE = DATA_DIR / "geocode_cache.json"


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def classify_station(tags: dict) -> str:
    blob = " ".join(str(tags.get(k, "")) for k in ("network", "name", "line", "station", "operator", "railway")).lower()
    if "mrt" in blob or "kajang line" in blob or "putrajaya line" in blob:
        return "MRT"
    if "monorail" in blob:
        return "Monorail"
    if "lrt" in blob or "light_rail" in blob or "kelana jaya" in blob or "ampang line" in blob or "sri petaling" in blob:
        return "LRT"
    if "ktm" in blob or "komuter" in blob:
        return "KTM"
    if "subway" in blob:
        return "MRT"
    return "Rail"


def fetch_stations(bbox) -> list[dict]:
    s, w, n, e = bbox
    q = f"""
    [out:json][timeout:60];
    (
      node["railway"="station"]({s},{w},{n},{e});
      node["public_transport"="station"]["train"="yes"]({s},{w},{n},{e});
      node["public_transport"="station"]["subway"="yes"]({s},{w},{n},{e});
      node["public_transport"="station"]["light_rail"="yes"]({s},{w},{n},{e});
      node["public_transport"="station"]["monorail"="yes"]({s},{w},{n},{e});
    );
    out body;
    """
    r = requests.post(OVERPASS, data={"data": q}, headers=HEADERS, timeout=120)
    r.raise_for_status()
    stations, seen = [], set()
    for el in r.json().get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name:en") or tags.get("name")
        if not name:
            continue
        key = (name.lower(), round(el["lat"], 3), round(el["lon"], 3))
        if key in seen:
            continue
        seen.add(key)
        stations.append({"name": name, "lat": el["lat"], "lon": el["lon"], "type": classify_station(tags)})
    return stations


def load_stations(bbox, refresh: bool = False) -> list[dict]:
    manual = DATA_DIR / "stations_manual.json"
    extra = json.loads(manual.read_text()) if manual.exists() else []
    if STATIONS_FILE.exists() and not refresh:
        return json.loads(STATIONS_FILE.read_text()) + extra
    try:
        stations = fetch_stations(bbox)
        STATIONS_FILE.write_text(json.dumps(stations, indent=1, ensure_ascii=False))
        log.info("Cached %d rail stations from OpenStreetMap", len(stations))
        return stations + extra
    except Exception as exc:
        log.warning("Could not load stations from Overpass: %s", exc)
        return extra


class Geocoder:
    def __init__(self, path: Path = GEOCODE_FILE):
        self.path = path
        self.cache: dict = json.loads(path.read_text()) if path.exists() else {}
        self._last = 0.0
        self.dirty = False

    def save(self):
        if self.dirty:
            self.path.write_text(json.dumps(self.cache, indent=1, ensure_ascii=False, sort_keys=True))
            self.dirty = False

    def lookup(self, query: str) -> tuple[float, float] | None:
        key = query.lower().strip()
        if key in self.cache:
            hit = self.cache[key]
            return (hit[0], hit[1]) if hit else None
        wait = 1.1 - (time.time() - self._last)   # Nominatim policy: 1 req/s
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()
        try:
            r = requests.get(NOMINATIM, params={"q": query, "format": "json", "limit": 1, "countrycodes": "my"},
                             headers=HEADERS, timeout=30)
            r.raise_for_status()
            res = r.json()
        except Exception as exc:
            log.warning("geocode failed for %r: %s", query, exc)
            return None              # don't cache transient failures
        hit = [float(res[0]["lat"]), float(res[0]["lon"])] if res else None
        self.cache[key] = hit
        self.dirty = True
        return tuple(hit) if hit else None

    def locate(self, building: str, address: str, area: str, state: str) -> tuple[float, float] | None:
        """Try the most specific query first; never fall back to a mere area centroid."""
        candidates = []
        if building:
            candidates.append(f"{building}, {area}, {state}")
            candidates.append(f"{building}, {state}")
        if address:
            candidates.append(address)
        for q in candidates:
            hit = self.lookup(q)
            if hit:
                return hit
        return None


def nearest_station(lat: float, lon: float, stations: list[dict], detour: float = 1.3) -> dict | None:
    best = None
    for st in stations:
        if st["type"] == "KTM":   # infrequent; not a renter magnet
            continue
        d = haversine_m(lat, lon, st["lat"], st["lon"]) * detour
        if best is None or d < best["walk_m"]:
            best = {"name": st["name"], "type": st["type"], "walk_m": round(d)}
    if best:
        best["walk_min"] = round(best["walk_m"] / 80)   # ~80 m per minute
    return best
