"""Find nearby pharmacies from OpenStreetMap and prepare user-controlled contact links."""
from __future__ import annotations

import json
import math
import re
import urllib.parse
import urllib.request

OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    value = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def _phone(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"[^+\d]", "", value)
    if not re.search(r"\d{8,}", cleaned):
        return None
    return cleaned


def nearby_pharmacies(payload: dict) -> dict:
    try:
        lat, lon = float(payload.get("latitude")), float(payload.get("longitude"))
        radius = min(50000, max(500, int(payload.get("radius_m", 5000))))
    except (TypeError, ValueError, OverflowError):
        raise ValueError("A valid location and search radius are required.")
    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("The location coordinates are invalid.")
    query = (f"[out:json][timeout:20];(node[\"amenity\"=\"pharmacy\"](around:{radius},{lat},{lon});"
             f"way[\"amenity\"=\"pharmacy\"](around:{radius},{lat},{lon});"
             f"relation[\"amenity\"=\"pharmacy\"](around:{radius},{lat},{lon}););out center tags;")
    request = urllib.request.Request(
        OVERPASS_URL, data=urllib.parse.urlencode({"data": query}).encode(),
        headers={"User-Agent": "DawaLink/1.0 (Moroccan pharmacy finder)", "Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, TimeoutError, json.JSONDecodeError) as error:
        raise ConnectionError("OpenStreetMap pharmacy search is temporarily unavailable. Try again or open the map search.") from error
    message = str(payload.get("message", "")).strip()[:1200]
    results = []
    seen = set()
    for entry in data.get("elements", []):
        tags = entry.get("tags") or {}
        point = entry.get("center") or entry
        try:
            p_lat, p_lon = float(point["lat"]), float(point["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        identity = (round(p_lat, 5), round(p_lon, 5), tags.get("name", ""))
        if identity in seen:
            continue
        seen.add(identity)
        phone = _phone(tags.get("contact:phone") or tags.get("phone") or tags.get("contact:mobile"))
        whatsapp = _phone(tags.get("contact:whatsapp"))
        if whatsapp and whatsapp.startswith("0") and len(whatsapp) == 10:
            whatsapp = "212" + whatsapp[1:]
        email = (tags.get("contact:email") or tags.get("email") or "").strip()[:160]
        distance = _distance_km(lat, lon, p_lat, p_lon)
        results.append({
            "name": (tags.get("name") or tags.get("name:fr") or "Pharmacie").strip()[:120],
            "distance_km": round(distance, 2), "latitude": p_lat, "longitude": p_lon,
            "address": ", ".join(x for x in (tags.get("addr:street"), tags.get("addr:housenumber"), tags.get("addr:city")) if x)[:180],
            "phone": phone, "whatsapp": whatsapp, "email": email if "@" in email else None,
            "osm_url": f"https://www.openstreetmap.org/{entry.get('type','node')}/{entry.get('id')}",
            "directions_url": "https://www.google.com/maps/dir/?api=1&destination=" + urllib.parse.quote(f"{p_lat},{p_lon}"),
            "message": message,
        })
    results.sort(key=lambda pharmacy: pharmacy["distance_km"])
    return {"pharmacies": results[:12], "source": "OpenStreetMap contributors", "searched_radius_m": radius,
            "map_search_url": "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote(f"pharmacy near {lat},{lon}")}
