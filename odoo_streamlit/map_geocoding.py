"""Géocodage des codes postaux et des adresses, sans clé Google.

La recherche de lieux reste distincte des recherches de prospects Odoo.
"""

import json
import re
import urllib.error
import urllib.parse
import urllib.request


class GeocodingError(Exception):
    """Erreur de recherche de lieu présentable au commercial."""


def _fetch_json(url):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "ABM-Cartographie/1.0", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=9) as response:
            return json.load(response)
    except (OSError, ValueError, UnicodeError) as exc:
        raise GeocodingError("Le service de recherche géographique ne répond pas.") from exc


def _point(geometry):
    if not isinstance(geometry, dict):
        return None
    coords = geometry.get("coordinates")
    if not isinstance(coords, (list, tuple)) or len(coords) < 2:
        return None
    try:
        lon, lat = float(coords[0]), float(coords[1])
    except (TypeError, ValueError):
        return None
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        return None
    return lat, lon


def search_location(query):
    """Retourne jusqu'à six positions françaises à afficher sur la carte.

    Un code postal seul passe par le référentiel communal officiel : la
    recherche d'adresses ne retourne pas toujours les CP isolés.
    """
    query = str(query or "").strip()[:140]
    if len(query) < 2:
        return []

    if re.fullmatch(r"\\d{5}", query):
        url = (
            "https://geo.api.gouv.fr/communes?codePostal="
            + urllib.parse.quote(query)
            + "&fields=nom,centre,codesPostaux&format=json&geometry=centre"
        )
        payload = _fetch_json(url)
        if not isinstance(payload, list):
            return []
        results = []
        for commune in payload[:20]:
            point = _point(commune.get("centre"))
            if point:
                results.append({
                    "label": f"{query} · {commune.get('nom', 'Commune')}",
                    "lat": point[0],
                    "lon": point[1],
                    "zoom": 11,
                })
        return results[:6]

    url = (
        "https://data.geopf.fr/geocodage/search?q="
        + urllib.parse.quote(query)
        + "&limit=6"
    )
    payload = _fetch_json(url)
    results = []
    for feature in payload.get("features", [])[:6]:
        if not isinstance(feature, dict):
            continue
        point = _point(feature.get("geometry"))
        if point is None:
            continue
        props = feature.get("properties") or {}
        label = str(props.get("label") or props.get("name") or query)[:180]
        kind = str(props.get("type") or "")
        results.append({
            "label": label,
            "lat": point[0],
            "lon": point[1],
            "zoom": 11 if kind in ("municipality", "city") else 14,
        })
    return results
